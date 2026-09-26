"""Catalog amendment G4, owner decision D5: a backup keeps every group's ``grp_`` ref.

R-E15 recorded that ``grp_`` refs were not in the backup, so a restore on a fresh installation
minted new ones and every saved group ref went stale. The payload now carries each group with
its destination. A compatible restore reuses them; a ref bound differently here is a staged
incompatibility, never a silent rebind; a payload from before carries none, and the restore mints
as before. A group whose provider this installation lacks is restored disabled, refs kept.
"""

import os

import pytest

from comms.core.backup import age
from comms.core.backup.export_import import (
    ImportRefused,
    StagedImports,
    _apply_directory,
    commit_import,
    export,
    stage_import,
)
from comms.core.backup.payload import _directory
from comms.core.campaigns import directory as d
from comms.core.groups import group_ref
from comms.core.installation import installation_ref
from comms.core.keys import rotate as rot
from comms.core.refs import mint
from comms.core.storage.db import write_tx
from tests.core import schema_fixtures as fx
from tests.core.audit.legacy_fixtures import comms_world
from tests.core.campaign_helpers import NOW

PEER = (501, 20)
PROVIDERS = {"meta_phone_number": "106540352242922", "meta_waba": "102290129340398"}
WA = "Y2FwaV9ncm91cDoxOTUwNTU1MDA3OToxMjAzNjMzOTQzMjAdOTY0MTUZD"


def _world(tmp_path, name):
    (tmp_path / name).mkdir(mode=0o700, exist_ok=True)
    w = comms_world(tmp_path / name)
    rot.rotate(w["writer"], w["store"], "backup-key", material=os.urandom(32),
               prove=lambda m: None, now=NOW)  # fmt: skip
    installation_ref(w["conn"], now=NOW)
    return w


def _groups(conn):
    return dict(
        conn.execute(
            "SELECT d.ref, g.ref FROM groups g JOIN destinations d ON d.id = g.destination_id"
        ).fetchall()
    )


@pytest.fixture
def env(tmp_path):
    source = _world(tmp_path, "a")
    conn = source["conn"]
    loc = d.add_location(conn, "L", now=NOW)
    tg = d.add_destination(conn, loc, "telegram", "group:77", "TG", normalize=fx.tg, now=NOW)
    wa = d.add_destination(conn, loc, "whatsapp", f"group:{WA}", "WA", normalize=lambda s: s,
                           now=NOW)  # fmt: skip
    d.add_destination(conn, loc, "telegram", "private:5", "DM", normalize=fx.tg, now=NOW)
    identity = age.generate_identity()
    key_file = tmp_path / "age.key"
    key_file.write_text(identity + "\n")
    key_file.chmod(0o600)
    exported = export(
        source["writer"], source["store"], age.recipient_of(identity), PROVIDERS, now=NOW
    )
    return {"source": source, "tg": tg, "wa": wa, "exported": exported, "key": key_file,
            "groups": _groups(conn), "tmp": tmp_path}  # fmt: skip


def _import(env, target, *, providers=PROVIDERS, adopt=True):
    staged = StagedImports()
    stage = stage_import(
        target["conn"], staged, PEER, env["exported"].ciphertext, env["exported"].sidecar,
        env["key"], providers=providers, trust_key=env["exported"].signer_key_id, adopt=adopt,
        now=NOW,
    )  # fmt: skip
    return stage, lambda: commit_import(
        target["writer"], target["store"], staged, stage.handle, PEER, now=NOW
    )


def test_the_payload_carries_each_group_with_its_destination(env):
    rows = _directory(env["source"]["conn"])["groups"]
    assert {r["destination_ref"]: r["ref"] for r in rows} == env["groups"]
    assert len(rows) == 2  # the private chat is a destination, not a group


def test_a_restore_on_a_fresh_installation_keeps_every_group_ref(env):
    target = _world(env["tmp"], "b")
    stage, commit = _import(env, target)
    assert stage.incompatibilities == ()
    commit()
    assert _groups(target["conn"]) == env["groups"]


def test_a_restore_onto_the_same_installation_reuses_the_refs(env):
    source = env["source"]
    _stage, commit = _import(env, source)
    commit()
    assert _groups(source["conn"]) == env["groups"]
    assert source["conn"].execute("SELECT count(*) FROM groups").fetchone()[0] == 2


def test_a_ref_bound_differently_here_is_a_staged_incompatibility(env):
    target = _world(env["tmp"], "b")
    conn = target["conn"]
    taken = env["groups"][env["tg"]]
    here = mint("destination")
    with write_tx(conn):  # this installation already uses the backup's grp_ for another group
        (loc,) = conn.execute(
            "INSERT INTO locations (ref, name, created_at) VALUES (?, 'Here', 'now') RETURNING id",
            (mint("location"),),
        ).fetchone()
        ident = fx.identity(conn, "telegram", "-99")
        conn.execute(
            "INSERT INTO destinations (ref, location_id, transport, platform_identity,"
            " identity_id, display_name, created_at) VALUES (?, ?, 'telegram', 'group:99', ?,"
            " 'Here', 'now')",
            (here, loc, ident),
        )
        conn.execute(
            "INSERT INTO groups (ref, destination_id, created_at)"
            " SELECT ?, id, 'now' FROM destinations WHERE ref = ?",
            (taken, here),
        )
    stage, commit = _import(env, target)
    assert stage.incompatibilities == ("GROUP_REF_CONFLICT",)
    with pytest.raises(ImportRefused):
        commit()
    assert _groups(target["conn"]) == {here: taken}  # nothing rebound


def test_a_payload_from_before_g4_mints_as_it_did(env):
    target = _world(env["tmp"], "b")
    directory = dict(_directory(env["source"]["conn"]))
    del directory["groups"]
    with write_tx(target["conn"]):
        _apply_directory(target["conn"], directory, "2026-09-26T00:00:00.000000Z")
    minted = _groups(target["conn"])
    assert set(minted) == {env["tg"], env["wa"]}
    assert all(ref.startswith("grp_") for ref in minted.values())


def test_a_group_whose_provider_is_missing_here_is_restored_disabled_with_its_refs(env):
    target = _world(env["tmp"], "b")
    _stage, commit = _import(env, target, providers={"meta_waba": "102290129340398"})
    commit()
    enabled = dict(target["conn"].execute("SELECT ref, enabled FROM destinations").fetchall())
    assert enabled[env["wa"]] == 0 and enabled[env["tg"]] == 1
    assert _groups(target["conn"]) == env["groups"]  # its grp_ is kept for when it returns


def test_group_ref_is_stable_after_restore(env):
    target = _world(env["tmp"], "b")
    _stage, commit = _import(env, target)
    commit()
    assert group_ref(target["conn"], env["tg"], now=NOW) == env["groups"][env["tg"]]
    assert mint("group") not in env["groups"].values()
