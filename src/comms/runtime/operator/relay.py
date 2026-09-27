"""The owner's relay commands (comms v0.3 A48): local and read-only, like ``comms doctor``.

``recipient`` prints the public ``age1…`` key. ``export-pull-key`` and ``new-path`` write a
secret only into a pipe (``| npx wrangler secret put …``) and refuse a terminal, so a secret
never lands on a screen or in a transcript. ``status`` reports the collector's progress, and
``setup`` prints the ordered checklist. Nothing here writes to the comms state.
"""

from __future__ import annotations

import base64
import secrets
from typing import Any

from comms.core.backup import age
from comms.core.keys.secrets import SecretStoreError
from comms.core.keys.slots import KeySlotError, KeySlotStore, load_active
from comms.core.storage.db import CommsDbKeyError
from comms.runtime.doctor import open_read_only
from comms.runtime.paths import CommsPaths

__all__ = ["RelayOpRefused", "new_path_token", "pull_key_hex", "recipient", "setup_text", "status"]


class RelayOpRefused(Exception):
    """A relay command refused; the message is fixed and names the fix."""


def _key(paths: CommsPaths, purpose: str) -> bytes:
    if not paths.db.exists() or not paths.db_key_pointer.exists():
        raise RelayOpRefused("comms is not provisioned (run: comms keys provision)")
    try:
        conn = open_read_only(paths)
    except (CommsDbKeyError, SecretStoreError):
        raise RelayOpRefused("the comms database key does not open comms.db") from None
    try:
        material, _key_id = load_active(conn, KeySlotStore(paths.slots_dir), purpose)
    except KeySlotError:
        raise RelayOpRefused("the relay keys are missing (run: comms keys provision)") from None
    finally:
        conn.close()
    return material


def recipient(paths: CommsPaths) -> str:
    return age.recipient_of(age.identity_from_raw(_key(paths, "relay-age-key")))


def pull_key_hex(paths: CommsPaths) -> str:
    return _key(paths, "relay-pull-key").hex()


def new_path_token() -> str:
    """32 random bytes, base64url: the secret part of Meta's callback URL."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def status(paths: CommsPaths) -> dict[str, Any]:
    if not paths.db.exists() or not paths.db_key_pointer.exists():
        raise RelayOpRefused("comms is not provisioned (run: comms keys provision)")
    try:
        conn = open_read_only(paths)
    except (CommsDbKeyError, SecretStoreError):
        raise RelayOpRefused("the comms database key does not open comms.db") from None
    try:
        row = conn.execute(
            "SELECT acked_through, purged_through, depth, oldest_received_at, last_success_at,"
            " last_error FROM relay_state WHERE id = 1"
        ).fetchone()
        quarantined = conn.execute("SELECT count(*) FROM relay_quarantine").fetchone()[0]
        gaps = conn.execute("SELECT count(*) FROM relay_gaps").fetchone()[0]
    finally:
        conn.close()
    names = ("acked_through", "purged_through", "depth", "oldest_received_at", "last_success_at",
             "last_error")  # fmt: skip
    values = row if row is not None else (0, 0, None, None, None, None)
    return {**dict(zip(names, values, strict=True)), "quarantined": quarantined, "gaps": gaps}


_SETUP = """\
The WhatsApp relay (spec A48). Run each step yourself, in your own terminal.

1. cd relay && npm ci && npx wrangler login
2. comms relay export-pull-key | npx wrangler secret put RELAY_PULL_KEY
3. comms relay recipient | npx wrangler secret put RELAY_AGE_RECIPIENT
4. comms relay new-path | tee /dev/tty | npx wrangler secret put RELAY_PATH_TOKEN
   (keep the token shown: it is the end of Meta's callback URL)
5. npx wrangler secret put META_VERIFY_TOKEN   (type a new random value)
6. npx wrangler deploy
7. In Meta's WhatsApp Configuration, set the callback URL to
   https://comms-relay.<your-subdomain>.workers.dev/webhooks/meta/<token from step 4>
   and the verify token to the value from step 5.
8. Add to comms.json: "relay": {"url": "https://comms-relay.<your-subdomain>.workers.dev"}
   (and remove webhook_port), then restart the daemon.
9. comms relay status   and   comms doctor

Meta's app secret never goes to Cloudflare (D-R1): only the daemon verifies it."""


def setup_text() -> str:
    return _SETUP
