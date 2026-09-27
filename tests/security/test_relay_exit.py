"""Spec A48 (Task R5): the relay's exit gate. The plan's tasks R0–R5, each by its owning tests,
re-run in a fresh process with nothing skipped; and A48's promises.

The checklist is read against the plan's own task titles, so the two cannot drift.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-09-27-comms-whatsapp-relay.md"
SMOKE_MAP = ROOT / "docs" / "verification" / "comms-v0.3-smoke-map.json"
EVIDENCE = ROOT / "docs" / "verification" / "comms-relay.md"

EXIT_CHECKLIST: dict[str, tuple[str, ...]] = {
    "R0 Spec amendment A48, key purposes, the frozen pull signature": (
        "tests/core/test_relay_sig.py",
        "tests/core/keys/test_purposes.py",
        "tests/security/test_comms_wire_frozen.py",
        "tests/security/test_v03_preflight.py",
        "tests/runtime/test_provision.py",
    ),
    "R1 One copy of Meta's signature, and the local cap fixed": (
        "tests/transports/whatsapp_webhooks/test_signature.py",
        "tests/transports/whatsapp_webhooks/test_ingress.py",
    ),
    "R2 The Worker and the Mailbox (`relay/`)": ("tests/security/test_relay_static.py",),
    "R3 The collector (the Mac side)": (
        "tests/runtime/test_relay_collector.py",
        "tests/runtime/test_relay_wiring.py",
        "tests/transports/test_relay_client.py",
        "tests/security/test_egress.py",
    ),
    "R4 Operator commands and doctor": (
        "tests/runtime/test_relay_operator.py",
        "tests/core/test_doctor_relay.py",
        "tests/cli/test_operator_completeness.py",
    ),
    "R5 End to end, the runbook, the evidence": (
        "tests/runtime/test_selftest_relay.py",
        "tests/security/test_runbooks.py",
        "tests/security/test_smoke_map.py",
        "tests/security/test_d39_pre_exit.py::test_the_real_daemon_checks_are_pinned",
    ),
}
RELAY_CHECKS = (
    "a webhook the relay held while the daemon was off is read over MCP once it starts",
    "an unsigned delivery through the relay is quarantined, never inboxed, and the mailbox drains",
)


def test_the_checklist_is_the_plan_task_list_in_full():
    titles = re.findall(r"^### Task (R\d+): (.+)$", PLAN.read_text(encoding="utf-8"), re.MULTILINE)
    assert [f"{n} {t}" for n, t in titles] == list(EXIT_CHECKLIST)


def test_relay_exit_checklist():
    ids = sorted({i for group in EXIT_CHECKLIST.values() for i in group})
    for target in ids:
        assert (ROOT / target.split("::")[0]).is_file(), target
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider", *ids],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=1200,
    )  # fmt: skip
    tail = done.stdout[-2000:] + done.stderr[-2000:]
    assert done.returncode == 0, tail
    assert re.search(r"\d+ passed", done.stdout), tail
    assert not re.search(r"\d+ (failed|skipped|errors?|deselected)", done.stdout), tail


def test_the_real_daemon_relay_checks_are_pinned():
    added = json.loads(SMOKE_MAP.read_text(encoding="utf-8"))["added_in_v0_3"]
    assert all(f"phase_v03_daemon::{c}" in added for c in RELAY_CHECKS)


def test_the_evidence_names_what_the_owner_still_does():
    text = EVIDENCE.read_text(encoding="utf-8")
    for needle in ("D-R1", "wrangler login", "wrangler deploy", "D39-B", "R-R0", "R-R5",
                   "comms relay setup"):  # fmt: skip
        assert needle in text, needle
