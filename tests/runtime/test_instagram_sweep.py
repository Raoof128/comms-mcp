"""Proposed A49, plan IG-6: every Instagram tool through the real dispatcher against a fake
graph.instagram.com (section 13 "Smoke"; R-IG4 (6)).

The daemon smoke (``scripts/smoke_sweep.py``) drives the selftest daemon, which configures no
Instagram account, so there each Instagram tool must answer ``NOT_CONFIGURED``. Here the same 22
tools run end to end, in the order an owner would use them, and each must succeed with a result
valid against its output schema.
"""

from datetime import timedelta

import httpx
import pytest
from jsonschema import Draft202012Validator

from comms.core import refs
from comms.mcp.catalog import TOOL_CATALOG
from comms.mcp.dispatch import AuthenticatedClient
from comms.transports.instagram import store
from tests.core.campaign_helpers import NOW
from tests.runtime.test_instagram_reads import _dispatcher
from tests.transports.instagram.fakes import USER_ID, USERNAME
from tests.transports.instagram.world import CLIENT, ig_world

SPECS = {s.name: s for s in TOOL_CATALOG}
INSTAGRAM = [s.name for s in TOOL_CATALOG if s.name.startswith("comms_instagram_")]
MEDIA, COMMENT, IGSID, CREATION = "17900000000000001", "17800000000000009", "9876543210", "1795001"
THREAD, MESSAGE = (
    "aWdfZAG06MTpJR01lc3NhZA2VUaHJlYWQ6MTc4NDE0",
    "aWdfZAG1faXRlbToxOklHTWVzc2FnZA0001",
)
STAMP = (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S+0000")


def _routes():
    item = {"id": MEDIA, "media_type": "IMAGE", "timestamp": STAMP, "like_count": 1,
            "comments_count": 1, "is_comment_enabled": True, "username": USERNAME}  # fmt: skip
    metric = {"data": [{"name": "reach", "period": "day", "values": [{"value": 5}]}]}
    ok = {"success": True}
    return {
        ("GET", "/v25.0/me/media"): {"data": [item]},
        ("GET", f"/v25.0/{MEDIA}"): item,
        ("GET", f"/v25.0/{MEDIA}/insights"): metric,
        ("GET", f"/v25.0/{USER_ID}/insights"): metric,
        ("GET", f"/v25.0/{MEDIA}/comments"): {"data": [
            {"id": COMMENT, "text": "Nice", "username": "fan", "timestamp": STAMP}]},
        ("GET", f"/v25.0/{COMMENT}/replies"): {"data": []},
        ("GET", f"/v25.0/{USER_ID}/tags"): {"data": [item]},
        ("GET", "/v25.0/me/conversations"): {"data": [
            {"id": THREAD, "participants": {"data": [{"id": IGSID, "username": "fan"}]}}]},
        ("GET", f"/v25.0/{THREAD}"): {"messages": {"data": [{"id": MESSAGE}]}},
        ("GET", f"/v25.0/{MESSAGE}"): {"id": MESSAGE, "from": {"id": IGSID}, "message": "hi",
                                       "created_time": STAMP},
        ("GET", f"/v25.0/{USER_ID}/content_publishing_limit"): {"data": [
            {"quota_usage": 0, "config": {"quota_total": 50, "quota_duration": 86400}}]},
        ("POST", f"/v25.0/{USER_ID}/media"): {"id": CREATION},
        ("GET", f"/v25.0/{CREATION}"): {"status_code": "FINISHED", "id": CREATION},
        ("POST", f"/v25.0/{USER_ID}/media_publish"): {"id": "17900000000000002"},
        ("POST", f"/v25.0/{COMMENT}/replies"): {"id": "17800000000000777"},
        ("POST", f"/v25.0/{COMMENT}"): ok,
        ("POST", f"/v25.0/{MEDIA}"): ok,
        ("DELETE", f"/v25.0/{COMMENT}"): ok,
        ("POST", f"/v25.0/{USER_ID}/messages"): {"recipient_id": IGSID, "message_id": MESSAGE},
    }  # fmt: skip


@pytest.fixture
def world(tmp_path):
    w = ig_world(tmp_path)
    for key, body in _routes().items():
        w["fake"].routes[key] = lambda _r, body=body: httpx.Response(200, json=body)
    made = iter(range(1795001, 1795100))  # each container Meta makes has its own id
    w["fake"].routes[("POST", f"/v25.0/{USER_ID}/media")] = lambda _r: httpx.Response(
        200, json={"id": str(next(made))}
    )
    yield w
    w["conn"].close()


def test_every_instagram_tool_succeeds_end_to_end(world):
    dispatcher = _dispatcher(world, world["service"])
    client = AuthenticatedClient(CLIENT, "cml1")
    seen: dict = {}

    def call(name, arguments):
        spec = SPECS[f"comms_instagram_{name}"]
        if spec.requires_request_id:
            arguments = {"account": "main", **arguments, "request_id": refs.mint("request")}
        result = dispatcher.call(client, spec.name, arguments)
        assert result.error_code is None, (spec.name, result.error_code)
        errors = list(Draft202012Validator(dict(spec.output_schema)).iter_errors(result.structured))
        assert not errors, (spec.name, errors[0].message)
        seen[spec.name] = result.structured
        return result.structured

    call("account_list", {})
    call("whoami", {})
    call("profile_get", {})
    media = call("media_list", {})["items"][0]["media"]
    call("media_get", {"media": media})
    call("media_insights", {"media": media, "metrics": ["reach"]})
    call("account_insights", {"metrics": ["views"], "breakdown": "follower_type"})
    comment = call("comment_list", {"media": media})["items"][0]["comment"]
    call("comment_replies", {"comment": comment})
    call("tag_list", {})
    person = call("conversation_list", {})["items"][0]["person"]
    call("conversation_messages", {"person": person})
    call("publish_quota", {})
    image = {"kind": "image", "url": "https://cdn.example.com/p.jpg", "caption": "Hi"}
    preview = call("publish_preview", {"account": "main", "create": "container_create", **image})
    container = call("container_create", {**image, "preview_digest": preview["preview_digest"]})
    children = [
        call("container_create", {"kind": kind, "url": image["url"]})["container"]
        for kind in ("carousel_image", "carousel_image")
    ]
    call("carousel_create", {"children": children})
    call("publish", {"container": container["container"]})
    story = call("container_create", {"kind": "story_image", "url": image["url"]})["container"]
    account_id = world["adapters"].instagram.resolve("main", for_write=True).account_id
    creation = store.container(world["conn"], story, account_id).creation_id
    world["fake"].routes[("GET", f"/v25.0/{creation}")] = lambda _r: httpx.Response(
        200, json={"id": creation, "status_code": "FINISHED"}
    )
    shared = call("publish", {"container": story})  # R-IG10: a Story, published as any other
    assert shared["result"] == "SUCCEEDED" and shared["media"].startswith("igm_")
    call("comment_reply", {"comment": comment, "text": "Thanks!"})
    call("comment_hide", {"comment": comment, "hide": True})
    call("comments_enabled_set", {"media": media, "enabled": False})
    call("comment_delete", {"comment": comment})
    call("message_send", {"person": person, "text": "Hello"})
    assert sorted(seen) == sorted(INSTAGRAM) and len(INSTAGRAM) == 22
