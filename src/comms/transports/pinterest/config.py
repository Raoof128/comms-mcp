"""The Pinterest section of ``comms.json`` (proposed A50, section 4.3): non-secret, no identity.

``{"app_id": "1234567", "redirect_uri": "https://…", "default": "sarabi", "daily_pin_budget": 50,
   "accounts": {"sarabi": {"label": "Sarabi's Fine Rugs", "writes": true, "sandbox": false}}}``

``writes`` is a per-account ceiling: a refused write never reaches Pinterest. ``sandbox`` pins the
account to Pinterest's sandbox host. An alias follows ``comms.core.keys.purposes.instagram_alias``
(the one alias grammar; the secret-like words refused).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from comms.core.keys.purposes import instagram_alias
from comms.transports.instagram.urls import public_url

__all__ = ["DEFAULT_PIN_BUDGET", "AccountPolicy", "PinterestSettings", "parse_pinterest"]

DEFAULT_PIN_BUDGET = 50  # D-P7: comms' own ceiling, under Trial access's 300 org_write a day
_TOP = {"app_id", "redirect_uri", "default", "daily_pin_budget", "accounts"}
_ACCOUNT = {"label", "writes", "sandbox"}
_APP_ID = re.compile(r"\A[0-9]{1,32}\Z")
_LABEL = re.compile(r"\A[^\x00-\x1f\x7f]{1,64}\Z")
_MAX_ACCOUNTS = 16


@dataclass(frozen=True)
class AccountPolicy:
    label: str
    writes: bool = False
    sandbox: bool = False


@dataclass(frozen=True)
class PinterestSettings:
    app_id: str
    redirect_uri: str
    default: str | None = None
    daily_pin_budget: int = DEFAULT_PIN_BUDGET
    accounts: Mapping[str, AccountPolicy] = field(default_factory=lambda: MappingProxyType({}))


def parse_pinterest(value: Any, refuse: Any) -> PinterestSettings:
    """``refuse(message)`` raises the caller's settings error (one message style)."""
    if not isinstance(value, dict) or set(value) - _TOP:
        refuse("comms.json: unknown key in pinterest")
    app_id = value.get("app_id")
    if not isinstance(app_id, str) or not _APP_ID.match(app_id):
        refuse("comms.json: pinterest.app_id is 1 to 32 digits")
    redirect = value.get("redirect_uri")
    try:
        public_url(redirect)
    except ValueError:
        refuse("comms.json: pinterest.redirect_uri is a public https URL")
    budget = value.get("daily_pin_budget", DEFAULT_PIN_BUDGET)
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 300:
        refuse("comms.json: pinterest.daily_pin_budget is 1 to 300")
    raw = value.get("accounts", {})
    if not isinstance(raw, dict) or len(raw) > _MAX_ACCOUNTS:
        refuse("comms.json: pinterest.accounts is an object of at most 16 accounts")
    accounts: dict[str, AccountPolicy] = {}
    for alias, entry in raw.items():
        if instagram_alias(alias) is None:
            refuse("comms.json: a pinterest alias is a-z, 0-9, _ or -, at most 32")
        if not isinstance(entry, dict) or set(entry) - _ACCOUNT or "label" not in entry:
            refuse("comms.json: a pinterest account is {label, writes, sandbox}")
        label = entry["label"]
        writes, sandbox = entry.get("writes", False), entry.get("sandbox", False)
        if not isinstance(label, str) or not _LABEL.fullmatch(label):
            refuse("comms.json: a pinterest label is 1 to 64 printable characters")
        if not isinstance(writes, bool) or not isinstance(sandbox, bool):
            refuse("comms.json: pinterest writes and sandbox are true or false")
        accounts[alias] = AccountPolicy(label, writes, sandbox)
    default = value.get("default")
    if default is not None and default not in accounts:
        refuse("comms.json: pinterest.default names a configured account")
    return PinterestSettings(
        str(app_id), str(redirect), default, int(budget), MappingProxyType(accounts)
    )
