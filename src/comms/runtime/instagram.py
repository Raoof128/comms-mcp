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

from comms.core import domains, timeutil
from comms.core import mutations as records
from comms.core.canonical import jcs_dumps
from comms.core.errors import CommsError
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import SemanticOperation
from comms.services.capability import STATE_CODE, CapabilityService
from comms.services.handles import ContextHandles
from comms.services.mutations import CallContext, MutationExecutor
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
    window_open,
)
from comms.transports.instagram.publish import (
    CONTAINER_BUDGET,
    LEDGER_KIND,
    Publisher,
    caption_counts,
    check_carousel,
    check_container,
    quota,
)

__all__ = ["InstagramService"]

_PAGE = 25
_WINDOW_LOOKBACK = 5  # the newest messages the window check reads (D-I8)


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
        publisher: Publisher | None = None,
    ) -> None:
        self._conn, self._accounts, self._capability = conn, accounts, capability
        self._handles, self._clock = handles, clock
        self._throttle = throttle or Throttle()
        self._executor, self._publisher = executor, publisher

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

    def story_list(self, client: str, args: Mapping[str, Any]) -> dict[str, Any]:
        """The account's live Stories (``GET /<IG_ID>/stories``; R-IG11, 🧪 GI-3 on this host):
        ``igm_`` refs like any media, so ``media_get`` reads one. A Story lives 24 hours."""
        runtime, username = self._read(args.get("account"), C.MEDIA_LIST)
        limit = str(args.get("limit", _PAGE))

        def call(after: str | None) -> Any:
            params = {
                "fields": self._fields(),
                "limit": limit,
                **({"after": after} if after else {}),
            }
            return runtime.api.get(runtime.user_id, "stories", params=params)

        data, token = self._page(client, "story_list", runtime, args, call)
        now = self._clock()
        items = [
            media_item(self._conn, runtime, raw, now=now) for raw in data if isinstance(raw, dict)
        ]
        return {**self._head(runtime, username), "items": items, "next_cursor": token}

    def story_insights(self, args: Mapping[str, Any]) -> dict[str, Any]:
        """A Story's own metrics (R-IG11), checked before Meta is asked."""
        runtime, username = self._read(args.get("account"), C.INSIGHTS_READ)
        ident = self._media_id(runtime, args["media"])
        try:
            params = insights.story_params(args.get("metrics") or (), args.get("breakdown"))
        except ValueError:
            raise CommsError("INVALID_ARGUMENT") from None
        body = graph_read(lambda: runtime.api.get(ident, "insights", params=params), insights=True)
        return {**self._head(runtime, username), "media": args["media"], "metrics": _metrics(body)}

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

    # -- writes (IG-3) ----------------------------------------------------------------------------

    def _write(
        self,
        client: str,
        tool: str,
        a: Mapping[str, Any],
        capability: C,
        args: Mapping[str, Any],
        *,
        on_created: Callable[[AccountRuntime], Callable[[Any, str], Mapping[str, Any]]]
        | None = None,
        prepare: Callable[[AccountRuntime], dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        """One write: the named account (never a default, D-I5), its identity, its ceiling
        (``NOT_AUTHORIZED`` before anything is recorded), then the executor (A28, A41)."""
        if self._executor is None:
            raise CommsError("NOT_CONFIGURED")
        runtime = self._accounts.resolve(a.get("account"), for_write=True)
        username = self._accounts.username(runtime)
        self._capability.require_for_write(ACTOR, runtime.target(), capability)
        head = {**self._head(runtime, username), "actor": ACTOR}
        replay = records.find(self._conn, client, a["request_id"]) is not None
        if prepare is not None and not replay:  # a replay answers its record (A28), unchecked
            refused = prepare(runtime)  # a check that answers without a provider write
            if refused is not None:
                return {**head, **refused}
        outcome = self._executor.provider(
            CallContext(client), tool, runtime.target(), SemanticOperation(capability, dict(args)),
            a["request_id"], on_created=None if on_created is None else on_created(runtime),
        )  # fmt: skip
        extra = {k: v for k, v in outcome.result.items() if k not in ("state", "code")}
        return {**head, "result": outcome.state, "code": outcome.code, "op_ref": outcome.op_ref,
                "replayed": outcome.replayed, **extra}  # fmt: skip

    def _owned(self, runtime: AccountRuntime, ref: object, kind: str) -> None:
        """``NOT_FOUND`` before anything is recorded for a ref of another account or kind."""
        store.resolve_object(self._conn, ref, kind, runtime.account_id)

    def _created(
        self, kind: str, key: str
    ) -> Callable[[AccountRuntime], Callable[[Any, str], Mapping[str, Any]]]:
        def bind(runtime: AccountRuntime) -> Callable[[Any, str], Mapping[str, Any]]:
            def made(conn: Any, provider_ref: str) -> Mapping[str, Any]:
                return {
                    key: store.object_ref(
                        conn, runtime.account_id, kind, provider_ref, now=self._clock()
                    )
                }

            return made

        return bind

    def comment_reply(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        def prepare(runtime: AccountRuntime) -> None:
            self._owned(runtime, a["comment"], "comment")

        result = self._write(
            client, "comms_instagram_comment_reply", a, C.COMMENT_REPLY,
            {"comment": a["comment"], "text": a["text"]},
            on_created=self._created("comment", "comment"), prepare=prepare,
        )  # fmt: skip
        return {"comment": None, **result}

    def comment_hide(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            client, "comms_instagram_comment_hide", a, C.COMMENT_HIDE,
            {"comment": a["comment"], "hide": a["hide"]},
            prepare=lambda runtime: self._owned(runtime, a["comment"], "comment"),
        )  # fmt: skip

    def comments_enabled_set(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            client, "comms_instagram_comments_enabled_set", a, C.MEDIA_COMMENTS_TOGGLE,
            {"media": a["media"], "enabled": a["enabled"]},
            prepare=lambda runtime: self._owned(runtime, a["media"], "media"),
        )  # fmt: skip

    def comment_delete(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        return self._write(
            client, "comms_instagram_comment_delete", a, C.COMMENT_DELETE, {"comment": a["comment"]},
            prepare=lambda runtime: self._owned(runtime, a["comment"], "comment"),
        )  # fmt: skip

    def message_send(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        """A DM reply inside the 24-hour window (D-I8): the window is read live first, and a
        closed window answers ``FAILED WINDOW_CLOSED`` with nothing recorded or sent."""
        footer = self._accounts.settings.dm_disclosure
        text = a["text"] if not footer else f"{a['text']}\n\n{footer}"

        def prepare(runtime: AccountRuntime) -> dict[str, Any] | None:
            igsid = store.resolve_object(self._conn, a["person"], "person", runtime.account_id)
            thread = conversation_id(runtime, igsid, self._throttle)
            recent = message_items(runtime, thread, igsid, _WINDOW_LOOKBACK, self._throttle)
            if window_open(recent, timeutil.utc(self._clock())):
                return None
            return {"result": "FAILED", "code": "WINDOW_CLOSED", "op_ref": None, "replayed": False}

        return self._write(
            client, "comms_instagram_message_send", a, C.MESSAGE_REPLY,
            {"person": a["person"], "text": text}, prepare=prepare,
        )  # fmt: skip

    # -- publishing (IG-4) -------------------------------------------------------------------------

    def _publishing(self) -> Publisher:
        if self._publisher is None:
            raise CommsError("NOT_CONFIGURED")
        return self._publisher

    def publish_quota(self, a: Mapping[str, Any]) -> dict[str, Any]:
        """The live published-post quota and the local 400-container ledger."""
        runtime, username = self._read(a.get("account"), C.PUBLISHING_QUOTA_READ)
        since = a.get("since")
        if since is not None:
            now = timeutil.utc(self._clock()).timestamp()
            if not now - 24 * 3600 <= since <= now:
                raise CommsError("INVALID_ARGUMENT")
        live = quota(runtime, since)
        return {**self._head(runtime, username), **live,
                "containers_last_24h": self._publishing().budget_used(runtime),
                "container_budget": CONTAINER_BUDGET}  # fmt: skip

    def _blocked(self, runtime: AccountRuntime, live: Mapping[str, int | None]) -> str | None:
        """What a create answers before Meta: the ledger's budget, then the live post quota."""
        if self._publishing().budget_used(runtime) >= CONTAINER_BUDGET:
            return "CONTAINER_BUDGET"
        used, total = live.get("quota_usage"), live.get("quota_total")
        if used is not None and total is not None and used >= total:
            return "PUBLISH_CAP"
        return None

    def publish_preview(self, a: Mapping[str, Any]) -> dict[str, Any]:
        """Exactly what one ``container_create`` or ``carousel_create`` would do (D-I3), with
        an advisory ``preview_digest`` the create may echo (open question 3). Read-only."""
        runtime = self._accounts.resolve(a.get("account"), for_write=True)
        username = self._accounts.username(runtime)
        state = self._capability.state(ACTOR, runtime.target(), C.PUBLISHING_QUOTA_READ)
        if state is not S.AVAILABLE:
            raise CommsError(STATE_CODE[state])
        tool, args = a["create"], _create_args(a, ("account", "create"))
        capability = (
            C.MEDIA_CAROUSEL_CREATE if tool == "carousel_create" else C.MEDIA_CONTAINER_CREATE
        )
        try:
            (check_carousel if tool == "carousel_create" else check_container)(args)
        except ValueError:
            raise CommsError("INVALID_ARGUMENT") from None
        if tool == "carousel_create":
            self._publishing().children(runtime, args["children"])
        write_state = self._capability.state(ACTOR, runtime.target(), capability)
        live = quota(runtime)
        refusal = STATE_CODE[write_state] if write_state is not S.AVAILABLE else None
        caption = args.get("caption")
        tags, mentions = caption_counts(caption) if isinstance(caption, str) else (0, 0)
        return {
            **self._head(runtime, username),
            "create": tool,
            "kind": "carousel" if tool == "carousel_create" else args["kind"],
            "children": len(args["children"]) if tool == "carousel_create" else None,
            "caption_chars": len(caption) if isinstance(caption, str) else 0,
            "hashtags": tags,
            "mentions": mentions,
            "writes_allowed": write_state is S.AVAILABLE,
            **live,
            "containers_last_24h": self._publishing().budget_used(runtime),
            "container_budget": CONTAINER_BUDGET,
            "refusal": refusal or self._blocked(runtime, live),
            "preview_digest": _preview_digest(tool, runtime.ref, args),
            "untrusted_text": caption if isinstance(caption, str) else None,
        }

    def _create(
        self, client: str, tool: str, a: Mapping[str, Any], capability: C, kind_of: str
    ) -> dict[str, Any]:
        args = _create_args(a, ("account", "request_id", "preview_digest"))

        def prepare(runtime: AccountRuntime) -> dict[str, Any] | None:
            digest = a.get("preview_digest")
            if digest is not None and digest != _preview_digest(tool, runtime.ref, args):
                raise CommsError("INVALID_ARGUMENT")  # not what was previewed (open question 3)
            if tool == "carousel_create":
                self._publishing().children(runtime, list(a.get("children") or ()))
            try:
                live = quota(runtime)
            except CommsError:  # advisory: the ledger holds; Meta's answer is final (A25)
                live = {}
            code = self._blocked(runtime, live)
            if code is None:
                return None
            return {"result": "FAILED", "code": code, "op_ref": None, "replayed": False}

        def bind(runtime: AccountRuntime) -> Callable[[Any, str], Mapping[str, Any]]:
            def made(conn: Any, provider_ref: str) -> Mapping[str, Any]:
                ref = store.record_container(
                    conn, runtime.account_id, kind_of, provider_ref, now=self._clock()
                )
                return {"container": ref}

            return made

        result = self._write(
            client, f"comms_instagram_{tool}", a, capability, args, on_created=bind,
            prepare=prepare,
        )  # fmt: skip
        return {"container": None, **result}

    def container_create(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        kind = a.get("kind")
        if kind not in LEDGER_KIND:
            raise CommsError("INVALID_ARGUMENT")
        return self._create(
            client, "container_create", a, C.MEDIA_CONTAINER_CREATE, LEDGER_KIND[kind]
        )

    def carousel_create(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        return self._create(client, "carousel_create", a, C.MEDIA_CAROUSEL_CREATE, "carousel")

    def publish(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        """One status read, then ``media_publish`` (D-I7). A container still processing
        answers ``FAILED CONTAINER_NOT_READY``: call again later with a new ``request_id``."""

        def prepare(runtime: AccountRuntime) -> None:
            store.container(self._conn, a["container"], runtime.account_id)  # NOT_FOUND first
            self._publishing()

        def bind(runtime: AccountRuntime) -> Callable[[Any, str], Mapping[str, Any]]:
            def made(conn: Any, provider_ref: str) -> Mapping[str, Any]:
                ref = store.object_ref(
                    conn, runtime.account_id, "media", provider_ref, now=self._clock()
                )
                store.mark_container(conn, a["container"], "PUBLISHED", ref)
                return {"media": ref}

            return made

        result = self._write(
            client, "comms_instagram_publish", a, C.MEDIA_PUBLISH,
            {"container": a["container"]}, on_created=bind, prepare=prepare,
        )  # fmt: skip
        return {"media": None, **result}


def _create_args(a: Mapping[str, Any], drop: tuple[str, ...]) -> dict[str, Any]:
    """A create's arguments as Meta will see them: everything but comms' own fields."""
    return {k: (list(v) if isinstance(v, (list, tuple)) else v) for k, v in a.items()
            if k not in drop}  # fmt: skip


def _preview_digest(tool: str, account_ref: str, args: Mapping[str, Any]) -> str:
    """The advisory binding of a preview to one create: tool, account and exact arguments."""
    body = {"tool": tool, "account": account_ref, "args": dict(args)}
    return hashlib.sha256(domains.INSTAGRAM_PREVIEW + jcs_dumps(body)).hexdigest()


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
