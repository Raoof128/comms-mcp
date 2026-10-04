"""The Instagram capability snapshot (proposed A49, 4.3, 4.5; P §9; A25).

A snapshot is per account (``destination_ref`` is the ``iga_``). Without the account, every
capability is ``NOT_CONFIGURED``; an account blocked by an identity mismatch is
``UNAVAILABLE``. Reads are ``AVAILABLE``; a write is ``AVAILABLE`` only where the account's
``comms.json`` ceiling allows it (``writes``; ``dms`` for the DM reply), else
``NOT_AUTHORIZED``. Snapshots are advisory: Meta's answer to a write is final (A25).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from comms.core import timeutil
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import CapabilitySnapshot, ProviderTarget
from comms.core.providers.semantics import SUPPORT, is_write
from comms.transports.instagram.accounts import ACTOR, InstagramAccounts

__all__ = ["INSTAGRAM_CAPABILITIES", "InstagramCapability"]

INSTAGRAM_CAPABILITIES = tuple(c for c in C if ACTOR in SUPPORT[c])


class InstagramCapability:
    def __init__(self, accounts: InstagramAccounts | None, *, clock: Callable[[], datetime]):
        self._accounts, self._clock = accounts, clock

    def __repr__(self) -> str:
        return "InstagramCapability(<redacted>)"

    def snapshot(self, actor: str, destination: ProviderTarget) -> CapabilitySnapshot:
        if actor != ACTOR or destination.actor != ACTOR:
            raise ValueError("not an instagram destination")
        stamp = timeutil.iso(self._clock())
        runtime = (
            None if self._accounts is None else self._accounts.by_ref(destination.destination_ref)
        )
        if runtime is None:
            states = dict.fromkeys(INSTAGRAM_CAPABILITIES, S.NOT_CONFIGURED)
        elif self._accounts is not None and self._accounts.blocked(runtime.alias):
            states = dict.fromkeys(INSTAGRAM_CAPABILITIES, S.UNAVAILABLE)
        else:
            states = {}
            for cap in INSTAGRAM_CAPABILITIES:
                if not is_write(cap):
                    states[cap] = S.AVAILABLE
                elif cap is C.MESSAGE_REPLY:
                    states[cap] = S.AVAILABLE if runtime.policy.dms else S.NOT_AUTHORIZED
                else:
                    states[cap] = S.AVAILABLE if runtime.policy.writes else S.NOT_AUTHORIZED
        return CapabilitySnapshot(ACTOR, destination.destination_ref, states, stamp)
