"""The configured Instagram accounts at runtime, and the identity check (proposed A49, 4.5).

``InstagramAccounts`` holds one ``AccountRuntime`` per alias that is both configured in
``comms.json`` and registered with an active token. The first use of an account in this daemon's
lifetime calls ``GET /me?fields=user_id,username`` and compares ``user_id`` (the ``<IG_ID>``;
``id`` is app-scoped) with the registered one: a mismatch blocks the alias until the operator
re-adds it, and nothing is sent for it. The username is live and untrusted: it is echoed under
``untrusted`` and never stored. No network at construction.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from comms.core.errors import CommsError
from comms.core.providers.protocols import ProviderTarget
from comms.transports.instagram import store
from comms.transports.instagram.config import AccountPolicy, InstagramSettings
from comms.transports.instagram.http import GraphIgApi, GraphTransportError

__all__ = ["ACTOR", "AccountRuntime", "InstagramAccounts", "read_identity"]

ACTOR = "instagram"
_USER_ID = re.compile(r"\A[0-9]{1,20}\Z")
_USERNAME = re.compile(r"\A[A-Za-z0-9._]{1,30}\Z")


@dataclass(frozen=True)
class AccountRuntime:
    alias: str
    ref: str  # iga_
    account_id: int
    policy: AccountPolicy
    api: GraphIgApi = field(repr=False)
    user_id: str = field(repr=False)

    def target(self) -> ProviderTarget:
        return ProviderTarget("instagram", ACTOR, self.ref, self.user_id)


def read_identity(api: GraphIgApi) -> tuple[str, str]:
    """``(user_id, username)`` from ``/me``; ``CommsError`` when Meta does not answer one."""
    try:
        response = api.me(("user_id", "username"))
    except GraphTransportError:
        raise CommsError("PROVIDER_UNAVAILABLE") from None
    body = response.envelope or {}
    user_id, username = body.get("user_id"), body.get("username")
    if isinstance(user_id, int) and not isinstance(user_id, bool):
        user_id = str(user_id)
    if response.http_status == 200 and isinstance(user_id, str) and _USER_ID.match(user_id):
        name = username if isinstance(username, str) and _USERNAME.match(username) else ""
        return user_id, name
    error = body.get("error")
    if isinstance(error, dict) and error.get("code") == 190:
        raise CommsError("NOT_AUTHORIZED")
    raise CommsError("PROVIDER_UNAVAILABLE")


class InstagramAccounts:
    def __init__(
        self,
        conn: Any,
        settings: InstagramSettings,
        runtimes: Mapping[str, AccountRuntime],
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._conn, self.settings, self._clock = conn, settings, clock
        self._by_alias = dict(runtimes)
        self._by_ref = {r.ref: r for r in runtimes.values()}
        self._checked: dict[str, str] = {}  # alias -> live username
        self._blocked: set[str] = set()
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"InstagramAccounts({sorted(self._by_alias)})"

    @property
    def configured(self) -> bool:
        return bool(self._by_alias)

    def aliases(self) -> list[str]:
        return sorted(self.settings.accounts)

    def by_ref(self, ref: str) -> AccountRuntime | None:
        return self._by_ref.get(ref)

    def blocked(self, alias: str) -> bool:
        return alias in self._blocked

    def resolve(self, alias: object, *, for_write: bool) -> AccountRuntime:
        """The account a call names. A read may fall back to ``instagram.default``; a write
        never does (D-I5). Unknown or unregistered: ``NOT_CONFIGURED``."""
        if alias is None:
            if for_write:
                raise CommsError("INVALID_ARGUMENT")
            alias = self.settings.default
            if alias is None and len(self._by_alias) == 1:
                alias = next(iter(self._by_alias))
        if not isinstance(alias, str) or alias not in self.settings.accounts:
            raise CommsError("NOT_FOUND" if isinstance(alias, str) else "INVALID_ARGUMENT")
        runtime = self._by_alias.get(alias)
        if runtime is None:
            raise CommsError("NOT_CONFIGURED")
        return runtime

    def username(self, runtime: AccountRuntime) -> str:
        """The live username, checking the identity once per daemon lifetime (4.5)."""
        with self._lock:
            if runtime.alias in self._blocked:
                raise CommsError("IDENTITY_MISMATCH")
            known = self._checked.get(runtime.alias)
        if known is not None:
            return known
        user_id, username = read_identity(runtime.api)
        with self._lock:
            if user_id != runtime.user_id:
                self._blocked.add(runtime.alias)
                raise CommsError("IDENTITY_MISMATCH")
            self._checked[runtime.alias] = username
        store.mark_identity_checked(self._conn, runtime.ref, now=self._clock())
        return username

    def close(self) -> None:
        for runtime in self._by_alias.values():
            runtime.api.close()
