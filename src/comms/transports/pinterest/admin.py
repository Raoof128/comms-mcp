"""The Pinterest writes (proposed A50, sections 5.2, 6, 8): ``AdminOperations`` for the
``pinterest`` actor.

Arguments are refs (``pnb_``, ``pnp_``, ``pnv_``), texts and URLs, never a provider id, so a
request's digest and the audit chain carry no identity; ``invoke`` resolves each ref inside the
account the target names (a ref of another account is ``NOT_FOUND``). ``validate`` checks shapes
only and touches nothing. A board and a Pin are one call each; a video upload is the register
and the one upload; a video Pin reads the upload's status once first (D-P7). comms never retries
a CREATE, and Pinterest's answer is final (A25).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from comms.core.errors import CommsError
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderResult, ProviderTarget, SemanticOperation
from comms.transports.pinterest import store, upload
from comms.transports.pinterest.accounts import ACTOR, AccountRuntime, PinterestAccounts
from comms.transports.pinterest.classify import api_read, classify_write, write_call
from comms.transports.pinterest.http import GraphTransportError
from comms.transports.pinterest.items import media_status
from comms.transports.pinterest.publish import (
    check_board_create,
    check_pin_create,
    check_pin_delete,
    check_pin_update,
    check_video_upload,
    pin_body,
    pin_update_body,
)

__all__ = ["NOT_READY", "PinterestAdmin"]

NOT_READY = {
    "registered": "MEDIA_NOT_READY",
    "processing": "MEDIA_NOT_READY",
    "failed": "MEDIA_FAILED",
}
_CHECKS: Mapping[C, Callable[[Mapping[str, Any]], None]] = {
    C.BOARD_CREATE: check_board_create,
    C.MEDIA_UPLOAD: check_video_upload,
    C.PIN_CREATE: check_pin_create,
    C.PIN_UPDATE: check_pin_update,
    C.PIN_DELETE: check_pin_delete,
}


class PinterestAdmin:
    def __init__(
        self,
        accounts: PinterestAccounts,
        conn: Any,
        *,
        clock: Callable[[], datetime],
        transport: Any = None,
    ):
        self._accounts, self._conn, self._clock = accounts, conn, clock
        self._transport = transport  # the upload host's seam (None: the network)

    def __repr__(self) -> str:
        return "PinterestAdmin(<redacted>)"

    # -- AdminOperations ---------------------------------------------------------------------

    def validate(self, op: SemanticOperation, target: ProviderTarget) -> None:
        if target.actor != ACTOR:
            raise ValueError("not a pinterest target")
        check = _CHECKS.get(op.capability)
        if check is None:
            raise NotImplementedError
        check(op.args)

    def invoke(self, op: SemanticOperation, target: ProviderTarget, op_key: str) -> ProviderResult:
        runtime = self._accounts.by_ref(target.destination_ref)
        if runtime is None:
            return ProviderResult("FAILED", "NOT_CONFIGURED")
        try:
            if op.capability is C.BOARD_CREATE:
                return self._board_create(runtime, op.args)
            if op.capability is C.MEDIA_UPLOAD:
                return self._video_upload(runtime, op.args)
            if op.capability is C.PIN_CREATE:
                return self._pin_create(runtime, op.args)
            if op.capability is C.PIN_UPDATE:
                return self._pin_update(runtime, op.args)
            if op.capability is C.PIN_DELETE:
                return self._pin_delete(runtime, op.args)
        except CommsError as refused:  # a ref of another account, or a read that refused
            return ProviderResult("FAILED", refused.code)
        return ProviderResult("FAILED", "PROVIDER_UNSUPPORTED")

    # -- the calls -----------------------------------------------------------------------------

    def _board_create(self, runtime: AccountRuntime, a: Mapping[str, Any]) -> ProviderResult:
        body = {"name": a["name"], "privacy": a.get("privacy", "PUBLIC")}
        if "description" in a:
            body["description"] = a["description"]
        result = write_call(lambda: runtime.api.post("boards", body=body))
        if result.outcome == "SUCCEEDED" and result.provider_ref:
            store.object_ref(
                self._conn, runtime.account_id, "board", result.provider_ref, now=self._clock()
            )
        return result

    def _video_upload(self, runtime: AccountRuntime, a: Mapping[str, Any]) -> ProviderResult:
        """Register, then the one upload. The registration's answer (the signed URL and fields)
        is read here and nowhere else: it never reaches a result, a record or a log."""
        try:
            answer = runtime.api.post("media", body={"media_type": "video"})
        except GraphTransportError as exc:
            return classify_write(exc)
        registered = classify_write(answer, ref_key="media_id")
        if registered.outcome != "SUCCEEDED":
            return registered
        envelope = answer.envelope or {}
        try:
            url, fields = upload.check_target(
                envelope.get("upload_url"), envelope.get("upload_parameters")
            )
        except ValueError:
            return ProviderResult("FAILED", "UPLOAD_FAILED")  # registered, never uploaded
        outcome = upload.upload_video(url, fields, a["data"], a["mime"], transport=self._transport)
        if outcome == "ok":
            assert registered.provider_ref is not None
            store.record_media(  # the ledger row at once, whatever happens to the executor next
                self._conn, runtime.account_id, registered.provider_ref, now=self._clock(),
                status="registered",
            )  # fmt: skip
            return ProviderResult("SUCCEEDED", None, provider_ref=registered.provider_ref)
        if outcome == "refused":
            return ProviderResult("FAILED", "UPLOAD_FAILED")
        return ProviderResult("OUTCOME_UNKNOWN", None)

    def _video_ready(self, runtime: AccountRuntime, ref: str) -> tuple[str, str | None]:
        """The upload's media id, and a failure code when it is not ``succeeded``."""
        row = store.media(self._conn, ref, runtime.account_id)
        body = api_read(runtime.api, lambda: runtime.api.get("media/{id}", row.media_id))
        status = media_status(body)
        if status is None:
            return row.media_id, "PROVIDER_UNAVAILABLE"
        store.mark_media(self._conn, row.ref, status)
        return row.media_id, NOT_READY.get(status)

    def _pin_create(self, runtime: AccountRuntime, a: Mapping[str, Any]) -> ProviderResult:
        board_id = store.resolve_object(self._conn, a["board"], "board", runtime.account_id)
        media_id = None
        if a["kind"] == "video":
            media_id, blocked = self._video_ready(runtime, a["media"])
            if blocked is not None:
                return ProviderResult("FAILED", blocked)
        body = pin_body(a, board_id, media_id)
        result = write_call(lambda: runtime.api.post("pins", body=body))
        if result.outcome == "SUCCEEDED" and result.provider_ref:
            # A created Pin is a ledger row at once (D-P7), so a crash between Pinterest's answer
            # and the executor's record never loses a Pin the budget must count.
            now = self._clock()
            ref = store.object_ref(
                self._conn, runtime.account_id, "pin", result.provider_ref, now=now
            )
            store.record_publication(self._conn, runtime.account_id, ref, now=now)
        return result

    def _pin_update(self, runtime: AccountRuntime, a: Mapping[str, Any]) -> ProviderResult:
        pin_id = store.resolve_object(self._conn, a["pin"], "pin", runtime.account_id)
        board_id = (
            store.resolve_object(self._conn, a["board"], "board", runtime.account_id)
            if "board" in a
            else None
        )
        body = pin_update_body(a, board_id)
        return write_call(lambda: runtime.api.patch("pins/{id}", pin_id, body=body))

    def _pin_delete(self, runtime: AccountRuntime, a: Mapping[str, Any]) -> ProviderResult:
        pin_id = store.resolve_object(self._conn, a["pin"], "pin", runtime.account_id)
        return write_call(lambda: runtime.api.delete("pins/{id}", pin_id), ref_key=None)
