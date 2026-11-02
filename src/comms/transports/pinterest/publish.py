"""Publishing rules and bodies (proposed A50, sections 5.2 and 6; D-P7, D-P8).

The argument checks are ``AdminOperations.validate``'s (shapes only, nothing touched): a Pin's
board, kind and texts within Pinterest's limits; a board's name and privacy (never ``SECRET``);
a video upload's bytes and mime. ``pin_body`` is the one place a ``POST /v5/pins`` body is
built. ``budget_used`` reads the publication ledger for the rolling 24 hours. Every URL the model
supplies is checked with the one ``public_url`` rule and passed to Pinterest, never fetched.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from comms.core import refs
from comms.transports.instagram.urls import public_url
from comms.transports.pinterest import store
from comms.transports.pinterest.accounts import AccountRuntime
from comms.transports.pinterest.upload import VIDEO_MAX_BYTES, VIDEO_MIMES

__all__ = [
    "AI_DISCLOSURES",
    "ALT_TEXT_MAX",
    "BOARD_NAME_MAX",
    "BOARD_PRIVACIES",
    "CAROUSEL_MAX",
    "CAROUSEL_MIN",
    "DESCRIPTION_MAX",
    "KINDS",
    "LINK_MAX",
    "TITLE_MAX",
    "budget_used",
    "check_board_create",
    "check_pin_create",
    "check_pin_delete",
    "check_pin_update",
    "check_video_upload",
    "pin_body",
    "pin_update_body",
]

TITLE_MAX, DESCRIPTION_MAX, LINK_MAX, ALT_TEXT_MAX = 100, 800, 2048, 500  # ✅ PinCreate
BOARD_NAME_MAX, BOARD_DESCRIPTION_MAX = 180, 500
CAROUSEL_MIN, CAROUSEL_MAX = 2, 5  # ✅ multiple_image_urls items
KINDS = ("image", "carousel", "video")
BOARD_PRIVACIES = ("PUBLIC", "PROTECTED")  # never SECRET (D-P10)
AI_DISCLOSURES = ("AI_MODIFIED", "SYNTHETIC_PERFORMER")
_TEXTS = {"title": TITLE_MAX, "description": DESCRIPTION_MAX, "alt_text": ALT_TEXT_MAX}
_PIN_COMMON = {"board", "kind", "title", "description", "link", "alt_text", "ai_disclosures"}
_PIN_ALLOWED = {
    "image": _PIN_COMMON | {"url"},
    "carousel": _PIN_COMMON | {"images"},
    "video": _PIN_COMMON | {"media", "cover_url"},
}
_IMAGE_ITEM = {"url", "title", "description", "link"}
_UPDATE_FIELDS = {"title", "description", "link", "alt_text", "board"}
_NAME = re.compile(r"\A[^\x00-\x1f\x7f]{1,180}\Z")


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value or len(value) > limit:
        raise ValueError("text refused")
    return value


def _texts(a: Mapping[str, Any]) -> None:
    for key, limit in _TEXTS.items():
        if key in a:
            _text(a[key], limit)
    if "link" in a:
        public_url(a["link"])
        if len(a["link"]) > LINK_MAX:
            raise ValueError("link refused")


def _disclosures(value: object) -> None:
    if not isinstance(value, list) or len(set(value)) != len(value) or len(value) > 2:
        raise ValueError("ai_disclosures refused")
    if any(item not in AI_DISCLOSURES for item in value):
        raise ValueError("ai_disclosures refused")


def check_pin_create(a: Mapping[str, Any]) -> None:
    kind = a.get("kind")
    if kind not in _PIN_ALLOWED or set(a) - _PIN_ALLOWED[kind] or "board" not in a:
        raise ValueError("pin arguments refused")
    refs.check(a["board"], "pinterest_board")
    _texts(a)
    if "ai_disclosures" in a:
        _disclosures(a["ai_disclosures"])
    if kind == "image":
        public_url(a.get("url"))
    elif kind == "carousel":
        images = a.get("images")
        if not isinstance(images, list) or not CAROUSEL_MIN <= len(images) <= CAROUSEL_MAX:
            raise ValueError("a carousel has 2 to 5 images")
        for item in images:
            if not isinstance(item, dict) or set(item) - _IMAGE_ITEM or "url" not in item:
                raise ValueError("carousel image refused")
            public_url(item["url"])
            _texts({k: v for k, v in item.items() if k != "url"})
    else:
        refs.check(a.get("media"), "pinterest_media")
        public_url(a.get("cover_url"))


def check_pin_update(a: Mapping[str, Any]) -> None:
    if "pin" not in a or set(a) - ({"pin"} | _UPDATE_FIELDS) or len(a) < 2:
        raise ValueError("pin update refused")
    refs.check(a["pin"], "pinterest_pin")
    _texts(a)
    if "board" in a:
        refs.check(a["board"], "pinterest_board")


def check_pin_delete(a: Mapping[str, Any]) -> None:
    if set(a) != {"pin"}:
        raise ValueError("pin delete takes one pin")
    refs.check(a["pin"], "pinterest_pin")


def check_board_create(a: Mapping[str, Any]) -> None:
    if set(a) - {"name", "description", "privacy"} or "name" not in a:
        raise ValueError("board arguments refused")
    if not isinstance(a["name"], str) or not _NAME.match(a["name"]) or not a["name"].strip():
        raise ValueError("board name refused")
    if "description" in a:
        _text(a["description"], BOARD_DESCRIPTION_MAX)
    if "privacy" in a and a["privacy"] not in BOARD_PRIVACIES:
        raise ValueError("board privacy refused")


def check_video_upload(a: Mapping[str, Any]) -> None:
    if set(a) != {"data", "mime"}:
        raise ValueError("video upload refused")
    data, mime = a["data"], a["mime"]
    if not isinstance(data, bytes) or not 0 < len(data) <= VIDEO_MAX_BYTES:
        raise ValueError("video refused")
    if mime not in VIDEO_MIMES:
        raise ValueError("video mime refused")


# -- bodies ------------------------------------------------------------------------------------


def pin_body(a: Mapping[str, Any], board_id: str, media_id: str | None) -> dict[str, Any]:
    kind = a["kind"]
    if kind == "image":
        source: dict[str, Any] = {"source_type": "image_url", "url": a["url"]}
    elif kind == "carousel":
        source = {
            "source_type": "multiple_image_urls",
            "items": [dict(item) for item in a["images"]],
            "index": 0,
        }
    else:
        source = {
            "source_type": "video_id",
            "media_id": media_id,
            "cover_image_url": a["cover_url"],
        }
    body: dict[str, Any] = {"board_id": board_id, "media_source": source}
    for key in ("title", "description", "link", "alt_text"):
        if key in a:
            body[key] = a[key]
    if "ai_disclosures" in a:
        body["ai_disclosures"] = {"values": list(a["ai_disclosures"])}
    return body


def pin_update_body(a: Mapping[str, Any], board_id: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {k: a[k] for k in ("title", "description", "link", "alt_text") if k in a}
    if board_id is not None:
        body["board_id"] = board_id
    return body


def budget_used(conn: Any, runtime: AccountRuntime, now: datetime) -> int:
    return store.publications_since(conn, runtime.account_id, now - timedelta(hours=24))
