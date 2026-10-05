"""Proposed A49, plan IG-9: reading Stories (R-IG11; spec section 5.1, 7).

``story_list`` reads the account's live Stories (``GET /<IG_ID>/stories``; 🧪 GI-3 on the
Instagram Login host) as ``igm_`` refs, the same refs ``media_get`` reads. ``story_insights``
asks a Story's own metrics, checked first because Meta answers an unsupported combination with
an unknown error; under 5 viewers is ``NOT_ENOUGH_DATA``.
"""

import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from comms.core.errors import CommsError
from comms.mcp.catalog import TOOL_CATALOG
from tests.transports.instagram.fakes import USER_ID, USERNAME
from tests.transports.instagram.world import CLIENT, ig_world

SPECS = {s.name: s for s in TOOL_CATALOG}
STORY, STORY_2 = "17900000000000501", "17900000000000502"
STORIES = f"/v25.0/{USER_ID}/stories"


def _valid(tool, result):
    errors = list(
        Draft202012Validator(dict(SPECS[f"comms_instagram_{tool}"].output_schema)).iter_errors(
            result
        )
    )
    assert not errors, errors[0].message
    return result


def _json(status, body):
    return lambda _request: httpx.Response(status, json=body)


def _story(media_id, media_type="IMAGE"):
    return {"id": media_id, "media_type": media_type, "timestamp": "2026-10-04T10:00:00+0000",
            "username": USERNAME, "permalink": "https://www.instagram.com/stories/x/1/"}  # fmt: skip


@pytest.fixture
def world(tmp_path):
    w = ig_world(tmp_path)
    yield w
    w["conn"].close()


def _list(world, **args):
    return world["service"].story_list(CLIENT, {**args})


def test_story_list_reads_the_stories_edge_as_media_refs(world):
    world["fake"].routes[("GET", STORIES)] = _json(
        200, {"data": [_story(STORY), _story(STORY_2, "VIDEO")]}
    )
    out = _valid("story_list", _list(world))
    refs = [item["media"] for item in out["items"]]
    assert len(refs) == 2 and all(r.startswith("igm_") for r in refs)
    assert STORY not in json.dumps(out) and USER_ID not in json.dumps(out)
    asked = next(r for r in world["fake"].requests if r.url.path == STORIES)
    fields = asked.url.params["fields"].split(",")
    assert "caption" not in fields and "media_url" not in fields
    world["fake"].routes[("GET", f"/v25.0/{STORY}")] = _json(200, _story(STORY))
    got = _valid("media_get", world["service"].media_get({"media": refs[0]}))
    assert got["media"] == refs[0]  # a Story ref is an ordinary igm_


def test_story_list_pages_through_a_client_bound_cursor(world):
    def stories(request):
        if request.url.params.get("after") == "U1RPUlkx":
            return httpx.Response(200, json={"data": [_story(STORY_2)]})
        return httpx.Response(200, json={"data": [_story(STORY)],
                              "paging": {"cursors": {"after": "U1RPUlkx"}, "next": "https://n"}})  # fmt: skip

    world["fake"].routes[("GET", STORIES)] = stories
    first = _list(world, limit=1)
    assert first["next_cursor"].startswith("cur_") and "U1RPUlkx" not in json.dumps(first)
    second = _list(world, limit=1, cursor=first["next_cursor"])
    assert (
        second["next_cursor"] is None and second["items"][0]["media"] != first["items"][0]["media"]
    )
    with pytest.raises(CommsError) as stolen:  # a media_list cursor never reads Stories
        world["service"].media_list(CLIENT, {"limit": 1, "cursor": first["next_cursor"]})
    assert stolen.value.code == "STALE_HANDLE"


def _story_ref(world):
    world["fake"].routes[("GET", STORIES)] = _json(200, {"data": [_story(STORY)]})
    return _list(world)["items"][0]["media"]


def test_story_insights_ask_story_metrics(world):
    ref = _story_ref(world)
    path = f"/v25.0/{STORY}/insights"
    world["fake"].routes[("GET", path)] = _json(200, {"data": [
        {"name": "navigation", "period": "lifetime", "total_value": {"value": 12, "breakdowns": [
            {"results": [{"dimension_values": ["TAP_FORWARD"], "value": 9},
                         {"dimension_values": ["TAP_EXIT"], "value": 3}]}]}}]})  # fmt: skip
    out = _valid("story_insights", world["service"].story_insights(
        {"media": ref, "metrics": ["navigation"], "breakdown": "story_navigation_action_type"}))  # fmt: skip
    assert out["metrics"][0]["total"] == 12 and len(out["metrics"][0]["breakdown"]) == 2
    asked = next(r for r in world["fake"].requests if r.url.path == path)
    assert dict(asked.url.params) == {"metric": "navigation",
                                      "breakdown": "story_navigation_action_type"}  # fmt: skip


@pytest.mark.parametrize(
    "args",
    [
        {"metrics": ["likes"]},  # a Feed metric a Story does not have
        {"metrics": ["reach", "reach"]},
        {"metrics": ["reach"], "breakdown": "story_navigation_action_type"},
        {"metrics": ["navigation", "replies"], "breakdown": "story_navigation_action_type"},
        {"metrics": ["replies"], "breakdown": "action_type"},
        {"metrics": ["facebook_views"]},  # never requested (section 7)
        {"metrics": []},
    ],
)
def test_story_insights_refuse_what_meta_refuses_before_asking(world, args):
    ref = _story_ref(world)
    with pytest.raises(CommsError) as refused:
        world["service"].story_insights({"media": ref, **args})
    assert refused.value.code == "INVALID_ARGUMENT"
    assert not any(r.url.path.endswith("/insights") for r in world["fake"].requests)


def test_a_story_under_five_viewers_is_not_enough_data(world):
    ref = _story_ref(world)
    world["fake"].routes[("GET", f"/v25.0/{STORY}/insights")] = _json(
        400, {"error": {"code": 10, "message": "Not enough viewers"}}
    )
    with pytest.raises(CommsError) as refused:
        world["service"].story_insights({"media": ref, "metrics": ["reach", "replies"]})
    assert refused.value.code == "NOT_ENOUGH_DATA"


def test_a_story_ref_of_another_account_is_not_found(tmp_path):
    w = ig_world(tmp_path, accounts=("main", "studio"))
    ref = _story_ref(w)
    with pytest.raises(CommsError) as refused:
        w["service"].story_insights({"account": "studio", "media": ref, "metrics": ["reach"]})
    assert refused.value.code == "NOT_FOUND"
    w["conn"].close()
