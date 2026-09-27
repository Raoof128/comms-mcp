"""Catalog amendment G8 (part c) and spec A46: account profile, phone status and messaging health.

Each account shows what it calls itself (the bot's and the user's name, the WhatsApp business
profile), untrusted, and never an identity: no username, user id, phone number or WABA id. The
phone status and the health status come from the Graph API; health drops every entity id.
"""

import asyncio
import json
import os

import httpx

from comms.core.keys import rotate as rot
from comms.core.providers.capability import CapabilityState as S
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.adapters import Adapters
from comms.runtime.comms_runtime import build_comms_runtime
from comms.runtime.selftest import _OneSecret
from comms.transports.profiles import bot_profile, user_profile, whatsapp_profile
from comms.transports.telegram.bot.http import BotApi
from comms.transports.whatsapp.cloud.account import WhatsAppCapability, health_of
from comms.transports.whatsapp.cloud.groups import GroupDiscovery
from tests.conformance.meta_oracle import PHONE_ID, WABA_ID, oracle
from tests.conformance.test_meta_oracle import _api
from tests.core.campaign_helpers import NOW
from tests.services.context_fixtures import Clock
from tests.services.group_fixtures import Provider, group_world

CLIENT = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")


def test_the_bots_name_without_its_username():
    def handle(request):
        return httpx.Response(200, json={"ok": True, "result": {
            "id": 7788, "is_bot": True, "first_name": "Comms", "username": "comms_owner_bot"}})  # fmt: skip

    read = bot_profile(BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle)))
    got = read()
    assert got == {"kind": "bot", "reachable": True, "untrusted": {"name": "Comms"}}
    assert "comms_owner_bot" not in json.dumps(got) and "7788" not in json.dumps(got)


def test_the_user_accounts_name():
    class Session:
        async def own_name(self, deadline):
            return "Raouf R"

    got = user_profile(Session(), asyncio.run)()
    assert got == {"kind": "user", "reachable": True, "untrusted": {"name": "Raouf R"}}


def test_the_whatsapp_business_profile():
    got = whatsapp_profile(_api(oracle()))()
    assert got["reachable"] is True
    assert got["untrusted"] == {"about": "Succulent specialists!", "description": None,
                                "vertical": "RETAIL"}  # fmt: skip


def _runtime(tmp_path):
    w = group_world(tmp_path)
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(w["writer"], w["store"], purpose, material=os.urandom(32),
                   prove=lambda m: None, now=NOW)  # fmt: skip
    graph = oracle()
    api = _api(graph)
    capability = WhatsAppCapability(api, GroupDiscovery(api), clock=lambda: NOW)
    adapters = Adapters(
        capability={"whatsapp_cloud": Provider(S.AVAILABLE)},
        admin={"whatsapp_cloud": object()},
        profiles={"whatsapp_cloud": whatsapp_profile(api)},
        phone=capability.inspect_phone,
        health=health_of(api),
    )
    built = build_comms_runtime(w["conn"], w["writer"], w["store"], adapters, clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip
    return lambda tool: built.dispatcher.call(CLIENT, tool, {})


def _clean(result):
    assert result.error_code is None, result.error_code
    text = json.dumps(result.structured)
    for identity in (PHONE_ID, WABA_ID, "61400000001"):
        assert identity not in text, identity
    return result.structured


def test_the_profile_through_the_dispatcher(tmp_path):
    actors = _clean(_runtime(tmp_path)("comms_account_profile"))["actors"]
    assert actors["whatsapp_cloud"]["configured"] and actors["whatsapp_cloud"]["reachable"]
    assert actors["whatsapp_cloud"]["untrusted"]["about"] == "Succulent specialists!"
    assert actors["telegram_bot"] == {"configured": False, "kind": "bot", "reachable": None,
                                      "untrusted": {}}  # fmt: skip


def test_phone_status_and_health_without_ids(tmp_path):
    call = _runtime(tmp_path)
    status = _clean(call("comms_whatsapp_phone_status"))
    assert status["status"] == "CONNECTED"
    health = _clean(call("comms_whatsapp_health_status"))
    assert health["can_send_message"] == "AVAILABLE"
    assert [e["entity_type"] for e in health["entities"]] == ["PHONE_NUMBER", "WABA"]


def test_without_whatsapp_the_health_is_not_configured(tmp_path):
    w = group_world(tmp_path)
    built = build_comms_runtime(w["conn"], w["writer"], w["store"], Adapters(), clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip
    got = built.dispatcher.call(CLIENT, "comms_whatsapp_health_status", {})
    assert got.error_code == "NOT_CONFIGURED"
