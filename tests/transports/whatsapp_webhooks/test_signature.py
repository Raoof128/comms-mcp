"""Spec A48 (Task R1): Meta's webhook signature rule has one copy, shared by the local listener
and the relay collector."""

import ast
import hashlib
import hmac
from pathlib import Path

import httpx

from comms.transports.whatsapp.webhooks import ingress
from comms.transports.whatsapp.webhooks.ingress import MAX_BODY_BYTES, WebhookIngress
from comms.transports.whatsapp.webhooks.signature import meta_signed

SECRET = b"fixture-app-secret"
BODY = b'{"object":"whatsapp_business_account","entry":[]}'
ROOT = Path(__file__).resolve().parents[3]


def _header(body: bytes, secret: bytes = SECRET) -> bytes:
    return b"sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest().encode()


def test_a_correct_signature_verifies():
    assert meta_signed(SECRET, BODY, _header(BODY))


def test_every_malformed_or_wrong_signature_is_refused():
    good = _header(BODY)
    for header in (
        None,
        b"",
        good[len(b"sha256=") :],  # no prefix
        b"sha1=" + good[len(b"sha256=") :],
        b"sha256=" + good[len(b"sha256=") :].upper(),
        good[:-2],
        good + b"00",
        _header(BODY, b"another-secret"),
        _header(BODY + b" "),
    ):
        assert not meta_signed(SECRET, BODY, header), header


def test_an_empty_secret_never_verifies():
    assert not meta_signed(b"", BODY, _header(BODY, b""))


def test_the_rule_has_one_copy():
    """No module but ``signature.py`` computes an HMAC over a webhook body."""
    for path in (ROOT / "src" / "comms").rglob("*.py"):
        if path.name == "signature.py" or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "x-hub-signature-256" not in text.lower() and "sha256=" not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Attribute) and node.attr == "new":
                base = node.value
                assert not (isinstance(base, ast.Name) and base.id == "hmac"), path
    assert not hasattr(ingress.WebhookIngress, "_signed")


async def test_the_local_listener_accepts_a_signed_two_mib_batch():
    """Meta sets no size limit and batches up to 1000 updates; the relay keeps up to 8 MiB."""
    assert MAX_BODY_BYTES == 8 * 1024 * 1024
    accepted: list[bytes] = []

    async def accept(raw: bytes) -> None:
        accepted.append(raw)

    app = WebhookIngress(app_secret=SECRET, verify_token="t", accept=accept, clock=lambda: 0.0)
    big = b'{"object":"whatsapp_business_account","entry":["' + b"x" * (2 * 1024 * 1024) + b'"]}'
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://hooks.example"
    ) as client:
        response = await client.post(
            "/webhooks/meta",
            content=big,
            headers={
                "content-type": "application/json",
                "x-hub-signature-256": _header(big).decode(),
            },
        )
    assert response.status_code == 200 and accepted == [big]
