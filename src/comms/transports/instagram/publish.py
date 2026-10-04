"""Publishing on a durable container ref (proposed A49, sections 5.2 and 6; D-I7, D-I13).

Three single-effect CREATEs, each one ``request_id``: ``container_create`` (one item),
``carousel_create`` (from 2 to 10 child ``igk_``) and ``publish`` (one status read, then
``media_publish``). Each ``igk_`` is a row of ``instagram_containers``, the account's 400-per-24-h
budget, written as soon as Meta answers with an id (before the executor records the step), so a
crash never loses a container the budget must count. ``publish`` resolves by the container's
status: ``FINISHED`` publishes; ``IN_PROGRESS``, ``ERROR`` and ``EXPIRED`` answer ``FAILED`` with
a fixed code; a container the ledger already knows as published answers ``SUCCEEDED`` with its
``igm_`` and makes no call. Nothing here polls, and a media URL is checked, never fetched.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from comms.core import refs
from comms.core.errors import CommsError
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderResult, SemanticOperation
from comms.transports.instagram import store
from comms.transports.instagram.accounts import AccountRuntime
from comms.transports.instagram.classify import graph_read, write_call
from comms.transports.instagram.media import count
from comms.transports.instagram.urls import public_url

__all__ = [
    "ALT_TEXT_MAX",
    "CAPTION_MAX",
    "CAROUSEL_MAX",
    "CAROUSEL_MIN",
    "CONTAINER_BUDGET",
    "ITEM_KINDS",
    "LEDGER_KIND",
    "Publisher",
    "caption_counts",
    "check_carousel",
    "check_container",
    "quota",
]

CONTAINER_BUDGET = 400  # containers per rolling 24 h per account ✅
CAPTION_MAX, HASHTAGS_MAX, MENTIONS_MAX, ALT_TEXT_MAX = 2200, 30, 20, 1000
CAROUSEL_MIN, CAROUSEL_MAX = 2, 10
THUMB_OFFSET_MAX = 15 * 60 * 1000  # a Reel is at most 15 minutes; the offset is in ms
ITEM_KINDS = ("image", "reel", "carousel_image", "carousel_video")
LEDGER_KIND = {"image": "image", "reel": "reel", "carousel_image": "child",
               "carousel_video": "child"}  # fmt: skip
_ALLOWED = {
    "image": {"kind", "url", "caption", "alt_text", "location_id", "is_ai_generated"},
    "reel": {
        "kind",
        "url",
        "caption",
        "location_id",
        "share_to_feed",
        "cover_url",
        "thumb_offset",
        "is_ai_generated",
    },
    "carousel_image": {"kind", "url", "alt_text"},  # no caption, location or AI label on a child
    "carousel_video": {"kind", "url"},
}
_CAROUSEL_ALLOWED = {"children", "caption", "location_id", "is_ai_generated"}
_HASHTAG = re.compile(r"(?<![\w#])#\w+")
_MENTION = re.compile(r"(?<![\w@])@[\w.]+")
_LOCATION = re.compile(r"\A[0-9]{1,20}\Z")
_CREATION = re.compile(r"\A[0-9]{1,20}\Z")  # the ledger's CHECK: a container id is numeric
_NOT_PUBLISHABLE = {
    "IN_PROGRESS": "CONTAINER_NOT_READY",
    "ERROR": "CONTAINER_FAILED",
    "EXPIRED": "CONTAINER_EXPIRED",
}


# -- argument checks (``AdminOperations.validate``: shapes only, nothing touched) ----------------


def caption_counts(caption: str) -> tuple[int, int]:
    """(hashtags, @ mentions) as Meta counts them."""
    return len(_HASHTAG.findall(caption)), len(_MENTION.findall(caption))


def _caption(value: object) -> None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError("caption refused")
    tags, mentions = caption_counts(value)
    if len(value) > CAPTION_MAX or tags > HASHTAGS_MAX or mentions > MENTIONS_MAX:
        raise ValueError("caption over Meta's limits")


def _common(a: Mapping[str, Any]) -> None:
    if "caption" in a:
        _caption(a["caption"])
    if "location_id" in a and not (
        isinstance(a["location_id"], str) and _LOCATION.match(a["location_id"])
    ):
        raise ValueError("location_id refused")
    if "is_ai_generated" in a and not isinstance(a["is_ai_generated"], bool):
        raise ValueError("is_ai_generated is true or false")


def check_container(a: Mapping[str, Any]) -> None:
    kind = a.get("kind")
    if kind not in _ALLOWED or set(a) - _ALLOWED[kind]:
        raise ValueError("container arguments refused")
    public_url(a.get("url"))
    _common(a)
    alt = a.get("alt_text")
    if alt is not None and (not isinstance(alt, str) or not alt.strip() or len(alt) > ALT_TEXT_MAX):
        raise ValueError("alt_text refused")
    if "share_to_feed" in a and not isinstance(a["share_to_feed"], bool):
        raise ValueError("share_to_feed is true or false")
    if "cover_url" in a:
        public_url(a["cover_url"])
    offset = a.get("thumb_offset")
    if offset is not None and (type(offset) is not int or not 0 <= offset <= THUMB_OFFSET_MAX):
        raise ValueError("thumb_offset refused")


def check_carousel(a: Mapping[str, Any]) -> None:
    children = a.get("children")
    if set(a) - _CAROUSEL_ALLOWED or not isinstance(children, list):
        raise ValueError("carousel arguments refused")
    if not CAROUSEL_MIN <= len(children) <= CAROUSEL_MAX or len(set(children)) != len(children):
        raise ValueError("a carousel has 2 to 10 distinct children")
    for child in children:
        refs.check(child, "instagram_container")
    _common(a)


def _check_publish(a: Mapping[str, Any]) -> None:
    if set(a) != {"container"}:
        raise ValueError("publish takes one container")
    refs.check(a["container"], "instagram_container")


# -- Graph bodies --------------------------------------------------------------------------------


def _container_body(a: Mapping[str, Any]) -> dict[str, Any]:
    kind = a["kind"]
    body: dict[str, Any] = {}
    if kind in ("image", "carousel_image"):
        body["image_url"] = a["url"]
    else:
        body["media_type"] = "REELS" if kind == "reel" else "VIDEO"
        body["video_url"] = a["url"]
    if kind.startswith("carousel_"):
        body["is_carousel_item"] = True
    for key in ("caption", "alt_text", "location_id", "share_to_feed", "cover_url",
                "thumb_offset", "is_ai_generated"):  # fmt: skip
        if key in a:
            body[key] = a[key]
    return body


def quota(runtime: AccountRuntime, since: int | None = None) -> dict[str, int | None]:
    """``GET /<IG_ID>/content_publishing_limit``: the live published-post quota (GI-3 🧪)."""
    params = {"fields": "quota_usage,config", **({"since": str(since)} if since else {})}
    body = graph_read(
        lambda: runtime.api.get(runtime.user_id, "content_publishing_limit", params=params)
    )
    data = body.get("data")
    row: Mapping[str, Any] = data[0] if isinstance(data, list) and data and isinstance(
        data[0], dict
    ) else {}  # fmt: skip
    raw_config = row.get("config")
    config: Mapping[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    return {
        "quota_usage": count(row.get("quota_usage")),
        "quota_total": count(config.get("quota_total")),
        "quota_duration": count(config.get("quota_duration")),
    }


# -- the adapter's three calls -------------------------------------------------------------------


class Publisher:
    """The publishing calls, registered on ``InstagramAdmin`` (one adapter per actor)."""

    def __init__(self, conn: Any, *, clock: Callable[[], datetime]) -> None:
        self._conn, self._clock = conn, clock

    def __repr__(self) -> str:
        return "Publisher(<redacted>)"

    def register(self, admin: Any) -> None:
        admin.register(C.MEDIA_CONTAINER_CREATE, self.container_create, check_container)
        admin.register(C.MEDIA_CAROUSEL_CREATE, self.carousel_create, check_carousel)
        admin.register(C.MEDIA_PUBLISH, self.publish, _check_publish)

    def budget_used(self, runtime: AccountRuntime) -> int:
        since = self._clock() - timedelta(hours=24)
        return store.containers_since(self._conn, runtime.account_id, since)

    def _ledger(self, result: ProviderResult, runtime: AccountRuntime, kind: str) -> ProviderResult:
        """A created container is a ledger row at once, whatever happens next."""
        if result.outcome != "SUCCEEDED":
            return result
        if not _CREATION.match(result.provider_ref or ""):
            return ProviderResult("OUTCOME_UNKNOWN", None)  # created, but not nameable
        store.record_container(
            self._conn, runtime.account_id, kind, str(result.provider_ref), now=self._clock()
        )
        return result

    def container_create(self, op: SemanticOperation, runtime: AccountRuntime) -> ProviderResult:
        a = op.args
        body = _container_body(a)
        result = write_call(lambda: runtime.api.post(runtime.user_id, "media", body=body))
        return self._ledger(result, runtime, LEDGER_KIND[a["kind"]])

    def children(self, runtime: AccountRuntime, children: list[str]) -> list[store.Container]:
        """The children, each this account's carousel item (``NOT_FOUND`` for another
        account's, ``INVALID_ARGUMENT`` for a container that is not a child)."""
        boxes = [store.container(self._conn, ref, runtime.account_id) for ref in children]
        if any(box.kind != "child" for box in boxes):
            raise CommsError("INVALID_ARGUMENT")
        return boxes

    def carousel_create(self, op: SemanticOperation, runtime: AccountRuntime) -> ProviderResult:
        a = op.args
        try:
            boxes = self.children(runtime, a["children"])
        except CommsError as refused:
            return ProviderResult("FAILED", refused.code)
        body: dict[str, Any] = {"media_type": "CAROUSEL",
                                "children": ",".join(box.creation_id for box in boxes)}  # fmt: skip
        for key in ("caption", "location_id", "is_ai_generated"):
            if key in a:
                body[key] = a[key]
        result = write_call(lambda: runtime.api.post(runtime.user_id, "media", body=body))
        return self._ledger(result, runtime, "carousel")

    def publish(self, op: SemanticOperation, runtime: AccountRuntime) -> ProviderResult:
        conn, account_id = self._conn, runtime.account_id
        try:
            box = store.container(conn, op.args["container"], account_id)
            if box.kind == "child":  # a carousel item is published only inside its carousel
                return ProviderResult("FAILED", "INVALID_ARGUMENT")
            if box.status == "PUBLISHED" and box.media_ref is not None:
                media = store.resolve_object(conn, box.media_ref, "media", account_id)
                return ProviderResult("SUCCEEDED", None, provider_ref=media)
            status = graph_read(
                lambda: runtime.api.get(box.creation_id, params={"fields": "status_code"})
            ).get("status_code")
        except CommsError as refused:  # a read made no effect: a plain failure
            return ProviderResult("FAILED", refused.code)
        if status in _NOT_PUBLISHABLE:
            store.mark_container(conn, box.ref, status)
            return ProviderResult("FAILED", _NOT_PUBLISHABLE[status])
        if status == "PUBLISHED":  # published, but comms never learned the media id (A19)
            store.mark_container(conn, box.ref, status)
            return ProviderResult("OUTCOME_UNKNOWN", None)
        if status != "FINISHED":
            return ProviderResult("FAILED", "PROVIDER_UNAVAILABLE")
        store.mark_container(conn, box.ref, status)
        body = {"creation_id": box.creation_id}
        result = write_call(lambda: runtime.api.post(runtime.user_id, "media_publish", body=body))
        if result.outcome != "SUCCEEDED":
            return result
        if not _CREATION.match(result.provider_ref or ""):
            return ProviderResult("OUTCOME_UNKNOWN", None)
        media_ref = store.object_ref(
            conn, account_id, "media", str(result.provider_ref), now=self._clock()
        )
        store.mark_container(conn, box.ref, "PUBLISHED", media_ref)
        return result
