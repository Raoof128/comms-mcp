"""The host-pinned HTTP client for provider adapters (comms v0.3 Task C1, A26).

Every provider adapter reaches the network only through ``pinned_client``: one allowed
``https`` origin, checked on every request (scheme, host and port), and no redirect is ever
followed. Only the adapter network modules may import ``httpx`` (pinned by
``tests/security/test_egress.py``); the typed egress matrix (A44) builds on this.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

__all__ = [
    "MAX_DOWNLOAD_BYTES",
    "DownloadRefused",
    "EgressRefused",
    "MediaBlob",
    "blob",
    "host_allowed",
    "pinned_client",
    "read_capped",
    "suffix_pinned_client",
]

# D3 and A47: the most any download holds (WhatsApp's video limit; the Bot API allows 20 MB)
MAX_DOWNLOAD_BYTES = 16 * 1024 * 1024
_DOWNLOAD_CODES = frozenset(
    {
        "NOT_FOUND",
        "PROVIDER_UNSUPPORTED",
        "PROVIDER_UNAVAILABLE",
        "RATE_LIMITED",
        "INVALID_ARGUMENT",
    }
)


class DownloadRefused(ValueError):
    """A download an adapter will not make or finish (G8, A47). A fixed service code and never
    a URL, a path, a token or a file id; ``retry_after`` only with ``RATE_LIMITED``."""

    def __init__(
        self, code: str = "PROVIDER_UNAVAILABLE", *, retry_after: int | None = None
    ) -> None:
        if code not in _DOWNLOAD_CODES:
            code = "PROVIDER_UNAVAILABLE"
        super().__init__(f"download refused: {code}")
        self.code = code
        self.retry_after = retry_after if code == "RATE_LIMITED" else None


@dataclass(frozen=True)
class MediaBlob:
    data: bytes = field(repr=False)
    mime: str
    sha256: str


def blob(data: bytes, mime: str) -> MediaBlob:
    return MediaBlob(data, mime, hashlib.sha256(data).hexdigest())


def read_capped(response: httpx.Response, *, limit: int, deadline: float) -> bytes:
    """The one bounded read of a streamed body (G8, A47 Gx12): stops past ``limit`` bytes or
    ``deadline`` (``time.monotonic``) rather than holding whatever the server sends."""
    chunks, size = [], 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > limit:
            raise DownloadRefused("PROVIDER_UNSUPPORTED")  # larger than any download may be
        if time.monotonic() > deadline:
            raise DownloadRefused("PROVIDER_UNAVAILABLE")
        chunks.append(chunk)
    return b"".join(chunks)


class EgressRefused(Exception):
    """A request left its pinned origin. Fixed message; never the URL."""

    def __init__(self) -> None:
        super().__init__("egress refused: the request is not to the pinned origin")


def _origin(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query:
        raise ValueError("the pinned origin must be https://host[:port]")
    return parts.scheme, parts.hostname, parts.port or 443


class _Pinned(httpx.BaseTransport):
    def __init__(self, origin: tuple[str, str, int], inner: httpx.BaseTransport) -> None:
        self._origin, self._inner = origin, inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if (url.scheme, url.host, url.port or 443) != self._origin:
            raise EgressRefused
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def pinned_client(
    allowed_origin: str, *, timeout: float, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """An ``httpx.Client`` bound to one origin; ``transport`` is the injected network seam."""
    origin = _origin(allowed_origin)
    return httpx.Client(
        transport=_Pinned(origin, transport or httpx.HTTPTransport(retries=0)),
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,  # no proxy or certificate settings from the environment
    )


def host_allowed(url: str, suffixes: tuple[str, ...]) -> bool:
    """``https`` on 443, no userinfo, and a host that after IDNA normalisation equals a suffix
    or ends with ``"." + suffix``: an exact suffix match, never a substring (A26, O6)."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        return False
    if (
        parts.scheme != "https"
        or "@" in parts.netloc
        or port not in (None, 443)
        or not parts.hostname
    ):
        return False
    try:
        host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in suffixes)


class _SuffixPinned(httpx.BaseTransport):
    def __init__(self, suffixes: tuple[str, ...], inner: httpx.BaseTransport) -> None:
        self._suffixes, self._inner = suffixes, inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if not host_allowed(str(request.url), self._suffixes):
            raise EgressRefused
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def suffix_pinned_client(
    suffixes: tuple[str, ...], *, timeout: float, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """A client that reaches only hosts under ``suffixes`` (checked on every request), never
    follows a redirect itself, and ignores the environment. For the Meta media downloader."""
    return httpx.Client(
        transport=_SuffixPinned(suffixes, transport or httpx.HTTPTransport(retries=0)),
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    )
