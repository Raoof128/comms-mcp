"""Catalog amendment G8 (part a): WhatsApp group writes and live group reads over the real
adapters and composition, with only Meta's HTTP scripted.

Sends and pins go to ``POST /{phone}/messages`` as a group message; join requests are answered
by Meta's own request id, found by the member's ``wa_id``; participants, join requests and the
one invite link are read live (``whatsapp_live``). A person leaves as their ``rcp_`` ref (or
``null``); no number, ``wa_id`` or group id appears in any output.
"""

import json
import os
from typing import Any

import httpx
import pytest

from comms.core import refs
from comms.core.campaigns import directory as d
from comms.core.groups import group_ref
from comms.core.keys import rotate as rot
from comms.core.providers.capability import CapabilityState as S
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.adapters import Adapters
from comms.runtime.comms_runtime import build_comms_runtime
from comms.transports.whatsapp.cloud.context import WhatsAppContext
from comms.transports.whatsapp.cloud.groups import GroupDiscovery, WhatsAppAdmin
from comms.transports.whatsapp.cloud.http import GraphApi
from comms.transports.whatsapp.numbers import wa_group_id
from comms.transports.whatsapp.webhooks.archive import ArchiveContext, CommsArchive
from tests.core.campaign_helpers import NOW
from tests.services.context_fixtures import Clock
from tests.services.group_fixtures import WA_PHONE, Provider, group_world

CLIENT = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")
GROUP = "Y2FwaV9ncm91cDoxOTUwNTU1MDA3OToxMjAzNjMzOTQzMjAdOTY0MTUZD"
PHONE_ID = "106540352242922"
STRANGER = "61400000099"
IDS = (WA_PHONE[1:], STRANGER, GROUP, PHONE_ID, "JR1", "JR2")


class Token:
    def get(self, item, version):
        return b"EAAB" + b"x" * 40


class Meta:
    """Meta's Graph API, scripted by method and path; every request recorded."""

    def __init__(self):
        self.sent: list[tuple[str, str, Any]] = []
        self.join_requests = [{"join_request_id": "JR1", "wa_id": WA_PHONE[1:],
                               "creation_timestamp": "1758800000"},
                              {"join_request_id": "JR2", "wa_id": STRANGER,
                               "creation_timestamp": "1758800100"}]  # fmt: skip

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path.split("/", 2)[-1]  # drop the version
        self.sent.append((request.method, path, body))
        answer: Any = {"success": True}
        if path.endswith("/groups") and request.method == "GET":
            answer = {"data": [{"id": GROUP}]}
        elif path == GROUP and request.method == "GET":
            answer = {"id": GROUP, "participants": [{"wa_id": WA_PHONE[1:]}, {"wa_id": STRANGER}],
                      "total_participant_count": "2"}  # fmt: skip
        elif path.endswith("/invite_link"):
            answer = {
                "messaging_product": "whatsapp",
                "invite_link": "https://chat.whatsapp.com/Abc",
            }
        elif path.endswith("/join_requests") and request.method == "GET":
            answer = {"data": self.join_requests, "paging": {"cursors": {"after": "c1"}}}
        elif path.endswith("/join_requests"):
            key = "approved_join_requests" if request.method == "POST" else "rejected_join_requests"
            answer = {"messaging_product": "whatsapp", key: body["join_requests"]}
        elif path == f"{PHONE_ID}/groups" and request.method == "POST":
            answer = {"messaging_product": "whatsapp", "request_id": "REQ1"}
        elif path == GROUP and request.method == "DELETE":
            answer = {"success": True}
        elif path.endswith("/messages"):
            answer = {"messaging_product": "whatsapp", "messages": [{"id": "wamid.NEW1"}]}
        return httpx.Response(200, json=answer)


@pytest.fixture
def world(tmp_path):
    w = group_world(tmp_path)
    conn = w["conn"]
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(w["writer"], w["store"], purpose, material=os.urandom(32),
                   prove=lambda m: None, now=NOW)  # fmt: skip
    loc = d.add_location(conn, "WA", now=NOW)
    dst = d.add_destination(conn, loc, "whatsapp", f"group:{GROUP}", "Family",
                            normalize=wa_group_id, now=NOW)  # fmt: skip
    w["wa"] = group_ref(conn, dst, now=NOW)
    webhook = {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "messages", "value": {"messaging_product": "whatsapp",
        "metadata": {"phone_number_id": PHONE_ID}, "contacts": [{"wa_id": WA_PHONE[1:]}],
        "messages": [{"from": WA_PHONE[1:], "id": "wamid.OLD1", "timestamp": "1758800000",
                      "type": "text", "text": {"body": "hi"}, "group_id": GROUP}]}}]}]}  # fmt: skip
    CommsArchive(conn, clock=lambda: NOW).ingest(json.dumps(webhook).encode())
    meta = Meta()
    api = GraphApi(Token(), version=1, phone_number_id=PHONE_ID,
                   transport=httpx.MockTransport(meta.handle))  # fmt: skip
    discovery = GroupDiscovery(api)
    discovery.discover()
    w["loc"] = loc
    adapters = Adapters(
        capability={"whatsapp_cloud": Provider(S.AVAILABLE)},
        admin={"whatsapp_cloud": WhatsAppAdmin(api, discovery)},
        context={
            "whatsapp_cloud": WhatsAppContext(
                ArchiveContext(conn, clock=lambda: NOW), api, clock=lambda: NOW
            )
        },
    )
    built = build_comms_runtime(conn, w["writer"], w["store"], adapters, clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip
    w["meta"] = meta
    w["call"] = lambda tool, args: built.dispatcher.call(CLIENT, tool, args)
    return w


def _ok(result):
    assert result.error_code is None, result.error_code
    text = json.dumps(result.structured)
    for identity in IDS:
        assert identity not in text, identity
    return result.structured


def _write(world, tool, **args):
    return world["call"](tool, {"group": world["wa"], "request_id": refs.mint("request"), **args})


def test_participants_by_ref(world):
    page = _ok(world["call"]("comms_group_members_list", {"group": world["wa"]}))
    assert page["source"] == "whatsapp_live"
    assert [i["recipient"] for i in page["items"]] == [world["rcp"], None]
    got = _ok(
        world["call"]("comms_group_members_get", {"group": world["wa"], "recipient": world["rcp"]})
    )
    assert (got["role"], got["status"]) == ("member", "member")


def test_join_requests_by_ref(world):
    page = _ok(world["call"]("comms_group_join_requests_list", {"group": world["wa"]}))
    assert [(i["source"], i["recipient"]) for i in page["items"]] == [
        ("whatsapp_live", world["rcp"]), ("whatsapp_live", None)]  # fmt: skip
    assert page["items"][0]["requested_at"].startswith("2025-")


def test_the_one_invite_link_by_ref(world):
    (item,) = _ok(world["call"]("comms_group_invite_list", {"group": world["wa"]}))["items"]
    assert item["invite"].startswith("inv_") and item["primary"] is True and item["usage"] is None
    invited = _ok(_write(world, "comms_group_member_invite", recipient=world["rcp"]))
    assert invited["invite"] == item["invite"] and invited["result"] == "SUCCEEDED"


def test_a_group_send_is_a_group_message(world):
    got = _ok(_write(world, "comms_message_send", text="salaam"))
    assert got["result"] == "SUCCEEDED" and got["message"].startswith("cmg_")
    (method, path, body) = world["meta"].sent[-1]
    assert (method, path) == ("POST", f"{PHONE_ID}/messages")
    assert body == {"messaging_product": "whatsapp", "recipient_type": "group", "to": GROUP,
                    "type": "text", "text": {"body": "salaam"}}  # fmt: skip


def test_pins_carry_their_days(world):
    first = world["call"]("comms_context_recent", {"group": world["wa"], "limit": 1})
    message = first.structured["items"][0]["message_ref"]
    for extra, expected in (({}, 30), ({"expire_days": 7}, 7)):
        assert (
            _ok(_write(world, "comms_message_pin", message=message, **extra))["result"]
            == "SUCCEEDED"
        )
        pin = world["meta"].sent[-1][2]["pin"]
        assert pin == {"type": "pin", "message_id": "wamid.OLD1", "expiration_days": expected}
    _ok(_write(world, "comms_message_unpin", message=message))
    assert world["meta"].sent[-1][2]["pin"] == {"type": "unpin", "message_id": "wamid.OLD1"}
    bad = _write(world, "comms_message_pin", message=message, expire_days=31)
    assert bad.error_code == "INVALID_ARGUMENT"


def test_join_requests_are_answered_by_metas_own_id(world):
    got = _ok(_write(world, "comms_group_join_requests_approve", recipient=world["rcp"]))
    assert got["result"] == "SUCCEEDED"
    assert world["meta"].sent[-1] == ("POST", f"{GROUP}/join_requests",
                                      {"messaging_product": "whatsapp", "join_requests": ["JR1"]})  # fmt: skip
    _ok(_write(world, "comms_group_join_requests_reject", recipient=world["rcp"]))
    assert world["meta"].sent[-1][0] == "DELETE"
    world["meta"].join_requests = []
    none = _ok(_write(world, "comms_group_join_requests_approve", recipient=world["rcp"]))
    assert (none["result"], none["code"]) == ("FAILED", "TARGET_NOT_FOUND")


def test_the_groups_api_has_no_roles(world):
    got = world["call"]("comms_group_admins_list", {"group": world["wa"]})
    assert got.error_code == "PROVIDER_UNSUPPORTED"


# -- G8 part b: create (asynchronous, settled by Meta's webhook) and delete ----------------------

NEW = "Y2FwaV9ncm91cDpORVdHUk9VUDEyMzQ1Njc4OQ"


def _lifecycle(request_id, group_id=None, errors=None):
    event = {"timestamp": "1790000000", "type": "group_create", "request_id": request_id,
             "subject": "Families"}  # fmt: skip
    if group_id:
        event["group_id"] = group_id
    if errors:
        event["errors"] = errors
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "waba",
        "changes": [{"field": "group_lifecycle_update", "value": {"messaging_product": "whatsapp",
        "groups": [event]}}]}]}).encode()  # fmt: skip


def _groups(conn):
    return dict(conn.execute(
        "SELECT d.platform_identity, g.ref FROM groups g JOIN destinations d"
        " ON d.id = g.destination_id").fetchall())  # fmt: skip


def test_a_whatsapp_group_is_filed_when_metas_webhook_names_it(world):
    got = _ok(world["call"]("comms_group_create", {"location": world["loc"], "title": "Families",
                            "kind": "supergroup", "request_id": refs.mint("request")}))  # fmt: skip
    assert (got["result"], got["group"]) == ("SUCCEEDED", None)  # Meta creates asynchronously
    assert world["meta"].sent[-1] == ("POST", f"{PHONE_ID}/groups",
                                      {"messaging_product": "whatsapp", "subject": "Families"})  # fmt: skip
    conn = world["conn"]
    CommsArchive(conn, clock=lambda: NOW).ingest(_lifecycle("REQ-unknown", NEW))
    assert f"group:{NEW}" not in _groups(conn)  # a request this installation never made
    CommsArchive(conn, clock=lambda: NOW).ingest(_lifecycle("REQ1", NEW))
    grp = _groups(conn)[f"group:{NEW}"]
    assert grp.startswith("grp_")
    CommsArchive(conn, clock=lambda: NOW).ingest(_lifecycle("REQ1", NEW))  # a redelivery
    assert list(_groups(conn)).count(f"group:{NEW}") == 1
    listed = _ok(world["call"]("comms_group_get", {"group": grp}))
    assert (listed["name"], listed["location"]) == ("Families", world["loc"])


def test_a_failed_creation_is_marked_and_files_nothing(world):
    _ok(world["call"]("comms_group_create", {"location": world["loc"], "title": "Nope",
                      "kind": "supergroup", "request_id": refs.mint("request")}))  # fmt: skip
    conn = world["conn"]
    CommsArchive(conn, clock=lambda: NOW).ingest(
        _lifecycle("REQ1", NEW, errors=[{"code": 131000, "title": "x"}]))  # fmt: skip
    assert f"group:{NEW}" not in _groups(conn)
    row = conn.execute("SELECT failed_at, destination_id FROM pending_group_creations").fetchone()
    assert row[0] is not None and row[1] is None


def test_delete_asks_meta(world):
    got = _ok(_write(world, "comms_group_delete"))
    assert got["result"] == "SUCCEEDED" and world["meta"].sent[-1][:2] == ("DELETE", GROUP)


def test_with_both_platforms_a_create_must_say_which(tmp_path):
    from tests.services.group_fixtures import fixtures

    w = group_world(tmp_path)
    _cap, _ex, admins = fixtures(w)
    adapters = Adapters(
        capability={a: Provider(S.AVAILABLE) for a in ("telegram_user", "whatsapp_cloud")},
        admin={a: admins[a] for a in ("telegram_user", "whatsapp_cloud")},
    )
    built = build_comms_runtime(w["conn"], w["writer"], w["store"], adapters, clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip
    loc = d.add_location(w["conn"], "Both", now=NOW)
    args = {"location": loc, "title": "T", "kind": "supergroup", "request_id": refs.mint("request")}
    assert (
        built.dispatcher.call(CLIENT, "comms_group_create", args).error_code == "AMBIGUOUS_TARGET"
    )
    assert admins["telegram_user"].calls == admins["whatsapp_cloud"].calls == []
    chosen = built.dispatcher.call(CLIENT, "comms_group_create", {**args, "actor": "telegram_user",
                                   "request_id": refs.mint("request")})  # fmt: skip
    assert chosen.error_code is None and [c for c, _a in admins["telegram_user"].calls]
