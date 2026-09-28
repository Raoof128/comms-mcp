"""Catalog amendment G8 (part d), owner decision D3: staged media, media upload and download,
and group photos on all three APIs.

A file is staged in memory for one client (``upl_``), in order, capped at 16 MiB, checked
against its SHA-256, used once and forgotten after five minutes; a small one may come inline.
Bytes never enter a request digest (their SHA-256 and size do). A download is paged in bounded
base64 slices. A group photo takes staged bytes directly on every API.
"""

import base64
import hashlib
import os

import httpx
import pytest

from comms.core import refs
from comms.core.errors import CommsError
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import ProviderTarget, SemanticOperation
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.adapters import Adapters
from comms.runtime.comms_runtime import build_comms_runtime
from comms.runtime.selftest import _OneSecret
from comms.services.mutations import request_digest
from comms.services.uploads import CHUNK_MAX, MAX_BYTES, TTL_S, StagedMedia
from comms.transports.telegram.bot.admin import BotAdmin
from comms.transports.telegram.bot.http import BotApi
from comms.transports.whatsapp.cloud.groups import GroupDiscovery, WhatsAppAdmin
from comms.transports.whatsapp.cloud.media import MediaOps
from tests.conformance.meta_oracle import oracle, oracle_transport
from tests.conformance.test_meta_oracle import _api
from tests.core.campaign_helpers import NOW
from tests.services.context_fixtures import Clock
from tests.services.group_fixtures import Provider, group_world
from tests.transports.telegram_user.test_admin_chat import SUPER, _invoke

ALICE, BOB = "cli_" + "a" * 26, "cli_" + "b" * 26
CLIENT = AuthenticatedClient(client_ref=ALICE, auth_kind="cml1")
JPEG = b"\xff\xd8\xff" + os.urandom(120_000)


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _stage(staged, data, mime="image/jpeg", client=ALICE):
    begun = staged.begin(client, mime, len(data), hashlib.sha256(data).hexdigest())
    for seq, start in enumerate(range(0, len(data), CHUNK_MAX)):
        staged.chunk(client, begun["upload"], seq, _b64(data[start : start + CHUNK_MAX]))
    return begun["upload"]


def _code(call):
    with pytest.raises(CommsError) as refused:
        call()
    return refused.value.code


class Ticks:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_a_staged_file_comes_back_whole_once_for_its_request():
    staged = StagedMedia()
    upload = _stage(staged, JPEG)
    assert staged.take(ALICE, upload, "req_1") == (JPEG, "image/jpeg")
    assert staged.take(ALICE, upload, "req_1") == (JPEG, "image/jpeg")  # its replay
    assert _code(lambda: staged.take(ALICE, upload, "req_2")) == "NOT_FOUND"  # used once


def test_chunks_are_strictly_in_order_and_bound_to_their_client():
    staged = StagedMedia()
    begun = staged.begin(ALICE, "image/jpeg", 10, hashlib.sha256(b"0123456789").hexdigest())
    upload = begun["upload"]
    assert _code(lambda: staged.chunk(ALICE, upload, 1, _b64(b"01234"))) == "INVALID_ARGUMENT"
    assert _code(lambda: staged.chunk(BOB, upload, 0, _b64(b"01234"))) == "NOT_FOUND"
    staged.chunk(ALICE, upload, 0, _b64(b"01234"))
    assert _code(lambda: staged.chunk(ALICE, upload, 0, _b64(b"01234"))) == "INVALID_ARGUMENT"
    assert _code(lambda: staged.chunk(ALICE, upload, 1, _b64(b"0123456"))) == "INVALID_ARGUMENT"
    assert _code(lambda: staged.take(BOB, upload, "r")) == "NOT_FOUND"


def test_an_incomplete_or_altered_file_is_refused_and_dropped():
    staged = StagedMedia()
    begun = staged.begin(ALICE, "image/jpeg", 4, hashlib.sha256(b"abcd").hexdigest())
    staged.chunk(ALICE, begun["upload"], 0, _b64(b"abc"))
    assert _code(lambda: staged.take(ALICE, begun["upload"], "r")) == "INVALID_ARGUMENT"
    assert _code(lambda: staged.take(ALICE, begun["upload"], "r")) == "NOT_FOUND"
    wrong = staged.begin(ALICE, "image/jpeg", 4, hashlib.sha256(b"abcd").hexdigest())
    staged.chunk(ALICE, wrong["upload"], 0, _b64(b"abce"))
    assert _code(lambda: staged.take(ALICE, wrong["upload"], "r")) == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    ("mime", "size", "sha"),
    [("image/jpeg", MAX_BYTES + 1, "a" * 64), ("image/jpeg", 0, "a" * 64),
     ("jpeg", 10, "a" * 64), ("image/jpeg", 10, "A" * 64), ("image/jpeg", 10, "a" * 63)],
)  # fmt: skip
def test_a_bad_begin_is_refused(mime, size, sha):
    assert _code(lambda: StagedMedia().begin(ALICE, mime, size, sha)) == "INVALID_ARGUMENT"


def test_a_staged_file_expires():
    ticks = Ticks()
    staged = StagedMedia(clock=ticks)
    upload = _stage(staged, b"x" * 10, "text/plain")
    ticks.t = TTL_S + 1
    assert _code(lambda: staged.take(ALICE, upload, "r")) == "NOT_FOUND"


def test_a_replayed_begin_stages_one_file():
    staged = StagedMedia()
    sha = hashlib.sha256(b"x").hexdigest()
    first = staged.replayed(ALICE, "req_b", lambda: staged.begin(ALICE, "text/plain", 1, sha))
    again = staged.replayed(ALICE, "req_b", lambda: staged.begin(ALICE, "text/plain", 1, sha))
    assert again == {**first, "replayed": True} and first["replayed"] is False


# -- through the dispatcher, over the Meta oracle ----------------------------------------------


@pytest.fixture
def world(tmp_path):
    from comms.core.keys import rotate as rot

    w = group_world(tmp_path)
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(w["writer"], w["store"], purpose, material=os.urandom(32),
                   prove=lambda m: None, now=NOW)  # fmt: skip
    graph = oracle()
    api = _api(graph)
    discovery = GroupDiscovery(api)
    discovery.discover()
    adapters = Adapters(
        capability={"whatsapp_cloud": Provider(S.AVAILABLE)},
        admin={"whatsapp_cloud": WhatsAppAdmin(api, discovery)},
        media=MediaOps(api, download_transport=oracle_transport(graph)),
        account=ProviderTarget("whatsapp", "whatsapp_cloud", "account", "waba:102290129340398"),
    )
    built = build_comms_runtime(w["conn"], w["writer"], w["store"], adapters, clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip
    w["call"] = lambda tool, args: built.dispatcher.call(CLIENT, tool, args)
    return w


def _ok(result):
    assert result.error_code is None, result.error_code
    return result.structured


def _staged_upload(world, data, mime):
    begun = _ok(world["call"]("comms_media_stage_begin", {
        "mime": mime, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "request_id": refs.mint("request")}))  # fmt: skip
    for seq, start in enumerate(range(0, len(data), begun["chunk_max"])):
        _ok(world["call"]("comms_media_stage_chunk", {
            "upload": begun["upload"], "seq": seq,
            "data_b64": _b64(data[start : start + begun["chunk_max"]]),
            "request_id": refs.mint("request")}))  # fmt: skip
    return begun["upload"]


def test_a_staged_upload_becomes_a_media_ref_and_downloads_back(world):
    data = b"\x89PNG" + os.urandom(100_000)
    upload = _staged_upload(world, data, "image/png")
    request = refs.mint("request")
    made = _ok(world["call"]("comms_media_upload", {"upload": upload, "request_id": request}))
    assert made["result"] == "SUCCEEDED" and made["media"].startswith("med_")
    again = _ok(world["call"]("comms_media_upload", {"upload": upload, "request_id": request}))
    assert again["replayed"] and again["media"] == made["media"]
    (digest,) = world["conn"].execute(
        "SELECT request_digest FROM mutations WHERE tool = 'comms_media_upload'").fetchone()  # fmt: skip
    expected = request_digest(
        "comms_media_upload",
        {
            "data": {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
            "mime": "image/png",
        },
        {"actor": "whatsapp_cloud", "capability": "media.upload", "destination": "account"},
    )
    assert digest == expected  # the bytes' hash, never the bytes
    got, offset = b"", 0
    while True:
        page = _ok(
            world["call"]("comms_media_download", {"media": made["media"], "offset": offset})
        )
        got += base64.b64decode(page["data_b64"])
        offset += CHUNK_MAX
        if page["complete"]:
            break
    assert got == data and page["sha256"] == hashlib.sha256(data).hexdigest()


def test_a_small_file_inline_and_exactly_one_source(world):
    made = _ok(world["call"]("comms_media_upload", {"data_b64": _b64(b"hello"), "mime": "text/plain",
                             "request_id": refs.mint("request")}))  # fmt: skip
    assert made["media"].startswith("med_")
    both = world["call"]("comms_media_upload", {"data_b64": _b64(b"x"), "mime": "text/plain",
                         "upload": "upl_" + "a" * 26, "request_id": refs.mint("request")})  # fmt: skip
    assert both.error_code == "INVALID_ARGUMENT"
    other = world["call"]("comms_media_upload", {"upload": "upl_" + "a" * 26,
                          "request_id": refs.mint("request")})  # fmt: skip
    assert other.error_code == "NOT_FOUND"


# -- group photos on every API ------------------------------------------------------------------


def test_the_bot_sets_a_photo_as_a_file_part():
    seen = []

    def handle(request):
        seen.append((request.url.path.rsplit("/", 1)[-1], request.headers["content-type"],
                     request.content))  # fmt: skip
        return httpx.Response(200, json={"ok": True, "result": True})

    admin = BotAdmin(BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle)))
    op = SemanticOperation(C.CHAT_SET_PHOTO, {"photo": JPEG, "mime": "image/jpeg"})
    result = admin.invoke(op, ProviderTarget("telegram", "telegram_bot", "d", "-77"), "k")
    assert result.outcome == "SUCCEEDED"
    ((method, kind, body),) = seen
    assert method == "setChatPhoto" and kind.startswith("multipart/form-data")
    assert JPEG[:50] in body and b'name="chat_id"' in body


def test_the_user_account_uploads_the_photo_in_parts_then_sets_it(tmp_path):
    from telethon.tl import types

    big = b"\xff\xd8\xff" + os.urandom(600_000)  # two parts
    ok = types.Updates(updates=[], users=[], chats=[], date=None, seq=0)
    result, sent, calls = _invoke(tmp_path, {"upload.SaveFilePartRequest": True,
                                             "channels.EditPhotoRequest": ok},
                                  C.CHAT_SET_PHOTO, {"photo": big, "mime": "image/jpeg"}, SUPER)  # fmt: skip
    assert calls == ["upload.SaveFilePartRequest", "upload.SaveFilePartRequest",
                     "channels.EditPhotoRequest"]  # fmt: skip
    assert b"".join(r.bytes for r in sent[:2]) == big and result.outcome == "SUCCEEDED"
    assert sent[2].photo.file.parts == 2


def test_whatsapp_sets_the_group_picture_as_multipart():
    seen = []

    def handle(request):
        seen.append((request.method, request.url.path, request.headers["content-type"]))
        return httpx.Response(200, json={"success": True})

    from comms.transports.whatsapp.cloud.http import GraphApi
    from tests.runtime.test_whatsapp_groups_live import Token

    api = GraphApi(Token(), version=1, phone_number_id="106540352242922",
                   transport=httpx.MockTransport(handle))  # fmt: skip
    discovery = GroupDiscovery(api)
    discovery.states = dict.fromkeys(discovery.states, S.AVAILABLE)
    admin = WhatsAppAdmin(api, discovery)
    group = ProviderTarget("whatsapp", "whatsapp_cloud", "d", "group:120363049891234567")
    op = SemanticOperation(C.GROUP_SETTINGS_UPDATE, {"photo": JPEG, "mime": "image/jpeg"})
    assert admin.invoke(op, group, "k").outcome == "SUCCEEDED"
    assert seen[0][0] == "POST" and seen[0][2].startswith("multipart/form-data")
    with pytest.raises(ValueError):
        admin.validate(
            SemanticOperation(C.GROUP_SETTINGS_UPDATE, {"photo": JPEG, "mime": "image/png"}), group
        )


def test_a_group_photo_is_uploaded_with_its_extension(tmp_path):
    """Found live (2026-09-28): Telegram types an uploaded photo by its file name."""
    from telethon.tl import types

    ok = types.Updates(updates=[], users=[], chats=[], date=None, seq=0)
    _result, sent, _calls = _invoke(tmp_path, {"upload.SaveFilePartRequest": True,
                                               "channels.EditPhotoRequest": ok},
                                    C.CHAT_SET_PHOTO, {"photo": JPEG, "mime": "image/jpeg"}, SUPER)  # fmt: skip
    assert sent[-1].photo.file.name == "file.jpg"


@pytest.mark.parametrize("error", ["PhotoCropSizeSmallError", "PhotoInvalidDimensionsError",
                                   "PhotoExtInvalidError", "ImageProcessFailedError"])  # fmt: skip
def test_a_refused_group_photo_is_failed_not_unknown(tmp_path, error):
    """Found live (2026-09-28, R-TG4): a 96 px photo was refused PHOTO_CROP_SIZE_SMALL and
    reported OUTCOME_UNKNOWN; Telegram refused it, and the photo is unchanged."""
    from telethon import errors

    refusal = getattr(errors, error)(request=None)
    result, _sent, calls = _invoke(tmp_path, {"upload.SaveFilePartRequest": True,
                                              "channels.EditPhotoRequest": refusal},
                                   C.CHAT_SET_PHOTO, {"photo": JPEG, "mime": "image/jpeg"}, SUPER)  # fmt: skip
    assert (result.outcome, result.code) == ("FAILED", "INVALID_ARGUMENT")
    assert calls.count("channels.EditPhotoRequest") == 1
