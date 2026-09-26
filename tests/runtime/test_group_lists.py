"""Catalog amendment G6 part 2: the user account's group lists through the real composition.

Invites leave as ``inv_`` refs, topics as ``top_`` refs, requesters and admin-log actors as the
directory person's ``rcp_`` (or ``null``); no link, topic id or user id appears in any output.
"""

import json
import os

import pytest

from comms.core.keys import rotate as rot
from comms.core.providers.capability import CapabilityState as S
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.adapters import Adapters
from comms.runtime.comms_runtime import build_comms_runtime
from tests.core.campaign_helpers import NOW
from tests.services.context_fixtures import Clock, Source
from tests.services.group_fixtures import TG_USER, Provider, group_world

CLIENT = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")
IDS = (TG_USER, "t.me", "AbCdEf", '"9"', ": 9")


@pytest.fixture
def world(tmp_path):
    w = group_world(tmp_path)
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(w["writer"], w["store"], purpose, material=os.urandom(32),
                   prove=lambda m: None, now=NOW)  # fmt: skip
    adapters = Adapters(
        capability={"telegram_user": Provider(S.AVAILABLE)},
        context={"telegram_user": Source()},
    )
    built = build_comms_runtime(w["conn"], w["writer"], w["store"], adapters, clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip
    w["call"] = lambda tool, args: built.dispatcher.call(CLIENT, tool, args)
    return w


def _ok(result):
    assert result.error_code is None, result.error_code
    text = json.dumps(result.structured)
    for identity in IDS:
        assert identity not in text, identity
    return result.structured


def test_invites_by_ref(world):
    (item,) = _ok(world["call"]("comms_group_invite_list", {"group": world["grp"]}))["items"]
    assert item["invite"].startswith("inv_") and item["primary"] is True
    assert item["untrusted"] == {"title": "Main"} and item["usage"] == 2
    again = _ok(world["call"]("comms_group_invite_list", {"group": world["grp"]}))["items"][0]
    assert again["invite"] == item["invite"]  # one ref per link


def test_topics_by_ref_and_one_topic_by_its_ref(world):
    (item,) = _ok(world["call"]("comms_group_topic_list", {"group": world["grp"]}))["items"]
    assert item["topic"].startswith("top_") and item["pinned"] is True
    got = _ok(
        world["call"]("comms_group_topic_get", {"group": world["grp"], "topic": item["topic"]})
    )
    assert got == {"group": world["grp"], "topic": item["topic"], "closed": True,
                   "untrusted": {"name": "Events"}, "next_actions": got["next_actions"]}  # fmt: skip


def test_join_requests_and_admin_log_name_people_by_ref(world):
    (req,) = _ok(world["call"]("comms_group_join_requests_list", {"group": world["grp"]}))["items"]
    assert req["recipient"] == world["rcp"] and req["source"] == "telegram_live"
    (event,) = _ok(world["call"]("comms_group_admin_log", {"group": world["grp"]}))["items"]
    assert event == {"at": "2026-09-25T00:00:00Z",
                     "action": "ChannelAdminLogEventActionChangeTitle", "actor": world["rcp"]}  # fmt: skip


def test_an_unknown_topic_ref_is_not_found(world):
    got = world["call"](
        "comms_group_topic_get", {"group": world["grp"], "topic": "top_" + "a" * 26}
    )
    assert got.error_code == "NOT_FOUND"
