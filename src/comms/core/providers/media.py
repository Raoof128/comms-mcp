"""The one rule for a media send's shape (spec A47, H4), shared by the service and every actor.

A send is a ``photo`` or a ``document``. Its caption is at most 1024 UTF-16 code units, the
unit Telegram counts in; the Bot API allows 0–1024 characters after entity parsing,
``caption_length_limit_default`` is 1024, and Meta allows 1024, so this bound holds on all three
(Gf11). No entities are ever sent. A file's own bytes say what an image is (Gx11): the MIME type
a client declares is only a claim. A document's name on the wire is neutral, derived from its
type, never a caller's string (Gf7).
"""

from __future__ import annotations

import mimetypes

__all__ = ["CAPTION_MAX", "KINDS", "caption", "image_type", "neutral_name"]

KINDS = ("photo", "document")
CAPTION_MAX = 1024  # UTF-16 code units


def caption(value: object) -> str:
    """A caption, or ValueError. Empty is allowed (no caption)."""
    if not isinstance(value, str) or len(value.encode("utf-16-le")) // 2 > CAPTION_MAX:
        raise ValueError("caption refused")
    return value


def image_type(data: bytes) -> str | None:
    """``image/jpeg`` or ``image/png`` by the file's magic bytes, else None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def neutral_name(mime: str) -> str:
    """``file`` plus the type's usual extension (``file.pdf``), else ``file.bin``."""
    extension = mimetypes.guess_extension(mime.split(";")[0].strip().lower(), strict=True)
    return "file" + (extension if extension and extension.isascii() else ".bin")
