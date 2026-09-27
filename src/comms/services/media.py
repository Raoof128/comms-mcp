"""Media services (comms v0.3 Task D17; P §33).

Every media object is named by an opaque ``med_`` ref; the provider id stays internal.
``inspect`` returns type, size and digest; ``delete`` is an audited provider write. Upload takes
staged bytes (G8, D3), which never pass through a request digest (their SHA-256 does);
download pages a held file in bounded base64 slices.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from comms.core.errors import CommsError
from comms.core.objects import media_facts, record_media, resolve_object
from comms.core.providers import media as media_rules
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
        source: MediaSource | None,
        *,
        downloads: Mapping[str, Any] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._conn, self._source, self._clock = conn, source, clock
        # A47 (H3): who fetches a ``med_``'s bytes is the actor that minted it
        self._downloads: dict[str, Any] = dict(downloads or {})
        if source is not None:
            self._downloads.setdefault(ACTOR, source)
        self._writes = ProviderWrites(conn, capability, executor)

    def inspect(self, media: str) -> dict[str, Any]:
        found = resolve_object(self._conn, media, "media")
        if found.transport == "telegram":  # A47 (H5): the recorded facts, with no call
            facts = media_facts(self._conn, media)
            if facts is None:
                raise CommsError("NOT_FOUND")
            return {"media": media, "mime": facts["mime"], "size": facts["size"], "sha256": None}
        if self._source is None:
            raise CommsError("NOT_CONFIGURED")
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
        self, ctx: CallContext, account: ProviderTarget | None, media: str, request_id: str
    ) -> dict[str, Any]:
        if resolve_object(self._conn, media, "media").transport == "telegram":
            raise CommsError("PROVIDER_UNSUPPORTED")  # A47: Telegram has no file delete
        if account is None or self._source is None:
            raise CommsError("NOT_CONFIGURED")
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
        self,
        ctx: CallContext,
        account: ProviderTarget,
        data: bytes,
        mime: str,
        request_id: str,
        *,
        kind: str | None = None,
    ) -> dict[str, Any]:
        """``media.upload`` (G8, D3): staged bytes to a new ``med_``; the bytes reach only the
        adapter, and the request digest holds their SHA-256. A47 (H5): the Telegram user account
        uploads to itself, by kind (a JPEG or PNG is a photo unless told otherwise), and its
        ``med_`` records its facts."""
        actor = account.actor
        args: dict[str, Any] = {"data": data, "mime": mime}
        if account.transport == "telegram":
            args["kind"] = kind or ("photo" if media_rules.image_type(data) else "document")
        _chosen, _target, outcome = self._writes.write(
            ctx, "media.upload", {actor: account}, C.MEDIA_UPLOAD, args, request_id, actor,
            object_kind="media",
        )  # fmt: skip
        ref = outcome.result.get("object_ref")
        if (
            account.transport == "telegram"
            and outcome.state == "SUCCEEDED"
            and isinstance(ref, str)
        ):
            record_media(self._conn, ref, args["kind"], mime, len(data), "telegram_upload",
                         now=self._clock())  # fmt: skip
        return {**summary(actor, outcome), "media": ref}

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
            source = self._downloads.get(found.actor)
            if source is None:
                raise CommsError("NOT_CONFIGURED")
            try:
                blob = source.retrieve(found.provider_identity)
            except ValueError as refused:  # a fixed code, never a URL, path or file id
                raise _refusal(refused) from None
            facts = media_facts(self._conn, media)  # A47: a Telegram file's type is the ref's
            held = (blob.data, facts["mime"] if facts else blob.mime)
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


_DOWNLOAD_CODES = frozenset(
    {
        "NOT_FOUND",
        "PROVIDER_UNSUPPORTED",
        "PROVIDER_UNAVAILABLE",
        "RATE_LIMITED",
        "INVALID_ARGUMENT",
    }
)


def _refusal(refused: ValueError) -> CommsError:
    """An adapter's download refusal as the service error: its fixed code, else unavailable."""
    code = getattr(refused, "code", None)
    if code not in _DOWNLOAD_CODES:
        return CommsError("PROVIDER_UNAVAILABLE")
    if code == "RATE_LIMITED":
        wait = getattr(refused, "retry_after", None)
        return CommsError(code, retry_after=wait if type(wait) is int else None)
    return CommsError(code)
