"""The relay's pull signature (comms v0.3 A48): the one Python copy.

``hex(HMAC-SHA256(key, "comms-relay-pull/v1\\0" ‖ method ‖ "\\0" ‖ path ‖ "\\0" ‖ timestamp
‖ "\\0" ‖ body))``. The Worker's TypeScript copy (``relay/src/pull_sig.ts``) is bound to this
one by ``tests/fixtures/relay/pull_signature_vectors.json``, byte for byte.
"""

from __future__ import annotations

import hashlib
import hmac

from comms.core import domains

__all__ = ["WINDOW_SECONDS", "sign", "verify"]

WINDOW_SECONDS = 300


def _message(method: str, path: str, timestamp: int, body: bytes) -> bytes:
    parts = (method.encode("ascii"), path.encode("ascii"), str(int(timestamp)).encode("ascii"))
    return domains.RELAY_PULL + b"\0".join((*parts, body))


def sign(key: bytes, method: str, path: str, timestamp: int, body: bytes) -> str:
    return hmac.new(key, _message(method, path, timestamp, body), hashlib.sha256).hexdigest()


def verify(
    key: bytes,
    method: str,
    path: str,
    timestamp: int,
    body: bytes,
    signature: str,
    *,
    now: int,
    window: int = WINDOW_SECONDS,
) -> bool:
    if not isinstance(signature, str) or abs(int(now) - int(timestamp)) > window:
        return False
    return hmac.compare_digest(sign(key, method, path, timestamp, body), signature)
