"""Message services (comms v0.3 Task D14; P §23, §72, §77).

Writes go through the one provider write path (``ProviderWrites``). The actor is chosen by
capability and preference: "send it as me" is ``actor="telegram_user"`` and never falls back
to the bot. A message is named by its ``cmg_`` ref — the same ref the context engine mints for
it — and must belong to the group acted on. A sent message comes back as its ref.

Deletion reports its scope as the provider reported it (``local``, ``everyone``); when the
provider says nothing it is ``provider_defined``, and a delete that did not succeed claims no
scope (P §72). Marking read is a write of its own, audited, and no read ever marks anything
(P §77). The reads themselves (get, recent, search, context) are the context engine's.

WhatsApp: ``mark_read`` only. Free-form WhatsApp sends go through the campaign path, which
enforces the customer-service window and templates; forwarding is not offered yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from comms.core.errors import CommsError
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderTarget
from comms.services.capability import CapabilityService
from comms.services.mutations import CallContext, MutationExecutor, MutationOutcome
from comms.services.writes import ProviderWrites, summary, transport_of

__all__ = ["DELETE_SCOPES", "MessageService"]

DELETE_SCOPES = ("local", "everyone", "provider_defined")
_MESSAGE = ("message", "message_id")
_TEXT_MAX = 4096
# tool → the capability that performs it on each transport (P §23).
_OPERATIONS: Mapping[str, Mapping[str, C]] = {
    "message.send": {"telegram": C.MESSAGE_SEND, "whatsapp": C.GROUP_MESSAGE_SEND},  # G8
    "message.reply": {"telegram": C.MESSAGE_SEND},
    "message.edit": {"telegram": C.MESSAGE_EDIT},
    "message.delete": {"telegram": C.MESSAGE_DELETE},
    "message.pin": {"telegram": C.MESSAGE_PIN, "whatsapp": C.MESSAGE_PIN},  # G8
    "message.unpin": {"telegram": C.MESSAGE_PIN, "whatsapp": C.MESSAGE_PIN},
    "message.mark_read": {"whatsapp": C.MESSAGE_MARK_READ},
    "message.forward": {"telegram": C.MESSAGE_FORWARD},  # G7
}


def _text(text: object) -> str:
    if not isinstance(text, str) or not text.strip() or len(text) > _TEXT_MAX:
        raise CommsError("INVALID_ARGUMENT")
    return text


class MessageService:
    def __init__(
        self, conn: Any, capability: CapabilityService, executor: MutationExecutor
    ) -> None:
        self._writes = ProviderWrites(conn, capability, executor)

    def send(
        self,
        ctx: CallContext,
        group: str,
        targets: Mapping[str, ProviderTarget],
        text: str,
        request_id: str,
        *,
        actor: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        tool = "message.send" if reply_to is None else "message.reply"
        objects = {} if reply_to is None else {("message", "reply_to_message_id"): reply_to}
        chosen, outcome = self._run(
            ctx, tool, targets, {"text": _text(text)}, request_id, actor, objects, "message"
        )
        return {**self._head(group, tool, chosen, outcome), "message": _made(outcome)}

    def edit(
        self,
        ctx: CallContext,
        group: str,
        targets: Mapping[str, ProviderTarget],
        message: str,
        text: str,
        request_id: str,
        *,
        actor: str | None = None,
    ) -> dict[str, Any]:
        chosen, outcome = self._run(
            ctx,
            "message.edit",
            targets,
            {"text": _text(text)},
            request_id,
            actor,
            {_MESSAGE: message},
        )
        return self._head(group, "message.edit", chosen, outcome)

    def delete(
        self,
        ctx: CallContext,
        group: str,
        targets: Mapping[str, ProviderTarget],
        message: str,
        request_id: str,
        *,
        scope: str = "everyone",
        actor: str | None = None,
    ) -> dict[str, Any]:
        if scope not in ("local", "everyone"):
            raise CommsError("INVALID_ARGUMENT")
        chosen, outcome = self._run(
            ctx,
            "message.delete",
            targets,
            {"revoke": scope == "everyone"},
            request_id,
            actor,
            {_MESSAGE: message},
        )
        reported = None
        if outcome.state == "SUCCEEDED":  # never a scope the provider did not report
            reported = outcome.result.get("scope") or "provider_defined"
        return {**self._head(group, "message.delete", chosen, outcome), "scope": reported}

    def pin(
        self,
        ctx: CallContext,
        group: str,
        targets: Mapping[str, ProviderTarget],
        message: str,
        request_id: str,
        *,
        pinned: bool = True,
        actor: str | None = None,
        expire_days: int | None = None,
    ) -> dict[str, Any]:
        """A pin; ``expire_days`` (1-30) is WhatsApp's, which requires days to pin (G8)."""
        tool = "message.pin" if pinned else "message.unpin"
        args: dict[str, Any] = {"pinned": pinned}
        if expire_days is not None:
            if transport_of(targets) != "whatsapp" or not pinned:
                raise CommsError("INVALID_ARGUMENT")
            args["expire_days"] = expire_days
        chosen, outcome = self._run(
            ctx, tool, targets, args, request_id, actor, {_MESSAGE: message}
        )
        return self._head(group, tool, chosen, outcome)

    def mark_read(
        self,
        ctx: CallContext,
        subject: str,
        targets: Mapping[str, ProviderTarget],
        message: str,
        request_id: str,
    ) -> dict[str, Any]:
        chosen, outcome = self._run(
            ctx, "message.mark_read", targets, {}, request_id, None, {_MESSAGE: message}
        )
        return self._head(subject, "message.mark_read", chosen, outcome)

    def forward(
        self,
        ctx: CallContext,
        to_group: str,
        targets: Mapping[str, ProviderTarget],
        from_chat: str,
        message_id: int,
        request_id: str,
        *,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """``message.forward`` (G7): one message of another group, as a new message in this one.
        ``targets`` are the actors present in both groups; the new message gets a ``cmg_`` ref
        in this group."""
        chosen, outcome = self._run(
            ctx, "message.forward", targets, {"from_chat": from_chat, "message_id": message_id},
            request_id, actor, {}, "message",
        )  # fmt: skip
        return {**self._head(to_group, "message.forward", chosen, outcome),
                "message": _made(outcome)}  # fmt: skip

    def _run(
        self,
        ctx: CallContext,
        tool: str,
        targets: Mapping[str, ProviderTarget],
        args: Mapping[str, Any],
        request_id: str,
        actor: str | None,
        objects: Mapping[tuple[str, str], object],
        object_kind: str | None = None,
    ) -> tuple[str, MutationOutcome]:
        if not targets:
            raise CommsError("INVALID_ARGUMENT")
        capability = _OPERATIONS[tool].get(transport_of(targets))
        if capability is None:
            raise CommsError("PROVIDER_UNSUPPORTED")
        chosen, _target, outcome = self._writes.write(
            ctx,
            tool,
            targets,
            capability,
            args,
            request_id,
            actor,
            objects=objects,
            object_kind=object_kind,
        )
        return chosen, outcome

    @staticmethod
    def _head(group: str, tool: str, actor: str, outcome: MutationOutcome) -> dict[str, Any]:
        return {"group": group, "operation": tool, **summary(actor, outcome)}


def _made(outcome: MutationOutcome) -> str | None:
    ref = outcome.result.get("object_ref")
    return ref if isinstance(ref, str) else None
