"""The one upload of a video to the ``upload_url`` Pinterest returned (proposed A50, D-P6, D-P8).

Pinterest's ``POST /v5/media`` answers an S3 presigned POST: a URL and the form fields to send
with the file. comms POSTs the staged bytes once, as ``multipart/form-data`` with every field and
the file, to a host under ``amazonaws.com`` only (🧪 GP-4 records the real host), with **no**
``Authorization`` header. The URL and the fields are AWS-signed and short-lived: they are used for
this one call and never stored, logged or returned. A 2xx is the upload; a 4xx is a refusal a
resend cannot fix; anything else is ambiguous (resolved by ``GET /v5/media/{id}``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Literal

import httpx

from comms.transports.net import host_allowed, suffix_pinned_client

__all__ = [
    "MAX_FIELDS",
    "UPLOAD_SUFFIXES",
    "VIDEO_MAX_BYTES",
    "VIDEO_MIMES",
    "check_target",
    "upload_video",
]

UPLOAD_SUFFIXES = ("amazonaws.com",)
VIDEO_MAX_BYTES = 16 * 1024 * 1024  # D-P8: the staged upload's cap (services/uploads.MAX_BYTES)
VIDEO_MIMES: Mapping[str, str] = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/x-m4v": "m4v",
}
MAX_FIELDS = 32
_FIELD_NAME = re.compile(r"\A[A-Za-z0-9_.\-]{1,64}\Z")
_TIMEOUT = 25.0  # D-P13: one upload of at most 16 MiB inside the proxy's 30 s

Outcome = Literal["ok", "refused", "unknown"]


def check_target(upload_url: object, parameters: object) -> tuple[str, dict[str, str]]:
    """The URL and fields Pinterest answered, if comms may POST to them; ``ValueError``
    otherwise. Values are never echoed."""
    if not isinstance(upload_url, str) or not host_allowed(upload_url, UPLOAD_SUFFIXES):
        raise ValueError("upload url refused")
    if not isinstance(parameters, dict) or not 0 < len(parameters) <= MAX_FIELDS:
        raise ValueError("upload parameters refused")
    fields: dict[str, str] = {}
    for name, value in parameters.items():
        if not isinstance(name, str) or not _FIELD_NAME.match(name):
            raise ValueError("upload parameters refused")
        if not isinstance(value, str) or not 0 < len(value) <= 4096:
            raise ValueError("upload parameters refused")
        fields[name] = value
    return upload_url, fields


def upload_video(
    upload_url: str,
    parameters: Mapping[str, str],
    data: bytes,
    mime: str,
    *,
    timeout: float = _TIMEOUT,
    transport: httpx.BaseTransport | None = None,
) -> Outcome:
    """POST the file once. The caller has already checked the target (``check_target``)."""
    extension = VIDEO_MIMES.get(mime)
    if extension is None:
        raise ValueError("video mime refused")
    client = suffix_pinned_client(UPLOAD_SUFFIXES, timeout=timeout, transport=transport)
    try:
        response = client.post(
            upload_url,
            data=dict(parameters),
            files={"file": (f"video.{extension}", data, mime)},
        )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return "refused"  # nothing was sent: the registration stays unused
    except httpx.HTTPError:
        return "unknown"
    finally:
        client.close()
    return _verdict(response.status_code)


def _verdict(status: int) -> Outcome:
    if 200 <= status < 300:
        return "ok"
    if 400 <= status < 500:
        return "refused"
    return "unknown"


def describe(outcome: Outcome) -> dict[str, Any]:
    """A fixed description of an outcome for a result (no URL, no field)."""
    return {"uploaded": outcome == "ok"}
