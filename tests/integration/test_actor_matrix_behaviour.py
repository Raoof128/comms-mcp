"""Catalog amendment G6a gauntlet: the actor matrix, proved by behaviour.

Every matrix tool goes through the real dispatcher, facades, services, executor and the real
adapters' validation, once per Telegram actor with only that actor configured. The bot's context
is the real ``BotContext`` over a scripted Bot API. ``A done`` must succeed; ``B`` and ``A todo``
must be refused with no provider call (``B`` as ``PROVIDER_UNSUPPORTED``, or ``NOT_CONFIGURED``
when the only capable actor is the other, unconfigured one). ``—`` cells are not addressed to the
actor. WhatsApp cells are proved from G1 on, when WhatsApp groups become destinations.
"""

import json
import os
import re
from typing import Any

import httpx
import pytest

from comms.core import refs
from comms.core.delivery.commitment import commit_context
from comms.core.keys import rotate as rot
from comms.core.providers.capability import CapabilityState as S
from comms.mcp.dispatch import AuthenticatedClient, Dispatcher
from comms.runtime.facades import Services, build_registry
from comms.runtime.selftest import _OneSecret
from comms.services.account import AccountService
from comms.services.campaigns import CampaignService
from comms.services.context import ContextEngine
from comms.services.directory import DirectoryService
from comms.services.groups import GroupService
from comms.services.handles import ContextHandles
from comms.services.identity import IdentityService
from comms.services.messages import MessageService
from comms.transports.telegram.bot.context import BotContext
from comms.transports.telegram.bot.http import BotApi
from comms.transports.telegram.bot.updates import BotPoller
from tests.core import fakes
from tests.core.campaign_helpers import NOW
from tests.core.providers.test_actor_matrix import CATALOG, _rows
from tests.services.context_fixtures import Clock, Source
from tests.services.group_fixtures import fixtures, group_world
from tests.services.test_templates_media_account import WebhookState

CLIENT = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")
TELEGRAM = ("telegram_bot", "telegram_user")
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
            result = {"id": -77, "type": "group", "title": "G"}
        elif method == "getChatAdministrators":
            result = []
        elif method == "getChatMemberCount":
            result = 3
        else:
            result = True
        return httpx.Response(200, json={"ok": True, "result": result})

    store: Any = _OneSecret()
    return BotApi(store, version=1, transport=httpx.MockTransport(handle))


def _world(actor, tmp_path):
    from comms.mcp.catalog import TOOL_CATALOG

    w = group_world(tmp_path)
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(
            w["writer"], w["store"], purpose, material=os.urandom(32), prove=lambda m: None, now=NOW
        )
    other = "telegram_user" if actor == "telegram_bot" else "telegram_bot"
    states = {actor: S.AVAILABLE, other: S.NOT_CONFIGURED, "whatsapp_cloud": S.NOT_CONFIGURED}
    capability, executor, admins = fixtures(w, states=states)
    conn = w["conn"]
    if actor == "telegram_bot":
        api = _bot_api()
        BotPoller(api, conn, clock=lambda: NOW).poll_once()
        source: Any = BotContext(api, conn, clock=lambda: NOW)
    else:
        source = Source(provenance="telegram_live")
    services = Services(
        conn=conn, capability=capability,
        context=ContextEngine(conn, {actor: source}, clock=lambda: NOW, monotonic=Clock(), capability=capability),
        handles=ContextHandles(conn, w["store"], clock=lambda: NOW),
        groups=GroupService(conn, capability, executor), messages=MessageService(conn, capability, executor),
        campaigns=CampaignService(w["writer"], executor, {"whatsapp": fakes.FakeWhatsApp(conn=conn)},
                                  commit=lambda: commit_context(w["writer"], w["store"])),
        directory=DirectoryService(w["writer"], executor), templates=None, media=None,
        account=AccountService(capability, webhooks=WebhookState()), identity=IdentityService(conn),
        actors=(actor,),
    )  # fmt: skip
    dispatcher = Dispatcher(build_registry(services))
    specs = {spec.name: spec for spec in TOOL_CATALOG}
    return w, dispatcher, admins[actor], specs


def _fresh(dispatcher, name, w, actor):
    created = dispatcher.call(CLIENT, name, {"group": w["grp"], "actor": actor, "name": "T",
                                             "request_id": refs.mint("request")})  # fmt: skip
    assert created.error_code is None, (name, created.error_code)
    return created.structured["object"]


def _arguments(spec, w, actor, dispatcher, message, cursor):
    """Realistic arguments: fresh objects for the tools that act on one."""
    values = {
        "group": w["grp"], "groups": [w["grp"]], "recipient": w["rcp"], "message": message,
        "to_group": w["grp"], "text": "hi", "title": "T", "name": "renamed", "kind": "supergroup",
        "location": "loc_" + "a" * 26, "profile": "moderator", "actor": actor, "description": "d",
        "permissions": {"can_send_messages": True}, "conversation": w["rcp"],
        "media": "med_" + "a" * 26, "file": "f", "mime": "image/png", "query": "hello",
        "scope": "everyone", "rights": {"can_pin_messages": True}, "cursor": cursor,
        "capability": "member.ban",
    }  # fmt: skip
    required = set(spec.input_schema.get("required", ()))
    properties = spec.input_schema.get("properties", {})
    if "invite" in properties:  # revoke takes one optionally (with none: G6's primary-link reset)
        required.add("invite")
    if "invite" in required:
        values["invite"] = _fresh(dispatcher, "comms_group_invite_create", w, actor)
    if "topic" in required:
        values["topic"] = _fresh(dispatcher, "comms_group_topic_create", w, actor)
    arguments = {k: values[k] for k in required if values.get(k) is not None}
    if spec.name.endswith("_edit") and "name" in spec.input_schema.get("properties", {}):
        arguments["name"] = "renamed"  # an edit must change something
    if spec.requires_request_id:
        arguments["request_id"] = refs.mint("request")
    return arguments


@pytest.mark.parametrize("actor", TELEGRAM)
def test_every_telegram_cell_behaves_as_the_matrix_says(actor, tmp_path):
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
            refused_right = result.error_code in ("PROVIDER_UNSUPPORTED", "NOT_CONFIGURED")
            ok = (
                (kind == "A done" and result.error_code is None)
                or (kind == "B" and refused_right and not reached)
                or (kind == "A todo" and result.error_code is not None and not reached)
            )
            if not ok:
                wrong.append((name, kind, result.error_code, reached))
    assert wrong == [], wrong
