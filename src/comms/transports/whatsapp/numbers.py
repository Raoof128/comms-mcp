"""The WhatsApp delivery identities, one copy each: the E.164 number (5b-4 R3) for a contact,
and ``group:<group_id>`` for a group (catalog amendment G1).

Meta's group ids are opaque (the Groups reference's sample is ``Y2FwaV9ncm91cDox…``; older ids
are digits), so the rule accepts a path-safe token: an ASCII letter or digit, then letters,
digits, ``_``, ``-`` or ``=``, at most 128 in all. A Telegram marked id (``-100…``), a path
separator or a query character is refused.
"""

from __future__ import annotations

import re

__all__ = ["WA_GROUP_ID", "e164", "wa_group_id"]

WA_GROUP_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_=-]{4,127}\Z")


def e164(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isascii() and ch.isdigit())
    if not raw.strip().startswith("+") or not 8 <= len(digits) <= 15:
        raise ValueError("unrecognised number")
    return "+" + digits


def wa_group_id(raw: str) -> str:
    kind, sep, group_id = raw.partition(":")
    if kind != "group" or not sep or not WA_GROUP_ID.match(group_id):
        raise ValueError("unrecognised group")
    return raw
