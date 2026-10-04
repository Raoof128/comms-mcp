"""The whole catalog against the real daemon (D39-A): every tool over HTTP ``/mcp``.

A prologue creates real objects over MCP (a person with a Telegram identity, a location, an
audience, a campaign, a staged file, an invite, a topic). Then every catalog tool is called with
arguments built from its own schema and those objects, destructive tools last. Each answer must
be either a success whose ``structuredContent`` validates against the tool's output schema, or an
error whose code the tool declares, never ``INTERNAL_ERROR``. The report names every tool.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import jsonschema

# Destructive tools run after everything that needs their objects: the group's own last, then
# the directory's (a disabled person answers NOT_FOUND to every later member tool).
_GROUP_LAST = ("delete", "remove", "revoke", "ban", "unban", "reject", "demote", "unrestrict",
               "reactions_clear", "migrate")  # fmt: skip
_DIRECTORY_LAST = ("comms_audience_remove", "comms_location_member_remove",
                   "comms_directory_contact_disable", "comms_directory_contact_opt_out",
                   "comms_directory_destination_disable", "comms_directory_recipient_disable",
                   "comms_location_disable")  # fmt: skip
_CAMPAIGN = ("create", "set_content", "set_targets", "validate", "preview", "get", "list", "status",
             "schedule", "unschedule", "send", "delivery_report", "retry_failed",
             "resolve_unknown", "cancel")  # fmt: skip
PHOTO = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 40


# The only refusals the selftest daemon (the production daemon with local providers) owes:
# each is the actor's or the environment's honest answer, and each tool is also driven through
# the composition root with scripted providers (the actor-matrix behaviour test, the Meta
# oracle). Every other tool must succeed.
EXPECTED_REFUSALS: Mapping[str, tuple[str, str]] = {
    "comms_context_search": ("NOT_CONFIGURED", "search is the user account's; none is logged in"),
    "comms_message_search": ("NOT_CONFIGURED", "search is the user account's; none is logged in"),
    "comms_context_thread": ("PROVIDER_UNSUPPORTED", "the bot keeps no thread index"),
    "comms_group_admin_log": ("PROVIDER_UNSUPPORTED", "the Bot API has no admin log"),
    "comms_group_invite_list": ("PROVIDER_UNSUPPORTED", "the Bot API cannot list invites"),
    "comms_group_members_list": ("PROVIDER_UNSUPPORTED", "the Bot API cannot list members"),
    "comms_group_topic_get": ("PROVIDER_UNSUPPORTED", "the Bot API cannot read a topic"),
    "comms_group_topic_list": ("PROVIDER_UNSUPPORTED", "the Bot API cannot list topics"),
    "comms_message_mark_read": ("PROVIDER_UNSUPPORTED", "a bot message ref: bots have no read state (R-H1)"),
    "comms_media_delete": ("PROVIDER_UNSUPPORTED", "Telegram has no file delete (A47)"),
    "comms_campaign_resolve_unknown": ("NOT_FOUND", "no job is in an unknown outcome"),
    **{name: ("NOT_CONFIGURED", "the selftest daemon has no Graph API")
       for name in ("comms_whatsapp_health_status", "comms_whatsapp_phone_status",
                    "comms_whatsapp_template_create", "comms_whatsapp_template_delete",
                    "comms_whatsapp_template_edit", "comms_whatsapp_template_get",
                    "comms_whatsapp_template_list")},
}  # fmt: skip

# Proposed A49: the selftest daemon configures no Instagram account, so every Instagram tool
# answers NOT_CONFIGURED here, as the WhatsApp Graph tools do (R-IG4). The same tools run
# against a fake graph.instagram.com through the real dispatcher in the pytest suite.
INSTAGRAM_REFUSAL = ("NOT_CONFIGURED", "the selftest daemon has no Instagram account")
_INSTAGRAM_VALUES: Mapping[str, Any] = {
    "account": "main", "media": "igm_" + "a" * 26, "comment": "igc_" + "a" * 26,
    "person": "igp_" + "a" * 26, "container": "igk_" + "a" * 26,
    "children": ["igk_" + "a" * 26, "igk_" + "b" * 26], "text": "Sweep", "hide": True,
    "enabled": True, "url": "https://cdn.example.com/sweep.jpg",
}  # fmt: skip


def _expected(name: str) -> tuple[str, str] | None:
    if name.startswith("comms_instagram_"):
        return INSTAGRAM_REFUSAL
    return EXPECTED_REFUSALS.get(name)


def _instagram_arguments(spec: Any) -> dict[str, Any]:
    """Schema-valid arguments for an Instagram tool: its required keys, nothing more."""
    props, out = spec.input_schema.get("properties", {}), {}
    for key in spec.input_schema.get("required", ()):
        schema = props.get(key, {})
        if key == "request_id":
            continue
        if key in _INSTAGRAM_VALUES:
            out[key] = _INSTAGRAM_VALUES[key]
        elif "enum" in schema:
            out[key] = schema["enum"][0]
        elif "enum" in schema.get("items", {}):
            out[key] = [schema["items"]["enum"][0]]
    return out


def _order(name: str) -> tuple[int, int, str]:
    tail = name.removeprefix("comms_")
    if name in _DIRECTORY_LAST:
        return (4, _DIRECTORY_LAST.index(name), name)
    if name == "comms_group_delete":
        return (5, 0, name)  # the very last: the group every other tool used
    if tail.startswith("campaign_"):
        return (2, _CAMPAIGN.index(tail.removeprefix("campaign_")), name)
    if any(word in tail for word in _GROUP_LAST):
        return (3, 0, name)
    return (0 if tail.endswith(("create", "add", "stage_begin")) else 1, 0, name)


def sweep(call: Callable[[str, dict[str, Any]], dict[str, Any]], grp: str) -> dict[str, Any]:
    """``call(name, arguments)`` answers the MCP ``result`` (``isError``, ``structuredContent``)."""
    from comms.core import refs
    from comms.mcp.catalog import TOOL_CATALOG

    def ok(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        answer = call(name, {**arguments, "request_id": refs.mint("request")})
        return {} if answer["isError"] else dict(answer["structuredContent"])

    person = ok("comms_directory_recipient_create", {"display_name": "Sweep Person"})["recipient"]
    contact = ok("comms_directory_contact_add", {"recipient": person, "transport": "telegram",
                                                 "identity": "4242"}).get("contact")  # fmt: skip
    location = ok("comms_location_create", {"name": "Sweep place"})["location"]
    ok("comms_location_member_add", {"location": location, "recipient": person})
    audience = ok("comms_audience_create", {"name": "Sweep audience"})["audience"]
    ok("comms_audience_add", {"audience": audience, "member": location})
    campaign = ok("comms_campaign_create", {"title": "Sweep"})["campaign"]
    destination = ok("comms_directory_destination_create", {
        "location": location, "transport": "telegram", "identity": "-4343",
        "name": "Sweep TG"})  # fmt: skip
    invite = ok("comms_group_invite_create", {"group": grp}).get("object")
    topic = ok("comms_group_topic_create", {"group": grp, "name": "Sweep topic"}).get("object")
    begun = ok(
        "comms_media_stage_begin",
        {"mime": "image/jpeg", "size": len(PHOTO), "sha256": hashlib.sha256(PHOTO).hexdigest()},
    )
    upload = begun.get("upload")
    page = call("comms_context_recent", {"group": grp, "limit": 2})["structuredContent"]
    items = call("comms_context_recent", {"group": grp, "limit": 10})["structuredContent"]["items"]
    message = items[0]["message_ref"]
    media = next((i["media_ref"] for i in items if "media_ref" in i), None)
    values: dict[str, Any] = {
        "group": grp, "groups": [grp], "to_group": grp, "message": message,
        "recipient": person, "conversation": person, "ref": person, "member": location,
        "location": location, "audience": audience, "campaign": campaign, "contact": contact,
        "destination": destination.get("destination") or destination.get("group"),
        "invite": invite, "topic": topic, "media": media, "upload": upload,
        "cursor": page.get("next_cursor"), "query": "selftest", "text": "Sweep",
        "title": "Sweep", "name": "Sweep", "display_name": "Sweep", "description": "Sweep",
        "tag": "vip", "content": {"canonical": "Salaam"}, "targets": {"audiences": [audience]},
        "transports": ["telegram"], "transport": "telegram", "identity": "4343",
        "permissions": {"can_send_messages": True}, "rights": {"can_pin_messages": True},
        "at": (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actor": "telegram_bot", "capability": "member.ban", "language": "en",
        "profile": "moderator", "verdict": "not_sent",
        "category": "MARKETING", "components": [{"type": "BODY", "text": "Hi"}],
        "template": "ctp_" + "a" * 26, "job": "djb_" + "a" * 26,
        "mime": "image/jpeg", "size": len(PHOTO), "sha256": hashlib.sha256(PHOTO).hexdigest(),
        "seq": 0, "data_b64": base64.b64encode(PHOTO).decode(),
    }  # fmt: skip
    overrides: Mapping[str, dict[str, Any]] = {
        "comms_message_send_media": {
            "kind": "photo",
            "data_b64": values["data_b64"],
            "mime": "image/jpeg",
        },
        "comms_group_info_set_photo": {"data_b64": values["data_b64"], "mime": "image/jpeg"},
        "comms_media_stage_chunk": {
            "upload": upload,
            "seq": 0,
            "data_b64": values["data_b64"],
        },
        "comms_group_create": {
            "kind": "supergroup",
            "location": location,
            "title": "Sweep",
            "actor": "telegram_user",
        },
        "comms_media_upload": {
            "data_b64": values["data_b64"],
            "mime": "image/jpeg",
            "actor": "telegram_user",
        },
        "comms_whatsapp_template_create": {
            "name": "sweep_tpl",
            "language": "en",
            "category": "MARKETING",
            "components": [{"type": "BODY", "text": "Hi"}],
        },
        "comms_whatsapp_template_delete": {"name": "sweep_tpl"},
        "comms_directory_contact_add": {
            "recipient": person,
            "transport": "whatsapp",
            "identity": "+61400000099",
        },
        "comms_directory_destination_create": {
            "location": location,
            "transport": "telegram",
            "identity": "-4444",
            "name": "Sweep TG 2",
        },
        "comms_campaign_schedule": {"campaign": campaign, "at": values["at"]},
        "comms_group_invite_edit": {"group": grp, "invite": invite, "name": "Renamed"},
        "comms_group_topic_edit": {"group": grp, "topic": topic, "name": "Renamed"},
    }
    report: dict[str, Any] = {}
    for spec in sorted(TOOL_CATALOG, key=lambda s: _order(s.name)):
        props = spec.input_schema.get("properties", {})
        arguments = {}
        if spec.name.startswith("comms_instagram_"):
            arguments = _instagram_arguments(spec)
            if spec.requires_request_id:
                arguments["request_id"] = refs.mint("request")
            report[spec.name] = _judge(spec, call(spec.name, arguments))
            continue
        for key in spec.input_schema.get("required", ()):
            if key == "request_id":
                continue
            if key in values and values[key] is not None:
                arguments[key] = values[key]
            elif "enum" in props.get(key, {}):
                arguments[key] = props[key]["enum"][0]
        arguments.update(overrides.get(spec.name, {}))
        if spec.requires_request_id:
            arguments["request_id"] = refs.mint("request")
        answer = call(spec.name, arguments)
        report[spec.name] = _judge(spec, answer)
    return report


def _judge(spec: Any, answer: Mapping[str, Any]) -> tuple[str, str | None]:
    """``("ok", None)``, ``("expected", code)``, or ``("WRONG", why)``: a success valid against
    the output schema, exactly the pinned refusal, and nothing else."""
    body = answer.get("structuredContent") or {}
    expected = _expected(spec.name)
    if answer.get("isError"):
        code = (body.get("error") or {}).get("code")
        if code == "INTERNAL_ERROR" or code not in spec.failure_modes:
            return ("WRONG", f"undeclared error {code}")
        if expected is None or expected[0] != code:
            return ("WRONG", f"refused {code}; expected {expected[0] if expected else 'success'}")
        return ("expected", code)
    if expected is not None:
        return ("WRONG", f"succeeded; expected {expected[0]} ({expected[1]})")
    try:
        jsonschema.Draft202012Validator(spec.output_schema).validate(body)
    except jsonschema.ValidationError as bad:
        return ("WRONG", f"output schema: {bad.message[:120]}")
    return ("ok", None)
