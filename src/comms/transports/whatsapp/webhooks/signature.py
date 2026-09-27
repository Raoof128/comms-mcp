"""Meta's ``X-Hub-Signature-256`` rule: the one copy (comms v0.3 A36, A48).

``sha256=`` followed by the lowercase hex HMAC-SHA256 of the exact raw bytes under the app
secret, compared in constant time. The local listener and the relay collector both import it;
the relay itself never holds the app secret (D-R1).
"""

from __future__ import annotations

import hashlib
import hmac

__all__ = ["meta_signed"]

_PREFIX = b"sha256="


def meta_signed(secret: bytes, raw: bytes, header: bytes | None) -> bool:
    if not secret or header is None or not header.startswith(_PREFIX):
        return False
    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest().encode()
    return hmac.compare_digest(header[len(_PREFIX) :], expected)
