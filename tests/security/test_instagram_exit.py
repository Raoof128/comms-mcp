"""Proposed A49, plan IG-6: the Instagram exit test (spec section 13 "Exit test").

One place that pins everything A49 adds to comms' surfaces, so a later change to any of them is
a deliberate edit here and a ruling, never a drift.
"""

import json
from pathlib import Path

from comms.core.audit.specs import _ACTORS as AUDIT_ACTORS
from comms.core.providers.protocols import ADAPTER_CONTRACTS
from comms.core.refs import CORE_PREFIXES
from comms.core.storage.migrations import MIGRATIONS
from comms.mcp.catalog import _TRANSPORT, TOOL_CATALOG, catalog_digest, tools_list_payload
from comms.mcp.egress import _BODY, _NAMES
from comms.mcp.schemas import ACTORS as MCP_ACTORS
from tests.mcp.test_catalog_pin import PENDING_A49, PIN
from tests.security.test_egress import NETWORK_MODULES

ROOT = Path(__file__).resolve().parents[2]

# Section 5's 22 tools, in catalog order: the 14 reads, then the 8 writes.
TOOLS = (
    "comms_instagram_account_list",
    "comms_instagram_whoami",
    "comms_instagram_profile_get",
    "comms_instagram_media_list",
    "comms_instagram_media_get",
    "comms_instagram_media_insights",
    "comms_instagram_account_insights",
    "comms_instagram_comment_list",
    "comms_instagram_comment_replies",
    "comms_instagram_tag_list",
    "comms_instagram_conversation_list",
    "comms_instagram_conversation_messages",
    "comms_instagram_publish_quota",
    "comms_instagram_publish_preview",
    "comms_instagram_container_create",
    "comms_instagram_carousel_create",
    "comms_instagram_publish",
    "comms_instagram_comment_reply",
    "comms_instagram_comment_hide",
    "comms_instagram_comments_enabled_set",
    "comms_instagram_comment_delete",
    "comms_instagram_message_send",
)
WRITES = TOOLS[14:]
PROMPTED = {
    "comms_instagram_publish",
    "comms_instagram_comment_reply",
    "comms_instagram_comment_delete",
    "comms_instagram_message_send",
}
CATALOG_DIGEST = "1032910948054f2585316d40eca1be973dfe6347ab7b8"  # a prefix of the pin (R-IG10)


def test_the_22_tools_in_order_and_the_catalog_digest():
    names = [s.name for s in TOOL_CATALOG]
    assert tuple(n for n in names if n.startswith("comms_instagram_")) == TOOLS
    assert len(TOOL_CATALOG) == PIN["count"] == 152
    assert catalog_digest() == PIN["catalog"] and PIN["catalog"].startswith(CATALOG_DIGEST)
    assert PENDING_A49 == {}  # every A49 capability has its tool


def test_exactly_the_eight_writes_need_a_request_id_and_are_in_the_ask_list():
    by_name = {s.name: s for s in TOOL_CATALOG}
    assert {n for n in TOOLS if by_name[n].requires_request_id} == set(WRITES)
    ask = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["ask"]
    assert {a for a in ask if a.startswith("mcp__comms__comms_instagram_")} == {
        f"mcp__comms__{n}" for n in WRITES
    }


def test_egress_classes():
    assert {n for n in _NAMES if n.startswith("comms_instagram_")} == set(TOOLS)
    assert {n for n in _BODY if n.startswith("comms_instagram_")} == {
        "comms_instagram_media_list",
        "comms_instagram_media_get",
        "comms_instagram_comment_list",
        "comms_instagram_comment_replies",
        "comms_instagram_tag_list",
        "comms_instagram_conversation_messages",
        "comms_instagram_publish_preview",
    }
    assert "transports/instagram/http.py" in NETWORK_MODULES


def test_meta_on_exactly_the_four_prompted_tools():
    flagged = {e["name"] for e in tools_list_payload() if "_meta" in e}
    assert flagged == PROMPTED


def test_actor_contracts_prefixes_enums_and_schema():
    assert ADAPTER_CONTRACTS["instagram"] == frozenset({"capability", "admin", "context"})
    # section 4.1's four plus the DM counterpart (R-IG2)
    assert {k: v for k, v in CORE_PREFIXES.items() if k.startswith("instagram_")} == {
        "instagram_account": "iga_",
        "instagram_container": "igk_",
        "instagram_media": "igm_",
        "instagram_comment": "igc_",
        "instagram_person": "igp_",
    }
    assert "instagram" in AUDIT_ACTORS and "instagram" in MCP_ACTORS
    assert "instagram" in _TRANSPORT["enum"]
    assert MIGRATIONS[-1].version == 11  # v11: a Story in the ledger (R-IG10)
