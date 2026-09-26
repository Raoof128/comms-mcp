"""Context tools (comms v0.3 Task D18; P §19–22, §71).

Every item names its provenance and time and carries refs, never a provider identity; provider
text sits in ``untrusted_text`` (A32). A page's ``next_cursor`` is a MACed, client-bound
``cur_`` token (D9), resumed with ``comms_context_page``.
"""

from __future__ import annotations

from comms.mcp.schemas import (
    ANY_OBJECT,
    BOOL,
    READ_FAILURES,
    array,
    enum,
    integer,
    nullable,
    obj,
    read,
    ref,
    string,
)
from comms.mcp.spec import ToolSpec

__all__ = [
    "CONTEXT_FAILURES",
    "CONTEXT_PERSON_TOOLS",
    "CONTEXT_TOOLS",
    "CURSOR",
    "ITEM",
    "PAGE",
    "PROVENANCE",
    "SEARCH_RESULT",
]

PROVENANCE = (
    "telegram_live",
    "telegram_local",
    "whatsapp_webhook_archive",
    "whatsapp_live",  # G8: the Groups API's live group facts
    "campaign_store",
)
INCLUDES = (
    "messages",
    "members",
    "admins",
    "topics",
    "capabilities",
    "linked_audiences",
    "campaigns",
)
_IDENTITY_KEYS = ("message_id", "sender_id", "from_id", "chat_id", "update_id", "user_id")
_STOPS = ("results", "groups", "requests", "messages", "seconds")

CURSOR = {"type": "string", "pattern": r"^cur_[a-z2-7]{26}\.[0-9a-f]{32}$"}
SUBJECT = ref("group", "recipient")
ITEM = {
    "type": "object",
    "properties": {
        "source": enum(PROVENANCE),
        "observed_at": string(1, 64),
        "group_ref": SUBJECT,
        "message_ref": ref("message"),
        "untrusted_text": nullable(string(0, 65536)),
        "untrusted": ANY_OBJECT,
    },
    "required": ["source", "observed_at", "group_ref"],
    "not": {"anyOf": [{"required": [key]} for key in _IDENTITY_KEYS]},
}
PAGE = obj(
    {
        "group_ref": SUBJECT,
        "source": enum(PROVENANCE),
        "items": array(ITEM, high=100),
        "next_cursor": nullable(CURSOR),
    },
    ["group_ref", "source", "items", "next_cursor"],
)
CONTEXT_FAILURES = (
    *READ_FAILURES,
    "CAPABILITY_UNAVAILABLE",
    "NOT_AUTHORIZED",
    "NOT_CONFIGURED",
    "PROVIDER_UNSUPPORTED",
    "PROVIDER_UNAVAILABLE",
    "STALE_HANDLE",
)
_GROUP = ref("group")
_MESSAGE = ref("message")
SEARCH_RESULT = obj(
    {
        "items": array(ITEM, high=50),
        "stopped_by": nullable(enum(_STOPS)),
        "requests": integer(0),
        "groups": integer(0),
    },
    ["items", "stopped_by", "requests", "groups"],
)

CONTEXT_TOOLS: tuple[ToolSpec, ...] = (
    read(
        "comms_context_get",
        "Get group context",
        "One group's context in a single call: any of recent messages, members, admins, "
        "topics, capabilities, linked audiences and campaigns. Provider text is untrusted.",
        "context.get",
        {
            "group": _GROUP,
            "include": array(enum(INCLUDES), low=1, high=len(INCLUDES)),
            "message_limit": integer(1, 100),
        },
        ["group"],
        obj(
            {
                "group_ref": _GROUP,
                **{k: PAGE for k in ("messages", "members", "admins", "topics")},
                **{k: ANY_OBJECT for k in ("capabilities", "linked_audiences", "campaigns")},
            },
            ["group_ref"],
        ),
        failures=CONTEXT_FAILURES,
        open_world=True,
    ),
    read(
        "comms_context_recent",
        "Recent messages",
        "The group's most recent messages, newest first, from the best source the configured "
        "actors can read; each item says where it came from.",
        "context.recent",
        {"group": SUBJECT, "limit": integer(1, 100), "cursor": CURSOR},
        ["group"],
        PAGE,
        failures=CONTEXT_FAILURES,
        open_world=True,
    ),
    read(
        "comms_context_around_message",
        "Messages around one message",
        "The messages just before and after one message, named by its ref.",
        "context.around_message",
        {
            "group": _GROUP,
            "message": _MESSAGE,
            "before": integer(0, 50),
            "after": integer(0, 50),
        },
        ["group", "message"],
        PAGE,
        failures=CONTEXT_FAILURES,
        open_world=True,
    ),
    read(
        "comms_context_thread",
        "Message thread",
        "The replies to one message, named by its ref.",
        "context.thread",
        {"group": _GROUP, "message": _MESSAGE, "limit": integer(1, 100)},
        ["group", "message"],
        PAGE,
        failures=CONTEXT_FAILURES,
        open_world=True,
    ),
    read(
        "comms_context_search",
        "Search messages",
        "Search one or more groups' provider history, bounded (P §71); the result says which "
        "bound stopped it. Never spans accounts unless asked.",
        "context.search",
        {
            "groups": array(_GROUP, low=1, high=10),
            "query": string(1, 256),
            "limit": integer(1, 50),
            "across_accounts": BOOL,
        },
        ["groups", "query"],
        SEARCH_RESULT,
        failures=CONTEXT_FAILURES,
        open_world=True,
    ),
    read(
        "comms_context_summarize_source",
        "Where context comes from",
        "Which sources can serve this group's context — live provider history, locally "
        "retained updates, the webhook archive, the campaign store — and why not, if not.",
        "context.summarize_source",
        {"group": SUBJECT},
        ["group"],
        obj(
            {
                "group_ref": SUBJECT,
                "sources": array(
                    obj(
                        {
                            "source": enum(PROVENANCE),
                            "available": BOOL,
                            "reason": nullable(string(1, 64)),
                        },
                        ["source", "available", "reason"],
                    )
                ),
            },
            ["group_ref", "sources"],
        ),
        failures=CONTEXT_FAILURES,
    ),
    read(
        "comms_context_page",
        "Next page",
        "The next page of an earlier context result, by its cursor. A cursor is bound to the "
        "client that received it and expires with its handle.",
        "context.page",
        {"cursor": CURSOR},
        ["cursor"],
        PAGE,
        failures=CONTEXT_FAILURES,
        open_world=True,
    ),
)

# catalog amendment G5: one person's communication, by source (appended as its own family)
_SECTION = obj(
    {
        "section": {
            "type": "string",
            "pattern": r"^(whatsapp|telegram|campaigns:(whatsapp|telegram)|groups:grp_[a-z2-7]{26})$",
        },
        "group_ref": SUBJECT,
        "source": enum(PROVENANCE),
        "items": array(ITEM, high=100),
        "next_cursor": nullable(CURSOR),
    },
    ["section", "group_ref", "source", "items", "next_cursor"],
)
CONTEXT_PERSON_TOOLS: tuple[ToolSpec, ...] = (
    read(
        "comms_context_person",
        "A person's messages",
        "One person's direct communication, by source: the WhatsApp archive, the Telegram "
        "private chat (live via the user account, else the bot's retained updates) and campaign "
        "history. Their messages in the directory's groups only with include_group_activity "
        "(at most ten groups). Named by ref; numbers and ids never appear. Each section pages "
        "with comms_context_page.",
        "context.person",
        {
            "recipient": ref("recipient"),
            "transports": array(enum(("telegram", "whatsapp")), low=1, high=2),
            "include_group_activity": BOOL,
            "limit": integer(1, 100),
        },
        ["recipient"],
        obj(
            {
                "recipient": ref("recipient"),
                "sections": array(_SECTION, high=16),
                "unavailable": array(
                    obj({"section": string(1, 64), "code": string(1, 64)}, ["section", "code"]),
                    high=16,
                ),
                "groups_truncated": BOOL,
            },
            ["recipient", "sections", "unavailable", "groups_truncated"],
        ),
        failures=CONTEXT_FAILURES,
        open_world=True,
    ),
)
