"""Spec A47 (H5): the user account's media upload, and a Telegram ``med_``'s inspect and delete.

``comms_media_upload`` with ``actor: telegram_user`` sends the file through the one part upload,
then ``messages.uploadMedia(peer=inputPeerSelf)`` (Gf16); the result is a reusable ``med_``.
Nothing refreshes an uploaded file's reference (Gf15), so a send that meets an expired one is
``NOT_FOUND`` ("upload again") and is never retried. The Bot API has no standalone upload (B).
Inspect answers from the recorded facts with no call; Telegram has no file delete (B). With both
WhatsApp and the user account configured, an upload that names no actor is ambiguous.
"""

import pytest
from telethon import errors
from telethon.tl import types

from comms.core import refs
from comms.core.objects import media_facts, resolve_object
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderTarget, SemanticOperation
from comms.core.providers.semantics import SUPPORT
from tests.integration.test_actor_matrix_behaviour import CLIENT, _world
from tests.runtime.test_media_staged import _b64
from tests.transports.telegram_user.test_admin_chat import SUPER, _run

ACCOUNT = ProviderTarget("telegram", "telegram_user", "loc", "account")
JPEG = b"\xff\xd8\xff\xe0" + b"j" * 3000
PHOTO = types.Photo(id=11, access_hash=22, file_reference=b"\x01\x02", date=None, dc_id=2,
                    sizes=[types.PhotoSize("x", 800, 600, 3004)])  # fmt: skip


def _invoke(tmp_path, script, cap, args, target):
    return _run(tmp_path, script,
                lambda admin: admin.invoke(SemanticOperation(cap, args), target, "cd" * 32))  # fmt: skip


def test_upload_is_the_user_account_and_whatsapp():
    assert set(SUPPORT[C.MEDIA_UPLOAD]) == {"telegram_user", "whatsapp_cloud"}


def test_the_account_uploads_to_itself(tmp_path):
    result, sent, calls = _invoke(tmp_path, {
        "upload.SaveFilePartRequest": True,
        "messages.UploadMediaRequest": types.MessageMediaPhoto(photo=PHOTO)},
        C.MEDIA_UPLOAD, {"data": JPEG, "mime": "image/jpeg", "kind": "photo"}, ACCOUNT)  # fmt: skip
    assert result.outcome == "SUCCEEDED"
    assert result.provider_ref == "upload:photo:11:22:0102"
    assert calls == ["upload.SaveFilePartRequest", "messages.UploadMediaRequest"]
    request = sent[-1]
    assert isinstance(request.peer, types.InputPeerSelf)
    assert isinstance(request.media, types.InputMediaUploadedPhoto)


def test_an_uploaded_file_is_sent_without_fetching_a_message(tmp_path):
    def sent(request):
        return types.Updates(updates=[types.UpdateMessageID(id=78, random_id=request.random_id)],
                             users=[], chats=[], date=None, seq=0)  # fmt: skip

    result, sent_requests, calls = _invoke(tmp_path, {"messages.SendMediaRequest": sent},
        C.MESSAGE_SEND_MEDIA, {"kind": "photo", "media_id": "upload:photo:11:22:0102"}, SUPER)  # fmt: skip
    assert (result.outcome, result.provider_ref) == ("SUCCEEDED", "78")
    assert calls == ["messages.SendMediaRequest"]
    media = sent_requests[-1].media
    assert isinstance(media, types.InputMediaPhoto)
    assert (media.id.id, media.id.access_hash, media.id.file_reference) == (11, 22, b"\x01\x02")


@pytest.mark.parametrize(("error", "code"), [
    (errors.FileReferenceExpiredError(request=None), "NOT_FOUND"),
    (errors.PhotoInvalidDimensionsError(request=None), "INVALID_ARGUMENT"),
    (errors.ChatSendMediaForbiddenError(request=None), "NOT_AUTHORIZED"),
])  # fmt: skip
def test_a_media_refusal_is_final_not_unknown(tmp_path, error, code):
    result, _sent, calls = _invoke(tmp_path, {"messages.SendMediaRequest": error},
        C.MESSAGE_SEND_MEDIA, {"kind": "photo", "media_id": "upload:photo:11:22:0102"}, SUPER)  # fmt: skip
    assert (result.outcome, result.code) == ("FAILED", code)
    assert calls.count("messages.SendMediaRequest") == 1  # refused: never reissued


def test_an_uploaded_document_is_never_sent_as_a_photo(tmp_path):
    result, _sent, calls = _invoke(tmp_path, {}, C.MESSAGE_SEND_MEDIA,
        {"kind": "photo", "media_id": "upload:document:5:6:ab"}, SUPER)  # fmt: skip
    assert (result.outcome, result.code) == ("FAILED", "INVALID_ARGUMENT") and calls == []


# -- through the dispatcher ----------------------------------------------------------------


def test_upload_then_inspect_through_the_dispatcher(tmp_path):
    w, dispatcher, admin, _specs = _world("telegram_user", tmp_path)
    made = dispatcher.call(CLIENT, "comms_media_upload", {
        "data_b64": _b64(JPEG), "mime": "image/jpeg", "request_id": refs.mint("request")})  # fmt: skip
    assert made.error_code is None and made.structured["result"] == "SUCCEEDED"
    media = made.structured["media"]
    ((cap, args),) = admin.calls
    assert cap is C.MEDIA_UPLOAD and args["kind"] == "photo"  # a JPEG by its bytes
    assert resolve_object(w["conn"], media, "media").actor == "telegram_user"
    assert media_facts(w["conn"], media) == {"kind": "photo", "mime": "image/jpeg",
                                             "size": len(JPEG), "origin": "telegram_upload"}  # fmt: skip
    seen = dispatcher.call(CLIENT, "comms_media_inspect", {"media": media})
    assert seen.error_code is None
    assert {k: v for k, v in seen.structured.items() if k != "next_actions"} == {
        "media": media, "mime": "image/jpeg", "size": len(JPEG), "sha256": None}  # fmt: skip
    assert len(admin.calls) == 1  # inspect made no call
    gone = dispatcher.call(CLIENT, "comms_media_delete", {"media": media,
                           "request_id": refs.mint("request")})  # fmt: skip
    assert gone.error_code == "PROVIDER_UNSUPPORTED" and len(admin.calls) == 1


def test_the_bot_has_no_standalone_upload(tmp_path):
    _w, dispatcher, admin, _specs = _world("telegram_bot", tmp_path)
    got = dispatcher.call(CLIENT, "comms_media_upload", {
        "data_b64": _b64(JPEG), "mime": "image/jpeg", "actor": "telegram_bot",
        "request_id": refs.mint("request")})  # fmt: skip
    assert got.error_code in ("INVALID_ARGUMENT", "PROVIDER_UNSUPPORTED") and admin.calls == []


# -- found live (2026-09-28): Telegram types an uploaded photo by its file name ---------------

PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 3000


@pytest.mark.parametrize(("data", "mime", "name"), [(JPEG, "image/jpeg", "file.jpg"),
                                                     (PNG, "image/png", "file.png")], ids=["jpeg", "png"])  # fmt: skip
def test_an_uploaded_photo_is_named_with_its_extension(tmp_path, data, mime, name):
    """Named plain ``file``, Telegram refused every photo upload with PHOTO_EXT_INVALID."""
    _result, sent, _calls = _invoke(tmp_path, {
        "upload.SaveFilePartRequest": True,
        "messages.UploadMediaRequest": types.MessageMediaPhoto(photo=PHOTO)},
        C.MEDIA_UPLOAD, {"data": data, "mime": mime, "kind": "photo"}, ACCOUNT)  # fmt: skip
    assert sent[-1].media.file.name == name


def test_a_photo_sent_from_staged_bytes_is_named_with_its_extension(tmp_path):
    def sent(request):
        return types.Updates(updates=[types.UpdateMessageID(id=79, random_id=request.random_id)],
                             users=[], chats=[], date=None, seq=0)  # fmt: skip

    result, requests, _calls = _invoke(tmp_path, {"upload.SaveFilePartRequest": True,
                                                  "messages.SendMediaRequest": sent},
        C.MESSAGE_SEND_MEDIA, {"kind": "photo", "data": JPEG, "mime": "image/jpeg"}, SUPER)  # fmt: skip
    assert result.outcome == "SUCCEEDED"
    assert requests[-1].media.file.name == "file.jpg"


def test_a_refused_upload_is_failed_with_its_code_not_unknown(tmp_path):
    result, _sent, calls = _invoke(tmp_path, {
        "upload.SaveFilePartRequest": True,
        "messages.UploadMediaRequest": errors.PhotoExtInvalidError(request=None)},
        C.MEDIA_UPLOAD, {"data": JPEG, "mime": "image/jpeg", "kind": "photo"}, ACCOUNT)  # fmt: skip
    assert (result.outcome, result.code) == ("FAILED", "INVALID_ARGUMENT")
    assert calls.count("messages.UploadMediaRequest") == 1
