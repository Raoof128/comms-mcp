"""Instagram Graph outcomes by explicit table (proposed A49, section 8; A19).

``IG_CODES`` maps a documented ``(code, error_subcode)`` (or a code alone) to a result kind and
a comms code. Only a documented rejection before acceptance is ``FAILED_TRANSIENT``; a
documented refusal a resend cannot fix is ``FAILED_PERMANENT``; a 5xx, a malformed body, an
undocumented pair, and any transport failure after connecting are ``OUTCOME_UNKNOWN``; a
connection never made is ``FAILED_TRANSIENT``. comms never retries a CREATE (5.3): "transient"
tells the owner the same call may be repeated with a new ``request_id``.

Reads have their own mapping (``read_refusal``): a read is never an outcome, only an answer or a
fixed ``CommsError`` code.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from comms.core.delivery.transport import ResultKind
from comms.core.errors import CommsError
from comms.core.providers.protocols import ProviderResult
from comms.transports.instagram.http import GraphResponse, GraphTransportError

__all__ = ["IG_CODES", "classify_write", "graph_read", "read_refusal", "write_call"]

_T, _P, _U = ResultKind.FAILED_TRANSIENT, ResultKind.FAILED_PERMANENT, ResultKind.OUTCOME_UNKNOWN
_INVALID = (_P, "INVALID_ARGUMENT")
IG_CODES: Mapping[tuple[int, int | str | None], tuple[ResultKind, str | None]] = MappingProxyType(
    {
        (-2, 2207003): (_T, "MEDIA_FETCH_TIMEOUT"),
        (-2, 2207020): (_P, "CONTAINER_EXPIRED"),
        (-1, 2207001): (_U, None),
        (-1, 2207032): (_T, "CONTAINER_FAILED"),
        (-1, 2207053): (_P, "CONTAINER_FAILED"),
        (1, 2207057): _INVALID,
        (4, 2207051): (_P, "SPAM_FLAGGED"),
        (9, 2207042): (_P, "PUBLISH_CAP"),
        (24, 2207006): (_P, "NOT_FOUND"),
        (24, 2207008): (_T, "CONTAINER_NOT_READY"),
        (25, 2207050): (_P, "ACCOUNT_RESTRICTED"),
        (100, 2207023): _INVALID,
        (100, 2207028): _INVALID,
        (100, 2207040): _INVALID,
        (100, "INSTAGRAM_PLATFORM_API__INVALID_LOCATION_ID"): _INVALID,
        (352, 2207026): _INVALID,
        (9004, 2207052): (_P, "MEDIA_FETCH_FAILED"),
        (9007, 2207027): (_T, "CONTAINER_NOT_READY"),
        (36000, 2207004): _INVALID,
        (36001, 2207005): _INVALID,
        (36003, 2207009): _INVALID,
        (36004, 2207010): _INVALID,
        # standard Graph codes, any subcode (gate GI-5 confirms the real values)
        (190, None): (_T, "CREDENTIAL"),
        (4, None): (_T, "RATE_LIMITED"),
        (17, None): (_T, "RATE_LIMITED"),
        (32, None): (_T, "RATE_LIMITED"),
        (613, None): (_T, "RATE_LIMITED"),
    }
)
_ID_KEYS = ("id",)


def _error(envelope: Mapping[str, Any] | None) -> tuple[Any, Any]:
    error = (envelope or {}).get("error")
    if not isinstance(error, dict):
        return None, None
    return error.get("code"), error.get("error_subcode")


def _lookup(code: Any, subcode: Any) -> tuple[ResultKind, str | None]:
    if type(code) is not int:
        return _U, None
    if (code, subcode) in IG_CODES:
        return IG_CODES[(code, subcode)]
    return IG_CODES.get((code, None), (_U, None))


def classify_write(
    outcome: GraphResponse | GraphTransportError, *, ref_key: str | None = "id"
) -> ProviderResult:
    """A write's verdict. ``ref_key`` names the field a success must carry as its provider ref
    (``id`` for a creation); ``None`` for a set-state write answering ``{"success": true}``."""
    if isinstance(outcome, GraphTransportError):
        if outcome.stage == "not_sent":
            return ProviderResult("FAILED", "PROVIDER_UNAVAILABLE")
        return ProviderResult("OUTCOME_UNKNOWN", None)
    envelope = outcome.envelope
    if outcome.http_status >= 500 or envelope is None:
        return ProviderResult("OUTCOME_UNKNOWN", None)
    if outcome.http_status == 200 and "error" not in envelope:
        if ref_key is None:
            ok = envelope.get("success") is True
            return ProviderResult("SUCCEEDED" if ok else "OUTCOME_UNKNOWN", None)
        ref = envelope.get(ref_key)
        if isinstance(ref, int) and not isinstance(ref, bool):
            ref = str(ref)
        if isinstance(ref, str) and ref.isascii() and ref.isdigit() and len(ref) <= 20:
            return ProviderResult("SUCCEEDED", None, provider_ref=ref)
        return ProviderResult("OUTCOME_UNKNOWN", None)
    kind, name = _lookup(*_error(envelope))
    if kind is _U:
        return ProviderResult("OUTCOME_UNKNOWN", None)
    return ProviderResult("FAILED", name)


def write_call(call: Callable[[], GraphResponse], *, ref_key: str | None = "id") -> ProviderResult:
    """Make one write call and classify it (one copy for every Instagram write)."""
    try:
        outcome: GraphResponse | GraphTransportError = call()
    except GraphTransportError as exc:
        outcome = exc
    return classify_write(outcome, ref_key=ref_key)


_READ_CODES = MappingProxyType(
    {
        190: "NOT_AUTHORIZED",
        200: "NOT_AUTHORIZED",
        3: "NOT_AUTHORIZED",
        4: "RATE_LIMITED",
        17: "RATE_LIMITED",
        32: "RATE_LIMITED",
        613: "RATE_LIMITED",
        100: "INVALID_ARGUMENT",
        24: "NOT_FOUND",
        803: "NOT_FOUND",
    }
)


def read_refusal(response: GraphResponse, *, insights: bool = False) -> str:
    """The fixed code a failed read answers. For an insights read, code 10 is "not enough
    viewers" and code 1 is Meta's "unknown error" for an unsupported metric combination."""
    code, _subcode = _error(response.envelope)
    if response.http_status >= 500 or type(code) is not int:
        return "PROVIDER_UNAVAILABLE"
    if insights and code == 10:
        return "NOT_ENOUGH_DATA"
    if insights and code == 1:
        return "INVALID_ARGUMENT"
    if code == 10:
        return "NOT_AUTHORIZED"
    return _READ_CODES.get(code, "PROVIDER_UNAVAILABLE")


def graph_read(call: Callable[[], GraphResponse], *, insights: bool = False) -> dict[str, Any]:
    """Make one read call; its JSON object, or a fixed ``CommsError``."""
    try:
        response = call()
    except GraphTransportError:
        raise CommsError("PROVIDER_UNAVAILABLE") from None
    envelope = response.envelope
    if response.http_status == 200 and envelope is not None and "error" not in envelope:
        return dict(envelope)
    code = read_refusal(response, insights=insights)
    raise CommsError(code)
