"""The WhatsApp context source (catalog amendment G8; P §19-21, A32).

Message kinds (``recent``, ``around``, ``from``) are the comms webhook archive's; the Cloud API
has no history. Group kinds are the Groups API's, read live and labelled ``whatsapp_live``:
``members`` and ``member`` (participants), ``join_requests`` and ``invites`` (the group's one
link). A member's id is given as its delivery identity (``+`` E.164) so the context engine and
the group reads service can map it to a directory person and drop it; nothing here decides what
leaves. The Groups API exposes no roles, so ``admins`` is refused.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from comms.core import timeutil
from comms.core.providers.protocols import ContextPage, ContextQuery, ContextRefused
from comms.transports.whatsapp.cloud.groups import group_id_of
from comms.transports.whatsapp.cloud.http import GraphApi, GraphTransportError

__all__ = ["PROVENANCE", "WhatsAppContext"]

PROVENANCE = "whatsapp_live"
_ARCHIVE_KINDS = frozenset({"recent", "around", "from"})
_LIMIT = 100


class WhatsAppContext:
    def __init__(
        self, archive: Any, api: GraphApi | None, *, clock: Callable[[], datetime]
    ) -> None:
        self._archive, self._api, self._clock = archive, api, clock

    def __repr__(self) -> str:
        return "WhatsAppContext(<redacted>)"

    def read(self, query: ContextQuery) -> ContextPage:
        if query.kind in _ARCHIVE_KINDS or query.kind not in _LIVE:
            if self._archive is None:
                raise ContextRefused("NOT_CONFIGURED")
            return self._archive.read(query)  # it refuses the kinds it cannot serve
        if self._api is None:
            raise ContextRefused("NOT_CONFIGURED")
        group_id = group_id_of(query.target)
        stamp = {"source": PROVENANCE, "observed_at": timeutil.iso(self._clock())}
        return _LIVE[query.kind](self._api, group_id, query.args, stamp)


def _envelope(call: Callable[[], Any]) -> Mapping[str, Any]:
    try:
        response = call()
    except GraphTransportError:
        raise ContextRefused("UNAVAILABLE") from None
    envelope = response.envelope or {}
    if response.http_status == 200:
        return envelope
    error = envelope.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if response.http_status in (401, 403) or code in (3, 10, 200):
        raise ContextRefused("NOT_AUTHORIZED")
    if response.http_status == 404:
        raise ContextRefused("TARGET_NOT_FOUND")
    raise ContextRefused("UNAVAILABLE")


def _rows(envelope: Mapping[str, Any], key: str) -> list[Any]:
    rows = envelope.get(key)
    return rows if isinstance(rows, list) else []


def _identity(wa_id: object) -> str | None:
    return f"+{wa_id}" if isinstance(wa_id, str) and wa_id.isdigit() else None


def _members(api: GraphApi, group_id: str, args: Mapping[str, Any], stamp: Any) -> ContextPage:
    info = _envelope(lambda: api.group_info(group_id))
    rows = _rows(info, "participants")
    items = tuple(
        {**stamp, "user_id": identity, "role": "member"}
        for row in rows
        if isinstance(row, dict) and (identity := _identity(row.get("wa_id"))) is not None
    )
    return ContextPage(items[:_LIMIT], PROVENANCE)


def _member(api: GraphApi, group_id: str, args: Mapping[str, Any], stamp: Any) -> ContextPage:
    wanted = _identity(str(args.get("user_id", "")).removeprefix("+"))
    if wanted is None:
        raise ValueError("member refused")
    present = any(i["user_id"] == wanted for i in _members(api, group_id, {}, stamp).items)
    role, status = ("member", "member") if present else (None, "left")
    return ContextPage(({**stamp, "user_id": wanted, "role": role, "status": status},), PROVENANCE)


def _join_requests(
    api: GraphApi, group_id: str, args: Mapping[str, Any], stamp: Any
) -> ContextPage:
    limit = min(int(args.get("limit") or 50), _LIMIT)
    after = args.get("cursor")
    envelope = _envelope(lambda: api.join_requests(group_id, limit=limit, after=after))
    rows = _rows(envelope, "data")
    items = []
    for row in rows:
        identity = _identity(row.get("wa_id")) if isinstance(row, dict) else None
        if identity is None:
            continue
        created = row.get("creation_timestamp")
        seconds = int(created) if isinstance(created, str | int) and str(created).isdigit() else 0
        items.append({**stamp, "user_id": identity, "requested_at": seconds or None,
                      "untrusted": {}})  # fmt: skip
    paging = envelope.get("paging")
    cursors = paging.get("cursors") if isinstance(paging, dict) else None
    following = cursors.get("after") if isinstance(cursors, dict) else None
    more = len(rows) == limit and isinstance(following, str) and following
    return ContextPage(tuple(items), PROVENANCE, following if more else None)


def _invites(api: GraphApi, group_id: str, args: Mapping[str, Any], stamp: Any) -> ContextPage:
    envelope = _envelope(lambda: api.group_invite(group_id))
    link = envelope.get("invite_link")
    if not isinstance(link, str) or not link.startswith("https://chat.whatsapp.com/"):
        raise ContextRefused("UNAVAILABLE")
    item = {**stamp, "link": link, "primary": True, "revoked": False, "usage": None,
            "usage_limit": None, "expires_at": None, "request_needed": False, "requested": None,
            "untrusted": {}}  # fmt: skip
    return ContextPage((item,), PROVENANCE)


_LIVE: Mapping[str, Callable[[GraphApi, str, Mapping[str, Any], Any], ContextPage]] = {
    "members": _members,
    "member": _member,
    "join_requests": _join_requests,
    "invites": _invites,
}
