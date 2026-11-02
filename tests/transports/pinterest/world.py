"""A Pinterest world for service tests (proposed A50): registered accounts over a recording fake
of api.pinterest.com and the upload host, the real adapters, capability service, cursor handles
and mutation executor."""

from __future__ import annotations

from datetime import timedelta
from types import MappingProxyType
from typing import Any

from comms.core.credentials import rotate_credential
from comms.core.keys.secrets import FileSecretStore
from comms.core.storage.db import write_tx
from comms.runtime.adapters import AdapterSettings, build_adapters
from comms.runtime.pinterest import PinterestService
from comms.services.capability import CapabilityService
from comms.services.mutations import MutationExecutor
from comms.transports.pinterest import store
from comms.transports.pinterest.config import AccountPolicy, PinterestSettings
from tests.core.campaign_helpers import NOW
from tests.services import handle_fixtures

from .fakes import APP_ID, OTHER_REFRESH, OTHER_TOKEN, REFRESH, TOKEN, USER_ID, FakePinterest

CLIENT = handle_fixtures.CLIENT
REDIRECT = "https://raoof128.github.io/comms-mcp/pinterest/"


def route(adapters: Any, fake: FakePinterest) -> None:
    """Point every account's pinned client, and the upload client, at the fake."""
    for runtime in adapters.pinterest._by_alias.values():
        runtime.api._client._transport._inner = fake.transport()
    if "pinterest" in adapters.admin:
        adapters.admin["pinterest"]._transport = fake.transport()


def settings(
    *, writes: bool = True, budget: int = 50, default: str | None = "main"
) -> PinterestSettings:
    return PinterestSettings(
        APP_ID,
        REDIRECT,
        default,
        budget,
        MappingProxyType(
            {alias: AccountPolicy(alias.title(), writes, False) for alias in ("main", "studio")}
        ),
    )


def pn_world(tmp_path, *, writes=True, budget=50, accounts=("main",)) -> dict:
    env = handle_fixtures.world(tmp_path)
    secrets = FileSecretStore(tmp_path / "secrets")
    conn = env["conn"]
    users = {"main": USER_ID, "studio": "900000000000000003"}
    tokens = {"main": (TOKEN, REFRESH), "studio": (OTHER_TOKEN, OTHER_REFRESH)}
    for alias in accounts:
        for purpose, value in zip(
            (f"pinterest-access-token.{alias}", f"pinterest-refresh-token.{alias}"),
            tokens[alias], strict=True,
        ):  # fmt: skip
            rotate_credential(
                env["writer"], secrets, purpose, value.encode(), prove=lambda _v: None, now=NOW
            )
        with write_tx(conn):
            store.register_account(
                conn, alias, users[alias], now=NOW, access_lifetime=timedelta(days=30),
                refresh_lifetime=timedelta(days=60),
            )  # fmt: skip
    fake = FakePinterest()
    fake.user_id[TOKEN], fake.user_id[OTHER_TOKEN] = USER_ID, users["studio"]
    adapters = build_adapters(
        conn, secrets, AdapterSettings(pinterest=settings(writes=writes, budget=budget)),
        clock=env["clock"], monotonic=lambda: 0.0, archive=None,
    )  # fmt: skip
    route(adapters, fake)
    capability = CapabilityService(adapters.capability, clock=env["clock"])
    executor = MutationExecutor(env["writer"], adapters.admin)
    service = PinterestService(
        conn, adapters.pinterest, capability, env["handles"], clock=env["clock"], executor=executor
    )
    return {**env, "secrets": secrets, "fake": fake, "adapters": adapters, "service": service,
            "capability": capability, "executor": executor}  # fmt: skip
