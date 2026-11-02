"""Proposed A50, plan PN-4: the Pinterest exit test (spec section 11).

One place that pins everything A50 adds to comms' surfaces, so a later change to any of them is
a deliberate edit here and a ruling, never a drift.
"""

import json
from pathlib import Path

from comms.core.audit.specs import _ACTORS as AUDIT_ACTORS
from comms.core.keys.purposes import PURPOSES, purpose_of
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ADAPTER_CONTRACTS
from comms.core.providers.semantics import SUPPORT
from comms.core.refs import CORE_PREFIXES
from comms.core.storage.migrations import MIGRATIONS
from comms.mcp.catalog import _TRANSPORT, TOOL_CATALOG, catalog_digest, tools_list_payload
from comms.mcp.egress import _BODY, _NAMES
from comms.mcp.schemas import ACTORS as MCP_ACTORS
from tests.mcp.test_catalog_pin import PIN
from tests.security.test_egress import NETWORK_MODULES

ROOT = Path(__file__).resolve().parents[2]

# Section 5's 18 tools, in catalog order: the 13 reads, then the 5 writes.
TOOLS = (
    "comms_pinterest_account_list",
    "comms_pinterest_whoami",
    "comms_pinterest_profile_get",
    "comms_pinterest_board_list",
    "comms_pinterest_board_get",
    "comms_pinterest_board_pins",
    "comms_pinterest_pin_list",
    "comms_pinterest_pin_get",
    "comms_pinterest_pin_analytics",
    "comms_pinterest_account_analytics",
    "comms_pinterest_media_status",
    "comms_pinterest_publish_quota",
    "comms_pinterest_pin_preview",
    "comms_pinterest_board_create",
    "comms_pinterest_video_upload",
    "comms_pinterest_pin_create",
    "comms_pinterest_pin_update",
    "comms_pinterest_pin_delete",
)
WRITES = TOOLS[13:]
PROMPTED = {
    "comms_pinterest_board_create",
    "comms_pinterest_pin_create",
    "comms_pinterest_pin_delete",
}
CATALOG_DIGEST = "09c2da271299cb22"  # a prefix of the pin (R-PN2)


def test_the_18_tools_in_order_and_the_catalog_digest():
    names = [s.name for s in TOOL_CATALOG]
    assert tuple(n for n in names if n.startswith("comms_pinterest_")) == TOOLS
    assert names[-18:] == list(TOOLS)  # appended after A49's, so earlier order holds
    assert len(TOOL_CATALOG) == PIN["count"] == 172
    assert catalog_digest() == PIN["catalog"] and PIN["catalog"].startswith(CATALOG_DIGEST)


def test_exactly_the_five_writes_need_a_request_id_and_are_in_the_ask_list():
    by_name = {s.name: s for s in TOOL_CATALOG}
    assert {n for n in TOOLS if by_name[n].requires_request_id} == set(WRITES)
    ask = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["ask"]
    assert {a for a in ask if a.startswith("mcp__comms__comms_pinterest_")} == {
        f"mcp__comms__{n}" for n in WRITES
    }


def test_egress_classes():
    assert {n for n in _NAMES if n.startswith("comms_pinterest_")} == set(TOOLS)
    assert {n for n in _BODY if n.startswith("comms_pinterest_")} == {
        "comms_pinterest_board_list",
        "comms_pinterest_board_get",
        "comms_pinterest_board_pins",
        "comms_pinterest_pin_list",
        "comms_pinterest_pin_get",
        "comms_pinterest_pin_preview",
    }
    assert {"transports/pinterest/http.py", "transports/pinterest/upload.py"} <= set(
        NETWORK_MODULES
    )


def test_meta_on_exactly_the_three_prompted_tools():
    flagged = {e["name"] for e in tools_list_payload() if "_meta" in e}
    assert {n for n in flagged if n.startswith("comms_pinterest_")} == PROMPTED


def test_actor_contracts_prefixes_enums_purposes_and_schema():
    assert ADAPTER_CONTRACTS["pinterest"] == frozenset({"capability", "admin"})
    assert {k: v for k, v in CORE_PREFIXES.items() if k.startswith("pinterest_")} == {
        "pinterest_account": "pna_",
        "pinterest_board": "pnb_",
        "pinterest_pin": "pnp_",
        "pinterest_media": "pnv_",
    }
    assert "pinterest" in AUDIT_ACTORS and "pinterest" in MCP_ACTORS
    assert "pinterest" in _TRANSPORT["enum"]
    assert MIGRATIONS[-1].version == 12
    assert "pinterest-app-secret" in PURPOSES
    assert purpose_of("pinterest-access-token.sarabi") is not None
    assert purpose_of("pinterest-refresh-token.sarabi") is not None
    only = {C.BOARD_LIST, C.BOARD_GET, C.BOARD_CREATE, C.PIN_LIST, C.PIN_GET, C.PIN_CREATE,
            C.PIN_UPDATE, C.PIN_DELETE, C.MEDIA_STATUS_READ}  # fmt: skip
    assert {c for c in C if SUPPORT[c] == ("pinterest",)} == only
    assert "pinterest" in SUPPORT[C.MEDIA_UPLOAD] and "pinterest" in SUPPORT[C.INSIGHTS_READ]
