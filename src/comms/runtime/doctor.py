"""``comms doctor`` over the real state, read-only (D39-PRE Task E9).

It never writes: ``comms.db`` is opened with the pointer's key only (no pointer repair, no
migration, no latch, no re-anchor), ``meta.db`` read-only, and nothing is created when the state
is absent. It runs while a daemon runs. The report carries fixed codes and subjects (purposes,
phases), never material.

``ok`` is true when the only findings are ``CREDENTIAL_NOT_CONFIGURED`` (the owner's choice of
providers) or ``IG_TOKEN_EXPIRING`` (a warning); ``--production`` exits nonzero otherwise.

Proposed A49: the Instagram accounts in comms.json are checked against the registered ones and
their token metadata, offline. The identity check needs Meta and a token, so it is
``comms transport instagram doctor``'s, never this one's.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from comms.core.doctor import Finding, doctor
from comms.core.keys.purposes import instagram_token_purpose
from comms.core.keys.secrets import FileSecretStore, SecretStoreError
from comms.core.keys.slots import KeySlotStore, active_version
from comms.core.storage.db import CommsDbKeyError, open_comms_db
from comms.core.storage.migrations import MIGRATIONS
from comms.core.storage.rekey import ITEM, KeyPointer
from comms.runtime.paths import CommsPaths
from comms.runtime.settings import SettingsError, load_settings
from comms.runtime.state import bootstrap_state
from comms.transports.instagram import store as instagram_store
from comms.transports.instagram.doctor import findings as instagram_findings

__all__ = ["open_read_only", "run_doctor"]

_ACCEPTABLE = frozenset({"CREDENTIAL_NOT_CONFIGURED", "IG_TOKEN_EXPIRING"})
_INSTAGRAM_DETAIL = {
    "IG_ACCOUNT_UNREGISTERED": "in comms.json but never added (comms transport instagram account add)",
    "IG_ACCOUNT_UNCONFIGURED": "added but missing from comms.json",
    "IG_TOKEN_MISSING": "no active token",
    "IG_TOKEN_EXPIRED": "the token has expired: add the account's token again",
    "IG_TOKEN_EXPIRING": "the token expires within ten days (comms transport instagram token refresh)",
}


def _report(bootstrap: str, findings: list[Finding]) -> dict[str, Any]:
    return {
        "bootstrap": bootstrap,
        "findings": [{"code": f.code, "subject": f.subject, "detail": f.detail} for f in findings],
        "ok": all(f.code in _ACCEPTABLE for f in findings),
    }


def _legacy(paths: CommsPaths) -> tuple[Any, Any] | None:
    if not paths.legacy_db.exists():
        return None
    from comms.transports.telegram.disclosure.keys import checkpoint_public_for
    from comms.transports.telegram.keys.store import load_key, set_store_dir
    from comms.transports.telegram.runtime.cutover_barrier import legacy_verifier

    conn = sqlite3.connect(f"file:{paths.legacy_db}?mode=ro", uri=True)
    set_store_dir(paths.legacy_keys)
    return conn, legacy_verifier(load_key("audit-chain-key"), checkpoint_public_for(conn))


def _telegram_session(paths: CommsPaths) -> bool:
    """A logged-in session exists where the daemon keeps it (``state/telegram``)."""
    from comms.transports.telegram.telegram.telethon_adapter import SESSION_FILE

    return (paths.state_dir / "telegram" / SESSION_FILE).is_file()


def open_read_only(paths: CommsPaths) -> Any:
    """comms.db under the pointer's key only: no repair, no migration, nothing created."""
    key = FileSecretStore(paths.secrets_dir).get(ITEM, KeyPointer(paths.db_key_pointer).get())
    return open_comms_db(paths.db, key)


def _instagram(paths: CommsPaths, conn: Any, now: datetime) -> list[Finding]:
    """Proposed A49: each account's offline findings; metadata only, no network."""
    try:
        settings = load_settings(paths.settings).adapter.instagram
    except SettingsError:
        return [Finding("SETTINGS_INVALID", None, "comms.json does not load")]
    configured = sorted(settings.accounts) if settings is not None else []
    live = {
        row.alias: (row, active_version(conn, instagram_token_purpose(row.alias)) is not None)
        for row in instagram_store.live_accounts(conn)
    }
    return [
        Finding(code, report["alias"], _INSTAGRAM_DETAIL[code])
        for report in instagram_findings(configured, live, None, now=now)
        for code in report["codes"]
    ]


def run_doctor(paths: CommsPaths, *, now: datetime) -> dict[str, Any]:
    if not paths.db.exists() or not paths.db_key_pointer.exists():
        return _report(
            "UNINITIALIZED",
            [
                Finding(
                    "NOT_PROVISIONED", None, "comms is not provisioned (run: comms keys provision)"
                )
            ],
        )
    try:
        conn = open_read_only(paths)
    except (CommsDbKeyError, SecretStoreError):
        return _report(
            "UNINITIALIZED",
            [Finding("DB_KEY_INVALID", None, "the comms database key does not open comms.db")],
        )
    legacy = None
    try:
        row = conn.execute("SELECT max(version) FROM schema_version").fetchone()
        if row is None or row[0] != MIGRATIONS[-1].version:
            return _report(
                "UNINITIALIZED",
                [Finding("SCHEMA_BEHIND", None, "comms.db migrates when the daemon starts")],
            )
        store = KeySlotStore(paths.slots_dir)
        legacy = _legacy(paths)
        findings = doctor(
            conn,
            store,
            now=now,
            legacy_conn=None if legacy is None else legacy[0],
            legacy=None if legacy is None else legacy[1],
            telegram_session=_telegram_session(paths),
        )
        findings += _instagram(paths, conn, now)
        return _report(bootstrap_state(conn, store, paths), findings)
    finally:
        conn.close()
        if legacy is not None:
            legacy[0].close()
