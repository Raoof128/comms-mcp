"""Spec A47 (H3): downloading a Telegram ``med_``.

Bot: ``getFile``, then one streamed GET on ``api.telegram.org/file/bot…/<file_path>``, capped
at 16 MiB (the Bot API allows 20 MB), with the ``file_path`` checked before it joins a URL that
carries the token (Gf13, Gx12, Gx13). The ``file_id`` is read from the newest retained update
holding the ``file_unique_id`` (Gx9).

User account: the message is fetched again (a fresh file reference), then ``upload.getFile`` in
512 KiB slices at 512 KiB offsets with ``precise`` and ``cdn_supported`` unset (Gf2, Gf9), on
the file's own DC through a borrowed sender when it is not the home DC (Gf1, Gx1). An expired
reference is fetched again once; a migrate is followed once; the Premium throttle is a rate
limit (Gx3, Gx4).
"""

import base64
import hashlib
import json
import os
from datetime import UTC, datetime

import httpx
import pytest
from telethon import errors
from telethon.tl import functions, types

from comms.core.errors import CommsError
from comms.core.keys import rotate as rot
from comms.core.objects import object_ref
from comms.core.providers.capability import CapabilityState as S
from comms.mcp.dispatch import AuthenticatedClient
from comms.runtime.adapters import Adapters
from comms.runtime.comms_runtime import build_comms_runtime
from comms.runtime.selftest import _OneSecret
from comms.services.media import MediaService
from comms.services.uploads import StagedMedia
from comms.transports.net import DownloadRefused
from comms.transports.telegram.bot.context import BotContext
from comms.transports.telegram.bot.http import BotApi
from comms.transports.telegram.bot.media import BotMedia
from comms.transports.telegram.bot.updates import BotPoller
from comms.transports.telegram.telegram.deadline import WorkBudget
from comms.transports.telegram.telegram.telethon_adapter import OPERATIONS, _operation
from comms.transports.telegram.user.media import UserMedia
from tests.core.campaign_helpers import NOW
from tests.services.context_fixtures import Clock
from tests.services.group_fixtures import Provider, group_world
from tests.transports.telegram_user.test_admin_chat import _run
from tests.unit.test_gateway_client import _client

TOKEN_MARK = "selftest"  # _OneSecret's bot token is "1:selftest"
SLICE = 512 * 1024


def _document(**over):
    fields = {"file_id": "BQAC-one", "file_unique_id": "AgADdoc", "mime_type": "application/pdf",
              "file_size": 3 * 1024 * 1024} | over  # fmt: skip
    return {"update_id": 1, "message": {"message_id": 101, "date": 1758800001,
            "chat": {"id": -77, "type": "group", "title": "G"},
            "from": {"id": 42, "is_bot": False, "first_name": "S"}, "document": fields}}  # fmt: skip


def _bot(tmp_path, update, *, file_path="documents/file_7.pdf", size=None, body=None, world=None):
    w = group_world(tmp_path)
    if world is not None:
        world.update(w)
    blob = body if body is not None else b"%PDF" + b"x" * (3 * 1024 * 1024 - 4)
    seen = []

    def handle(request):
        seen.append(str(request.url))
        path = request.url.path
        if path.endswith("/getUpdates"):
            offset = int(json.loads(request.content or b"{}").get("offset") or 0)
            result = [update] if update["update_id"] >= offset else []
            return httpx.Response(200, json={"ok": True, "result": result})
        if path.endswith("/getFile"):
            got = json.loads(request.content)
            assert got == {"file_id": "BQAC-one"}
            result = {"file_id": "BQAC-one", "file_unique_id": "AgADdoc", "file_path": file_path}
            if size is not None:
                result["file_size"] = size
            return httpx.Response(200, json={"ok": True, "result": result})
        if "/file/bot" in path:
            return httpx.Response(200, content=blob)
        return httpx.Response(404)

    api = BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle))
    BotPoller(api, w["conn"], clock=lambda: NOW).poll_once()
    return BotMedia(api, w["conn"]), seen, blob


def test_the_bot_downloads_by_file_unique_id(tmp_path):
    media, seen, blob = _bot(tmp_path, _document(), size=3 * 1024 * 1024)
    got = media.retrieve("AgADdoc")
    assert got.data == blob and got.sha256 == hashlib.sha256(blob).hexdigest()
    assert seen[-1] == "https://api.telegram.org/file/bot1:selftest/documents/file_7.pdf"


def test_a_declared_size_over_the_cap_is_refused_before_the_download(tmp_path):
    media, seen, _blob = _bot(tmp_path, _document(), size=17 * 1024 * 1024)
    with pytest.raises(DownloadRefused) as refused:
        media.retrieve("AgADdoc")
    assert refused.value.code == "PROVIDER_UNSUPPORTED"
    assert not any("/file/bot" in url for url in seen)


def test_an_undeclared_size_is_capped_while_streaming(tmp_path):
    media, _seen, _blob = _bot(tmp_path, _document(), body=b"x" * (16 * 1024 * 1024 + 1))
    with pytest.raises(DownloadRefused) as refused:
        media.retrieve("AgADdoc")
    assert refused.value.code == "PROVIDER_UNSUPPORTED"


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "https://evil.example/x", "a b",
                                  "documents/../../x", "a//b", "é.pdf", ""])  # fmt: skip
def test_a_file_path_is_checked_before_it_joins_the_token_url(tmp_path, path):
    media, seen, _blob = _bot(tmp_path, _document(), file_path=path)
    with pytest.raises(DownloadRefused) as refused:
        media.retrieve("AgADdoc")
    assert refused.value.code == "PROVIDER_UNAVAILABLE"
    assert not any("/file/bot" in url for url in seen)
    assert TOKEN_MARK not in str(refused.value) and TOKEN_MARK not in repr(refused.value)


def test_a_purged_update_leaves_the_bots_med_not_found(tmp_path):
    media, _seen, _blob = _bot(tmp_path, _document())
    media._conn.execute("DELETE FROM bot_updates")
    with pytest.raises(DownloadRefused) as refused:
        media.retrieve("AgADdoc")
    assert refused.value.code == "NOT_FOUND"


# -- the user account -------------------------------------------------------------------


def _msg(dc=2, size=SLICE + 100):
    doc = types.Document(id=5, access_hash=6, file_reference=b"fresh", date=None,
                         mime_type="application/pdf", size=size, dc_id=dc, attributes=[])  # fmt: skip
    return types.messages.Messages(messages=[types.Message(
        id=55, peer_id=types.PeerUser(42), date=datetime(2026, 9, 1, tzinfo=UTC), message="",
        media=types.MessageMediaDocument(document=doc))], chats=[], users=[], topics=[])  # fmt: skip


def _slices(data):
    def answer(request):
        assert request.limit == SLICE and request.offset % SLICE == 0
        assert not request.precise and not request.cdn_supported
        return types.upload.File(types.storage.FilePdf(), 0,
                                 data[request.offset : request.offset + request.limit])  # fmt: skip

    return answer


def _seq(*outcomes):
    """Outcomes in order; the last one repeats (an exception is raised, a callable answered)."""
    queue = list(outcomes)

    def answer(request):
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome(request) if callable(outcome) else outcome

    return answer


def _download(tmp_path, script, identity="42:55"):
    def act(admin):
        return UserMedia(admin._session, run=admin._run).retrieve(identity)

    return _run(tmp_path, script, act)


DATA = bytes(range(256)) * ((SLICE + 100) // 256 + 1)
DATA = DATA[: SLICE + 100]


def test_the_account_downloads_in_aligned_slices_on_the_home_dc(tmp_path):
    got, _sent, calls = _download(tmp_path, {"messages.GetMessagesRequest": _msg(),
                                             "upload.GetFileRequest": _slices(DATA)})  # fmt: skip
    assert got.data == DATA
    assert calls == ["messages.GetMessagesRequest", "upload.GetFileRequest",
                     "upload.GetFileRequest"]  # fmt: skip


def test_a_file_on_another_dc_goes_through_a_borrowed_sender(tmp_path):
    got, _sent, calls = _download(tmp_path, {"messages.GetMessagesRequest": _msg(dc=4),
                                             "upload.GetFileRequest": _slices(DATA)})  # fmt: skip
    assert got.data == DATA
    assert calls == ["messages.GetMessagesRequest", "borrow:4", "dc4:upload.GetFileRequest",
                     "return:4", "borrow:4", "dc4:upload.GetFileRequest", "return:4"]  # fmt: skip


def test_an_unexpected_migrate_is_followed_once(tmp_path):
    migrate = errors.FileMigrateError(request=None, capture=3)
    got, _sent, calls = _download(tmp_path, {"messages.GetMessagesRequest": _msg(),
        "upload.GetFileRequest": _seq(migrate, _slices(DATA))})  # fmt: skip
    assert got.data == DATA and "borrow:3" in calls


def test_an_expired_reference_is_fetched_again_once(tmp_path):
    expired = errors.FileReferenceExpiredError(request=None)
    got, _sent, calls = _download(tmp_path, {"messages.GetMessagesRequest": _msg(),
        "upload.GetFileRequest": _seq(expired, _slices(DATA))})  # fmt: skip
    assert got.data == DATA and calls.count("messages.GetMessagesRequest") == 2


def test_a_second_expiry_is_refused_not_looped(tmp_path):
    expired = errors.FileReferenceExpiredError(request=None)
    with pytest.raises(DownloadRefused) as refused:
        _download(tmp_path, {"messages.GetMessagesRequest": _msg(),
                             "upload.GetFileRequest": _seq(expired, expired, _slices(DATA))})  # fmt: skip
    assert refused.value.code == "PROVIDER_UNAVAILABLE"


def test_the_premium_throttle_is_a_rate_limit(tmp_path):
    throttle = errors.FloodPremiumWaitError(request=None, capture=9)
    with pytest.raises(DownloadRefused) as refused:
        _download(tmp_path, {"messages.GetMessagesRequest": _msg(),
                             "upload.GetFileRequest": _seq(throttle)})  # fmt: skip
    assert (refused.value.code, refused.value.retry_after) == ("RATE_LIMITED", 9)


def test_a_declared_size_over_the_cap_is_refused_before_any_slice(tmp_path):
    with pytest.raises(DownloadRefused) as refused:
        _download(tmp_path, {"messages.GetMessagesRequest": _msg(size=17 * 1024 * 1024)})
    assert refused.value.code == "PROVIDER_UNSUPPORTED"


def test_a_message_without_the_file_is_not_found(tmp_path):
    empty = types.messages.Messages(messages=[], chats=[], users=[], topics=[])
    with pytest.raises(DownloadRefused) as refused:
        _download(tmp_path, {"messages.GetMessagesRequest": empty})
    assert refused.value.code == "NOT_FOUND"


# -- the allowlist on a borrowed sender (the real _GatewayClient) -----------------------


def test_media_download_allows_exactly_the_download_requests():
    assert OPERATIONS["media.download"] == frozenset({
        "messages.GetMessagesRequest", "channels.GetMessagesRequest", "upload.GetFileRequest",
        "auth.ExportAuthorizationRequest", "help.GetConfigRequest"})  # fmt: skip
    for name, names in OPERATIONS.items():
        if name != "media.download":
            assert "upload.GetFileRequest" not in names and (
                "auth.ExportAuthorizationRequest" not in names), name  # fmt: skip


async def test_a_borrowed_sender_is_held_to_the_same_allowlist(tmp_path):
    client = _client(tmp_path, types.upload.File(types.storage.FilePdf(), 0, b"x"))
    other = type(client._sender)(types.upload.File(types.storage.FilePdf(), 0, b"y"))
    location = types.InputDocumentFileLocation(5, 6, b"r", "")
    with _operation("media.download", WorkBudget(max_rpcs=2)):
        await client._call(other, functions.upload.GetFileRequest(location, 0, SLICE))
        await client(functions.auth.ExportAuthorizationRequest(4))
    assert other.sent == ["upload.GetFileRequest"]
    with _operation("mcp.retrieval", WorkBudget()), pytest.raises(PermissionError):
        await client._call(other, functions.upload.GetFileRequest(location, 0, SLICE))
    with _operation("mcp.retrieval", WorkBudget()), pytest.raises(PermissionError):
        await client(functions.auth.ExportAuthorizationRequest(4))


def test_through_the_dispatcher_a_bot_file_pages_back_whole(tmp_path):
    """The one composition root: a retained document's ``media_ref`` from a context read, then
    ``comms_media_download`` in slices with the file's SHA-256, and no identity in any output."""
    w = {}
    media, _seen, blob = _bot(tmp_path, _document(), size=3 * 1024 * 1024, world=w)
    for purpose in ("campaign-commit-key", "cursor-key"):
        rot.rotate(w["writer"], w["store"], purpose, material=os.urandom(32),
                   prove=lambda m: None, now=NOW)  # fmt: skip
    adapters = Adapters(
        capability={"telegram_bot": Provider(S.AVAILABLE)},
        context={"telegram_bot": BotContext(media._api, w["conn"], clock=lambda: NOW)},
        downloads={"telegram_bot": media},
    )
    built = build_comms_runtime(w["conn"], w["writer"], w["store"], adapters, clock=lambda: NOW,
                                monotonic=Clock(), host="127.0.0.1", local_port=8765)  # fmt: skip
    client = AuthenticatedClient(client_ref="cli_" + "a" * 26, auth_kind="cml1")
    recent = built.dispatcher.call(client, "comms_context_recent", {"group": w["grp"], "limit": 5})
    assert recent.error_code is None, recent.error_code
    ref = next(i["media_ref"] for i in recent.structured["items"] if "media_ref" in i)
    got, offset = b"", 0
    while True:
        page = built.dispatcher.call(client, "comms_media_download",
                                     {"media": ref, "offset": offset, "length": 32768})  # fmt: skip
        assert page.error_code is None, page.error_code
        assert page.structured["mime"] == "application/pdf"
        piece = base64.b64decode(page.structured["data_b64"])
        got, offset = got + piece, offset + len(piece)
        if page.structured["complete"]:
            break
    assert got == blob and page.structured["sha256"] == hashlib.sha256(blob).hexdigest()
    text = json.dumps([recent.structured, page.structured])
    for secret in ("BQAC-one", "AgADdoc", "file_7", "selftest"):
        assert secret not in text, secret


def test_a_whatsapp_ref_without_whatsapp_is_not_configured(tmp_path):
    w = {}
    _media, _seen, _blob = _bot(tmp_path, _document(), world=w)
    wa = object_ref(w["conn"], "media", "whatsapp", "whatsapp_cloud", None, "7788990011", now=NOW)
    service = MediaService(w["conn"], None, None, None, downloads={"telegram_bot": _media})
    with pytest.raises(CommsError) as refused:
        service.download(StagedMedia(), "cli_x", wa, 0, 1024)
    assert refused.value.code == "NOT_CONFIGURED"
