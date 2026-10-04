"""An Instagram world for service tests (proposed A49): one registered account ``main`` over a
recording fake of graph.instagram.com, the real adapters, capability service, cursor handles and
mutation executor."""

from __future__ import annotations

from datetime import timedelta
from types import MappingProxyType
from typing import Any

from comms.core.credentials import rotate_credential
from comms.core.keys.secrets import FileSecretStore
from comms.core.storage.db import write_tx
from comms.runtime.adapters import AdapterSettings, build_adapters
from comms.runtime.instagram import InstagramService
from comms.services.capability import CapabilityService
from comms.services.mutations import MutationExecutor
from comms.transports.instagram import store
from comms.transports.instagram.config import AccountPolicy, InstagramSettings
from comms.transports.instagram.messages import Throttle
from tests.core.campaign_helpers import NOW
from tests.services import handle_fixtures

from .fakes import OTHER_TOKEN, TOKEN, USER_ID, FakeGraph

CLIENT = handle_fixtures.CLIENT


def route(adapters: Any, fake: FakeGraph) -> None:
    """Point every account's pinned client at the fake (the pin itself stays in place)."""
    for runtime in adapters.instagram._by_alias.values():
        runtime.api._client._transport._inner = fake.transport()


def ig_world(tmp_path, *, writes=True, dms=True, caption=False, accounts=("main",)) -> dict:
    env = handle_fixtures.world(tmp_path)
    secrets = FileSecretStore(tmp_path / "secrets")
    conn = env["conn"]
    users = {"main": USER_ID, "studio": "17841400000000003"}
    tokens = {"main": TOKEN, "studio": OTHER_TOKEN}
    for alias in accounts:
        rotate_credential(
            env["writer"], secrets, f"meta-ig-access-token.{alias}", tokens[alias].encode(),
            prove=lambda _v: None, now=NOW,
        )  # fmt: skip
        with write_tx(conn):
            store.register_account(conn, alias, users[alias], now=NOW, lifetime=timedelta(days=60))
    fake = FakeGraph()
    fake.user_id[TOKEN], fake.user_id[OTHER_TOKEN] = USER_ID, users["studio"]
    settings = InstagramSettings(
        default="main",
        caption=caption,
        accounts=MappingProxyType(
            {alias: AccountPolicy(alias.title(), writes, dms) for alias in ("main", "studio")}
        ),
    )
    adapters = build_adapters(
        conn, secrets, AdapterSettings(instagram=settings), clock=env["clock"],
        monotonic=lambda: 0.0, archive=None,
    )  # fmt: skip
    route(adapters, fake)
    capability = CapabilityService(adapters.capability, clock=env["clock"])
    executor = MutationExecutor(env["writer"], adapters.admin)
    sleeps: list[float] = []
    elapsed = [0.0]

    def sleep(seconds: float) -> None:  # a sleep moves the fake clock, as a real one would
        sleeps.append(seconds)
        elapsed[0] += seconds

    service = InstagramService(
        conn, adapters.instagram, capability, env["handles"], clock=env["clock"],
        throttle=Throttle(sleep=sleep, monotonic=lambda: elapsed[0]), executor=executor,
    )  # fmt: skip
    return {**env, "secrets": secrets, "fake": fake, "adapters": adapters, "service": service,
            "capability": capability, "executor": executor, "sleeps": sleeps}  # fmt: skip
