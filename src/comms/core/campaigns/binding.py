"""A directory identity bound to a request without being recoverable from it (catalog amendment
G3; A26, D1).

A mutation's request digest is an unkeyed SHA-256 of its arguments, and it reaches the audit
chain. A phone number or a Telegram user id is low-entropy, so an unkeyed hash of one could be
brute-forced back to it. A directory write that takes an identity therefore binds its request to
``HMAC(campaign-commit-key, "comms-directory-identity/v1\\0" ‖ JCS({identity, transport}))``: a
different identity under the same ``req_`` id is still ``REQUEST_ID_REUSE``, and the chain holds
nothing an attacker without the key can test a guess against. After the key rotates, a replay of
an older request binds differently and is refused rather than repeated (fail closed).
"""

from __future__ import annotations

import hashlib
import hmac

from comms.core import domains
from comms.core.canonical import jcs_dumps

__all__ = ["identity_binding"]


def identity_binding(key: bytes, transport: str, identity: str) -> str:
    body = jcs_dumps({"identity": identity, "transport": transport})
    return hmac.new(key, domains.DIRECTORY_IDENTITY + body, hashlib.sha256).hexdigest()
