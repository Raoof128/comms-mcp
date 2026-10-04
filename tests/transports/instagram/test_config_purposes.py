"""Proposed A49, plan IG-1: comms.json's instagram section, the alias grammar and the
parameterised token purpose (sections 4.1 to 4.3; D-I4)."""

import json
import os

import pytest

from comms.core.audit.specs import validate_audit_event
from comms.core.keys.purposes import PURPOSES, instagram_alias, instagram_token_purpose, purpose_of
from comms.core.keys.secrets import FileSecretStore, SecretStoreError
from comms.core.keys.slots import key_id_for
from comms.runtime.settings import SettingsError, load_settings

GOOD = {
    "api_version": "v25.0",
    "default": "main",
    "accounts": {
        "main": {"label": "Main account", "writes": False, "dms": False},
        "studio": {"label": "Studio", "writes": True, "dms": True},
    },
}


def _settings(tmp_path, instagram):
    tmp_path.mkdir(exist_ok=True)
    home = tmp_path / "comms"
    home.mkdir(mode=0o700)
    os.chmod(home, 0o700)
    path = home / "comms.json"
    path.write_text(json.dumps({"instagram": instagram}))
    os.chmod(path, 0o600)
    return load_settings(path)


def test_the_instagram_section_parses_into_adapter_settings(tmp_path):
    settings = _settings(tmp_path, GOOD).adapter.instagram
    assert settings is not None and settings.default == "main"
    assert settings.accounts["studio"].writes and not settings.accounts["main"].writes
    assert settings.api_version == "v25.0" and settings.caption is False
    assert _settings(tmp_path / "c", {**GOOD, "caption": True}).adapter.instagram.caption is True


@pytest.mark.parametrize(
    "broken",
    [
        {**GOOD, "token": "x"},
        {**GOOD, "api_version": "latest"},
        {**GOOD, "default": "nobody"},
        {**GOOD, "accounts": {"Main": {"label": "x"}}},
        {**GOOD, "accounts": {"main": {"label": "x", "writes": "yes"}}},
        {**GOOD, "accounts": {"main": {"writes": True}}},
        {**GOOD, "accounts": {"main": {"label": "x", "owner": "me"}}},
        {**GOOD, "caption": "yes"},
    ],
)
def test_a_malformed_section_is_refused(tmp_path, broken):
    with pytest.raises(SettingsError):
        _settings(tmp_path, broken)


def test_alias_grammar_refuses_secret_substrings(tmp_path):
    for alias in ("keystone", "my_token", "seedling", "a" * 33, "Main", "a/b", ""):
        assert instagram_alias(alias) is None
    assert instagram_alias("studio-2") == "studio-2"
    with pytest.raises(SettingsError):  # comms.json refuses a secret-like key anywhere
        _settings(tmp_path, {"accounts": {"keystone": {"label": "x"}}})


def test_purpose_pattern_resolves_alias_and_refuses_unknown():
    spec = purpose_of("meta-ig-access-token.studio")
    assert spec is not None and (spec.kind, spec.rotation, spec.public_registry) == (
        "opaque",
        "staged",
        False,
    )
    assert purpose_of("meta-ig-access-token.keystone") is None
    assert purpose_of("meta-ig-access-token.") is None
    assert purpose_of("meta-ig-access-token.a/b") is None
    assert purpose_of("meta-access-token") is PURPOSES["meta-access-token"]
    assert instagram_token_purpose("main") == "meta-ig-access-token.main"
    with pytest.raises(ValueError):
        instagram_token_purpose("Main")
    assert key_id_for("meta-ig-access-token.main", b"x" * 40).startswith("opaque:sha256:")


def test_the_secret_store_holds_an_account_token_and_nothing_unknown(tmp_path):
    store = FileSecretStore(tmp_path / "secrets")
    store.put("meta-ig-access-token.main", 1, b"value")
    assert store.get("meta-ig-access-token.main", 1) == b"value"
    for item in ("meta-ig-access-token.Main", "meta-ig-access-token../x", "ig-token"):
        with pytest.raises(SecretStoreError):
            store.put(item, 1, b"value")


def test_credential_audit_events_accept_an_account_token_purpose():
    payload = {"purpose": "meta-ig-access-token.main", "old_version": 0, "new_version": 1}
    validate_audit_event("admin.credential_rotation", None, None, payload)
    with pytest.raises(ValueError):
        validate_audit_event(
            "admin.credential_rotation", None, None, {**payload, "purpose": "meta-ig-x"}
        )
