"""Catalog amendment G6: group reads through the real composition, for the bot actor.

A requester or member leaves as the directory person's ``rcp_`` ref (``null`` when unknown) and
never as a user id; join requests page with a client-bound ``cur_`` token that stays with the
actor that served the first page; ``comms_group_context`` for the bot serves messages and
admins and leaves out the member list the Bot API cannot produce.
"""

import json
import os

import pytest

from comms.core.keys import rotate as rot
from comms.core.providers.capability import CapabilityState as S
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.adapters import Adapters
from comms.runtime.comms_runtime import build_comms_runtime
from comms.transports.telegram.bot.context import BotContext
from comms.transports.telegram.bot.updates import BotPoller
from tests.core.campaign_helpers import NOW
from tests.services.context_fixtures import Clock
from tests.services.group_fixtures import TG_USER, Provider, group_world
from tests.transports.telegram_bot import test_context_g6 as bot

CLIENT = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")
OTHER = AuthenticatedClient(client_ref="cli_" + "b" * 26, auth_kind="cml1")


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = group_world(tmp_path)
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(w["writer"], w["store"], purpose, material=os.urandom(32),
                   prove=lambda m: None, now=NOW)  # fmt: skip
    requests = [
        {"update_id": n, "chat_join_request": {"chat": {"id": -77, "type": "group"},
         "from": {"id": uid, "first_name": name}, "user_chat_id": uid, "date": 1758800000 + n}}
        for n, uid, name in ((1, int(TG_USER), "Ali"), (2, 5551, "Stranger"), (3, 5552, "Third"))
    ]  # fmt: skip
    monkeypatch.setattr(bot, "UPDATES", requests)
    api = bot.Api({
        "getChatAdministrators": [{"status": "creator", "user": {"id": 1, "first_name": "O"}}],
        "getChatMember": {"status": "administrator", "user": {"id": int(TG_USER)}},
        "getChat": {"id": -77, "permissions": {"can_send_messages": False}},
    }).build()  # fmt: skip
    BotPoller(api, w["conn"], clock=lambda: NOW).poll_once()
    w["poll"] = lambda: BotPoller(api, w["conn"], clock=lambda: NOW).poll_once()
    adapters = Adapters(
        capability={"telegram_bot": Provider(S.AVAILABLE)},
        context={"telegram_bot": BotContext(api, w["conn"], clock=lambda: NOW)},
    )
    built = build_comms_runtime(w["conn"], w["writer"], w["store"], adapters, clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip
    w["call"] = lambda tool, args, client=CLIENT: built.dispatcher.call(client, tool, args)
    return w


def _ok(result):
    assert result.error_code is None, result.error_code
    return result.structured


def test_a_member_by_ref(world):
    got = _ok(world["call"]("comms_group_members_get", {"group": world["grp"],
                                                        "recipient": world["rcp"]}))  # fmt: skip
    assert (got["recipient"], got["role"], got["status"]) == (world["rcp"], "admin", "member")
    assert TG_USER not in json.dumps(got)


def test_default_permissions(world):
    got = _ok(world["call"]("comms_group_permissions_get", {"group": world["grp"]}))
    assert got["permissions"] == {"can_send_messages": False}


def test_join_requests_by_ref_and_paged_with_a_client_bound_token(world):
    first = _ok(world["call"]("comms_group_join_requests_list", {"group": world["grp"]}))
    assert [i["recipient"] for i in first["items"]] == [None, None, world["rcp"]]
    assert [i["untrusted"]["name"] for i in first["items"]] == ["Third", "Stranger", "Ali"]
    assert first["items"][0]["requested_at"].startswith("2025-")
    text = json.dumps(first)
    assert TG_USER not in text and "5551" not in text
    assert first["next_cursor"] is None


def test_group_context_serves_messages_and_admins_without_the_member_list(world):
    got = _ok(world["call"]("comms_group_context", {"group": world["grp"]}))
    assert set(got) >= {"group_ref", "messages", "admins"} and "members" not in got
    assert [i["role"] for i in got["admins"]["items"]] == ["creator"]
    alone = world["call"]("comms_group_members_list", {"group": world["grp"]})
    assert alone.error_code == "PROVIDER_UNSUPPORTED"  # asked alone, it still refuses


def test_a_second_page_needs_the_same_client_and_group(world, monkeypatch):
    many = [
        {"update_id": 10 + n, "chat_join_request": {"chat": {"id": -77, "type": "group"},
         "from": {"id": 7000 + n, "first_name": f"P{n}"}, "date": 1758800100 + n}}
        for n in range(55)
    ]  # fmt: skip
    monkeypatch.setattr(bot, "UPDATES", many)
    world["poll"]()
    first = _ok(world["call"]("comms_group_join_requests_list", {"group": world["grp"]}))
    assert len(first["items"]) == 50 and first["next_cursor"].startswith("cur_")
    args = {"group": world["grp"], "cursor": first["next_cursor"]}
    rest = _ok(world["call"]("comms_group_join_requests_list", args))
    assert len(rest["items"]) == 8 and rest["next_cursor"] is None  # 55 + the 3 before
    assert world["call"]("comms_group_join_requests_list", args, client=OTHER).error_code
    from comms.core.campaigns import directory as d
    from comms.core.groups import group_ref

    loc = d.add_location(world["conn"], "X", now=NOW)
    other = d.add_destination(world["conn"], loc, "telegram", "group:88", "X",
                              normalize=lambda s: "-88", now=NOW)  # fmt: skip
    elsewhere = {"group": group_ref(world["conn"], other, now=NOW), "cursor": first["next_cursor"]}
    assert world["call"]("comms_group_join_requests_list", elsewhere).error_code == "STALE_HANDLE"
