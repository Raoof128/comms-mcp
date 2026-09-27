"""Catalog amendment G2 prerequisite: the real composition wires the WhatsApp actor.

Found while starting G2: ``build_comms_runtime`` listed only the Telegram actors and passed no
template service, media service or account target, so in the daemon a WhatsApp group (G1) and
every WhatsApp account tool answered ``NOT_CONFIGURED`` although their tests, which built their
own services, passed. These tests go through ``build_adapters`` and ``build_comms_runtime``.
"""

import json
import os
from datetime import UTC, datetime

import pytest

from comms.core.campaigns import directory as d
from comms.core.groups import group_ref
from comms.core.keys import rotate as rot
from comms.core.keys.secrets import FileSecretStore
from comms.core.providers.protocols import ProviderTarget
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.adapters import AdapterSettings, build_adapters
from comms.runtime.comms_runtime import build_comms_runtime
from comms.transports.whatsapp.numbers import wa_group_id
from comms.transports.whatsapp.webhooks.archive import CommsArchive
from tests.core.audit.legacy_fixtures import comms_world
from tests.core.campaign_helpers import NOW
from tests.integration.test_adapter_registry import SETTINGS
from tests.integration.test_adapter_registry import _configure as configure

CLIENT = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")
GROUP = "Y2FwaV9ncm91cDoxOTUwNTU1MDA3OToxMjAzNjMzOTQzMjAdOTY0MTUZD"


def _runtime(w, settings):
    adapters = build_adapters(
        w["conn"], w["secrets"], settings, clock=lambda: datetime.now(UTC),
        monotonic=lambda: 0.0, archive=CommsArchive(w["conn"], clock=lambda: NOW),
    )  # fmt: skip
    return build_comms_runtime(
        w["conn"], w["writer"], w["store"], adapters, clock=lambda: datetime.now(UTC),
        monotonic=lambda: 0.0, host="127.0.0.1", local_port=8765,
    )  # fmt: skip


@pytest.fixture
def w(tmp_path):
    w = comms_world(tmp_path)
    w["secrets"] = FileSecretStore(tmp_path / "secrets")
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(
            w["writer"], w["store"], purpose, material=os.urandom(32), prove=lambda m: None, now=NOW
        )
    return w


def test_a_configured_whatsapp_account_is_an_actor_with_its_services(w):
    configure(w, "meta-access-token")
    services = _runtime(w, SETTINGS).services
    assert "whatsapp_cloud" in services.actors
    assert services.templates is not None and services.media is not None
    assert services.account_target == ProviderTarget(
        "whatsapp", "whatsapp_cloud", "account", "waba:102290129340398"
    )


def test_without_the_token_whatsapp_is_not_an_actor(w):
    services = _runtime(w, SETTINGS).services
    assert "whatsapp_cloud" not in services.actors
    assert services.templates is None and services.media is None
    assert services.account_target is None


def test_without_a_business_account_id_there_is_no_account_target(w):
    configure(w, "meta-access-token")
    services = _runtime(w, AdapterSettings(meta_phone_number_id="106540352242922")).services
    assert "whatsapp_cloud" in services.actors  # groups and messages need only the number
    assert services.templates is None and services.account_target is None
    assert services.media is not None  # media is by phone number


def test_a_whatsapp_group_is_read_through_the_real_daemon_surface(w):
    configure(w, "meta-access-token", "meta-app-secret", "meta-webhook-secret")
    built = _runtime(w, SETTINGS)
    conn = w["conn"]
    loc = d.add_location(conn, "WA", now=NOW)
    dst = d.add_destination(
        conn, loc, "whatsapp", f"group:{GROUP}", "Family", normalize=wa_group_id, now=NOW
    )
    grp = group_ref(conn, dst, now=NOW)
    body = {"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp", "metadata": {"phone_number_id": "106540352242922"},
            "contacts": [{"wa_id": "61400000001", "profile": {"name": "S"}}],
            "messages": [{"from": "61400000001", "id": "wamid.X", "timestamp": "1758800000",
                          "type": "text", "text": {"body": "salaam"}, "group_id": GROUP}]}}]}]}  # fmt: skip
    CommsArchive(conn, clock=lambda: NOW).ingest(json.dumps(body).encode())
    page = built.dispatcher.call(CLIENT, "comms_context_recent", {"group": grp, "limit": 5})
    assert page.error_code is None, page.error_code
    assert [i["untrusted_text"] for i in page.structured["items"]] == ["salaam"]
