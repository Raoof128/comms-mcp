"""Pinterest outcomes by HTTP status (proposed A50, section 8; A19).

Pinterest answers ``{"code": <int>, "message": "…"}`` with a status; the message is untrusted and
never leaves comms. A 2xx with a JSON object is a success; 400 and 409 are refusals a resend
cannot fix; 401 is a credential the owner refreshes; 403 is not authorized; 404 not found; 429
rate limited; a 5xx, a non-JSON body and any transport failure after connecting are
``OUTCOME_UNKNOWN``; a connection never made is ``PROVIDER_UNAVAILABLE``. comms never retries a
CREATE (5.3): "transient" tells the owner the same call may be repeated with a new
``request_id``. Reads have their own mapping: a read is never an outcome, only an answer or a
fixed ``CommsError`` code.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from comms.core.delivery.transport import ResultKind
from comms.core.errors import CommsError
from comms.core.providers.protocols import ProviderResult
from comms.transports.pinterest.http import GraphResponse, GraphTransportError, PinterestApi

__all__ = ["STATUS_CODES", "api_read", "classify_write", "read_refusal", "write_call"]

_T, _P, _U = ResultKind.FAILED_TRANSIENT, ResultKind.FAILED_PERMANENT, ResultKind.OUTCOME_UNKNOWN
STATUS_CODES = MappingProxyType(
    {
        400: (_P, "INVALID_ARGUMENT"),
        401: (_T, "CREDENTIAL"),
        403: (_P, "NOT_AUTHORIZED"),
        404: (_P, "NOT_FOUND"),
        409: (_P, "INVALID_ARGUMENT"),
        429: (_T, "RATE_LIMITED"),
    }
)
_REF = re.compile(r"\A[0-9]{1,24}\Z")  # a created object's id, never path syntax
_READ_CODES = MappingProxyType(
    {
        400: "INVALID_ARGUMENT",
        401: "NOT_AUTHORIZED",
        403: "NOT_AUTHORIZED",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
    }
)


def classify_write(
    outcome: GraphResponse | GraphTransportError, *, ref_key: str | None = "id"
) -> ProviderResult:
    """A write's verdict. ``ref_key`` names the field a success must carry as its provider ref
    (``id`` for a Pin or a board, ``media_id`` for an upload); ``None`` for a write whose
    success is the status alone (a delete)."""
    if isinstance(outcome, GraphTransportError):
        if outcome.stage == "not_sent":
            return ProviderResult("FAILED", "PROVIDER_UNAVAILABLE")
        return ProviderResult("OUTCOME_UNKNOWN", None)
    status, envelope = outcome.http_status, outcome.envelope
    if status >= 500 or envelope is None:
        return ProviderResult("OUTCOME_UNKNOWN", None)
    if 200 <= status < 300:
        if ref_key is None:
            return ProviderResult("SUCCEEDED", None)
        ref = envelope.get(ref_key)
        if isinstance(ref, int) and not isinstance(ref, bool):
            ref = str(ref)
        if isinstance(ref, str) and _REF.match(ref):
            return ProviderResult("SUCCEEDED", None, provider_ref=ref)
        return ProviderResult("OUTCOME_UNKNOWN", None)  # created, but nothing to name it by
    kind, name = STATUS_CODES.get(status, (_U, None))
    if kind is _U:
        return ProviderResult("OUTCOME_UNKNOWN", None)
    return ProviderResult("FAILED", name)


def write_call(call: Callable[[], GraphResponse], *, ref_key: str | None = "id") -> ProviderResult:
    """Make one write call and classify it (one copy for every Pinterest write)."""
    try:
        outcome: GraphResponse | GraphTransportError = call()
    except GraphTransportError as exc:
        outcome = exc
    return classify_write(outcome, ref_key=ref_key)


def read_refusal(response: GraphResponse) -> str:
    """The fixed code a failed read answers."""
    if response.http_status >= 500:
        return "PROVIDER_UNAVAILABLE"
    return _READ_CODES.get(response.http_status, "PROVIDER_UNAVAILABLE")


def api_read(api: PinterestApi, call: Callable[[], GraphResponse]) -> dict[str, Any]:
    """Make one read call; its JSON object, or a fixed ``CommsError`` (a rate limit carries the
    seconds to wait when Pinterest said them)."""
    try:
        response = call()
    except GraphTransportError:
        raise CommsError("PROVIDER_UNAVAILABLE") from None
    envelope = response.envelope
    if 200 <= response.http_status < 300 and envelope is not None:
        return dict(envelope)
    code = read_refusal(response)
    if code == "RATE_LIMITED":
        limit = api.last_rate_limit
        wait = limit.reset if limit is not None and limit.reset and limit.reset > 0 else None
        raise CommsError(code, retry_after=wait)
    raise CommsError(code)
