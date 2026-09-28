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


# -- G6 part 2: the user account's lists ---------------------------------------------------


def _list(tmp_path, script, kind, target=SUPER, args=None):
    return _run(tmp_path, script, kind, target, args)


def test_admin_log_pages_by_event_id_kinds_only(tmp_path):
    def event(n):
        return types.ChannelAdminLogEvent(id=n, date=NOW, user_id=42,
                                          action=types.ChannelAdminLogEventActionChangeTitle("a", "b"))  # fmt: skip

    full = types.channels.AdminLogResults(events=[event(50), event(49)], chats=[], users=[])
    seen = []
    page, calls = _list(tmp_path, {"channels.GetAdminLogRequest": lambda r: seen.append(r) or full},
                        "admin_log", args={"limit": 2})  # fmt: skip
    assert calls == ["channels.GetAdminLogRequest"] and (seen[0].limit, seen[0].max_id) == (2, 0)
    assert [(i["event_id"], i["user_id"], i["action"]) for i in page.items] == [
        (50, 42, "ChannelAdminLogEventActionChangeTitle"), (49, 42, "ChannelAdminLogEventActionChangeTitle")]  # fmt: skip
    assert page.next_cursor == "[49, 0]"
    last = types.channels.AdminLogResults(events=[event(48)], chats=[], users=[])
    seen.clear()
    page, _ = _list(tmp_path, {"channels.GetAdminLogRequest": lambda r: seen.append(r) or last},
                    "admin_log", args={"limit": 2, "cursor": "[49, 0]"})  # fmt: skip
    assert seen[0].max_id == 49 and page.next_cursor is None
    page, calls = _list(tmp_path, {}, "admin_log", BASIC)
    assert page.items == () and calls == []  # basic groups have no admin log


def test_invites_are_the_accounts_own_active_links(tmp_path):
    link = types.ChatInviteExported(link="https://t.me/+Abc", admin_id=4242, date=NOW, usage=3,
                                    usage_limit=10, permanent=True, title="Family")  # fmt: skip
    answer = types.messages.ExportedChatInvites(count=1, invites=[link], users=[])
    seen = []
    page, calls = _list(tmp_path, {"messages.GetExportedChatInvitesRequest":
                                   lambda r: seen.append(r) or answer}, "invites")  # fmt: skip
    assert calls == ["messages.GetExportedChatInvitesRequest"]
    assert isinstance(seen[0].admin_id, types.InputUserSelf) and seen[0].revoked is False
    (item,) = page.items
    assert (item["link"], item["usage"], item["usage_limit"], item["primary"]) == (
        "https://t.me/+Abc", 3, 10, True)  # fmt: skip
    assert item["untrusted"] == {"title": "Family"} and page.next_cursor is None


def test_join_requests_are_the_requested_importers(tmp_path):
    answer = types.messages.ChatInviteImporters(
        count=1, importers=[types.ChatInviteImporter(user_id=42, date=NOW, requested=True)],
        users=[_user(42, "Jack")])  # fmt: skip
    seen = []
    page, calls = _list(tmp_path, {"messages.GetChatInviteImportersRequest":
                                   lambda r: seen.append(r) or answer}, "join_requests")  # fmt: skip
    assert calls == ["messages.GetChatInviteImportersRequest"] and seen[0].requested is True
    assert [(i["user_id"], i["untrusted"]) for i in page.items] == [(42, {"name": "Jack"})]


def _topic(tid, title, **kw):
    return types.ForumTopic(id=tid, date=NOW, peer=types.PeerChannel(77), title=title,
                            icon_color=0, top_message=tid, read_inbox_max_id=0,
                            read_outbox_max_id=0, unread_count=0, unread_mentions_count=0,
                            unread_reactions_count=0, unread_poll_votes_count=0,
                            from_id=types.PeerUser(42),
                            notify_settings=types.PeerNotifySettings(), **kw)  # fmt: skip


def test_topics_listed_and_one_by_id(tmp_path):
    answer = types.messages.ForumTopics(count=2, topics=[_topic(1, "General"),
                                        _topic(9, "Events", closed=True)], messages=[], chats=[],
                                        users=[], pts=1)  # fmt: skip
    page, calls = _list(tmp_path, {"messages.GetForumTopicsRequest": answer}, "topics")
    assert calls == ["messages.GetForumTopicsRequest"]
    assert [(i["topic_id"], i["closed"], i["untrusted"]["name"]) for i in page.items] == [
        (1, False, "General"), (9, True, "Events")]  # fmt: skip
    seen = []
    one = types.messages.ForumTopics(count=1, topics=[_topic(9, "Events")], messages=[],
                                     chats=[], users=[], pts=1)  # fmt: skip
    page, calls = _list(tmp_path, {"messages.GetForumTopicsByIDRequest":
                                   lambda r: seen.append(r) or one}, "topic",
                        args={"topic_id": "9"})  # fmt: skip
    assert calls == ["messages.GetForumTopicsByIDRequest"] and seen[0].topics == [9]
    page, calls = _list(tmp_path, {}, "topics", BASIC)
    assert page.items == () and calls == []


def test_one_senders_messages_narrow_the_same_search(tmp_path):
    answer = types.messages.Messages(messages=[], topics=[], chats=[], users=[])
    seen = []
    _page, calls = _list(tmp_path, {"messages.SearchRequest": lambda r: seen.append(r) or answer},
                         "from", args={"sender": "42"})  # fmt: skip
    assert calls == ["messages.SearchRequest"]
    assert seen[0].q == "" and isinstance(seen[0].from_id, types.InputPeerUser)
    assert seen[0].from_id.user_id == 42


def test_default_permissions_when_the_participant_answer_omits_the_channel(tmp_path):
    """Found live (2026-09-28, R-TG4): for the group's creator Telegram's getParticipant answer
    carried no channel, so the read failed; the channel comes from one peer-dialog read."""
    banned = types.ChatBannedRights(until_date=None, pin_messages=True)
    bare = types.channels.ChannelParticipant(
        participant=types.ChannelParticipantCreator(user_id=4242, admin_rights=types.ChatAdminRights()),
        chats=[], users=[])  # fmt: skip
    dialogs = types.messages.PeerDialogs(dialogs=[], messages=[], users=[],
        chats=[_channel(default_banned_rights=banned)], state=types.updates.State(1, 0, None, 0, 0))  # fmt: skip
    page, calls = _run(tmp_path, {"channels.GetParticipantRequest": bare,
                                  "messages.GetPeerDialogsRequest": dialogs}, "permissions")  # fmt: skip
    assert calls == ["channels.GetParticipantRequest", "messages.GetPeerDialogsRequest"]
    permissions = page.items[0]["permissions"]
    assert permissions["can_pin_messages"] is False and permissions["can_send_messages"] is True
