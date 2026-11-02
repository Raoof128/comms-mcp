"""Proposed A50, plan PN-3: the Pinterest writes through the real executor (sections 5.2, 6, 8;
D-P3, D-P7, D-P8; A19, A28)."""

import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from comms.core import refs
from comms.core.errors import CommsError
from comms.mcp.catalog import TOOL_CATALOG
from comms.runtime.pinterest import PinterestService
from comms.services.mutations import MutationCrash, MutationExecutor
from comms.transports.pinterest import store
from tests.transports.pinterest.fakes import UPLOAD_HOST, USERNAME
from tests.transports.pinterest.world import CLIENT, pn_world

SPECS = {s.name: s for s in TOOL_CATALOG}
BOARD_ID, PIN_ID, NEW_PIN, NEW_BOARD, MEDIA_ID = (
    "549755885175",
    "1100000000000000001",
    "1100000000000000777",
    "549755885999",
    "777000111",
)
IMAGE = {"kind": "image", "url": "https://cdn.sarabi.example/rug.jpg", "title": "Vintage Arak",
         "description": "Hand-knotted wool", "link": "https://sarabi.example/rug/1", "alt_text": "a rug"}  # fmt: skip


def _valid(tool, result):
    errors = list(Draft202012Validator(dict(SPECS[f"comms_pinterest_{tool}"].output_schema))
                  .iter_errors(result))  # fmt: skip
    assert not errors, errors[0].message
    return result


def _req():
    return refs.mint("request")


def _json(status, body):
    return lambda _request: httpx.Response(status, json=body)


def _pin(i, board=BOARD_ID, creative="REGULAR"):
    return {"id": i, "board_id": board, "created_at": "2026-11-01T10:00:00", "creative_type": creative,
            "media": {"media_type": "image"}, "is_owner": True, "title": "t", "description": "d"}  # fmt: skip


def _writes(world):
    return [r for r in world["fake"].requests if r.method in ("POST", "PATCH", "DELETE")]


def _seed(world):
    world["fake"].route("GET", "/v5/boards", 200, {"items": [{"id": BOARD_ID, "name": "Rugs", "privacy": "PUBLIC"}],
                                                   "bookmark": None})  # fmt: skip
    board = world["service"].board_list(CLIENT, {"account": "main"})["items"][0]["board"]
    world["fake"].route("GET", "/v5/pins", 200, {"items": [_pin(PIN_ID)], "bookmark": None})
    pin = world["service"].pin_list(CLIENT, {"account": "main"})["items"][0]["pin"]
    world["fake"].route("POST", "/v5/pins", 200, _pin(NEW_PIN))
    world["fake"].route(
        "POST", "/v5/boards", 200, {"id": NEW_BOARD, "name": "New", "privacy": "PUBLIC"}
    )
    world["fake"].route("PATCH", f"/v5/pins/{PIN_ID}", 200, _pin(PIN_ID))
    world["fake"].route("DELETE", f"/v5/pins/{PIN_ID}", 200, _pin(PIN_ID))
    world["fake"].route("POST", "/v5/media", 200, {
        "media_id": MEDIA_ID, "media_type": "video", "upload_url": UPLOAD_HOST,
        "upload_parameters": {"key": "uploads/1", "policy": "cG9saWN5", "x-amz-signature": "0" * 64,
                              "Content-Type": "multipart/form-data"}})  # fmt: skip
    world["fake"].route("GET", f"/v5/media/{MEDIA_ID}", 200, {"media_id": MEDIA_ID, "media_type": "video",
                                                               "status": "succeeded"})  # fmt: skip
    return board, pin


@pytest.fixture
def world(tmp_path):
    w = pn_world(tmp_path, accounts=("main", "studio"))
    w["seed"] = _seed(w)
    yield w
    w["conn"].close()


def _create(world, board, service=None, **extra):
    call = (service or world["service"]).pin_create
    return call(CLIENT, {"account": "main", "board": board, **IMAGE, "request_id": _req(), **extra})


def test_reading_hostile_text_causes_no_write(world):
    assert _writes(world) == []
    assert world["conn"].execute("SELECT count(*) FROM mutations").fetchone()[0] == 0


def test_pin_create_sends_the_documented_body_and_records_a_pin_and_a_publication(world):
    board, _ = world["seed"]
    out = _valid("pin_create", _create(world, board))
    assert (
        out["result"] == "SUCCEEDED"
        and out["actor"] == "pinterest"
        and out["pin"].startswith("pnp_")
    )
    assert out["untrusted"]["account_username"] == USERNAME and NEW_PIN not in json.dumps(out)
    (post,) = _writes(world)
    assert post.url.path == "/v5/pins" and json.loads(post.content) == {
        "board_id": BOARD_ID,
        "media_source": {"source_type": "image_url", "url": IMAGE["url"]},
        "title": "Vintage Arak", "description": "Hand-knotted wool",
        "link": IMAGE["link"], "alt_text": "a rug",
    }  # fmt: skip
    assert world["service"].publish_quota({"account": "main"})["pins_last_24h"] == 1
    payloads = [json.loads(p) for (p,) in world["conn"].execute(
        "SELECT payload FROM audit_events WHERE kind = 'admin.mutation_started'")]  # fmt: skip
    assert payloads[-1] == {
        "tool": "comms_pinterest_pin_create",
        "scope": "provider",
        "actor": "pinterest",
    }
    rows = world["conn"].execute("SELECT request_digest FROM mutations").fetchall()
    assert BOARD_ID not in json.dumps(rows) and IMAGE["title"] not in json.dumps(rows)


def test_pin_create_replay_makes_one_pin(world):
    board, _ = world["seed"]
    args = {"account": "main", "board": board, **IMAGE, "request_id": _req()}
    first = world["service"].pin_create(CLIENT, args)
    again = world["service"].pin_create(CLIENT, args)
    assert again["replayed"] is True and again["pin"] == first["pin"] and len(_writes(world)) == 1
    with pytest.raises(CommsError) as reuse:
        world["service"].pin_create(CLIENT, {**args, "title": "Other"})
    assert reuse.value.code == "REQUEST_ID_REUSE"


@pytest.mark.parametrize("point", ["before_call", "after_call", "after_record"])
def test_a_crash_at_any_point_never_creates_twice(world, point):
    board, _ = world["seed"]
    crashing = PinterestService(
        world["conn"], world["adapters"].pinterest, world["capability"], world["handles"],
        clock=world["clock"],
        executor=MutationExecutor(world["writer"], world["adapters"].admin, crash_at=point),
    )  # fmt: skip
    args = {"account": "main", "board": board, **IMAGE, "request_id": _req()}
    with pytest.raises(MutationCrash):
        crashing.pin_create(CLIENT, args)
    resumed = world["service"].pin_create(CLIENT, args)
    assert len(_writes(world)) <= 1  # CREATE is resolve-only: never a second Pin
    assert resumed["result"] in ("SUCCEEDED", "OUTCOME_UNKNOWN")
    budget = world["service"].publish_quota({"account": "main"})["pins_last_24h"]
    assert budget == len(_writes(world))  # a Pin Pinterest made is always in the ledger


def test_the_budget_refuses_before_pinterest(tmp_path):
    w = pn_world(tmp_path, budget=1)
    board, _ = _seed(w)
    assert _create(w, board)["result"] == "SUCCEEDED"
    refused = _valid("pin_create", _create(w, board))
    assert (refused["result"], refused["code"], refused["op_ref"]) == ("FAILED", "PIN_BUDGET", None)
    assert len(_writes(w)) == 1
    preview = w["service"].pin_preview({"account": "main", "board": board, **IMAGE})
    assert preview["refusal"] == "PIN_BUDGET" and preview["writes_allowed"] is True
    w["conn"].close()


def test_preview_binds_a_create_and_echoes_only_what_the_create_would_do(world):
    board, _ = world["seed"]
    preview = _valid(
        "pin_preview", world["service"].pin_preview({"account": "main", "board": board, **IMAGE})
    )
    assert (
        preview["kind"] == "image" and preview["refusal"] is None and preview["title_chars"] == 12
    )
    assert preview["untrusted_text"] == "Hand-knotted wool" and _writes(world) == []
    out = _create(world, board, preview_digest=preview["preview_digest"])
    assert out["result"] == "SUCCEEDED"
    with pytest.raises(CommsError) as refused:
        _create(world, board, title="Changed", preview_digest=preview["preview_digest"])
    assert refused.value.code == "INVALID_ARGUMENT" and len(_writes(world)) == 1


def test_wrong_account_and_foreign_board_are_refused_before_provider(world):
    board, _ = world["seed"]
    with pytest.raises(CommsError) as missing:
        world["service"].pin_create(CLIENT, {"board": board, **IMAGE, "request_id": _req()})
    assert missing.value.code == "INVALID_ARGUMENT"
    with pytest.raises(CommsError) as foreign:
        world["service"].pin_create(CLIENT, {"account": "studio", "board": board, **IMAGE,
                                             "request_id": _req()})  # fmt: skip
    assert foreign.value.code == "NOT_FOUND"
    assert (
        _writes(world) == []
        and world["conn"].execute("SELECT count(*) FROM mutations").fetchone()[0] == 0
    )


def test_writes_off_refuse_before_provider(tmp_path):
    w = pn_world(tmp_path, writes=False)
    board, _ = _seed(w)
    with pytest.raises(CommsError) as refused:
        _create(w, board)
    assert refused.value.code == "NOT_AUTHORIZED" and _writes(w) == []
    preview = w["service"].pin_preview({"account": "main", "board": board, **IMAGE})
    assert preview["writes_allowed"] is False and preview["refusal"] == "NOT_AUTHORIZED"
    w["conn"].close()


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "image"},  # no url
        {"kind": "image", "url": "http://cdn.example.com/x.jpg"},
        {"kind": "image", "url": "https://10.0.0.1/x.jpg"},
        {"kind": "image", "url": "https://cdn.example.com/x.jpg", "title": "t" * 101},
        {"kind": "image", "url": "https://cdn.example.com/x.jpg", "description": "d" * 801},
        {
            "kind": "image",
            "url": "https://cdn.example.com/x.jpg",
            "link": "https://user@x.example/",
        },
        {"kind": "image", "url": "https://cdn.example.com/x.jpg", "ai_disclosures": ["DEEPFAKE"]},
        {"kind": "carousel", "images": [{"url": "https://cdn.example.com/1.jpg"}]},
        {"kind": "carousel", "images": [{"url": "https://cdn.example.com/1.jpg", "extra": 1}] * 2},
        {"kind": "video", "cover_url": "https://cdn.example.com/c.jpg"},  # no media
        {"kind": "video", "media": "pnv_" + "a" * 26},  # no cover
        {"kind": "story", "url": "https://cdn.example.com/x.jpg"},
        {"kind": "image", "url": "https://cdn.example.com/x.jpg", "caption": "no such field"},
    ],
)
def test_malformed_pin_arguments_are_refused_before_anything_is_recorded(world, bad):
    board, _ = world["seed"]
    with pytest.raises(CommsError) as refused:
        world["service"].pin_create(
            CLIENT, {"account": "main", "board": board, **bad, "request_id": _req()}
        )
    assert refused.value.code in ("INVALID_ARGUMENT", "NOT_FOUND")
    assert _writes(world) == []


def test_a_carousel_sends_multiple_image_urls(world):
    board, _ = world["seed"]
    images = [
        {"url": "https://cdn.example.com/1.jpg", "title": "One"},
        {"url": "https://cdn.example.com/2.jpg"},
    ]
    out = world["service"].pin_create(CLIENT, {"account": "main", "board": board, "kind": "carousel",
                                               "images": images, "title": "Set", "request_id": _req()})  # fmt: skip
    assert out["result"] == "SUCCEEDED"
    (post,) = _writes(world)
    assert json.loads(post.content)["media_source"] == {"source_type": "multiple_image_urls",
                                                        "items": images, "index": 0}  # fmt: skip


def test_video_upload_registers_uploads_once_and_a_video_pin_waits_for_processing(world):
    board, _ = world["seed"]
    upload = world["service"].video_upload(
        CLIENT, {"account": "main", "upload": "upl_" + "a" * 26, "request_id": _req()},
        b"\x00\x00\x00 ftypmp42" * 100, "video/mp4",
    )  # fmt: skip
    out = _valid("video_upload", upload)
    assert (
        out["result"] == "SUCCEEDED"
        and out["media"].startswith("pnv_")
        and MEDIA_ID not in json.dumps(out)
    )
    register, upload_post = _writes(world)
    assert register.url.path == "/v5/media" and json.loads(register.content) == {
        "media_type": "video"
    }
    assert upload_post.url == UPLOAD_HOST and "authorization" not in upload_post.headers
    assert b"ftypmp42" in upload_post.content and b"cG9saWN5" in upload_post.content
    status = _valid(
        "media_status", world["service"].media_status({"account": "main", "media": out["media"]})
    )
    assert status["status"] == "succeeded"
    world["fake"].route(
        "GET", f"/v5/media/{MEDIA_ID}", 200, {"media_id": MEDIA_ID, "status": "processing"}
    )
    video = {
        "kind": "video",
        "media": out["media"],
        "cover_url": "https://cdn.example.com/c.jpg",
        "title": "V",
    }
    waiting = world["service"].pin_create(
        CLIENT, {"account": "main", "board": board, **video, "request_id": _req()}
    )
    assert (waiting["result"], waiting["code"]) == ("FAILED", "MEDIA_NOT_READY")
    assert [r.url.path for r in _writes(world)] == ["/v5/media", "/"]  # no Pin was posted
    world["fake"].route(
        "GET", f"/v5/media/{MEDIA_ID}", 200, {"media_id": MEDIA_ID, "status": "succeeded"}
    )
    world["fake"].route("POST", "/v5/pins", 200, _pin(NEW_PIN, creative="VIDEO"))
    done = world["service"].pin_create(
        CLIENT, {"account": "main", "board": board, **video, "request_id": _req()}
    )
    assert done["result"] == "SUCCEEDED"
    body = json.loads(_writes(world)[-1].content)
    assert body["media_source"] == {"source_type": "video_id", "media_id": MEDIA_ID,
                                    "cover_image_url": "https://cdn.example.com/c.jpg"}  # fmt: skip
    assert MEDIA_ID not in json.dumps(done)


def test_a_refused_upload_fails_and_an_ambiguous_one_is_unknown(world):
    world["fake"].upload_status = 403
    out = world["service"].video_upload(CLIENT, {"account": "main", "upload": "upl_" + "b" * 26,
                                                 "request_id": _req()}, b"x" * 10, "video/mp4")  # fmt: skip
    assert (out["result"], out["code"], out["media"]) == ("FAILED", "UPLOAD_FAILED", None)
    world["fake"].upload_status = 500
    out = world["service"].video_upload(CLIENT, {"account": "main", "upload": "upl_" + "c" * 26,
                                                 "request_id": _req()}, b"x" * 10, "video/mp4")  # fmt: skip
    assert out["result"] == "OUTCOME_UNKNOWN"
    with pytest.raises(CommsError):  # a mime that is not a video, refused before any call
        world["service"].video_upload(CLIENT, {"account": "main", "upload": "upl_" + "d" * 26,
                                               "request_id": _req()}, b"x", "image/png")  # fmt: skip
    assert world["conn"].execute("SELECT count(*) FROM pinterest_media").fetchone()[0] == 0


def test_board_create_update_and_delete_send_one_call_each(world):
    _board, pin = world["seed"]
    made = _valid("board_create", world["service"].board_create(
        CLIENT, {"account": "main", "name": "Kilims", "privacy": "PROTECTED", "request_id": _req()}))  # fmt: skip
    assert made["result"] == "SUCCEEDED" and made["board"].startswith("pnb_")
    edited = _valid("pin_update", world["service"].pin_update(
        CLIENT, {"account": "main", "pin": pin, "title": "New title", "board": made["board"], "request_id": _req()}))  # fmt: skip
    assert edited["result"] == "SUCCEEDED"
    gone = _valid("pin_delete", world["service"].pin_delete(
        CLIENT, {"account": "main", "pin": pin, "request_id": _req()}))  # fmt: skip
    assert gone["result"] == "SUCCEEDED"
    board_post, patch, delete = _writes(world)
    assert json.loads(board_post.content) == {"name": "Kilims", "privacy": "PROTECTED"}
    assert patch.method == "PATCH" and json.loads(patch.content) == {
        "title": "New title",
        "board_id": NEW_BOARD,
    }
    assert delete.method == "DELETE" and delete.url.path == f"/v5/pins/{PIN_ID}"
    with pytest.raises(CommsError):
        world["service"].board_create(CLIENT, {"account": "main", "name": "Secret", "privacy": "SECRET",
                                               "request_id": _req()})  # fmt: skip


def test_a_documented_refusal_is_failed_with_its_code_and_no_message(world):
    board, _ = world["seed"]
    world["fake"].route(
        "POST", "/v5/pins", 403, {"code": 3, "message": "PINNER_DATA_ACCESS_DENIED secret"}
    )
    out = _create(world, board)
    assert (out["result"], out["code"]) == ("FAILED", "NOT_AUTHORIZED")
    assert "secret" not in json.dumps(out)
    world["fake"].route("POST", "/v5/pins", 429, {"code": 6, "message": "x"})
    assert _create(world, board)["code"] == "RATE_LIMITED"
    assert world["service"].publish_quota({"account": "main"})["pins_last_24h"] == 0
    rows = [json.loads(p) for (p,) in world["conn"].execute(
        "SELECT payload FROM audit_events WHERE kind = 'admin.mutation_finished'")]  # fmt: skip
    assert rows[-2:] == [{"state": "FAILED", "provider_code": "NOT_AUTHORIZED"},
                         {"state": "FAILED", "provider_code": "RATE_LIMITED"}]  # fmt: skip


def test_a_ref_of_the_wrong_kind_is_refused(world):
    board, _pin = world["seed"]
    with pytest.raises(CommsError):
        world["service"].pin_update(
            CLIENT, {"account": "main", "pin": board, "title": "x", "request_id": _req()}
        )
    with pytest.raises(CommsError):
        world["service"].pin_delete(
            CLIENT, {"account": "main", "pin": "pnp_" + "z" * 26, "request_id": _req()}
        )
    assert _writes(world) == []
    assert store.account_by_alias(world["conn"], "main") is not None
