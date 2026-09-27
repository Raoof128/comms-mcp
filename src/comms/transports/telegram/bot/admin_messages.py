"""Bot API message writes (comms v0.3 Task D14; P §23, §72): send, edit, delete.

``message.send`` is a ``MESSAGE_SEND`` without a provider key (resolve-only on ambiguity); its
provider ref is the new ``message_id``. The bot cannot delete a message only for itself, so a
local delete is not performed here, and a successful delete is reported as ``everyone``.
Pinning is in ``admin_chat``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from comms.core.providers import media
from comms.core.providers.capability import Capability as C
from comms.transports.telegram import chat_specs as specs
from comms.transports.telegram.args import boolean, positive_int, take, text

__all__ = ["DELETE_SCOPE", "MESSAGE_REQUESTS"]

DELETE_SCOPE = "everyone"
TEXT_MAX = 4096


def _send(chat_id: int, args: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    fields = take(args, {"text": text(1, TEXT_MAX)}, {"reply_to_message_id": positive_int})
    params: dict[str, Any] = {"chat_id": chat_id, "text": fields["text"]}
    if "reply_to_message_id" in fields:
        params["reply_parameters"] = {"message_id": fields["reply_to_message_id"]}
    return "sendMessage", params


def _edit(chat_id: int, args: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    fields = take(args, {"message_id": positive_int, "text": text(1, TEXT_MAX)}, {})
    return "editMessageText", {"chat_id": chat_id, **fields}


def _delete(chat_id: int, args: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    fields = take(args, {"message_id": positive_int}, {"revoke": boolean})
    if fields.get("revoke") is False:
        raise NotImplementedError("the bot cannot delete a message only for itself")
    return "deleteMessage", {"chat_id": chat_id, "message_id": fields["message_id"]}


def _forward(chat_id: int, args: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    fields = specs.forward(args)
    return "forwardMessage", {"chat_id": chat_id, "from_chat_id": int(fields["from_chat"]),
                              "message_id": fields["message_id"]}  # fmt: skip


PHOTO_MAX = 10 * 1024 * 1024  # the Bot API's multipart photo limit
_MEDIA_FIELDS = frozenset({"kind", "caption", "data", "mime", "media_id"})


def send_media(chat_id: int, args: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """A47 (H4): ``sendPhoto`` or ``sendDocument``, from bytes or from a held file; the file
    itself is attached by ``BotAdmin``. Checked before any call."""
    kind = args.get("kind")
    if (
        kind not in media.KINDS
        or set(args) - _MEDIA_FIELDS
        or ("data" in args) == ("media_id" in args)
    ):
        raise ValueError("operation arguments are malformed")
    params: dict[str, Any] = {"chat_id": chat_id}
    if args.get("caption"):
        params["caption"] = media.caption(args["caption"])
    if "data" in args:
        data, mime = args["data"], args.get("mime")
        if not isinstance(data, bytes) or not data or not isinstance(mime, str):
            raise ValueError("operation arguments are malformed")
        if kind == "photo" and (len(data) > PHOTO_MAX or media.image_type(data) is None):
            raise ValueError("photo refused")  # a JPEG or PNG of at most 10 MB
    elif not isinstance(args["media_id"], str) or not args["media_id"]:
        raise ValueError("operation arguments are malformed")
    return ("sendPhoto" if kind == "photo" else "sendDocument"), params


MESSAGE_REQUESTS = {
    C.MESSAGE_SEND: _send,
    C.MESSAGE_EDIT: _edit,
    C.MESSAGE_DELETE: _delete,
    C.MESSAGE_FORWARD: _forward,  # G7: the new message's id is its provider ref
    C.MESSAGE_SEND_MEDIA: send_media,  # A47 (H4)
}
