"""Catalog amendment G7: forward on both Telegram APIs, and group creation by the user account.

A forward is a new message: the bot's ``forwardMessage`` names it by its new id; the user
account's ``messages.forwardMessages`` carries a ``random_id`` from the operation key, exactly as
a send, so a retry with the same key is one message. A group is created from the account (no
destination), and on success it is filed in the directory with its ``grp_`` in the same step.
"""

import json

import httpx
import pytest
from telethon.tl import types

from comms.core import refs
from comms.core.campaigns import directory as d
from comms.core.groups import list_groups
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderTarget, SemanticOperation
from comms.runtime.selftest import _OneSecret
from comms.transports.telegram.bot.admin import BotAdmin
from comms.transports.telegram.bot.http import BotApi
from comms.transports.telegram.user.send import random_id_for
from tests.core.campaign_helpers import NOW
from tests.integration.test_actor_matrix_behaviour import CLIENT, _world
from tests.transports.telegram_user.test_admin_chat import SUPER, _invoke, _run

FORWARD = SemanticOperation(C.MESSAGE_FORWARD, {"from_chat": "-55", "message_id": 7})
KEY = "ab" * 32


def test_the_bot_forwards_and_names_the_new_message():
    sent = []

    def handle(request):
        sent.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 901}})

    admin = BotAdmin(BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle)))
    result = admin.invoke(FORWARD, ProviderTarget("telegram", "telegram_bot", "d", "-77"), KEY)
    assert sent == [("forwardMessage", {"chat_id": -77, "from_chat_id": -55, "message_id": 7})]
    assert (result.outcome, result.provider_ref) == ("SUCCEEDED", "901")


@pytest.mark.parametrize(
    "args",
    [{"from_chat": "55", "message_id": 7}, {"from_chat": "-55", "message_id": 0},
     {"from_chat": "-x", "message_id": 7}, {"message_id": 7}],
)  # fmt: skip
def test_a_malformed_forward_is_refused_before_a_call(args):
    admin = BotAdmin(
        BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(lambda r: 1 / 0))
    )
    with pytest.raises(ValueError):
        admin.validate(SemanticOperation(C.MESSAGE_FORWARD, args),
                       ProviderTarget("telegram", "telegram_bot", "d", "-77"))  # fmt: skip


def test_the_user_account_forwards_with_the_keys_random_id(tmp_path):
    random_id = random_id_for(KEY)  # an operation key is a hex digest
    answer = types.Updates(
        updates=[types.UpdateMessageID(id=902, random_id=random_id)], users=[], chats=[],
        date=None, seq=0)  # fmt: skip
    args = {"from_chat": "-1000000000077", "message_id": 7}
    op = SemanticOperation(C.MESSAGE_FORWARD, args)
    result, sent, calls = _run(tmp_path, {"messages.ForwardMessagesRequest": answer},
                               lambda admin: admin.invoke(op, SUPER, KEY))  # fmt: skip
    assert calls == ["messages.ForwardMessagesRequest"]
    assert sent[0].id == [7] and sent[0].random_id == [random_id]
    assert (result.outcome, result.provider_ref) == ("SUCCEEDED", "902")


def test_an_unknown_source_chat_is_provably_unsent(tmp_path):
    result, _sent, calls = _invoke(tmp_path, {}, C.MESSAGE_FORWARD,
                                   {"from_chat": "-55", "message_id": 7}, SUPER)  # fmt: skip
    assert calls == [] and (result.outcome, result.code) == ("FAILED", "PROVIDER_UNAVAILABLE")


def test_the_user_account_creates_a_supergroup_from_the_account(tmp_path):
    channel = types.Channel(id=4321, title="New", photo=types.ChatPhotoEmpty(), date=None,
                            access_hash=1, megagroup=True)  # fmt: skip
    answer = types.Updates(updates=[], users=[], chats=[channel], date=None, seq=0)
    account = ProviderTarget("telegram", "telegram_user", "loc_x", "account")
    result, sent, calls = _invoke(tmp_path, {"channels.CreateChannelRequest": answer},
                                  C.GROUP_CREATE, {"title": "New", "kind": "supergroup"},
                                  account)  # fmt: skip
    assert calls == ["channels.CreateChannelRequest"] and sent[0].megagroup
    assert (result.outcome, result.provider_ref) == ("SUCCEEDED", "-1000000004321")


def test_created_from_a_group_is_refused(tmp_path):
    from comms.transports.telegram.user.admin import UserAdmin

    admin = UserAdmin(session=None, run=None, clock=lambda: NOW)
    with pytest.raises(ValueError):
        admin.validate(SemanticOperation(C.GROUP_CREATE, {"title": "x", "kind": "supergroup"}),
                       SUPER)  # fmt: skip


def test_a_created_group_is_filed_with_its_group_ref_at_once(tmp_path):
    w, dispatcher, admin, _specs = _world("telegram_user", tmp_path)
    loc = d.add_location(w["conn"], "New place", now=NOW)
    got = dispatcher.call(CLIENT, "comms_group_create", {"location": loc, "title": "Families",
                          "kind": "supergroup", "request_id": refs.mint("request")})  # fmt: skip
    assert got.error_code is None and got.structured["result"] == "SUCCEEDED"
    grp = got.structured["group"]
    listed = {g["group"]: g for g in list_groups(w["conn"], limit=20)[0]}
    assert listed[grp]["location"] == loc and listed[grp]["name"] == "Families"
    assert [c for c, _a in admin.calls] == [C.GROUP_CREATE]


def test_an_unknown_location_is_refused_before_telegram_is_asked(tmp_path):
    _w, dispatcher, admin, _specs = _world("telegram_user", tmp_path)
    got = dispatcher.call(CLIENT, "comms_group_create", {"location": "loc_" + "a" * 26,
                          "title": "X", "kind": "supergroup", "request_id": refs.mint("request")})  # fmt: skip
    assert got.error_code == "NOT_FOUND" and admin.calls == []


def test_forward_between_two_groups_through_the_dispatcher(tmp_path):
    w, dispatcher, admin, _specs = _world("telegram_bot", tmp_path)
    first = dispatcher.call(CLIENT, "comms_context_recent", {"group": w["grp"], "limit": 1})
    message = first.structured["items"][0]["message_ref"]
    got = dispatcher.call(CLIENT, "comms_message_forward", {"group": w["grp"], "message": message,
                          "to_group": w["grp"], "request_id": refs.mint("request")})  # fmt: skip
    assert got.error_code is None and got.structured["message"].startswith("cmg_")
    ((capability, args),) = admin.calls
    assert capability is C.MESSAGE_FORWARD and args["from_chat"] == "-77"
