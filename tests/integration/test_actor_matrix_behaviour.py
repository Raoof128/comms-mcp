"""Catalog amendment G6a gauntlet: the actor matrix, proved by behaviour.

Every matrix tool goes through the real dispatcher, facades, services, executor and the real
adapters' validation, once per actor with only that actor configured. The bot's context
is the real ``BotContext`` over a scripted Bot API. ``A done`` must succeed; ``B`` and ``A todo``
must be refused with no provider call (``B`` as ``PROVIDER_UNSUPPORTED``, or ``NOT_CONFIGURED``
when the only capable actor is the other, unconfigured one). ``—`` cells are not addressed to the
actor. From G1 the WhatsApp column is proved the same way: its group is a WhatsApp group read from
the real archive, and its account tools run through the real template and media services.
"""

import json
import os
import re
from typing import Any

import httpx
import pytest

from comms.core import refs
from comms.core.campaigns import directory as d
from comms.core.groups import group_ref
from comms.core.keys import rotate as rot
from comms.core.objects import object_ref
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import ProviderTarget
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.adapters import Adapters
from comms.runtime.comms_runtime import build_comms_runtime
from comms.runtime.selftest import _OneSecret
from comms.transports.telegram.bot.context import BotContext
from comms.transports.telegram.bot.http import BotApi
from comms.transports.telegram.bot.updates import BotPoller
from comms.transports.whatsapp.cloud.context import WhatsAppContext
from comms.transports.whatsapp.cloud.http import GraphApi
from comms.transports.whatsapp.numbers import wa_group_id
from comms.transports.whatsapp.webhooks.archive import ArchiveContext, CommsArchive
from tests.core import fakes
from tests.core.campaign_helpers import NOW
from tests.core.providers.test_actor_matrix import CATALOG, _rows
from tests.runtime.test_whatsapp_groups_live import Meta, Token
from tests.services.context_fixtures import Clock, Source
from tests.services.group_fixtures import WA_PHONE, Provider, fixtures, group_world
from tests.services.test_templates_media_account import ACCOUNT, Media, Templates

CLIENT = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")
ACTORS = ("telegram_bot", "telegram_user", "whatsapp_cloud")
WA_GROUP = "Y2FwaV9ncm91cDoxOTUwNTU1MDA3OToxMjAzNjMzOTQzMjAdOTY0MTUZD"
SPECS = {name: spec for name, spec in CATALOG.items()} if isinstance(CATALOG, dict) else None


def _bot_api() -> BotApi:
    def handle(request: Any) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getUpdates":
            offset = int(json.loads(request.content or b"{}").get("offset") or 0)
            result: Any = [
                {"update_id": n, "message": {"message_id": 100 + n, "date": 1758800000 + n,
                 "chat": {"id": -77, "type": "group", "title": "G"},
                 "from": {"id": 42, "is_bot": False, "first_name": "S"}, "text": f"u{n}"}}
                for n in (1, 2, 3) if n >= offset
            ]  # fmt: skip
        elif method == "getChat":
            result = {
                "id": -77,
                "type": "group",
                "title": "G",
                "permissions": {"can_send_messages": True, "can_pin_messages": False},
            }
        elif method == "getChatMember":
            result = {
                "status": "member",
                "user": {"id": 908180, "is_bot": False, "first_name": "A"},
            }
        elif method == "getChatAdministrators":
            result = []
        elif method == "getChatMemberCount":
            result = 3
        else:
            result = True
        return httpx.Response(200, json={"ok": True, "result": result})

    store: Any = _OneSecret()
    return BotApi(store, version=1, transport=httpx.MockTransport(handle))


def _group_webhook() -> bytes:
    messages = [
        {"from": "61400000001", "id": f"wamid.G{n}", "timestamp": str(1758800000 + n),
         "type": "text", "text": {"body": f"w{n}"}, "group_id": WA_GROUP}
        for n in (1, 2, 3)
    ] + [{"from": "61400000001", "id": "wamid.D1", "timestamp": "1758800009", "type": "text",
          "text": {"body": "dm"}}]  # fmt: skip
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp", "metadata": {"phone_number_id": "1234567890"},
            "contacts": [{"wa_id": "61400000001", "profile": {"name": "S"}}],
            "messages": messages}}]}]}).encode()  # fmt: skip


def _world(actor, tmp_path):
    from comms.mcp.catalog import TOOL_CATALOG

    w = group_world(tmp_path)
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(
            w["writer"], w["store"], purpose, material=os.urandom(32), prove=lambda m: None, now=NOW
        )
    states = dict.fromkeys(ACTORS, S.NOT_CONFIGURED) | {actor: S.AVAILABLE}
    _capability, _executor, admins = fixtures(w, states=states)
    conn = w["conn"]
    w["loc"] = d.add_location(conn, "Real", now=NOW)  # G7: group.create checks it first
    if actor == "whatsapp_cloud":  # its group is a WhatsApp group, read from the archive (G1)
        loc = d.add_location(conn, "WA", now=NOW)
        dst = d.add_destination(
            conn, loc, "whatsapp", f"group:{WA_GROUP}", "W", normalize=wa_group_id, now=NOW
        )
        w["grp"] = group_ref(conn, dst, now=NOW)
        CommsArchive(conn, clock=lambda: NOW).ingest(_group_webhook())
        graph = GraphApi(
            Token(), version=1, phone_number_id="106540352242922",
            transport=httpx.MockTransport(Meta().handle),
        )  # fmt: skip
        # G8: group facts live from a scripted Groups API, messages from the archive
        source: Any = WhatsAppContext(
            ArchiveContext(conn, clock=lambda: NOW), graph, clock=lambda: NOW
        )
    elif actor == "telegram_bot":
        api = _bot_api()
        BotPoller(api, conn, clock=lambda: NOW).poll_once()
        source = BotContext(api, conn, clock=lambda: NOW)
    else:
        source = Source(provenance="telegram_live")
    adapters = Adapters(
        delivery={"whatsapp": fakes.FakeWhatsApp(conn=conn)},
        capability={a: Provider(states[a]) for a in ACTORS},
        admin={actor: admins[actor]},  # only this actor is configured
        context={actor: source},
    )
    adapters.profiles[actor] = lambda: {"reachable": True, "untrusted": {"name": "N"}}  # G8
    if actor == "whatsapp_cloud":  # the account tools run through the real services too
        adapters.templates, adapters.media, adapters.account = Templates(), Media(), ACCOUNT
        adapters.phone = lambda: {"quality_rating": "GREEN", "status": "CONNECTED"}
        adapters.health = lambda: {"can_send_message": "AVAILABLE", "entities": [],
                                   "untrusted": {"notes": []}}  # fmt: skip
    # the one composition root the daemon uses (G2 found hand-built services hid its gaps)
    built = build_comms_runtime(
        conn, w["writer"], w["store"], adapters, clock=lambda: NOW, monotonic=Clock(),
        host="127.0.0.1", local_port=8765,
    )  # fmt: skip
    assert built.services.actors == (actor,)
    if actor == "whatsapp_cloud":
        w["media"] = object_ref(conn, "media", "whatsapp", "whatsapp_cloud", None, "7788990011",
                                now=NOW)  # fmt: skip
        dm = ProviderTarget("whatsapp", "whatsapp_cloud", w["rcp"], WA_PHONE)
        page = built.services.context.archive(w["rcp"], dm, limit=1)
        w["dm_message"] = page["items"][0]["message_ref"]
    dispatcher = built.dispatcher
    specs = {spec.name: spec for spec in TOOL_CATALOG}
    return w, dispatcher, admins[actor], specs


def _fresh(dispatcher, name, w, actor, kind):
    """A fresh object for a tool that acts on one; an unknown ref where the actor cannot create
    it (a WhatsApp topic), since that tool's cell is B and must refuse anyway."""
    created = dispatcher.call(CLIENT, name, {"group": w["grp"], "actor": actor, "name": "T",
                                             "request_id": refs.mint("request")})  # fmt: skip
    if actor == "whatsapp_cloud" and created.error_code == "PROVIDER_UNSUPPORTED":
        return refs.mint(kind)
    assert created.error_code is None, (name, created.error_code)
    return created.structured["object"]


def _arguments(spec, w, actor, dispatcher, message, cursor):
    """Realistic arguments: fresh objects for the tools that act on one."""
    values = {
        "group": w["grp"], "groups": [w["grp"]], "recipient": w["rcp"], "message": message,
        "to_group": w["grp"], "text": "hi", "title": "T", "name": "renamed", "kind": "supergroup",
        "location": w["loc"], "profile": "moderator", "actor": actor, "description": "d",
        "permissions": {"can_send_messages": True}, "conversation": w["rcp"],
        "media": "med_" + "a" * 26, "file": "f", "mime": "image/png", "query": "hello",
        "scope": "everyone", "rights": {"can_pin_messages": True}, "cursor": cursor,
        "capability": "member.ban", "tag": "vip", "language": "en", "category": "MARKETING",
        "components": [{"type": "BODY", "text": "Hi"}],
    }  # fmt: skip
    if actor == "whatsapp_cloud":
        values.update(media=w["media"])
        if spec.name == "comms_message_mark_read":  # conversation-addressed: a direct message
            values.update(message=w["dm_message"])
        if spec.name.startswith("comms_whatsapp_template_"):
            values.update(name="spring")  # the one template the source double holds
    required = set(spec.input_schema.get("required", ()))
    properties = spec.input_schema.get("properties", {})
    # revoke takes an invite optionally: Telegram revokes the one it names (with none: G6's
    # primary-link reset); WhatsApp has one link per group and only resets it
    if "invite" in properties and actor != "whatsapp_cloud":
        required.add("invite")
    if "invite" in required:
        values["invite"] = _fresh(dispatcher, "comms_group_invite_create", w, actor, "invite")
    if "template" in required:
        created = dispatcher.call(CLIENT, "comms_whatsapp_template_create", {
            "name": "fresh", "language": "en", "category": "MARKETING",
            "components": values["components"], "request_id": refs.mint("request")})  # fmt: skip
        assert created.error_code is None, created.error_code
        values["template"] = created.structured["template"]
    if "topic" in required:
        values["topic"] = _fresh(dispatcher, "comms_group_topic_create", w, actor, "topic")
    arguments = {k: values[k] for k in required if values.get(k) is not None}
    if spec.name.endswith("_edit") and "name" in spec.input_schema.get("properties", {}):
        arguments["name"] = "renamed"  # an edit must change something
    if spec.name in ("comms_group_info_set_photo", "comms_media_upload"):  # G8: staged bytes
        arguments.update(data_b64="/9j/4AAQ", mime="image/jpeg")
    if spec.requires_request_id:
        arguments["request_id"] = refs.mint("request")
    return arguments


@pytest.mark.parametrize("actor", ACTORS)
def test_every_cell_behaves_as_the_matrix_says(actor, tmp_path):
    w, dispatcher, admin, specs = _world(actor, tmp_path)
    first = dispatcher.call(CLIENT, "comms_context_recent", {"group": w["grp"], "limit": 2})
    assert first.error_code is None
    message = first.structured["items"][0]["message_ref"]
    cursor = first.structured["next_cursor"]
    wrong = []
    for names, cells in _rows(variants=False):
        cell = cells[actor]
        if cell.startswith("—"):
            continue
        kind = re.match(r"A done|A todo|B", cell).group(0)
        for name in sorted(names):
            spec = specs[name]
            arguments = _arguments(spec, w, actor, dispatcher, message, cursor)
            before = len(admin.calls)  # after any object the arguments needed was created
            result = dispatcher.call(CLIENT, name, arguments)
            reached = len(admin.calls) > before
            refused_right = result.error_code in ("PROVIDER_UNSUPPORTED", "NOT_CONFIGURED") or (
                result.error_code is None  # P §25: a WhatsApp add answers "invite instead"
                and result.structured.get("result") == "INVITE_REQUIRED"
            )
            ok = (
                (kind == "A done" and result.error_code is None)
                or (kind == "B" and refused_right and not reached)
                or (kind == "A todo" and result.error_code is not None and not reached)
            )
            if not ok:
                wrong.append((name, kind, result.error_code, reached))
    assert wrong == [], wrong
