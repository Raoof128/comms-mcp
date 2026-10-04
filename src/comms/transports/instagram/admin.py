"""The Instagram writes (proposed A49, sections 5.2, 5.3, 7, 8): ``AdminOperations`` for the
``instagram`` actor.

Arguments are refs (``igc_``, ``igm_``, ``igp_``) and text, never a provider id, so a request's
digest and the audit chain carry no identity; ``invoke`` resolves each ref inside the account
the target names (a ref of another account is ``NOT_FOUND``). ``validate`` checks shapes only and
touches nothing. Every write is one Graph call, classified by ``IG_CODES``; comms never retries a
CREATE (5.3), and Meta's answer is final (A25).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from comms.core import refs
from comms.core.errors import CommsError
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderResult, ProviderTarget, SemanticOperation
from comms.transports.instagram import store
from comms.transports.instagram.accounts import ACTOR, AccountRuntime, InstagramAccounts
from comms.transports.instagram.classify import write_call

__all__ = ["COMMENT_MAX", "DM_MAX_BYTES", "InstagramAdmin"]

COMMENT_MAX = 2200  # characters, as a caption ℹ️
DM_MAX_BYTES = 1000  # UTF-8 bytes ✅
_REF_ARGS: Mapping[C, Mapping[str, str]] = {
    C.COMMENT_REPLY: {"comment": "instagram_comment"},
    C.COMMENT_HIDE: {"comment": "instagram_comment"},
    C.COMMENT_DELETE: {"comment": "instagram_comment"},
    C.MEDIA_COMMENTS_TOGGLE: {"media": "instagram_media"},
    C.MESSAGE_REPLY: {"person": "instagram_person"},
}
_KIND = {"instagram_comment": "comment", "instagram_media": "media", "instagram_person": "person"}


def _text(value: object, *, chars: int | None = None, utf8: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError("text refused")
    if chars is not None and len(value) > chars:
        raise ValueError("text too long")
    if utf8 is not None and len(value.encode("utf-8")) > utf8:
        raise ValueError("text too long")
    return value


class InstagramAdmin:
    def __init__(self, accounts: InstagramAccounts, conn: Any, *, clock: Callable[[], datetime]):
        self._accounts, self._conn, self._clock = accounts, conn, clock
        self._extra: dict[C, Callable[[SemanticOperation, AccountRuntime], ProviderResult]] = {}

    def __repr__(self) -> str:
        return "InstagramAdmin(<redacted>)"

    def register(
        self, capability: C, call: Callable[[SemanticOperation, AccountRuntime], ProviderResult]
    ) -> None:
        """A later family's writes (publishing, IG-4) join the same adapter."""
        self._extra[capability] = call

    # -- AdminOperations ---------------------------------------------------------------------

    def validate(self, op: SemanticOperation, target: ProviderTarget) -> None:
        if target.actor != ACTOR:
            raise ValueError("not an instagram target")
        a, cap = op.args, op.capability
        for name, kind in _REF_ARGS.get(cap, {}).items():
            refs.check(a.get(name), kind)
        if cap is C.COMMENT_REPLY:
            _text(a.get("text"), chars=COMMENT_MAX)
        elif cap is C.COMMENT_HIDE:
            if not isinstance(a.get("hide"), bool):
                raise ValueError("hide is true or false")
        elif cap is C.MEDIA_COMMENTS_TOGGLE:
            if not isinstance(a.get("enabled"), bool):
                raise ValueError("enabled is true or false")
        elif cap is C.MESSAGE_REPLY:
            _text(a.get("text"), utf8=DM_MAX_BYTES)
        elif cap is C.COMMENT_DELETE:
            pass
        elif cap not in self._extra:
            raise NotImplementedError

    def invoke(self, op: SemanticOperation, target: ProviderTarget, op_key: str) -> ProviderResult:
        runtime = self._accounts.by_ref(target.destination_ref)
        if runtime is None:
            return ProviderResult("FAILED", "NOT_CONFIGURED")
        try:
            ids = {
                name: store.resolve_object(
                    self._conn, op.args[name], _KIND[kind], runtime.account_id
                )
                for name, kind in _REF_ARGS.get(op.capability, {}).items()
            }
        except CommsError as refused:
            return ProviderResult("FAILED", refused.code)
        api, a, cap = runtime.api, op.args, op.capability
        if cap is C.COMMENT_REPLY:
            return write_call(
                lambda: api.post(ids["comment"], "replies", body={"message": a["text"]})
            )
        if cap is C.COMMENT_HIDE:
            hide = "true" if a["hide"] else "false"
            return write_call(lambda: api.post(ids["comment"], params={"hide": hide}), ref_key=None)
        if cap is C.MEDIA_COMMENTS_TOGGLE:
            on = "true" if a["enabled"] else "false"
            return write_call(
                lambda: api.post(ids["media"], params={"comment_enabled": on}), ref_key=None
            )
        if cap is C.COMMENT_DELETE:
            return write_call(lambda: api.delete(ids["comment"]), ref_key=None)
        if cap is C.MESSAGE_REPLY:
            body = {"recipient": {"id": ids["person"]}, "message": {"text": a["text"]}}
            return write_call(
                lambda: api.post(runtime.user_id, "messages", body=body), ref_key="message_id"
            )
        extra = self._extra.get(cap)
        if extra is None:
            return ProviderResult("FAILED", "PROVIDER_UNSUPPORTED")
        return extra(op, runtime)
