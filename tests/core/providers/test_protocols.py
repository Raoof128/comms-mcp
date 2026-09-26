"""comms v0.3 Task C2: core provider protocols, capability ids and states, ADAPTER_CONTRACTS."""

import re
from pathlib import Path

from comms.core.providers.capability import Capability, CapabilityState, is_available
from comms.core.providers.protocols import ADAPTER_CONTRACTS, ProviderResult, ProviderTarget

PROPOSAL = Path(__file__).resolve().parents[3] / "docs" / "provenance" / "comms-v0.3-proposal.md"
_ID = re.compile(r"[a-z_]+(\.[a-z_]+)+")


def _section_ids(number: int) -> set[str]:
    text = PROPOSAL.read_text(encoding="utf-8")
    start = text.index(f"\n# {number}. ")
    section = text[start : text.index("\n# ", start + 1)]
    ids = set()
    for block in re.findall(r"```text\n(.*?)```", section, re.DOTALL):
        ids.update(line.strip() for line in block.splitlines() if _ID.fullmatch(line.strip()))
    return ids


def test_unknown_is_never_available():
    assert [s for s in CapabilityState if is_available(s)] == [CapabilityState.AVAILABLE]
    assert not is_available(CapabilityState.UNKNOWN)


def test_capability_states_are_p_section_9():
    assert [s.value for s in CapabilityState] == [
        "AVAILABLE",
        "UNAVAILABLE",
        "NOT_AUTHORIZED",
        "ACCOUNT_INELIGIBLE",
        "PROVIDER_UNSUPPORTED",
        "NOT_CONFIGURED",
        "TEMPORARILY_UNAVAILABLE",
        "UNKNOWN",
    ]


def _a46_ids() -> set[str]:
    """The capabilities spec amendment A46 adds (owner, 2026-09-26), named in its text."""
    spec = (PROPOSAL.parents[1] / "comms-spec-v0.3.md").read_text(encoding="utf-8")
    start = spec.index("- **A46.")
    section = spec[start : spec.index("\n## ", start)]
    return set(re.findall(r"capability `([a-z_.]+)`", section))


def test_capability_ids_match_p_sections():
    expected = _section_ids(11) | _section_ids(14) | _section_ids(16)
    assert len(expected) > 60
    a46 = _a46_ids()
    assert a46 == {"member.tag", "reaction.remove", "reaction.clear", "phone_number.health"}
    assert {c.value for c in Capability} <= expected | a46
    assert expected <= {c.value for c in Capability}
    # A46's capabilities arrive with the task that builds them (G7; phone_number.health in G8)
    assert all(c.name == c.value.upper().replace(".", "_") for c in Capability)


def test_adapter_contracts_match_a18():
    assert ADAPTER_CONTRACTS == {
        "telegram_bot": frozenset({"delivery", "capability", "admin", "context"}),
        "telegram_user": frozenset({"delivery", "capability", "admin", "context"}),
        "whatsapp_cloud": frozenset({"delivery", "capability", "admin"}),
        "whatsapp_webhooks": frozenset({"inbound_context", "provider_updates"}),
    }


def test_provider_target_repr_holds_no_identity():
    target = ProviderTarget(
        transport="whatsapp",
        actor="whatsapp_cloud",
        destination_ref="dst_" + "a" * 26,
        identity="+61400000001",
    )
    assert "61400000001" not in repr(target) and "dst_" in repr(target)
    result = ProviderResult(outcome="SUCCEEDED", code=None, provider_ref="wamid.secret")
    assert "wamid" not in repr(result)
