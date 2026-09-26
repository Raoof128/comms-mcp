"""The Bot API context source (comms v0.3 Task C13; P §19–21; A32).

A bot sees only what Telegram gives it now and what this installation retained as it arrived
(P §20). ``info`` reads current provider data (chat, administrators, member count) and is
``telegram_live``; ``recent`` pages the locally retained updates for the chat and is
``telegram_local``; ``from`` pages one sender's retained updates in a group (G5). History,
search and member enumeration are ``PROVIDER_UNSUPPORTED`` and
never reach Telegram: the bot never presents local retention as full history. Every item
carries its ``source`` and ``observed_at`` (P §21); provider text sits under ``untrusted``
(A32). A failed live lookup refuses the whole read rather than returning part of it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from comms.core import timeutil
from comms.core.delivery.transport import ResultKind
from comms.core.providers.protocols import ContextPage, ContextQuery, ContextRefused
from comms.transports.telegram.args import CHAT_PERMISSIONS, positive_int, take
from comms.transports.telegram.bot.classify import LookupFailed, lookup
from comms.transports.telegram.bot.http import BotApi

__all__ = ["BotContext"]

ACTOR = "telegram_bot"
MAX_LIMIT = 100


_LOOKUP_CODES = {ResultKind.FAILED_PERMANENT: "NOT_AUTHORIZED"}


class BotContext:
    def __init__(self, api: BotApi, conn: Any, *, clock: Callable[[], datetime]) -> None:
        self._api, self._conn, self._clock = api, conn, clock

    def __repr__(self) -> str:
        return "BotContext(<redacted>)"

    def read(self, query: ContextQuery) -> ContextPage:
        if query.target.actor != ACTOR:
            raise ValueError("not a telegram_bot destination")
        chat_id = int(query.target.identity)
        if query.kind == "info":
            take(query.args, {}, {})
            return self._info(chat_id)
        if query.kind == "recent":
            args = take(query.args, {}, {"limit": _limit, "cursor": _cursor})
            return self._recent(chat_id, args.get("limit", 20), args.get("cursor"))
        if query.kind == "admins":  # G6: getChatAdministrators, bots included
            take(query.args, {}, {})
            return self._admins(chat_id)
        if query.kind == "member":  # G6: one member's standing
            args = take(query.args, {"user_id": _sender}, {})
            return self._member(chat_id, int(args["user_id"]))
        if query.kind == "permissions":  # G6: the chat's default permissions
            take(query.args, {}, {})
            return self._permissions(chat_id)
        if query.kind == "join_requests":  # G6: retained chat_join_request updates
            args = take(query.args, {}, {"limit": _limit, "cursor": _cursor})
            return self._recent(
                chat_id, args.get("limit", 20), args.get("cursor"), kind="chat_join_request"
            )
        if query.kind == "around":  # G6: retained updates around one message
            args = take(query.args, {"message_id": _positive}, {"before": _span, "after": _span})
            return self._around(chat_id, args["message_id"], args.get("before", 10),
                                args.get("after", 10))  # fmt: skip
        if query.kind == "from" and chat_id < 0:  # one sender in a group (G5), retained only
            args = take(query.args, {"sender": _sender}, {"limit": _limit, "cursor": _cursor})
            return self._recent(
                chat_id, args.get("limit", 20), args.get("cursor"), sender=int(args["sender"])
            )
        raise ContextRefused("PROVIDER_UNSUPPORTED")

    def _info(self, chat_id: int) -> ContextPage:
        try:
            chat = lookup(self._api, "getChat", {"chat_id": chat_id})
            admins = lookup(self._api, "getChatAdministrators", {"chat_id": chat_id})
            count = lookup(self._api, "getChatMemberCount", {"chat_id": chat_id})
        except LookupFailed as failed:
            raise ContextRefused(_LOOKUP_CODES.get(failed.kind, "UNAVAILABLE")) from None
        if not isinstance(chat, dict) or not isinstance(admins, list) or type(count) is not int:
            raise ContextRefused("UNAVAILABLE")
        stamp = {"source": "telegram_live", "observed_at": timeutil.iso(self._clock())}
        title = chat.get("title") or chat.get("first_name")
        items: list[Mapping[str, Any]] = [
            {
                **stamp,
                "item": "chat",
                "chat_id": chat_id,
                "type": chat.get("type"),
                "is_forum": chat.get("is_forum") is True,
                "member_count": count,
                "untrusted": {"title": title} if isinstance(title, str) else {},
            }
        ]
        for admin in admins:
            user = admin.get("user") if isinstance(admin, dict) else None
            if isinstance(user, dict) and type(user.get("id")) is int:
                items.append(
                    {
                        **stamp,
                        "item": "admin",
                        "user_id": user["id"],
                        "status": admin.get("status"),
                        "is_bot": user.get("is_bot") is True,
                        "untrusted": {"name": user.get("first_name")},
                    }
                )
        return ContextPage(tuple(items), "telegram_live")

    def _admins(self, chat_id: int) -> ContextPage:
        admins = self._lookup("getChatAdministrators", {"chat_id": chat_id, "return_bots": True})
        if not isinstance(admins, list):
            raise ContextRefused("UNAVAILABLE")
        stamp = {"source": "telegram_live", "observed_at": timeutil.iso(self._clock())}
        items = []
        for admin in admins:
            user = admin.get("user") if isinstance(admin, dict) else None
            status = admin.get("status") if isinstance(admin, dict) else None
            role = _ROLES.get(status) if isinstance(status, str) else None
            if isinstance(user, dict) and type(user.get("id")) is int and role is not None:
                name = user.get("first_name")
                items.append({**stamp, "user_id": user["id"], "role": role,
                              "is_bot": user.get("is_bot") is True,
                              "untrusted": {"name": name} if isinstance(name, str) else {}})  # fmt: skip
        return ContextPage(tuple(items), "telegram_live")

    def _member(self, chat_id: int, user_id: int) -> ContextPage:
        member = self._lookup("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        status = member.get("status") if isinstance(member, dict) else None
        if status not in _STANDING:
            raise ContextRefused("UNAVAILABLE")
        role, standing = _STANDING[status]
        item = {"source": "telegram_live", "observed_at": timeutil.iso(self._clock()),
                "user_id": user_id, "role": role, "status": standing}  # fmt: skip
        return ContextPage((item,), "telegram_live")

    def _permissions(self, chat_id: int) -> ContextPage:
        chat = self._lookup("getChat", {"chat_id": chat_id})
        given = chat.get("permissions") if isinstance(chat, dict) else None
        if not isinstance(given, dict):
            raise ContextRefused("UNAVAILABLE")
        permissions = {k: v for k, v in given.items() if k in CHAT_PERMISSIONS and type(v) is bool}
        item = {"source": "telegram_live", "observed_at": timeutil.iso(self._clock()),
                "permissions": permissions}  # fmt: skip
        return ContextPage((item,), "telegram_live")

    def _lookup(self, method: str, params: Mapping[str, Any]) -> Any:
        try:
            return lookup(self._api, method, dict(params))
        except LookupFailed as failed:
            raise ContextRefused(_LOOKUP_CODES.get(failed.kind, "UNAVAILABLE")) from None

    def _around(self, chat_id: int, message_id: int, before: int, after: int) -> ContextPage:
        anchor = self._conn.execute(
            "SELECT update_id FROM bot_updates WHERE chat_id = ?"
            " AND json_extract(payload, '$.' || kind || '.message_id') = ?",
            (chat_id, message_id),
        ).fetchone()
        if anchor is None:
            raise ContextRefused("TARGET_NOT_FOUND")
        newer = self._conn.execute(
            "SELECT update_id, kind, payload, received_at FROM bot_updates WHERE chat_id = ?"
            " AND update_id > ? AND kind <> 'chat_join_request' ORDER BY update_id LIMIT ?",
            (chat_id, anchor[0], after),
        ).fetchall()
        older = self._conn.execute(
            "SELECT update_id, kind, payload, received_at FROM bot_updates WHERE chat_id = ?"
            " AND update_id <= ? AND kind <> 'chat_join_request' ORDER BY update_id DESC LIMIT ?",
            (chat_id, anchor[0], before + 1),
        ).fetchall()
        rows = [*reversed(newer), *older]
        return ContextPage(tuple(_local_item(*row) for row in rows), "telegram_local")

    def _recent(
        self,
        chat_id: int,
        limit: int,
        cursor: str | None,
        *,
        sender: int | None = None,
        kind: str | None = None,
    ) -> ContextPage:
        """Retained updates, newest first: every kind but join requests (they are not messages),
        or one kind (``chat_join_request``, G6); optionally one sender's (G5)."""
        before = int(cursor) if cursor is not None else None
        rows = self._conn.execute(
            "SELECT update_id, kind, payload, received_at FROM bot_updates WHERE chat_id = ?"
            " AND (? IS NULL OR json_extract(payload, '$.' || kind || '.from.id') = ?)"
            " AND (CASE WHEN ? IS NULL THEN kind <> 'chat_join_request' ELSE kind = ? END)"
            " AND (? IS NULL OR update_id < ?) ORDER BY update_id DESC LIMIT ?",
            (chat_id, sender, sender, kind, kind, before, before, limit + 1),
        ).fetchall()
        items = tuple(_local_item(*row) for row in rows[:limit])
        next_cursor = str(rows[limit - 1][0]) if len(rows) > limit else None
        return ContextPage(items, "telegram_local", next_cursor)


# Bot API ChatMember.status → (role, status), as the user actor reports them (G6).
_STANDING = {
    "creator": ("creator", "member"),
    "administrator": ("admin", "member"),
    "member": ("member", "member"),
    "restricted": ("member", "restricted"),
    "left": (None, "left"),
    "kicked": (None, "banned"),
}
_ROLES = {"creator": "creator", "administrator": "admin"}


def _positive(value: object) -> bool:
    return type(value) is int and value > 0


def _span(value: object) -> bool:
    return type(value) is int and 0 <= value <= 50


def _sender(value: object) -> bool:
    """A Telegram user's marked id: a positive integer, as a string (G5)."""
    return isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0


def _limit(value: object) -> bool:
    return type(value) is int and 1 <= value <= MAX_LIMIT


def _cursor(value: object) -> bool:
    return (
        isinstance(value, str) and value.isdigit() and value.isascii() and positive_int(int(value))
    )


def _local_item(update_id: int, kind: str, payload: str, received_at: str) -> Mapping[str, Any]:
    body = json.loads(payload).get(kind)
    body = body if isinstance(body, dict) else {}
    sender = body.get("from")
    sender = sender if isinstance(sender, dict) else {}
    text = body.get("text") if isinstance(body.get("text"), str) else body.get("caption")
    return {
        "source": "telegram_local",
        "observed_at": received_at,
        "update_id": update_id,
        "kind": kind,
        "message_id": body.get("message_id"),
        "date": body.get("date"),
        "from_id": sender.get("id"),
        "untrusted": {"text": text} if isinstance(text, str) else _name(kind, sender),
        **_media(body),
    }


def _unique(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 128
        and value.isascii()
        and value.isprintable()
        and " " not in value
    )


def _media(body: Mapping[str, Any]) -> dict[str, Any]:
    """A47 (H2): a photo's largest size or a document, keyed by ``file_unique_id`` (one file
    can have several ``file_id``s, Gf4). The ``file_id`` stays in the retained update, the one
    copy (Gx9); the engine keeps only the key and the facts."""
    photo = body.get("photo")
    if isinstance(photo, list):
        sizes = [p for p in photo if isinstance(p, dict) and _unique(p.get("file_unique_id"))]
        if not sizes:
            return {}
        largest = max(sizes, key=lambda p: int(p.get("width") or 0) * int(p.get("height") or 0))
        size = largest.get("file_size")
        return {"media": {"kind": "photo", "mime": "image/jpeg",
                          "size": size if type(size) is int and size >= 0 else None},
                "media_key": largest["file_unique_id"]}  # fmt: skip
    document = body.get("document")
    if isinstance(document, dict) and _unique(document.get("file_unique_id")):
        mime = document.get("mime_type")
        size = document.get("file_size")
        return {"media": {"kind": "document",
                          "mime": mime if isinstance(mime, str) and 3 <= len(mime) <= 128
                          else "application/octet-stream",
                          "size": size if type(size) is int and size >= 0 else None},
                "media_key": document["file_unique_id"]}  # fmt: skip
    return {}


def _name(kind: str, sender: Mapping[str, Any]) -> dict[str, Any]:
    """A join request carries no text; its requester's name is its untrusted content (G6)."""
    name = sender.get("first_name")
    return {"name": name} if kind == "chat_join_request" and isinstance(name, str) else {}
