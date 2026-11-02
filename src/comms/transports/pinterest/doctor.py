"""``comms transport pinterest doctor``'s findings (proposed A50, section 4.4).

One finding per problem, each a fixed code an owner can act on; an account with none is ``OK``.
The identity probe is injected (a live ``GET /v5/user_account``); a probe that cannot run reports
``PN_IDENTITY_UNCHECKED`` rather than success (fail closed). ``comms doctor`` is offline and reads
no token material, so it passes no probe and the identity codes never appear there.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from comms.core import timeutil

__all__ = ["CODES", "EXPIRY_WARNING", "findings"]

EXPIRY_WARNING = timedelta(days=10)
CODES = (
    "PN_ACCOUNT_UNREGISTERED",  # configured in comms.json, never added
    "PN_ACCOUNT_UNCONFIGURED",  # added, but gone from comms.json
    "PN_TOKEN_MISSING",  # added, no active access token
    "PN_TOKEN_EXPIRED",  # the access token (30 days)
    "PN_TOKEN_EXPIRING",  # under ten days
    "PN_REFRESH_EXPIRED",  # the refresh token (60 days): the owner must add the account again
    "PN_REFRESH_EXPIRING",
    "PN_IDENTITY_MISMATCH",  # the token names another account
    "PN_IDENTITY_UNCHECKED",  # Pinterest did not answer /user_account
    "PN_APP_SECRET_MISSING",  # no pinterest-app-secret: no exchange and no refresh possible
)


def findings(
    configured: Sequence[str],
    live: Mapping[str, tuple[Any, bool]],
    identity: Callable[[str], str | None] | None,
    *,
    now: datetime,
    app_secret: bool = True,
) -> list[dict[str, Any]]:
    out = []
    for alias in sorted(set(configured) | set(live)):
        codes = []
        if alias not in live:
            codes.append("PN_ACCOUNT_UNREGISTERED")
        else:
            row, has_token = live[alias]
            if alias not in configured:
                codes.append("PN_ACCOUNT_UNCONFIGURED")
            if not has_token:
                codes.append("PN_TOKEN_MISSING")
            access = timeutil.instant(row.access_expires_at)
            refresh = timeutil.instant(row.refresh_expires_at)
            if access <= now:
                codes.append("PN_TOKEN_EXPIRED")
            elif access - now < EXPIRY_WARNING:
                codes.append("PN_TOKEN_EXPIRING")
            if refresh <= now:
                codes.append("PN_REFRESH_EXPIRED")
            elif refresh - now < EXPIRY_WARNING:
                codes.append("PN_REFRESH_EXPIRING")
            if not app_secret:
                codes.append("PN_APP_SECRET_MISSING")
            if identity is not None and has_token and access > now:
                user_id = identity(alias)
                if user_id is None:
                    codes.append("PN_IDENTITY_UNCHECKED")
                elif user_id != row.user_id:
                    codes.append("PN_IDENTITY_MISMATCH")
        out.append({"alias": alias, "status": "OK" if not codes else "FINDINGS", "codes": codes})
    return out
