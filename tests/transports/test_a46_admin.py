"""Spec A46 (built in G7): member tags and reaction moderation on both Telegram APIs.

Bot: ``setChatMemberTag``, ``deleteMessageReaction`` (with ``user_id``) and
``deleteAllMessageReactions``. User: ``messages.editChatParticipantRank``,
``messages.deleteParticipantReaction`` and ``messages.deleteParticipantReactions``. A tag is
0–16 characters with no emoji; an empty tag clears it. WhatsApp has none of these.
"""

import json

import httpx
import pytest

from comms.core import refs
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderTarget, SemanticOperation
from comms.core.providers.semantics import SEMANTICS, SUPPORT
from comms.runtime.selftest import _OneSecret
from comms.transports.telegram.bot.admin import BotAdmin
from comms.transports.telegram.bot.http import BotApi
from tests.integration.test_actor_matrix_behaviour import CLIENT, _world
from tests.transports.telegram_user.test_admin_chat import OK, SUPER, _invoke

BOT = ProviderTarget("telegram", "telegram_bot", "d", "-77")


def _bot(op):
    sent = []

    def handle(request):
        sent.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": True})

    admin = BotAdmin(BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle)))
    return admin.invoke(op, BOT, "k"), sent


def test_the_three_capabilities_are_telegram_only_and_set_state():
    for cap in (C.MEMBER_TAG, C.REACTION_REMOVE, C.REACTION_CLEAR):
        assert set(SUPPORT[cap]) == {"telegram_bot", "telegram_user"}
        for actor in SUPPORT[cap]:
            assert SEMANTICS[(cap, actor)].retry_class == "SET_STATE"


@pytest.mark.parametrize(
    ("cap", "args", "method", "params"),
    [
        (C.MEMBER_TAG, {"user_id": 42, "tag": "Elder"}, "setChatMemberTag",
         {"chat_id": -77, "user_id": 42, "tag": "Elder"}),
        (C.MEMBER_TAG, {"user_id": 42, "tag": ""}, "setChatMemberTag",
         {"chat_id": -77, "user_id": 42, "tag": ""}),
        (C.REACTION_REMOVE, {"user_id": 42, "message_id": 9}, "deleteMessageReaction",
         {"chat_id": -77, "user_id": 42, "message_id": 9}),
        (C.REACTION_CLEAR, {"user_id": 42}, "deleteAllMessageReactions",
         {"chat_id": -77, "user_id": 42}),
    ],
)  # fmt: skip
def test_the_bot_requests(cap, args, method, params):
    result, sent = _bot(SemanticOperation(cap, args))
    assert sent == [(method, params)] and result.outcome == "SUCCEEDED"


@pytest.mark.parametrize("tag", ["x" * 17, "Elder🙂", "a\nb", 7])
def test_a_bad_tag_is_refused_before_a_call(tag):
    admin = BotAdmin(
        BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(lambda r: 1 / 0))
    )
    with pytest.raises(ValueError):
        admin.validate(SemanticOperation(C.MEMBER_TAG, {"user_id": 42, "tag": tag}), BOT)


@pytest.mark.parametrize(
    ("cap", "args", "rpc", "check"),
    [
        (C.MEMBER_TAG, {"user_id": 42, "tag": "Elder"}, "messages.EditChatParticipantRankRequest",
         lambda r: r.rank == "Elder" and r.participant.user_id == 42),
        (C.REACTION_REMOVE, {"user_id": 42, "message_id": 9},
         "messages.DeleteParticipantReactionRequest",
         lambda r: r.msg_id == 9 and r.participant.user_id == 42),
        (C.REACTION_CLEAR, {"user_id": 42}, "messages.DeleteParticipantReactionsRequest",
         lambda r: r.participant.user_id == 42),
    ],
)  # fmt: skip
def test_the_user_account_requests(tmp_path, cap, args, rpc, check):
    result, sent, calls = _invoke(tmp_path, {rpc: OK}, cap, args, SUPER)
    assert calls == [rpc] and check(sent[0]) and result.outcome == "SUCCEEDED"


def test_an_unknown_member_is_not_found_without_a_call(tmp_path):
    result, _sent, calls = _invoke(tmp_path, {}, C.REACTION_CLEAR, {"user_id": 9999}, SUPER)
    assert calls == [] and (result.outcome, result.code) == ("FAILED", "TARGET_NOT_FOUND")


@pytest.mark.parametrize("actor", ["telegram_bot", "telegram_user"])
def test_through_the_dispatcher_by_refs(actor, tmp_path):
    w, dispatcher, admin, _specs = _world(actor, tmp_path)
    first = dispatcher.call(CLIENT, "comms_context_recent", {"group": w["grp"], "limit": 1})
    message = first.structured["items"][0]["message_ref"]
    for tool, extra in (
        ("comms_group_member_tag_set", {"tag": "Elder"}),
        ("comms_message_reaction_remove", {"message": message}),
        ("comms_group_member_reactions_clear", {}),
    ):
        got = dispatcher.call(CLIENT, tool, {"group": w["grp"], "recipient": w["rcp"],
                              "request_id": refs.mint("request"), **extra})  # fmt: skip
        assert got.error_code is None and got.structured["result"] == "SUCCEEDED", tool
    caps = [c for c, _a in admin.calls]
    assert caps == [C.MEMBER_TAG, C.REACTION_REMOVE, C.REACTION_CLEAR]
    assert admin.calls[1][1]["message_id"] > 0 and "message" not in admin.calls[1][1]


def test_whatsapp_refuses_all_three(tmp_path):
    w, dispatcher, admin, _specs = _world("whatsapp_cloud", tmp_path)
    got = dispatcher.call(CLIENT, "comms_group_member_tag_set", {"group": w["grp"],
                          "recipient": w["rcp"], "tag": "x", "request_id": refs.mint("request")})  # fmt: skip
    assert got.error_code == "PROVIDER_UNSUPPORTED" and admin.calls == []
