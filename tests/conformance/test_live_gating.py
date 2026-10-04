"""comms v0.3 Task C32: live acceptance is opt-in and evidence-only (design §C.8; P §84–85)."""

import ast
import json
import subprocess
import sys
from pathlib import Path

from tests.conformance.runner import Failure, Report, record

ROOT = Path(__file__).resolve().parents[2]
LIVE_TEST = Path(__file__).with_name("test_live_acceptance.py")


def _collected(*flags):
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:randomly",
            "tests/conformance",
            *flags,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout


def test_live_tests_never_collected_without_flag():
    assert "test_live_acceptance" not in _collected()
    assert "test_live_acceptance.py::test_live_acceptance_evidence" in _collected(
        "--run-live-acceptance"
    )


def test_live_results_written_to_evidence_file_not_asserted_in_gate(tmp_path):
    report = Report(
        passed=3,
        skipped={"delivery_accepts_with_one_call": "NOT_CONFIGURED"},
        failures=(Failure("telegram_bot", "admin", "admin_x", "FAILED", "AssertionError"),),
    )
    path = record(
        report,
        tmp_path / "evidence.json",
        started="2026-09-25T00:00:00Z",
        accounts=("telegram_bot",),
    )
    written = json.loads(path.read_text())
    assert written == {
        "schema": "comms-live-acceptance/v1",
        "started": "2026-09-25T00:00:00Z",
        "accounts": ["telegram_bot"],
        "passed": 3,
        "skipped": {"delivery_accepts_with_one_call": "NOT_CONFIGURED"},
        "failures": [
            {
                "adapter": "telegram_bot",
                "contract": "admin",
                "case": "admin_x",
                "kind": "FAILED",
                "detail": "AssertionError",
            }
        ],
    }
    tree = ast.parse(LIVE_TEST.read_text())
    assert not any(
        isinstance(node, ast.Assert) for node in ast.walk(tree)
    )  # evidence, never a gate


def test_runbooks_exist_and_cover_p84_p85():
    telegram = (ROOT / "docs" / "runbooks" / "live-acceptance-telegram.md").read_text()
    whatsapp = (ROOT / "docs" / "runbooks" / "live-acceptance-whatsapp.md").read_text()
    for item in (
        "bot send",
        "user send",
        "member list",
        "restrict",
        "promote",
        "invite",
        "history",
        "search",
        "topic",
        "edit",
    ):
        assert item in telegram.lower(), item
    for item in (
        "free-form",
        "template",
        "media",
        "reply",
        "status webhook",
        "duplicate webhook",
        "failed status",
        "group",
    ):
        assert item in whatsapp.lower(), item
    for text in (telegram, whatsapp):
        assert "--run-live-acceptance" in text and "disposable" in text.lower()


def test_instagram_live_cases_are_not_configured_without_an_account(monkeypatch):
    """Proposed A49 (IG-6): until the accounts file names an Instagram account, every
    Instagram case reports NOT_CONFIGURED in a live run, never a result."""
    from comms.core.providers.protocols import ADAPTER_CONTRACTS
    from tests.conformance.registry import REGISTRY
    from tests.conformance.runner import Registry, run_suite

    monkeypatch.delenv("COMMS_LIVE_ACCOUNTS", raising=False)
    cases = {k: v for k, v in REGISTRY.cases.items() if k[0] == "instagram"}
    report = run_suite(Registry(cases), {"instagram": ADAPTER_CONTRACTS["instagram"]}, live=True)
    assert report.failures == () and report.passed == 0
    assert set(report.skipped.values()) == {"NOT_CONFIGURED"} and len(report.skipped) == 6


def test_the_instagram_runbook_covers_every_live_gate():
    text = (ROOT / "docs" / "runbooks" / "live-acceptance-instagram.md").read_text()
    for gate in ("GI-1", "GI-2", "GI-3", "GI-4", "GI-5", "GI-6", "GI-7", "GI-8"):
        assert gate in text, gate
    assert "--run-live-acceptance" in text and "throwaway" in text.lower()
    assert "hidden prompt" in text.lower()  # the token is never piped or passed (R-IG2)
