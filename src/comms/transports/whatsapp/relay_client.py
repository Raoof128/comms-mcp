"""The relay's HTTP client (comms v0.3 A48): the daemon's only route to the Cloudflare relay.

One pinned origin (``transports.net.pinned_client``), no redirect, and every request signed
with the pull key (``comms.core.relay_sig``). A pull returns only ciphertext; an ack is
idempotent. Errors carry fixed messages: never the URL, the key or a body.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from comms.core import relay_sig
from comms.core.strict_json import strict_json_loads
from comms.transports.net import DownloadRefused, pinned_client, read_capped

__all__ = ["PAGE_LIMIT", "RelayClient", "RelayPage", "RelayRefused", "RelayRow", "RelayUnavailable"]

PAGE_LIMIT = 50
# A page is at most 256 KiB of ciphertext, or one row of up to about 1.4 MB: base64 and JSON
# stay well under this.
_MAX_RESPONSE = 4 * 1024 * 1024
_TIMEOUT_S = 10.0
_ROW_KEYS = {"seq", "received_at", "batch", "part", "parts", "ciphertext_b64"}
_PAGE_KEYS = {"rows", "purged_through", "depth", "oldest_received_at"}


class RelayUnavailable(Exception):
    """The relay could not be reached or answered something unusable."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"relay unavailable: {stage}")
        self.stage = stage


class RelayRefused(Exception):
    """The relay answered with a refusal. ``skew`` is the relay clock minus ours, in seconds,
    when the answer carried a ``Date`` header (a 401 with a large skew is a clock problem)."""

    def __init__(self, status: int, skew: int | None) -> None:
        super().__init__(f"relay refused: {status}")
        self.status, self.skew = status, skew


@dataclass(frozen=True)
class RelayRow:
    seq: int
    received_at: int  # unix milliseconds, the relay's clock
    batch: str
    part: int
    parts: int
    ciphertext: bytes = field(repr=False)


@dataclass(frozen=True)
class RelayPage:
    rows: tuple[RelayRow, ...]
    purged_through: int
    depth: int
    oldest_received_at: int | None


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("not a count")
    return value


def _row(value: Any) -> RelayRow:
    if not isinstance(value, dict) or set(value) != _ROW_KEYS:
        raise ValueError("row shape")
    batch = value["batch"]
    if (
        not isinstance(batch, str)
        or len(batch) != 32
        or not all(c in "0123456789abcdef" for c in batch)
    ):
        raise ValueError("batch")
    try:
        ciphertext = base64.b64decode(value["ciphertext_b64"], validate=True)
    except (binascii.Error, TypeError):
        raise ValueError("ciphertext") from None
    row = RelayRow(
        _count(value["seq"]),
        _count(value["received_at"]),
        batch,
        _count(value["part"]),
        _count(value["parts"]),
        ciphertext,
    )
    if row.seq < 1 or row.parts < 1 or row.part >= row.parts:
        raise ValueError("row fields")
    return row


def _page(raw: bytes) -> RelayPage:
    value = strict_json_loads(raw.decode("utf-8"))
    if (
        not isinstance(value, dict)
        or set(value) != _PAGE_KEYS
        or not isinstance(value["rows"], list)
    ):
        raise ValueError("page shape")
    rows = tuple(_row(r) for r in value["rows"])
    if [r.seq for r in rows] != sorted({r.seq for r in rows}):
        raise ValueError("rows out of order")
    oldest = value["oldest_received_at"]
    return RelayPage(
        rows,
        _count(value["purged_through"]),
        _count(value["depth"]),
        None if oldest is None else _count(oldest),
    )


class RelayClient:
    def __init__(
        self,
        base_url: str,
        pull_key: bytes,
        *,
        clock: Callable[[], float] = time.time,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if len(pull_key) != 32:
            raise ValueError("the relay pull key is 32 bytes")
        self._key, self._clock = pull_key, clock
        self._client = pinned_client(base_url, timeout=_TIMEOUT_S, transport=transport)
        self._origin = base_url.rstrip("/")

    def __repr__(self) -> str:
        return "RelayClient(<redacted>)"

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, fields: dict[str, int]) -> bytes:
        body = json.dumps(fields, separators=(",", ":"), sort_keys=True).encode("ascii")
        now = int(self._clock())
        headers = {
            "content-type": "application/json",
            "x-comms-timestamp": str(now),
            "x-comms-signature": relay_sig.sign(self._key, "POST", path, now, body),
        }
        try:
            with self._client.stream(
                "POST", self._origin + path, content=body, headers=headers
            ) as response:
                if response.status_code != 200:
                    raise RelayRefused(response.status_code, _skew(response, now))
                return read_capped(
                    response, limit=_MAX_RESPONSE, deadline=time.monotonic() + _TIMEOUT_S
                )
        except httpx.HTTPError:
            raise RelayUnavailable("network") from None
        except DownloadRefused:
            raise RelayUnavailable("response") from None

    def pull(self, after: int, limit: int = PAGE_LIMIT) -> RelayPage:
        raw = self._post("/pull", {"after": int(after), "limit": int(limit)})
        try:
            return _page(raw)
        except (ValueError, UnicodeDecodeError):
            raise RelayUnavailable("malformed") from None

    def ack(self, through: int) -> int:
        raw = self._post("/ack", {"through": int(through)})
        try:
            value = strict_json_loads(raw.decode("utf-8"))
            if not isinstance(value, dict) or set(value) != {"deleted"}:
                raise ValueError("ack shape")
            return _count(value["deleted"])
        except (ValueError, UnicodeDecodeError):
            raise RelayUnavailable("malformed") from None


def _skew(response: httpx.Response, now: int) -> int | None:
    date = response.headers.get("date")
    if date is None:
        return None
    try:
        return int(parsedate_to_datetime(date).timestamp()) - now
    except (TypeError, ValueError):
        return None
