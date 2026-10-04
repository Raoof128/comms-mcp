"""Proposed A49, plan IG-5: ``requires_user_interaction`` (section 11; D-I3).

The public-posting and irreversible Instagram tools carry
``_meta: {"anthropic/requiresUserInteraction": true}``, so Claude Code prompts on every call,
whatever the permission mode. No other tool carries ``_meta``, so no other digest moves.
"""

import dataclasses
import json
from pathlib import Path

from comms.mcp.catalog import TOOL_CATALOG, tool_schema_digest, tools_list_payload
from comms.mcp.http import _tools

ROOT = Path(__file__).resolve().parents[2]
FLAGGED = {
    "comms_instagram_publish",
    "comms_instagram_comment_reply",
    "comms_instagram_comment_delete",
    "comms_instagram_message_send",
}
META = {"anthropic/requiresUserInteraction": True}


def test_meta_is_on_exactly_the_four_flagged_tools():
    payload = tools_list_payload()
    assert {e["name"] for e in payload if "_meta" in e} == FLAGGED
    assert all(e["_meta"] == META for e in payload if "_meta" in e)
    assert {s.name for s in TOOL_CATALOG if s.requires_user_interaction} == FLAGGED


def test_the_flag_is_part_of_the_pinned_digest():
    spec = next(s for s in TOOL_CATALOG if s.name == "comms_instagram_publish")
    unflagged = dataclasses.replace(spec, requires_user_interaction=False)
    assert tool_schema_digest(spec) != tool_schema_digest(unflagged)


def test_meta_reaches_the_wire_through_http_tools():
    wire = {t.name: t.model_dump(by_alias=True, exclude_none=True) for t in _tools()}
    assert {name for name, tool in wire.items() if "_meta" in tool} == FLAGGED
    assert wire["comms_instagram_publish"]["_meta"] == META


def test_every_flagged_tool_is_also_in_the_ask_list():
    ask = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["ask"]
    assert {f"mcp__comms__{name}" for name in FLAGGED} <= set(ask)
