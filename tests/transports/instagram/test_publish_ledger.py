"""Proposed A49, plan IG-4: the ``igk_`` ledger is the 400-container budget (section 6; D-I7)."""

from datetime import timedelta

import pytest

from comms.core.errors import CommsError
from comms.transports.instagram import store
from comms.transports.instagram.publish import (
    CONTAINER_BUDGET,
    caption_counts,
    check_carousel,
    check_container,
)
from tests.core.campaign_helpers import NOW
from tests.transports.instagram.world import ig_world


@pytest.fixture
def world(tmp_path):
    w = ig_world(tmp_path, accounts=("main", "studio"))
    yield w
    w["conn"].close()


def _runtime(world, alias="main"):
    return world["adapters"].instagram.resolve(alias, for_write=True)


def test_the_budget_counts_a_rolling_24_hours_per_account(world):
    conn, main, studio = world["conn"], _runtime(world), _runtime(world, "studio")
    stamps = (NOW - timedelta(hours=25), NOW - timedelta(hours=23), NOW - timedelta(minutes=1))
    for n, at in enumerate(stamps):
        store.record_container(conn, main.account_id, "image", str(1790000 + n), now=at)
    store.record_container(conn, studio.account_id, "image", "1790099", now=NOW)
    publisher = world["adapters"].publisher
    assert CONTAINER_BUDGET == 400
    assert publisher.budget_used(main) == 2  # the 25-hour-old one has rolled off
    assert publisher.budget_used(studio) == 1


def test_a_container_id_is_recorded_once(world):
    conn, main = world["conn"], _runtime(world)
    first = store.record_container(conn, main.account_id, "reel", "1790001", now=NOW)
    again = store.record_container(conn, main.account_id, "reel", "1790001", now=NOW)
    assert first == again and first.startswith("igk_")
    assert world["adapters"].publisher.budget_used(main) == 1


def test_a_foreign_or_non_child_container_is_refused(world):
    conn, main, studio = world["conn"], _runtime(world), _runtime(world, "studio")
    theirs = store.record_container(conn, studio.account_id, "child", "1790010", now=NOW)
    mine = store.record_container(conn, main.account_id, "image", "1790011", now=NOW)
    child = store.record_container(conn, main.account_id, "child", "1790012", now=NOW)
    publisher = world["adapters"].publisher
    with pytest.raises(CommsError) as foreign:
        publisher.children(main, [child, theirs])
    assert foreign.value.code == "NOT_FOUND"
    with pytest.raises(CommsError) as not_child:
        publisher.children(main, [child, mine])
    assert not_child.value.code == "INVALID_ARGUMENT"
    assert [box.ref for box in publisher.children(main, [child])] == [child]


@pytest.mark.parametrize(
    "args",
    [
        {"kind": "image", "url": "https://cdn.example.com/a.jpg", "share_to_feed": True},
        {"kind": "reel", "url": "https://cdn.example.com/a.mp4", "alt_text": "x"},
        {"kind": "carousel_image", "url": "https://cdn.example.com/a.jpg", "caption": "x"},
        {"kind": "carousel_video", "url": "https://cdn.example.com/a.mp4", "location_id": "1"},
        {"kind": "carousel_image", "url": "https://cdn.example.com/a.jpg", "is_ai_generated": True},
        {"kind": "image", "url": "http://cdn.example.com/a.jpg"},
        {"kind": "image", "url": "https://127.0.0.1/a.jpg"},
        {
            "kind": "reel",
            "url": "https://cdn.example.com/a.mp4",
            "cover_url": "https://localhost/c",
        },
        {"kind": "reel", "url": "https://cdn.example.com/a.mp4", "thumb_offset": -1},
        {"kind": "image", "url": "https://cdn.example.com/a.jpg", "caption": "#a " * 31},
        {"kind": "image", "url": "https://cdn.example.com/a.jpg", "caption": "@a " * 21},
        {"kind": "image", "url": "https://cdn.example.com/a.jpg", "caption": "x" * 2201},
        {"kind": "image", "url": "https://cdn.example.com/a.jpg", "location_id": "Sydney"},
        {"kind": "story", "url": "https://cdn.example.com/a.jpg"},
    ],
)
def test_container_arguments_meta_would_refuse_are_refused_first(args):
    with pytest.raises(ValueError):
        check_container(args)


def test_valid_containers_pass():
    check_container({"kind": "image", "url": "https://cdn.example.com/a.jpg",
                     "caption": "#a " * 30 + "@b " * 20, "alt_text": "A dog", "location_id": "7",
                     "is_ai_generated": False})  # fmt: skip
    check_container({"kind": "reel", "url": "https://cdn.example.com/a.mp4", "share_to_feed": True,
                     "cover_url": "https://cdn.example.com/c.jpg", "thumb_offset": 1500})  # fmt: skip
    check_container({"kind": "carousel_image", "url": "https://cdn.example.com/a.jpg",
                     "alt_text": "x"})  # fmt: skip
    assert caption_counts("#one #two @raouf.studio email@x.com") == (2, 1)


def test_a_carousel_has_2_to_10_distinct_children():
    ref = "igk_" + "a" * 26
    others = ["igk_" + c * 26 for c in "bcdefghijk"]
    for children in ([ref], [ref, ref], [ref, *others]):
        with pytest.raises(ValueError):
            check_carousel({"children": children})
    with pytest.raises(ValueError):
        check_carousel({"children": [ref, "igm_" + "b" * 26]})
    with pytest.raises(ValueError):
        check_carousel({"children": [ref, others[0]], "alt_text": "x"})
    check_carousel({"children": [ref, *others[:9]], "caption": "Ten"})


STORY = "https://cdn.example.com/story.jpg"


@pytest.mark.parametrize(
    "extra",
    [
        {"caption": "Hi"},
        {"alt_text": "x"},
        {"location_id": "7"},
        {"share_to_feed": True},
        {"cover_url": "https://cdn.example.com/c.jpg"},
        {"thumb_offset": 10},
        {"is_ai_generated": True},
    ],
)
def test_a_story_takes_only_a_url(extra):
    """R-IG10: Meta accepts no caption, location, alt text, cover or AI label on a Story."""
    for kind in ("story_image", "story_video"):
        with pytest.raises(ValueError):
            check_container({"kind": kind, "url": STORY, **extra})
        check_container({"kind": kind, "url": STORY})
    with pytest.raises(ValueError):
        check_container({"kind": "story_image", "url": "http://cdn.example.com/s.jpg"})
