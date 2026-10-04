"""The Instagram section of ``comms.json`` (proposed A49, section 4.3): non-secret, no identity.

``{"api_version": "v25.0", "default": "main", "dm_disclosure": null,
   "accounts": {"main": {"label": "Main account", "writes": false, "dms": false}}}``

``writes`` and ``dms`` are per-account ceilings: a refused write never reaches Meta. An alias
follows ``comms.core.keys.purposes.instagram_alias`` (the secret-like words refused).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from comms.core.keys.purposes import instagram_alias
from comms.transports.instagram.http import DEFAULT_API_VERSION, api_version_ok

__all__ = ["AccountPolicy", "InstagramSettings", "parse_instagram"]

_TOP = {"api_version", "default", "dm_disclosure", "accounts"}
_ACCOUNT = {"label", "writes", "dms"}
_LABEL = re.compile(r"\A[^\x00-\x1f\x7f]{1,64}\Z")
_MAX_ACCOUNTS = 16


@dataclass(frozen=True)
class AccountPolicy:
    label: str
    writes: bool = False
    dms: bool = False


@dataclass(frozen=True)
class InstagramSettings:
    api_version: str = DEFAULT_API_VERSION
    default: str | None = None
    dm_disclosure: str | None = None
    accounts: Mapping[str, AccountPolicy] = field(default_factory=lambda: MappingProxyType({}))


def parse_instagram(value: Any, refuse: Any) -> InstagramSettings:
    """``refuse(message)`` raises the caller's settings error (one message style)."""
    if not isinstance(value, dict) or set(value) - _TOP:
        refuse("comms.json: unknown key in instagram")
    version = value.get("api_version", DEFAULT_API_VERSION)
    if not api_version_ok(version):
        refuse("comms.json: instagram.api_version is like v25.0")
    disclosure = value.get("dm_disclosure")
    if disclosure is not None and (
        not isinstance(disclosure, str) or not 1 <= len(disclosure) <= 200
    ):
        refuse("comms.json: instagram.dm_disclosure is 1 to 200 characters")
    raw = value.get("accounts", {})
    if not isinstance(raw, dict) or len(raw) > _MAX_ACCOUNTS:
        refuse("comms.json: instagram.accounts is an object of at most 16 accounts")
    accounts: dict[str, AccountPolicy] = {}
    for alias, entry in raw.items():
        if instagram_alias(alias) is None:
            refuse("comms.json: an instagram alias is a-z, 0-9, _ or -, at most 32")
        if not isinstance(entry, dict) or set(entry) - _ACCOUNT or "label" not in entry:
            refuse("comms.json: an instagram account is {label, writes, dms}")
        label, writes, dms = entry["label"], entry.get("writes", False), entry.get("dms", False)
        if not isinstance(label, str) or not _LABEL.fullmatch(label):
            refuse("comms.json: an instagram label is 1 to 64 printable characters")
        if not isinstance(writes, bool) or not isinstance(dms, bool):
            refuse("comms.json: instagram writes and dms are true or false")
        accounts[alias] = AccountPolicy(label, writes, dms)
    default = value.get("default")
    if default is not None and default not in accounts:
        refuse("comms.json: instagram.default names a configured account")
    return InstagramSettings(version, default, disclosure, MappingProxyType(accounts))
