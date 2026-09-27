"""Staged media, in memory only (catalog amendment G8; owner decision D3).

A tool call carries at most one frame, so a file arrives in pieces: ``begin`` names its type,
size and SHA-256 and returns a ``upl_`` ref; ``chunk`` appends the next piece, strictly in
order; the upload tool then ``take``s the whole file once. A staged file is bound to the client
that began it, expires after five minutes, is used once, is capped at 16 MiB (WhatsApp's video
limit) and is checked against its SHA-256 before anything reaches a provider. Nothing is
written to disk, and a restart forgets every staged file. A small file (at most 512 KiB) may
come inline as ``data_b64`` instead. Downloads are held the same way while a client pages
through them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from comms.core import refs
from comms.core.errors import CommsError

__all__ = [
    "CHUNK_MAX",
    "INLINE_MAX",
    "MAX_BYTES",
    "TTL_S",
    "Staged",
    "StagedMedia",
    "decode_b64",
]

MAX_BYTES = 16 * 1024 * 1024
CHUNK_MAX = 48 * 1024  # raw bytes per chunk: its base64 fits one tool call's frame
INLINE_MAX = 512 * 1024
TTL_S = 300.0
MIME_MAX = 128


@dataclass
class Staged:
    client: str
    mime: str
    size: int
    sha256: str
    expires: float
    data: bytearray = field(default_factory=bytearray, repr=False)
    next_seq: int = 0

    def __repr__(self) -> str:
        return f"Staged(mime={self.mime!r}, size={self.size}, received={len(self.data)})"


def decode_b64(value: object, *, limit: int) -> bytes:
    """Strict base64 of at most ``limit`` bytes, or INVALID_ARGUMENT."""
    if not isinstance(value, str) or len(value) > (limit + 2) // 3 * 4:
        raise CommsError("INVALID_ARGUMENT")
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise CommsError("INVALID_ARGUMENT") from None
    if not data or len(data) > limit:
        raise CommsError("INVALID_ARGUMENT")
    return data


def _sha(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or value.strip("0123456789abcdef") != "":
        raise CommsError("INVALID_ARGUMENT")
    return value


class StagedMedia:
    """Uploads being staged and downloads being paged, per client, in memory."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._uploads: dict[str, Staged] = {}
        self._downloads: dict[tuple[str, str], tuple[float, bytes, str]] = {}
        self._replies: dict[tuple[str, str], tuple[float, dict[str, object]]] = {}
        self._taken: dict[str, tuple[str, str, bytes, str, float]] = {}

    def replayed(
        self, client: str, request_id: str, run: Callable[[], dict[str, object]]
    ) -> dict[str, object]:
        """A staging call by ``req_``: a replay returns its first result and stages nothing
        more (for as long as the staged file lives)."""
        self._sweep()
        key = (client, request_id)
        if key in self._replies:
            return {**self._replies[key][1], "replayed": True}
        result = run()
        self._replies[key] = (self._clock() + TTL_S, result)
        return {**result, "replayed": False}

    def __repr__(self) -> str:
        return f"StagedMedia(uploads={len(self._uploads)})"

    def _sweep(self) -> None:
        now = self._clock()
        for ref in [r for r, s in self._uploads.items() if s.expires <= now]:
            del self._uploads[ref]
        for key in [k for k, v in self._downloads.items() if v[0] <= now]:
            del self._downloads[key]
        for reply in [k for k, v in self._replies.items() if v[0] <= now]:
            del self._replies[reply]
        for used in [r for r, v in self._taken.items() if v[4] <= now]:
            del self._taken[used]

    def begin(self, client: str, mime: object, size: object, sha256: object) -> dict[str, object]:
        self._sweep()
        if not isinstance(mime, str) or not 0 < len(mime) <= MIME_MAX or "/" not in mime:
            raise CommsError("INVALID_ARGUMENT")
        if type(size) is not int or not 0 < size <= MAX_BYTES:
            raise CommsError("INVALID_ARGUMENT")
        ref = refs.mint("upload")
        expires = self._clock() + TTL_S
        self._uploads[ref] = Staged(client, mime, size, _sha(sha256), expires)
        return {"upload": ref, "chunk_max": CHUNK_MAX, "expires_in": int(TTL_S)}

    def _own(self, client: str, ref: object) -> Staged:
        self._sweep()
        staged = self._uploads.get(ref) if isinstance(ref, str) else None
        if staged is None or not hmac.compare_digest(staged.client, client):
            raise CommsError("NOT_FOUND")  # unknown, expired, used, or another client's
        return staged

    def chunk(self, client: str, ref: object, seq: object, data_b64: object) -> dict[str, object]:
        staged = self._own(client, ref)
        if type(seq) is not int or seq != staged.next_seq:
            raise CommsError("INVALID_ARGUMENT")  # strictly in order, no gap, no repeat
        piece = decode_b64(data_b64, limit=CHUNK_MAX)
        if len(staged.data) + len(piece) > staged.size:
            raise CommsError("INVALID_ARGUMENT")
        staged.data += piece
        staged.next_seq += 1
        return {"upload": ref, "received": len(staged.data),
                "complete": len(staged.data) == staged.size}  # fmt: skip

    def take(self, client: str, ref: object, request_id: str) -> tuple[bytes, str]:
        """The whole file, for one request: incomplete or not matching its SHA-256 is refused
        and dropped. The request that took it may take it again while it lives (a replay, which
        the executor answers from its record); any other request finds nothing."""
        self._sweep()
        taken = self._taken.get(ref) if isinstance(ref, str) else None
        if taken is not None:
            owner, first, data, mime, _expires = taken
            if hmac.compare_digest(owner, client) and first == request_id:
                return data, mime
            raise CommsError("NOT_FOUND")
        staged = self._own(client, ref)
        del self._uploads[str(ref)]
        data = bytes(staged.data)
        if len(data) != staged.size:
            raise CommsError("INVALID_ARGUMENT")
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), staged.sha256):
            raise CommsError("INVALID_ARGUMENT")
        self._taken[str(ref)] = (client, request_id, data, staged.mime, staged.expires)
        return data, staged.mime

    def hold_download(self, client: str, media: str, data: bytes, mime: str) -> None:
        self._sweep()
        self._downloads[(client, media)] = (self._clock() + TTL_S, data, mime)

    def held_download(self, client: str, media: str) -> tuple[bytes, str] | None:
        self._sweep()
        held = self._downloads.get((client, media))
        return None if held is None else (held[1], held[2])
