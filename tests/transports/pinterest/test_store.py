"""Proposed A50, plan PN-1: schema v12 and the Pinterest tables (section 4.1)."""

from datetime import UTC, datetime, timedelta

import pytest
import sqlcipher3

from comms.core.audit.specs import validate_audit_event
from comms.core.errors import CommsError
from comms.core.identities import identities_of
from comms.core.refs import mint
from comms.core.storage.db import write_tx
from comms.transports.pinterest import store
from tests.core.audit.legacy_fixtures import comms_world

NOW = datetime(2026, 11, 2, tzinfo=UTC)
USER = "900000000000000001"


@pytest.fixture
def conn(tmp_path):
    w = comms_world(tmp_path)
    yield w["conn"]
    w["conn"].close()


def _add(conn, alias="main", user=USER):
    with write_tx(conn):
        return store.register_account(
            conn, alias, user, now=NOW, access_lifetime=timedelta(days=30),
            refresh_lifetime=timedelta(days=60),
        )  # fmt: skip


def test_migration_v12_adds_the_four_tables_and_no_existing_table_changes(conn):
    assert conn.execute("SELECT max(version) FROM schema_version").fetchone()[0] == 12
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "pinterest_accounts",
        "pinterest_objects",
        "pinterest_media",
        "pinterest_publications",
    } <= tables
    for other in ("delivery_identities", "contact_points", "destinations", "instagram_objects"):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (other,)).fetchone()[0]
        assert "pinterest" not in sql


def test_one_live_account_per_alias_and_per_user_and_the_binding_is_immutable(conn):
    ref = _add(conn)
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(conn):
        store.register_account(conn, "main", "900000000000000002", now=NOW,
                               access_lifetime=timedelta(1), refresh_lifetime=timedelta(1))  # fmt: skip
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(conn):
        store.register_account(conn, "other", USER, now=NOW,
                               access_lifetime=timedelta(1), refresh_lifetime=timedelta(1))  # fmt: skip
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(conn):
        conn.execute("UPDATE pinterest_accounts SET user_id = '1' WHERE ref = ?", (ref,))
    with write_tx(conn):
        store.remove_account(conn, ref, now=NOW)
    assert store.account_by_alias(conn, "main") is None
    again = _add(conn)
    assert again != ref and store.account_by_ref(conn, again).alias == "main"
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(conn):
        conn.execute("UPDATE pinterest_accounts SET removed_at = NULL WHERE ref = ?", (ref,))


def test_expiry_moves_and_the_refresh_expiry_only_with_a_new_refresh_token(conn):
    ref = _add(conn)
    with write_tx(conn):
        store.set_expiry(conn, ref, now=NOW + timedelta(days=10), access_lifetime=timedelta(days=30),
                         refresh_lifetime=None)  # fmt: skip
    row = store.account_by_ref(conn, ref)
    assert row.access_expires_at.startswith("2026-12-12") and row.refresh_expires_at.startswith(
        "2027-01-01"
    )
    with write_tx(conn):
        store.set_expiry(conn, ref, now=NOW + timedelta(days=10), access_lifetime=timedelta(days=30),
                         refresh_lifetime=timedelta(days=60))  # fmt: skip
    assert store.account_by_ref(conn, ref).refresh_expires_at.startswith("2027-01-11")


def test_objects_are_one_ref_per_identity_and_isolated_per_account(conn):
    a, b = _add(conn), _add(conn, "studio", "900000000000000003")
    ida, idb = store.account_by_ref(conn, a).id, store.account_by_ref(conn, b).id
    board = store.object_ref(conn, ida, "board", "549755885175", now=NOW)
    assert (
        board.startswith("pnb_")
        and store.object_ref(conn, ida, "board", "549755885175", now=NOW) == board
    )
    pin = store.object_ref(conn, ida, "pin", "1100000000000000001", now=NOW)
    assert pin.startswith("pnp_")
    assert store.resolve_object(conn, board, "board", ida) == "549755885175"
    for bad, kind, account in ((board, "board", idb), (board, "pin", ida), (pin, "board", ida)):
        with pytest.raises(CommsError) as refused:
            store.resolve_object(conn, bad, kind, account)
        assert refused.value.code in ("NOT_FOUND", "INVALID_ARGUMENT")
    with pytest.raises(CommsError):
        store.resolve_object(conn, "igm_" + "a" * 26, "pin", ida)
    assert identities_of(conn, board) == [{"transport": "pinterest", "identity": "549755885175"}]
    assert identities_of(conn, a) == [{"transport": "pinterest", "identity": USER}]


def test_the_media_ledger_and_the_publication_ledger(conn):
    ref = _add(conn)
    account = store.account_by_ref(conn, ref).id
    media = store.record_media(conn, account, "777000111", now=NOW, status="registered")
    assert media.startswith("pnv_") and store.media(conn, media, account).status == "registered"
    assert store.record_media(conn, account, "777000111", now=NOW, status="succeeded") == media
    store.mark_media(conn, media, "succeeded")
    assert store.media(conn, media, account).status == "succeeded"
    with pytest.raises(CommsError):
        store.mark_media(conn, media, "done")
    assert identities_of(conn, media) == [{"transport": "pinterest", "identity": "777000111"}]
    pin = store.object_ref(conn, account, "pin", "1100000000000000009", now=NOW)
    assert store.publications_since(conn, account, NOW - timedelta(hours=24)) == 0
    store.record_publication(conn, account, pin, now=NOW)
    store.record_publication(conn, account, pin, now=NOW)  # a repeat is a no-op
    assert store.publications_since(conn, account, NOW - timedelta(hours=24)) == 1
    assert store.publications_since(conn, account, NOW + timedelta(seconds=1)) == 0
    with pytest.raises(CommsError):
        store.record_publication(conn, account, "pnp_" + "a" * 26, now=NOW)


def test_audit_payload_accepts_the_pinterest_actor_and_event(conn):
    validate_audit_event(
        "admin.mutation_started", mint("operation"), "a" * 64,
        {"tool": "comms_pinterest_pin_create", "scope": "provider", "actor": "pinterest"},
    )  # fmt: skip
    validate_audit_event("admin.pinterest_account", mint("pinterest_account"), None,
                         {"action": "added"})  # fmt: skip
    with pytest.raises(ValueError):
        validate_audit_event("admin.pinterest_account", mint("instagram_account"), None,
                             {"action": "added"})  # fmt: skip


def test_reprs_never_show_identities(conn):
    ref = _add(conn)
    row = store.account_by_ref(conn, ref)
    assert USER not in repr(row)
    media = store.record_media(conn, row.id, "777000111", now=NOW, status="registered")
    assert "777000111" not in repr(store.media(conn, media, row.id))
