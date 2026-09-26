"""Spec A47 (H2): Telegram media as ``med_`` refs minted from context items.

A message carrying a photo or a document gets a ``media_ref``. The user account's identity is
the message's locator; the file reference is fetched again whenever it is used, so it is never
stored. The bot's identity is the ``file_unique_id``: one file can have several ``file_id``s
(Gf4), and no ``file_id`` is stored a second time, since the retained update already holds it
(Gx9). Kind, MIME type and size live in ``media_facts`` (schema v8, Gx8). No file id, file
reference or locator ever leaves.
"""

import json
from datetime import UTC, datetime

import httpx
from telethon.tl import types

from comms.core.objects import media_facts, resolve_object
from comms.core.providers.protocols import ContextPage
from comms.runtime.selftest import _OneSecret
from comms.services.context import ContextEngine
from comms.transports.telegram.bot.context import BotContext
from comms.transports.telegram.bot.http import BotApi
from comms.transports.telegram.bot.updates import BotPoller
from comms.transports.telegram.telegram.telethon_adapter import _message_view
from tests.core.campaign_helpers import NOW
from tests.services.context_fixtures import Clock
from tests.services.group_fixtures import group_world

FILE_ID_A, FILE_ID_B, UNIQUE = (
    "BQACAgIAAxkBAAIBnWbf-first",
    "BQACAgIAAxkBAAIBnWbf-second",
    "AgADrBAAAk",
)


def _photo():
    sizes = [types.PhotoStrippedSize("i", b"x"), types.PhotoSize("m", 320, 320, 1000),
             types.PhotoSizeProgressive("y", 1280, 1280, [100, 5000, 90000])]  # fmt: skip
    return types.MessageMediaPhoto(photo=types.Photo(
        id=1, access_hash=2, file_reference=b"ref", date=None, sizes=sizes, dc_id=4))  # fmt: skip


def _document():
    return types.MessageMediaDocument(document=types.Document(
        id=5, access_hash=6, file_reference=b"ref", date=None, mime_type="application/pdf",
        size=12345, dc_id=2, attributes=[types.DocumentAttributeFilename("minutes.pdf")]))  # fmt: skip


def _message(media, mid=55):
    return types.Message(id=mid, peer_id=types.PeerChannel(77), date=datetime(2026, 9, 1, tzinfo=UTC),
                         message="", media=media)  # fmt: skip


def test_the_user_accounts_view_carries_the_media_facts():
    chat = ("channel", 77)
    assert _message_view(_message(_photo()), chat, {}).media_facts == ("photo", "image/jpeg", 90000)
    assert _message_view(_message(_document()), chat, {}).media_facts == (
        "document", "application/pdf", 12345)  # fmt: skip
    geo = types.MessageMediaGeo(types.GeoPointEmpty())
    assert _message_view(_message(geo), chat, {}).media_facts is None


class _Source:
    def __init__(self, items, provenance="telegram_live"):
        self.items, self.provenance = items, provenance

    def read(self, query):
        stamp = {"source": self.provenance, "observed_at": "2026-09-25T00:00:00.000000Z"}
        return ContextPage(tuple({**stamp, **i} for i in self.items), self.provenance)


def _engine(w, source, actor="telegram_user"):
    return ContextEngine(w["conn"], {actor: source}, clock=lambda: NOW, monotonic=Clock())


def test_the_user_account_mints_a_med_by_the_message_locator(tmp_path):
    w = group_world(tmp_path)
    media = {"kind": "photo", "mime": "image/jpeg", "size": 90000}
    engine = _engine(w, _Source([{"message_id": 55, "media": media}]))
    first = engine.recent(w["grp"], w["user"], limit=5)["items"][0]
    again = engine.recent(w["grp"], w["user"], limit=5)["items"][0]
    assert first["media_ref"].startswith("med_") and first["media_ref"] == again["media_ref"]
    assert "media" not in first  # the facts are recorded, not echoed
    found = resolve_object(w["conn"], first["media_ref"], "media")
    assert (found.transport, found.actor, found.provider_identity) == (
        "telegram", "telegram_user", "-77:55")  # fmt: skip
    assert media_facts(w["conn"], first["media_ref"]) == {
        "kind": "photo", "mime": "image/jpeg", "size": 90000, "origin": "telegram_message"}  # fmt: skip


def test_an_item_without_media_has_no_media_ref(tmp_path):
    w = group_world(tmp_path)
    item = _engine(w, _Source([{"message_id": 56}])).recent(w["grp"], w["user"], limit=5)["items"][
        0
    ]
    assert "media_ref" not in item


def _bot(w, updates):
    def handle(request):
        method = request.url.path.rsplit("/", 1)[-1]
        offset = int(json.loads(request.content or b"{}").get("offset") or 0)
        result = (
            [u for u in updates if u["update_id"] >= offset] if method == "getUpdates" else True
        )
        return httpx.Response(200, json={"ok": True, "result": result})

    api = BotApi(_OneSecret(), version=1, transport=httpx.MockTransport(handle))
    BotPoller(api, w["conn"], clock=lambda: NOW).poll_once()
    return BotContext(api, w["conn"], clock=lambda: NOW)


def _update(n, **body):
    return {"update_id": n, "message": {"message_id": 100 + n, "date": 1758800000 + n,
            "chat": {"id": -77, "type": "group", "title": "G"},
            "from": {"id": 42, "is_bot": False, "first_name": "S"}, **body}}  # fmt: skip


def test_the_bot_keys_a_file_by_its_unique_id_and_stores_no_file_id(tmp_path):
    w = group_world(tmp_path)
    document = {"file_id": FILE_ID_A, "file_unique_id": UNIQUE, "mime_type": "application/pdf",
                "file_size": 2048, "file_name": "minutes.pdf"}  # fmt: skip
    photo = [{"file_id": "p-small", "file_unique_id": "u-small", "width": 90, "height": 90,
              "file_size": 900},
             {"file_id": "p-big", "file_unique_id": "u-big", "width": 1280, "height": 960,
              "file_size": 70000}]  # fmt: skip
    source = _bot(w, [
        _update(1, document=document, caption="minutes"),
        _update(2, document={**document, "file_id": FILE_ID_B}),  # same file, another file_id
        _update(3, photo=photo),
        _update(4, text="plain"),
    ])  # fmt: skip
    items = _engine(w, source, "telegram_bot").recent(w["grp"], w["bot"], limit=10)["items"]
    by_text = {i.get("untrusted_text"): i for i in items}
    refs = [i.get("media_ref") for i in items]
    documents = [r for r in refs if r and media_facts(w["conn"], r)["kind"] == "document"]
    assert len(set(documents)) == 1 and len(documents) == 2  # one med_ for one file
    (photo_ref,) = [r for r in refs if r and media_facts(w["conn"], r)["kind"] == "photo"]
    assert media_facts(w["conn"], photo_ref) == {
        "kind": "photo", "mime": "image/jpeg", "size": 70000, "origin": "telegram_bot_update"}  # fmt: skip
    assert resolve_object(w["conn"], photo_ref, "media").provider_identity == "u-big"
    assert "media_ref" not in by_text["plain"]
    text = json.dumps(items)
    for secret in (FILE_ID_A, FILE_ID_B, UNIQUE, "p-big", "u-big", "minutes.pdf"):
        assert secret not in text, secret
    stored = " ".join(str(v) for row in w["conn"].execute("SELECT * FROM media_facts")
                      for v in row)  # fmt: skip
    assert FILE_ID_A not in stored and FILE_ID_B not in stored


def test_schema_v8_holds_media_facts(tmp_path):
    w = group_world(tmp_path)
    version = w["conn"].execute("SELECT max(version) FROM schema_version").fetchone()[0]
    assert version == 8
    cols = [r[1] for r in w["conn"].execute("PRAGMA table_info(media_facts)")]
    assert cols == ["object_id", "media_kind", "mime", "size", "origin", "recorded_at"]


def test_the_user_accounts_source_hands_the_engine_facts_not_a_file_reference():
    from comms.transports.telegram.user.context import _message

    view = _message_view(_message_real := types.Message(
        id=55, peer_id=types.PeerUser(42), date=datetime(2026, 9, 1, tzinfo=UTC), message="", media=_photo()),
        ("user", 42), {})  # fmt: skip
    item = _message(view, "2026-09-25T00:00:00.000000Z")
    assert item["media"] == {"kind": "photo", "mime": "image/jpeg", "size": 90000}
    assert "media_key" not in item and b"ref" not in json.dumps(item).encode()
    assert _message_real.media.photo.file_reference == b"ref"  # it stayed in the adapter
