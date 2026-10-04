"""Instagram profile, media and tag reads (proposed A49, sections 5.1 and 7) ✅.

Every provider id becomes an opaque ref here (``igm_``); every text Meta returns (captions, alt
text, usernames, permalinks) is untrusted and bounded, control characters stripped. Fields
documented as Facebook-Login-only are never requested; ``caption`` only when the owner turns it
on in comms.json after gate GI-4 (it is documented Facebook-Login-only on the IG Media node).
``media_url`` is never requested: ``permalink`` is enough, and a CDN address is not.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from comms.core.errors import CommsError
from comms.transports.instagram import store
from comms.transports.instagram.accounts import AccountRuntime
from comms.transports.instagram.classify import graph_read

__all__ = [
    "MEDIA_FIELDS",
    "clean",
    "count",
    "media_item",
    "page_of",
    "profile",
    "provider_id",
]

MEDIA_FIELDS = (
    "id,media_type,permalink,timestamp,like_count,comments_count,is_comment_enabled,"
    "thumbnail_url,alt_text,username"
)
_PROFILE_FIELDS = "user_id,username,name,account_type,followers_count,follows_count,media_count"
_ID = re.compile(r"\A[0-9]{1,20}\Z")
_MEDIA_TYPES = frozenset({"IMAGE", "VIDEO", "CAROUSEL_ALBUM"})
_CURSOR = re.compile(r"\A[A-Za-z0-9_=-]{1,512}\Z")


def clean(value: Any, limit: int) -> str | None:
    """Untrusted text: control characters (Unicode category C*, except newline) removed, then
    capped at ``limit`` characters. ``None`` for anything that is not a string."""
    if not isinstance(value, str):
        return None
    kept = "".join(ch for ch in value if ch == "\n" or not unicodedata.category(ch).startswith("C"))
    return kept[:limit]


def count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def provider_id(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not _ID.match(value):
        raise CommsError("PROVIDER_UNAVAILABLE")  # Meta answered something that is not an id
    return value


def page_of(body: Mapping[str, Any]) -> tuple[list[Any], str | None]:
    """A Graph page's items and its ``after`` cursor (only when Meta says there is more)."""
    data = body.get("data")
    raw_paging = body.get("paging")
    paging: Mapping[str, Any] = raw_paging if isinstance(raw_paging, dict) else {}
    raw_cursors = paging.get("cursors")
    cursors: Mapping[str, Any] = raw_cursors if isinstance(raw_cursors, dict) else {}
    after = cursors.get("after")
    more = isinstance(after, str) and _CURSOR.match(after) and "next" in paging
    return (data if isinstance(data, list) else []), (after if more else None)


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") if parsed.utcoffset() is not None else None


def media_item(
    conn: Any, runtime: AccountRuntime, raw: Mapping[str, Any], *, now: datetime
) -> dict[str, Any]:
    media_type = raw.get("media_type")
    return {
        "media": store.object_ref(
            conn, runtime.account_id, "media", provider_id(raw.get("id")), now=now
        ),
        "media_type": media_type if media_type in _MEDIA_TYPES else None,
        "timestamp": _timestamp(raw.get("timestamp")),
        "like_count": count(raw.get("like_count")),
        "comments_count": count(raw.get("comments_count")),
        "comments_enabled": raw.get("is_comment_enabled")
        if isinstance(raw.get("is_comment_enabled"), bool)
        else None,
        "untrusted": {
            "username": clean(raw.get("username"), 64),
            "permalink": clean(raw.get("permalink"), 512),
            "alt_text": clean(raw.get("alt_text"), 1000),
        },
        "untrusted_text": clean(raw.get("caption"), 2200),
    }


def media_created(raw: Mapping[str, Any]) -> datetime:
    stamp = _timestamp(raw.get("timestamp"))
    if stamp is None:
        raise CommsError("PROVIDER_UNAVAILABLE")
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z")


def profile(runtime: AccountRuntime) -> dict[str, Any]:
    body = graph_read(lambda: runtime.api.get("me", params={"fields": _PROFILE_FIELDS}))
    account_type = body.get("account_type")
    return {
        "account_type": account_type if account_type in ("BUSINESS", "MEDIA_CREATOR") else None,
        "followers_count": count(body.get("followers_count")),
        "follows_count": count(body.get("follows_count")),
        "media_count": count(body.get("media_count")),
        "untrusted": {
            "username": clean(body.get("username"), 64),
            "name": clean(body.get("name"), 128),
        },
    }
