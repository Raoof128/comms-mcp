"""Spec A48 (Task R3): the relay in the composition — settings, adapters, keys, workers."""

import json
from types import SimpleNamespace

import pytest

from comms.core.backup import age
from comms.core.credentials import rotate_credential
from comms.core.keys.secrets import FileSecretStore
from comms.core.keys.slots import bootstrap_keys
from comms.runtime.adapters import AdapterSettings, RelayKeys, build_adapters
from comms.runtime.assemble import relay_keys
from comms.runtime.relay import Collector
from comms.runtime.settings import SettingsError, load_settings
from comms.runtime.workers import build_workers
from comms.transports.whatsapp.webhooks.archive import ArchiveContext
from tests.core.audit.legacy_fixtures import comms_world
from tests.core.campaign_helpers import NOW

URL = "https://comms-relay.example.workers.dev"
KEYS = RelayKeys(b"k" * 32, (age.generate_identity(),))


class Archive:
    def ingest(self, raw):
        return None


@pytest.fixture
def world(tmp_path):
    world = comms_world(tmp_path)
    world["secrets"] = FileSecretStore(tmp_path / "secrets")
    return world


def _secret(world, purpose, value):
    rotate_credential(
        world["writer"], world["secrets"], purpose, value, prove=lambda v: None, now=NOW
    )


def _build(world, settings, keys=KEYS):
    return build_adapters(world["conn"], world["secrets"], settings, clock=lambda: NOW,
                          monotonic=lambda: 0.0, archive=Archive(), relay_keys=keys)  # fmt: skip


def test_with_a_relay_no_listener_is_served_and_the_collector_runs(world):
    _secret(world, "meta-app-secret", b"fixture-app-secret-0123456789")
    adapters = _build(world, AdapterSettings(relay_url=URL))
    assert isinstance(adapters.relay, Collector)
    assert adapters.webhook is None and "webhook" not in adapters.listeners
    assert adapters.inbox is not None and adapters.worker is not None
    assert isinstance(adapters.context["whatsapp_cloud"], ArchiveContext)
    state = SimpleNamespace(conn=world["conn"])
    loops = {
        loop.name: loop for loop in build_workers(state, adapters, None, clock=lambda: NOW).loops
    }
    assert loops["relay"].every == 60.0 and loops["relay"].effects is False


def test_the_verify_token_is_not_needed_with_a_relay_but_the_app_secret_is(world):
    adapters = _build(world, AdapterSettings(relay_url=URL))
    assert adapters.relay is None and adapters.inbox is None  # D-R1: nothing unverifiable
    _secret(world, "meta-app-secret", b"fixture-app-secret-0123456789")
    assert _build(world, AdapterSettings(relay_url=URL), keys=None).relay is None


def test_without_a_relay_nothing_changes(world):
    _secret(world, "meta-app-secret", b"fixture-app-secret-0123456789")
    _secret(world, "meta-webhook-secret", b"fixture-verify-token-0123456789")
    adapters = _build(world, AdapterSettings())
    assert adapters.relay is None and adapters.listeners["webhook"] is adapters.webhook


def test_the_relay_keys_come_from_the_slots(world):
    bootstrap_keys(world["conn"], world["store"], ["relay-age-key", "relay-pull-key"], now=NOW)
    keys = relay_keys(SimpleNamespace(conn=world["conn"], store=world["store"]))
    assert len(keys.pull_key) == 32 and keys.identities[0].startswith("AGE-SECRET-KEY-1")
    assert age.recipient_of(keys.identities[0]).startswith("age1")
    assert "AGE-SECRET" not in repr(keys) and keys.pull_key.hex() not in repr(keys)


@pytest.fixture
def root(tmp_path):
    d = tmp_path / "comms"
    d.mkdir(mode=0o700)
    return d


def _settings(root, body):
    path = root / "comms.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    path.chmod(0o600)
    return load_settings(path)


def test_settings_take_a_relay_origin(root):
    assert _settings(root, {"relay": {"url": URL}}).adapter.relay_url == URL
    assert _settings(root, {"relay": {"url": URL + "/"}}).adapter.relay_url == URL
    assert _settings(root, {}).adapter.relay_url is None


@pytest.mark.parametrize(
    "body, message",
    [
        ({"relay": {"url": "http://comms-relay.example.workers.dev"}}, "https origin"),
        ({"relay": {"url": URL + "/pull"}}, "https origin"),
        ({"relay": {"url": URL, "pull_key": "x"}}, "unknown key|no secrets"),
        ({"relay": {}}, "https origin"),
        ({"relay": {"url": URL}, "webhook_port": 9003}, "not served"),
    ],
)
def test_settings_refuse_a_bad_relay(root, body, message):
    with pytest.raises(SettingsError, match=message):
        _settings(root, body)
