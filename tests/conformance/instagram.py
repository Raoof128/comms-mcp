"""Conformance cases for ``instagram`` (proposed A49, A18), over a recording fake of
graph.instagram.com. ``ADAPTER_CONTRACTS["instagram"]`` grows with the code (R-IG3 (8)):
``capability`` from IG-1, ``context`` from IG-2, ``admin`` from IG-3. Live mode needs the
owner's throwaway account (section 12)."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

from comms.core.credentials import rotate_credential
from comms.core.keys.secrets import FileSecretStore
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import ProviderTarget
from comms.core.storage.db import write_tx
from comms.runtime.adapters import AdapterSettings, build_adapters
from comms.transports.instagram import store
from comms.transports.instagram.config import AccountPolicy, InstagramSettings
from tests.conformance.registry import REGISTRY
from tests.conformance.runner import Mode, Skip
from tests.core.audit.legacy_fixtures import comms_world
from tests.transports.instagram.fakes import TOKEN, USER_ID, FakeGraph

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _adapters(mode: Mode, *, writes: bool, register: bool = True):
    if mode.live:
        raise Skip("NOT_CONFIGURED")
    root = Path(tempfile.mkdtemp())
    w = comms_world(root)
    conn, secrets = w["conn"], FileSecretStore(root / "secrets")
    if register:
        rotate_credential(
            w["writer"], secrets, "meta-ig-access-token.main", TOKEN.encode(),
            prove=lambda _v: None, now=NOW,
        )  # fmt: skip
        with write_tx(conn):
            store.register_account(conn, "main", USER_ID, now=NOW, lifetime=timedelta(days=60))
    settings = InstagramSettings(
        default="main",
        accounts=MappingProxyType({"main": AccountPolicy("Main", writes, False)}),
    )
    adapters = build_adapters(
        conn, secrets, AdapterSettings(instagram=settings), clock=lambda: NOW,
        monotonic=lambda: 0.0, archive=None,
    )  # fmt: skip
    fake = FakeGraph()
    if adapters.instagram is not None:
        for runtime in adapters.instagram._by_alias.values():
            runtime.api._client._transport._inner = fake.transport()
    return adapters, fake, conn


def _target(conn) -> ProviderTarget:
    account = store.account_by_alias(conn, "main")
    ref = account.ref if account is not None else "iga_" + "a" * 26
    return ProviderTarget("instagram", "instagram", ref, "main")


@REGISTRY.case("instagram", "capability")
def capability_unregistered_account_is_not_configured(mode: Mode) -> None:
    adapters, fake, conn = _adapters(mode, writes=True, register=False)
    states = adapters.capability["instagram"].snapshot("instagram", _target(conn)).states
    assert set(states.values()) == {S.NOT_CONFIGURED} and fake.requests == []


@REGISTRY.case("instagram", "capability")
def capability_writes_follow_the_comms_json_ceiling(mode: Mode) -> None:
    adapters, fake, conn = _adapters(mode, writes=False)
    states = adapters.capability["instagram"].snapshot("instagram", _target(conn)).states
    assert states[C.MEDIA_LIST] is S.AVAILABLE
    assert states[C.COMMENT_REPLY] is S.NOT_AUTHORIZED
    assert states[C.MESSAGE_REPLY] is S.NOT_AUTHORIZED
    assert fake.requests == []  # a snapshot never reaches Meta
