"""The comms-native WhatsApp archive (D39-PRE Task E10b; owner decision, 2026-09-25).

``CommsArchive`` is the webhook worker's ``Archive``: it parses a verified webhook body with
WhatsVault's public, pure normaliser (``split_webhook``, ``classify``, ``to_rows``,
``semantic_key``) and keeps each inbound or echoed message once, keyed by its semantic key, so a
redelivery or a crash between the archive and its inbox flag changes nothing. Statuses are not
messages (the worker applies them as provider updates). A body that does not parse raises
``ValueError``, which the worker counts as malformed.

``ArchiveContext`` is the ``whatsapp_webhook_archive`` context source: one conversation, newest
first, with an opaque numeric cursor, or the messages around one of them (G1). A conversation is ``group:<group_id>`` for a message Meta
marks with a ``group_id`` (the Groups API), else the contact's number: the same identities the
directory's WhatsApp destinations and contact points use. Provider text and names go
under ``untrusted`` (A32); the context engine drops the provider identities.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

# WhatsVault ships no py.typed marker; its normaliser is pure and has its own suite
from whatsvault.ingest import normalise  # type: ignore[import-untyped]

from comms.core import timeutil
from comms.core.providers.protocols import ContextPage, ContextQuery, ContextRefused
from comms.core.storage.db import write_tx

__all__ = ["PROVENANCE", "ArchiveContext", "CommsArchive"]

PROVENANCE = "whatsapp_webhook_archive"
_MESSAGES = frozenset({"MESSAGE_INBOUND", "MESSAGE_ECHO"})
_MAX_LIMIT = 50


class CommsArchive:
    def __init__(self, conn: Any, *, clock: Callable[[], datetime]) -> None:
        self._conn, self._clock = conn, clock

    def __repr__(self) -> str:
        return "CommsArchive(<redacted>)"

    def ingest(self, raw: bytes) -> None:
        try:
            payload = json.loads(raw)
            atoms = normalise.split_webhook(payload) if isinstance(payload, dict) else None
        except (ValueError, TypeError, AttributeError):
            raise ValueError("the webhook body is not a Meta webhook") from None
        if atoms is None:
            raise ValueError("the webhook body is not a Meta webhook")
        received = timeutil.iso(self._clock())
        with write_tx(self._conn):
            for atom in atoms:
                family, key = normalise.semantic_key(atom)
                if family not in _MESSAGES:
                    continue
                rows = normalise.to_rows(atom)
                message, contact = rows["message"], rows["contact"]
                if not message.get("wamid") or not contact.get("wa_id"):
                    continue
                group = (atom.get("raw") or {}).get("group_id")
                chat = f"group:{group}" if group else str(contact["wa_id"])
                sent = datetime.fromtimestamp(message["ts_lower_ms"] / 1000, UTC)
                self._conn.execute(
                    "INSERT INTO whatsapp_messages (semantic_key, phone_number_id, chat,"
                    " sender_wa_id, wamid, direction, type, body, sender_name, sent_at,"
                    " received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (semantic_key) DO NOTHING",
                    (
                        key,
                        message.get("phone_number_id"),
                        chat,
                        str(contact["wa_id"]),
                        str(message["wamid"]),
                        message["direction"],
                        str(message.get("type") or "text"),
                        message.get("text_original"),
                        contact.get("name"),
                        timeutil.iso(sent),
                        received,
                    ),
                )


class ArchiveContext:
    """The archive as a context source for one WhatsApp conversation: ``recent`` (paged) and
    ``around`` one message (newest first, as Telegram's history reads are). Any other kind is
    refused ``PROVIDER_UNSUPPORTED``: the archive has no thread or search index (G1 found every
    kind was served as ``recent``)."""

    def __init__(self, conn: Any, *, clock: Callable[[], datetime]) -> None:
        self._conn, self._clock = conn, clock

    def __repr__(self) -> str:
        return "ArchiveContext(<redacted>)"

    def read(self, query: ContextQuery) -> ContextPage:
        identity = query.target.identity
        chat = identity if identity.startswith("group:") else identity.removeprefix("+")
        if query.kind == "recent":
            return self._recent(chat, query.args)
        if query.kind == "around":
            return self._around(chat, query.args)
        raise ContextRefused("PROVIDER_UNSUPPORTED")

    def _recent(self, chat: str, args: Mapping[str, Any]) -> ContextPage:
        limit = min(int(args.get("limit") or 20), _MAX_LIMIT)
        cursor = args.get("cursor")
        before = int(cursor) if isinstance(cursor, str) and cursor.isdigit() else None
        # page by (sent_at, id): messages can arrive out of their send order
        edge = None
        if before is not None:
            edge = self._conn.execute(
                "SELECT sent_at FROM whatsapp_messages WHERE id = ? AND chat = ?", (before, chat)
            ).fetchone()
            if edge is None:
                return ContextPage((), PROVENANCE, None)
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_messages"
            " WHERE chat = ? AND (? IS NULL OR sent_at < ? OR (sent_at = ? AND id < ?))"
            " ORDER BY sent_at DESC, id DESC LIMIT ?",
            (chat, before, *(edge or (None,)) * 2, before, limit + 1),
        ).fetchall()
        more = len(rows) > limit
        items = self._items(rows[:limit])
        return ContextPage(items, PROVENANCE, str(rows[limit - 1][0]) if more else None)

    def _around(self, chat: str, args: Mapping[str, Any]) -> ContextPage:
        wamid, before, after = args.get("message_id"), args.get("before", 10), args.get("after", 10)
        if not isinstance(wamid, str) or not all(
            type(n) is int and 0 <= n <= _MAX_LIMIT for n in (before, after)
        ):
            raise ValueError("around arguments refused")
        anchor = self._conn.execute(
            "SELECT id, sent_at FROM whatsapp_messages WHERE chat = ? AND wamid = ?",
            (chat, wamid),
        ).fetchone()
        if anchor is None:
            raise ContextRefused("TARGET_NOT_FOUND")
        key = (anchor[1], anchor[1], anchor[0])
        newer = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_messages WHERE chat = ?"
            " AND (sent_at > ? OR (sent_at = ? AND id > ?)) ORDER BY sent_at, id LIMIT ?",
            (chat, *key, after),
        ).fetchall()
        older = self._conn.execute(
            f"SELECT {_COLUMNS} FROM whatsapp_messages WHERE chat = ?"
            " AND (sent_at < ? OR (sent_at = ? AND id <= ?)) ORDER BY sent_at DESC, id DESC"
            " LIMIT ?",
            (chat, *key, before + 1),
        ).fetchall()
        return ContextPage(self._items([*reversed(newer), *older]), PROVENANCE, None)

    def _items(self, rows: list[Any]) -> tuple[dict[str, Any], ...]:
        observed = timeutil.iso(self._clock())
        return tuple(
            {
                "source": PROVENANCE,
                "observed_at": observed,
                "message_id": wamid,
                "sent_at": sent_at,
                "direction": direction,
                "type": kind,
                "untrusted": {"text": body, "sender_name": name},
            }
            for _id, wamid, direction, kind, body, name, sent_at in rows
        )


_COLUMNS = "id, wamid, direction, type, body, sender_name, sent_at"
