"""The relay collector (comms v0.3 A48): WhatsApp webhooks the Cloudflare relay held while the
daemon was off, brought home.

Each tick pulls pages in ``seq`` order. For each row it decrypts with the ``relay-age-key``
identity, checks the envelope, reassembles a batch's parts, and verifies Meta's
``X-Hub-Signature-256`` with the app secret (the only place it is checked, D-R1) through the one
shared rule. A verified body goes to the inbox, which commits it; a row that fails anywhere is
quarantined in comms.db with its ciphertext (an ack is cumulative, so the relay will not keep
it). Only then does progress move and the relay get its ack. A crash between the inbox commit
and the ack re-pulls the same rows, and the inbox and the archive each deduplicate them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from comms.core import timeutil
from comms.core.backup import age
from comms.core.storage.db import write_tx
from comms.core.strict_json import strict_json_loads
from comms.transports.whatsapp.relay_client import (
    RelayClient,
    RelayRefused,
    RelayRow,
    RelayUnavailable,
)
from comms.transports.whatsapp.webhooks.inbox import Inbox
from comms.transports.whatsapp.webhooks.ingress import MAX_BODY_BYTES
from comms.transports.whatsapp.webhooks.signature import meta_signed

__all__ = ["CLOCK_WINDOW_S", "CollectReport", "Collector"]

CLOCK_WINDOW_S = 300  # the relay refuses a pull whose timestamp is further off than this
_PAGES_PER_TICK = 40
_QUARANTINE_KEEP_BYTES = 64 * 1024 * 1024  # beyond this, a refused row keeps its digest only
_ENVELOPE_KEYS = {"batch", "part", "parts", "raw_b64", "received_at", "signature"}


@dataclass(frozen=True)
class CollectReport:
    pulled: int = 0
    stored: int = 0
    quarantined: int = 0
    acked_through: int = 0
    error: str | None = None


class _Refused(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _envelope(row: RelayRow, identities: Sequence[str]) -> tuple[bytes, bytes]:
    """The row's raw slice and signature header, once its ciphertext and envelope check out."""
    plain = None
    for identity in identities:
        try:
            plain = age.decrypt(row.ciphertext, identity)
            break
        except age.AgeError:
            continue
    if plain is None:
        raise _Refused("decrypt")
    try:
        value = strict_json_loads(plain.decode("utf-8"))
        if not isinstance(value, dict) or set(value) != _ENVELOPE_KEYS:
            raise ValueError("envelope shape")
        if (value["batch"], value["part"], value["parts"]) != (row.batch, row.part, row.parts):
            raise ValueError("envelope does not match its row")
        signature = value["signature"]
        if not isinstance(signature, str) or not signature.isascii():
            raise ValueError("signature header")
        return base64.b64decode(value["raw_b64"], validate=True), signature.encode("ascii")
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        raise _Refused("envelope") from None


class Collector:
    def __init__(
        self,
        conn: Any,
        client: RelayClient,
        inbox: Inbox,
        *,
        identities: Sequence[str],
        app_secret: bytes,
        clock: Callable[[], datetime],
        on_verified: Callable[[str], None] | None = None,
    ) -> None:
        if not identities or not app_secret:
            raise ValueError("the relay collector needs its identity and the app secret")
        self._conn, self._client, self._inbox = conn, client, inbox
        self._identities, self._secret, self._clock = tuple(identities), app_secret, clock
        self._on_verified = on_verified  # R-E6: the app secret is confirmed in operation

    def __repr__(self) -> str:
        return "Collector(<redacted>)"

    # -- state --------------------------------------------------------------------------------

    def _state(self) -> tuple[int, int]:
        with write_tx(self._conn):
            self._conn.execute(
                "INSERT INTO relay_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
            )
        row = self._conn.execute(
            "SELECT acked_through, purged_through FROM relay_state WHERE id = 1"
        ).fetchone()
        return int(row[0]), int(row[1])

    def _failed(self, error: str, skew: int | None = None) -> CollectReport:
        now = timeutil.iso(self._clock())
        with write_tx(self._conn):
            self._conn.execute(
                "UPDATE relay_state SET last_attempt_at = ?, last_error = ?, clock_skew_s = ?"
                " WHERE id = 1",
                (now, error, skew),
            )
        return CollectReport(error=error)

    def _quarantine(self, rows: Sequence[RelayRow], reason: str) -> None:
        kept = self._conn.execute(
            "SELECT coalesce(sum(length(ciphertext)), 0) FROM relay_quarantine"
        ).fetchone()[0]
        now = timeutil.iso(self._clock())
        for row in rows:
            keep = kept + len(row.ciphertext) <= _QUARANTINE_KEEP_BYTES
            kept += len(row.ciphertext) if keep else 0
            self._conn.execute(
                "INSERT INTO relay_quarantine (seq, reason, ciphertext_sha256, ciphertext,"
                " quarantined_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT (seq) DO NOTHING",
                (
                    row.seq,
                    reason,
                    hashlib.sha256(row.ciphertext).hexdigest(),
                    row.ciphertext if keep else None,
                    now,
                ),
            )

    # -- one tick -----------------------------------------------------------------------------

    def run_once(self) -> CollectReport:
        acked, purged = self._state()
        pulled = stored = quarantined = 0
        pending: list[RelayRow] = []  # the parts of one batch, in order, not yet complete
        cursor, drained = acked, False
        with write_tx(self._conn):
            self._conn.execute(
                "UPDATE relay_state SET last_attempt_at = ? WHERE id = 1",
                (timeutil.iso(self._clock()),),
            )
        for _ in range(_PAGES_PER_TICK):
            try:
                page = self._client.pull(cursor)
            except RelayRefused as refused:
                clock = refused.status == 401 and abs(refused.skew or 0) > CLOCK_WINDOW_S
                return self._failed("clock" if clock else "refused", refused.skew)
            except RelayUnavailable as unavailable:
                return self._failed(
                    "malformed" if unavailable.stage == "malformed" else "unreachable"
                )
            purged = max(purged, page.purged_through)
            self._record_page(page.purged_through, page.depth, page.oldest_received_at)
            if not page.rows:
                drained = True
                break
            if page.rows[0].seq <= cursor:
                return self._failed("malformed")  # the relay went backwards
            for row in page.rows:
                self._gap(cursor, row.seq, purged)
                cursor = row.seq
                pulled += 1
                done, n_stored, n_quarantined = self._take(row, pending)
                stored += n_stored
                quarantined += n_quarantined
                if done:
                    acked = self._advance(row.seq)
        if pending and drained:  # the relay stores a batch in one transaction: a part is lost
            with write_tx(self._conn):
                self._quarantine(pending, "parts")
            quarantined += len(pending)
            acked = self._advance(pending[-1].seq)
        if acked > 0:
            try:
                self._client.ack(acked)
            except (RelayRefused, RelayUnavailable):
                pass  # the relay deletes these on the next successful ack (cumulative)
        with write_tx(self._conn):
            self._conn.execute(
                "UPDATE relay_state SET last_success_at = ?, last_error = NULL, clock_skew_s = NULL"
                " WHERE id = 1",
                (timeutil.iso(self._clock()),),
            )
        return CollectReport(pulled, stored, quarantined, acked)

    def _record_page(self, purged: int, depth: int, oldest: int | None) -> None:
        oldest_at = (
            None if oldest is None else timeutil.iso(datetime.fromtimestamp(oldest / 1000, UTC))
        )
        with write_tx(self._conn):
            self._conn.execute(
                "UPDATE relay_state SET purged_through = max(purged_through, ?), depth = ?,"
                " oldest_received_at = ? WHERE id = 1",
                (purged, depth, oldest_at),
            )

    def _gap(self, previous: int, seq: int, purged: int) -> None:
        """Rows the relay no longer has that were neither acked nor purged by age."""
        low = max(previous, purged) + 1
        if seq > low:
            with write_tx(self._conn):
                self._conn.execute(
                    "INSERT INTO relay_gaps (from_seq, to_seq, found_at) VALUES (?, ?, ?)",
                    (low, seq - 1, timeutil.iso(self._clock())),
                )

    def _advance(self, seq: int) -> int:
        with write_tx(self._conn):
            self._conn.execute(
                "UPDATE relay_state SET acked_through = max(acked_through, ?) WHERE id = 1", (seq,)
            )
        return seq

    def _take(self, row: RelayRow, pending: list[RelayRow]) -> tuple[bool, int, int]:
        """Handle one row: ``(complete, stored, quarantined)``. ``complete`` means every row up
        to this one is settled, so progress may move past it."""
        quarantined = 0
        if pending and (row.batch != pending[0].batch or row.part != len(pending)
                        or row.seq != pending[-1].seq + 1):  # fmt: skip
            with write_tx(self._conn):
                self._quarantine(pending, "parts")  # a batch that never finished
            quarantined += len(pending)
            pending.clear()
        if not pending and row.part != 0:
            with write_tx(self._conn):
                self._quarantine([row], "parts")
            return True, 0, quarantined + 1
        pending.append(row)
        if len(pending) < row.parts:
            return False, 0, quarantined
        rows = list(pending)
        pending.clear()
        try:
            opened = [_envelope(r, self._identities) for r in rows]
        except _Refused as refused:
            with write_tx(self._conn):
                self._quarantine(rows, refused.reason)
            return True, 0, quarantined + len(rows)
        raw = b"".join(part for part, _signature in opened)
        if len(raw) > MAX_BODY_BYTES or not meta_signed(self._secret, raw, opened[0][1]):
            with write_tx(self._conn):
                self._quarantine(rows, "signature")
            return True, 0, quarantined + len(rows)
        if self._on_verified is not None:
            self._on_verified("meta-app-secret")
        self._inbox.store(raw)  # commits; a re-pulled body is deduplicated by its SHA-256
        return True, 1, quarantined
