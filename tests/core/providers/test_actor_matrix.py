"""Catalog amendment G6a (spec A45): full admin on both APIs — the actor matrix holds.

`docs/verification/comms-v0.3-actor-matrix.md` has one cell per provider tool and actor:
- `A done [cap]`: `SUPPORT[cap]` must include the actor;
- `B [cap]`: `SUPPORT[cap]` must exclude it, so its capability reports `PROVIDER_UNSUPPORTED`;
- `B [cap] (groups)`: the capability exists in 1:1 chats but not for the group-addressed tool;
- `A todo:G<n>`: the API supports it and task G<n> builds it (G9 requires none left).

Every catalog tool is either a matrix row or a local tool.
"""

import fnmatch
import re
from pathlib import Path

from comms.core.providers.capability import Capability
from comms.core.providers.semantics import SUPPORT
from comms.mcp.catalog import TOOL_CATALOG

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "docs" / "verification" / "comms-v0.3-actor-matrix.md"
ACTORS = ("telegram_bot", "telegram_user", "whatsapp_cloud")
KIND = re.compile(r"^(A done|A todo:G\d+[a-z]?|B)\b")
CATALOG = {spec.name for spec in TOOL_CATALOG}


def _names(cell):
    patterns = re.findall(r"`([a-z_*]+)`", cell)
    found = set()
    for pattern in patterns:
        matched = fnmatch.filter(CATALOG, pattern)
        assert matched, f"{pattern} names no catalog tool"
        found.update(matched)
    return found


def _rows():
    text = MATRIX.read_text(encoding="utf-8")
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].startswith("`comms_"):
            yield _names(cells[0]), dict(zip(ACTORS, cells[1:], strict=True))


def _local():
    text = MATRIX.read_text(encoding="utf-8")
    section = text[text.index("## Local tools") :]
    names = set()
    for pattern in re.findall(r"`([a-z_*]+)`", section):
        names.update(fnmatch.filter(CATALOG, pattern))
    return names


def _caps(cell):
    head = cell.split(":", 1)[0] if not cell.startswith("A todo") else cell.split(":", 2)[1]
    return [Capability(c) for c in re.findall(r"\[([a-z_.]+)\]", head)]


def test_every_catalog_tool_is_a_row_or_a_local_tool():
    rowed = set().union(*(names for names, _cells in _rows()))
    assert rowed | _local() >= CATALOG, sorted(CATALOG - rowed - _local())
    assert not rowed & _local(), sorted(rowed & _local())


def test_every_cell_is_well_formed_and_every_b_names_its_reason():
    for names, cells in _rows():
        for actor, cell in cells.items():
            assert KIND.match(cell), (sorted(names), actor, cell)
            if cell.startswith("B"):
                assert ":" in cell and cell.split(":", 1)[1].strip(), (sorted(names), actor)


def test_the_matrix_agrees_with_what_the_code_supports():
    for names, cells in _rows():
        for actor, cell in cells.items():
            for capability in _caps(cell):
                if cell.startswith("A done"):
                    assert actor in SUPPORT[capability], (sorted(names), actor, capability)
                elif cell.startswith("B") and "(groups)" not in cell.split(":", 1)[0]:
                    assert actor not in SUPPORT[capability], (sorted(names), actor, capability)


def test_the_open_work_is_named_by_task():
    todo = [
        (min(names), actor, re.match(r"A todo:G\d+[a-z]?", cell).group(0))
        for names, cells in _rows()
        for actor, cell in cells.items()
        if cell.startswith("A todo")
    ]
    assert all(
        kind in ("A todo:G1", "A todo:G6", "A todo:G7", "A todo:G8") for *_x, kind in todo
    ), todo
