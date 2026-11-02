"""The Pinterest tools (proposed A50, section 5; ``docs/pinterest-spec-v0.1.md``).

Every tool but ``comms_pinterest_account_list`` takes ``account``, an alias from comms.json; a
read may omit it (the configured default), a write never may (D-P5). Every provider id becomes
an opaque ref (``pna_``, ``pnb_``, ``pnp_``, ``pnv_``); titles, descriptions, board names,
usernames and Pinterest's links only under ``untrusted`` or ``untrusted_text`` (A44). A page's
``next_cursor`` is a client-bound ``cur_``. Descriptions are short: Claude Code truncates a
description at 2,048 characters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from comms.core.providers.capability import Capability as C
from comms.core.providers.pinterest_analytics import (
    ACCOUNT_METRICS,
    APP_TYPES,
    CLAIMED,
    CONTENT_TYPES,
    DATA_STATUSES,
    PIN_FORMATS,
    PIN_METRICS,
    SOURCES,
)
from comms.mcp.schemas import (
    ACTOR,
    BOOL,
    OUTCOMES,
    READ_FAILURES,
    array,
    enum,
    integer,
    nullable,
    obj,
    read,
    ref,
    string,
    write,
)
from comms.mcp.spec import ToolSpec
from comms.mcp.tools.context import CURSOR

__all__ = ["PINTEREST_TOOLS"]

ALIAS: Mapping[str, Any] = {"type": "string", "pattern": "^[a-z0-9_-]{1,32}$"}
_READ_FAILURES = (
    *READ_FAILURES,
    "NOT_CONFIGURED",
    "NOT_AUTHORIZED",
    "CAPABILITY_UNAVAILABLE",
    "RATE_LIMITED",
    "PROVIDER_UNAVAILABLE",
    "IDENTITY_MISMATCH",
    "STALE_HANDLE",
)
_NUMBER: Mapping[str, Any] = {"type": "number"}
_METRIC_MAP: Mapping[str, Any] = {"type": "object", "additionalProperties": _NUMBER}
_TEXT = nullable(string(0, 64))
_ACCOUNT_UNTRUSTED = {"account_username": string(0, 64)}
_DATE = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}
_URL = {"type": "string", "minLength": 9, "maxLength": 2048, "pattern": "^https://"}
_DIGEST = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_MEDIA_STATUS = nullable(enum(("registered", "processing", "succeeded", "failed")))
_BOARD_UNTRUSTED = {"name": nullable(string(0, 180)), "owner_username": _TEXT}
_BOARD_FIELDS = {
    "board": ref("pinterest_board"),
    "privacy": nullable(enum(("PUBLIC", "PROTECTED", "SECRET"))),
    "pin_count": nullable(integer(0)),
    "follower_count": nullable(integer(0)),
    "collaborator_count": nullable(integer(0)),
    "created_at": nullable(string(0, 32)),
    "untrusted_text": nullable(string(0, 500)),
}
BOARD_ITEM = obj(
    {**_BOARD_FIELDS, "untrusted": obj(_BOARD_UNTRUSTED, list(_BOARD_UNTRUSTED))},
    [*_BOARD_FIELDS, "untrusted"],
)
_PIN_UNTRUSTED = {
    "title": nullable(string(0, 100)),
    "link": nullable(string(0, 2048)),
    "alt_text": nullable(string(0, 500)),
    "board_owner_username": _TEXT,
}
_PIN_FIELDS = {
    "pin": ref("pinterest_pin"),
    "board": nullable(ref("pinterest_board")),
    "created_at": nullable(string(0, 32)),
    "creative_type": nullable(string(1, 40)),
    "media_type": nullable(
        enum(("image", "video", "multiple_images", "multiple_videos", "multiple_mixed"))
    ),
    "is_owner": nullable(BOOL),
    "has_been_promoted": nullable(BOOL),
    "metrics_90d": nullable(_METRIC_MAP),
    "metrics_lifetime": nullable(_METRIC_MAP),
    "untrusted_text": nullable(string(0, 800)),
}
PIN_ITEM = obj(
    {**_PIN_FIELDS, "untrusted": obj(_PIN_UNTRUSTED, list(_PIN_UNTRUSTED))},
    [*_PIN_FIELDS, "untrusted"],
)
_ANALYTICS = {
    "summary": _METRIC_MAP,
    "daily": array(
        obj(
            {
                "date": nullable(_DATE),
                "data_status": nullable(enum(DATA_STATUSES)),
                "metrics": _METRIC_MAP,
            },
            ["date", "data_status", "metrics"],
        ),
        high=100,
    ),
    "lifetime": _METRIC_MAP,
}
_RANGE = {"start_date": _DATE, "end_date": _DATE, "app_types": enum(APP_TYPES)}


def _out(fields: Mapping[str, Any], untrusted: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A Pinterest result: the account named, its live username, and ``fields``."""
    head = {
        "account": ALIAS,
        "account_ref": ref("pinterest_account"),
        "untrusted": obj(
            {**_ACCOUNT_UNTRUSTED, **(untrusted or {})}, [*_ACCOUNT_UNTRUSTED, *(untrusted or {})]
        ),
    }
    return obj({**head, **fields}, [*head, *fields])


def _read(
    name: str, title: str, description: str, inputs: Mapping[str, Any], required: Sequence[str],
    output: Mapping[str, Any], *, failures: Sequence[str] = (),
) -> ToolSpec:  # fmt: skip
    return read(
        f"comms_pinterest_{name}",
        title,
        description,
        f"pinterest.{name}",
        {"account": ALIAS, **inputs} if name != "account_list" else dict(inputs),
        required,
        output,
        failures=(*_READ_FAILURES, *failures),
        open_world=name != "account_list",
    )


_PAGED = {"limit": integer(1, 100), "cursor": CURSOR}
_QUOTA = {
    "pins_last_24h": integer(0),
    "daily_pin_budget": integer(1, 300),
    "rate_limit_remaining": nullable(integer(0)),
    "rate_limit_reset_s": nullable(integer(0)),
}
_ACCOUNT_ROW = obj(
    {
        "account": ALIAS,
        "account_ref": nullable(ref("pinterest_account")),
        "registered": BOOL,
        "writes": BOOL,
        "sandbox": BOOL,
        "token_expires_in_days": nullable(integer(0)),
        "refresh_expires_in_days": nullable(integer(0)),
        "untrusted": obj({"label": string(1, 64)}, ["label"]),
    },
    [
        "account",
        "account_ref",
        "registered",
        "writes",
        "sandbox",
        "token_expires_in_days",
        "refresh_expires_in_days",
        "untrusted",
    ],
)

READ_TOOLS: tuple[ToolSpec, ...] = (
    _read(
        "account_list",
        "List Pinterest accounts",
        "The Pinterest accounts configured for comms: alias, whether added, its write ceiling, "
        "sandbox or production, and days left on its access and refresh tokens. Never a token or "
        "an account id.",
        {},
        [],
        obj(
            {"accounts": array(_ACCOUNT_ROW, high=16), "default": nullable(ALIAS)},
            ["accounts", "default"],
        ),
    ),
    _read(
        "whoami",
        "Check a Pinterest account",
        "Check that an account's token still names it (GET /user_account), and show its username "
        "and both token expiries. Omit account for the default.",
        {},
        [],
        _out(
            {
                "identity_checked": BOOL,
                "sandbox": BOOL,
                "token_expires_at": nullable(string(1, 40)),
                "refresh_expires_at": nullable(string(1, 40)),
            }
        ),
    ),
    _read(
        "profile_get",
        "Get a Pinterest profile",
        "The account's profile: type and board, Pin, follower, following and monthly view "
        "counts. Names and the website are untrusted.",
        {},
        [],
        _out(
            {
                "account_type": nullable(enum(("PINNER", "BUSINESS"))),
                "board_count": nullable(integer(0)),
                "pin_count": nullable(integer(0)),
                "follower_count": nullable(integer(0)),
                "following_count": nullable(integer(0)),
                "monthly_views": nullable(integer(0)),
            },
            {
                "username": _TEXT,
                "business_name": nullable(string(0, 128)),
                "website_url": nullable(string(0, 512)),
            },
        ),
    ),
    _read(
        "board_list",
        "List boards",
        "The account's boards (public and protected by default; never secret), 25 a page. Board "
        "names and descriptions are untrusted.",
        {**_PAGED, "privacy": enum(("ALL", "PUBLIC", "PROTECTED"))},
        [],
        _out({"items": array(BOARD_ITEM, high=100), "next_cursor": nullable(CURSOR)}),
    ),
    _read(
        "board_get",
        "Get a board",
        "One board of the account, by its pnb_ ref.",
        {"board": ref("pinterest_board")},
        ["board"],
        _out(dict(_BOARD_FIELDS), _BOARD_UNTRUSTED),
    ),
    _read(
        "board_pins",
        "List a board's Pins",
        "The Pins on one board, 25 a page. Titles and descriptions are untrusted text.",
        {"board": ref("pinterest_board"), **_PAGED},
        ["board"],
        _out({"items": array(PIN_ITEM, high=100), "next_cursor": nullable(CURSOR)}),
    ),
    _read(
        "pin_list",
        "List the account's Pins",
        "The account's own Pins, newest first, 25 a page. Titles and descriptions are untrusted "
        "text.",
        _PAGED,
        [],
        _out({"items": array(PIN_ITEM, high=100), "next_cursor": nullable(CURSOR)}),
    ),
    _read(
        "pin_get",
        "Get a Pin",
        "One Pin by its pnp_ ref; metrics=true adds its 90-day and lifetime metrics.",
        {"pin": ref("pinterest_pin"), "metrics": BOOL},
        ["pin"],
        _out(dict(_PIN_FIELDS), _PIN_UNTRUSTED),
    ),
    _read(
        "pin_analytics",
        "Get Pin analytics",
        "Analytics for one Pin over a date range (YYYY-MM-DD, at most 90 days back and 90 wide): "
        "impressions, clicks, saves, video views and more, as a summary and by day.",
        {
            "pin": ref("pinterest_pin"),
            **_RANGE,
            "metric_types": array(enum(PIN_METRICS), low=1, high=15),
        },
        ["pin", "start_date", "end_date", "metric_types"],
        _out({"pin": ref("pinterest_pin"), **_ANALYTICS}),
    ),
    _read(
        "account_analytics",
        "Get account analytics",
        "The account's analytics over a date range (YYYY-MM-DD, at most 90 days back and 90 "
        "wide): engagement, impressions, clicks and saves, with rates, as a summary and by day.",
        {
            **_RANGE,
            "metric_types": array(enum(ACCOUNT_METRICS), low=1, high=9),
            "from_claimed_content": enum(CLAIMED),
            "pin_format": enum(PIN_FORMATS),
            "content_type": enum(CONTENT_TYPES),
            "source": enum(SOURCES),
        },
        ["start_date", "end_date"],
        _out(dict(_ANALYTICS)),
    ),
    _read(
        "media_status",
        "Check a video upload",
        "The processing status of one video upload (pnv_): registered, processing, succeeded "
        "or failed. A video Pin needs succeeded.",
        {"media": ref("pinterest_media")},
        ["media"],
        _out({"media": ref("pinterest_media"), "status": _MEDIA_STATUS}),
    ),
    _read(
        "publish_quota",
        "Publishing budget",
        "Pins this account created through comms in the last 24 h against its daily budget, and "
        "Pinterest's rate-limit headers as last seen.",
        {},
        [],
        _out(_QUOTA),
    ),
    _read(
        "pin_preview",
        "Preview a Pin",
        "Check one pin_create exactly as given (same arguments, no request_id): what it would "
        "make, whether policy, budget and a video's status allow it, and a preview_digest the "
        "create may echo. Makes nothing.",
        {
            "board": ref("pinterest_board"),
            "kind": enum(("image", "carousel", "video")),
            "url": _URL,
            "images": array(
                obj(
                    {
                        "url": _URL,
                        "title": string(1, 100),
                        "description": string(1, 800),
                        "link": _URL,
                    },
                    ["url"],
                ),
                low=2,
                high=5,
            ),
            "media": ref("pinterest_media"),
            "cover_url": _URL,
            "title": string(1, 100),
            "description": string(1, 800),
            "link": _URL,
            "alt_text": string(1, 500),
            "ai_disclosures": array(enum(("AI_MODIFIED", "SYNTHETIC_PERFORMER")), high=2),
        },
        ["account", "board", "kind"],
        _out(
            {
                "kind": enum(("image", "carousel", "video")),
                "board": ref("pinterest_board"),
                "images": nullable(integer(2, 5)),
                "media_status": _MEDIA_STATUS,
                "title_chars": integer(0, 100),
                "description_chars": integer(0, 800),
                "writes_allowed": BOOL,
                **_QUOTA,
                "refusal": nullable(string(1, 64)),
                "preview_digest": _DIGEST,
                "untrusted_text": nullable(string(0, 800)),
            }
        ),
        failures=("INVALID_ARGUMENT",),
    ),
)

_WRITE_FAILURES = ("IDENTITY_MISMATCH",)


def _result(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A write's structured truth (P §73) on the account it named."""
    return _out(
        {
            "actor": nullable(ACTOR),
            "result": enum(OUTCOMES),
            "code": nullable(string(1, 64)),
            "op_ref": nullable(ref("operation")),
            "replayed": BOOL,
            **(extra or {}),
        }
    )


def _write(
    name: str, title: str, description: str, inputs: Mapping[str, Any], required: Sequence[str],
    output: Mapping[str, Any], capability: C, *, prompt: bool = False,
) -> ToolSpec:  # fmt: skip
    """``prompt``: public or irreversible, so the host asks on every call (D-P3, section 9)."""
    return write(
        f"comms_pinterest_{name}", title, description, f"pinterest.{name}",
        {"account": ALIAS, **inputs}, ["account", *required], output,
        capability=capability, failures=_WRITE_FAILURES, requires_user_interaction=prompt,
    )  # fmt: skip


_PIN_INPUTS = {
    k: v for k, v in READ_TOOLS[12].input_schema["properties"].items() if k not in ("account",)
}

WRITE_TOOLS: tuple[ToolSpec, ...] = (
    _write(
        "board_create",
        "Create a board",
        "Create one board (name up to 180 characters; PUBLIC by default, or PROTECTED). Public "
        "and visible at once.",
        {
            "name": string(1, 180),
            "description": string(1, 500),
            "privacy": enum(("PUBLIC", "PROTECTED")),
        },
        ["name"],
        _result({"board": nullable(ref("pinterest_board"))}),
        C.BOARD_CREATE,
        prompt=True,
    ),
    _write(
        "video_upload",
        "Upload a video",
        "Register and upload one staged video (upl_ from comms_media_stage_*; mp4, mov or m4v, "
        "at most 16 MiB) for a video Pin. Returns a pnv_; check media_status until succeeded, "
        "then pin_create with kind video.",
        {"upload": ref("upload")},
        ["upload"],
        _result({"media": nullable(ref("pinterest_media"))}),
        C.MEDIA_UPLOAD,
    ),
    _write(
        "pin_create",
        "Create a Pin",
        "Publish one Pin to a board: an image from a public https URL Pinterest fetches, a "
        "carousel of 2 to 5 images, or a processed video upload with a cover image. Title up to "
        "100, description 800, link 2048, alt text 500. Public at once; counts against the daily "
        "budget.",
        {**_PIN_INPUTS, "preview_digest": _DIGEST},
        ["board", "kind"],
        _result({"pin": nullable(ref("pinterest_pin"))}),
        C.PIN_CREATE,
        prompt=True,
    ),
    _write(
        "pin_update",
        "Edit a Pin",
        "Change one Pin's title, description, link, alt text or board. Only the fields given "
        "change.",
        {
            "pin": ref("pinterest_pin"),
            "title": string(1, 100),
            "description": string(1, 800),
            "link": _URL,
            "alt_text": string(1, 500),
            "board": ref("pinterest_board"),
        },
        ["pin"],
        _result(),
        C.PIN_UPDATE,
    ),
    _write(
        "pin_delete",
        "Delete a Pin",
        "Delete one of the account's own Pins. Irreversible.",
        {"pin": ref("pinterest_pin")},
        ["pin"],
        _result(),
        C.PIN_DELETE,
        prompt=True,
    ),
)

PINTEREST_TOOLS: tuple[ToolSpec, ...] = (*READ_TOOLS, *WRITE_TOOLS)
