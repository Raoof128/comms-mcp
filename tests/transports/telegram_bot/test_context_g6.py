"""Catalog amendment G6: the bot's group reads — admins (bots included), one member, the chat's
default permissions, and, from retained updates, join requests and messages around one."""

import json
from typing import Any

import httpx
import pytest

from comms.core.providers.protocols import ContextQuery, ContextRefused, ProviderTarget
from comms.runtime.selftest import _OneSecret
from comms.transports.telegram.bot.context import BotContext
from comms.transports.telegram.bot.http import BotApi
from comms.transports.telegram.bot.updates import BotPoller
from tests.core.audit.legacy_fixtures import comms_world
from tests.core.campaign_helpers import NOW

GROUP = ProviderTarget("telegram", "telegram_bot", "dst_g", "-77")


def _message(n, chat=-77, sender=42, text=None):
    return {"update_id": n, "message": {"message_id": 100 + n, "date": 1758800000 + n,
            "chat": {"id": chat, "type": "group"}, "from": {"id": sender, "first_name": "S"},
            "text": text or f"m{n}"}}  # fmt: skip


UPDATES = [
    _message(1),
    _message(2),
    {
        "update_id": 3,
        "chat_join_request": {
            "chat": {"id": -77, "type": "group"},
            "from": {"id": 908180, "first_name": "Sara"},
            "user_chat_id": 908180,
            "date": 1758800003,
        },
    },
    _message(4),
    _message(5),
]


class Api:
    def __init__(self, answers):
        self.answers, self.sent = answers, []

    def build(self):
        def handle(request: Any) -> httpx.Response:
            method = request.url.path.rsplit("/", 1)[-1]
            body = json.loads(request.content or b"{}")
            self.sent.append((method, body))
            if method == "getUpdates":
                offset = int(body.get("offset") or 0)
                result: Any = [u for u in UPDATES if u["update_id"] >= offset]
            else:
                result = self.answers.get(method, True)
            return httpx.Response(200, json={"ok": True, "result": result})

        return BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle))


@pytest.fixture
def world(tmp_path):
    conn = comms_world(tmp_path)["conn"]
    answers = {
        "getChatAdministrators": [
            {"status": "creator", "user": {"id": 1, "is_bot": False, "first_name": "Owner"}},
            {"status": "administrator", "user": {"id": 2, "is_bot": True, "first_name": "Bot"}},
        ],
        "getChatMember": {"status": "kicked", "user": {"id": 908180, "first_name": "Sara"}},
        "getChat": {"id": -77, "permissions": {"can_send_messages": True, "can_pin_messages": False,
                                               "unknown_flag": True, "can_invite_users": "yes"}},
    }  # fmt: skip
    api = Api(answers)
    bot = api.build()
    BotPoller(bot, conn, clock=lambda: NOW).poll_once()
    return {"ctx": BotContext(bot, conn, clock=lambda: NOW), "api": api}


def _read(world, kind, args=None):
    return world["ctx"].read(ContextQuery(GROUP, kind, dict(args or {})))


def test_admins_include_bots_and_carry_roles(world):
    page = _read(world, "admins")
    assert [(i["user_id"], i["role"], i["is_bot"]) for i in page.items] == [
        (1, "creator", False), (2, "admin", True)]  # fmt: skip
    assert ("getChatAdministrators", {"chat_id": -77, "return_bots": True}) in world["api"].sent


def test_one_member_standing(world):
    (item,) = _read(world, "member", {"user_id": "908180"}).items
    assert (item["role"], item["status"]) == (None, "banned")
    with pytest.raises(ValueError):
        _read(world, "member", {"user_id": "-5"})


def test_default_permissions_keep_only_the_known_boolean_flags(world):
    (item,) = _read(world, "permissions").items
    assert item["permissions"] == {"can_send_messages": True, "can_pin_messages": False}


def test_join_requests_come_from_retained_updates_and_are_not_messages(world):
    requests = _read(world, "join_requests")
    assert [(i["kind"], i["from_id"], i["untrusted"]) for i in requests.items] == [
        ("chat_join_request", 908180, {"name": "Sara"})]  # fmt: skip
    recent = _read(world, "recent", {"limit": 10})
    assert "chat_join_request" not in {i["kind"] for i in recent.items}
    assert requests.provenance == "telegram_local" and world["api"].sent[-1][0] == "getUpdates"


def test_around_one_retained_message_newest_first(world):
    page = _read(world, "around", {"message_id": 102, "before": 1, "after": 1})
    assert [i["message_id"] for i in page.items] == [104, 102, 101]  # the join request skipped
    with pytest.raises(ContextRefused) as missing:
        _read(world, "around", {"message_id": 999})
    assert missing.value.code == "TARGET_NOT_FOUND"
