"""Proposed A49, plan IG-1: ``comms transport instagram account add|list|remove``, ``token
refresh`` and ``doctor`` (section 4.4). The token is proved by ``GET /me`` before it is active, the ``iga_``
is recorded in one audited transaction, and no token or Instagram id leaves in a reply, an
audit row or a log."""

import json
import logging
from datetime import UTC, datetime, timedelta
from types import MappingProxyType

import pytest

from comms.core import timeutil
from comms.core.credentials import active_credential
from comms.runtime.operator import OperatorContext, operator_handler
from comms.runtime.operator.instagram import InstagramOperator
from comms.transports.instagram import store
from comms.transports.instagram.config import AccountPolicy, InstagramSettings
from tests.transports.instagram.fakes import OTHER_TOKEN, OTHER_USER_ID, TOKEN, USER_ID, FakeGraph

SETTINGS = InstagramSettings(
    accounts=MappingProxyType({"main": AccountPolicy("Main"), "studio": AccountPolicy("Studio")})
)


@pytest.fixture
def world(daemon_world):
    daemon_world["run"]("cutover", "run")
    ctx, fake, reloads = daemon_world["ctx"], FakeGraph(), []
    operator = InstagramOperator(daemon_world["state"].conn, SETTINGS, transport=fake.transport())
    full = OperatorContext(
        writer=ctx.writer, store=ctx.store, clock=ctx.clock, legacy=ctx.legacy,
        secrets=daemon_world["state"].secrets, proofs=operator.proofs(), instagram=operator,
        reload=lambda: reloads.append(1) or {"reloaded": True},
    )  # fmt: skip
    handle = operator_handler(full)
    run = lambda *words, **args: handle({"command": list(words), **args})
    return {**daemon_world, "fake": fake, "run": run, "reloads": reloads}


def _leaks(world, reply, caplog):
    rows = world["state"].conn.execute("SELECT payload FROM audit_events").fetchall()
    surfaces = {"reply": json.dumps(reply), "audit": json.dumps(rows), "log": caplog.text}
    return [
        (where, secret)
        for where, text in surfaces.items()
        for secret in (TOKEN, OTHER_TOKEN, USER_ID, OTHER_USER_ID)
        if secret in text
    ]


def test_account_add_proves_me_and_registers(world, caplog):
    with caplog.at_level(logging.DEBUG):
        reply = world["run"]("transport", "instagram", "account", "add", alias="main", value=TOKEN)
    conn, secrets = world["state"].conn, world["state"].secrets
    assert reply["alias"] == "main" and reply["account"].startswith("iga_")
    assert reply["username"] == "raouf.studio" and reply["reloaded"] is True
    row = store.account_by_alias(conn, "main")
    assert row.ref == reply["account"] and row.user_id == USER_ID
    assert active_credential(conn, secrets, "meta-ig-access-token.main") == TOKEN.encode()
    kinds = [k for (k,) in conn.execute("SELECT kind FROM audit_events ORDER BY chain_seq")]
    assert kinds[-2:] == ["admin.credential_rotation", "admin.instagram_account"]
    assert _leaks(world, reply, caplog) == []
    assert all("/me" in r.url.path for r in world["fake"].requests)  # the proof and its re-check


def test_a_token_that_does_not_prove_itself_adds_nothing(world):
    with pytest.raises(ValueError, match="not added"):
        world["run"](
            "transport", "instagram", "account", "add", alias="main", value="IGAA" + "x" * 40
        )
    conn = world["state"].conn
    assert store.account_by_alias(conn, "main") is None
    assert active_credential(conn, world["state"].secrets, "meta-ig-access-token.main") is None


def test_one_instagram_account_cannot_be_added_under_two_aliases(world):
    world["run"]("transport", "instagram", "account", "add", alias="main", value=TOKEN)
    with pytest.raises(ValueError, match="already added"):
        world["run"]("transport", "instagram", "account", "add", alias="studio", value=TOKEN)
    with pytest.raises(ValueError, match="already added"):
        world["run"]("transport", "instagram", "account", "add", alias="main", value=OTHER_TOKEN)


def test_an_unconfigured_or_malformed_alias_is_refused(world):
    for alias in ("ghost", "keystone", "Main"):
        with pytest.raises(ValueError):
            world["run"]("transport", "instagram", "account", "add", alias=alias, value=TOKEN)
    assert world["fake"].requests == []


def test_list_shows_refs_and_dates_never_ids(world):
    world["run"]("transport", "instagram", "account", "add", alias="main", value=TOKEN)
    reply = world["run"]("transport", "instagram", "account", "list")
    assert [a["alias"] for a in reply["accounts"]] == ["main", "studio"]
    assert reply["accounts"][1] == {"alias": "studio", "account": None, "configured": True,
                                    "expires_at": None}  # fmt: skip
    assert USER_ID not in json.dumps(reply)


def test_refresh_persists_the_returned_token_and_extends_the_lifetime(world):
    world["run"]("transport", "instagram", "account", "add", alias="main", value=TOKEN)
    world["fake"].user_id[OTHER_TOKEN] = USER_ID  # Meta's refreshed token names the same account
    reply = world["run"]("transport", "instagram", "token", "refresh", alias="main")
    assert reply["results"][0]["refreshed"] is True
    conn, secrets = world["state"].conn, world["state"].secrets
    assert active_credential(conn, secrets, "meta-ig-access-token.main") == OTHER_TOKEN.encode()
    refresh = [r for r in world["fake"].requests if r.url.path == "/refresh_access_token"]
    assert len(refresh) == 1 and refresh[0].headers["authorization"] == f"Bearer {TOKEN}"


def test_a_refreshed_token_naming_another_account_is_not_activated(world):
    world["run"]("transport", "instagram", "account", "add", alias="main", value=TOKEN)
    reply = world["run"]("transport", "instagram", "token", "refresh", all=True)
    assert reply["results"][0]["refreshed"] is False
    conn, secrets = world["state"].conn, world["state"].secrets
    assert active_credential(conn, secrets, "meta-ig-access-token.main") == TOKEN.encode()


def test_credential_rotate_for_an_account_token_must_name_the_registered_account(world):
    with pytest.raises(ValueError):  # not added yet: add it first
        world["run"]("credential", "rotate", purpose="meta-ig-access-token.main", value=TOKEN)
    world["run"]("transport", "instagram", "account", "add", alias="main", value=TOKEN)
    with pytest.raises(ValueError):
        world["run"]("credential", "rotate", purpose="meta-ig-access-token.main", value=OTHER_TOKEN)


def test_remove_revokes_the_token_and_keeps_the_row_removed(world):
    added = world["run"]("transport", "instagram", "account", "add", alias="main", value=TOKEN)
    reply = world["run"]("transport", "instagram", "account", "remove", alias="main")
    assert reply == {"account": added["account"], "alias": "main", "token_revoked": True,
                     "reloaded": True}  # fmt: skip
    conn = world["state"].conn
    assert store.account_by_alias(conn, "main") is None
    assert active_credential(conn, world["state"].secrets, "meta-ig-access-token.main") is None
    removed = conn.execute(
        "SELECT removed_at FROM instagram_accounts WHERE ref = ?", (added["account"],)
    ).fetchone()
    assert removed[0] is not None


def test_doctor_reports_each_account(world):
    world["run"]("transport", "instagram", "account", "add", alias="main", value=TOKEN)
    reply = world["run"]("transport", "instagram", "doctor")
    by_alias = {f["alias"]: f for f in reply["findings"]}
    assert by_alias["main"] == {"alias": "main", "status": "OK", "codes": []}
    assert by_alias["studio"]["codes"] == ["IG_ACCOUNT_UNREGISTERED"]
    conn = world["state"].conn
    soon = datetime.now(UTC) + timedelta(days=3)
    conn.execute("UPDATE instagram_accounts SET expires_at = ?", (timeutil.iso(soon),))
    world["fake"].user_id[TOKEN] = OTHER_USER_ID
    codes = {
        f["alias"]: f["codes"] for f in world["run"]("transport", "instagram", "doctor")["findings"]
    }
    assert codes["main"] == ["IG_TOKEN_EXPIRING", "IG_IDENTITY_MISMATCH"]
