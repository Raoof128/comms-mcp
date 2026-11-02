"""Proposed A50, plan PN-1: the account registry, the lazy identity check and the capability
snapshot (sections 3, 4.3, 4.5)."""

from datetime import UTC, datetime, timedelta
from types import MappingProxyType

import pytest

from comms.core.credentials import rotate_credential
from comms.core.errors import CommsError
from comms.core.keys.secrets import FileSecretStore
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import ProviderTarget
from comms.core.storage.db import write_tx
from comms.runtime.adapters import AdapterSettings, build_adapters
from comms.transports.pinterest import store
from comms.transports.pinterest.capability import PINTEREST_CAPABILITIES
from comms.transports.pinterest.config import AccountPolicy, PinterestSettings
from tests.core.audit.legacy_fixtures import comms_world

from .fakes import APP_ID, OTHER_USER_ID, REFRESH, TOKEN, USER_ID, FakePinterest

NOW = datetime(2026, 11, 2, tzinfo=UTC)
REDIRECT = "https://raoof128.github.io/comms-mcp/pinterest/"


def _world(tmp_path, *, writes=False, register=True, fake=None, sandbox=False):
    w = comms_world(tmp_path)
    conn, secrets = w["conn"], FileSecretStore(tmp_path / "secrets")
    fake = fake or FakePinterest()
    if register:
        for purpose, value in (("pinterest-access-token.main", TOKEN),
                               ("pinterest-refresh-token.main", REFRESH)):  # fmt: skip
            rotate_credential(w["writer"], secrets, purpose, value.encode(),
                              prove=lambda _v: None, now=NOW)  # fmt: skip
        with write_tx(conn):
            store.register_account(conn, "main", USER_ID, now=NOW, access_lifetime=timedelta(days=30),
                                   refresh_lifetime=timedelta(days=60))  # fmt: skip
    settings = PinterestSettings(
        APP_ID, REDIRECT, "main", 50,
        MappingProxyType({"main": AccountPolicy("Main", writes, sandbox)}),
    )  # fmt: skip
    adapters = build_adapters(
        conn, secrets, AdapterSettings(pinterest=settings), clock=lambda: NOW,
        monotonic=lambda: 0.0, archive=None,
    )  # fmt: skip
    if adapters.pinterest is not None:
        for runtime in adapters.pinterest._by_alias.values():
            runtime.api._client._transport._inner = fake.transport()
    return adapters, fake, conn


def _target(conn):
    account = store.account_by_alias(conn, "main")
    ref = account.ref if account is not None else "pna_" + "a" * 26
    return ProviderTarget("pinterest", "pinterest", ref, "main")


def test_no_network_at_boot_and_the_sandbox_pins_its_host(tmp_path):
    adapters, fake, _ = _world(tmp_path, sandbox=True)
    assert adapters.pinterest is not None and adapters.pinterest.configured
    assert fake.requests == [] and "pinterest" in adapters.admin
    runtime = adapters.pinterest.resolve("main", for_write=False)
    assert runtime.api.origin == "https://api-sandbox.pinterest.com"


def test_without_settings_there_is_no_pinterest_actor(tmp_path):
    w = comms_world(tmp_path)
    adapters = build_adapters(
        w["conn"], FileSecretStore(tmp_path / "s"), AdapterSettings(), clock=lambda: NOW,
        monotonic=lambda: 0.0, archive=None,
    )  # fmt: skip
    assert adapters.pinterest is None and "pinterest" not in adapters.capability


def test_an_unregistered_account_is_not_configured_and_has_no_admin(tmp_path):
    adapters, fake, conn = _world(tmp_path, register=False)
    states = adapters.capability["pinterest"].snapshot("pinterest", _target(conn)).states
    assert set(states) == set(PINTEREST_CAPABILITIES)
    assert set(states.values()) == {S.NOT_CONFIGURED} and "pinterest" not in adapters.admin
    with pytest.raises(CommsError) as refused:
        adapters.pinterest.resolve("main", for_write=False)
    assert refused.value.code == "NOT_CONFIGURED" and fake.requests == []


def test_writes_follow_the_ceiling_and_reads_are_available(tmp_path):
    adapters, fake, conn = _world(tmp_path, writes=False)
    states = adapters.capability["pinterest"].snapshot("pinterest", _target(conn)).states
    assert states[C.BOARD_LIST] is S.AVAILABLE and states[C.INSIGHTS_READ] is S.AVAILABLE
    assert states[C.PIN_CREATE] is S.NOT_AUTHORIZED and states[C.MEDIA_UPLOAD] is S.NOT_AUTHORIZED
    assert fake.requests == []  # a snapshot never reaches Pinterest
    (tmp_path / "w").mkdir(mode=0o700)
    adapters, _, conn = _world(tmp_path / "w", writes=True)
    states = adapters.capability["pinterest"].snapshot("pinterest", _target(conn)).states
    assert all(state is S.AVAILABLE for state in states.values())


def test_the_identity_is_checked_once_and_a_mismatch_blocks_the_alias(tmp_path):
    adapters, fake, conn = _world(tmp_path)
    runtime = adapters.pinterest.resolve(None, for_write=False)  # the default
    assert adapters.pinterest.username(runtime) == "raouf.pinner"
    assert adapters.pinterest.username(runtime) == "raouf.pinner"
    assert len(fake.requests) == 1 and fake.requests[0].url.path == "/v5/user_account"
    assert store.account_by_alias(conn, "main").last_identity_check_at.startswith("2026-11-02")
    fake.user_id[TOKEN] = OTHER_USER_ID
    (tmp_path / "m").mkdir(mode=0o700)
    adapters, fake, conn = _world(tmp_path / "m", fake=fake)
    runtime = adapters.pinterest.resolve("main", for_write=True)
    with pytest.raises(CommsError) as refused:
        adapters.pinterest.username(runtime)
    assert refused.value.code == "IDENTITY_MISMATCH"
    states = adapters.capability["pinterest"].snapshot("pinterest", _target(conn)).states
    assert set(states.values()) == {S.UNAVAILABLE}


def test_a_write_never_falls_back_to_the_default(tmp_path):
    adapters, _, _ = _world(tmp_path)
    with pytest.raises(CommsError) as refused:
        adapters.pinterest.resolve(None, for_write=True)
    assert refused.value.code == "INVALID_ARGUMENT"
    with pytest.raises(CommsError) as unknown:
        adapters.pinterest.resolve("ghost", for_write=False)
    assert unknown.value.code == "NOT_FOUND"
