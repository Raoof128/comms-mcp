"""The directory's people and their contact points over MCP (catalog amendment G2, G3).

A person is a ``rcp_`` ref with a label and contact points. Outputs carry the label under
``untrusted`` (owner-typed, but it can reach a model as text) and each contact point by its
``rct_`` ref and transport, never its identity. Every write replays by its ``req_`` id.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from comms.mcp.schemas import BOOL, array, integer, nullable, obj, read, ref, string, write
from comms.mcp.spec import ToolSpec

__all__ = ["DIRECTORY_PEOPLE_TOOLS"]

_RECIPIENT = ref("recipient")
_LABEL = string(1, 200)
_CURSOR = string(1, 18)
_FAILURES = ("INVALID_ARGUMENT", "NOT_FOUND")
_UNTRUSTED = obj({"display_name": nullable(_LABEL)}, ["display_name"])
_CONTACT = obj(
    {
        "contact": ref("contact_point"),
        "transport": {"enum": ["telegram", "whatsapp"]},
        "enabled": BOOL,
        "opted_out": BOOL,
    },
    ["contact", "transport", "enabled", "opted_out"],
)


def _done(**extra: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"op_ref": ref("operation"), "replayed": BOOL, **extra}
    return obj(fields, list(fields))


def _write(
    verb: str, title: str, description: str, inputs: Mapping[str, Any], output: Mapping[str, Any],
    *, idempotent: bool = True, noun: str = "recipient", open_world: bool = False,
) -> ToolSpec:  # fmt: skip
    return write(
        f"comms_directory_{noun}_{verb}",
        title,
        description,
        f"directory.{noun}_{verb}",
        inputs,
        list(inputs),
        output,
        idempotent=idempotent,
        failures=_FAILURES,
        open_world=open_world,
    )


DIRECTORY_PEOPLE_TOOLS: tuple[ToolSpec, ...] = (
    read(
        "comms_directory_recipient_list",
        "List people",
        "People in the directory, newest first: ref, whether enabled, and their untrusted label.",
        "directory.recipient_list",
        {"limit": integer(1, 100), "cursor": _CURSOR},
        [],
        obj(
            {
                "items": array(
                    obj(
                        {"recipient": _RECIPIENT, "enabled": BOOL, "untrusted": _UNTRUSTED},
                        ["recipient", "enabled", "untrusted"],
                    ),
                    high=100,
                ),
                "next_cursor": nullable(_CURSOR),
            },
            ["items", "next_cursor"],
        ),
    ),
    read(
        "comms_directory_recipient_get",
        "Get a person",
        "One person: whether enabled, their untrusted label, and their contact points by ref "
        "and transport — never a number or user id.",
        "directory.recipient_get",
        {"recipient": _RECIPIENT},
        ["recipient"],
        obj(
            {
                "recipient": _RECIPIENT,
                "enabled": BOOL,
                "created_at": string(1, 64),
                "untrusted": _UNTRUSTED,
                "contacts": array(_CONTACT, high=64),
            },
            ["recipient", "enabled", "created_at", "untrusted", "contacts"],
        ),
    ),
    _write(
        "create",
        "Add a person",
        "Add a person to the directory with a label. Add their numbers or accounts with "
        "comms_directory_contact_add.",
        {"display_name": _LABEL},
        _done(recipient=_RECIPIENT),
        idempotent=False,
    ),
    _write(
        "update",
        "Relabel a person",
        "Change a person's label; the ref never changes.",
        {"recipient": _RECIPIENT, "display_name": _LABEL},
        _done(),
    ),
    _write(
        "enable",
        "Enable a person",
        "Enable a person again.",
        {"recipient": _RECIPIENT},
        _done(),
    ),
    _write(
        "disable",
        "Disable a person",
        "Disable a person: campaigns and name resolution skip them. Nothing is deleted.",
        {"recipient": _RECIPIENT},
        _done(),
    ),
    # -- contact points (G3): the identity is input only, never an output ------------------
    _write(
        "add",
        "Add a number or account",
        "Give a person a WhatsApp number (E.164, e.g. +61400000001) or a numeric Telegram user "
        "id. The identity is stored encrypted and never returned; campaigns can then reach the "
        "person on that transport, so the host asks first.",
        {
            "recipient": _RECIPIENT,
            "transport": {"enum": ["whatsapp", "telegram"]},
            "identity": string(1, 32),
        },
        _done(contact=ref("contact_point")),
        idempotent=False,
        noun="contact",
        open_world=True,
    ),
    _write(
        "disable",
        "Disable a number or account",
        "Stop using one contact point; the person keeps their others.",
        {"contact": ref("contact_point")},
        _done(),
        noun="contact",
    ),
    _write(
        "opt_out",
        "Record an opt-out",
        "Record that this number or account opted out: campaigns skip it, and it can never be "
        "added again under any person.",
        {"contact": ref("contact_point")},
        _done(),
        noun="contact",
    ),
)
