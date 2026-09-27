"""Catalog amendment G3 (spec A45, D1, D4): contact points over MCP; identities are input only.

``comms_directory_contact_add`` takes a WhatsApp number (E.164) or a numeric Telegram user id,
normalised by the one rule for its transport, and returns a ``rct_`` ref. The identity is never
echoed: not in the output, the mutation record, the audit chain or a log. The request is bound to
the identity by a keyed HMAC (``comms-directory-identity/v1``), never an unkeyed hash a phone
number could be brute-forced from, so one ``req_`` id cannot be replayed for another number.
``contact_add`` reaches the outside world (a campaign can then send to it), so it is ``open_world``
and host-confirmed (D4). A duplicate, an opted-out identity and a malformed one are refused with
the same fixed ``INVALID_ARGUMENT``.
"""

import json
import logging
import os
from pathlib import Path

import pytest

from comms.core import refs
from comms.core.campaigns import directory as d
from comms.core.campaigns.resolve import resolve_targets
from comms.core.errors import CommsError
from comms.core.keys import rotate as rot
from comms.mcp.egress import EGRESS_MATRIX
from comms.mcp.tools.directory_people import DIRECTORY_PEOPLE_TOOLS
from comms.runtime.comms_runtime import directory_rules
from comms.services.directory import DirectoryService
from comms.services.mutations import MutationExecutor
from tests.core.audit.legacy_fixtures import comms_world
from tests.core.campaign_helpers import NOW
from tests.mcp import family
from tests.services.group_fixtures import CTX

ROOT = Path(__file__).resolve().parents[2]
CONTACT_TOOLS = ("contact_add", "contact_disable", "contact_opt_out")
BY_NAME = {s.name: s for s in DIRECTORY_PEOPLE_TOOLS if "_contact_" in s.name}
NAMES = sorted(BY_NAME)
CANARY = "+61 400 777 123"  # as typed; canonical +61400777123
DIGITS = "61400777123"
TG_USER = "908180777"


def req():
    return refs.mint("request")


def _service(w):
    rules, bind = directory_rules(w["writer"], w["store"])
    return DirectoryService(w["writer"], MutationExecutor(w["writer"], {}), rules, bind)


@pytest.fixture
def world(tmp_path):
    w = comms_world(tmp_path)
    rot.rotate(w["writer"], w["store"], "campaign-commit-key", material=os.urandom(32),
               prove=lambda m: None, now=NOW)  # fmt: skip
    w["service"] = s = _service(w)
    w["rcp"] = s.recipient_create(CTX, "Sara", req())["recipient"]
    w["other"] = s.recipient_create(CTX, "Ali", req())["recipient"]
    return w


def _add(w, identity=CANARY, *, recipient=None, transport="whatsapp", request=None):
    return w["service"].contact_add(
        CTX, recipient or w["rcp"], transport, identity, request or req()
    )


def _code(call):
    with pytest.raises(CommsError) as refused:
        call()
    return refused.value.code


def test_the_family_is_g3():
    assert NAMES == sorted(f"comms_directory_{t}" for t in CONTACT_TOOLS)


@pytest.mark.parametrize("name", NAMES)
def test_schema_and_egress(name):
    family.schema_valid(BY_NAME[name])
    family.annotations(BY_NAME[name])
    assert EGRESS_MATRIX[name] == frozenset({"refs"})


def test_contact_add_is_open_world_and_host_confirmed():
    spec = BY_NAME["comms_directory_contact_add"]
    assert spec.open_world and not spec.destructive and spec.requires_request_id
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "mcp__comms__comms_directory_contact_add" in settings["permissions"]["ask"]


def test_outputs_match_their_schemas_and_dispatch(world):
    added = _add(world)
    rct = added["contact"]
    examples = {
        "comms_directory_contact_add": (
            {"recipient": world["rcp"], "transport": "whatsapp", "identity": CANARY}, added),
        "comms_directory_contact_disable": (
            {"contact": rct}, world["service"].contact_disable(CTX, rct, req())),
        "comms_directory_contact_opt_out": (
            {"contact": rct}, world["service"].contact_opt_out(CTX, rct, req())),
    }  # fmt: skip
    for name, (example, result) in examples.items():
        family.output_matches(BY_NAME[name], result)
        family.write_requires_request_id(BY_NAME[name], example)
        family.dispatch_reaches_its_service(BY_NAME[name], example, result)
    assert rct.startswith("rct_")


def test_the_identity_is_never_echoed(world, caplog):
    caplog.set_level(logging.DEBUG)
    added = _add(world)
    conn = world["conn"]
    texts = [json.dumps(added), caplog.text]
    for table in ("mutations", "audit_events"):
        texts += [repr(row) for row in conn.execute(f"SELECT * FROM {table}")]
    texts.append(json.dumps(world["service"].recipient_get(world["rcp"])))
    for text in texts:
        assert DIGITS not in text and "400 777" not in text
    # it is stored where it belongs, canonical, in the encrypted directory
    assert (
        conn.execute(
            "SELECT count(*) FROM delivery_identities WHERE identity = '+61400777123'"
        ).fetchone()[0]
        == 1
    )


def test_the_request_is_bound_to_the_identity_by_a_keyed_digest(world):
    request = req()
    first = _add(world, request=request)
    assert _add(world, request=request) == {**first, "replayed": True}
    assert _code(lambda: _add(world, "+61400777999", request=request)) == "REQUEST_ID_REUSE"
    stored = world["conn"].execute("SELECT request_digest FROM mutations").fetchall()
    from comms.services.mutations import request_digest

    unkeyed = request_digest(
        "comms_directory_contact_add",
        {"transport": "whatsapp", "identity": "+61400777123"},
        {"recipient": world["rcp"]},
    )
    assert (unkeyed,) not in stored  # the number cannot be brute-forced from the digest


@pytest.mark.parametrize(
    ("transport", "identity"),
    [
        ("whatsapp", "61400777123"),  # no +
        ("whatsapp", "+61 4"),
        ("whatsapp", "group:ABCDEFGH12"),  # a group is a destination (G4), not a person
        ("telegram", "@sara"),
        ("telegram", "-1001234567"),  # a chat, not a user
        ("telegram", "user:12"),
        ("telegram", ""),
        ("sms", "+61400777123"),
    ],
)
def test_a_malformed_identity_is_refused_before_any_row(world, transport, identity):
    before = world["conn"].execute("SELECT count(*) FROM mutations").fetchone()[0]
    assert _code(lambda: _add(world, identity, transport=transport)) == "INVALID_ARGUMENT"
    assert world["conn"].execute("SELECT count(*) FROM mutations").fetchone()[0] == before
    assert world["conn"].execute("SELECT count(*) FROM contact_points").fetchone()[0] == 0


def test_a_telegram_user_id_is_a_contact(world):
    rct = _add(world, TG_USER, transport="telegram")["contact"]
    got = world["service"].recipient_get(world["rcp"])
    assert got["contacts"] == [
        {"contact": rct, "transport": "telegram", "enabled": True, "opted_out": False}
    ]
    assert TG_USER not in json.dumps(got)


def test_a_duplicate_identity_is_refused_for_anyone(world):
    _add(world)
    assert _code(lambda: _add(world, recipient=world["other"])) == "INVALID_ARGUMENT"
    assert _code(lambda: _add(world, "+61400777124")) == "INVALID_ARGUMENT"  # one per transport


def test_an_opted_out_identity_stays_out_even_after_disable(world):
    rct = _add(world)["contact"]
    world["service"].contact_opt_out(CTX, rct, req())
    world["service"].contact_disable(CTX, rct, req())
    # before G3 a disabled, opted-out contact could be re-added under a new ref and messaged
    assert _code(lambda: _add(world, recipient=world["other"])) == "INVALID_ARGUMENT"
    assert _code(lambda: _add(world)) == "INVALID_ARGUMENT"


def test_opt_out_and_disable_take_a_person_out_of_campaigns(world):
    conn = world["conn"]
    rct = _add(world)["contact"]
    assert resolve_targets(conn, {"recipients": [world["rcp"]]}, ("whatsapp",))
    world["service"].contact_opt_out(CTX, rct, req())
    assert resolve_targets(conn, {"recipients": [world["rcp"]]}, ("whatsapp",)) == []
    assert world["service"].recipient_get(world["rcp"])["contacts"][0]["opted_out"] is True


def test_a_disabled_contact_frees_its_transport_for_a_new_number(world):
    rct = _add(world)["contact"]
    world["service"].contact_disable(CTX, rct, req())
    assert _add(world, "+61400777124")["contact"] != rct


@pytest.mark.parametrize("ref", ["rct_" + "a" * 26, "rcp_" + "a" * 26, "x"])
def test_an_unknown_contact_is_not_found(world, ref):
    assert _code(lambda: world["service"].contact_disable(CTX, ref, req())) == "NOT_FOUND"
    assert _code(lambda: world["service"].contact_opt_out(CTX, ref, req())) == "NOT_FOUND"


def test_an_unknown_person_is_not_found(world):
    assert _code(lambda: _add(world, recipient="rcp_" + "b" * 26)) == "NOT_FOUND"


def test_without_the_commit_key_contact_add_is_not_configured(tmp_path):
    w = comms_world(tmp_path)
    s = _service(w)
    rcp = s.recipient_create(CTX, "Sara", req())["recipient"]
    assert _code(lambda: s.contact_add(CTX, rcp, "whatsapp", CANARY, req())) == "NOT_CONFIGURED"
    assert d.named_recipients(w["conn"]) == [(rcp, "Sara")]
