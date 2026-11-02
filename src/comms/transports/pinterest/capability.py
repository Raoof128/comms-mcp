"""The Pinterest capability snapshot (proposed A50, 4.3, 4.5; P §9; A25).

A snapshot is per account (``destination_ref`` is the ``pna_``). Without the account, every
capability is ``NOT_CONFIGURED``; an account blocked by an identity mismatch is ``UNAVAILABLE``.
Reads are ``AVAILABLE``; a write is ``AVAILABLE`` only where the account's ``comms.json`` ceiling
allows it (``writes``), else ``NOT_AUTHORIZED``. Snapshots are advisory: Pinterest's answer to a
write is final (A25).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from comms.core import timeutil
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import CapabilitySnapshot, ProviderTarget
from comms.core.providers.semantics import SUPPORT, is_write
from comms.transports.pinterest.accounts import ACTOR, PinterestAccounts

__all__ = ["PINTEREST_CAPABILITIES", "PinterestCapability"]

PINTEREST_CAPABILITIES = tuple(c for c in C if ACTOR in SUPPORT[c])


class PinterestCapability:
    def __init__(self, accounts: PinterestAccounts | None, *, clock: Callable[[], datetime]):
        self._accounts, self._clock = accounts, clock

    def __repr__(self) -> str:
        return "PinterestCapability(<redacted>)"

    def snapshot(self, actor: str, destination: ProviderTarget) -> CapabilitySnapshot:
        if actor != ACTOR or destination.actor != ACTOR:
            raise ValueError("not a pinterest destination")
        stamp = timeutil.iso(self._clock())
        runtime = (
            None if self._accounts is None else self._accounts.by_ref(destination.destination_ref)
        )
        if runtime is None:
            states = dict.fromkeys(PINTEREST_CAPABILITIES, S.NOT_CONFIGURED)
        elif self._accounts is not None and self._accounts.blocked(runtime.alias):
            states = dict.fromkeys(PINTEREST_CAPABILITIES, S.UNAVAILABLE)
        else:
            states = {
                cap: S.AVAILABLE if not is_write(cap) or runtime.policy.writes else S.NOT_AUTHORIZED
                for cap in PINTEREST_CAPABILITIES
            }
        return CapabilitySnapshot(ACTOR, destination.destination_ref, states, stamp)
