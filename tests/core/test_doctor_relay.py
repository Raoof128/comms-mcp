"""Spec A48 (Task R4): comms doctor reads the relay collector's state — one planted problem per
finding, and nothing when no relay was ever used."""

from datetime import timedelta

import pytest

from comms.core import timeutil
from comms.core.doctor import relay_findings
from tests.core import schema_fixtures as fx
from tests.core.campaign_helpers import NOW


@pytest.fixture
def conn(tmp_path):
    return fx.migrated(tmp_path)


def _state(conn, **fields):
    base = {"acked_through": 0, "purged_through": 0, "depth": 0, "oldest_received_at": None,
            "last_attempt_at": timeutil.iso(NOW), "last_success_at": timeutil.iso(NOW),
            "last_error": None, "clock_skew_s": None}  # fmt: skip
    base.update(fields)
    cols = ", ".join(base)
    conn.execute(f"INSERT INTO relay_state (id, {cols}) VALUES (1, {', '.join('?' * len(base))})",
                 tuple(base.values()))  # fmt: skip


def _codes(conn):
    return sorted(f.code for f in relay_findings(conn, now=NOW))


def test_no_relay_no_findings(conn):
    assert relay_findings(conn, now=NOW) == []


def test_a_healthy_relay_has_no_findings(conn):
    _state(conn, depth=3, oldest_received_at=timeutil.iso(NOW - timedelta(minutes=5)))
    assert _codes(conn) == []


@pytest.mark.parametrize(
    "fields, code",
    [
        ({"last_error": "unreachable"}, "RELAY_UNREACHABLE"),
        ({"last_error": "malformed"}, "RELAY_UNREACHABLE"),
        ({"last_error": "refused"}, "RELAY_REFUSED"),
        ({"last_error": "clock", "clock_skew_s": 912}, "RELAY_CLOCK"),
        (
            {"oldest_received_at": timeutil.iso(NOW - timedelta(days=26)), "depth": 1},
            "RELAY_BACKLOG_OLD",
        ),
    ],
)
def test_each_problem_is_named(conn, fields, code):
    _state(conn, **fields)
    assert code in _codes(conn)


def test_stale_only_while_the_daemon_is_trying(conn):
    old = timeutil.iso(NOW - timedelta(minutes=30))
    _state(conn, last_attempt_at=timeutil.iso(NOW - timedelta(minutes=1)), last_success_at=old,
           last_error="unreachable")  # fmt: skip
    assert "RELAY_STALE" in _codes(conn)
    conn.execute("UPDATE relay_state SET last_attempt_at = ? WHERE id = 1", (old,))
    assert "RELAY_STALE" not in _codes(conn)  # the daemon is off: that is the owner's choice


def test_gaps_and_quarantine_are_counted(conn):
    _state(conn)
    conn.execute("INSERT INTO relay_gaps (from_seq, to_seq, found_at) VALUES (4, 6, ?)",
                 (timeutil.iso(NOW),))  # fmt: skip
    for seq in (9, 10):
        conn.execute("INSERT INTO relay_quarantine (seq, reason, ciphertext_sha256, quarantined_at)"
                     " VALUES (?, 'signature', ?, ?)", (seq, "0" * 64, timeutil.iso(NOW)))  # fmt: skip
    findings = {f.code: f for f in relay_findings(conn, now=NOW)}
    assert findings["RELAY_GAP"].detail == "3 relay row(s) vanished without an ack or a purge"
    assert findings["RELAY_QUARANTINE"].detail == "2 relay row(s) quarantined (comms relay status)"


def test_the_findings_join_the_doctor_report(conn):
    from comms.core import doctor as core

    assert relay_findings in vars(core).values()
    from pathlib import Path

    assert "relay_findings(conn, now)" in Path(core.__file__).read_text(encoding="utf-8")
