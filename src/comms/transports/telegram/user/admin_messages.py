"""MTProto message writes (comms v0.3 Task D14; P §23, §72): send, edit, delete, pin; and
(A47) marking a person's conversation read.

``message.send`` is keyed: its ``random_id`` comes from the operation key (A20), so a retry
with the same key is one message on Telegram, and it runs through ``user.send`` with its one
reconciliation. A delete asks for everyone unless ``revoke`` is false; a supergroup or channel
delete is always for everyone, and the adapter reports the scope it actually performed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from comms.core.providers import media
from comms.core.providers.capability import Capability as C
from comms.transports.telegram import chat_specs as specs
from comms.transports.telegram.args import boolean, positive_int, take, text

__all__ = ["MESSAGE_SPECS", "TEXT_MAX"]

TEXT_MAX = 4096


def _send(args: Mapping[str, Any]) -> dict[str, Any]:
    return take(args, {"text": text(1, TEXT_MAX)}, {"reply_to_message_id": positive_int})


def _edit(args: Mapping[str, Any]) -> dict[str, Any]:
    return take(args, {"message_id": positive_int, "text": text(1, TEXT_MAX)}, {})


def _delete(args: Mapping[str, Any]) -> dict[str, Any]:
    fields = take(args, {"message_id": positive_int}, {"revoke": boolean})
    return {"message_id": fields["message_id"], "revoke": fields.get("revoke", True)}


def _mark_read(args: Mapping[str, Any]) -> dict[str, Any]:
    return take(args, {"message_id": positive_int}, {})  # A47: read up to this message


def _pin(args: Mapping[str, Any]) -> dict[str, Any]:
    return take(args, {"message_id": positive_int, "pinned": boolean}, {})


_MEDIA_FIELDS = frozenset({"kind", "caption", "data", "mime", "media_id"})


def send_media(args: Mapping[str, Any]) -> dict[str, Any]:
    """A47 (H4): a photo or a document from bytes or from a held file, checked before any
    call; the caption is empty when none is given."""
    kind = args.get("kind")
    if (
        kind not in media.KINDS
        or set(args) - _MEDIA_FIELDS
        or ("data" in args) == ("media_id" in args)
    ):
        raise ValueError("operation arguments are malformed")
    spec: dict[str, Any] = {"kind": kind, "caption": media.caption(args.get("caption", ""))}
    if "data" in args:
        data, mime = args["data"], args.get("mime")
        if not isinstance(data, bytes) or not data or not isinstance(mime, str):
            raise ValueError("operation arguments are malformed")
        if kind == "photo" and media.image_type(data) is None:
            raise ValueError("photo refused")  # a JPEG or PNG
        return {**spec, "data": data, "mime": mime}
    if not isinstance(args["media_id"], str) or ":" not in args["media_id"]:
        raise ValueError("operation arguments are malformed")
    return {**spec, "media_id": args["media_id"]}


MESSAGE_SPECS = {
    C.MESSAGE_SEND: _send,
    C.MESSAGE_EDIT: _edit,
    C.MESSAGE_DELETE: _delete,
    C.MESSAGE_PIN: _pin,
    C.MESSAGE_MARK_READ: _mark_read,
    C.MESSAGE_SEND_MEDIA: send_media,  # A47 (H4): keyed by random_id, like a send  # A47: a person's conversation only (``UserAdmin``)
    C.MESSAGE_FORWARD: specs.forward,  # G7: keyed like a send (random_id from the op key)
}
