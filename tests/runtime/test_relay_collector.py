"""Spec A48 (Task R3): the relay collector, against a scripted relay that checks every pull
signature the way the Worker does."""

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import httpx
import pytest

from comms.core import relay_sig
from comms.core.backup import age
from comms.runtime.relay import Collector
from comms.transports.whatsapp.relay_client import RelayClient
from comms.transports.whatsapp.webhooks.inbox import Inbox
from tests.core import schema_fixtures as fx
from tests.core.campaign_helpers import NOW

ROOT = Path(__file__).resolve().parents[2]
SECRET = b"fixture-app-secret"
PULL_KEY = hashlib.sha256(b"comms-relay test pull key").digest()
IDENTITY = age.identity_from_raw(
    hashlib.sha256(b"comms-relay test identity, never a real key").digest()
)
RECIPIENT = age.recipient_of(IDENTITY)
ORIGIN = "https://comms-relay.example.workers.dev"
PART = 1024 * 1024


def signed(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()


def webhook(n: int) -> bytes:
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"id": str(n), "changes": []}]},
                      separators=(",", ":")).encode()  # fmt: skip


class Relay:
    """The Worker's pull and ack semantics, in memory, with its signature check."""

    def __init__(self):
        self.rows: dict[int, dict] = {}
        self.next_seq, self.purged_through, self.acks = 1, 0, []
        self.down = False
        self.clock_skew = 0
        self.requests = []

    def put(self, raw: bytes, signature: str, *, parts_override=None, recipient=RECIPIENT):
        chunks = [raw[i : i + PART] for i in range(0, max(len(raw), 1), PART)] or [b""]
        batch = hashlib.sha256(raw + str(self.next_seq).encode()).hexdigest()[:32]
        seqs = []
        for part, chunk in enumerate(chunks):
            envelope = json.dumps({"batch": batch, "part": part, "parts": len(chunks),
                                   "raw_b64": base64.b64encode(chunk).decode(),
                                   "received_at": 1790000000000, "signature": signature},
                                  sort_keys=True, separators=(",", ":")).encode()  # fmt: skip
            seq = self.next_seq
            self.next_seq += 1
            self.rows[seq] = {"seq": seq, "received_at": 1790000000000, "batch": batch, "part": part,
                              "parts": len(chunks),
                              "ciphertext_b64": base64.b64encode(age.encrypt(envelope, recipient)).decode()}  # fmt: skip
            seqs.append(seq)
        return seqs

    def junk(self, ciphertext: bytes) -> int:
        seq = self.next_seq
        self.next_seq += 1
        self.rows[seq] = {"seq": seq, "received_at": 1790000000000, "batch": "0" * 32, "part": 0,
                          "parts": 1, "ciphertext_b64": base64.b64encode(ciphertext).decode()}  # fmt: skip
        return seq

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("relay down")
        now = int(time.time()) + self.clock_skew
        date = {"date": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(now))}
        body = request.content
        ok = relay_sig.verify(PULL_KEY, request.method, request.url.path,
                              int(request.headers["x-comms-timestamp"]), body,
                              request.headers["x-comms-signature"], now=now)  # fmt: skip
        if not ok:
            return httpx.Response(401, headers=date)
        fields = json.loads(body)
        if request.url.path == "/pull":
            rows, size = [], 0
            for seq in sorted(s for s in self.rows if s > fields["after"])[: fields["limit"]]:
                row = self.rows[seq]
                if rows and size + len(row["ciphertext_b64"]) > 256 * 1024:
                    break
                size += len(row["ciphertext_b64"])
                rows.append(row)
            oldest = min((r["received_at"] for r in self.rows.values()), default=None)
            return httpx.Response(200, json={"rows": rows, "purged_through": self.purged_through,
                                             "depth": len(self.rows), "oldest_received_at": oldest})  # fmt: skip
        self.acks.append(fields["through"])
        doomed = [s for s in self.rows if s <= fields["through"]]
        for s in doomed:
            del self.rows[s]
        return httpx.Response(200, json={"deleted": len(doomed)})


@pytest.fixture
def world(tmp_path):
    conn = fx.migrated(tmp_path)
    relay = Relay()
    client = RelayClient(ORIGIN, PULL_KEY, transport=httpx.MockTransport(relay.handler))
    inbox = Inbox(conn, clock=lambda: NOW)
    collector = Collector(conn, client, inbox, identities=[IDENTITY], app_secret=SECRET,
                          clock=lambda: NOW)  # fmt: skip
    return conn, relay, collector


def inboxed(conn) -> list[bytes]:
    return [bytes(r[0]) for r in conn.execute("SELECT body FROM webhook_inbox ORDER BY id")]


def state(conn) -> dict:
    cols = (
        "acked_through",
        "purged_through",
        "depth",
        "last_error",
        "clock_skew_s",
        "last_success_at",
    )
    row = conn.execute(f"SELECT {', '.join(cols)} FROM relay_state WHERE id = 1").fetchone()
    return dict(zip(cols, row, strict=True))


def test_rows_are_decrypted_verified_inboxed_then_acked(world):
    conn, relay, collector = world
    bodies = [webhook(n) for n in range(3)]
    for body in bodies:
        relay.put(body, signed(body))
    report = collector.run_once()
    assert (report.pulled, report.stored, report.quarantined, report.acked_through) == (3, 3, 0, 3)
    assert inboxed(conn) == bodies
    assert relay.acks == [3] and relay.rows == {}
    assert state(conn)["acked_through"] == 3 and state(conn)["last_error"] is None


def test_crash_between_commit_and_ack_duplicates_nothing(world, monkeypatch):
    conn, relay, collector = world
    body = webhook(1)
    relay.put(body, signed(body))

    def crash(through):
        raise KeyboardInterrupt  # the process dies after the inbox committed, before the ack

    monkeypatch.setattr(collector._client, "ack", crash)
    with pytest.raises(KeyboardInterrupt):
        collector.run_once()
    assert inboxed(conn) == [body] and relay.rows  # stored, and the relay still holds it
    monkeypatch.undo()
    report = collector.run_once()
    assert inboxed(conn) == [body]  # nothing new
    assert report.acked_through == 1 and relay.rows == {}


def test_a_crash_before_progress_moves_re_pulls_and_deduplicates(world, monkeypatch):
    conn, relay, collector = world
    body = webhook(2)
    relay.put(body, signed(body))
    monkeypatch.setattr(collector, "_advance", lambda seq: (_ for _ in ()).throw(KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        collector.run_once()
    monkeypatch.undo()
    assert collector.run_once().stored == 1  # re-pulled; the inbox ignores the duplicate body
    assert inboxed(conn) == [body] and relay.rows == {}


def test_junk_is_quarantined_not_inboxed_and_its_ciphertext_kept(world):
    conn, relay, collector = world
    body = webhook(3)
    unsigned = relay.put(body, "sha256=" + "00" * 32)
    wrong_key = relay.put(body, signed(body), recipient=age.recipient_of(age.generate_identity()))
    garbage = relay.junk(b"not age at all")
    good = webhook(4)
    relay.put(good, signed(good))
    report = collector.run_once()
    assert report.stored == 1 and report.quarantined == 3
    assert inboxed(conn) == [good]
    kept = {r[0]: (r[1], r[2] is not None) for r in
            conn.execute("SELECT seq, reason, ciphertext FROM relay_quarantine")}  # fmt: skip
    assert kept == {unsigned[0]: ("signature", True), wrong_key[0]: ("decrypt", True),
                    garbage: ("decrypt", True)}  # fmt: skip
    assert relay.rows == {}  # acked: the Mac holds the evidence now


def test_an_envelope_that_disagrees_with_its_row_is_quarantined(world):
    conn, relay, collector = world
    body = webhook(5)
    (seq,) = relay.put(body, signed(body))
    relay.rows[seq]["batch"] = "f" * 32  # the relay (or its account holder) rewrote a column
    assert collector.run_once().quarantined == 1
    assert conn.execute("SELECT reason FROM relay_quarantine").fetchone()[0] == "envelope"
    assert inboxed(conn) == []


def test_parts_reassemble_into_one_verified_body(world):
    conn, relay, collector = world
    big = b'{"object":"whatsapp_business_account","entry":["' + b"x" * (int(2.5 * PART)) + b'"]}'
    seqs = relay.put(big, signed(big))
    assert len(seqs) == 3
    report = collector.run_once()
    assert report.stored == 1 and report.pulled == 3
    assert inboxed(conn) == [big]


def test_a_batch_missing_a_part_is_quarantined_once_the_relay_is_drained(world):
    conn, relay, collector = world
    big = b'{"entry":["' + b"y" * (2 * PART) + b'"]}'
    seqs = relay.put(big, signed(big))
    del relay.rows[seqs[-1]]  # the last part is gone
    after = webhook(6)
    relay.put(after, signed(after))
    report = collector.run_once()
    assert inboxed(conn) == [after]
    reasons = dict(conn.execute("SELECT seq, reason FROM relay_quarantine").fetchall())
    assert reasons == {seqs[0]: "parts", seqs[1]: "parts"}
    assert report.acked_through == max(relay.acks)


def test_a_gap_not_covered_by_purge_is_recorded_and_a_purge_is_not(world):
    conn, relay, collector = world
    for n in range(6):
        body = webhook(10 + n)
        relay.put(body, signed(body))
    del relay.rows[2]  # deleted by someone: neither acked nor purged
    relay.purged_through = 0
    collector.run_once()
    assert conn.execute("SELECT from_seq, to_seq FROM relay_gaps").fetchall() == [(2, 2)]
    for n in range(3):
        body = webhook(20 + n)
        relay.put(body, signed(body))
    del relay.rows[7], relay.rows[8]
    relay.purged_through = 8  # purged by age: not a loss
    collector.run_once()
    assert conn.execute("SELECT count(*) FROM relay_gaps").fetchone()[0] == 1
    assert state(conn)["purged_through"] == 8


def test_an_unreachable_relay_loses_nothing(world):
    conn, relay, collector = world
    body = webhook(7)
    relay.put(body, signed(body))
    relay.down = True
    report = collector.run_once()
    assert report.error == "unreachable" and state(conn)["last_error"] == "unreachable"
    assert inboxed(conn) == [] and relay.rows
    relay.down = False
    assert collector.run_once().stored == 1
    assert inboxed(conn) == [body] and state(conn)["last_error"] is None


def test_clock_skew_is_recorded(world):
    conn, relay, collector = world
    relay.clock_skew = 900
    assert collector.run_once().error == "clock"
    st = state(conn)
    assert st["last_error"] == "clock" and 890 <= st["clock_skew_s"] <= 910


def test_a_wrong_pull_key_is_refused_not_a_clock_problem(world, tmp_path):
    conn, relay, _ = world
    client = RelayClient(ORIGIN, bytes(32), transport=httpx.MockTransport(relay.handler))
    collector = Collector(conn, client, Inbox(conn, clock=lambda: NOW), identities=[IDENTITY],
                          app_secret=SECRET, clock=lambda: NOW)  # fmt: skip
    assert collector.run_once().error == "refused"


def test_progress_never_moves_backwards(world):
    conn, _relay, _collector = world
    conn.execute("INSERT INTO relay_state (id, acked_through) VALUES (1, 5)")
    with pytest.raises(Exception, match="only moves forward"):
        conn.execute("UPDATE relay_state SET acked_through = 4 WHERE id = 1")


def test_the_real_workers_ciphertext_decrypts(world):
    """A page the real Worker served under ``wrangler dev`` (R-R2), opened by the daemon."""
    conn, relay, collector = world
    page = json.loads(
        (ROOT / "tests" / "fixtures" / "relay" / "wrangler_dev_page.json").read_text()
    )
    (row,) = page["rows"]
    relay.rows[row["seq"]] = row
    relay.next_seq = row["seq"] + 1
    report = collector.run_once()
    assert report.stored == 1
    (body,) = inboxed(conn)
    assert json.loads(body)["object"] == "whatsapp_business_account"


def test_the_client_sends_only_signed_counters(world):
    _conn, relay, collector = world
    body = webhook(8)
    relay.put(body, signed(body))
    collector.run_once()
    for request in relay.requests:
        assert str(request.url).startswith(ORIGIN)
        assert set(json.loads(request.content)) <= {"after", "limit", "through"}
        wire = request.content + b"".join(k + v for k, v in request.headers.raw)
        assert PULL_KEY.hex().encode() not in wire and PULL_KEY not in wire
        assert SECRET not in wire and IDENTITY.encode() not in wire


def test_schema_v9_holds_the_relay_state(world):
    conn, _relay, _collector = world
    assert conn.execute("SELECT max(version) FROM schema_version").fetchone()[0] == 9
    for table, columns in {
        "relay_state": ["id", "acked_through", "purged_through", "depth", "oldest_received_at",
                        "last_attempt_at", "last_success_at", "last_error", "clock_skew_s"],
        "relay_quarantine": ["seq", "reason", "ciphertext_sha256", "ciphertext", "quarantined_at"],
        "relay_gaps": ["id", "from_seq", "to_seq", "found_at"],
    }.items():  # fmt: skip
        assert [r[1] for r in conn.execute(f"PRAGMA table_info({table})")] == columns
