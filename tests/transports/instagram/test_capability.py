"""Proposed A49, plan IG-1: the account registry, the lazy identity check and the capability
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
from comms.transports.instagram import store
from comms.transports.instagram.capability import INSTAGRAM_CAPABILITIES
from comms.transports.instagram.config import AccountPolicy, InstagramSettings
from tests.core.audit.legacy_fixtures import comms_world

from .fakes import OTHER_USER_ID, TOKEN, USER_ID, FakeGraph

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _world(tmp_path, *, writes=False, dms=False, register=True, fake=None):
    w = comms_world(tmp_path)
    conn, secrets = w["conn"], FileSecretStore(tmp_path / "secrets")
    fake = fake or FakeGraph()
    if register:
        rotate_credential(
            w["writer"], secrets, "meta-ig-access-token.main", TOKEN.encode(),
            prove=lambda _v: None, now=NOW,
        )  # fmt: skip
        with write_tx(conn):
            store.register_account(conn, "main", USER_ID, now=NOW, lifetime=timedelta(days=60))
    settings = InstagramSettings(
        default="main", accounts=MappingProxyType({"main": AccountPolicy("Main", writes, dms)})
    )
    adapters = build_adapters(
        conn, secrets, AdapterSettings(instagram=settings), clock=lambda: NOW,
        monotonic=lambda: 0.0, archive=None,
    )  # fmt: skip
    if adapters.instagram is not None:  # the test seam: route the account's client to the fake
        for runtime in adapters.instagram._by_alias.values():
            runtime.api._client._transport._inner = fake.transport()
    return adapters, fake, conn


def test_no_network_at_boot(tmp_path):
    adapters, fake, _ = _world(tmp_path)
    assert adapters.instagram is not None and adapters.instagram.configured
    assert fake.requests == []


def test_without_instagram_settings_there_is_no_instagram_actor(tmp_path):
    w = comms_world(tmp_path)
    adapters = build_adapters(
        w["conn"], FileSecretStore(tmp_path / "s"), AdapterSettings(), clock=lambda: NOW,
        monotonic=lambda: 0.0, archive=None,
    )  # fmt: skip
    assert adapters.instagram is None and "instagram" not in adapters.capability


def test_an_unregistered_account_is_not_configured(tmp_path):
    adapters, _, _ = _world(tmp_path, register=False)
    accounts = adapters.instagram
    with pytest.raises(CommsError) as refused:
        accounts.resolve("main", for_write=False)
    assert refused.value.code == "NOT_CONFIGURED"
    target = ProviderTarget("instagram", "instagram", "iga_" + "a" * 26, "x")
    states = adapters.capability["instagram"].snapshot("instagram", target).states
    assert set(states.values()) == {S.NOT_CONFIGURED}


@pytest.mark.parametrize(("writes", "dms"), [(False, False), (True, False), (True, True)])
def test_writes_follow_the_account_ceiling(tmp_path, writes, dms):
    adapters, _, _ = _world(tmp_path, writes=writes, dms=dms)
    runtime = adapters.instagram.resolve("main", for_write=True)
    states = adapters.capability["instagram"].snapshot("instagram", runtime.target()).states
    assert set(states) == set(INSTAGRAM_CAPABILITIES)
    assert states[C.MEDIA_LIST] is S.AVAILABLE and states[C.HISTORY_READ] is S.AVAILABLE
    assert states[C.MEDIA_PUBLISH] is (S.AVAILABLE if writes else S.NOT_AUTHORIZED)
    assert states[C.MESSAGE_REPLY] is (S.AVAILABLE if dms else S.NOT_AUTHORIZED)


def test_a_read_falls_back_to_the_default_and_a_write_never_does(tmp_path):
    adapters, _, _ = _world(tmp_path)
    assert adapters.instagram.resolve(None, for_write=False).alias == "main"
    with pytest.raises(CommsError) as refused:
        adapters.instagram.resolve(None, for_write=True)
    assert refused.value.code == "INVALID_ARGUMENT"
    with pytest.raises(CommsError) as unknown:
        adapters.instagram.resolve("ghost", for_write=False)
    assert unknown.value.code == "NOT_FOUND"


def test_identity_is_checked_once_and_a_mismatch_blocks_the_alias(tmp_path):
    adapters, fake, conn = _world(tmp_path)
    accounts = adapters.instagram
    runtime = accounts.resolve("main", for_write=False)
    assert accounts.username(runtime) == "raouf.studio"
    assert accounts.username(runtime) == "raouf.studio"
    assert len(fake.requests) == 1  # once per daemon lifetime
    assert store.account_by_alias(conn, "main").last_identity_check_at is not None

    (tmp_path / "b").mkdir(mode=0o700)
    blocked, fake2, _ = _world(tmp_path / "b")
    fake2.user_id[TOKEN] = OTHER_USER_ID
    other = blocked.instagram.resolve("main", for_write=False)
    with pytest.raises(CommsError) as refused:
        blocked.instagram.username(other)
    assert refused.value.code == "IDENTITY_MISMATCH"
    with pytest.raises(CommsError):
        blocked.instagram.username(other)
    assert len(fake2.requests) == 1  # blocked: nothing more is sent
    states = blocked.capability["instagram"].snapshot("instagram", other.target()).states
    assert set(states.values()) == {S.UNAVAILABLE}
    assert USER_ID not in repr(other) and TOKEN not in repr(other)
