"""The Bot API HTTP client (comms v0.3 Task C6; A19, A26).

One pinned origin (``https://api.telegram.org``), one ``POST`` per call, no retries, no
redirects. ``method`` comes from the closed ``BOT_METHODS`` set, never from a caller's string.
The token is read from the secret store once, checked against the Bot API token shape, and
goes only into the URL path: ``repr`` hides it, transport errors are re-raised as a fixed
``BotTransportError`` with no chained httpx exception (which holds the URL), and a filter on
the ``httpx`` logger redacts the path httpx logs at INFO for every request.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from comms.core.keys.secrets import SecretStore
from comms.transports.net import DownloadRefused, pinned_client, read_capped

__all__ = ["BOT_METHODS", "BOT_ORIGIN", "BotApi", "BotRefused", "BotResponse", "BotTransportError"]

BOT_ORIGIN = "https://api.telegram.org"
TOKEN_ITEM = "telegram-bot-token"
_TOKEN = re.compile(r"\A[0-9]{1,20}:[A-Za-z0-9_-]{1,128}\Z")
# A47 (Gx13): a relative path of plain segments; the Bot API's own paths are like
# ``documents/file_7.pdf`` or ``photos/file_12.jpg``
_FILE_PATH = re.compile(
    r"\A[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}(/[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}){0,3}\Z"
)
_TOKEN_IN_PATH = re.compile(r"/bot[0-9]{1,20}:[A-Za-z0-9_-]+")

BOT_METHODS = frozenset(
    {
        "getMe",
        "getUpdates",
        "sendMessage",
        "editMessageText",
        "deleteMessage",
        "forwardMessage",
        "pinChatMessage",
        "unpinChatMessage",
        "getChat",
        "getChatMember",
        "getChatAdministrators",
        "getChatMemberCount",
        "banChatMember",
        "unbanChatMember",
        "restrictChatMember",
        "promoteChatMember",
        "setChatTitle",
        "setChatDescription",
        "setChatPermissions",
        "setChatPhoto",  # G8: multipart
        "createChatInviteLink",
        "editChatInviteLink",
        "revokeChatInviteLink",
        "exportChatInviteLink",  # G6: a new primary link revokes the old
        "setChatMemberTag",  # A46 (Bot API 9.5)
        "deleteMessageReaction",  # A46 (Bot API 10.0)
        "deleteAllMessageReactions",
        "getFile",  # A47 (H3): then one streamed GET on the file host
        "sendPhoto",  # A47 (H4): multipart, or by file_id
        "sendDocument",
        "approveChatJoinRequest",
        "declineChatJoinRequest",
        "createForumTopic",
        "editForumTopic",
        "closeForumTopic",
        "reopenForumTopic",
    }
)


class _RedactToken(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "/bot" in message:
            record.msg, record.args = _TOKEN_IN_PATH.sub("/bot<redacted>", message), ()
        return True


if not any(isinstance(f, _RedactToken) for f in logging.getLogger("httpx").filters):
    logging.getLogger("httpx").addFilter(_RedactToken())


class BotRefused(Exception):
    """A call the client will not make (unknown method, malformed token). Fixed messages."""


class BotTransportError(Exception):
    """No complete HTTP response. ``stage`` is ``not_sent`` only when the connection was never
    established, so no request byte can have reached Telegram; otherwise ``ambiguous``."""

    def __init__(self, stage: Literal["not_sent", "ambiguous"]) -> None:
        super().__init__(f"bot api transport error ({stage})")
        self.stage = stage


@dataclass(frozen=True)
class BotResponse:
    http_status: int
    envelope: Mapping[str, Any] | None = field(repr=False)  # None: the body was not a JSON object


class BotApi:
    def __init__(
        self,
        secrets: SecretStore,
        *,
        version: int,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        try:
            token = secrets.get(TOKEN_ITEM, version).decode("ascii")
        except UnicodeDecodeError:
            token = ""
        if not _TOKEN.match(token):
            raise BotRefused("the bot token is malformed")
        self._token = token
        self._client = pinned_client(BOT_ORIGIN, timeout=timeout, transport=transport)

    def __repr__(self) -> str:
        return "BotApi(<redacted>)"

    def call(self, method: str, params: Mapping[str, Any]) -> BotResponse:
        if method not in BOT_METHODS:
            raise BotRefused("the bot api method is not allowed")
        stage: Literal["not_sent", "ambiguous"] | None = None
        try:
            response = self._client.post(
                f"{BOT_ORIGIN}/bot{self._token}/{method}", json=dict(params)
            )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            stage = "not_sent"
        except httpx.HTTPError:
            stage = "ambiguous"
        if stage is not None:
            raise BotTransportError(stage)  # outside the handler: no chained, URL-bearing error
        try:
            envelope = json.loads(response.content)
        except ValueError:
            envelope = None
        return BotResponse(response.status_code, envelope if isinstance(envelope, dict) else None)

    def call_multipart(
        self, method: str, params: Mapping[str, Any], files: Mapping[str, Any]
    ) -> BotResponse:
        """One multipart call (G8: ``setChatPhoto``); classified as ``call`` is."""
        if method not in BOT_METHODS:
            raise BotRefused("the bot api method is not allowed")
        stage: Literal["not_sent", "ambiguous"] | None = None
        try:
            response = self._client.post(
                f"{BOT_ORIGIN}/bot{self._token}/{method}",
                data={k: str(v) for k, v in params.items()},
                files=dict(files),
            )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            stage = "not_sent"
        except httpx.HTTPError:
            stage = "ambiguous"
        if stage is not None:
            raise BotTransportError(stage)
        try:
            envelope = json.loads(response.content)
        except ValueError:
            envelope = None
        return BotResponse(response.status_code, envelope if isinstance(envelope, dict) else None)

    def download_file(self, file_path: str, *, limit: int, deadline: float) -> bytes:
        """A47 (H3): one streamed ``GET`` of ``/file/bot<token>/<file_path>`` on the pinned
        origin, capped at ``limit`` bytes. ``file_path`` is checked first, since it joins a URL
        that carries the token (Gx13); no error ever carries the URL."""
        if not _FILE_PATH.match(file_path) or ".." in file_path.split("/"):
            raise DownloadRefused("PROVIDER_UNAVAILABLE")
        refused: DownloadRefused | None = None
        try:
            with self._client.stream(
                "GET", f"{BOT_ORIGIN}/file/bot{self._token}/{file_path}"
            ) as response:
                if response.status_code != 200:
                    raise DownloadRefused("PROVIDER_UNAVAILABLE")
                return read_capped(response, limit=limit, deadline=deadline)
        except DownloadRefused as exc:
            refused = exc
        except httpx.HTTPError:
            refused = DownloadRefused("PROVIDER_UNAVAILABLE")
        raise DownloadRefused(refused.code)  # outside the handler: no chained, URL-bearing error

    def close(self) -> None:
        self._client.close()
