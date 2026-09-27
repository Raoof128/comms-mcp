"""Catalog amendment G4 (spec A45, D4): destinations and location membership over MCP.

``comms_directory_destination_create`` takes a Telegram marked chat id (``-N`` a group,
``-100…`` a supergroup or channel, ``N`` a private chat) or a WhatsApp group id as Meta gives it,
input only. A group gets its ``grp_`` in the same transaction and is listed at once; a private
chat is a destination without one. It is ``open_world`` and host-confirmed. Location membership
changes who a location campaign reaches.
"""

import json
import os
from pathlib import Path

import pytest

from comms.core import refs
from comms.core.campaigns.resolve import resolve_targets
from comms.core.errors import CommsError
from comms.core.groups import group_identity, list_groups
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
TOOLS = (
    "comms_directory_destination_create",
    "comms_directory_destination_disable",
    "comms_location_member_add",
    "comms_location_member_remove",
)
BY_NAME = {s.name: s for s in DIRECTORY_PEOPLE_TOOLS if s.name in TOOLS}
WA = "Y2FwaV9ncm91cDoxOTUwNTU1MDA3OToxMjAzNjMzOTQzMjAdOTY0MTUZD"


def req():
    return refs.mint("request")


@pytest.fixture
def world(tmp_path):
    w = comms_world(tmp_path)
    rot.rotate(w["writer"], w["store"], "campaign-commit-key", material=os.urandom(32),
               prove=lambda m: None, now=NOW)  # fmt: skip
    rules, bind = directory_rules(w["writer"], w["store"])
    w["s"] = s = DirectoryService(w["writer"], MutationExecutor(w["writer"], {}), rules, bind)
    w["loc"] = s.location_create(CTX, "Parramatta", req())["location"]
    return w


def _create(w, identity, transport="telegram", name="G"):
    return w["s"].destination_create(CTX, w["loc"], transport, identity, name, req())


def _code(call):
    with pytest.raises(CommsError) as refused:
        call()
    return refused.value.code


def test_the_family_is_g4():
    assert sorted(BY_NAME) == sorted(TOOLS)


@pytest.mark.parametrize("name", TOOLS)
def test_schema_annotations_and_egress(name):
    family.schema_valid(BY_NAME[name])
    family.annotations(BY_NAME[name])
    assert EGRESS_MATRIX[name] == frozenset({"refs"})


def test_destination_create_is_open_world_and_host_confirmed():
    spec = BY_NAME["comms_directory_destination_create"]
    assert spec.open_world and spec.requires_request_id
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "mcp__comms__comms_directory_destination_create" in settings["permissions"]["ask"]


def test_outputs_match_their_schemas_and_dispatch(world):
    s = world["s"]
    rcp = s.recipient_create(CTX, "Sara", req())["recipient"]
    created = _create(world, "-77")
    dst = created["destination"]
    examples = {
        "comms_directory_destination_create": (
            {"location": world["loc"], "transport": "telegram", "identity": "-77", "name": "G"},
            created),
        "comms_location_member_add": (
            {"location": world["loc"], "recipient": rcp},
            s.location_member_add(CTX, world["loc"], rcp, req())),
        "comms_location_member_remove": (
            {"location": world["loc"], "recipient": rcp},
            s.location_member_remove(CTX, world["loc"], rcp, req())),
        "comms_directory_destination_disable": (
            {"destination": dst}, s.destination_disable(CTX, dst, req())),
    }  # fmt: skip
    for name, (example, result) in examples.items():
        family.output_matches(BY_NAME[name], result)
        family.write_requires_request_id(BY_NAME[name], example)
        family.dispatch_reaches_its_service(BY_NAME[name], example, result)


@pytest.mark.parametrize(
    ("transport", "identity", "stored"),
    [
        ("telegram", "-77", "group:77"),
        ("telegram", "-1001234567890", "channel:1234567890"),
        ("whatsapp", WA, f"group:{WA}"),
    ],
)
def test_a_group_gets_its_ref_at_once_and_is_listed(world, transport, identity, stored):
    created = _create(world, identity, transport)
    assert created["group"].startswith("grp_")
    listed = [g["group"] for g in list_groups(world["conn"], limit=10)[0]]
    assert created["group"] in listed
    _dst, got_transport, _identity = group_identity(world["conn"], created["group"])
    assert got_transport == transport
    row = (
        world["conn"]
        .execute(
            "SELECT platform_identity FROM destinations WHERE ref = ?", (created["destination"],)
        )
        .fetchone()
    )
    assert row == (stored,)


def test_a_private_chat_is_a_destination_without_a_group(world):
    created = _create(world, "908180", name="DM")
    assert created["destination"].startswith("dst_") and created["group"] is None


def test_the_identity_is_never_echoed(world):
    created = _create(world, "-1009876543210")
    texts = [json.dumps(created)] + [
        repr(r)
        for t in ("mutations", "audit_events")
        for r in world["conn"].execute(f"SELECT * FROM {t}")
    ]
    assert not any("9876543210" in text for text in texts)


@pytest.mark.parametrize(
    ("transport", "identity"),
    [
        ("telegram", "group:77"),  # the directory's form is not an input
        ("telegram", "@channel"),
        ("telegram", "-0"),
        ("whatsapp", "+61400000001"),  # a person, not a group
        ("whatsapp", f"group:{WA}"),
        ("whatsapp", "abc/def"),
        ("sms", "-77"),
    ],
)
def test_a_malformed_identity_is_refused_before_any_row(world, transport, identity):
    before = world["conn"].execute("SELECT count(*) FROM mutations").fetchone()[0]
    assert _code(lambda: _create(world, identity, transport)) == "INVALID_ARGUMENT"
    assert world["conn"].execute("SELECT count(*) FROM mutations").fetchone()[0] == before


def test_the_same_group_twice_is_refused(world):
    _create(world, "-77")
    assert _code(lambda: _create(world, "-77")) == "INVALID_ARGUMENT"


def test_a_disabled_destination_is_no_longer_a_group_target(world):
    created = _create(world, "-77")
    world["s"].destination_disable(CTX, created["destination"], req())
    with pytest.raises(Exception):  # noqa: B017 -- GroupError: unknown group
        group_identity(world["conn"], created["group"])


def test_membership_changes_who_a_location_campaign_reaches(world):
    s, conn = world["s"], world["conn"]
    rcp = s.recipient_create(CTX, "Sara", req())["recipient"]
    s.contact_add(CTX, rcp, "whatsapp", "+61400000001", req())
    reach = lambda: resolve_targets(conn, {"locations": [world["loc"]]}, ("whatsapp",))
    assert reach() == []
    s.location_member_add(CTX, world["loc"], rcp, req())
    assert len(reach()) == 1
    s.location_member_remove(CTX, world["loc"], rcp, req())
    assert reach() == []


@pytest.mark.parametrize(
    ("location", "recipient"),
    [("loc_" + "a" * 26, None), (None, "rcp_" + "a" * 26), ("rcp_" + "a" * 26, None)],
)
def test_unknown_refs_are_not_found(world, location, recipient):
    s = world["s"]
    rcp = recipient or s.recipient_create(CTX, "X", req())["recipient"]
    loc = location or world["loc"]
    assert _code(lambda: s.location_member_add(CTX, loc, rcp, req())) == "NOT_FOUND"
    assert _code(lambda: s.destination_disable(CTX, "dst_" + "a" * 26, req())) == "NOT_FOUND"
