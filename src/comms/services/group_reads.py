"""Group reads that are not message context (catalog amendment G6; spec A45, A26).

One member's standing, the chat's default permissions and pending join requests, read through
the one reader rule (``ContextEngine.reader``) from whichever actor can serve them. Every
provider id is mapped to a ref before anything leaves: a user id becomes the directory person's
``rcp_`` ref, or ``null`` when the person is not in the directory, and is otherwise dropped.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from comms.core import timeutil
from comms.core.campaigns.directory import member_identity, recipient_of_identity
from comms.core.errors import CommsError
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderTarget
from comms.services.context import ContextEngine

__all__ = ["GroupReads"]

_PAGE_MAX = 100


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

    def join_requests(
        self,
        group: str,
        targets: Mapping[str, ProviderTarget],
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """``group.join_requests_list``: pending requests, newest first; each requester by
        ``rcp_`` ref when in the directory, their name untrusted. Returns the page and the actor
        that served it (its cursor is that actor's)."""
        transport = _transport(targets)
        target = self._context.reader(targets, C.JOIN_REQUEST_LIST, fallback=True)
        args: dict[str, Any] = {"limit": min(limit, _PAGE_MAX)}
        if cursor is not None:
            args["cursor"] = cursor
        page = self._context.read(target, "join_requests", args)
        items = []
        for item in page.items:
            user_id = item.get("user_id", item.get("from_id"))
            items.append(
                {
                    "source": page.provenance,
                    "recipient": None
                    if user_id is None
                    else recipient_of_identity(self._conn, transport, str(user_id)),
                    "requested_at": _when(item.get("requested_at", item.get("date"))),
                    "untrusted": dict(item.get("untrusted") or {}),
                }
            )
        return {"group": group, "items": items, "next_cursor": page.next_cursor}, target.actor
