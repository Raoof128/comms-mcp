"""The Pinterest service (proposed A50, sections 5 and 6; A37): every Pinterest tool calls it.
It lives in ``runtime`` because it composes the transport with comms services, and only
``runtime`` may import both (R-IG4).

A read resolves the account (by alias, else ``pinterest.default``), checks its identity once per
daemon lifetime (4.5), checks the capability, and calls Pinterest through the account's
``PinterestApi``. Every provider id becomes an opaque ref; every text is untrusted. A page's
``bookmark`` becomes a client-bound ``cur_`` through ``ContextHandles``, with the ``pna_`` as the
handle's target and ``pinterest`` as its actor, so a cursor from one tool, client, account or
epoch never reads another. Nothing is persisted but the refs and the ledgers.
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
from comms.core.providers.pinterest_analytics import account_params, pin_params
from comms.core.providers.protocols import SemanticOperation
from comms.services.capability import STATE_CODE, CapabilityService
from comms.services.handles import ContextHandles
from comms.services.mutations import CallContext, MutationExecutor
from comms.transports.pinterest import store
from comms.transports.pinterest.accounts import ACTOR, AccountRuntime, PinterestAccounts
from comms.transports.pinterest.classify import api_read
from comms.transports.pinterest.items import (
    analytics,
    board_item,
    media_status,
    page_of,
    pin_item,
    profile,
)
from comms.transports.pinterest.publish import budget_used, check_pin_create

__all__ = ["PinterestService"]

_PAGE = 25
_PAGE_MAX = 100


class PinterestService:
    def __init__(
        self,
        conn: Any,
        accounts: PinterestAccounts,
        capability: CapabilityService,
        handles: ContextHandles,
        *,
        clock: Callable[[], datetime],
        executor: MutationExecutor | None = None,
    ) -> None:
        self._conn, self._accounts, self._capability = conn, accounts, capability
        self._handles, self._clock, self._executor = handles, clock, executor

    def __repr__(self) -> str:
        return "PinterestService(<redacted>)"

    # -- shared --------------------------------------------------------------------------------

    def _read(self, alias: object, capability: C) -> tuple[AccountRuntime, str]:
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
        return {"account": runtime.alias, "account_ref": runtime.ref,
                "untrusted": {"account_username": username, **(untrusted or {})}}  # fmt: skip

    def _bookmark(
        self, client: str, kind: str, runtime: AccountRuntime, args: Mapping[str, Any]
    ) -> str | None:
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
        bookmark = position.get("bookmark")
        if not isinstance(bookmark, str):
            raise CommsError("STALE_HANDLE")
        return bookmark

    def _token(
        self, client: str, kind: str, runtime: AccountRuntime, args: Mapping[str, Any],
        bookmark: str | None,
    ) -> str | None:  # fmt: skip
        if bookmark is None:
            return None
        snapshot = {"kind": kind, "args": _query(args)}
        digest = hashlib.sha256(jcs_dumps(snapshot)).hexdigest()
        ctx_ref = self._handles.open(
            client=client, owner=client, target_ref=runtime.ref, actor=ACTOR,
            query_digest=digest, snapshot=snapshot,
        )  # fmt: skip
        return self._handles.cursor(client, ctx_ref, {"bookmark": bookmark})

    def _page(
        self, client: str, kind: str, runtime: AccountRuntime, args: Mapping[str, Any],
        call: Callable[[dict[str, str]], Any],
    ) -> tuple[list[Any], str | None]:  # fmt: skip
        bookmark = self._bookmark(client, kind, runtime, args)
        limit = args.get("limit", _PAGE)
        params = {"page_size": str(limit), **({"bookmark": bookmark} if bookmark else {})}
        body = api_read(runtime.api, lambda: call(params))
        items, more = page_of(body)
        return items, self._token(client, kind, runtime, args, more)

    # -- account and profile ---------------------------------------------------------------------

    def account_list(self) -> dict[str, Any]:
        now = timeutil.utc(self._clock())
        rows = {row.alias: row for row in store.live_accounts(self._conn)}
        accounts = []
        for alias, policy in sorted(self._accounts.settings.accounts.items()):
            row = rows.get(alias)
            days = refresh_days = None
            if row is not None:
                days = max(0, (timeutil.instant(row.access_expires_at) - now) // timedelta(days=1))
                refresh_days = max(
                    0, (timeutil.instant(row.refresh_expires_at) - now) // timedelta(days=1)
                )
            accounts.append(
                {
                    "account": alias,
                    "account_ref": row.ref if row else None,
                    "registered": row is not None,
                    "writes": policy.writes,
                    "sandbox": policy.sandbox,
                    "token_expires_in_days": days,
                    "refresh_expires_in_days": refresh_days,
                    "untrusted": {"label": policy.label},
                }
            )
        return {"accounts": accounts, "default": self._accounts.settings.default}

    def whoami(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.PROFILE_READ)
        row = store.account_by_ref(self._conn, runtime.ref)
        return {**self._head(runtime, username), "identity_checked": True,
                "sandbox": runtime.policy.sandbox,
                "token_expires_at": row.access_expires_at if row else None,
                "refresh_expires_at": row.refresh_expires_at if row else None}  # fmt: skip

    def profile(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.PROFILE_READ)
        found = profile(runtime)
        return {**found, **self._head(runtime, username, found.pop("untrusted"))}

    # -- boards ----------------------------------------------------------------------------------

    def board_list(self, client: str, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.BOARD_LIST)
        privacy = args.get("privacy", "ALL")

        def call(params: dict[str, str]) -> Any:
            return runtime.api.get("boards", params={**params, "privacy": str(privacy)})

        data, token = self._page(client, "board_list", runtime, args, call)
        now = self._clock()
        items = [board_item(self._conn, runtime, r, now=now) for r in data if isinstance(r, dict)]
        return {**self._head(runtime, username), "items": items, "next_cursor": token}

    def _board_id(self, runtime: AccountRuntime, board: object) -> str:
        return store.resolve_object(self._conn, board, "board", runtime.account_id)

    def board_get(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.BOARD_GET)
        ident = self._board_id(runtime, args["board"])
        raw = api_read(runtime.api, lambda: runtime.api.get("boards/{id}", ident))
        item = board_item(self._conn, runtime, raw, now=self._clock())
        return {**item, **self._head(runtime, username, item.pop("untrusted"))}

    def board_pins(self, client: str, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.PIN_LIST)
        ident = self._board_id(runtime, args["board"])

        def call(params: dict[str, str]) -> Any:
            return runtime.api.get("boards/{id}/pins", ident, params=params)

        data, token = self._page(client, "board_pins", runtime, args, call)
        now = self._clock()
        items = [pin_item(self._conn, runtime, r, now=now) for r in data if isinstance(r, dict)]
        return {**self._head(runtime, username), "items": items, "next_cursor": token}

    # -- pins ------------------------------------------------------------------------------------

    def pin_list(self, client: str, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.PIN_LIST)

        def call(params: dict[str, str]) -> Any:
            return runtime.api.get("pins", params=params)

        data, token = self._page(client, "pin_list", runtime, args, call)
        now = self._clock()
        items = [pin_item(self._conn, runtime, r, now=now) for r in data if isinstance(r, dict)]
        return {**self._head(runtime, username), "items": items, "next_cursor": token}

    def _pin_id(self, runtime: AccountRuntime, pin: object) -> str:
        return store.resolve_object(self._conn, pin, "pin", runtime.account_id)

    def pin_get(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.PIN_GET)
        ident = self._pin_id(runtime, args["pin"])
        params = {"pin_metrics": "true" if args.get("metrics") else "false"}
        raw = api_read(runtime.api, lambda: runtime.api.get("pins/{id}", ident, params=params))
        item = pin_item(self._conn, runtime, raw, now=self._clock())
        return {**item, **self._head(runtime, username, item.pop("untrusted"))}

    def pin_analytics(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.INSIGHTS_READ)
        ident = self._pin_id(runtime, args["pin"])
        try:
            params = pin_params(args, today=timeutil.utc(self._clock()).date())
        except ValueError:
            raise CommsError("INVALID_ARGUMENT") from None
        body = api_read(
            runtime.api, lambda: runtime.api.get("pins/{id}/analytics", ident, params=params)
        )
        return {**self._head(runtime, username), "pin": args["pin"], **analytics(body)}

    def account_analytics(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.INSIGHTS_READ)
        try:
            params = account_params(args, today=timeutil.utc(self._clock()).date())
        except ValueError:
            raise CommsError("INVALID_ARGUMENT") from None
        body = api_read(
            runtime.api, lambda: runtime.api.get("user_account/analytics", params=params)
        )
        return {**self._head(runtime, username), **analytics(body)}

    # -- media and the budget --------------------------------------------------------------------

    def media_status(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.MEDIA_STATUS_READ)
        row = store.media(self._conn, args["media"], runtime.account_id)
        body = api_read(runtime.api, lambda: runtime.api.get("media/{id}", row.media_id))
        status = media_status(body)
        if status is not None:
            store.mark_media(self._conn, row.ref, status)
        return {**self._head(runtime, username), "media": row.ref, "status": status}

    def _quota(self, runtime: AccountRuntime) -> dict[str, Any]:
        limit = runtime.api.last_rate_limit
        return {
            "pins_last_24h": budget_used(self._conn, runtime, self._clock()),
            "daily_pin_budget": self._accounts.settings.daily_pin_budget,
            "rate_limit_remaining": None if limit is None else limit.remaining,
            "rate_limit_reset_s": None if limit is None else limit.reset,
        }

    def publish_quota(self, args: Mapping[str, Any]) -> dict[str, Any]:
        runtime, username = self._read(args.get("account"), C.PUBLISHING_QUOTA_READ)
        return {**self._head(runtime, username), **self._quota(runtime)}

    def _blocked(self, runtime: AccountRuntime) -> str | None:
        """What a ``pin_create`` answers before Pinterest: the ledger's budget."""
        if (
            budget_used(self._conn, runtime, self._clock())
            >= self._accounts.settings.daily_pin_budget
        ):
            return "PIN_BUDGET"
        return None

    def pin_preview(self, a: Mapping[str, Any]) -> dict[str, Any]:
        """Exactly what one ``pin_create`` would do (D-P3), with an advisory ``preview_digest``
        the create may echo. Read-only: for a video, the upload's status is read."""
        runtime = self._accounts.resolve(a.get("account"), for_write=True)
        username = self._accounts.username(runtime)
        state = self._capability.state(ACTOR, runtime.target(), C.PUBLISHING_QUOTA_READ)
        if state is not S.AVAILABLE:
            raise CommsError(STATE_CODE[state])
        args = _create_args(a, ("account",))
        try:
            check_pin_create(args)
        except ValueError:
            raise CommsError("INVALID_ARGUMENT") from None
        self._board_id(runtime, args["board"])  # NOT_FOUND for another account's board
        media_state = None
        if args["kind"] == "video":
            media_state = self.media_status({"account": runtime.alias, "media": args["media"]})[
                "status"
            ]
        write_state = self._capability.state(ACTOR, runtime.target(), C.PIN_CREATE)
        refusal = STATE_CODE[write_state] if write_state is not S.AVAILABLE else None
        if refusal is None and media_state is not None and media_state != "succeeded":
            refusal = "MEDIA_FAILED" if media_state == "failed" else "MEDIA_NOT_READY"
        title, description = args.get("title"), args.get("description")
        return {
            **self._head(runtime, username),
            "kind": args["kind"],
            "board": args["board"],
            "images": len(args["images"]) if args["kind"] == "carousel" else None,
            "media_status": media_state,
            "title_chars": len(title) if isinstance(title, str) else 0,
            "description_chars": len(description) if isinstance(description, str) else 0,
            "writes_allowed": write_state is S.AVAILABLE,
            **self._quota(runtime),
            "refusal": refusal or self._blocked(runtime),
            "preview_digest": _preview_digest("pin_create", runtime.ref, args),
            "untrusted_text": description if isinstance(description, str) else None,
        }

    # -- writes ------------------------------------------------------------------------------------

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
        """One write: the named account (never a default, D-P5), its identity, its ceiling
        (``NOT_AUTHORIZED`` before anything is recorded), then the executor (A28, A41)."""
        if self._executor is None:
            raise CommsError("NOT_CONFIGURED")
        runtime = self._accounts.resolve(a.get("account"), for_write=True)
        username = self._accounts.username(runtime)
        self._capability.require_for_write(ACTOR, runtime.target(), capability)
        head = {**self._head(runtime, username), "actor": ACTOR}
        replay = records.find(self._conn, client, a["request_id"]) is not None
        if prepare is not None and not replay:  # a replay answers its record (A28), unchecked
            refused = prepare(runtime)
            if refused is not None:
                return {**head, **refused}
        outcome = self._executor.provider(
            CallContext(client), tool, runtime.target(), SemanticOperation(capability, dict(args)),
            a["request_id"], on_created=None if on_created is None else on_created(runtime),
        )  # fmt: skip
        extra = {k: v for k, v in outcome.result.items() if k not in ("state", "code")}
        return {**head, "result": outcome.state, "code": outcome.code, "op_ref": outcome.op_ref,
                "replayed": outcome.replayed, **extra}  # fmt: skip

    def _object_made(
        self, kind: str, key: str
    ) -> Callable[[AccountRuntime], Callable[[Any, str], Mapping[str, Any]]]:
        def bind(runtime: AccountRuntime) -> Callable[[Any, str], Mapping[str, Any]]:
            def made(conn: Any, provider_ref: str) -> Mapping[str, Any]:
                ref = store.object_ref(
                    conn, runtime.account_id, kind, provider_ref, now=self._clock()
                )
                if kind == "pin":
                    store.record_publication(conn, runtime.account_id, ref, now=self._clock())
                return {key: ref}

            return made

        return bind

    def board_create(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        args = _create_args(a, ("account", "request_id"))
        result = self._write(
            client, "comms_pinterest_board_create", a, C.BOARD_CREATE, args,
            on_created=self._object_made("board", "board"),
        )  # fmt: skip
        return {"board": None, **result}

    def video_upload(
        self, client: str, a: Mapping[str, Any], data: bytes, mime: str
    ) -> dict[str, Any]:
        """The staged bytes the facade took (``upl_``) go to Pinterest once (D-P8)."""

        def bind(runtime: AccountRuntime) -> Callable[[Any, str], Mapping[str, Any]]:
            def made(conn: Any, provider_ref: str) -> Mapping[str, Any]:
                ref = store.record_media(
                    conn, runtime.account_id, provider_ref, now=self._clock(), status="registered"
                )
                return {"media": ref}

            return made

        result = self._write(
            client, "comms_pinterest_video_upload", a, C.MEDIA_UPLOAD,
            {"data": data, "mime": mime}, on_created=bind,
        )  # fmt: skip
        return {"media": None, **result}

    def pin_create(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        args = _create_args(a, ("account", "request_id", "preview_digest"))

        def prepare(runtime: AccountRuntime) -> dict[str, Any] | None:
            try:
                check_pin_create(args)  # shapes first, so nothing below sees a malformed call
            except ValueError:
                raise CommsError("INVALID_ARGUMENT") from None
            digest = a.get("preview_digest")
            if digest is not None and digest != _preview_digest("pin_create", runtime.ref, args):
                raise CommsError("INVALID_ARGUMENT")  # not what was previewed
            self._board_id(runtime, args["board"])  # NOT_FOUND before anything is recorded
            if args["kind"] == "video":
                store.media(self._conn, args["media"], runtime.account_id)
            code = self._blocked(runtime)
            if code is None:
                return None
            return {"result": "FAILED", "code": code, "op_ref": None, "replayed": False}

        result = self._write(
            client, "comms_pinterest_pin_create", a, C.PIN_CREATE, args,
            on_created=self._object_made("pin", "pin"), prepare=prepare,
        )  # fmt: skip
        return {"pin": None, **result}

    def pin_update(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        args = _create_args(a, ("account", "request_id"))

        def prepare(runtime: AccountRuntime) -> None:
            self._pin_id(runtime, args["pin"])
            if "board" in args:
                self._board_id(runtime, args["board"])

        return self._write(
            client, "comms_pinterest_pin_update", a, C.PIN_UPDATE, args, prepare=prepare
        )

    def pin_delete(self, client: str, a: Mapping[str, Any]) -> dict[str, Any]:
        def prepare(runtime: AccountRuntime) -> None:
            self._pin_id(runtime, a["pin"])  # NOT_FOUND before anything is recorded

        return self._write(
            client, "comms_pinterest_pin_delete", a, C.PIN_DELETE, {"pin": a["pin"]},
            prepare=prepare,
        )  # fmt: skip


def _create_args(a: Mapping[str, Any], drop: tuple[str, ...]) -> dict[str, Any]:
    """A write's arguments as Pinterest will see them: everything but comms' own fields."""
    return {k: (list(v) if isinstance(v, (list, tuple)) else v) for k, v in a.items()
            if k not in drop}  # fmt: skip


def _preview_digest(tool: str, account_ref: str, args: Mapping[str, Any]) -> str:
    body = {"tool": tool, "account": account_ref, "args": dict(args)}
    return hashlib.sha256(domains.PINTEREST_PREVIEW + jcs_dumps(body)).hexdigest()


def _query(args: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in args.items() if k != "cursor"}
