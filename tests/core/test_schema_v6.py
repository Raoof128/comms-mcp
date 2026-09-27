"""Catalog amendment G1: schema v6 rebuilds ``destinations`` so WhatsApp groups can be
destinations. The rebuild must keep every row, index and trigger of a populated v5 database, and
every recreated guard must still fire."""

import pytest
import sqlcipher3

from comms.core import refs
from comms.core.campaigns import directory as d
from comms.core.groups import group_ref
from comms.core.storage.db import open_comms_db, write_tx
from comms.core.storage.migrations import MIGRATIONS, migrate
from tests.core import schema_fixtures as fx
from tests.core.campaign_helpers import NOW

TABLES = ("destinations", "groups", "audience_members", "delivery_identities", "job_origins")


def _objects(conn):
    return sorted(
        conn.execute("SELECT type, name FROM sqlite_master WHERE type IN ('index', 'trigger')")
    )


def _rows(conn):
    return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in TABLES}


@pytest.fixture
def upgraded(tmp_path):
    conn = open_comms_db(tmp_path / "v5.db", fx.KEY)
    migrate(conn, MIGRATIONS[:5])
    w = fx.world(conn)
    loc = d.add_location(conn, "L", now=NOW)
    dst = d.add_destination(conn, loc, "telegram", "group:77", "G", normalize=fx.tg, now=NOW)
    dm = d.add_destination(conn, loc, "telegram", "private:5", "DM", normalize=fx.tg, now=NOW)
    aud = d.add_audience(conn, "A", now=NOW)
    d.add_audience_member(conn, aud, dst)
    grp = group_ref(conn, dst, now=NOW)
    before, objects = _rows(conn), _objects(conn)
    assert migrate(conn, MIGRATIONS[:6]) == 6
    return conn, w, {"dst": dst, "dm": dm, "grp": grp, "loc": loc}, before, objects


def test_the_rebuild_keeps_every_row_index_and_trigger(upgraded):
    conn, _w, made, before, objects = upgraded
    assert _rows(conn) == before
    assert _objects(conn) == objects
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert group_ref(conn, made["dst"], now=NOW) == made["grp"]  # never re-minted


def _raw(conn, transport, identity, loc_id=1):
    with write_tx(conn):
        ident = fx.identity(conn, transport, identity)
        conn.execute(
            "INSERT INTO destinations (ref, location_id, transport, platform_identity, identity_id,"
            " display_name, created_at) VALUES (?, ?, ?, ?, ?, 'x', 'now')",
            (refs.mint("destination"), loc_id, transport, identity, ident),
        )


def test_the_schema_itself_admits_a_whatsapp_group_and_nothing_else(upgraded):
    conn = upgraded[0]
    _raw(conn, "whatsapp", "group:Y2FwaV9ncm91cDox")
    for identity in ("+61400000009", "private:5", "channel:7", "group:"):
        with pytest.raises(sqlcipher3.dbapi2.IntegrityError):
            _raw(conn, "whatsapp", identity)


def test_every_recreated_guard_still_fires(upgraded):
    conn, w, made, *_ = upgraded
    guards = {
        "destination identity is immutable": "UPDATE destinations SET platform_identity = 'group:9'"
        " WHERE ref = ?",
        "endpoints are disabled, never deleted": "DELETE FROM destinations WHERE ref = ?",
    }
    for message, sql in guards.items():
        with pytest.raises(sqlcipher3.dbapi2.IntegrityError, match=message):
            conn.execute(sql, (made["dst"],))
    mismatch = pytest.raises(sqlcipher3.dbapi2.IntegrityError, match="endpoint transport mismatch")
    with mismatch, write_tx(conn):
        ident = fx.identity(conn, "whatsapp", "+61400000008")
        conn.execute(
            "INSERT INTO destinations (ref, location_id, transport, platform_identity,"
            " identity_id, display_name, created_at) VALUES (?, 1, 'telegram', 'group:5', ?,"
            " 'x', 'now')",
            (refs.mint("destination"), ident),
        )
    dm_id = conn.execute("SELECT id FROM destinations WHERE ref = ?", (made["dm"],)).fetchone()[0]
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError, match="not a group destination"):
        conn.execute(
            "INSERT INTO groups (ref, destination_id, created_at) VALUES (?, ?, 'now')",
            (refs.mint("group"), dm_id),
        )
    with pytest.raises(sqlcipher3.dbapi2.IntegrityError, match="origin endpoint does not match"):
        fx.origin(conn, w["job"], made["dst"])  # a Telegram destination for a WhatsApp job
    fx.origin(conn, w["job"], w["cp_ref"])  # the matching endpoint still goes in


def test_a_whatsapp_group_identity_can_still_be_redacted(upgraded):
    conn, _w, made, *_ = upgraded
    dst = d.add_destination(
        conn, made["loc"], "whatsapp", "group:ABCDEFGH12", "W", normalize=lambda s: s, now=NOW
    )
    (identity_id,) = conn.execute(
        "SELECT identity_id FROM destinations WHERE ref = ?", (dst,)
    ).fetchone()
    conn.execute(
        "UPDATE destinations SET platform_identity = ? WHERE ref = ?",
        (f"redacted:{identity_id}", dst),
    )
