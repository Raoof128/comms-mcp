"""Group reads that are not message context (catalog amendment G6; spec A45, A26).

One member's standing, the chat's default permissions, and the group lists (join requests,
invites, forum topics, the admin log), read through
the one reader rule (``ContextEngine.reader``) from whichever actor can serve them. Every
provider id is mapped to a ref before anything leaves: a user id becomes the directory person's
``rcp_`` ref, or ``null`` when the person is not in the directory, and is otherwise dropped.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from comms.core import timeutil
from comms.core.campaigns.directory import (
    destination_id,
    member_identity,
    recipient_of_identity,
)
from comms.core.errors import CommsError
from comms.core.objects import object_ref, resolve_object
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderTarget
from comms.core.providers.semantics import SUPPORT
from comms.services.context import ContextEngine

__all__ = ["GroupReads"]

_PAGE_MAX = 100
_INVITE_FIELDS = (
    "primary", "revoked", "usage", "usage_limit", "expires_at", "request_needed", "requested",
)  # fmt: skip
# The capability each list is read under (the reader rule picks the actor by it).
_LISTS = {
    "join_requests": C.JOIN_REQUEST_LIST,
    "invites": C.INVITE_LIST,
    "topics": C.TOPIC_LIST,
    "admin_log": C.ADMIN_LOG_READ,
}


def _transport(targets: Mapping[str, ProviderTarget]) -> str:
    if not targets:
        raise CommsError("NOT_CONFIGURED")
    return next(iter(targets.values())).transport


def _when(value: object) -> str | None:
    """A provider date (Unix seconds or ISO text) as ISO text."""
    if type(value) is int and value > 0:
        return timeutil.iso(datetime.fromtimestamp(value, UTC))
    return value if isinstance(value, str) else None


class GroupReads:
    def __init__(self, conn: Any, context: ContextEngine) -> None:
        self._conn, self._context = conn, context

    def member(
        self, group: str, targets: Mapping[str, ProviderTarget], recipient: str
    ) -> dict[str, Any]:
        """``group.members_get``: a directory person's role and status in the group."""
        identity = member_identity(self._conn, recipient, _transport(targets))
        if identity is None:
            raise CommsError("NOT_FOUND")
        target = self._context.reader(targets, C.MEMBER_GET, fallback=True)
        (item,) = self._context.read(target, "member", {"user_id": identity}).items
        return {
            "group": group,
            "recipient": recipient,
            "role": item.get("role"),
            "status": item.get("status"),
        }

    def permissions(self, group: str, targets: Mapping[str, ProviderTarget]) -> dict[str, Any]:
        """``group.permissions_get``: the chat's default member permissions (membership is
        enough to read them, so ``member.get`` gates the read)."""
        target = self._context.reader(targets, C.MEMBER_GET, fallback=True)
        (item,) = self._context.read(target, "permissions", {}).items
        permissions = dict(item.get("permissions") or {})
        if not permissions:
            raise CommsError("PROVIDER_UNAVAILABLE")
        return {"group": group, "permissions": permissions}

    def listed(
        self,
        kind: str,
        group: str,
        targets: Mapping[str, ProviderTarget],
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """One page of a group list (G6): ``join_requests``, ``invites``, ``topics`` or
        ``admin_log``, read through the one reader rule; every provider id mapped to a ref.
        Returns the page and the actor that served it (its cursor is that actor's)."""
        transport = _transport(targets)
        target = self._context.reader(targets, _LISTS[kind], fallback=True)
        args: dict[str, Any] = {"limit": min(limit, _PAGE_MAX)}
        if cursor is not None:
            args["cursor"] = cursor
        page = self._context.read(target, kind, args)
        mapped = [
            self._mapped(kind, target, transport, item, page.provenance) for item in page.items
        ]
        return {"group": group, "items": mapped, "next_cursor": page.next_cursor}, target.actor

    def topic(
        self, group: str, targets: Mapping[str, ProviderTarget], topic: str
    ) -> dict[str, Any]:
        """``group.topic_get``: one forum topic by its ``top_`` ref."""
        target = self._context.reader(targets, C.TOPIC_LIST, fallback=True)
        if target.actor not in SUPPORT[C.TOPIC_LIST]:  # no topics at all: say so first
            raise CommsError("PROVIDER_UNSUPPORTED")
        found = resolve_object(self._conn, topic, "topic")
        if not found.provider_identity.isdigit():
            raise CommsError("NOT_FOUND")
        page = self._context.read(target, "topic", {"topic_id": found.provider_identity})
        if not page.items:
            raise CommsError("NOT_FOUND")
        item = page.items[0]
        return {
            "group": group,
            "topic": topic,
            "closed": bool(item.get("closed")),
            "untrusted": dict(item.get("untrusted") or {}),
        }

    def _person(self, transport: str, user_id: object) -> str | None:
        if user_id is None:
            return None
        return recipient_of_identity(self._conn, transport, str(user_id))

    def _mapped(
        self,
        kind: str,
        target: ProviderTarget,
        transport: str,
        item: Mapping[str, Any],
        provenance: str,
    ) -> dict[str, Any]:
        untrusted = dict(item.get("untrusted") or {})
        if kind == "join_requests":
            return {
                "source": provenance,
                "recipient": self._person(transport, item.get("user_id", item.get("from_id"))),
                "requested_at": _when(item.get("requested_at", item.get("date"))),
                "untrusted": untrusted,
            }
        if kind == "admin_log":
            return {
                "at": _when(item.get("at")),
                "action": str(item.get("action")),
                "actor": self._person(transport, item.get("user_id")),
            }
        destination = destination_id(self._conn, target.destination_ref)
        now = timeutil.utc(datetime.now(UTC))
        if kind == "invites":
            ref = object_ref(self._conn, "invite", transport, target.actor, destination,
                             str(item["link"]), now=now)  # fmt: skip
            fields = {k: item.get(k) for k in _INVITE_FIELDS}
            return {"invite": ref, **fields, "untrusted": untrusted}
        ref = object_ref(self._conn, "topic", transport, target.actor, destination,
                         str(item["topic_id"]), now=now)  # fmt: skip
        flags = {k: bool(item.get(k)) for k in ("closed", "pinned", "hidden")}
        return {"topic": ref, **flags, "untrusted": untrusted}
