"""Proposed A50, plan PN-1: ``comms transport pinterest auth-url``, ``account add|list|remove``,
``token refresh`` and ``doctor`` (section 4.4). The OAuth code is exchanged under the stored app
secret, the access token is proved by ``GET /v5/user_account`` before it is active, both tokens
are staged, the ``pna_`` is recorded in one audited transaction, and no code, token, secret or
id leaves in a reply, an audit row or a log."""

import json
import logging
from types import MappingProxyType

import pytest

from comms.core.credentials import active_credential
from comms.runtime.operator import OperatorContext, operator_handler
from comms.runtime.operator.pinterest import PinterestOperator
from comms.transports.pinterest import store
from comms.transports.pinterest.config import AccountPolicy, PinterestSettings
from tests.transports.pinterest.fakes import (
    APP_ID,
    APP_SECRET,
    CODE,
    OTHER_REFRESH,
    OTHER_TOKEN,
    OTHER_USER_ID,
    REFRESH,
    TOKEN,
    USER_ID,
    FakePinterest,
)

SETTINGS = PinterestSettings(
    APP_ID, "https://raoof128.github.io/comms-mcp/pinterest/", "main", 50,
    MappingProxyType({"main": AccountPolicy("Main"), "studio": AccountPolicy("Studio")}),
)  # fmt: skip
SECRETS = (TOKEN, OTHER_TOKEN, REFRESH, OTHER_REFRESH, APP_SECRET, CODE, USER_ID, OTHER_USER_ID)


@pytest.fixture
def world(daemon_world):
    daemon_world["run"]("cutover", "run")
    ctx, fake, reloads = daemon_world["ctx"], FakePinterest(), []
    operator = PinterestOperator(daemon_world["state"].conn, SETTINGS, transport=fake.transport())
    full = OperatorContext(
        writer=ctx.writer, store=ctx.store, clock=ctx.clock, legacy=ctx.legacy,
        secrets=daemon_world["state"].secrets, proofs=operator.proofs(), pinterest=operator,
        reload=lambda: reloads.append(1) or {"reloaded": True},
    )  # fmt: skip
    handle = operator_handler(full)
    run = lambda *words, **args: handle({"command": list(words), **args})
    run("credential", "set", purpose="pinterest-app-secret", value=APP_SECRET)
    return {**daemon_world, "fake": fake, "run": run, "reloads": reloads}


def _leaks(world, reply, caplog):
    rows = world["state"].conn.execute("SELECT payload FROM audit_events").fetchall()
    surfaces = {"reply": json.dumps(reply), "audit": json.dumps(rows), "log": caplog.text}
    return [(where, s) for where, text in surfaces.items() for s in SECRETS if s in text]


def _add(world, alias="main", value=CODE):
    return world["run"]("transport", "pinterest", "account", "add", alias=alias, value=value)


def test_auth_url_names_the_app_and_the_scopes_without_network(world):
    reply = world["run"]("transport", "pinterest", "auth-url", alias="main")
    assert reply["url"].startswith("https://www.pinterest.com/oauth/?client_id=1234567&")
    assert reply["state"] in reply["url"] and "pins%3Awrite" in reply["url"]
    assert world["fake"].requests == []


def test_account_add_exchanges_the_code_proves_the_token_and_registers(world, caplog):
    with caplog.at_level(logging.DEBUG):
        reply = _add(world)
    conn, secrets = world["state"].conn, world["state"].secrets
    assert reply["alias"] == "main" and reply["account"].startswith("pna_")
    assert reply["username"] == "raouf.pinner" and reply["reloaded"] is True
    assert reply["expires_at"] < reply["refresh_expires_at"]
    row = store.account_by_alias(conn, "main")
    assert row.ref == reply["account"] and row.user_id == USER_ID
    assert active_credential(conn, secrets, "pinterest-access-token.main") == TOKEN.encode()
    assert active_credential(conn, secrets, "pinterest-refresh-token.main") == REFRESH.encode()
    kinds = [k for (k,) in conn.execute("SELECT kind FROM audit_events ORDER BY chain_seq")]
    assert kinds[-3:] == [
        "admin.credential_rotation",
        "admin.credential_rotation",
        "admin.pinterest_account",
    ]
    assert _leaks(world, reply, caplog) == []
    paths = [r.url.path for r in world["fake"].requests]
    assert paths[0] == "/v5/oauth/token" and set(paths[1:]) == {"/v5/user_account"}


def test_without_the_app_secret_nothing_is_exchanged(daemon_world):
    daemon_world["run"]("cutover", "run")
    ctx, fake = daemon_world["ctx"], FakePinterest()
    operator = PinterestOperator(daemon_world["state"].conn, SETTINGS, transport=fake.transport())
    full = OperatorContext(writer=ctx.writer, store=ctx.store, clock=ctx.clock, legacy=ctx.legacy,
                           secrets=daemon_world["state"].secrets, proofs=operator.proofs(),
                           pinterest=operator)  # fmt: skip
    with pytest.raises(ValueError, match="app secret"):
        operator_handler(full)({"command": ["transport", "pinterest", "account", "add"],
                                "alias": "main", "value": CODE})  # fmt: skip
    assert fake.requests == []


def test_a_code_pinterest_refuses_adds_nothing(world):
    world["fake"].grant = {"code": 2, "message": "bad code"}
    with pytest.raises(ValueError, match="not added"):
        _add(world)
    conn = world["state"].conn
    assert store.account_by_alias(conn, "main") is None
    assert active_credential(conn, world["state"].secrets, "pinterest-access-token.main") is None


def test_one_pinterest_account_cannot_be_added_under_two_aliases(world):
    _add(world)
    with pytest.raises(ValueError, match="already added"):
        _add(world, alias="studio")
    with pytest.raises(ValueError, match="already added"):
        _add(world, alias="main")


def test_an_unconfigured_or_malformed_alias_is_refused(world):
    for alias in ("ghost", "keystone", "Main"):
        with pytest.raises(ValueError):
            _add(world, alias=alias)
    assert world["fake"].requests == []


def test_list_shows_refs_and_dates_never_ids(world):
    _add(world)
    reply = world["run"]("transport", "pinterest", "account", "list")
    assert [a["alias"] for a in reply["accounts"]] == ["main", "studio"]
    assert reply["accounts"][1] == {"alias": "studio", "account": None, "configured": True,
                                    "expires_at": None, "refresh_expires_at": None}  # fmt: skip
    assert USER_ID not in json.dumps(reply)


def test_refresh_persists_what_pinterest_returns(world, caplog):
    _add(world)
    world["fake"].grant = {"access_token": OTHER_TOKEN, "refresh_token": OTHER_REFRESH,
                           "expires_in": 2592000, "refresh_token_expires_in": 5184000,
                           "token_type": "bearer", "response_type": "refresh_token"}  # fmt: skip
    world["fake"].user_id[OTHER_TOKEN] = USER_ID  # the refreshed token names the same account
    with caplog.at_level(logging.DEBUG):
        reply = world["run"]("transport", "pinterest", "token", "refresh", alias="main")
    assert reply["results"][0]["refreshed"] is True and reply["results"][0]["refresh_token_rotated"]
    conn, secrets = world["state"].conn, world["state"].secrets
    assert active_credential(conn, secrets, "pinterest-access-token.main") == OTHER_TOKEN.encode()
    assert (
        active_credential(conn, secrets, "pinterest-refresh-token.main") == OTHER_REFRESH.encode()
    )
    exchanges = [r for r in world["fake"].requests if r.url.path == "/v5/oauth/token"]
    assert (
        b"grant_type=refresh_token" in exchanges[-1].content
        and REFRESH.encode() in exchanges[-1].content
    )
    assert _leaks(world, reply, caplog) == []
    # a refresh that answers no refresh token keeps the one it has
    world["fake"].grant = {"access_token": TOKEN, "expires_in": 2592000, "token_type": "bearer"}
    world["fake"].user_id[TOKEN] = USER_ID
    again = world["run"]("transport", "pinterest", "token", "refresh", all=True)
    assert again["results"][0]["refresh_token_rotated"] is False
    assert (
        active_credential(conn, secrets, "pinterest-refresh-token.main") == OTHER_REFRESH.encode()
    )


def test_a_refreshed_token_naming_another_account_is_not_activated(world):
    _add(world)
    world["fake"].grant = {"access_token": OTHER_TOKEN, "refresh_token": OTHER_REFRESH,
                           "expires_in": 2592000, "token_type": "bearer"}  # fmt: skip
    reply = world["run"]("transport", "pinterest", "token", "refresh", all=True)
    assert reply["results"][0]["refreshed"] is False
    conn, secrets = world["state"].conn, world["state"].secrets
    assert active_credential(conn, secrets, "pinterest-access-token.main") == TOKEN.encode()
    assert active_credential(conn, secrets, "pinterest-refresh-token.main") == REFRESH.encode()


def test_credential_rotate_for_an_access_token_must_name_the_registered_account(world):
    with pytest.raises(ValueError):  # not added yet: add it first
        world["run"]("credential", "rotate", purpose="pinterest-access-token.main", value=TOKEN)
    _add(world)
    with pytest.raises(ValueError):
        world["run"](
            "credential", "rotate", purpose="pinterest-access-token.main", value=OTHER_TOKEN
        )
    with pytest.raises(ValueError):
        world["run"]("credential", "set", purpose="pinterest-app-secret", value="short")


def test_remove_revokes_both_tokens_and_keeps_the_row_removed(world):
    added = _add(world)
    reply = world["run"]("transport", "pinterest", "account", "remove", alias="main")
    assert reply["tokens_revoked"] == 2 and reply["account"] == added["account"]
    conn, secrets = world["state"].conn, world["state"].secrets
    assert store.account_by_alias(conn, "main") is None
    assert active_credential(conn, secrets, "pinterest-access-token.main") is None
    assert active_credential(conn, secrets, "pinterest-refresh-token.main") is None
    with pytest.raises(ValueError):
        world["run"]("transport", "pinterest", "account", "remove", alias="main")


def test_doctor_reports_findings_and_probes_identity(world):
    before = world["run"]("transport", "pinterest", "doctor")["findings"]
    assert before == [{"alias": "main", "status": "FINDINGS", "codes": ["PN_ACCOUNT_UNREGISTERED"]},
                      {"alias": "studio", "status": "FINDINGS", "codes": ["PN_ACCOUNT_UNREGISTERED"]}]  # fmt: skip
    _add(world)
    after = world["run"]("transport", "pinterest", "doctor")["findings"]
    assert after[0] == {"alias": "main", "status": "OK", "codes": []}
    world["fake"].user_id[TOKEN] = OTHER_USER_ID
    mismatch = world["run"]("transport", "pinterest", "doctor")["findings"]
    assert mismatch[0]["codes"] == ["PN_IDENTITY_MISMATCH"]
