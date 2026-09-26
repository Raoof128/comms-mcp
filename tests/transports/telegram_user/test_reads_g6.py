"""Catalog amendment G6: the user account's group reads over real TL objects — administrators,
one member's standing and the chat's default permissions, each one reviewed read RPC."""

import asyncio
import threading
from datetime import UTC, datetime

import pytest
from telethon import errors
from telethon.tl import types

from comms.core.providers.protocols import ContextQuery, ProviderTarget
from comms.transports.telegram.telegram.telethon_adapter import TelegramConfig, TelethonSession
from comms.transports.telegram.user.context import UserContext
from tests.telegram.fake_client import FakeClient

NOW = datetime(2026, 9, 25, tzinfo=UTC)
SUPER = ProviderTarget("telegram", "telegram_user", "dst_s", "-1000000000077")
BASIC = ProviderTarget("telegram", "telegram_user", "dst_b", "-55")


def _channel(**kw):
    return types.Channel(id=77, title="t", photo=types.ChatPhotoEmpty(), date=None,
                         access_hash=5, megagroup=True, **kw)  # fmt: skip


def _user(uid, name):
    return types.User(id=uid, access_hash=9, first_name=name)


def _run(tmp_path, script, kind, target=SUPER, args=None):
    fake = FakeClient(script)
    fake.session.remember(_channel())
    fake.session.remember(_user(42, "Jack"))
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    def run(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop).result(10)

    session = TelethonSession(
        TelegramConfig(api_id=1, session_dir=tmp_path / "s"),
        api_hash="0" * 32,
        client_factory=lambda *a, **k: fake,
    )
    run(session.start())
    try:
        page = UserContext(session, run=run, clock=lambda: NOW).read(
            ContextQuery(target, kind, dict(args or {}))
        )
    finally:
        run(session.stop())
        loop.call_soon_threadsafe(loop.stop)
        thread.join(5)
        loop.close()
    return page, [c for c in fake.calls if not c.startswith(("updates.", "users.", "help."))]


def _full_chat(parts, rights=None):
    chat = types.Chat(id=55, title="b", photo=types.ChatPhotoEmpty(), participants_count=len(parts),
                      date=None, version=1, default_banned_rights=rights)  # fmt: skip
    full = types.ChatFull(id=55, about="", participants=types.ChatParticipants(55, parts, 1),
                          notify_settings=types.PeerNotifySettings())  # fmt: skip
    return types.messages.ChatFull(full_chat=full, chats=[chat], users=[_user(42, "Jack"),
                                   _user(43, "Jill")])  # fmt: skip


def test_admins_of_a_supergroup_use_the_admins_filter(tmp_path):
    answer = types.channels.ChannelParticipants(
        count=2,
        participants=[
            types.ChannelParticipantCreator(user_id=42, admin_rights=types.ChatAdminRights()),
            types.ChannelParticipantAdmin(
                user_id=43, promoted_by=42, date=None, admin_rights=types.ChatAdminRights()
            ),
        ],
        chats=[],
        users=[_user(42, "Jack"), _user(43, "Jill")],
    )
    seen = []
    page, calls = _run(
        tmp_path, {"channels.GetParticipantsRequest": lambda r: seen.append(r) or answer}, "admins"
    )
    assert calls == ["channels.GetParticipantsRequest"]
    assert isinstance(seen[0].filter, types.ChannelParticipantsAdmins)
    assert [(i["user_id"], i["role"], i["untrusted"]) for i in page.items] == [
        (42, "creator", {"name": "Jack"}), (43, "admin", {"name": "Jill"})]  # fmt: skip


def test_admins_of_a_basic_group_come_from_the_full_chat(tmp_path):
    parts = [types.ChatParticipantCreator(42), types.ChatParticipant(43, 42, None)]
    page, calls = _run(
        tmp_path, {"messages.GetFullChatRequest": _full_chat(parts)}, "admins", BASIC
    )
    assert calls == ["messages.GetFullChatRequest"]
    assert [(i["user_id"], i["role"]) for i in page.items] == [(42, "creator")]


@pytest.mark.parametrize(
    ("answer", "standing"),
    [
        (types.ChannelParticipant(user_id=42, date=None), ("member", "member")),
        (types.ChannelParticipantBanned(peer=types.PeerUser(42), kicked_by=1, date=None,
         banned_rights=types.ChatBannedRights(until_date=None, view_messages=True)), (None, "banned")),
        (types.ChannelParticipantBanned(peer=types.PeerUser(42), kicked_by=1, date=None,
         banned_rights=types.ChatBannedRights(until_date=None, send_messages=True)),
         ("member", "restricted")),
        (errors.UserNotParticipantError(request=None), (None, "left")),
    ],
)  # fmt: skip
def test_one_member_of_a_supergroup(tmp_path, answer, standing):
    if not isinstance(answer, BaseException):
        answer = types.channels.ChannelParticipant(participant=answer, chats=[], users=[])
    page, calls = _run(tmp_path, {"channels.GetParticipantRequest": answer}, "member",
                       args={"user_id": "42"})  # fmt: skip
    assert calls == ["channels.GetParticipantRequest"]
    assert (page.items[0]["role"], page.items[0]["status"]) == standing


def test_default_permissions_of_a_supergroup_invert_the_banned_rights(tmp_path):
    banned = types.ChatBannedRights(until_date=None, send_photos=True, pin_messages=True,
                                    send_stickers=True)  # fmt: skip
    answer = types.channels.ChannelParticipant(
        participant=types.ChannelParticipantSelf(user_id=4242, inviter_id=1, date=None),
        chats=[_channel(default_banned_rights=banned)], users=[],
    )  # fmt: skip
    seen = []
    page, calls = _run(tmp_path, {"channels.GetParticipantRequest": lambda r: seen.append(r) or answer},
                       "permissions")  # fmt: skip
    assert calls == ["channels.GetParticipantRequest"]  # no channels.getChannels, ever
    assert isinstance(seen[0].participant, types.InputUserSelf)
    permissions = page.items[0]["permissions"]
    assert permissions["can_send_messages"] is True and permissions["can_send_photos"] is False
    assert permissions["can_pin_messages"] is False
    assert permissions["can_send_other_messages"] is False  # any one of its flags denies it


def test_default_permissions_of_a_basic_group(tmp_path):
    rights = types.ChatBannedRights(until_date=None, invite_users=True)
    page, _calls = _run(tmp_path, {"messages.GetFullChatRequest": _full_chat([], rights)},
                        "permissions", BASIC)  # fmt: skip
    assert page.items[0]["permissions"]["can_invite_users"] is False
    assert page.items[0]["permissions"]["can_send_messages"] is True
