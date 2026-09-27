"""Spec A48 (Task R0): the relay's pull signature, its frozen layout, and the relay keys."""

import hashlib
import hmac
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from comms.core import relay_sig
from comms.core.backup import age
from comms.core.keys.slots import key_id_for

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "tests" / "fixtures" / "relay" / "pull_signature_vectors.json"
KEY = bytes(range(32))


def test_the_signature_is_the_frozen_layout():
    body = b'{"after":0,"limit":50}'
    message = b"comms-relay-pull/v1\0POST\0/pull\0" + b"1790000000\0" + body
    expected = hmac.new(KEY, message, hashlib.sha256).hexdigest()
    assert relay_sig.sign(KEY, "POST", "/pull", 1790000000, body) == expected


def test_verify_refuses_stale_altered_and_malformed():
    sig = relay_sig.sign(KEY, "POST", "/ack", 1000, b"{}")
    assert relay_sig.verify(KEY, "POST", "/ack", 1000, b"{}", sig, now=1300)
    assert relay_sig.verify(KEY, "POST", "/ack", 1000, b"{}", sig, now=700)
    assert not relay_sig.verify(KEY, "POST", "/ack", 1000, b"{}", sig, now=1301)
    assert not relay_sig.verify(KEY, "POST", "/ack", 1000, b"{}", sig, now=699)
    assert not relay_sig.verify(KEY, "POST", "/ack", 1000, b'{"through":9}', sig, now=1000)
    assert not relay_sig.verify(KEY, "POST", "/pull", 1000, b"{}", sig, now=1000)
    assert not relay_sig.verify(KEY, "POST", "/ack", 1000, b"{}", sig.upper(), now=1000)
    assert not relay_sig.verify(KEY, "POST", "/ack", 1000, b"{}", None, now=1000)  # type: ignore[arg-type]


def test_the_vector_file_matches_the_signer():
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert len(vectors) >= 8
    for v in vectors:
        body = bytes.fromhex(v["body"])
        assert relay_sig.sign(bytes.fromhex(v["key"]), v["method"], v["path"], v["timestamp"], body) == v["signature"]  # fmt: skip


def test_an_age_identity_from_raw_round_trips_and_names_its_key_id():
    raw = bytes(range(1, 33))
    identity = age.identity_from_raw(raw)
    assert identity.startswith("AGE-SECRET-KEY-1")
    assert age.decrypt(age.encrypt(b"x", age.recipient_of(identity)), identity) == b"x"
    public = X25519PrivateKey.from_private_bytes(raw).public_key().public_bytes_raw()
    assert key_id_for("relay-age-key", raw) == "x25519:sha256:" + hashlib.sha256(public).hexdigest()
    assert key_id_for("relay-pull-key", KEY) == "hmac:sha256:" + hashlib.sha256(KEY).hexdigest()
