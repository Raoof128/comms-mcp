"""Catalog amendment G5 (spec A45): ``comms_context_person`` — one person's communication.

Sections, each a context page with its provenance: the WhatsApp direct-message archive, the
Telegram private chat (live through the user account when it can read it, else the bot's retained
updates), and the campaign history per transport. With ``include_group_activity`` the person's
messages in the directory's groups are added, one section per group, from the local sources. The
person is named by ``rcp_`` ref only; numbers and user ids never appear. Every section pages
through ``comms_context_page`` with a client-bound ``cur_`` token.
"""

import json
import os
from typing import Any

import httpx
import pytest

from comms.core.campaigns import directory as d
from comms.core.delivery import freeze
from comms.core.groups import group_ref
from comms.core.keys import rotate as rot
from comms.core.providers.capability import CapabilityState as S
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.adapters import Adapters
from comms.runtime.comms_runtime import build_comms_runtime
from comms.runtime.selftest import _OneSecret
from comms.transports.telegram.bot.context import BotContext
from comms.transports.telegram.bot.http import BotApi
from comms.transports.telegram.bot.updates import BotPoller
from comms.transports.whatsapp.numbers import wa_group_id
from comms.transports.whatsapp.webhooks.archive import ArchiveContext, CommsArchive
from tests.core import fakes
from tests.core.campaign_helpers import NOW, ready
from tests.services.context_fixtures import Clock
from tests.services.group_fixtures import TG_USER, WA_PHONE, Provider, group_world

CLIENT = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")
OTHER = AuthenticatedClient(client_ref="cli_" + "b" * 26, auth_kind="cml1")
WA_GROUP = "Y2FwaV9ncm91cDoxOTUwNTU1MDA3OToxMjAzNjMzOTQzMjAdOTY0MTUZD"
IDENTITIES = (WA_PHONE[1:], TG_USER, WA_GROUP, "-77")


def _update(n, chat, sender, text):
    kind = "private" if chat > 0 else "group"
    return {"update_id": n, "message": {"message_id": 100 + n, "date": 1758800000 + n,
            "chat": {"id": chat, "type": kind}, "from": {"id": sender, "is_bot": False,
            "first_name": "S"}, "text": text}}  # fmt: skip


UPDATES = [
    _update(1, int(TG_USER), int(TG_USER), "tg dm one"),
    _update(2, int(TG_USER), int(TG_USER), "tg dm two"),
    _update(3, -77, int(TG_USER), "tg in the group"),
    _update(4, -77, 42, "someone else"),
]


def _bot_api():
    def handle(request: Any) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getUpdates":
            offset = int(json.loads(request.content or b"{}").get("offset") or 0)
            result: Any = [u for u in UPDATES if u["update_id"] >= offset]
        else:
            result = True
        return httpx.Response(200, json={"ok": True, "result": result})

    return BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle))


def _webhook():
    def message(wamid, text, ts, sender, group=None):
        body = {"from": sender, "id": wamid, "timestamp": str(ts), "type": "text",
                "text": {"body": text}}  # fmt: skip
        return {**body, "group_id": group} if group else body

    messages = [
        message("wamid.D1", "salaam dm", 1758800001, WA_PHONE[1:]),
        message("wamid.G1", "wa in the group", 1758800002, WA_PHONE[1:], WA_GROUP),
        message("wamid.G2", "not them", 1758800003, "61400000099", WA_GROUP),
    ]
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp", "metadata": {"phone_number_id": "1234567890"},
            "contacts": [{"wa_id": WA_PHONE[1:], "profile": {"name": "Ali"}}],
            "messages": messages}}]}]}).encode()  # fmt: skip


@pytest.fixture
def world(tmp_path):
    w = group_world(tmp_path)
    conn = w["conn"]
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(w["writer"], w["store"], purpose, material=os.urandom(32),
                   prove=lambda m: None, now=NOW)  # fmt: skip
    loc = d.add_location(conn, "WA", now=NOW)
    wa_dst = d.add_destination(conn, loc, "whatsapp", f"group:{WA_GROUP}", "Family",
                               normalize=wa_group_id, now=NOW)  # fmt: skip
    w["wa_grp"] = group_ref(conn, wa_dst, now=NOW)
    CommsArchive(conn, clock=lambda: NOW).ingest(_webhook())
    api = _bot_api()
    BotPoller(api, conn, clock=lambda: NOW).poll_once()
    cmp = ready(conn, {"recipients": [w["rcp"]]})
    freeze.send(conn, cmp, {"whatsapp": fakes.FakeWhatsApp(conn=conn)}, now=NOW)
    adapters = Adapters(
        capability={a: Provider(S.AVAILABLE) for a in ("telegram_bot", "whatsapp_cloud")},
        context={
            "telegram_bot": BotContext(api, conn, clock=lambda: NOW),
            "whatsapp_cloud": ArchiveContext(conn, clock=lambda: NOW),
        },
    )
    built = build_comms_runtime(conn, w["writer"], w["store"], adapters, clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip
    w["call"] = lambda args, client=CLIENT, tool="comms_context_person": built.dispatcher.call(
        client, tool, args
    )
    return w


def _sections(result):
    assert result.error_code is None, result.error_code
    return {
        s["section"]: (s["source"], [i.get("untrusted_text") for i in s["items"]])
        for s in result.structured["sections"]
    }


def test_a_persons_direct_communication_by_source(world):
    got = world["call"]({"recipient": world["rcp"]})
    assert _sections(got) == {
        "whatsapp": ("whatsapp_webhook_archive", ["salaam dm"]),
        "telegram": ("telegram_local", ["tg dm two", "tg dm one"]),
        "campaigns:whatsapp": ("campaign_store", [None]),
        "campaigns:telegram": ("campaign_store", []),
    }
    assert all(
        i["group_ref"] == world["rcp"] for s in got.structured["sections"] for i in s["items"]
    )


def test_no_number_or_user_id_ever_appears(world):
    got = world["call"]({"recipient": world["rcp"], "include_group_activity": True})
    text = json.dumps(got.structured)
    for identity in IDENTITIES:
        assert identity not in text, identity


def test_group_activity_only_when_asked_and_only_the_persons_messages(world):
    assert not any(
        k.startswith("groups:") for k in _sections(world["call"]({"recipient": world["rcp"]}))
    )
    got = _sections(world["call"]({"recipient": world["rcp"], "include_group_activity": True}))
    assert got[f"groups:{world['wa_grp']}"] == ("whatsapp_webhook_archive", ["wa in the group"])
    assert got[f"groups:{world['grp']}"] == ("telegram_local", ["tg in the group"])


def test_a_transport_filter_and_a_missing_contact_point(world):
    got = _sections(world["call"]({"recipient": world["rcp"], "transports": ["telegram"]}))
    assert set(got) == {"telegram", "campaigns:telegram"}
    bare = d.add_recipient(world["conn"], now=NOW, display_name="Nobody")
    missing = world["call"]({"recipient": bare, "transports": ["whatsapp"]})
    assert missing.error_code == "NOT_FOUND"
    assert world["call"]({"recipient": "rcp_" + "a" * 26}).error_code == "NOT_FOUND"


def test_each_section_pages_through_a_client_bound_cursor(world):
    got = world["call"]({"recipient": world["rcp"], "transports": ["telegram"], "limit": 1})
    (telegram,) = [s for s in got.structured["sections"] if s["section"] == "telegram"]
    assert [i["untrusted_text"] for i in telegram["items"]] == ["tg dm two"]
    cursor = telegram["next_cursor"]
    assert cursor.startswith("cur_")
    more = world["call"]({"cursor": cursor}, tool="comms_context_page")
    assert more.error_code is None, more.error_code
    assert [i["untrusted_text"] for i in more.structured["items"]] == ["tg dm one"]
    assert world["call"]({"cursor": cursor}, client=OTHER, tool="comms_context_page").error_code


def test_the_output_matches_its_schema(world):
    from comms.mcp.tools.context import CONTEXT_PERSON_TOOLS
    from tests.mcp import family

    (spec,) = CONTEXT_PERSON_TOOLS
    family.schema_valid(spec)
    family.annotations(spec)
    got = world["call"]({"recipient": world["rcp"], "include_group_activity": True, "limit": 1})
    family.output_matches(spec, got.structured)
