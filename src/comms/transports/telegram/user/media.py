"""The user account's media download (spec A47, H3).

A user-account ``med_`` is the message's locator (``<marked chat>:<message id>``). The adapter
fetches the message again for a fresh file reference and downloads the file on its own DC, in
aligned slices, at most 16 MiB. No file reference, DC or location leaves the adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from comms.transports.net import MAX_DOWNLOAD_BYTES, DownloadRefused, MediaBlob, blob
from comms.transports.telegram.peers import unmark_chat_id
from comms.transports.telegram.telegram.errors import GatewayError

__all__ = ["UserMedia"]

DOWNLOAD_TIMEOUT_S = 60.0
Runner = Callable[[Coroutine[Any, Any, Any]], Any]


class MediaSession(Protocol):
    async def download_media(
        self, peer_type: str, peer_id: int, message_id: int, *, max_bytes: int, timeout: float
    ) -> bytes: ...


class UserMedia:
    def __init__(self, session: MediaSession, *, run: Runner) -> None:
        self._session, self._run = session, run

    def __repr__(self) -> str:
        return "UserMedia(<redacted>)"

    def retrieve(self, locator: str) -> MediaBlob:
        chat, _sep, message_id = (
            locator.rpartition(":") if isinstance(locator, str) else ("", "", "")
        )
        if not chat or not message_id.isascii() or not message_id.isdigit():
            raise DownloadRefused("NOT_FOUND")
        try:
            peer_type, peer_id = unmark_chat_id(chat)
        except ValueError:
            raise DownloadRefused("NOT_FOUND") from None
        try:
            data = self._run(
                self._session.download_media(
                    peer_type, peer_id, int(message_id),
                    max_bytes=MAX_DOWNLOAD_BYTES, timeout=DOWNLOAD_TIMEOUT_S,
                )
            )  # fmt: skip
        except GatewayError as failed:
            if failed.code == "FLOOD_WAIT":  # includes the Premium download throttle (Gx4)
                raise DownloadRefused("RATE_LIMITED", retry_after=failed.retry_after) from None
            if failed.code in ("NOT_ACCESSIBLE", "MESSAGE_NOT_FOUND"):
                raise DownloadRefused("NOT_FOUND") from None
            raise DownloadRefused("PROVIDER_UNAVAILABLE") from None
        return blob(data, "application/octet-stream")  # the service reads the type from the ref
