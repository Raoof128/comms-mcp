"""Media services (comms v0.3 Task D17; P §33).

Every media object is named by an opaque ``med_`` ref; the provider id stays internal.
``inspect`` returns type, size and digest; ``delete`` is an audited provider write. Upload takes
staged bytes (G8, D3), which never pass through a request digest (their SHA-256 does);
download pages a held file in bounded base64 slices.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from typing import Any, Protocol

from comms.core.errors import CommsError
from comms.core.objects import resolve_object
from comms.core.providers.capability import Capability as C
from comms.core.providers.protocols import ProviderTarget
from comms.services.capability import CapabilityService
from comms.services.mutations import CallContext, MutationExecutor
from comms.services.uploads import CHUNK_MAX, StagedMedia
from comms.services.writes import ProviderWrites, summary

__all__ = ["MediaService", "MediaSource"]

ACTOR = "whatsapp_cloud"


class MediaSource(Protocol):
    def info(self, media_id: str) -> Mapping[str, Any]: ...

    def retrieve(self, media_id: str) -> Any: ...  # a blob: ``data``, ``mime``


class MediaService:
    def __init__(
        self,
        conn: Any,
        capability: CapabilityService,
        executor: MutationExecutor,
        source: MediaSource,
    ) -> None:
        self._conn, self._source = conn, source
        self._writes = ProviderWrites(conn, capability, executor)

    def inspect(self, media: str) -> dict[str, Any]:
        found = resolve_object(self._conn, media, "media")
        try:
            info = self._source.info(found.provider_identity)
        except ValueError:
            raise CommsError("PROVIDER_UNAVAILABLE") from None
        return {
            "media": media,
            "mime": info.get("mime_type"),
            "size": info.get("file_size"),
            "sha256": info.get("sha256"),
        }

    def delete(
        self, ctx: CallContext, account: ProviderTarget, media: str, request_id: str
    ) -> dict[str, Any]:
        _chosen, _target, outcome = self._writes.write(
            ctx,
            "media.delete",
            {ACTOR: account},
            C.MEDIA_DELETE,
            {},
            request_id,
            ACTOR,
            objects={("media", "media_id"): media},
        )
        return {**summary(ACTOR, outcome), "media": media}

    def upload(
        self, ctx: CallContext, account: ProviderTarget, data: bytes, mime: str, request_id: str
    ) -> dict[str, Any]:
        """``media.upload`` (G8, D3): staged bytes to a new ``med_``; the bytes reach only the
        adapter, and the request digest holds their SHA-256."""
        _chosen, _target, outcome = self._writes.write(
            ctx, "media.upload", {ACTOR: account}, C.MEDIA_UPLOAD,
            {"data": data, "mime": mime}, request_id, ACTOR, object_kind="media",
        )  # fmt: skip
        return {**summary(ACTOR, outcome), "media": outcome.result.get("object_ref")}

    def download(self, staged: StagedMedia, client: str, media: str, offset: int, length: int
                 ) -> dict[str, Any]:  # fmt: skip
        """``media.download`` (G8): one bounded slice of the file, base64; the whole file is
        fetched once (through the Meta-host-pinned downloader) and held for this client."""
        if type(offset) is not int or offset < 0 or type(length) is not int:
            raise CommsError("INVALID_ARGUMENT")
        if not 0 < length <= CHUNK_MAX:
            raise CommsError("INVALID_ARGUMENT")
        held = staged.held_download(client, media)
        if held is None:
            found = resolve_object(self._conn, media, "media")
            try:
                blob = self._source.retrieve(found.provider_identity)
            except ValueError:
                raise CommsError("PROVIDER_UNAVAILABLE") from None
            held = (blob.data, blob.mime)
            staged.hold_download(client, media, *held)
        data, mime = held
        if offset > len(data):
            raise CommsError("INVALID_ARGUMENT")
        piece = data[offset : offset + length]
        return {
            "media": media, "mime": mime, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "offset": offset,
            "data_b64": base64.b64encode(piece).decode("ascii"),
            "complete": offset + len(piece) >= len(data),
        }  # fmt: skip
