"""Proposed A49, plan IG-1: schema v10 and the Instagram tables (R-IG2); plan IG-8: migration v11
lets the container ledger record a Story (R-IG10)."""

from datetime import UTC, datetime, timedelta

import pytest
import sqlcipher3

from comms.core.audit.specs import validate_audit_event
from comms.core.errors import CommsError
from comms.core.refs import mint
from comms.core.storage.db import write_tx
from comms.transports.instagram import store
from tests.core.audit.legacy_fixtures import comms_world

NOW = datetime(2026, 10, 4, tzinfo=UTC)
USER = "17841400000000001"


@pytest.fixture
def conn(tmp_path):
    w = comms_world(tmp_path)
    yield w["conn"]
    w["conn"].close()


def _add(conn, alias="main", user=USER):
    with write_tx(conn):
        return store.register_account(conn, alias, user, now=NOW, lifetime=timedelta(days=60))


def test_migration_v10_adds_tables_and_checks(conn):
    assert conn.execute("SELECT max(version) FROM schema_version").fetchone()[0] == 11
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"instagram_accounts", "instagram_containers", "instagram_objects"} <= tables
    for transport_table in ("delivery_identities", "contact_points", "destinations"):
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?", (transport_table,)
        ).fetchone()[0]
        assert "instagram" not in sql  # R-IG2: no existing table changes


def test_one_live_account_per_alias_and_per_user_and_the_binding_is_immutable(conn):
    ref = _add(conn)
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(conn):
        store.register_account(conn, "main", "17841400000000002", now=NOW, lifetime=timedelta(1))
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(conn):
        store.register_account(conn, "other", USER, now=NOW, lifetime=timedelta(1))
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(conn):
        conn.execute("UPDATE instagram_accounts SET user_id = '1' WHERE ref = ?", (ref,))
    with write_tx(conn):
        store.remove_account(conn, ref, now=NOW)
    assert store.account_by_alias(conn, "main") is None
    again = _add(conn)  # a removed alias may be added again, as a new ref
    assert again != ref and store.account_by_ref(conn, again).alias == "main"
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(conn):
        conn.execute("UPDATE instagram_accounts SET removed_at = NULL WHERE ref = ?", (ref,))


def test_account_repr_never_shows_the_user_id(conn):
    _add(conn)
    assert USER not in repr(store.account_by_alias(conn, "main"))


def test_object_refs_are_stable_and_scoped_to_their_account(conn):
    main = store.account_by_ref(conn, _add(conn))
    other = store.account_by_ref(conn, _add(conn, "other", "17841400000000002"))
    media = store.object_ref(conn, main.id, "media", "17900000000000001", now=NOW)
    assert media.startswith("igm_")
    assert store.object_ref(conn, main.id, "media", "17900000000000001", now=NOW) == media
    assert store.resolve_object(conn, media, "media", main.id) == "17900000000000001"
    with pytest.raises(CommsError) as refused:
        store.resolve_object(conn, media, "media", other.id)
    assert refused.value.code == "NOT_FOUND"
    with pytest.raises(CommsError):
        store.resolve_object(conn, media, "comment", main.id)
    assert store.object_ref(conn, main.id, "person", "9876543210", now=NOW).startswith("igp_")


def test_the_container_ledger_counts_a_rolling_window(conn):
    main = store.account_by_ref(conn, _add(conn))
    first = store.record_container(conn, main.id, "image", "17800000000000001", now=NOW)
    assert store.record_container(conn, main.id, "image", "17800000000000001", now=NOW) == first
    store.record_container(
        conn, main.id, "child", "17800000000000002", now=NOW + timedelta(hours=1)
    )
    assert store.containers_since(conn, main.id, NOW) == 2
    assert store.containers_since(conn, main.id, NOW + timedelta(minutes=30)) == 1
    store.mark_container(conn, first, "PUBLISHED", mint("instagram_media"))
    assert store.container(conn, first, main.id).status == "PUBLISHED"


def test_the_account_audit_event_is_typed():
    ref = mint("instagram_account")
    validate_audit_event("admin.instagram_account", ref, None, {"action": "added"})
    with pytest.raises(ValueError):
        validate_audit_event("admin.instagram_account", ref, None, {"action": "renamed"})
    with pytest.raises(ValueError):
        validate_audit_event(
            "admin.instagram_account", mint("operation"), None, {"action": "added"}
        )


def test_audit_payload_accepts_instagram_actor():
    validate_audit_event(
        "admin.mutation_started",
        mint("operation"),
        None,
        {"tool": "comms_instagram_publish", "scope": "provider", "actor": "instagram"},
    )


def test_migration_v11_keeps_every_v10_container_and_admits_a_story(tmp_path):
    """R-IG10: v11 rebuilds instagram_containers alone; rows, index and trigger survive."""
    from comms.core.storage.db import open_comms_db
    from comms.core.storage.migrations import MIGRATIONS, migrate
    from tests.core.schema_fixtures import KEY

    db = open_comms_db(tmp_path / "comms.db", KEY)
    assert migrate(db, MIGRATIONS[:10]) == 10
    _add(db)
    account = store.account_by_alias(db, "main")
    kept = store.record_container(db, account.id, "image", "1790001", now=NOW)
    with pytest.raises(CommsError):  # v10's ledger has no Story kind
        store.record_container(db, account.id, "story_unknown", "1790002", now=NOW)
    assert migrate(db) == 11
    box = store.container(db, kept, account.id)
    assert (box.kind, box.creation_id) == ("image", "1790001")
    story = store.record_container(db, account.id, "story", "1790003", now=NOW)
    assert store.container(db, story, account.id).kind == "story"
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(db):
        db.execute(
            "INSERT INTO instagram_containers (ref, account_id, kind, creation_id, created_at)"
            " VALUES (?, ?, 'post', '1790004', '2026-10-04T00:00:00Z')",
            (mint("instagram_container"), account.id),
        )
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError), write_tx(db):
        db.execute("UPDATE instagram_containers SET kind = 'reel' WHERE ref = ?", (story,))
    names = {
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE tbl_name = 'instagram_containers'"
        )
    }
    assert {"instagram_containers_recent", "instagram_containers_binding_immutable"} <= names
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    db.close()
