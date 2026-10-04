"""``transport instagram account add|list|remove``, ``token refresh`` and ``doctor``
(proposed A49, section 4.4; A13, A37).

Adding an account is the staged credential rotation (stage, prove, activate, re-check) with one
more proof: ``GET /me?fields=user_id,username`` must answer, and its ``user_id`` must not belong
to another live account. Then one audited transaction records the ``iga_``. The token arrives
the way every credential does: typed at the owner's terminal, over the peer-credential admin
socket, never echoed, logged or audited. A refresh persists the token Meta **returns** (not the
old one) through the same rotation, and only if ``/me`` still names the registered account.
Replies carry the alias, refs, versions, dates and the public username, never a token or an id.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Any

from comms.core import timeutil
from comms.core.credentials import (
    CredentialCheckFailed,
    active_credential,
    revoke_credential,
    rotate_credential,
)
from comms.core.errors import CommsError
from comms.core.keys.purposes import instagram_alias, instagram_token_purpose
from comms.core.keys.slots import KeySlotError
from comms.runtime.operator.context import OperatorContext, OperatorHandler
from comms.runtime.proofs import CredentialProofFailed, one_value_store
from comms.transports.instagram import store
from comms.transports.instagram.accounts import read_identity
from comms.transports.instagram.config import InstagramSettings
from comms.transports.instagram.doctor import findings
from comms.transports.instagram.http import GraphIgApi, GraphTransportError

__all__ = ["INSTAGRAM_HANDLERS", "TOKEN_LIFETIME", "InstagramOperator"]

TOKEN_LIFETIME = timedelta(days=60)  # dashboard and refreshed tokens (section 2) ✅
_MAX_LIFETIME = timedelta(days=90)


class InstagramOperator:
    """The network side of the operator commands, over a candidate token (never stored here).
    ``transport`` is the httpx seam for tests."""

    def __init__(self, conn: Any, settings: InstagramSettings | None, *, transport: Any = None):
        self._conn, self._settings, self._transport = conn, settings, transport

    def __repr__(self) -> str:
        return "InstagramOperator(<redacted>)"

    def configured(self, alias: str) -> bool:
        return self._settings is not None and alias in self._settings.accounts

    def aliases(self) -> list[str]:
        return [] if self._settings is None else sorted(self._settings.accounts)

    def _api(self, alias: str, token: bytes) -> GraphIgApi:
        purpose = instagram_token_purpose(alias)
        version = self._settings.api_version if self._settings else "v25.0"
        try:
            return GraphIgApi(
                one_value_store(purpose, token), purpose=purpose, version=1,
                api_version=version, transport=self._transport,
            )  # fmt: skip
        except ValueError:
            raise CredentialProofFailed("the token is not an Instagram access token") from None

    def probe(self, alias: str, token: bytes) -> tuple[str, str]:
        """``(user_id, username)`` for a candidate token; ``CredentialProofFailed`` otherwise."""
        api = self._api(alias, token)
        try:
            return read_identity(api)
        except CommsError:
            raise CredentialProofFailed("the token did not prove itself (GET /me)") from None
        finally:
            api.close()

    def refresh(self, alias: str, token: bytes) -> tuple[bytes, timedelta]:
        """Meta's refreshed token and its lifetime (``expires_in``), or ``CredentialProofFailed``."""
        api = self._api(alias, token)
        try:
            response = api.refresh()
        except GraphTransportError:
            raise CredentialProofFailed("Meta did not answer the refresh") from None
        finally:
            api.close()
        body = response.envelope or {}
        fresh, expires_in = body.get("access_token"), body.get("expires_in")
        if (
            response.http_status != 200
            or not isinstance(fresh, str)
            or isinstance(expires_in, bool)
            or not isinstance(expires_in, int)
            or not 0 < expires_in <= _MAX_LIFETIME.total_seconds()
        ):
            raise CredentialProofFailed("Meta refused the refresh (a token under 24 hours old?)")
        if not fresh.isascii():
            raise CredentialProofFailed("Meta returned a malformed token")
        return fresh.encode("ascii"), timedelta(seconds=expires_in)

    def proofs(self) -> Mapping[str, Callable[[bytes], None]]:
        """``credential set|rotate meta-ig-access-token.<alias>``: the candidate must name the
        registered account (an unregistered alias is added with ``instagram account add``)."""

        def proof(alias: str) -> Callable[[bytes], None]:
            def check(value: bytes) -> None:
                row = store.account_by_alias(self._conn, alias)
                if row is None:
                    raise CredentialProofFailed(
                        "add the account first: comms transport instagram account add"
                    )
                if self.probe(alias, value)[0] != row.user_id:
                    raise CredentialProofFailed("the token names another Instagram account")

            return check

        return {instagram_token_purpose(alias): proof(alias) for alias in self.aliases()}


def _operator(ctx: OperatorContext) -> InstagramOperator:
    operator = getattr(ctx, "instagram", None)
    if not isinstance(operator, InstagramOperator) or ctx.secrets is None:
        raise ValueError("instagram accounts are managed by the daemon")
    return operator


def _alias(operator: InstagramOperator, args: dict[str, Any]) -> str:
    alias = instagram_alias(args.get("alias"))
    if alias is None:
        raise ValueError("an alias is a-z, 0-9, _ or -, at most 32")
    if not operator.configured(alias):
        raise ValueError("configure the alias under instagram.accounts in comms.json first")
    return alias


def _reloaded(ctx: OperatorContext) -> bool:
    return bool(ctx.reload()["reloaded"]) if ctx.reload is not None else False


def _add(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    operator = _operator(ctx)
    alias = _alias(operator, args)
    value = args.get("value")
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("the token is missing or too long")
    if store.account_by_alias(ctx.conn, alias) is not None:
        raise ValueError(
            "the account is already added: use comms transport instagram token refresh"
        )
    seen: dict[str, str] = {}
    failure: list[str] = []

    def prove(candidate: bytes) -> None:
        try:
            user_id, username = operator.probe(alias, candidate)
            taken = ctx.conn.execute(
                "SELECT 1 FROM instagram_accounts WHERE user_id = ? AND removed_at IS NULL",
                (user_id,),
            ).fetchone()
            if taken is not None or seen.get("user_id", user_id) != user_id:
                raise CredentialProofFailed("that Instagram account is already added")
        except CredentialProofFailed as refused:
            failure.append(str(refused))
            raise
        seen.update(user_id=user_id, username=username)

    purpose = instagram_token_purpose(alias)
    try:
        version = rotate_credential(
            ctx.writer, ctx.secrets, purpose, value.encode("utf-8"), prove=prove, now=ctx.clock()
        )
    except CredentialCheckFailed:
        reason = failure[0] if failure else "Meta did not accept it"
        raise ValueError(f"the account was not added: {reason}") from None
    with ctx.writer.transaction() as tx:
        ref = store.register_account(
            tx.conn, alias, seen["user_id"], now=tx.now, lifetime=TOKEN_LIFETIME
        )
        tx.append("admin.instagram_account", subject_ref=ref, payload={"action": "added"})
    return {"account": ref, "alias": alias, "username": seen["username"], "version": version,
            "expires_at": timeutil.iso(ctx.clock() + TOKEN_LIFETIME), "reloaded": _reloaded(ctx)}  # fmt: skip


def _list(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    operator = _operator(ctx)
    rows = {row.alias: row for row in store.live_accounts(ctx.conn)}
    accounts = []
    for alias in sorted(set(rows) | set(operator.aliases())):
        row = rows.get(alias)
        accounts.append(
            {
                "alias": alias,
                "account": row.ref if row else None,
                "configured": operator.configured(alias),
                "expires_at": row.expires_at if row else None,
            }
        )
    return {"accounts": accounts}


def _remove(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    _operator(ctx)
    alias = instagram_alias(args.get("alias"))
    row = None if alias is None else store.account_by_alias(ctx.conn, alias)
    if alias is None or row is None:
        raise ValueError("no such Instagram account")
    try:
        revoke_credential(ctx.writer, ctx.secrets, instagram_token_purpose(alias), now=ctx.clock())
        revoked = True
    except KeySlotError:
        revoked = False  # no active token: the account row still leaves
    with ctx.writer.transaction() as tx:
        store.remove_account(tx.conn, row.ref, now=tx.now)
        tx.append("admin.instagram_account", subject_ref=row.ref, payload={"action": "removed"})
    return {
        "account": row.ref,
        "alias": alias,
        "token_revoked": revoked,
        "reloaded": _reloaded(ctx),
    }


def _refresh(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    operator = _operator(ctx)
    if bool(args.get("all")) == (args.get("alias") is not None):
        raise ValueError("name one --alias, or --all")
    aliases = (
        [row.alias for row in store.live_accounts(ctx.conn)]
        if args.get("all")
        else [_alias(operator, args)]
    )
    results = []
    for alias in aliases:
        row = store.account_by_alias(ctx.conn, alias)
        purpose = instagram_token_purpose(alias)
        token = None if row is None else active_credential(ctx.conn, ctx.secrets, purpose)
        if row is None or token is None:
            results.append({"alias": alias, "refreshed": False, "reason": "not added"})
            continue
        try:
            fresh, lifetime = operator.refresh(alias, token)
        except CredentialProofFailed as refused:
            results.append({"alias": alias, "refreshed": False, "reason": str(refused)})
            continue

        def prove(candidate: bytes, alias: str = alias, user_id: str = row.user_id) -> None:
            if operator.probe(alias, candidate)[0] != user_id:
                raise CredentialProofFailed("the refreshed token names another account")

        try:
            version = rotate_credential(
                ctx.writer, ctx.secrets, purpose, fresh, prove=prove, now=ctx.clock()
            )
        except CredentialCheckFailed:
            results.append(
                {
                    "alias": alias,
                    "refreshed": False,
                    "reason": "the refreshed token did not prove itself",
                }
            )
            continue
        with ctx.writer.transaction() as tx:
            store.set_expiry(tx.conn, row.ref, now=tx.now, lifetime=lifetime)
            tx.append(
                "admin.instagram_account",
                subject_ref=row.ref,
                payload={"action": "token_refreshed"},
            )
        results.append({"alias": alias, "refreshed": True, "version": version,
                        "expires_at": timeutil.iso(ctx.clock() + lifetime)})  # fmt: skip
    return {
        "results": results,
        "reloaded": _reloaded(ctx) if any(r["refreshed"] for r in results) else False,
    }


def _doctor(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    operator = _operator(ctx)
    live = {}
    for row in store.live_accounts(ctx.conn):
        purpose = instagram_token_purpose(row.alias)
        try:
            live[row.alias] = (row, active_credential(ctx.conn, ctx.secrets, purpose))
        except KeySlotError:
            live[row.alias] = (row, None)

    def identity(alias: str, token: bytes) -> str | None:
        try:
            return operator.probe(alias, token)[0]
        except CredentialProofFailed:
            return None

    return {"findings": findings(operator.aliases(), live, identity, now=ctx.clock())}


INSTAGRAM_HANDLERS: dict[tuple[str, ...], OperatorHandler] = {
    ("transport", "instagram", "account", "add"): _add,
    ("transport", "instagram", "account", "list"): _list,
    ("transport", "instagram", "account", "remove"): _remove,
    ("transport", "instagram", "token", "refresh"): _refresh,
    ("transport", "instagram", "doctor"): _doctor,
}
