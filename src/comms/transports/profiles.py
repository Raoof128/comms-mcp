"""Each account's own descriptive profile, never an identity (catalog amendment G8; A26).

``comms_account_profile`` shows what each configured account calls itself: the bot's name
(``getMe``; its username is a handle and is dropped), the user account's name
(``users.getUsers(self)``, reviewed on ``admin.status``) and the WhatsApp business profile's
``about``, ``description`` and ``vertical``. Everything is the provider's text, so it is
untrusted. A lookup that fails reports the account as unreachable rather than inventing text.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from comms.transports.telegram.bot.classify import LookupFailed, lookup
from comms.transports.telegram.telegram.deadline import Deadline
from comms.transports.telegram.telegram.errors import GatewayError
from comms.transports.whatsapp.cloud.http import GraphTransportError

__all__ = ["Profile", "bot_profile", "user_profile", "whatsapp_profile"]

Profile = Callable[[], Mapping[str, Any]]
_TEXT_MAX = 512


def _text(value: object) -> str | None:
    return value[:_TEXT_MAX] if isinstance(value, str) and value else None


def bot_profile(api: Any) -> Profile:
    def read() -> Mapping[str, Any]:
        try:
            me = lookup(api, "getMe", {})
        except LookupFailed:
            return {"kind": "bot", "reachable": False, "untrusted": {}}
        name = _text(me.get("first_name")) if isinstance(me, dict) else None
        return {"kind": "bot", "reachable": True, "untrusted": {"name": name}}

    return read


def user_profile(session: Any, run: Callable[[Any], Any]) -> Profile:
    def read() -> Mapping[str, Any]:
        try:
            name = run(session.own_name(Deadline(15.0)))
        except GatewayError:
            return {"kind": "user", "reachable": False, "untrusted": {}}
        return {"kind": "user", "reachable": True, "untrusted": {"name": _text(name)}}

    return read


def whatsapp_profile(api: Any) -> Profile:
    def read() -> Mapping[str, Any]:
        try:
            response = api.business_profile()
        except GraphTransportError:
            return {"kind": "whatsapp_business", "reachable": False, "untrusted": {}}
        data = (response.envelope or {}).get("data") if response.http_status == 200 else None
        first = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else None
        if first is None:
            return {"kind": "whatsapp_business", "reachable": False, "untrusted": {}}
        text = {k: _text(first.get(k)) for k in ("about", "description", "vertical")}
        return {"kind": "whatsapp_business", "reachable": True, "untrusted": text}

    return read
