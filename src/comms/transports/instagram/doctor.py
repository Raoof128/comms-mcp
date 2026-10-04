"""``comms transport instagram doctor``'s findings (proposed A49, section 4.3, 4.4, 14 item 14).

One finding per problem, each a fixed code an owner can act on; an account with none is ``OK``.
The identity probe is injected (a live ``GET /me``); a probe that cannot run reports
``IG_IDENTITY_UNCHECKED`` rather than success (fail closed).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from comms.core import timeutil

__all__ = ["CODES", "EXPIRY_WARNING", "findings"]

EXPIRY_WARNING = timedelta(days=10)
CODES = (
    "IG_ACCOUNT_UNREGISTERED",  # configured in comms.json, never added
    "IG_ACCOUNT_UNCONFIGURED",  # added, but gone from comms.json
    "IG_TOKEN_MISSING",  # added, no active token
    "IG_TOKEN_EXPIRED",
    "IG_TOKEN_EXPIRING",  # under ten days
    "IG_IDENTITY_MISMATCH",  # the token names another account
    "IG_IDENTITY_UNCHECKED",  # Meta did not answer /me
)


def findings(
    configured: Sequence[str],
    live: Mapping[str, tuple[Any, bytes | None]],
    identity: Callable[[str, bytes], str | None],
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    out = []
    for alias in sorted(set(configured) | set(live)):
        codes = []
        if alias not in live:
            codes.append("IG_ACCOUNT_UNREGISTERED")
        else:
            row, token = live[alias]
            if alias not in configured:
                codes.append("IG_ACCOUNT_UNCONFIGURED")
            if token is None:
                codes.append("IG_TOKEN_MISSING")
            expires = timeutil.instant(row.expires_at)
            if expires <= now:
                codes.append("IG_TOKEN_EXPIRED")
            elif expires - now < EXPIRY_WARNING:
                codes.append("IG_TOKEN_EXPIRING")
            if token is not None and expires > now:
                user_id = identity(alias, token)
                if user_id is None:
                    codes.append("IG_IDENTITY_UNCHECKED")
                elif user_id != row.user_id:
                    codes.append("IG_IDENTITY_MISMATCH")
        out.append({"alias": alias, "status": "OK" if not codes else "FINDINGS", "codes": codes})
    return out
