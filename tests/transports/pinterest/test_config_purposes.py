"""Proposed A50, plan PN-1: the comms.json section, the alias grammar and the two per-account
purposes beside the static app secret (sections 4.2, 4.3)."""

import pytest

from comms.core.keys.purposes import (
    PINTEREST_APP_SECRET,
    PURPOSES,
    pinterest_token_purposes,
    purpose_of,
)
from comms.runtime.settings import SettingsError, load_settings
from comms.transports.pinterest.config import PinterestSettings, parse_pinterest

GOOD = {
    "app_id": "1234567",
    "redirect_uri": "https://raoof128.github.io/comms-mcp/pinterest/",
    "default": "sarabi",
    "daily_pin_budget": 20,
    "accounts": {"sarabi": {"label": "Sarabi's Fine Rugs", "writes": True, "sandbox": False}},
}


def _refuse(message):
    raise SettingsError(message)


def test_the_section_parses_with_its_defaults():
    out = parse_pinterest({**GOOD, "daily_pin_budget": 50}, _refuse)
    assert isinstance(out, PinterestSettings) and out.default == "sarabi"
    assert out.accounts["sarabi"].writes and not out.accounts["sarabi"].sandbox
    assert out.daily_pin_budget == 50 and out.app_id == "1234567"
    minimal = parse_pinterest({"app_id": "1", "redirect_uri": GOOD["redirect_uri"]}, _refuse)
    assert minimal.accounts == {} and minimal.default is None and minimal.daily_pin_budget == 50


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "app_id": "abc"},
        {**GOOD, "redirect_uri": "http://example.com/"},
        {**GOOD, "redirect_uri": "https://localhost/cb"},
        {**GOOD, "daily_pin_budget": 0},
        {**GOOD, "daily_pin_budget": 301},
        {**GOOD, "default": "ghost"},
        {**GOOD, "accounts": {"keystone": {"label": "x"}}},
        {**GOOD, "accounts": {"Sarabi": {"label": "x"}}},
        {**GOOD, "accounts": {"sarabi": {"label": "x", "dms": True}}},
        {**GOOD, "accounts": {"sarabi": {"writes": True}}},
        {**GOOD, "extra": 1},
        {**GOOD, "accounts": {"sarabi": {"label": "x", "sandbox": "yes"}}},
    ],
)
def test_a_malformed_section_is_refused(bad):
    with pytest.raises(SettingsError):
        parse_pinterest(bad, _refuse)


def test_comms_json_carries_the_section(tmp_path):
    path = tmp_path / "comms.json"
    path.write_text('{"local_port": 8766, "pinterest": ' + __import__("json").dumps(GOOD) + "}")
    path.chmod(0o600)
    settings = load_settings(path)
    assert settings.adapter.pinterest is not None
    assert settings.adapter.pinterest.accounts["sarabi"].label == "Sarabi's Fine Rugs"


def test_the_purposes_resolve_and_the_alias_grammar_refuses_secret_words():
    access, refresh = pinterest_token_purposes("sarabi")
    assert (access, refresh) == ("pinterest-access-token.sarabi", "pinterest-refresh-token.sarabi")
    for name in (access, refresh, PINTEREST_APP_SECRET):
        spec = purpose_of(name)
        assert spec is not None and (spec.kind, spec.rotation) == ("opaque", "staged")
    assert PINTEREST_APP_SECRET in PURPOSES
    for bad in ("pinterest-access-token.keystone", "pinterest-access-token.", "pinterest-token.x"):
        assert purpose_of(bad) is None
    with pytest.raises(ValueError):
        pinterest_token_purposes("my token")
