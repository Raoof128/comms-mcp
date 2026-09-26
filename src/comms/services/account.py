"""Account services (comms v0.3 Task D17; P §34): why an operation is or is not possible.

``status`` summarises each actor's capability snapshot: whether it is configured, how many
capabilities are available, and the reasons for the rest, counted by state. It names no
account identity; that is ``admin.identity.inspect``'s alone. ``webhook_status`` reports
whether the webhook ingress is configured and the inbox's pending and completed counts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from comms.core.errors import CommsError
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import ProviderTarget
from comms.services.capability import CapabilityService

__all__ = ["AccountService", "WebhookState"]


class WebhookState(Protocol):
    def counts(self) -> Mapping[str, Any]: ...


Reader = Callable[[], Mapping[str, Any] | None]
_KIND = {"telegram_bot": "bot", "telegram_user": "user", "whatsapp_cloud": "whatsapp_business"}
_PROFILE_FIELDS = frozenset({"name", "about", "description", "vertical"})


class AccountService:
    def __init__(
        self,
        capability: CapabilityService,
        *,
        webhooks: WebhookState,
        profiles: Mapping[str, Reader] | None = None,
        phone: Reader | None = None,
        health: Reader | None = None,
    ) -> None:
        self._capability, self._webhooks = capability, webhooks
        self._profiles, self._phone, self._health = dict(profiles or {}), phone, health

    def profile(self, actors: tuple[str, ...]) -> dict[str, Any]:
        """G8: each account's kind and what it calls itself, untrusted; never an identity."""
        out = {}
        for actor, kind in _KIND.items():
            read = self._profiles.get(actor)
            if read is None or actor not in actors:
                out[actor] = {"configured": False, "kind": kind, "reachable": None, "untrusted": {}}
                continue
            got = read() or {}
            untrusted = dict(got.get("untrusted") or {})
            out[actor] = {
                "configured": True,
                "kind": kind,
                "reachable": bool(got.get("reachable")),
                "untrusted": {k: v for k, v in untrusted.items() if k in _PROFILE_FIELDS},
            }
        return {"actors": out}

    def phone_status(self) -> dict[str, Any]:
        """G8: the business number's quality rating and status — not the number."""
        got = self._read(self._phone)
        return {"quality_rating": got.get("quality_rating"), "status": got.get("status")}

    def health_status(self) -> dict[str, Any]:
        """A46: whether the number can send messages, overall and per entity; no ids."""
        return dict(self._read(self._health))

    @staticmethod
    def _read(reader: Reader | None) -> Mapping[str, Any]:
        if reader is None:
            raise CommsError("NOT_CONFIGURED")
        got = reader()
        if got is None:
            raise CommsError("PROVIDER_UNAVAILABLE")
        return got

    def status(self, targets: Mapping[str, ProviderTarget]) -> dict[str, Any]:
        actors = {}
        for actor in sorted(targets):
            states = self._capability.snapshot(actor, targets[actor], refresh=True).states
            reasons: dict[str, int] = {}
            for state in states.values():
                if state is not S.AVAILABLE:
                    reasons[state.value] = reasons.get(state.value, 0) + 1
            actors[actor] = {
                "configured": S.NOT_CONFIGURED.value not in reasons
                or reasons[S.NOT_CONFIGURED.value] < len(states),
                "available": sum(state is S.AVAILABLE for state in states.values()),
                "reasons": reasons,
            }
        return {"actors": actors}

    def webhook_status(self) -> dict[str, Any]:
        counts = self._webhooks.counts()
        return {
            "configured": bool(counts.get("configured")),
            "pending": int(counts.get("pending", 0)),
            "completed": int(counts.get("completed", 0)),
        }
