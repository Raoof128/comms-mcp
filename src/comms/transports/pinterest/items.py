"""Pinterest profile, board, Pin, media and analytics items (proposed A50, sections 5.1, 7).

Every provider id becomes an opaque ref here (``pnb_``, ``pnp_``); every text Pinterest returns
(titles, descriptions, board names, usernames, links) is untrusted and bounded, control
characters stripped. Image and thumbnail URLs are never passed on: a CDN address is not what a
caller needs, and Pinterest's ``link`` is the one URL a Pin carries, under ``untrusted``.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from comms.core.errors import CommsError
from comms.core.providers.pinterest_analytics import DATA_STATUSES
from comms.transports.pinterest import store
from comms.transports.pinterest.accounts import AccountRuntime
from comms.transports.pinterest.classify import api_read

__all__ = [
    "ACCOUNT_TYPES",
    "BOARD_PRIVACIES",
    "CREATIVE_TYPES",
    "MEDIA_TYPES",
    "analytics",
    "board_item",
    "clean",
    "count",
    "media_status",
    "number",
    "page_of",
    "pin_item",
    "profile",
    "provider_id",
]

_ID = re.compile(r"\A[0-9]{1,24}\Z")
_BOOKMARK = re.compile(r"\A[A-Za-z0-9_=+/\-]{1,2048}\Z")
ACCOUNT_TYPES = ("PINNER", "BUSINESS")
BOARD_PRIVACIES = ("PUBLIC", "PROTECTED", "SECRET")
MEDIA_TYPES = ("image", "video", "multiple_images", "multiple_videos", "multiple_mixed")
CREATIVE_TYPES = (
    "REGULAR",
    "VIDEO",
    "SHOPPING",
    "CAROUSEL",
    "MAX_VIDEO",
    "SHOP_THE_PIN",
    "COLLECTION",
    "IDEA",
    "SHOWCASE",
    "QUIZ",
    "COLLAGE",
    "MAX_WIDTH_REGULAR_COLLECTION",
    "MAX_WIDTH_VIDEO_COLLECTION",
    "APP",
)
_PROFILE_FIELDS = (
    "account_type",
    "board_count",
    "pin_count",
    "follower_count",
    "following_count",
    "monthly_views",
)


def clean(value: Any, limit: int) -> str | None:
    """Untrusted text: control characters (Unicode category C*, except newline) removed, then
    capped at ``limit`` characters. ``None`` for anything that is not a string."""
    if not isinstance(value, str):
        return None
    kept = "".join(ch for ch in value if ch == "\n" or not unicodedata.category(ch).startswith("C"))
    return kept[:limit]


def count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and abs(value) < 1e15 else None  # no NaN, no infinity


def provider_id(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not _ID.match(value):
        raise CommsError("PROVIDER_UNAVAILABLE")  # Pinterest answered something that is not an id
    return value


def page_of(body: Mapping[str, Any]) -> tuple[list[Any], str | None]:
    """A page's items and its ``bookmark`` (``None`` on the last page)."""
    items = body.get("items")
    bookmark = body.get("bookmark")
    more = isinstance(bookmark, str) and _BOOKMARK.match(bookmark) is not None
    return (items if isinstance(items, list) else []), (bookmark if more else None)


def _stamp(value: Any) -> str | None:
    """Pinterest's ``created_at`` (``2026-10-01T10:00:00``, UTC without an offset, or with one)
    as the canonical second-precision UTC form."""
    if not isinstance(value, str) or not 19 <= len(value) <= 32:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def profile(runtime: AccountRuntime) -> dict[str, Any]:
    body = api_read(runtime.api, runtime.api.me)
    account_type = body.get("account_type")
    out: dict[str, Any] = {
        "account_type": account_type if account_type in ACCOUNT_TYPES else None,
        **{name: count(body.get(name)) for name in _PROFILE_FIELDS if name != "account_type"},
        "untrusted": {
            "username": clean(body.get("username"), 64),
            "business_name": clean(body.get("business_name"), 128),
            "website_url": clean(body.get("website_url"), 512),
        },
    }
    return out


def board_item(
    conn: Any, runtime: AccountRuntime, raw: Mapping[str, Any], *, now: datetime
) -> dict[str, Any]:
    privacy = raw.get("privacy")
    owner = raw.get("owner")
    return {
        "board": store.object_ref(
            conn, runtime.account_id, "board", provider_id(raw.get("id")), now=now
        ),
        "privacy": privacy if privacy in BOARD_PRIVACIES else None,
        "pin_count": count(raw.get("pin_count")),
        "follower_count": count(raw.get("follower_count")),
        "collaborator_count": count(raw.get("collaborator_count")),
        "created_at": _stamp(raw.get("created_at")),
        "untrusted": {
            "name": clean(raw.get("name"), 180),
            "owner_username": clean(owner.get("username") if isinstance(owner, dict) else None, 64),
        },
        "untrusted_text": clean(raw.get("description"), 500),
    }


def _metric_map(value: Any, limit: int = 64) -> dict[str, float | int] | None:
    if not isinstance(value, dict):
        return None
    out = {}
    for name, raw in value.items():
        if isinstance(name, str) and len(name) <= 64 and number(raw) is not None:
            out[name] = raw
        if len(out) >= limit:
            break
    return out


def pin_item(
    conn: Any, runtime: AccountRuntime, raw: Mapping[str, Any], *, now: datetime
) -> dict[str, Any]:
    media = raw.get("media")
    media_type = media.get("media_type") if isinstance(media, dict) else None
    creative = raw.get("creative_type")
    owner = raw.get("board_owner")
    board_id = raw.get("board_id")
    metrics = raw.get("pin_metrics")
    lifetime = metrics.get("lifetime_metrics") if isinstance(metrics, dict) else None
    ninety = metrics.get("90d") if isinstance(metrics, dict) else None
    return {
        "pin": store.object_ref(
            conn, runtime.account_id, "pin", provider_id(raw.get("id")), now=now
        ),
        "board": store.object_ref(conn, runtime.account_id, "board", provider_id(board_id), now=now)
        if isinstance(board_id, (str, int)) and _ID.match(str(board_id))
        else None,
        "created_at": _stamp(raw.get("created_at")),
        "creative_type": creative if creative in CREATIVE_TYPES else None,
        "media_type": media_type if media_type in MEDIA_TYPES else None,
        "is_owner": raw.get("is_owner") if isinstance(raw.get("is_owner"), bool) else None,
        "has_been_promoted": raw.get("has_been_promoted")
        if isinstance(raw.get("has_been_promoted"), bool)
        else None,
        "metrics_90d": _metric_map(ninety),
        "metrics_lifetime": _metric_map(lifetime),
        "untrusted": {
            "title": clean(raw.get("title"), 100),
            "link": clean(raw.get("link"), 2048),
            "alt_text": clean(raw.get("alt_text"), 500),
            "board_owner_username": clean(
                owner.get("username") if isinstance(owner, dict) else None, 64
            ),
        },
        "untrusted_text": clean(raw.get("description"), 800),
    }


def media_status(raw: Mapping[str, Any]) -> str | None:
    status = raw.get("status")
    return status if status in store.MEDIA_STATUSES else None


def analytics(body: Mapping[str, Any]) -> dict[str, Any]:
    """Pinterest's analytics answer under its ``ALL`` key: numbers only."""
    block = body.get("ALL")
    if not isinstance(block, dict):
        block = next((v for v in body.values() if isinstance(v, dict)), {})
    daily = []
    for row in block.get("daily_metrics") or ():
        if not isinstance(row, dict):
            continue
        status = row.get("data_status")
        day = row.get("date")
        daily.append(
            {
                "date": day if isinstance(day, str) and len(day) == 10 else None,
                "data_status": status if status in DATA_STATUSES else None,
                "metrics": _metric_map(row.get("metrics")) or {},
            }
        )
        if len(daily) >= 100:
            break
    return {
        "summary": _metric_map(block.get("summary_metrics")) or {},
        "daily": daily,
        "lifetime": _metric_map(block.get("lifetime_metrics")) or {},
    }
