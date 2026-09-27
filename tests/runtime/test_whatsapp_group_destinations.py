"""Catalog amendment G1 (spec A45): WhatsApp groups are destinations with ``grp_`` refs.

A WhatsApp group is a directory destination on the ``whatsapp`` transport whose identity is
``group:<group_id>``, normalised by one rule (``wa_group_id``). It gets its ``grp_`` in the
transaction that creates it, the group tools target it through ``whatsapp_cloud``, and its
context is the comms webhook archive (``whatsapp_webhook_archive``).

The 2026-docs gauntlet found Meta's group ids are opaque strings (its reference's sample is
``Y2FwaV9ncm91cDox…``), while the Graph client and ``group_id_of`` accepted digits only: every
real group call would have been refused. The one rule now accepts the documented shape.
"""

import json
import os

import pytest

from comms.core.campaigns import directory as d
from comms.core.errors import CommsError
from comms.core.keys import rotate as rot
from comms.core.providers.protocols import ProviderTarget
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.facades import group_targets
from comms.transports.whatsapp.cloud.groups import group_id_of
from comms.transports.whatsapp.cloud.http import GraphApi
from comms.transports.whatsapp.numbers import e164, wa_group_id
from comms.transports.whatsapp.webhooks.archive import ArchiveContext, CommsArchive
from tests.core.campaign_helpers import NOW
from tests.runtime.test_facades import CLIENT, _dispatcher
from tests.services.context_fixtures import Source
from tests.services.group_fixtures import group_world

META_ID = "Y2FwaV9ncm91cDoxOTUwNTU1MDA3OToxMjAzNjMzOTQzMjAdOTY0MTUZD"  # Meta's sample group id
JID_ID = "120363049891234567"


@pytest.mark.parametrize("group_id", [META_ID, JID_ID])
def test_the_one_rule_accepts_the_documented_group_ids(group_id):
    assert wa_group_id(f"group:{group_id}") == f"group:{group_id}"
    target = ProviderTarget("whatsapp", "whatsapp_cloud", "dst_w", f"group:{group_id}")
    assert group_id_of(target) == group_id
    assert GraphApi._group(group_id) == group_id


@pytest.mark.parametrize(
    "raw",
    [
        "+61400000001",  # a phone number is a contact, never a destination
        "61400000001",
        "group:",
        "group:-1001234567",  # a Telegram marked id
        "channel:77",
        "private:5",
        "user:9",
        "group:../../me",
        "group:abc/def",
        "group:a?b=c",
        "group:" + "A" * 129,
        " group:" + META_ID,
    ],
)
def test_the_one_rule_refuses_anything_else(raw):
    with pytest.raises(ValueError):
        wa_group_id(raw)


@pytest.fixture
def world(tmp_path):
    w = group_world(tmp_path)
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(
            w["writer"], w["store"], purpose, material=os.urandom(32), prove=lambda m: None, now=NOW
        )
    loc = d.add_location(w["conn"], "WA", now=NOW)
    dst = d.add_destination(
        w["conn"], loc, "whatsapp", f"group:{META_ID}", "Family", normalize=wa_group_id, now=NOW
    )
    w.update(wa_loc=loc, wa_dst=dst)
    return w


def _grp(conn, dst):
    rows = conn.execute(
        "SELECT g.ref FROM groups g JOIN destinations d ON d.id = g.destination_id WHERE d.ref = ?",
        (dst,),
    ).fetchall()
    return [r[0] for r in rows]


def test_a_whatsapp_group_destination_gets_its_group_ref_at_once(world):
    (grp,) = _grp(world["conn"], world["wa_dst"])
    assert grp.startswith("grp_")


def test_a_phone_number_is_refused_as_a_whatsapp_destination(world):
    for normalize in (wa_group_id, e164):  # even with the contact rule, it is not a group
        with pytest.raises(d.DirectoryError):
            d.add_destination(
                world["conn"], world["wa_loc"], "whatsapp", "+61400000002", "x",
                normalize=normalize, now=NOW,
            )  # fmt: skip


def test_the_same_group_twice_is_refused_and_its_ref_never_changes(world):
    before = _grp(world["conn"], world["wa_dst"])
    with pytest.raises(d.DirectoryError):
        d.add_destination(
            world["conn"], world["wa_loc"], "whatsapp", f"group:{META_ID}", "Again",
            normalize=wa_group_id, now=NOW,
        )  # fmt: skip
    assert _grp(world["conn"], world["wa_dst"]) == before
    assert (
        world["conn"]
        .execute("SELECT count(*) FROM destinations WHERE transport = 'whatsapp'")
        .fetchone()[0]
        == 1
    )


def test_its_targets_are_whatsapp_cloud_only(world):
    (grp,) = _grp(world["conn"], world["wa_dst"])
    actors = ("telegram_bot", "telegram_user", "whatsapp_cloud")
    assert group_targets(world["conn"], grp, actors) == {
        "whatsapp_cloud": ProviderTarget(
            "whatsapp", "whatsapp_cloud", world["wa_dst"], f"group:{META_ID}"
        )
    }
    with pytest.raises(CommsError) as refused:
        group_targets(world["conn"], grp, ("telegram_bot", "telegram_user"))
    assert refused.value.code == "NOT_CONFIGURED"
    with pytest.raises(CommsError) as refused:  # and a Telegram group is never WhatsApp's
        group_targets(world["conn"], world["grp"], ("whatsapp_cloud",))
    assert refused.value.code == "NOT_CONFIGURED"


def _group_webhook(*texts):
    messages = [
        {"from": "61400000001", "id": f"wamid.G{n}", "timestamp": str(1758800000 + n),
         "type": "text", "text": {"body": body}, "group_id": META_ID}
        for n, body in enumerate(texts)
    ]  # fmt: skip
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "waba", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp", "metadata": {"phone_number_id": "1234567890"},
            "contacts": [{"wa_id": "61400000001", "profile": {"name": "Sara"}}],
            "messages": messages}}]}]}).encode()  # fmt: skip


def _wa_dispatcher(world):
    CommsArchive(world["conn"], clock=lambda: NOW).ingest(_group_webhook("salaam", "nowruz?"))
    sources = {
        "telegram_bot": Source(provenance="telegram_local"),
        "whatsapp_cloud": ArchiveContext(world["conn"], clock=lambda: NOW),
    }
    return _dispatcher(world, sources, actors=("telegram_bot", "whatsapp_cloud"))


def test_its_context_is_the_webhook_archive_over_mcp(world):
    dispatcher = _wa_dispatcher(world)
    (grp,) = _grp(world["conn"], world["wa_dst"])
    page = dispatcher.call(CLIENT, "comms_context_recent", {"group": grp, "limit": 5})
    assert page.error_code is None, page.error_code
    items = page.structured["items"]
    assert [i["source"] for i in items] == ["whatsapp_webhook_archive"] * 2
    assert [i["untrusted_text"] for i in items] == ["nowruz?", "salaam"]
    assert all(i["message_ref"].startswith("cmg_") and i["group_ref"] == grp for i in items)
    assert META_ID not in json.dumps(page.structured) and "wamid" not in json.dumps(page.structured)
    # the Telegram group still reads Telegram
    tg = dispatcher.call(CLIENT, "comms_context_recent", {"group": world["grp"], "limit": 2})
    assert tg.error_code is None, tg.error_code
    assert {i["source"] for i in tg.structured["items"]} == {"telegram_local"}


def test_its_archive_pages_through_a_client_bound_cursor(world):
    dispatcher = _wa_dispatcher(world)
    (grp,) = _grp(world["conn"], world["wa_dst"])
    first = dispatcher.call(CLIENT, "comms_context_recent", {"group": grp, "limit": 1})
    assert first.error_code is None, first.error_code
    assert [i["untrusted_text"] for i in first.structured["items"]] == ["nowruz?"]
    cursor = first.structured["next_cursor"]
    assert cursor.startswith("cur_")
    second = dispatcher.call(CLIENT, "comms_context_page", {"cursor": cursor})
    assert second.error_code is None, second.error_code
    assert [i["untrusted_text"] for i in second.structured["items"]] == ["salaam"]
    other = AuthenticatedClient(client_ref="cli_" + "b" * 26, auth_kind="cml1")
    assert dispatcher.call(other, "comms_context_page", {"cursor": cursor}).error_code


def _three(world):
    CommsArchive(world["conn"], clock=lambda: NOW).ingest(_group_webhook("one", "two", "three"))
    sources = {"whatsapp_cloud": ArchiveContext(world["conn"], clock=lambda: NOW)}
    dispatcher = _dispatcher(world, sources, actors=("whatsapp_cloud",))
    (grp,) = _grp(world["conn"], world["wa_dst"])
    page = dispatcher.call(CLIENT, "comms_context_recent", {"group": grp, "limit": 5})
    refs_by_text = {i["untrusted_text"]: i["message_ref"] for i in page.structured["items"]}
    return dispatcher, grp, refs_by_text


def _texts(result):
    assert result.error_code is None, result.error_code
    return [i["untrusted_text"] for i in result.structured["items"]]


def test_one_archived_message_by_its_ref(world):
    dispatcher, grp, by = _three(world)
    got = dispatcher.call(CLIENT, "comms_message_get", {"group": grp, "message": by["two"]})
    assert _texts(got) == ["two"]
    assert got.structured["items"][0]["message_ref"] == by["two"]


@pytest.mark.parametrize("tool", ["comms_context_around_message", "comms_message_context"])
def test_messages_around_one_archived_message_newest_first(world, tool):
    dispatcher, grp, by = _three(world)
    args = {"group": grp, "message": by["two"], "before": 1, "after": 1}
    assert _texts(dispatcher.call(CLIENT, tool, args)) == ["three", "two", "one"]
    args = {"group": grp, "message": by["three"], "before": 5, "after": 0}
    assert _texts(dispatcher.call(CLIENT, tool, args)) == ["three", "two", "one"]
    args = {"group": grp, "message": by["one"], "before": 0, "after": 1}
    assert _texts(dispatcher.call(CLIENT, tool, args)) == ["two", "one"]


def test_the_archive_refuses_what_it_cannot_serve(world):
    """It served every read kind as "recent" before G1: a thread would have been answered with
    the wrong messages. A kind it has no index for is refused."""
    dispatcher, grp, by = _three(world)
    thread = dispatcher.call(CLIENT, "comms_context_thread", {"group": grp, "message": by["two"]})
    assert thread.error_code == "PROVIDER_UNSUPPORTED"
    search = dispatcher.call(CLIENT, "comms_context_search", {"groups": [grp], "query": "two"})
    assert search.error_code == "PROVIDER_UNSUPPORTED"


def test_a_message_of_another_group_is_not_found(world):
    dispatcher, _grp_ref, by = _three(world)
    tg = dispatcher.call(CLIENT, "comms_message_get", {"group": world["grp"], "message": by["two"]})
    assert tg.error_code == "NOT_CONFIGURED"  # a Telegram group, and only WhatsApp is configured
    other_loc = d.add_location(world["conn"], "Other", now=NOW)
    other = d.add_destination(
        world["conn"], other_loc, "whatsapp", "group:ABCDEFGH12", "Other",
        normalize=wa_group_id, now=NOW,
    )  # fmt: skip
    (other_grp,) = _grp(world["conn"], other)
    got = dispatcher.call(CLIENT, "comms_message_get", {"group": other_grp, "message": by["two"]})
    assert got.error_code == "NOT_FOUND"
