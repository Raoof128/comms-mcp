"""Spec A47 (H6): the exit gate. The plan's tasks H0–H6, each by its owning tests, re-run in a
fresh process with nothing skipped; and A47's promises.

The checklist is read against the plan's own task titles, so the two cannot drift. Beyond the
owning tests: the frozen prohibition moved only as A47 says (``messages.ReadHistoryRequest``
under ``cap.message.mark_read`` alone), every Telegram media cell of the actor matrix is served
or an honest B, the real-daemon media checks are pinned, and the catalog holds 130 tools.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from comms.mcp.catalog import TOOL_CATALOG
from comms.transports.telegram.telegram.telethon_adapter import OPERATIONS

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-09-26-comms-v0.3-a47.md"
MATRIX = ROOT / "docs" / "verification" / "comms-v0.3-actor-matrix.md"
SMOKE_MAP = ROOT / "docs" / "verification" / "comms-v0.3-smoke-map.json"

EXIT_CHECKLIST: dict[str, tuple[str, ...]] = {
    "H0 A47 and R-G9b (done with this plan)": (
        "tests/security/test_v03_preflight.py",
        "tests/core/providers/test_protocols.py",
        "tests/conformance/test_meta_oracle.py",
    ),
    "H1 Telegram user mark-read": (
        "tests/transports/test_mark_read.py",
        "tests/security/test_phase4_architecture.py",
    ),
    "H2 Telegram `med_` refs from context items": ("tests/runtime/test_telegram_media_refs.py",),
    "H3 Telegram download": (
        "tests/transports/test_telegram_download.py",
        "tests/telegram/test_update_rpcs.py",
    ),
    "H4 `comms_message_send_media` (all three actors)": (
        "tests/transports/test_send_media.py",
        "tests/telegram/test_rpc_sets.py",
        "tests/mcp/test_catalog_messages.py",
    ),
    "H5 Telegram user upload and inspect": ("tests/transports/test_telegram_upload.py",),
    "H6 The guards, D39-A, the evidence": (
        "tests/security/test_media_fits_the_wire.py",
        "tests/mcp/test_catalog_pin.py",
        "tests/security/test_host_permissions.py",
        "tests/security/test_smoke_map.py",
        "tests/core/providers/test_actor_matrix.py",
        "tests/integration/test_actor_matrix_behaviour.py",
    ),
}
MEDIA_CHECKS = (
    "a staged photo is sent to a Telegram group by the bot, once, and replays",
    "a retained Telegram document pages back whole with its SHA-256",
)


def test_the_checklist_is_the_plan_task_list_in_full():
    titles = re.findall(r"^### Task (H\d+): (.+)$", PLAN.read_text(encoding="utf-8"), re.MULTILINE)
    assert [f"{n} {t}" for n, t in titles] == list(EXIT_CHECKLIST)


def test_a47_exit_checklist():
    ids = sorted({i for group in EXIT_CHECKLIST.values() for i in group})
    for target in ids:
        assert (ROOT / target).is_file(), target
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider", *ids],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=1200,
    )  # fmt: skip
    tail = done.stdout[-2000:] + done.stderr[-2000:]
    assert done.returncode == 0, tail
    assert re.search(r"\d+ passed", done.stdout), tail
    assert not re.search(r"\d+ (failed|skipped|errors?|deselected)", done.stdout), tail


def test_the_prohibition_moved_only_as_a47_says():
    holders = {op for op, names in OPERATIONS.items() if "messages.ReadHistoryRequest" in names}
    assert holders == {"cap.message.mark_read"}
    for absent in ("channels.ReadHistoryRequest", "messages.ReadMessageContentsRequest",
                   "messages.ReadMentionsRequest", "messages.ReadReactionsRequest"):  # fmt: skip
        assert not any(absent in names for names in OPERATIONS.values()), absent


def test_every_telegram_media_cell_is_served_or_an_honest_b():
    rows = {
        line.split("|")[1].strip(): line
        for line in MATRIX.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `comms_m")
    }
    for tool in ("comms_message_send_media", "comms_media_download", "comms_media_upload",
                 "comms_media_inspect", "comms_media_delete", "comms_message_mark_read"):  # fmt: skip
        (row,) = [line for name, line in rows.items() if name.startswith(f"`{tool}`")]
        bot, user = (cell.strip() for cell in row.split("|")[2:4])
        for cell in (bot, user):
            assert cell.startswith(("A done", "B", "—")), (tool, cell)
        assert user.startswith("A done") or tool == "comms_media_delete", (tool, user)


def test_the_real_daemon_media_checks_are_pinned_and_the_catalog_is_130():
    added = json.loads(SMOKE_MAP.read_text(encoding="utf-8"))["added_in_v0_3"]
    assert all(f"phase_v03_daemon::{c}" in added for c in MEDIA_CHECKS)
    assert len(TOOL_CATALOG) == 130
