"""Catalog amendment G6: ``comms_group_invite_revoke`` with no invite resets the primary link on
both Telegram APIs (``group.invite.reset``), returning the new link's ``inv_`` ref, as WhatsApp's
reset does. With an invite named it still revokes that one link."""

import json

import httpx
import pytest
from telethon.tl import types

from comms.core import refs
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderTarget, SemanticOperation
from comms.core.providers.semantics import SEMANTICS, SUPPORT
from comms.runtime.selftest import _OneSecret
from comms.transports.telegram.bot.admin import BotAdmin
from comms.transports.telegram.bot.http import BotApi
from tests.integration.test_actor_matrix_behaviour import CLIENT, _world
from tests.transports.telegram_user.test_admin_chat import SUPER, _invoke

RESET = SemanticOperation(C.GROUP_INVITE_RESET, {})


def test_every_actor_can_reset_and_it_is_resolve_only():
    assert set(SUPPORT[C.GROUP_INVITE_RESET]) == {"telegram_bot", "telegram_user", "whatsapp_cloud"}
    for actor in ("telegram_bot", "telegram_user"):
        assert SEMANTICS[(C.GROUP_INVITE_RESET, actor)].ambiguity_policy == "resolve_only"


def test_the_bot_exports_a_new_primary_link_and_names_it():
    sent = []

    def handle(request):
        sent.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": "https://t.me/+NewPrimary"})

    admin = BotAdmin(BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle)))
    target = ProviderTarget("telegram", "telegram_bot", "dst_g", "-77")
    result = admin.invoke(RESET, target, "op")
    assert sent == [("exportChatInviteLink", {"chat_id": -77})]
    assert (result.outcome, result.provider_ref) == ("SUCCEEDED", "https://t.me/+NewPrimary")
    with pytest.raises(ValueError):
        admin.validate(SemanticOperation(C.GROUP_INVITE_RESET, {"invite_link": "x"}), target)


def test_the_user_account_exports_with_legacy_revoke_permanent(tmp_path):
    new = types.ChatInviteExported(link="https://t.me/+NewPrimary", admin_id=4242, date=None,
                                   permanent=True)  # fmt: skip
    result, sent, calls = _invoke(tmp_path, {"messages.ExportChatInviteRequest": new},
                                  C.GROUP_INVITE_RESET, {}, SUPER)  # fmt: skip
    assert calls == ["messages.ExportChatInviteRequest"] and sent[0].legacy_revoke_permanent
    assert (result.outcome, result.provider_ref) == ("SUCCEEDED", "https://t.me/+NewPrimary")


@pytest.mark.parametrize("actor", ["telegram_bot", "telegram_user"])
def test_revoke_without_an_invite_resets_and_returns_the_new_ref(actor, tmp_path):
    w, dispatcher, admin, _specs = _world(actor, tmp_path)
    got = dispatcher.call(CLIENT, "comms_group_invite_revoke",
                          {"group": w["grp"], "actor": actor, "request_id": refs.mint("request")})  # fmt: skip
    assert got.error_code is None, got.error_code
    assert got.structured["object"].startswith("inv_")
    assert [cap for cap, _args in admin.calls] == [C.GROUP_INVITE_RESET]
