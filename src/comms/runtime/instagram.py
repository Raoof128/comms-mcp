"""The Instagram service (proposed A49, sections 5 and 9; A37; R-IG4): every Instagram tool
calls it. It lives in ``runtime`` because it composes the transport with comms services, and
only ``runtime`` may import both.

A read resolves the account (by alias, else ``instagram.default``), checks its identity once per
daemon lifetime (4.5), checks the capability, and calls Meta through the account's
``GraphIgApi``. Every provider id becomes an opaque ref; every text is untrusted. A page's Meta
cursor becomes a client-bound ``cur_`` through ``ContextHandles``, with the ``iga_`` as the
handle's target and ``instagram`` as its actor (R-IG2, D9), so a cursor from one tool, client,
account or epoch never reads another. Nothing is persisted but the refs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from comms.core import timeutil
from comms.core.canonical import jcs_dumps
from comms.core.errors import CommsError
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.services.capability import STATE_CODE, CapabilityService
from comms.services.handles import ContextHandles
from comms.services.mutations import MutationExecutor
from comms.transports.instagram import insights, store
from comms.transports.instagram.accounts import ACTOR, AccountRuntime, InstagramAccounts
from comms.transports.instagram.classify import graph_read
from comms.transports.instagram.comments import COMMENT_FIELDS, comment_item
from comms.transports.instagram.media import (
    MEDIA_FIELDS,
    count,
    media_created,
    media_item,
    page_of,
    profile,
)
from comms.transports.instagram.messages import (
    Throttle,
    conversation_id,
    conversation_items,
    message_items,
)

__all__ = ["InstagramService"]

_PAGE = 25


class InstagramService:
    def __init__(
        self,
        conn: Any,
        accounts: InstagramAccounts,
        capability: CapabilityService,
        handles: ContextHandles,
        *,
        clock: Callable[[], datetime],
        throttle: Throttle | None = None,
        executor: MutationExecutor | None = None,
    ) -> None:
        self._conn, self._accounts, self._capability = conn, accounts, capability
        self._handles, self._clock = handles, clock
        self._throttle = throttle or Throttle()
        self._executor = executor

    def __repr__(self) -> str:
        return "InstagramService(<redacted>)"

    # -- shared --------------------------------------------------------------------------------

    def _read(self, alias: object, capability: C) -> tuple[AccountRuntime, str]:
        """The account a read names, its live username, and the capability's state."""
        runtime = self._accounts.resolve(alias, for_write=False)
        username = self._accounts.username(runtime)
        state = self._capability.state(ACTOR, runtime.target(), capability)
        if state is not S.AVAILABLE:
            raise CommsError(STATE_CODE[state])
        return runtime, username

    @staticmethod
    def _head(
        runtime: AccountRuntime, username: str, untrusted: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """The account named, and its live username (untrusted, A44) with any other names."""
        return {"account": runtime.alias, "account_ref": runtime.ref,
                "untrusted": {"account_username": username, **(untrusted or {})}}  # fmt: skip

    def _after(
        self, client: str, kind: str, runtime: AccountRuntime, args: Mapping[str, Any]
    ) -> str | None:
        """The Meta cursor a ``cur_`` names, if the caller passed one for this query."""
        token = args.get("cursor")
        if token is None:
            return None
        handle, position = self._handles.position(client, token)
        snapshot = handle.snapshot
        if (
            handle.target_ref != runtime.ref
            or handle.actor != ACTOR
            or snapshot.get("kind") != kind
            or snapshot.get("args") != _query(args)
        ):
            raise CommsError("STALE_HANDLE")
        after = position.get("after")
        if not isinstance(after, str):
            raise CommsError("STALE_HANDLE")
        return after

    def _token(
        self, client: str, kind: str, runtime: AccountRuntime, args: Mapping[str, Any],
        after: str | None,
    ) -> str | None:  # fmt: skip
        if after is None:
            return None
        snapshot = {"kind": kind, "args": _query(args)}
        digest = hashlib.sha256(jcs_dumps(snapshot)).hexdigest()
        ctx_ref = self._handles.open(
            client=client, owner=client, target_ref=runtime.ref, actor=ACTOR,
            query_digest=digest, snapshot=snapshot,
        )  # fmt: skip
        return self._handles.cursor(client, ctx_ref, {"after": after})

    def _page(
        self, client: str, kind: str, runtime: AccountRuntime, args: Mapping[str, Any],
        call: Callable[[str | None], Any],
    ) -> tuple[list[Any], str | None]:  # fmt: skip
        body = graph_read(lambda: call(self._after(client, kind, runtime, args)))
        data, after = page_of(body)
        return data, self._token(client, kind, runtime, args, after)

    # -- account and profile ---------------------------------------------------------------------

    def account_list(self) -> dict[str, Any]:
        now = timeutil.utc(self._clock())
        rows = {row.alias: row for row in store.live_accounts(self._conn)}
        accounts = []
        for alias, policy in sorted(self._accounts.settings.accounts.items()):
            row = rows.get(alias)
            days = None
            if row is not None:
                days = max(0, (timeutil.instant(row.expires_at) - now) // timedelta(days=1))
            accounts.append(
                {
                    "account": alias,
                    "account_ref": row.ref if row else None,
                    "registered": row is not None,
                    "writes": policy.writes,
                    "dms": policy.dms,
                    "token_expires_in_days": days,
                    "untrusted": {"label": policy.label},
                }
            )
        return {"accounts": accounts, "default": self._accounts.settings.default}

    def whoami(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.PROFILE_READ)
        row = store.account_by_ref(self._conn, runtime.ref)
        return {**self._head(runtime, username), "identity_checked": True,
                "token_expires_at": row.expires_at if row else None}  # fmt: skip

    def profile(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.PROFILE_READ)
        found = profile(runtime)
        return {**found, **self._head(runtime, username, found.pop("untrusted"))}

    # -- media -----------------------------------------------------------------------------------

    def _fields(self) -> str:
        return MEDIA_FIELDS + (",caption" if self._accounts.settings.caption else "")

    def media_list(self, client: str, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.MEDIA_LIST)
        limit = str(args.get("limit", _PAGE))

        def call(after: str | None) -> Any:
            params = {
                "fields": self._fields(),
                "limit": limit,
                **({"after": after} if after else {}),
            }
            return runtime.api.get("me", "media", params=params)

        data, token = self._page(client, "media_list", runtime, args, call)
        now = self._clock()
        items = [
            media_item(self._conn, runtime, raw, now=now) for raw in data if isinstance(raw, dict)
        ]
        return {**self._head(runtime, username), "items": items, "next_cursor": token}

    def _media_id(self, runtime: AccountRuntime, media: object) -> str:
        return store.resolve_object(self._conn, media, "media", runtime.account_id)

    def media_get(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.MEDIA_GET)
        ident = self._media_id(runtime, args["media"])
        raw = graph_read(lambda: runtime.api.get(ident, params={"fields": self._fields()}))
        item = media_item(self._conn, runtime, raw, now=self._clock())
        return {**item, **self._head(runtime, username, item.pop("untrusted"))}

    def media_insights(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.INSIGHTS_READ)
        ident = self._media_id(runtime, args["media"])
        raw = graph_read(lambda: runtime.api.get(ident, params={"fields": "media_type,timestamp"}))
        try:
            params = insights.media_params(
                args["metrics"],
                str(raw.get("media_type")),
                media_created(raw),
                args.get("breakdown"),
            )
        except ValueError:
            raise CommsError("INVALID_ARGUMENT") from None
        body = graph_read(lambda: runtime.api.get(ident, "insights", params=params), insights=True)
        return {**self._head(runtime, username), "media": args["media"], "metrics": _metrics(body)}

    def account_insights(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.INSIGHTS_READ)
        try:
            params = insights.account_params(dict(args))
        except ValueError:
            raise CommsError("INVALID_ARGUMENT") from None
        body = graph_read(
            lambda: runtime.api.get(runtime.user_id, "insights", params=params), insights=True
        )
        return {**self._head(runtime, username), "metrics": _metrics(body)}

    # -- comments and tags -----------------------------------------------------------------------

    def comment_list(self, client: str, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.COMMENT_LIST)
        ident = self._media_id(runtime, args["media"])
        return self._comments(client, "comment_list", runtime, username, args, ident, "comments")

    def comment_replies(self, client: str, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.COMMENT_LIST)
        ident = store.resolve_object(self._conn, args["comment"], "comment", runtime.account_id)
        return self._comments(client, "comment_replies", runtime, username, args, ident, "replies")

    def _comments(
        self, client: str, kind: str, runtime: AccountRuntime, username: str,
        args: Mapping[str, Any], ident: str, edge: str,
    ) -> dict[str, Any]:  # fmt: skip
        def call(after: str | None) -> Any:
            params = {"fields": COMMENT_FIELDS, "limit": str(args.get("limit", _PAGE)),
                      **({"after": after} if after else {})}  # fmt: skip
            return runtime.api.get(ident, edge, params=params)

        data, token = self._page(client, kind, runtime, args, call)
        now = self._clock()
        items = [
            comment_item(self._conn, runtime, raw, now=now) for raw in data if isinstance(raw, dict)
        ]
        return {**self._head(runtime, username), "items": items, "next_cursor": token}

    def tag_list(self, client: str, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.TAG_LIST)

        def call(after: str | None) -> Any:
            params = {"fields": self._fields(), "limit": str(args.get("limit", _PAGE)),
                      **({"after": after} if after else {})}  # fmt: skip
            return runtime.api.get(runtime.user_id, "tags", params=params)

        data, token = self._page(client, "tag_list", runtime, args, call)
        now = self._clock()
        items = [
            media_item(self._conn, runtime, raw, now=now) for raw in data if isinstance(raw, dict)
        ]
        return {**self._head(runtime, username), "items": items, "next_cursor": token}

    # -- conversations ---------------------------------------------------------------------------

    def conversation_list(self, client: str, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.HISTORY_READ)

        def call(after: str | None) -> Any:
            self._throttle.wait(runtime.ref)
            params = {"platform": "instagram", "fields": "participants,updated_time",
                      "limit": str(args.get("limit", _PAGE)), **({"after": after} if after else {})}  # fmt: skip
            return runtime.api.get("me", "conversations", params=params)

        data, token = self._page(client, "conversation_list", runtime, args, call)
        items = conversation_items(self._conn, runtime, data, username, now=self._clock())
        return {**self._head(runtime, username), "items": items, "next_cursor": token}

    def conversation_messages(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.HISTORY_READ)
        igsid = store.resolve_object(self._conn, args["person"], "person", runtime.account_id)
        thread = conversation_id(runtime, igsid, self._throttle)
        items = message_items(runtime, thread, igsid, int(args.get("limit", 10)), self._throttle)
        return {**self._head(runtime, username), "person": args["person"], "items": items}


def _query(args: Mapping[str, Any]) -> dict[str, Any]:
    """What a cursor is bound to: every argument but the cursor itself."""
    return {k: v for k, v in args.items() if k != "cursor"}


def _metrics(body: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Meta's insights rows, reduced to names, numbers and breakdown keys (no ids)."""
    out = []
    for row in body.get("data") or ():
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            continue
        raw_values, raw_total = row.get("values"), row.get("total_value")
        values: list[Any] = raw_values if isinstance(raw_values, list) else []
        total: Mapping[str, Any] = raw_total if isinstance(raw_total, dict) else {}
        series = [
            {"end_time": v.get("end_time") if isinstance(v.get("end_time"), str) else None,
             "value": count(v.get("value"))}
            for v in values if isinstance(v, dict) and count(v.get("value")) is not None
        ]  # fmt: skip
        breakdown = []
        for block in total.get("breakdowns") or ():
            for result in (block.get("results") or ()) if isinstance(block, dict) else ():
                if isinstance(result, dict) and count(result.get("value")) is not None:
                    keys = [str(k)[:64] for k in result.get("dimension_values") or ()][:4]
                    breakdown.append({"keys": keys, "value": result["value"]})
        out.append(
            {
                "name": row["name"][:64],
                "total": count(total.get("value"))
                if total
                else (series[0]["value"] if len(series) == 1 else None),
                "series": series or None,
                "breakdown": breakdown[:64] or None,
            }
        )
    return out
