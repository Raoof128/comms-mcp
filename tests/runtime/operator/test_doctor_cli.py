"""D39-PRE Task E9: ``comms doctor`` over the real state, read-only, and what it reports."""

import hashlib
import json
from pathlib import Path

import pytest

from comms.cli import main
from comms.core.credentials import record_confirmed, rotate_credential
from comms.runtime.state import open_comms_state
from tests.runtime.operator.conftest import _now


def _doctor(paths, capsys, *extra):
    main(["doctor", "--state-dir", str(paths.state_dir), *extra])
    return json.loads(capsys.readouterr().out)


def _codes(report):
    return {(f["code"], f["subject"]) for f in report["findings"]}


def _digest(paths):
    return hashlib.sha256(paths.db.read_bytes()).hexdigest()


def test_a_fresh_install_reports_the_pending_cutover_and_missing_credentials(daemon_world, capsys):
    paths = daemon_world["paths"]
    daemon_world["state"].conn.close()
    before = _digest(paths)
    report = _doctor(paths, capsys)
    assert report["bootstrap"] == "PROVISIONED"
    codes = {code for code, _subject in _codes(report)}
    # a fresh state: no cutover yet, no credentials, and retention has never run (the daemon's
    # maintenance loop runs it daily once the cutover releases the write hold)
    assert codes == {"CUTOVER_INCOMPLETE", "CREDENTIAL_NOT_CONFIGURED", "MAINTENANCE_OVERDUE"}
    assert report["ok"] is False
    assert _digest(paths) == before  # the doctor never writes


def test_after_the_cutover_and_retention_only_missing_credentials_remain(daemon_world, capsys):
    daemon_world["run"]("cutover", "run")
    daemon_world["run"]("retention", "run")
    daemon_world["state"].conn.close()
    report = _doctor(daemon_world["paths"], capsys)
    assert report["bootstrap"] == "READY"
    assert {code for code, _s in _codes(report)} == {"CREDENTIAL_NOT_CONFIGURED"}
    assert report["ok"] is True  # missing credentials are the owner's choice of providers


def test_an_unconfirmed_webhook_secret_is_reported_until_meta_confirms_it(daemon_world, capsys):
    run, paths = daemon_world["run"], daemon_world["paths"]
    run("cutover", "run")
    state = daemon_world["state"]
    version = rotate_credential(state.writer, state.secrets, "meta-app-secret", b"0" * 32,
                                prove=lambda v: None, now=_now())  # fmt: skip
    state.conn.close()
    assert ("CREDENTIAL_UNCONFIRMED", "meta-app-secret") in _codes(_doctor(paths, capsys))
    again = open_comms_state(paths, clock=_now)
    record_confirmed(again.conn, "meta-app-secret", version)
    again.conn.close()
    assert ("CREDENTIAL_UNCONFIRMED", "meta-app-secret") not in _codes(_doctor(paths, capsys))


def test_production_mode_exits_nonzero_unless_ok(daemon_world, capsys):
    daemon_world["state"].conn.close()
    with pytest.raises(SystemExit) as failed:
        _doctor(daemon_world["paths"], capsys, "--production")
    assert failed.value.code != 0


def test_an_unprovisioned_state_is_one_finding(tmp_path, capsys):
    main(["doctor", "--state-dir", str(tmp_path / "nothing")])
    report = json.loads(capsys.readouterr().out)
    assert [f["code"] for f in report["findings"]] == ["NOT_PROVISIONED"]
    assert not Path(tmp_path / "nothing").exists()  # never created


def test_a_logged_in_telegram_session_is_not_reported_missing(daemon_world, capsys):
    paths = daemon_world["paths"]
    daemon_world["state"].conn.close()
    before = {
        s for code, s in _codes(_doctor(paths, capsys)) if code == "CREDENTIAL_NOT_CONFIGURED"
    }
    assert "telegram-session" in before
    session_dir = paths.state_dir / "telegram"
    session_dir.mkdir(mode=0o700, exist_ok=True)
    (session_dir / "primary.session").write_bytes(b"")
    after = {s for code, s in _codes(_doctor(paths, capsys)) if code == "CREDENTIAL_NOT_CONFIGURED"}
    assert "telegram-session" not in after


def _comms_json(paths, body):
    paths.settings.write_text(json.dumps(body))
    paths.settings.chmod(0o600)


def test_instagram_accounts_are_checked_offline(daemon_world, capsys):
    """Proposed A49 (IG-6): comms.json against the registered accounts and their token
    metadata. No network and no token material: identity is the operator doctor's job."""
    from datetime import timedelta

    from comms.transports.instagram import store

    run, paths, state = daemon_world["run"], daemon_world["paths"], daemon_world["state"]
    run("cutover", "run")
    run("retention", "run")
    rotate_credential(state.writer, state.secrets, "meta-ig-access-token.main", b"IGAA" + b"x" * 40,
                      prove=lambda v: None, now=_now())  # fmt: skip
    store.register_account(state.conn, "main", "17841400000000001", now=_now(),
                           lifetime=timedelta(days=5))  # fmt: skip
    store.register_account(state.conn, "old", "17841400000000002", now=_now(),
                           lifetime=timedelta(days=60))  # fmt: skip
    state.conn.close()
    _comms_json(paths, {"instagram": {"accounts": {"main": {"label": "Main"},
                                                   "studio": {"label": "Studio"}}}})  # fmt: skip
    report = _doctor(paths, capsys)
    instagram = {(c, s) for c, s in _codes(report) if c.startswith("IG_")}
    assert instagram == {
        ("IG_TOKEN_EXPIRING", "main"),
        ("IG_ACCOUNT_UNREGISTERED", "studio"),
        ("IG_ACCOUNT_UNCONFIGURED", "old"),
        ("IG_TOKEN_MISSING", "old"),
    }
    assert report["ok"] is False
    text = json.dumps(report)
    assert "17841400000000001" not in text and "IGAA" not in text


def test_an_expiring_token_alone_keeps_the_doctor_ok(daemon_world, capsys):
    from datetime import timedelta

    from comms.transports.instagram import store

    run, paths, state = daemon_world["run"], daemon_world["paths"], daemon_world["state"]
    run("cutover", "run")
    run("retention", "run")
    rotate_credential(state.writer, state.secrets, "meta-ig-access-token.main", b"IGAA" + b"x" * 40,
                      prove=lambda v: None, now=_now())  # fmt: skip
    store.register_account(state.conn, "main", "17841400000000001", now=_now(),
                           lifetime=timedelta(days=5))  # fmt: skip
    state.conn.close()
    _comms_json(paths, {"instagram": {"accounts": {"main": {"label": "Main"}}}})
    report = _doctor(paths, capsys)
    assert {c for c, _s in _codes(report)} == {"CREDENTIAL_NOT_CONFIGURED", "IG_TOKEN_EXPIRING"}
    assert report["ok"] is True  # a warning: refresh within ten days


def test_a_malformed_comms_json_is_a_finding_not_a_crash(daemon_world, capsys):
    daemon_world["state"].conn.close()
    _comms_json(daemon_world["paths"], {"instagram": {"token": "x"}})
    report = _doctor(daemon_world["paths"], capsys)
    assert ("SETTINGS_INVALID", None) in _codes(report) and report["ok"] is False
