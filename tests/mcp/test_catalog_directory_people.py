"""Catalog amendment G2 (spec A45): the people of the directory over MCP.

``comms_directory_recipient_*`` lists, reads, creates, renames, enables and disables recipients.
Every write replays by its ``req_`` id and is audited. A person's display name is owner-typed but
can reach a model as text, so outputs carry it under ``untrusted``; a contact point is shown by
its ``rct_`` ref and transport, never its identity.
"""

import pytest

from comms.core import refs
from comms.core.campaigns import directory as d
from comms.core.errors import CommsError
from comms.mcp.egress import EGRESS_MATRIX
from comms.mcp.tools.directory_people import DIRECTORY_PEOPLE_TOOLS
from comms.services.directory import DirectoryService
from comms.services.mutations import MutationExecutor
from tests.core.audit.legacy_fixtures import comms_world
from tests.core.campaign_helpers import NOW
from tests.mcp import family
from tests.services.group_fixtures import CTX

BY_NAME = {spec.name: spec for spec in DIRECTORY_PEOPLE_TOOLS}
NAMES = sorted(BY_NAME)
READS = {"comms_directory_recipient_list", "comms_directory_recipient_get"}
PHONE = "+61400000001"


def req():
    return refs.mint("request")


@pytest.fixture
def world(tmp_path):
    w = comms_world(tmp_path)
    w["service"] = DirectoryService(w["writer"], MutationExecutor(w["writer"], {}))
    return w


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    w = comms_world(tmp_path_factory.mktemp("people"))
    s = DirectoryService(w["writer"], MutationExecutor(w["writer"], {}))
    produced, examples = {}, {}
    created = s.recipient_create(CTX, "Sara", req())
    rcp = created["recipient"]
    d.add_contact_point(w["conn"], rcp, "whatsapp", PHONE, normalize=lambda s: s, now=NOW)
    produced["comms_directory_recipient_create"] = created
    examples["comms_directory_recipient_create"] = {"display_name": "Sara"}
    produced["comms_directory_recipient_update"] = s.recipient_update(CTX, rcp, "Sara K", req())
    examples["comms_directory_recipient_update"] = {"recipient": rcp, "display_name": "Sara K"}
    produced["comms_directory_recipient_disable"] = s.recipient_disable(CTX, rcp, req())
    produced["comms_directory_recipient_enable"] = s.recipient_enable(CTX, rcp, req())
    for name in ("disable", "enable"):
        examples[f"comms_directory_recipient_{name}"] = {"recipient": rcp}
    produced["comms_directory_recipient_get"] = s.recipient_get(rcp)
    examples["comms_directory_recipient_get"] = {"recipient": rcp}
    produced["comms_directory_recipient_list"] = s.recipient_list(limit=5)
    examples["comms_directory_recipient_list"] = {"limit": 5}
    return {"results": produced, "examples": examples}


def test_the_family_is_g2():
    tools = ("list", "get", "create", "update", "enable", "disable")
    assert sorted(f"comms_directory_recipient_{t}" for t in tools) == NAMES


@pytest.mark.parametrize("name", NAMES)
def test_schema_valid_json_schema_2020_12(name):
    family.schema_valid(BY_NAME[name])


@pytest.mark.parametrize("name", NAMES)
def test_output_schema_matches_service_result(name, results):
    family.output_matches(BY_NAME[name], results["results"][name])


@pytest.mark.parametrize("name", NAMES)
def test_annotations(name):
    family.annotations(BY_NAME[name])
    assert BY_NAME[name].read_only == (name in READS)
    assert not BY_NAME[name].open_world  # the directory is local


@pytest.mark.parametrize("name", sorted(set(NAMES) - READS))
def test_write_requires_request_id(name, results):
    family.write_requires_request_id(BY_NAME[name], results["examples"][name])


@pytest.mark.parametrize("name", NAMES)
def test_dispatch_reaches_its_service(name, results):
    family.dispatch_reaches_its_service(
        BY_NAME[name], results["examples"][name], results["results"][name]
    )


@pytest.mark.parametrize("name", NAMES)
def test_only_the_reads_carry_names_in_the_egress_matrix(name):
    expected = {"refs", "names"} if name in READS else {"refs"}
    assert EGRESS_MATRIX[name] == frozenset(expected)


def test_a_person_is_shown_by_refs_and_an_untrusted_name_never_an_identity(results):
    got = results["results"]["comms_directory_recipient_get"]
    assert got["untrusted"] == {"display_name": "Sara K"} and got["enabled"] is True
    ((contact,),) = [got["contacts"]]
    assert contact["contact"].startswith("rct_") and contact["transport"] == "whatsapp"
    assert "61400000001" not in repr(results["results"])
    listed = results["results"]["comms_directory_recipient_list"]["items"]
    assert [i["untrusted"]["display_name"] for i in listed] == ["Sara K"]


def test_a_replay_returns_the_first_result_and_creates_one_person(world):
    s, request = world["service"], req()
    first = s.recipient_create(CTX, "Ali", request)
    again = s.recipient_create(CTX, "Ali", request)
    assert again == {**first, "replayed": True}
    assert world["conn"].execute("SELECT count(*) FROM recipients").fetchone()[0] == 1
    with pytest.raises(CommsError) as reused:
        s.recipient_create(CTX, "Other", request)
    assert reused.value.code == "REQUEST_ID_REUSE"


def test_each_write_is_audited(world):
    s = world["service"]
    rcp = s.recipient_create(CTX, "Ali", req())["recipient"]
    s.recipient_update(CTX, rcp, "Ali R", req())
    s.recipient_disable(CTX, rcp, req())
    tools = [r[0] for r in world["conn"].execute("SELECT tool FROM mutations ORDER BY id")]
    assert tools == [
        "comms_directory_recipient_create",
        "comms_directory_recipient_update",
        "comms_directory_recipient_disable",
    ]


def test_a_disabled_person_is_no_longer_resolvable_by_name(world):
    s = world["service"]
    rcp = s.recipient_create(CTX, "Ali", req())["recipient"]
    assert d.named_recipients(world["conn"]) == [(rcp, "Ali")]
    s.recipient_disable(CTX, rcp, req())
    assert d.named_recipients(world["conn"]) == []
    assert s.recipient_get(rcp)["enabled"] is False


@pytest.mark.parametrize("name", ["", "   ", "x" * 201, 7, None])
def test_a_bad_display_name_is_refused_before_anything_is_written(world, name):
    with pytest.raises(CommsError) as refused:
        world["service"].recipient_create(CTX, name, req())
    assert refused.value.code == "INVALID_ARGUMENT"
    assert world["conn"].execute("SELECT count(*) FROM mutations").fetchone()[0] == 0


@pytest.mark.parametrize("ref", ["rcp_" + "a" * 26, "loc_" + "a" * 26, "nonsense"])
def test_an_unknown_person_is_not_found(world, ref):
    s = world["service"]
    for call in (
        lambda: s.recipient_get(ref),
        lambda: s.recipient_update(CTX, ref, "X", req()),
        lambda: s.recipient_disable(CTX, ref, req()),
    ):
        with pytest.raises(CommsError) as missing:
            call()
        assert missing.value.code == "NOT_FOUND"


def test_the_list_pages_newest_first(world):
    s = world["service"]
    made = [s.recipient_create(CTX, f"P{n}", req())["recipient"] for n in range(3)]
    first = s.recipient_list(limit=2)
    assert [i["recipient"] for i in first["items"]] == made[::-1][:2]
    rest = s.recipient_list(limit=2, cursor=first["next_cursor"])
    assert [i["recipient"] for i in rest["items"]] == [made[0]] and rest["next_cursor"] is None
