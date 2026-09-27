"""The bot's media download (spec A47, H3).

A bot ``med_`` is keyed by ``file_unique_id`` (one file can have several ``file_id``s, Gf4).
The ``file_id`` is never stored a second time: it is read from the newest retained update that
holds the file (Gx9), so once retention purges that update the ref answers ``NOT_FOUND``.
Then ``getFile`` gives a ``file_path``, and one streamed ``GET`` on the pinned origin fetches at
most 16 MiB (the Bot API itself allows 20 MB). Neither the path nor the token ever reaches an
error, a log or an output.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from comms.transports.net import MAX_DOWNLOAD_BYTES, DownloadRefused, MediaBlob, blob
from comms.transports.telegram.bot.http import BotApi, BotTransportError

__all__ = ["BotMedia"]

DOWNLOAD_DEADLINE_S = 30.0
_SCANNED = 20  # the newest retained updates that name the file; one is enough


class BotMedia:
    def __init__(self, api: BotApi, conn: Any) -> None:
        self._api, self._conn = api, conn

    def __repr__(self) -> str:
        return "BotMedia(<redacted>)"

    def retrieve(self, file_unique_id: str) -> MediaBlob:
        file_id = self._file_id(file_unique_id)
        try:
            answer = self._api.call("getFile", {"file_id": file_id})
        except BotTransportError:
            raise DownloadRefused("PROVIDER_UNAVAILABLE") from None
        envelope = answer.envelope or {}
        result = envelope.get("result") if envelope.get("ok") is True else None
        if answer.http_status == 429:
            raise DownloadRefused("RATE_LIMITED", retry_after=_retry_after(envelope))
        if not isinstance(result, dict) or not isinstance(result.get("file_path"), str):
            raise DownloadRefused(
                "NOT_FOUND" if answer.http_status == 400 else "PROVIDER_UNAVAILABLE"
            )
        size = result.get("file_size")
        if type(size) is int and size > MAX_DOWNLOAD_BYTES:
            raise DownloadRefused("PROVIDER_UNSUPPORTED")  # refused before any byte moves
        data = self._api.download_file(
            result["file_path"],
            limit=MAX_DOWNLOAD_BYTES,
            deadline=time.monotonic() + DOWNLOAD_DEADLINE_S,
        )
        return blob(data, "application/octet-stream")  # the service reads the type from the ref

    def _file_id(self, file_unique_id: str) -> str:
        if (
            not isinstance(file_unique_id, str)
            or not file_unique_id.isascii()
            or '"' in file_unique_id
        ):
            raise DownloadRefused("NOT_FOUND")
        needle = json.dumps({"file_unique_id": file_unique_id})[1:-1]
        pattern = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = self._conn.execute(
            "SELECT payload FROM bot_updates WHERE payload LIKE ? ESCAPE '\\'"
            " ORDER BY update_id DESC LIMIT ?",
            (pattern, _SCANNED),
        ).fetchall()
        for (payload,) in rows:
            for node in _objects(json.loads(payload)):
                found = node.get("file_id")
                if node.get("file_unique_id") == file_unique_id and isinstance(found, str):
                    return found
        raise DownloadRefused("NOT_FOUND")  # purged by retention, or never retained


def _objects(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _retry_after(envelope: Any) -> int | None:
    params = envelope.get("parameters") if isinstance(envelope, dict) else None
    wait = params.get("retry_after") if isinstance(params, dict) else None
    return wait if type(wait) is int and wait > 0 else None
