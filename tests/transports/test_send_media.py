"""Spec A47 (H4): ``comms_message_send_media`` on all three actors.

A photo or a document, from a staged ``upl_`` (or inline ``data_b64``) or from a ``med_`` the
same actor holds, with a caption of at most 1024 UTF-16 code units. Bot: ``sendPhoto`` (at most
10 MB) or ``sendDocument``, multipart, or by the ``file_id`` read from the retained update. User
account: the one part upload (``saveFilePart`` up to 10 MB, ``saveBigFilePart`` and
``inputFileBig`` above, Gf6), then ``messages.sendMedia`` keyed by ``random_id``. WhatsApp: the
file uploaded, then a group message by media id; an image is a real JPEG or PNG of at most
5 MB (Gx11). Limits, a kind mismatch (Gf5) and another actor's ``med_`` are refused before any
call; the bytes never reach a request digest.
"""

import hashlib
import json

import httpx
import pytest
from telethon.tl import types

from comms.core import refs
from comms.core.objects import object_ref, record_media
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import ProviderTarget, SemanticOperation
from comms.core.providers.semantics import SEMANTICS, SUPPORT
from comms.runtime.selftest import _OneSecret
from comms.transports.telegram.bot.admin import BotAdmin
from comms.transports.telegram.bot.http import BotApi
from comms.transports.whatsapp.cloud.groups import GroupDiscovery, WhatsAppAdmin
from comms.transports.whatsapp.cloud.http import GraphApi
from tests.core.campaign_helpers import NOW
from tests.integration.test_actor_matrix_behaviour import CLIENT, _world
from tests.runtime.test_media_staged import _b64, _ok
from tests.runtime.test_whatsapp_groups_live import Token
from tests.transports.telegram_user.test_admin_chat import SUPER, _run

JPEG = b"\xff\xd8\xff\xe0" + b"j" * 2000
PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 2000
PDF = b"%PDF-1.7" + b"d" * (3 * 1024 * 1024)
BOT = ProviderTarget("telegram", "telegram_bot", "d", "-77")
WA = ProviderTarget("whatsapp", "whatsapp_cloud", "dst_w", "group:120363049891234567")


def test_send_media_is_a_send_on_all_three_actors():
    assert set(SUPPORT[C.MESSAGE_SEND_MEDIA]) == {"telegram_bot", "telegram_user", "whatsapp_cloud"}
    user = SEMANTICS[(C.MESSAGE_SEND_MEDIA, "telegram_user")]
    assert (user.idempotency_strategy, user.ambiguity_policy) == ("provider_random_id",
                                                                   "retry_same_key")  # fmt: skip
    for actor in ("telegram_bot", "whatsapp_cloud"):
        assert SEMANTICS[(C.MESSAGE_SEND_MEDIA, actor)].ambiguity_policy == "resolve_only"


# -- the bot ------------------------------------------------------------------------------


def _bot(files=None):
    sent = []

    def handle(request):
        method = request.url.path.rsplit("/", 1)[-1]
        sent.append((method, request.headers.get("content-type", ""), request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 901}})

    api = BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle))
    return BotAdmin(api, files=files), sent


def test_the_bot_sends_a_staged_photo_as_multipart():
    admin, sent = _bot()
    op = SemanticOperation(C.MESSAGE_SEND_MEDIA, {"kind": "photo", "data": JPEG,
                                                  "mime": "image/jpeg", "caption": "Nowruz"})  # fmt: skip
    result = admin.invoke(op, BOT, "k")
    assert (result.outcome, result.provider_ref) == ("SUCCEEDED", "901")
    ((method, ctype, body),) = sent
    assert method == "sendPhoto" and ctype.startswith("multipart/form-data")
    assert b'name="photo"' in body and b"Nowruz" in body and JPEG[:4] in body


def test_the_bot_resends_a_held_document_by_its_file_id():
    admin, sent = _bot(files=lambda unique: {"AgADdoc": "BQAC-one"}[unique])
    op = SemanticOperation(C.MESSAGE_SEND_MEDIA, {"kind": "document", "media_id": "AgADdoc"})
    assert admin.invoke(op, BOT, "k").outcome == "SUCCEEDED"
    ((method, _ctype, body),) = sent
    assert method == "sendDocument" and json.loads(body)["document"] == "BQAC-one"


def test_the_bot_refuses_an_oversized_photo_before_a_call():
    admin, sent = _bot()
    big = b"\xff\xd8\xff" + b"x" * (10 * 1024 * 1024)
    with pytest.raises(ValueError):
        admin.validate(SemanticOperation(C.MESSAGE_SEND_MEDIA, {
            "kind": "photo", "data": big, "mime": "image/jpeg"}), BOT)  # fmt: skip
    assert sent == []


# -- the user account ---------------------------------------------------------------------


def _invoke(tmp_path, script, cap, args, target):
    """One keyed operation (a send's random_id comes from its hex operation key, A20)."""
    return _run(tmp_path, script,
                lambda admin: admin.invoke(SemanticOperation(cap, args), target, "ab" * 32))  # fmt: skip


def _sent_media(request):
    return types.Updates(updates=[types.UpdateMessageID(id=77, random_id=request.random_id)],
                         users=[], chats=[], date=None, seq=0)  # fmt: skip


def test_the_account_uploads_in_parts_then_sends_a_document(tmp_path):
    result, sent, calls = _invoke(tmp_path, {
        "upload.SaveFilePartRequest": True, "messages.SendMediaRequest": _sent_media},
        C.MESSAGE_SEND_MEDIA, {"kind": "document", "data": PDF, "mime": "application/pdf",
                               "caption": "minutes"}, SUPER)  # fmt: skip
    assert (result.outcome, result.provider_ref) == ("SUCCEEDED", "77")
    parts = [r for r in sent if isinstance(r, type(sent[0])) and hasattr(r, "file_part")]
    assert len(parts) == 7 and all(len(p.bytes) <= 512 * 1024 for p in parts)
    request = sent[-1]
    media = request.media
    assert isinstance(media, types.InputMediaUploadedDocument) and media.force_file
    assert media.mime_type == "application/pdf" and request.message == "minutes"
    (attribute,) = media.attributes
    assert attribute.file_name == "file.pdf"  # neutral, never the caller's (Gf7)
    assert isinstance(media.file, types.InputFile) and media.file.parts == 7
    assert calls[-1] == "messages.SendMediaRequest"


def test_above_ten_megabytes_the_parts_are_big(tmp_path):
    big = b"%PDF" + b"b" * (12 * 1024 * 1024)
    result, sent, calls = _invoke(tmp_path, {
        "upload.SaveBigFilePartRequest": True, "messages.SendMediaRequest": _sent_media},
        C.MESSAGE_SEND_MEDIA, {"kind": "document", "data": big, "mime": "application/pdf"},
        SUPER)  # fmt: skip
    assert result.outcome == "SUCCEEDED"
    assert "upload.SaveFilePartRequest" not in calls
    assert isinstance(sent[-1].media.file, types.InputFileBig)
    assert {p.file_total_parts for p in sent[:-1]} == {25}


def test_the_account_resends_its_own_photo_by_the_message(tmp_path):
    photo = types.Photo(id=1, access_hash=2, file_reference=b"fresh", date=None, dc_id=2,
                        sizes=[types.PhotoSize("x", 800, 800, 50000)])  # fmt: skip
    held = types.messages.ChannelMessages(pts=1, count=1, messages=[types.Message(
        id=55, peer_id=types.PeerChannel(77), date=None, message="",
        media=types.MessageMediaPhoto(photo=photo))], chats=[], users=[], topics=[])  # fmt: skip
    result, sent, calls = _invoke(tmp_path, {
        "channels.GetMessagesRequest": held, "messages.SendMediaRequest": _sent_media},
        C.MESSAGE_SEND_MEDIA, {"kind": "photo", "media_id": "-1000000000077:55"}, SUPER)  # fmt: skip
    assert result.outcome == "SUCCEEDED"
    media = sent[-1].media
    assert isinstance(media, types.InputMediaPhoto) and media.id.file_reference == b"fresh"
    assert calls == ["channels.GetMessagesRequest", "messages.SendMediaRequest"]


def test_a_held_document_is_never_sent_as_a_photo(tmp_path):
    doc = types.Document(id=5, access_hash=6, file_reference=b"r", date=None,
                         mime_type="application/pdf", size=9, dc_id=2, attributes=[])  # fmt: skip
    held = types.messages.ChannelMessages(pts=1, count=1, messages=[types.Message(
        id=55, peer_id=types.PeerChannel(77), date=None, message="",
        media=types.MessageMediaDocument(document=doc))], chats=[], users=[], topics=[])  # fmt: skip
    result, _sent, calls = _invoke(tmp_path, {"channels.GetMessagesRequest": held},
        C.MESSAGE_SEND_MEDIA, {"kind": "photo", "media_id": "-1000000000077:55"}, SUPER)  # fmt: skip
    assert (result.outcome, result.code) == ("FAILED", "INVALID_ARGUMENT")
    assert "messages.SendMediaRequest" not in calls


# -- WhatsApp -----------------------------------------------------------------------------


def _wa():
    sent = []

    def handle(request):
        sent.append((request.url.path, request.headers.get("content-type", ""), request.content))
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "4455667788"})
        return httpx.Response(200, json={"messages": [{"id": "wamid.HBgM"}]})

    api = GraphApi(Token(), version=1, phone_number_id="106540352242922",
                   transport=httpx.MockTransport(handle))  # fmt: skip
    discovery = GroupDiscovery(api)
    discovery.states = {c: S.AVAILABLE for c in (C.MESSAGE_SEND_MEDIA, C.GROUP_MESSAGE_SEND)}
    return WhatsAppAdmin(api, discovery), sent


@pytest.mark.parametrize("data", [JPEG, PNG])
def test_whatsapp_uploads_then_sends_an_image_to_the_group(data):
    admin, sent = _wa()
    mime = "image/jpeg" if data is JPEG else "image/png"
    op = SemanticOperation(C.MESSAGE_SEND_MEDIA, {"kind": "photo", "data": data, "mime": mime,
                                                  "caption": "hi"})  # fmt: skip
    result = admin.invoke(op, WA, "k")
    assert result.outcome == "SUCCEEDED"
    (upload, _c, _b), (send, _c2, body) = sent
    assert upload.endswith("/media") and send.endswith("/messages")
    assert json.loads(body) == {"messaging_product": "whatsapp", "recipient_type": "group",
        "to": "120363049891234567", "type": "image",
        "image": {"id": "4455667788", "caption": "hi"}}  # fmt: skip


@pytest.mark.parametrize(("data", "mime"), [(b"GIF89a" + b"x" * 10, "image/jpeg"),
                                            (b"\xff\xd8\xff" + b"x" * (5 * 1024 * 1024), "image/jpeg")])  # fmt: skip
def test_whatsapp_refuses_a_bad_image_before_a_call(data, mime):
    admin, sent = _wa()
    with pytest.raises(ValueError):
        admin.validate(SemanticOperation(C.MESSAGE_SEND_MEDIA, {
            "kind": "photo", "data": data, "mime": mime}), WA)  # fmt: skip
    assert sent == []


# -- through the dispatcher ----------------------------------------------------------------


def _stage(dispatcher, data, mime):
    begun = _ok(dispatcher.call(CLIENT, "comms_media_stage_begin", {
        "mime": mime, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "request_id": refs.mint("request")}))  # fmt: skip
    for seq, start in enumerate(range(0, len(data), begun["chunk_max"])):
        _ok(dispatcher.call(CLIENT, "comms_media_stage_chunk", {
            "upload": begun["upload"], "seq": seq,
            "data_b64": _b64(data[start : start + begun["chunk_max"]]),
            "request_id": refs.mint("request")}))  # fmt: skip
    return begun["upload"]


def test_a_staged_photo_is_sent_once_and_replays(tmp_path):
    w, dispatcher, admin, _specs = _world("telegram_bot", tmp_path)
    args = {"group": w["grp"], "upload": _stage(dispatcher, JPEG, "image/jpeg"),
            "kind": "photo", "caption": "Salaam", "request_id": refs.mint("request")}  # fmt: skip
    got = dispatcher.call(CLIENT, "comms_message_send_media", args)
    assert got.error_code is None and got.structured["result"] == "SUCCEEDED"
    assert got.structured["message"].startswith("cmg_")
    again = dispatcher.call(CLIENT, "comms_message_send_media", args)
    assert again.structured["replayed"] is True and len(admin.calls) == 1
    ((cap, sent),) = admin.calls
    assert cap is C.MESSAGE_SEND_MEDIA and sent["data"] == JPEG and sent["caption"] == "Salaam"
    (digest,) = (
        w["conn"]
        .execute("SELECT request_digest FROM mutations WHERE tool = 'comms_message_send_media'")
        .fetchone()
    )
    assert JPEG[:8].hex() not in digest


@pytest.mark.parametrize("bad", [
    {"caption": "x" * 1025},
    {"caption": "😀" * 513},  # 1026 UTF-16 code units
    {"kind": "video"},
    {"media": "med_" + "a" * 26, "upload": "upl_" + "a" * 26},
    {"upload": None},
])  # fmt: skip
def test_refused_before_any_call(tmp_path, bad):
    w, dispatcher, admin, _specs = _world("telegram_bot", tmp_path)
    args = {"group": w["grp"], "kind": "photo", "data_b64": _b64(JPEG), "mime": "image/jpeg",
            "request_id": refs.mint("request"), **bad}  # fmt: skip
    if "upload" in bad:
        args.pop("data_b64"), args.pop("mime")
        if bad["upload"] is None:
            args.pop("upload")
    got = dispatcher.call(CLIENT, "comms_message_send_media", args)
    assert got.error_code == "INVALID_ARGUMENT" and admin.calls == []


def test_another_actors_or_another_kinds_media_is_refused(tmp_path):
    w, dispatcher, admin, _specs = _world("telegram_bot", tmp_path)
    conn = w["conn"]
    theirs = object_ref(conn, "media", "telegram", "telegram_user", None, "-77:9", now=NOW)
    record_media(conn, theirs, "photo", "image/jpeg", 9, "telegram_message", now=NOW)
    mine = object_ref(conn, "media", "telegram", "telegram_bot", None, "AgADdoc", now=NOW)
    record_media(conn, mine, "document", "application/pdf", 9, "telegram_bot_update", now=NOW)
    for media, kind, code in ((theirs, "photo", "NOT_FOUND"), (mine, "photo", "INVALID_ARGUMENT")):
        got = dispatcher.call(CLIENT, "comms_message_send_media", {
            "group": w["grp"], "media": media, "kind": kind,
            "request_id": refs.mint("request")})  # fmt: skip
        assert got.error_code == code, (media, got.error_code)
    assert admin.calls == []


def test_a_whatsapp_media_id_past_thirty_days_is_refused_before_a_call(tmp_path):
    from datetime import timedelta

    w, dispatcher, admin, _specs = _world("whatsapp_cloud", tmp_path)
    old = object_ref(w["conn"], "media", "whatsapp", "whatsapp_cloud", None, "5566778899",
                     now=NOW - timedelta(days=31))  # fmt: skip
    got = dispatcher.call(CLIENT, "comms_message_send_media", {
        "group": w["grp"], "media": old, "kind": "photo", "request_id": refs.mint("request")})  # fmt: skip
    assert got.error_code == "NOT_FOUND" and admin.calls == []
    fresh = dispatcher.call(CLIENT, "comms_message_send_media", {
        "group": w["grp"], "media": w["media"], "kind": "document",
        "request_id": refs.mint("request")})  # fmt: skip
    assert fresh.error_code is None and admin.calls[0][1]["media_id"] == "7788990011"
