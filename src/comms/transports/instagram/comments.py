"""Instagram comment reads (proposed A49, sections 5.1 and 7) ✅.

A comment becomes an ``igc_``; its text is untrusted (A44: only in ``untrusted_text``) and its
author's username only under ``untrusted``. Reading the author's username needs
``instagram_business_manage_comments``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from comms.transports.instagram import store
from comms.transports.instagram.accounts import AccountRuntime
from comms.transports.instagram.media import clean, count, provider_id

__all__ = ["COMMENT_FIELDS", "comment_item"]

COMMENT_FIELDS = "id,text,timestamp,username,like_count,hidden"


def comment_item(
    conn: Any, runtime: AccountRuntime, raw: Mapping[str, Any], *, now: datetime
) -> dict[str, Any]:
    ident = provider_id(raw.get("id"))
    stamp = raw.get("timestamp")
    return {
        "comment": store.object_ref(conn, runtime.account_id, "comment", ident, now=now),
        "timestamp": clean(stamp, 32),
        "like_count": count(raw.get("like_count")),
        "hidden": raw.get("hidden") if isinstance(raw.get("hidden"), bool) else None,
        "untrusted": {"username": clean(raw.get("username"), 64)},
        "untrusted_text": clean(raw.get("text"), 2200),
    }
