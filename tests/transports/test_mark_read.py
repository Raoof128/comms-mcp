"""Spec A47 (H1): the Telegram user account marks a person's conversation read.

``messages.readHistory(peer=<the person>, max_id=<the message>)``, reviewed under
``cap.message.mark_read`` and nowhere else: every other read-acknowledge request stays absent,
and no read path marks anything read. The message is a ``cmg_`` the user account minted in that
person's conversation. Message ids belong to the actor that read them, so a ``cmg_`` from the
bot's retained updates is refused (Gx6), and the tool routes by the ``cmg_``, not by a schema
change (Gx7).
"""

import pytest
from telethon.tl import types

from comms.core import refs
from comms.core.campaigns.directory import member_identity
from comms.core.objects import message_identity, object_ref
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import ProviderTarget
from comms.core.providers.semantics import SEMANTICS, SUPPORT
from comms.transports.telegram.telegram.telethon_adapter import OPERATIONS
from comms.transports.telegram.user.capability import UserCapability
from tests.core.campaign_helpers import NOW
from tests.integration.test_actor_matrix_behaviour import CLIENT, _world
from tests.transports.telegram_user.test_admin_chat import SUPER, _invoke

PERSON = ProviderTarget("telegram", "telegram_user", "rcp_x", "42")


def test_mark_read_is_the_user_account_and_whatsapp_only():
    assert set(SUPPORT[C.MESSAGE_MARK_READ]) == {"telegram_user", "whatsapp_cloud"}
    assert SEMANTICS[(C.MESSAGE_MARK_READ, "telegram_user")].retry_class == "SET_STATE"


def test_read_history_is_reviewed_under_mark_read_only():
    holders = {op for op, names in OPERATIONS.items() if "messages.ReadHistoryRequest" in names}
    assert holders == {"cap.message.mark_read"}
    assert OPERATIONS["cap.message.mark_read"] == frozenset({"messages.ReadHistoryRequest"})
    for absent in ("channels.ReadHistoryRequest", "messages.ReadMessageContentsRequest",
                   "messages.ReadMentionsRequest", "messages.ReadReactionsRequest",
                   "messages.GetMessagesViewsRequest"):  # fmt: skip
        assert not any(absent in names for names in OPERATIONS.values()), absent


def test_the_request(tmp_path):
    result, sent, calls = _invoke(
        tmp_path, {"messages.ReadHistoryRequest": types.messages.AffectedMessages(pts=1, pts_count=1)},
        C.MESSAGE_MARK_READ, {"message_id": 55}, PERSON,
    )  # fmt: skip
    assert calls == ["messages.ReadHistoryRequest"] and result.outcome == "SUCCEEDED"
    assert isinstance(sent[0].peer, types.InputPeerUser) and sent[0].peer.user_id == 42
    assert sent[0].max_id == 55


def test_a_group_is_never_marked_read(tmp_path):
    with pytest.raises(ValueError):
        _invoke(tmp_path, {}, C.MESSAGE_MARK_READ, {"message_id": 5}, SUPER)


def test_any_other_write_to_a_private_chat_is_still_refused(tmp_path):
    with pytest.raises(ValueError):
        _invoke(tmp_path, {}, C.MESSAGE_PIN, {"message_id": 5, "pinned": True}, PERSON)


def test_capability_states():
    class Session:
        def readiness(self):
            return None

        async def self_rights(self, *a, **k):  # a private chat needs no lookup
            raise AssertionError

    cap = UserCapability(Session(), run=lambda c: None, clock=lambda: NOW)
    person = cap.snapshot("telegram_user", PERSON).states
    assert person[C.MESSAGE_MARK_READ] is S.AVAILABLE


def _refs(w, *, actor, person=True):
    conn = w["conn"]
    chat = member_identity(conn, w["rcp"], "telegram") if person else "-77"
    return object_ref(conn, "message", "telegram", actor, None, message_identity(chat, 55), now=NOW)


def test_through_the_dispatcher_by_the_users_cmg(tmp_path):
    w, dispatcher, admin, _specs = _world("telegram_user", tmp_path)
    args = {"conversation": w["rcp"], "message": _refs(w, actor="telegram_user"),
            "request_id": refs.mint("request")}  # fmt: skip
    got = dispatcher.call(CLIENT, "comms_message_mark_read", args)
    assert got.error_code is None and got.structured["result"] == "SUCCEEDED"
    assert got.structured["actor"] == "telegram_user"
    assert admin.calls == [(C.MESSAGE_MARK_READ, {"message_id": 55})]
    again = dispatcher.call(CLIENT, "comms_message_mark_read", args)
    assert again.structured["replayed"] is True and len(admin.calls) == 1


def test_a_bot_cmg_is_refused_before_any_call(tmp_path):
    w, dispatcher, admin, _specs = _world("telegram_user", tmp_path)
    got = dispatcher.call(CLIENT, "comms_message_mark_read", {
        "conversation": w["rcp"], "message": _refs(w, actor="telegram_bot"),
        "request_id": refs.mint("request")})  # fmt: skip
    assert got.error_code == "PROVIDER_UNSUPPORTED" and admin.calls == []


def test_another_conversations_message_is_refused(tmp_path):
    w, dispatcher, admin, _specs = _world("telegram_user", tmp_path)
    got = dispatcher.call(CLIENT, "comms_message_mark_read", {
        "conversation": w["rcp"], "message": _refs(w, actor="telegram_user", person=False),
        "request_id": refs.mint("request")})  # fmt: skip
    assert got.error_code == "NOT_FOUND" and admin.calls == []


def test_the_writes_path_refuses_another_actors_message_in_a_private_chat(tmp_path):
    """Gx6 at the one write path: a private chat's or a basic group's message ids are each
    account's own; only a supergroup or channel shares them."""
    from comms.services.writes import ProviderWrites
    from tests.services.group_fixtures import fixtures

    w, _dispatcher, _admin, _specs = _world("telegram_user", tmp_path)
    capability, executor, _admins = fixtures(w)
    writes = ProviderWrites(w["conn"], capability, executor)
    identity = member_identity(w["conn"], w["rcp"], "telegram")
    target = ProviderTarget("telegram", "telegram_user", w["rcp"], identity)
    assert writes.identity(_refs(w, actor="telegram_user"), "message", target) == 55
    with pytest.raises(Exception) as refused:
        writes.identity(_refs(w, actor="telegram_bot"), "message", target)
    assert getattr(refused.value, "code", None) == "NOT_FOUND"
    channel = ProviderTarget("telegram", "telegram_user", "d", "-1000000000077")
    shared = object_ref(w["conn"], "message", "telegram", "telegram_bot", None,
                        message_identity("-1000000000077", 9), now=NOW)  # fmt: skip
    assert writes.identity(shared, "message", channel) == 9
