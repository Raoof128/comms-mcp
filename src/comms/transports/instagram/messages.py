"""Instagram DM reads and the messaging window (proposed A49, sections 5.1, 7; D-I8) ✅ 🧪 GI-8.

A conversation's counterpart becomes an ``igp_`` (R-IG2); a message carries no ref. Message
details are readable only for the 20 most recent messages, one call each, so they are fetched
sequentially at the Conversations API's 2 calls per second per account. The window is computed
from the counterpart's latest message: inside 24 hours a reply is allowed; the 7-day
Click-to-Direct window is not visible without webhooks, so it is treated as closed (D-I8) ℹ️.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from comms.core.errors import CommsError
from comms.transports.instagram import store
from comms.transports.instagram.accounts import AccountRuntime
from comms.transports.instagram.classify import graph_read
from comms.transports.instagram.media import clean, provider_id

_THREAD = re.compile(r"\A[A-Za-z0-9_=-]{16,512}\Z")

__all__ = [
    "MAX_DETAILS",
    "WINDOW",
    "Throttle",
    "conversation_id",
    "conversation_items",
    "message_items",
    "window_open",
]

WINDOW = timedelta(hours=24)
MAX_DETAILS = 20  # Meta: details for the 20 most recent messages only
_MESSAGE_FIELDS = "id,created_time,from,to,message"


class Throttle:
    """At most ``rate`` calls per second per account (2 for the Conversations API)."""

    def __init__(self, rate: float = 2.0, *, sleep: Callable[[float], None] = time.sleep,
                 monotonic: Callable[[], float] = time.monotonic) -> None:  # fmt: skip
        self._gap, self._sleep, self._monotonic = 1.0 / rate, sleep, monotonic
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, account: str) -> None:
        with self._lock:
            now = self._monotonic()
            due = self._last.get(account, now - self._gap) + self._gap
            if due > now:
                self._sleep(due - now)
                now = due
            self._last[account] = now


def _participants(raw: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    block = raw.get("participants")
    data = block.get("data") if isinstance(block, dict) else None
    return [p for p in (data or []) if isinstance(p, dict)]


def _counterpart(raw: Mapping[str, Any], runtime: AccountRuntime, own: str) -> Mapping[str, Any]:
    others = [
        p for p in _participants(raw)
        if str(p.get("id")) != runtime.user_id and p.get("username") != own
    ]  # fmt: skip
    if len(others) != 1:
        raise CommsError("PROVIDER_UNAVAILABLE")  # groups are unsupported: one counterpart
    return others[0]


def conversation_items(
    conn: Any, runtime: AccountRuntime, data: list[Any], own: str, *, now: datetime
) -> list[dict[str, Any]]:
    items = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        other = _counterpart(raw, runtime, own)
        person = store.object_ref(
            conn, runtime.account_id, "person", provider_id(other.get("id")), now=now
        )
        items.append(
            {
                "person": person,
                "updated_time": clean(raw.get("updated_time"), 32),
                "untrusted": {"username": clean(other.get("username"), 64)},
            }
        )
    return items


def conversation_id(runtime: AccountRuntime, igsid: str, throttle: Throttle) -> str:
    """The conversation with one person (``GET /me/conversations?user_id=<IGSID>``)."""
    throttle.wait(runtime.ref)
    body = graph_read(
        lambda: runtime.api.get(
            "me", "conversations", params={"platform": "instagram", "user_id": igsid}
        )
    )
    data = body.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise CommsError("NOT_FOUND")
    ident = data[0].get("id")
    if not isinstance(ident, str) or not _THREAD.match(ident):
        raise CommsError("PROVIDER_UNAVAILABLE")
    return ident


def message_items(
    runtime: AccountRuntime, conversation: str, igsid: str, limit: int, throttle: Throttle
) -> list[dict[str, Any]]:
    """The ``limit`` most recent messages, newest first: ``at``, ``direction`` and the text."""
    throttle.wait(runtime.ref)
    body = graph_read(lambda: runtime.api.get(conversation, params={"fields": "messages"}))
    block = body.get("messages")
    listed = block.get("data") if isinstance(block, dict) else None
    items = []
    for entry in (listed or [])[: min(limit, MAX_DETAILS)]:
        if not isinstance(entry, dict):
            continue
        message = entry.get("id")
        if not isinstance(message, str) or not _THREAD.match(message):
            continue
        throttle.wait(runtime.ref)
        detail = graph_read(_detail(runtime, message))
        raw_sender = detail.get("from")
        sender: Mapping[str, Any] = raw_sender if isinstance(raw_sender, dict) else {}
        items.append(
            {
                "at": clean(detail.get("created_time"), 32),
                "direction": "in" if str(sender.get("id")) == igsid else "out",
                "untrusted_text": clean(detail.get("message"), 1000),
            }
        )
    return items


def _detail(runtime: AccountRuntime, message: str) -> Callable[[], Any]:
    return lambda: runtime.api.get(message, params={"fields": _MESSAGE_FIELDS})


def window_open(items: list[dict[str, Any]], now: datetime) -> bool:
    """Whether the counterpart wrote within 24 hours (their latest inbound message)."""
    for item in items:
        if item["direction"] != "in" or not isinstance(item["at"], str):
            continue
        try:
            at = datetime.strptime(item["at"], "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            continue
        return now - at < WINDOW
    return False
