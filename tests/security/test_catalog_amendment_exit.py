"""Catalog amendment G9: the exit gate — the plan's tasks G0-G9 (G6a included), each by its
owning tests, re-run in a fresh process with nothing skipped; and the amendment's promises.

The checklist is read against the plan's own task titles, so the two cannot drift. Beyond the
owning tests: no catalog tool answers a constant refusal (``NOT_OFFERED`` is gone), the actor
matrix has no open cell and no A46 section left, and the whole path runs over MCP through the one
composition root: a person, their WhatsApp number, a location, an audience, a campaign frozen and
delivered by a fake provider, and that delivery in ``comms_context_person``. The real-daemon
acceptance is the smoke's ``phase_v03_daemon`` (``catalog_*`` checks, pinned by the smoke map).
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from comms.core import refs
from comms.core.delivery.engine import Engine, ExecutorLease
from comms.core.keys import rotate as rot
from comms.core.providers.capability import CapabilityState as S
from comms.mcp.catalog import TOOL_CATALOG
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime import facades
from comms.runtime.adapters import Adapters
from comms.runtime.comms_runtime import build_comms_runtime
from tests.core import fakes
from tests.core.audit.legacy_fixtures import comms_world
from tests.core.campaign_helpers import NOW
from tests.services.context_fixtures import Clock
from tests.services.group_fixtures import Provider

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-09-25-comms-v0.3-catalog-amendment.md"
MATRIX = ROOT / "docs" / "verification" / "comms-v0.3-actor-matrix.md"
SMOKE_MAP = ROOT / "docs" / "verification" / "comms-v0.3-smoke-map.json"
CLIENT = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")

EXIT_CHECKLIST: dict[str, tuple[str, ...]] = {
    "G0 Spec amendment A45, rulings, and the preflight pin": (
        "tests/security/test_v03_preflight.py",
    ),
    "G1 WhatsApp groups are destinations with `grp_` refs": (
        "tests/runtime/test_whatsapp_group_destinations.py",
        "tests/core/test_schema_v6.py",
        "tests/runtime/test_comms_runtime_whatsapp.py",
    ),
    "G2 Directory people — `comms_directory_recipient_*`": (
        "tests/mcp/test_catalog_directory_people.py",
    ),
    "G3 Contact points — `comms_directory_contact_*`": (
        "tests/mcp/test_catalog_directory_contacts.py",
        "tests/security/test_comms_wire_frozen.py",
    ),
    "G4 Destinations and location membership": (
        "tests/mcp/test_catalog_directory_places.py",
        "tests/core/backup/test_backup_groups.py",
    ),
    "G5 Per-person context — `comms_context_person`": ("tests/runtime/test_context_person.py",),
    "G6a Full admin on both APIs — the actor matrix (owner addition)": (
        "tests/core/providers/test_actor_matrix.py",
        "tests/integration/test_actor_matrix_behaviour.py",
    ),
    "G6 Telegram reads (7 tools)": (
        "tests/runtime/test_group_reads.py",
        "tests/runtime/test_group_lists.py",
        "tests/transports/telegram_bot/test_context_g6.py",
        "tests/transports/telegram_user/test_reads_g6.py",
        "tests/transports/test_invite_reset.py",
        "tests/security/test_phase4_architecture.py",
    ),
    "G7 Telegram writes (2 tools, plus A46's 3)": (
        "tests/transports/test_forward_and_create.py",
        "tests/transports/test_a46_admin.py",
    ),
    "G8 Account and media (4 tools, plus A46's 1)": (
        "tests/runtime/test_whatsapp_groups_live.py",
        "tests/runtime/test_account_profile.py",
        "tests/runtime/test_media_staged.py",
        "tests/conformance/test_meta_oracle.py",
    ),
    "G9 The pin, the guards, D39-A, the evidence": (
        "tests/mcp/test_catalog_pin.py",
        "tests/security/test_v03_egress.py",
        "tests/security/test_host_permissions.py",
        "tests/security/test_smoke_map.py",
        "tests/runtime/test_facades.py",
    ),
}
CATALOG_CHECKS = (
    "the directory over MCP: a person, a WhatsApp contact, a location with them, a Telegram and a WhatsApp group",
    "a location campaign reaches the person added over MCP",
    "a signed webhook for a WhatsApp group is read by its grp_",
    "comms_context_person serves the person's WhatsApp direct message",
)


def test_the_checklist_is_the_plan_task_list_in_full():
    titles = re.findall(
        r"^### Task (G\d+a?): (.+)$", PLAN.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert [f"{n} {t}" for n, t in titles] == list(EXIT_CHECKLIST)


def test_catalog_amendment_exit_checklist():
    ids = sorted({i for group in EXIT_CHECKLIST.values() for i in group})
    for target in ids:
        assert (ROOT / target).is_file(), target
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider", *ids],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=1200,
    )  # fmt: skip
    tail = done.stdout[-2000:] + done.stderr[-2000:]
    assert done.returncode == 0, tail
    assert re.search(r"\d+ passed", done.stdout), tail
    assert not re.search(r"\d+ (failed|skipped|errors?|deselected)", done.stdout), tail


def test_no_catalog_tool_is_unconditionally_not_offered():
    assert not hasattr(facades, "NOT_OFFERED")
    source = (ROOT / "src" / "comms" / "runtime" / "facades.py").read_text(encoding="utf-8")
    assert "_not_offered" not in source
    # the one constant refusal left answers a registry built without services, never a tool
    assert source.count("registry.register(spec.service, _unbound)") == 1


def test_the_matrix_has_no_open_cell_and_no_a46_section():
    text = MATRIX.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| `comms_")]
    assert rows and not [r for r in rows if "A todo" in r]
    assert "## Added by A46" not in text


def test_the_real_daemon_catalog_checks_are_pinned():
    added = json.loads(SMOKE_MAP.read_text(encoding="utf-8"))["added_in_v0_3"]
    assert all(f"phase_v03_daemon::{c}" in added for c in CATALOG_CHECKS)


def test_the_catalog_is_a45_and_a46_in_full():
    names = {s.name for s in TOOL_CATALOG}
    a45 = {
        *(f"comms_directory_recipient_{v}" for v in ("list", "get", "create", "update", "enable", "disable")),
        *(f"comms_directory_contact_{v}" for v in ("add", "disable", "opt_out")),
        "comms_directory_destination_create", "comms_directory_destination_disable",
        "comms_location_member_add", "comms_location_member_remove", "comms_context_person",
        "comms_media_stage_begin", "comms_media_stage_chunk",
    }  # fmt: skip
    a46 = {"comms_group_member_tag_set", "comms_message_reaction_remove",
           "comms_group_member_reactions_clear", "comms_whatsapp_health_status"}  # fmt: skip
    # A47 (after the amendment's tag) adds comms_message_send_media: 129 + 1
    assert a45 | a46 <= names and len(TOOL_CATALOG) == 130


def test_the_whole_path_over_mcp(tmp_path):
    """A person and their number over MCP, a location and an audience, a campaign frozen and
    delivered by a fake provider, and that delivery in the person's context."""
    w = comms_world(tmp_path)
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(w["writer"], w["store"], purpose, material=os.urandom(32),
                   prove=lambda m: None, now=NOW)  # fmt: skip
    conn = w["conn"]
    whatsapp = fakes.FakeWhatsApp(conn=conn)
    adapters = Adapters(
        delivery={"whatsapp": whatsapp},
        capability={"whatsapp_cloud": Provider(S.AVAILABLE)},
        context={"whatsapp_cloud": _EmptyArchive()},
    )
    built = build_comms_runtime(conn, w["writer"], w["store"], adapters, clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip

    def call(tool, **args):
        spec = next(s for s in TOOL_CATALOG if s.name == tool)
        if spec.requires_request_id:
            args["request_id"] = refs.mint("request")
        got = built.dispatcher.call(CLIENT, tool, args)
        assert got.error_code is None, (tool, got.error_code)
        return got.structured

    rcp = call("comms_directory_recipient_create", display_name="Sara")["recipient"]
    call(
        "comms_directory_contact_add", recipient=rcp, transport="whatsapp", identity="+61400000001"
    )
    loc = call("comms_location_create", name="Parramatta")["location"]
    call("comms_location_member_add", location=loc, recipient=rcp)
    aud = call("comms_audience_create", name="Everyone")["audience"]
    call("comms_audience_add", audience=aud, member=loc)
    assert call("comms_audience_resolve", audience=aud)["count"] == 1
    cmp = call("comms_campaign_create", title="Nowruz")["campaign"]
    call("comms_campaign_set_content", campaign=cmp, content={"canonical": "Salaam"})
    call("comms_campaign_set_targets", campaign=cmp, targets={"audiences": [aud]},
         transports=["whatsapp"])  # fmt: skip
    call("comms_campaign_validate", campaign=cmp)
    call("comms_campaign_send", campaign=cmp)
    Engine(conn, {"whatsapp": whatsapp}, clock=lambda: NOW).execute(
        ExecutorLease(fakes.FakeLock()), cmp
    )
    person = call("comms_context_person", recipient=rcp)
    (campaigns,) = [s for s in person["sections"] if s["section"] == "campaigns:whatsapp"]
    (item,) = campaigns["items"]
    assert item["campaign_ref"] == cmp and item["state"] != "PENDING"
    assert "61400000001" not in json.dumps(person)


class _EmptyArchive:
    """A WhatsApp archive with nothing in it: the person's campaign history is the point."""

    def read(self, query):
        from comms.core.providers.protocols import ContextPage

        return ContextPage((), "whatsapp_webhook_archive")
