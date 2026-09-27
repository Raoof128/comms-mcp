"""comms v0.3 Task C17: the adapter's self_rights over both group kinds (FakeClient)."""

import pytest
from telethon import errors
from telethon.tl import types

from comms.transports.telegram.telegram.errors import GatewayError
from comms.transports.telegram.telegram.telethon_adapter import TelegramConfig, TelethonSession
from tests.telegram.fake_client import FakeClient

ADMIN = types.ChatAdminRights(delete_messages=True, ban_users=True, invite_users=True)
MUTED = types.ChatBannedRights(until_date=None, send_messages=True)


def _channel(**kw):
    base = {
        "id": 77,
        "title": "t",
        "photo": types.ChatPhotoEmpty(),
        "date": None,
        "access_hash": 5,
        "megagroup": True,
    }
    return types.Channel(**{**base, **kw})


def _participant(participant, **channel):
    return types.channels.ChannelParticipant(
        participant=participant, chats=[_channel(**channel)], users=[]
    )


def _chat_full(**chat):
    base = {
        "id": 55,
        "title": "g",
        "photo": types.ChatPhotoEmpty(),
        "participants_count": 3,
        "date": None,
        "version": 1,
    }
    full = types.ChatFull(
        id=55,
        about="",
        participants=types.ChatParticipantsForbidden(chat_id=55),
        notify_settings=types.PeerNotifySettings(),
    )
    return types.messages.ChatFull(full_chat=full, chats=[types.Chat(**{**base, **chat})], users=[])


async def _rights(tmp_path, name, answer, peer=("channel", 77)):
    fake = FakeClient({name: answer})
    fake.session.remember(_channel())
    fake.session.remember(
        types.Chat(
            id=55,
            title="g",
            photo=types.ChatPhotoEmpty(),
            participants_count=3,
            date=None,
            version=1,
        )
    )
    session = TelethonSession(
        TelegramConfig(api_id=1, session_dir=tmp_path / "s"),
        api_hash="0" * 32,
        client_factory=lambda *a, **k: fake,
    )
    await session.start()
    try:
        return await session.self_rights(*peer, timeout=5)
    finally:
        await session.stop()


GET = "channels.GetParticipantRequest"
FULL = "messages.GetFullChatRequest"


async def test_a_supergroup_admin(tmp_path):
    view = await _rights(
        tmp_path,
        GET,
        _participant(
            types.ChannelParticipantAdmin(1, 2, None, ADMIN),
            forum=True,
            default_banned_rights=MUTED,
        ),
    )
    assert (view.kind, view.status, view.is_forum) == ("megagroup", "admin", True)
    assert view.rights == {"delete_messages", "ban_users", "invite_users"}
    assert view.denied == frozenset()  # chat defaults do not bind admins


async def test_a_supergroup_creator_holds_every_right(tmp_path):
    view = await _rights(
        tmp_path, GET, _participant(types.ChannelParticipantCreator(1, types.ChatAdminRights()))
    )
    assert (
        view.status == "creator" and {"add_admins", "change_info", "manage_topics"} <= view.rights
    )


async def test_a_member_under_chat_defaults(tmp_path):
    view = await _rights(
        tmp_path,
        GET,
        _participant(types.ChannelParticipantSelf(1, 2, None), default_banned_rights=MUTED),
    )
    assert (view.status, view.rights, view.denied) == ("member", frozenset(), {"send_messages"})


async def test_a_broadcast_channel_subscriber(tmp_path):
    view = await _rights(
        tmp_path,
        GET,
        _participant(types.ChannelParticipantSelf(1, 2, None), megagroup=False, broadcast=True),
    )
    assert (view.kind, view.status) == ("broadcast", "member")


@pytest.mark.parametrize(
    "answer,status",
    [
        (errors.UserNotParticipantError(request=None), "left"),
        (_participant(types.ChannelParticipantLeft(types.PeerUser(1))), "left"),
        (
            _participant(
                types.ChannelParticipantBanned(
                    types.PeerUser(1),
                    2,
                    None,
                    types.ChatBannedRights(until_date=None, view_messages=True),
                )
            ),
            "banned",
        ),
        (
            _participant(types.ChannelParticipantBanned(types.PeerUser(1), 2, None, MUTED)),
            "restricted",
        ),
    ],
)
async def test_left_banned_and_restricted(tmp_path, answer, status):
    view = await _rights(tmp_path, GET, answer)
    assert view.status == status
    if status == "restricted":
        assert view.denied == {"send_messages"}


async def test_a_basic_group_admin_has_the_same_shape(tmp_path):
    view = await _rights(
        tmp_path,
        FULL,
        _chat_full(admin_rights=ADMIN, default_banned_rights=MUTED),
        peer=("chat", 55),
    )
    assert (view.kind, view.status, view.is_forum) == ("chat", "admin", False)
    assert (
        view.rights == {"delete_messages", "ban_users", "invite_users"}
        and view.denied == frozenset()
    )


@pytest.mark.parametrize(
    "chat,status",
    [({"creator": True}, "creator"), ({"left": True}, "left"), ({}, "member")],
)
async def test_basic_group_standing(tmp_path, chat, status):
    assert (await _rights(tmp_path, FULL, _chat_full(**chat), peer=("chat", 55))).status == status


async def test_a_forbidden_basic_group_is_banned(tmp_path):
    full = _chat_full()
    full.chats = [types.ChatForbidden(55, "g")]
    assert (await _rights(tmp_path, FULL, full, peer=("chat", 55))).status == "banned"


async def test_lookup_failures_are_gateway_errors(tmp_path):
    with pytest.raises(GatewayError) as failed:
        await _rights(tmp_path, GET, errors.FloodWaitError(request=None, capture=3))
    assert failed.value.code == "FLOOD_WAIT"
    with pytest.raises(GatewayError) as failed:
        await _rights(
            tmp_path, GET, _participant(types.ChannelParticipantSelf(1, 2, None)), peer=("user", 1)
        )
    assert failed.value.code == "NOT_ACCESSIBLE"  # a user is not a group


# -- found live (2026-09-28): Telegram's getParticipant answer can omit the channel ------------

PEER_DIALOGS = "messages.GetPeerDialogsRequest"


def _bare(participant):
    """channels.channelParticipant as Telegram answered it live: ``chats`` is empty."""
    return types.channels.ChannelParticipant(participant=participant, chats=[], users=[])


def _peer_dialogs(*chats):
    return types.messages.PeerDialogs(dialogs=[], messages=[], chats=list(chats), users=[],
                                      state=types.updates.State(1, 0, None, 0, 0))  # fmt: skip


async def _rights_scripted(tmp_path, script):
    fake = FakeClient(script)
    fake.session.remember(_channel())
    session = TelethonSession(
        TelegramConfig(api_id=1, session_dir=tmp_path / "s"),
        api_hash="0" * 32,
        client_factory=lambda *a, **k: fake,
    )
    await session.start()
    try:
        return await session.self_rights("channel", 77, timeout=5), fake.calls
    finally:
        await session.stop()


async def test_a_creator_whose_answer_omits_the_channel_is_still_the_creator(tmp_path):
    view, calls = await _rights_scripted(tmp_path, {
        GET: _bare(types.ChannelParticipantCreator(1, types.ChatAdminRights())),
        PEER_DIALOGS: _peer_dialogs(_channel(forum=True)),
    })  # fmt: skip
    assert (view.kind, view.status, view.is_forum) == ("megagroup", "creator", True)
    assert calls[-2:] == [GET, PEER_DIALOGS]  # one more reviewed read, only when needed


async def test_a_member_whose_answer_omits_the_channel_gets_its_defaults_from_the_dialog(tmp_path):
    view, _calls = await _rights_scripted(tmp_path, {
        GET: _bare(types.ChannelParticipantSelf(1, 2, None)),
        PEER_DIALOGS: _peer_dialogs(_channel(default_banned_rights=MUTED)),
    })  # fmt: skip
    assert (view.status, view.denied) == ("member", {"send_messages"})


async def test_an_answer_with_the_channel_needs_no_second_read(tmp_path):
    _view, calls = await _rights_scripted(tmp_path, {
        GET: _participant(types.ChannelParticipantCreator(1, types.ChatAdminRights())),
    })  # fmt: skip
    assert PEER_DIALOGS not in calls


async def test_no_channel_anywhere_is_still_not_accessible(tmp_path):
    with pytest.raises(GatewayError) as exc:
        await _rights_scripted(tmp_path, {
            GET: _bare(types.ChannelParticipantSelf(1, 2, None)),
            PEER_DIALOGS: _peer_dialogs(),
        })  # fmt: skip
    assert exc.value.code == "NOT_ACCESSIBLE"
