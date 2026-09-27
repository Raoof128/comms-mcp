"""Spec A48 (Task R4): the owner's relay commands — local, read-only, and a secret only ever
into a pipe."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from comms import cli
from comms.core.backup import age
from comms.runtime.paths import CommsPaths
from comms.runtime.provision import provision

NOW = datetime(2026, 9, 27, tzinfo=UTC)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # AF_UNIX-length paths stay short
    Path("run").mkdir(mode=0o700)
    provision(CommsPaths(tmp_path / "state"), now=NOW, runtime_dir=Path("run"))
    return tmp_path / "state"


def _run(argv, monkeypatch, *, tty=False):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty)
    try:
        cli.main(argv)
    except SystemExit as exit_:
        return int(exit_.code or 0)
    return 0


def test_the_recipient_is_the_public_half_of_the_relay_key(state, monkeypatch, capsys):
    assert _run(["relay", "recipient", "--state-dir", str(state)], monkeypatch, tty=True) == 0
    recipient = capsys.readouterr().out.strip()
    assert recipient.startswith("age1") and len(recipient) == 62
    assert "AGE-SECRET" not in recipient


def test_the_pull_key_goes_only_into_a_pipe(state, monkeypatch, capsys):
    assert _run(["relay", "export-pull-key", "--state-dir", str(state)], monkeypatch, tty=True) == 4
    out, err = capsys.readouterr()
    assert out == "" and "wrangler secret put RELAY_PULL_KEY" in err
    assert _run(["relay", "export-pull-key", "--state-dir", str(state)], monkeypatch) == 0
    key = capsys.readouterr().out
    assert len(key) == 64 and int(key, 16) >= 0 and "\n" not in key


def test_a_new_path_token_goes_only_into_a_pipe(state, monkeypatch, capsys):
    assert _run(["relay", "new-path"], monkeypatch, tty=True) == 4
    assert capsys.readouterr().out == ""
    assert _run(["relay", "new-path"], monkeypatch) == 0
    first = capsys.readouterr().out
    _run(["relay", "new-path"], monkeypatch)
    second = capsys.readouterr().out
    assert len(first) == 43 and first != second
    assert set(first) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_status_reports_the_collectors_state_without_material(state, monkeypatch, capsys):
    assert _run(["relay", "status", "--state-dir", str(state)], monkeypatch, tty=True) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == {"acked_through": 0, "depth": None, "gaps": 0, "last_error": None,
                      "last_success_at": None, "oldest_received_at": None, "purged_through": 0,
                      "quarantined": 0}  # fmt: skip


def test_setup_prints_the_checklist_and_no_secret(state, monkeypatch, capsys):
    assert _run(["relay", "setup"], monkeypatch, tty=True) == 0
    text = capsys.readouterr().out
    for step in ("npm ci", "comms relay export-pull-key | npx wrangler secret put RELAY_PULL_KEY",
                 "comms relay recipient | npx wrangler secret put RELAY_AGE_RECIPIENT",
                 "npx wrangler secret put META_VERIFY_TOKEN", "npx wrangler deploy",
                 "/webhooks/meta/", '"relay"'):  # fmt: skip
        assert step in text, step
    assert "AGE-SECRET" not in text


def test_nothing_is_created_without_provisioned_state(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "nothing"
    assert _run(["relay", "recipient", "--state-dir", str(empty)], monkeypatch) == 4
    assert "comms keys provision" in capsys.readouterr().err
    assert not empty.exists()


def test_the_recipient_opens_what_the_daemon_can_read(state, monkeypatch, capsys):
    from comms.core.keys.slots import KeySlotStore, load_active
    from comms.runtime.doctor import open_read_only

    _run(["relay", "recipient", "--state-dir", str(state)], monkeypatch)
    recipient = capsys.readouterr().out.strip()
    conn = open_read_only(CommsPaths(state))
    raw, _ = load_active(conn, KeySlotStore(CommsPaths(state).slots_dir), "relay-age-key")
    assert age.decrypt(age.encrypt(b"x", recipient), age.identity_from_raw(raw)) == b"x"
