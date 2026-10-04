"""Proposed A49, plan IG-4 (Stories: IG-8, R-IG10): publishing on the ``igk_`` ledger through the real executor
(sections 5.1, 5.2, 6, 8; D-I3, D-I7, D-I13; A19, A28; open question 3; R-IG6)."""

import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from comms.core import refs
from comms.core.errors import CommsError
from comms.mcp.catalog import TOOL_CATALOG
from comms.runtime.instagram import InstagramService
from comms.services.mutations import CRASH_POINTS, MutationCrash, MutationExecutor
from comms.transports.instagram import store
from comms.transports.instagram.messages import Throttle
from tests.core.campaign_helpers import NOW
from tests.transports.instagram.fakes import USER_ID, USERNAME
from tests.transports.instagram.world import CLIENT, ig_world

SPECS = {s.name: s for s in TOOL_CATALOG}
CREATION, CREATION_2, CAROUSEL, MEDIA_ID = (
    "17950000000000001",
    "17950000000000002",
    "17950000000000009",
    "17900000000000077",
)
IMAGE = {"kind": "image", "url": "https://cdn.example.com/p.jpg", "caption": "Hello #sydney"}
MEDIA_PATH, PUBLISH_PATH = f"/v25.0/{USER_ID}/media", f"/v25.0/{USER_ID}/media_publish"
QUOTA_PATH = f"/v25.0/{USER_ID}/content_publishing_limit"


def _valid(tool, result):
    errors = list(
        Draft202012Validator(dict(SPECS[f"comms_instagram_{tool}"].output_schema)).iter_errors(
            result
        )
    )
    assert not errors, errors[0].message
    return result


def _req():
    return refs.mint("request")


def _json(status, body):
    return lambda _request: httpx.Response(status, json=body)


def _quota(world, used=1, total=50):
    world["fake"].routes[("GET", QUOTA_PATH)] = _json(200, {"data": [
        {"quota_usage": used, "config": {"quota_total": total, "quota_duration": 86400}}]})  # fmt: skip


def _status(world, creation, status):
    world["fake"].routes[("GET", f"/v25.0/{creation}")] = _json(
        200, {"status_code": status, "id": creation}
    )


def _posts(world, path=None):
    return [r for r in world["fake"].requests
            if r.method == "POST" and (path is None or r.url.path == path)]  # fmt: skip


@pytest.fixture
def world(tmp_path):
    w = ig_world(tmp_path, accounts=("main", "studio"))
    _quota(w)
    w["fake"].routes[("POST", MEDIA_PATH)] = _json(200, {"id": CREATION})
    w["fake"].routes[("POST", PUBLISH_PATH)] = _json(200, {"id": MEDIA_ID})
    yield w
    w["conn"].close()


def _create(world, args=IMAGE, service=None, **extra):
    call = (service or world["service"]).container_create
    return call(CLIENT, {"account": "main", **args, "request_id": _req(), **extra})


def _publish(world, container, request_id=None, service=None):
    call = (service or world["service"]).publish
    return call(CLIENT, {"account": "main", "container": container,
                         "request_id": request_id or _req()})  # fmt: skip


def _crashing(world, point):
    return InstagramService(
        world["conn"], world["adapters"].instagram, world["capability"], world["handles"],
        clock=world["clock"], throttle=Throttle(sleep=lambda s: None),
        executor=MutationExecutor(world["writer"], world["adapters"].admin, crash_at=point),
        publisher=world["adapters"].publisher,
    )  # fmt: skip


def test_container_create_records_an_igk_and_sends_the_documented_body(world):
    out = _valid("container_create", _create(world))
    assert out["result"] == "SUCCEEDED" and out["container"].startswith("igk_")
    assert out["untrusted"]["account_username"] == USERNAME and CREATION not in json.dumps(out)
    (post,) = _posts(world)
    assert json.loads(post.content) == {"image_url": IMAGE["url"], "caption": IMAGE["caption"]}
    assert "caption" not in str(post.url) and "image_url" not in str(post.url)  # body, never URL
    assert world["adapters"].publisher.budget_used(_main(world)) == 1


def _main(world):
    return world["adapters"].instagram.resolve("main", for_write=True)


@pytest.mark.parametrize("point", CRASH_POINTS)
def test_container_create_replay_makes_one_container(world, point):
    args = {"account": "main", **IMAGE, "request_id": _req()}
    crashing = _crashing(world, point)
    try:
        crashing.container_create(CLIENT, args)
    except MutationCrash:
        pass
    again = world["service"].container_create(CLIENT, args)
    assert len(_posts(world, MEDIA_PATH)) <= 1  # CREATE is resolve-only: never a second one
    assert again["result"] in ("SUCCEEDED", "OUTCOME_UNKNOWN")
    if _posts(world, MEDIA_PATH):  # whatever the crash, a container Meta made is in the ledger
        assert world["adapters"].publisher.budget_used(_main(world)) == 1


def test_an_ambiguous_create_is_outcome_unknown_and_never_retried(world):
    world["fake"].routes[("POST", MEDIA_PATH)] = _json(500, {"error": {"code": 2}})
    args = {"account": "main", **IMAGE, "request_id": _req()}
    first = world["service"].container_create(CLIENT, args)
    again = world["service"].container_create(CLIENT, args)
    assert (first["result"], again["result"], again["replayed"]) == (
        "OUTCOME_UNKNOWN", "OUTCOME_UNKNOWN", True,
    )  # fmt: skip
    assert len(_posts(world, MEDIA_PATH)) == 1


def test_a_bad_url_is_refused_before_anything_is_recorded(world):
    for url in ("https://127.0.0.1/p.jpg", "https://user@cdn.example.com/p.jpg"):
        with pytest.raises(CommsError) as refused:
            _create(world, {**IMAGE, "url": url})
        assert refused.value.code == "INVALID_ARGUMENT"
    assert _posts(world) == []
    assert world["conn"].execute("SELECT count(*) FROM mutations").fetchone()[0] == 0


def test_the_container_budget_refuses_before_meta(world):
    main = _main(world)
    for n in range(400):
        store.record_container(world["conn"], main.account_id, "image", str(1700000 + n), now=NOW)
    out = _valid("container_create", _create(world))
    assert (out["result"], out["code"], out["op_ref"]) == ("FAILED", "CONTAINER_BUDGET", None)
    assert _posts(world) == []


def test_a_full_post_quota_refuses_before_meta(world):
    _quota(world, used=50, total=50)
    out = _create(world)
    assert (out["result"], out["code"]) == ("FAILED", "PUBLISH_CAP") and _posts(world) == []


def test_a_failed_quota_read_is_advisory(world):
    world["fake"].routes[("GET", QUOTA_PATH)] = _json(500, {"error": {"code": 2}})
    assert _create(world)["result"] == "SUCCEEDED"


def test_a_replay_answers_its_record_even_after_the_budget_fills(world):
    args = {"account": "main", **IMAGE, "request_id": _req()}
    first = world["service"].container_create(CLIENT, args)
    main = _main(world)
    for n in range(400):
        store.record_container(world["conn"], main.account_id, "image", str(1700000 + n), now=NOW)
    again = world["service"].container_create(CLIENT, args)
    assert (again["result"], again["replayed"], again["container"]) == (
        "SUCCEEDED", True, first["container"],
    )  # fmt: skip
    assert len(_posts(world)) == 1


def test_writes_false_refuses_every_publishing_write(tmp_path):
    w = ig_world(tmp_path, writes=False)
    _quota(w)
    for call in (
        lambda: _create(w),
        lambda: _publish(w, "igk_" + "a" * 26),
        lambda: w["service"].carousel_create(
            CLIENT,
            {
                "account": "main",
                "children": ["igk_" + "a" * 26, "igk_" + "b" * 26],
                "request_id": _req(),
            },
        ),
    ):
        with pytest.raises(CommsError) as refused:
            call()
        assert refused.value.code == "NOT_AUTHORIZED"
    assert _posts(w) == []
    w["conn"].close()


def test_publish_finished_publishes_once_and_names_the_media(world):
    container = _create(world)["container"]
    _status(world, CREATION, "FINISHED")
    out = _valid("publish", _publish(world, container))
    assert out["result"] == "SUCCEEDED" and out["media"].startswith("igm_")
    (post,) = _posts(world, PUBLISH_PATH)
    assert json.loads(post.content) == {"creation_id": CREATION}
    box = store.container(world["conn"], container, _main(world).account_id)
    assert (box.status, box.media_ref) == ("PUBLISHED", out["media"])
    assert MEDIA_ID not in json.dumps(out)


def test_publish_not_ready_is_failed_not_retried(world):
    container = _create(world)["container"]
    _status(world, CREATION, "IN_PROGRESS")
    out = _publish(world, container)
    assert (out["result"], out["code"]) == ("FAILED", "CONTAINER_NOT_READY")
    assert _posts(world, PUBLISH_PATH) == []
    _status(world, CREATION, "FINISHED")  # later, a new request_id on the same igk_
    assert _publish(world, container)["result"] == "SUCCEEDED"
    assert len(_posts(world, PUBLISH_PATH)) == 1


@pytest.mark.parametrize(
    ("status", "code"), [("ERROR", "CONTAINER_FAILED"), ("EXPIRED", "CONTAINER_EXPIRED")]
)
def test_a_dead_container_is_failed_with_its_code(world, status, code):
    container = _create(world)["container"]
    _status(world, CREATION, status)
    out = _publish(world, container)
    assert (out["result"], out["code"]) == ("FAILED", code) and _posts(world, PUBLISH_PATH) == []


def test_published_container_answers_succeeded_with_media(world):
    container = _create(world)["container"]
    _status(world, CREATION, "FINISHED")
    first = _publish(world, container)
    reads = len(world["fake"].requests)
    second = _publish(world, container)  # a new request_id: the ledger already knows
    assert (second["result"], second["media"]) == ("SUCCEEDED", first["media"])
    assert len(_posts(world, PUBLISH_PATH)) == 1
    assert all(r.url.path.endswith("/me") for r in world["fake"].requests[reads:])


def test_publish_resolves_by_status_after_crash(world):
    container = _create(world)["container"]
    _status(world, CREATION, "FINISHED")
    request_id = _req()
    with pytest.raises(MutationCrash):
        _publish(world, container, request_id, service=_crashing(world, "after_call"))
    replay = _publish(world, container, request_id)  # resolve-only: no second publish
    assert replay["result"] == "OUTCOME_UNKNOWN" and len(_posts(world, PUBLISH_PATH)) == 1
    _status(world, CREATION, "PUBLISHED")
    resolved = _publish(world, container)  # a new request_id: resolved by the ledger and status
    assert resolved["result"] == "SUCCEEDED" and resolved["media"].startswith("igm_")
    assert len(_posts(world, PUBLISH_PATH)) == 1


def test_publish_of_an_unrecorded_published_container_is_unknown(world):
    container = _create(world)["container"]
    _status(world, CREATION, "PUBLISHED")  # published elsewhere; comms never saw the media id
    out = _publish(world, container)
    assert (out["result"], out["media"]) == ("OUTCOME_UNKNOWN", None)
    assert _posts(world, PUBLISH_PATH) == []


def test_quota_cap_2207042_is_publish_cap(world):
    container = _create(world)["container"]
    _status(world, CREATION, "FINISHED")
    world["fake"].routes[("POST", PUBLISH_PATH)] = _json(
        400, {"error": {"code": 9, "error_subcode": 2207042}}
    )
    out = _publish(world, container)
    assert (out["result"], out["code"]) == ("FAILED", "PUBLISH_CAP")
    assert len(_posts(world, PUBLISH_PATH)) == 1


def test_a_child_or_foreign_container_cannot_be_published(world):
    child = _create(world, {"kind": "carousel_image", "url": IMAGE["url"]})["container"]
    out = _publish(world, child)
    assert (out["result"], out["code"]) == ("FAILED", "INVALID_ARGUMENT")
    studio = world["adapters"].instagram.resolve("studio", for_write=True)
    theirs = store.record_container(world["conn"], studio.account_id, "image", "1790555", now=NOW)
    with pytest.raises(CommsError) as foreign:
        _publish(world, theirs)
    assert foreign.value.code == "NOT_FOUND"
    assert _posts(world, PUBLISH_PATH) == []


def _children(world, n):
    made = []
    for i in range(n):
        world["fake"].routes[("POST", MEDIA_PATH)] = _json(200, {"id": str(1795000000 + i)})
        made.append(_create(world, {"kind": "carousel_image", "url": IMAGE["url"]})["container"])
    world["fake"].routes[("POST", MEDIA_PATH)] = _json(200, {"id": CAROUSEL})
    return made


def test_carousel_needs_2_to_10_same_account_children(world):
    children = _children(world, 3)
    out = _valid("carousel_create", world["service"].carousel_create(
        CLIENT, {"account": "main", "children": children, "caption": "Three",
                 "request_id": _req()}))  # fmt: skip
    assert out["result"] == "SUCCEEDED" and out["container"].startswith("igk_")
    body = json.loads(_posts(world, MEDIA_PATH)[-1].content)
    assert body == {"media_type": "CAROUSEL", "children": "1795000000,1795000001,1795000002",
                    "caption": "Three"}  # fmt: skip
    studio = world["adapters"].instagram.resolve("studio", for_write=True)
    theirs = store.record_container(world["conn"], studio.account_id, "child", "1790777", now=NOW)
    image = _create(world, IMAGE)["container"]
    sent = len(_posts(world))
    for bad, code in (([children[0], theirs], "NOT_FOUND"), ([children[0], image], "INVALID_ARGUMENT"),
                      ([children[0]], "INVALID_ARGUMENT")):  # fmt: skip
        with pytest.raises(CommsError) as refused:
            world["service"].carousel_create(
                CLIENT, {"account": "main", "children": bad, "request_id": _req()}
            )
        assert refused.value.code == code
    assert len(_posts(world)) == sent


def test_publish_quota_reads_meta_and_the_ledger(world):
    _create(world)
    out = _valid("publish_quota", world["service"].publish_quota({"account": "main"}))
    assert (out["quota_usage"], out["quota_total"], out["quota_duration"]) == (1, 50, 86400)
    assert (out["containers_last_24h"], out["container_budget"]) == (1, 400)
    asked = [r for r in world["fake"].requests if r.url.path == QUOTA_PATH][-1]
    assert asked.url.params["fields"] == "quota_usage,config"
    with pytest.raises(CommsError) as refused:
        world["service"].publish_quota({"account": "main", "since": 1})  # older than 24 h
    assert refused.value.code == "INVALID_ARGUMENT"


def test_preview_is_read_only_and_its_digest_binds_the_create(world):
    preview = _valid("publish_preview", world["service"].publish_preview(
        {"account": "main", "create": "container_create", **IMAGE}))  # fmt: skip
    assert preview["refusal"] is None and preview["writes_allowed"] is True
    assert (preview["kind"], preview["hashtags"], preview["caption_chars"]) == ("image", 1, 13)
    assert preview["untrusted_text"] == IMAGE["caption"] and _posts(world) == []
    assert world["conn"].execute("SELECT count(*) FROM mutations").fetchone()[0] == 0
    digest = preview["preview_digest"]
    with pytest.raises(CommsError) as changed:
        _create(world, {**IMAGE, "caption": "Something else"}, preview_digest=digest)
    assert changed.value.code == "INVALID_ARGUMENT" and _posts(world) == []
    assert _create(world, IMAGE, preview_digest=digest)["result"] == "SUCCEEDED"


def test_preview_reports_what_the_create_would_refuse(tmp_path):
    w = ig_world(tmp_path, writes=False)
    _quota(w, used=50, total=50)
    preview = w["service"].publish_preview(
        {"account": "main", "create": "container_create", **IMAGE}
    )
    assert (preview["writes_allowed"], preview["refusal"]) == (False, "NOT_AUTHORIZED")
    with pytest.raises(CommsError) as missing:
        w["service"].publish_preview({"create": "container_create", **IMAGE})
    assert missing.value.code == "INVALID_ARGUMENT"  # a preview names its account, as a write
    w["conn"].close()


def test_records_never_hold_captions_urls_or_ids(world):
    container = _create(world)["container"]
    _status(world, CREATION, "FINISHED")
    _publish(world, container)
    rows = json.dumps([list(r) for r in world["conn"].execute(
        "SELECT target_refs, result FROM mutations")] + [list(r) for r in world["conn"].execute(
        "SELECT payload FROM audit_events")])  # fmt: skip
    for secret in (IMAGE["caption"], IMAGE["url"], CREATION, MEDIA_ID, USER_ID):
        assert secret not in rows


@pytest.mark.parametrize(
    ("kind", "field"), [("story_image", "image_url"), ("story_video", "video_url")]
)
def test_a_story_is_a_stories_container_and_publishes(world, kind, field):
    """R-IG10: media_type STORIES with the one URL, recorded as a Story, published as any other."""
    url = "https://cdn.example.com/story"
    out = _valid("container_create", _create(world, {"kind": kind, "url": url}))
    assert out["result"] == "SUCCEEDED"
    (post,) = _posts(world, MEDIA_PATH)
    assert json.loads(post.content) == {"media_type": "STORIES", field: url}
    box = store.container(world["conn"], out["container"], _main(world).account_id)
    assert box.kind == "story"
    _status(world, CREATION, "FINISHED")
    published = _valid("publish", _publish(world, out["container"]))
    assert published["result"] == "SUCCEEDED" and published["media"].startswith("igm_")
    preview = _valid("publish_preview", world["service"].publish_preview(
        {"account": "main", "create": "container_create", "kind": kind, "url": url}))  # fmt: skip
    assert (preview["kind"], preview["refusal"]) == (kind, None)


def test_a_story_with_a_caption_is_refused_before_meta(world):
    with pytest.raises(CommsError) as refused:
        _create(world, {"kind": "story_image", "url": "https://cdn.example.com/s.jpg",
                        "caption": "Not on a Story"})  # fmt: skip
    assert refused.value.code == "INVALID_ARGUMENT" and _posts(world) == []
