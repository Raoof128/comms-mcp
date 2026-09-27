"""The Telegram capability ids (P §11), shared by the bot and user capability providers."""

from __future__ import annotations

from comms.core.providers.capability import Capability
from comms.core.providers.semantics import SUPPORT

__all__ = ["ACCOUNT_TARGET", "TELEGRAM_CAPABILITIES"]

# The identity of an account-level target (no chat): account status, group create, upload.
ACCOUNT_TARGET = "account"

TELEGRAM_CAPABILITIES = tuple(
    c for c in Capability if set(SUPPORT[c]) & {"telegram_bot", "telegram_user"}
)
