"""WhatsApp groups: discovery and capability-gated operations (comms v0.3 Task C26; P §16).

Group management is a capability-gated extension: ``GroupDiscovery.discover()`` asks Graph for
the number's groups once and sets every group capability from the answer —
``AVAILABLE`` on success, ``ACCOUNT_INELIGIBLE`` when Meta refuses on permission grounds,
``PROVIDER_UNSUPPORTED`` when Meta does not know the path, ``UNKNOWN`` otherwise (never treated
as available). ``WhatsAppAdmin`` refuses a group operation that discovery did not make available,
with that state as its code and no call; nothing is ever simulated (no unofficial automation).
The group endpoint shapes follow Meta's Groups API documentation and are confirmed by the
live acceptance runbook.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import ProviderResult, ProviderTarget, SemanticOperation
from comms.transports.whatsapp.cloud.classify import admin_call
from comms.transports.whatsapp.cloud.http import GraphApi, GraphTransportError
from comms.transports.whatsapp.cloud.templates import (
    TemplateOps,
    check_create,
    check_delete,
    check_edit,
)
from comms.transports.whatsapp.numbers import WA_GROUP_ID, wa_group_id

__all__ = ["GROUP_CAPABILITIES", "GroupDiscovery", "WhatsAppAdmin", "group_id_of"]

ACTOR = "whatsapp_cloud"
GROUP_CAPABILITIES = (
    C.GROUP_LIST,
    C.GROUP_GET,
    C.GROUP_MEMBERS,
    C.GROUP_MEMBER_REMOVE,
    C.GROUP_INVITE_GET,
    C.GROUP_INVITE_RESET,
    C.GROUP_SETTINGS_UPDATE,
    C.GROUP_MESSAGE_SEND,
    C.MESSAGE_PIN,  # G8: pins, join requests and participants are the Groups API's too
    C.JOIN_REQUEST_LIST,
    C.JOIN_REQUEST_APPROVE,
    C.JOIN_REQUEST_REJECT,
    C.GROUP_CREATE,  # G8
    C.GROUP_DELETE,
)
_PERMISSION_CODES = frozenset({3, 10, 200, 131005})
_UNKNOWN_PATH_CODES = frozenset({2500})
_WA_ID = re.compile(r"\A[0-9]{8,15}\Z")
_CONTACT = re.compile(r"\A\+[0-9]{8,15}\Z")
_WAMID = re.compile(r"\A[A-Za-z0-9._=+/-]{1,256}\Z")


def contact_of(target: ProviderTarget) -> str:
    if target.actor != ACTOR or not _CONTACT.match(target.identity):
        raise ValueError("not a whatsapp contact")
    return target.identity


def group_id_of(target: ProviderTarget) -> str:
    if target.actor != ACTOR:
        raise ValueError("not a whatsapp group destination")
    try:
        return wa_group_id(target.identity).partition(":")[2]
    except ValueError:
        raise ValueError("not a whatsapp group destination") from None


class GroupDiscovery:
    def __init__(self, api: GraphApi) -> None:
        self._api = api
        self.states: dict[C, S] = dict.fromkeys(GROUP_CAPABILITIES, S.UNKNOWN)

    def discover(self) -> Mapping[C, S]:
        try:
            response = self._api.list_groups(limit=1)
        except GraphTransportError:
            state = S.UNKNOWN
        else:
            state = _discovered(response.http_status, response.envelope)
        self.states = dict.fromkeys(GROUP_CAPABILITIES, state)
        return self.states


def _discovered(status: int, envelope: Mapping[str, Any] | None) -> S:
    if envelope is None or status >= 500:
        return S.UNKNOWN
    if status == 200 and isinstance(envelope.get("data"), list):
        return S.AVAILABLE
    error = envelope.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if code in _PERMISSION_CODES:
        return S.ACCOUNT_INELIGIBLE
    if code in _UNKNOWN_PATH_CODES or status == 404:
        return S.PROVIDER_UNSUPPORTED
    return S.UNKNOWN


def _remove_args(args: Mapping[str, Any]) -> None:
    if set(args) != {"wa_id"} or not (
        isinstance(args["wa_id"], str) and _WA_ID.match(args["wa_id"])
    ):
        raise ValueError("operation arguments are malformed")


def _remove(api: GraphApi, group_id: str, args: Mapping[str, Any]) -> ProviderResult:
    return admin_call(lambda: api.remove_group_participant(group_id, args["wa_id"]))


def _reset_args(args: Mapping[str, Any]) -> None:
    if args:
        raise ValueError("operation arguments are malformed")


def _reset(api: GraphApi, group_id: str, args: Mapping[str, Any]) -> ProviderResult:
    result = admin_call(lambda: api.reset_group_invite(group_id))
    if result.outcome != "SUCCEEDED":
        return result
    link = result.detail.get("invite_link")
    if not isinstance(link, str) or not link.startswith("https://chat.whatsapp.com/"):
        return ProviderResult("OUTCOME_UNKNOWN", None)
    return ProviderResult("SUCCEEDED", None, provider_ref=link)


_SETTINGS = {
    "subject": lambda v: isinstance(v, str) and 1 <= len(v) <= 100,
    "description": lambda v: isinstance(v, str) and len(v) <= 2048,
}


def _settings_args(args: Mapping[str, Any]) -> None:
    if (
        not args
        or not set(args) <= set(_SETTINGS)
        or not all(_SETTINGS[k](v) for k, v in args.items())
    ):
        raise ValueError("operation arguments are malformed")


def _settings(api: GraphApi, group_id: str, args: Mapping[str, Any]) -> ProviderResult:
    return admin_call(lambda: api.update_group(group_id, args))


def _mark_read_args(args: Mapping[str, Any]) -> None:
    if set(args) != {"message_id"} or not (
        isinstance(args["message_id"], str) and _WAMID.match(args["message_id"])
    ):
        raise ValueError("operation arguments are malformed")


def _mark_read(api: GraphApi, _contact: str, args: Mapping[str, Any]) -> ProviderResult:
    return admin_call(lambda: api.mark_read(args["message_id"]))


def account_of(target: ProviderTarget) -> str:
    kind, sep, waba_id = target.identity.partition(":")
    if target.actor != ACTOR or kind != "waba" or not sep or not waba_id.isdigit():
        raise ValueError("not the whatsapp business account")
    return waba_id


def _template_create_args(args: Mapping[str, Any]) -> None:
    check_create(args)


def _template_create(api: GraphApi, _waba: str, args: Mapping[str, Any]) -> ProviderResult:
    return TemplateOps(api).create(args)


def _template_edit_args(args: Mapping[str, Any]) -> None:
    if set(args) != {"template_id", "components"}:
        raise ValueError("operation arguments are malformed")
    check_edit(args["template_id"], {"components": args["components"]})


def _template_edit(api: GraphApi, _waba: str, args: Mapping[str, Any]) -> ProviderResult:
    return TemplateOps(api).edit(args["template_id"], {"components": args["components"]})


def _template_delete_args(args: Mapping[str, Any]) -> None:
    if set(args) != {"name"}:
        raise ValueError("operation arguments are malformed")
    check_delete(args["name"])


def _template_delete(api: GraphApi, _waba: str, args: Mapping[str, Any]) -> ProviderResult:
    return TemplateOps(api).delete(args["name"])


def _media_delete_args(args: Mapping[str, Any]) -> None:
    if set(args) != {"media_id"} or not (
        isinstance(args["media_id"], str)
        and args["media_id"].isascii()
        and args["media_id"].isdigit()
    ):
        raise ValueError("operation arguments are malformed")


def _media_delete(api: GraphApi, _waba: str, args: Mapping[str, Any]) -> ProviderResult:
    return admin_call(lambda: api.delete_media(args["media_id"]))


# -- catalog amendment G8: group sends, pins and join requests ------------------------------

TEXT_MAX = 4096
PIN_DAYS = range(1, 31)  # Meta: a pin lasts 1-30 days, and the days are required to pin
JOIN_PAGE = 100


def _send_args(args: Mapping[str, Any]) -> None:
    text = args.get("text")
    if set(args) != {"text"} or not (isinstance(text, str) and 1 <= len(text) <= TEXT_MAX):
        raise ValueError("operation arguments are malformed")


def _send(api: GraphApi, group_id: str, args: Mapping[str, Any]) -> ProviderResult:
    body = {"messaging_product": "whatsapp", "recipient_type": "group", "to": group_id,
            "type": "text", "text": {"body": args["text"]}}  # fmt: skip
    return _sent_wamid(admin_call(lambda: api.send_message(body)))


def _pin_args(args: Mapping[str, Any]) -> None:
    days = args.get("expire_days", 30)
    if (
        not {"message_id", "pinned"} <= set(args) <= {"message_id", "pinned", "expire_days"}
        or not (isinstance(args["message_id"], str) and _WAMID.match(args["message_id"]))
        or type(args["pinned"]) is not bool
        or type(days) is not int
        or days not in PIN_DAYS
    ):
        raise ValueError("operation arguments are malformed")


def _pin(api: GraphApi, group_id: str, args: Mapping[str, Any]) -> ProviderResult:
    pin: dict[str, Any] = {"type": "pin" if args["pinned"] else "unpin",
                           "message_id": args["message_id"]}  # fmt: skip
    if args["pinned"]:
        pin["expiration_days"] = args.get("expire_days", 30)
    body = {"messaging_product": "whatsapp", "recipient_type": "group", "to": group_id,
            "type": "pin", "pin": pin}  # fmt: skip
    result = admin_call(lambda: api.send_message(body))
    return ProviderResult(result.outcome, result.code)  # the pin's own wamid names nothing


def _sent_wamid(result: ProviderResult) -> ProviderResult:
    if result.outcome != "SUCCEEDED":
        return result
    messages = result.detail.get("messages")
    first = messages[0] if isinstance(messages, list) and messages else None
    wamid = first.get("id") if isinstance(first, dict) else None
    if not isinstance(wamid, str) or not _WAMID.match(wamid):
        return ProviderResult("OUTCOME_UNKNOWN", None)
    return ProviderResult("SUCCEEDED", None, provider_ref=wamid)


def _join_args(args: Mapping[str, Any]) -> None:
    _remove_args(args)  # the requester by wa_id, as a removal names its participant


def _join(approve: bool) -> Call:
    def call(api: GraphApi, group_id: str, args: Mapping[str, Any]) -> ProviderResult:
        """The member's pending request, found by ``wa_id`` (Meta answers requests by their
        own id), then approved or rejected: one read, one write."""
        listed = api.join_requests(group_id, limit=JOIN_PAGE, after=None)
        rows = (listed.envelope or {}).get("data") if listed.http_status == 200 else None
        if not isinstance(rows, list):
            return ProviderResult("FAILED", "PROVIDER_UNAVAILABLE")  # nothing was sent
        request_id = next(
            (r.get("join_request_id") for r in rows
             if isinstance(r, dict) and r.get("wa_id") == args["wa_id"]),
            None,
        )  # fmt: skip
        if not isinstance(request_id, str):
            return ProviderResult("FAILED", "TARGET_NOT_FOUND")
        result = admin_call(lambda: api.answer_join_requests(group_id, [request_id],
                                                             approve=approve))  # fmt: skip
        done = result.detail.get("approved_join_requests" if approve else "rejected_join_requests")
        if result.outcome == "SUCCEEDED" and not (isinstance(done, list) and request_id in done):
            return ProviderResult("FAILED", "PROVIDER_UNAVAILABLE")  # Meta listed it as failed
        return result

    return call


_CREATE = {
    "subject": lambda v: isinstance(v, str) and 1 <= len(v) <= 128,
    "description": lambda v: isinstance(v, str) and len(v) <= 2048,
    "join_approval_mode": lambda v: v in ("auto_approve", "approval_required"),
}


def _create_args(args: Mapping[str, Any]) -> None:
    if (
        "subject" not in args
        or not set(args) <= set(_CREATE)
        or not all(_CREATE[k](v) for k, v in args.items())
    ):
        raise ValueError("operation arguments are malformed")


def _create(api: GraphApi, _phone: str, args: Mapping[str, Any]) -> ProviderResult:
    """Meta creates the group asynchronously: its ``request_id`` names it until the
    ``group_lifecycle_update`` webhook does; a group ``id`` in the answer names it at once."""
    result = admin_call(lambda: api.create_group({"messaging_product": "whatsapp", **args}))
    if result.outcome != "SUCCEEDED":
        return result
    group, request = result.detail.get("id"), result.detail.get("request_id")
    if isinstance(group, str) and WA_GROUP_ID.match(group):
        return ProviderResult("SUCCEEDED", None, provider_ref=f"group:{group}")
    if isinstance(request, str) and 0 < len(request) <= 256:
        return ProviderResult("SUCCEEDED", None, provider_ref=f"request:{request}")
    return ProviderResult("OUTCOME_UNKNOWN", None)  # accepted, but nothing to name it by


def _delete(api: GraphApi, group_id: str, args: Mapping[str, Any]) -> ProviderResult:
    return admin_call(lambda: api.delete_group(group_id))


def phone_account(target: ProviderTarget) -> str:
    """The account-level target (no group yet): ``group.create`` (G8)."""
    if target.actor != ACTOR or target.identity != "account":
        raise ValueError("a group is created from the account")
    return "account"


Check = Callable[[Mapping[str, Any]], None]
Call = Callable[[GraphApi, str, Mapping[str, Any]], ProviderResult]
Where = Callable[[ProviderTarget], str]
# capability → (argument check, the call, what the target must be)
_OPERATIONS: Mapping[C, tuple[Check, Call, Where]] = {
    C.GROUP_MEMBER_REMOVE: (_remove_args, _remove, group_id_of),
    C.GROUP_INVITE_RESET: (_reset_args, _reset, group_id_of),
    C.GROUP_SETTINGS_UPDATE: (_settings_args, _settings, group_id_of),
    C.MESSAGE_MARK_READ: (_mark_read_args, _mark_read, contact_of),  # D14
    C.TEMPLATE_CREATE: (_template_create_args, _template_create, account_of),  # D17
    C.TEMPLATE_EDIT: (_template_edit_args, _template_edit, account_of),
    C.TEMPLATE_DELETE: (_template_delete_args, _template_delete, account_of),
    C.MEDIA_DELETE: (_media_delete_args, _media_delete, account_of),
    C.GROUP_MESSAGE_SEND: (_send_args, _send, group_id_of),  # G8
    C.MESSAGE_PIN: (_pin_args, _pin, group_id_of),
    C.JOIN_REQUEST_APPROVE: (_join_args, _join(True), group_id_of),
    C.JOIN_REQUEST_REJECT: (_join_args, _join(False), group_id_of),
    C.GROUP_CREATE: (_create_args, _create, phone_account),
    C.GROUP_DELETE: (_reset_args, _delete, group_id_of),
}


class WhatsAppAdmin:
    operations = frozenset(_OPERATIONS)

    def __init__(self, api: GraphApi, discovery: GroupDiscovery) -> None:
        self._api, self._discovery = api, discovery

    def __repr__(self) -> str:
        return "WhatsAppAdmin(<redacted>)"

    def validate(self, op: SemanticOperation, target: ProviderTarget) -> None:
        self._request(op, target)

    def _request(self, op: SemanticOperation, target: ProviderTarget) -> tuple[Call, str]:
        operation = _OPERATIONS.get(op.capability)
        if operation is None:
            raise NotImplementedError("whatsapp_cloud does not perform this operation")
        check, call, where = operation
        place = where(target)
        check(op.args)
        return call, place

    def invoke(self, op: SemanticOperation, target: ProviderTarget, op_key: str) -> ProviderResult:
        call, where = self._request(op, target)
        if op.capability in GROUP_CAPABILITIES:  # groups are gated by discovery (P §16)
            state = self._discovery.states.get(op.capability, S.UNKNOWN)
            if state is not S.AVAILABLE:
                return ProviderResult("FAILED", state.value)  # nothing sent, nothing simulated
        return call(self._api, where, op.args)
