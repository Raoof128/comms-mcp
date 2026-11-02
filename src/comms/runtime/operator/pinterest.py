"""``transport pinterest auth-url``, ``account add|list|remove``, ``token refresh`` and
``doctor`` (proposed A50, section 4.4; A13, A37).

Adding an account is the OAuth code exchange (D-P4) followed by the staged credential rotation
for both tokens: the authorization code is typed at the owner's terminal, exchanged at
``POST /v5/oauth/token`` under the app id and the stored app secret, the access token proved by
``GET /v5/user_account`` (its ``id`` must not belong to another live account), both tokens
staged and activated, then one audited transaction records the ``pna_``. A refresh exchanges the
refresh token the same way and persists what Pinterest **returns**, only if ``/user_account``
still names the registered account. Replies carry the alias, refs, versions, dates and the public
username, never a code, a token, the secret or an id.
"""

from __future__ import annotations

import secrets as _secrets
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
from comms.core.keys.purposes import (
    PINTEREST_APP_SECRET,
    instagram_alias,
    pinterest_token_purposes,
)
from comms.core.keys.slots import KeySlotError
from comms.runtime.operator.context import OperatorContext, OperatorHandler
from comms.runtime.proofs import CredentialProofFailed, one_value_store
from comms.transports.pinterest import store
from comms.transports.pinterest.accounts import read_identity
from comms.transports.pinterest.config import PinterestSettings
from comms.transports.pinterest.doctor import findings
from comms.transports.pinterest.http import (
    GraphRefused,
    GraphTransportError,
    PinterestApi,
    TokenGrant,
    TokenRefused,
    authorize_url,
    exchange_token,
)

__all__ = ["PINTEREST_HANDLERS", "PinterestOperator", "app_secret_proof"]

_MAX_LIFETIME = timedelta(days=366)
_DEFAULT_REFRESH = timedelta(days=60)  # ✅ the continuous refresh token's window


def app_secret_proof(value: bytes) -> None:
    """``credential set pinterest-app-secret``: a local shape check (no whoami exists)."""
    if not 16 <= len(value) <= 256 or not all(0x21 <= b <= 0x7E for b in value):
        raise CredentialProofFailed("the app secret is not printable ASCII of 16 to 256 bytes")


class PinterestOperator:
    """The network side of the operator commands, over candidate tokens (never stored here).
    ``transport`` is the httpx seam for tests."""

    def __init__(self, conn: Any, settings: PinterestSettings | None, *, transport: Any = None):
        self._conn, self._settings, self._transport = conn, settings, transport

    def __repr__(self) -> str:
        return "PinterestOperator(<redacted>)"

    def configured(self, alias: str) -> bool:
        return self._settings is not None and alias in self._settings.accounts

    def aliases(self) -> list[str]:
        return [] if self._settings is None else sorted(self._settings.accounts)

    def sandbox(self, alias: str) -> bool:
        return bool(self._settings and self._settings.accounts[alias].sandbox)

    def settings(self) -> PinterestSettings:
        if self._settings is None:
            raise ValueError("configure pinterest in comms.json first")
        return self._settings

    def _api(self, alias: str, token: bytes) -> PinterestApi:
        purpose = pinterest_token_purposes(alias)[0]
        try:
            return PinterestApi(
                one_value_store(purpose, token), purpose=purpose, version=1,
                sandbox=self.sandbox(alias), transport=self._transport,
            )  # fmt: skip
        except ValueError:
            raise CredentialProofFailed("the token is not a Pinterest access token") from None

    def probe(self, alias: str, token: bytes) -> tuple[str, str]:
        """``(user_id, username)`` for a candidate access token; ``CredentialProofFailed``
        otherwise."""
        api = self._api(alias, token)
        try:
            return read_identity(api)
        except CommsError:
            raise CredentialProofFailed(
                "the token did not prove itself (GET /user_account)"
            ) from None
        finally:
            api.close()

    def exchange(
        self,
        alias: str,
        app_secret: bytes,
        *,
        code: str | None = None,
        refresh: bytes | None = None,
    ) -> TokenGrant:
        settings = self.settings()
        try:
            return exchange_token(
                settings.app_id, app_secret, code=code, refresh_token=refresh,
                redirect_uri=settings.redirect_uri, sandbox=self.sandbox(alias),
                transport=self._transport,
            )  # fmt: skip
        except GraphTransportError:
            raise CredentialProofFailed("Pinterest did not answer the token request") from None
        except (GraphRefused, TokenRefused) as refused:
            raise CredentialProofFailed(str(refused)) from None

    def proofs(self) -> Mapping[str, Callable[[bytes], None]]:
        """``credential set|rotate`` on a Pinterest purpose: the app secret by shape; an access
        token must name the registered account; a refresh token by shape only."""

        def access_proof(alias: str) -> Callable[[bytes], None]:
            def check(value: bytes) -> None:
                row = store.account_by_alias(self._conn, alias)
                if row is None:
                    raise CredentialProofFailed(
                        "add the account first: comms transport pinterest account add"
                    )
                if self.probe(alias, value)[0] != row.user_id:
                    raise CredentialProofFailed("the token names another Pinterest account")

            return check

        def refresh_proof(value: bytes) -> None:
            if not 20 <= len(value) <= 2048 or not value.isascii():
                raise CredentialProofFailed("the refresh token is malformed")

        out: dict[str, Callable[[bytes], None]] = {PINTEREST_APP_SECRET: app_secret_proof}
        for alias in self.aliases():
            access, refresh = pinterest_token_purposes(alias)
            out[access], out[refresh] = access_proof(alias), refresh_proof
        return out


def _operator(ctx: OperatorContext) -> PinterestOperator:
    operator = getattr(ctx, "pinterest", None)
    if not isinstance(operator, PinterestOperator) or ctx.secrets is None:
        raise ValueError("pinterest accounts are managed by the daemon")
    return operator


def _alias(operator: PinterestOperator, args: dict[str, Any]) -> str:
    alias = instagram_alias(args.get("alias"))
    if alias is None:
        raise ValueError("an alias is a-z, 0-9, _ or -, at most 32")
    if not operator.configured(alias):
        raise ValueError("configure the alias under pinterest.accounts in comms.json first")
    return alias


def _app_secret(ctx: OperatorContext) -> bytes:
    try:
        secret = active_credential(ctx.conn, ctx.secrets, PINTEREST_APP_SECRET)
    except KeySlotError:
        secret = None
    if secret is None:
        raise ValueError("set the app secret first: comms credential set pinterest-app-secret")
    return secret


def _reloaded(ctx: OperatorContext) -> bool:
    return bool(ctx.reload()["reloaded"]) if ctx.reload is not None else False


def _lifetimes(grant: TokenGrant) -> tuple[timedelta, timedelta | None]:
    access = timedelta(seconds=min(grant.access_expires_in, int(_MAX_LIFETIME.total_seconds())))
    refresh = (
        None
        if grant.refresh_token is None
        else timedelta(
            seconds=min(grant.refresh_expires_in or int(_DEFAULT_REFRESH.total_seconds()),
                        int(_MAX_LIFETIME.total_seconds()))
        )
    )  # fmt: skip
    return access, refresh


def _auth_url(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    operator = _operator(ctx)
    alias = _alias(operator, args)
    settings = operator.settings()
    state = _secrets.token_urlsafe(24)
    return {
        "alias": alias,
        "url": authorize_url(settings.app_id, settings.redirect_uri, state),
        "state": state,
        "sandbox": operator.sandbox(alias),
        "next": "sign in, copy the code from the redirect, then: comms transport pinterest"
        f" account add {alias}",
    }


def _add(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    operator = _operator(ctx)
    alias = _alias(operator, args)
    value = args.get("value")
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("the authorization code is missing or too long")
    if store.account_by_alias(ctx.conn, alias) is not None:
        raise ValueError(
            "the account is already added: use comms transport pinterest token refresh"
        )
    app_secret = _app_secret(ctx)
    try:
        grant = operator.exchange(alias, app_secret, code=value.strip())
    except CredentialProofFailed as refused:
        raise ValueError(f"the account was not added: {refused}") from None
    if grant.refresh_token is None:
        raise ValueError("the account was not added: Pinterest granted no refresh token")
    seen: dict[str, str] = {}
    failure: list[str] = []

    def prove(candidate: bytes) -> None:
        try:
            user_id, username = operator.probe(alias, candidate)
            taken = ctx.conn.execute(
                "SELECT 1 FROM pinterest_accounts WHERE user_id = ? AND removed_at IS NULL",
                (user_id,),
            ).fetchone()
            if taken is not None or seen.get("user_id", user_id) != user_id:
                raise CredentialProofFailed("that Pinterest account is already added")
        except CredentialProofFailed as refused:
            failure.append(str(refused))
            raise
        seen.update(user_id=user_id, username=username)

    access_purpose, refresh_purpose = pinterest_token_purposes(alias)
    try:
        version = rotate_credential(
            ctx.writer, ctx.secrets, access_purpose, grant.access_token, prove=prove,
            now=ctx.clock(),
        )  # fmt: skip
    except CredentialCheckFailed:
        reason = failure[0] if failure else "Pinterest did not accept it"
        raise ValueError(f"the account was not added: {reason}") from None
    rotate_credential(
        ctx.writer, ctx.secrets, refresh_purpose, grant.refresh_token, prove=lambda _v: None,
        now=ctx.clock(),
    )  # fmt: skip
    access_life, refresh_life = _lifetimes(grant)
    with ctx.writer.transaction() as tx:
        ref = store.register_account(
            tx.conn, alias, seen["user_id"], now=tx.now, access_lifetime=access_life,
            refresh_lifetime=refresh_life or _DEFAULT_REFRESH,
        )  # fmt: skip
        tx.append("admin.pinterest_account", subject_ref=ref, payload={"action": "added"})
    return {"account": ref, "alias": alias, "username": seen["username"], "version": version,
            "expires_at": timeutil.iso(ctx.clock() + access_life),
            "refresh_expires_at": timeutil.iso(ctx.clock() + (refresh_life or _DEFAULT_REFRESH)),
            "reloaded": _reloaded(ctx)}  # fmt: skip


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
                "expires_at": row.access_expires_at if row else None,
                "refresh_expires_at": row.refresh_expires_at if row else None,
            }
        )
    return {"accounts": accounts}


def _remove(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    _operator(ctx)
    alias = instagram_alias(args.get("alias"))
    row = None if alias is None else store.account_by_alias(ctx.conn, alias)
    if alias is None or row is None:
        raise ValueError("no such Pinterest account")
    revoked = 0
    for purpose in pinterest_token_purposes(alias):
        try:
            revoke_credential(ctx.writer, ctx.secrets, purpose, now=ctx.clock())
            revoked += 1
        except KeySlotError:
            pass  # no active token: the account row still leaves
    with ctx.writer.transaction() as tx:
        store.remove_account(tx.conn, row.ref, now=tx.now)
        tx.append("admin.pinterest_account", subject_ref=row.ref, payload={"action": "removed"})
    return {"account": row.ref, "alias": alias, "tokens_revoked": revoked,
            "reloaded": _reloaded(ctx)}  # fmt: skip


def _refresh(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    operator = _operator(ctx)
    if bool(args.get("all")) == (args.get("alias") is not None):
        raise ValueError("name one --alias, or --all")
    aliases = (
        [row.alias for row in store.live_accounts(ctx.conn)]
        if args.get("all")
        else [_alias(operator, args)]
    )
    app_secret = _app_secret(ctx)
    results = []
    for alias in aliases:
        row = store.account_by_alias(ctx.conn, alias)
        access_purpose, refresh_purpose = pinterest_token_purposes(alias)
        try:
            refresh = (
                None if row is None else active_credential(ctx.conn, ctx.secrets, refresh_purpose)
            )
        except KeySlotError:
            refresh = None
        if row is None or refresh is None:
            results.append({"alias": alias, "refreshed": False, "reason": "not added"})
            continue
        try:
            grant = operator.exchange(alias, app_secret, refresh=refresh)
        except CredentialProofFailed as refused:
            results.append({"alias": alias, "refreshed": False, "reason": str(refused)})
            continue

        def prove(candidate: bytes, alias: str = alias, user_id: str = row.user_id) -> None:
            if operator.probe(alias, candidate)[0] != user_id:
                raise CredentialProofFailed("the refreshed token names another account")

        try:
            version = rotate_credential(
                ctx.writer, ctx.secrets, access_purpose, grant.access_token, prove=prove,
                now=ctx.clock(),
            )  # fmt: skip
        except CredentialCheckFailed:
            results.append({"alias": alias, "refreshed": False,
                            "reason": "the refreshed token did not prove itself"})  # fmt: skip
            continue
        if grant.refresh_token is not None:
            rotate_credential(
                ctx.writer, ctx.secrets, refresh_purpose, grant.refresh_token,
                prove=lambda _v: None, now=ctx.clock(),
            )  # fmt: skip
        access_life, refresh_life = _lifetimes(grant)
        with ctx.writer.transaction() as tx:
            store.set_expiry(
                tx.conn, row.ref, now=tx.now, access_lifetime=access_life,
                refresh_lifetime=refresh_life,
            )  # fmt: skip
            tx.append("admin.pinterest_account", subject_ref=row.ref,
                      payload={"action": "token_refreshed"})  # fmt: skip
        results.append({"alias": alias, "refreshed": True, "version": version,
                        "expires_at": timeutil.iso(ctx.clock() + access_life),
                        "refresh_token_rotated": grant.refresh_token is not None})  # fmt: skip
    return {
        "results": results,
        "reloaded": _reloaded(ctx) if any(r["refreshed"] for r in results) else False,
    }


def _doctor(ctx: OperatorContext, args: dict[str, Any]) -> dict[str, Any]:
    operator = _operator(ctx)
    live, tokens = {}, {}
    for row in store.live_accounts(ctx.conn):
        purpose = pinterest_token_purposes(row.alias)[0]
        try:
            token = active_credential(ctx.conn, ctx.secrets, purpose)
        except KeySlotError:
            token = None
        live[row.alias] = (row, token is not None)
        if token is not None:
            tokens[row.alias] = token
    try:
        has_secret = active_credential(ctx.conn, ctx.secrets, PINTEREST_APP_SECRET) is not None
    except KeySlotError:
        has_secret = False

    def identity(alias: str) -> str | None:
        try:
            return operator.probe(alias, tokens[alias])[0]
        except CredentialProofFailed:
            return None

    return {"findings": findings(operator.aliases(), live, identity, now=ctx.clock(),
                                 app_secret=has_secret)}  # fmt: skip


PINTEREST_HANDLERS: dict[tuple[str, ...], OperatorHandler] = {
    ("transport", "pinterest", "auth-url"): _auth_url,
    ("transport", "pinterest", "account", "add"): _add,
    ("transport", "pinterest", "account", "list"): _list,
    ("transport", "pinterest", "account", "remove"): _remove,
    ("transport", "pinterest", "token", "refresh"): _refresh,
    ("transport", "pinterest", "doctor"): _doctor,
}
