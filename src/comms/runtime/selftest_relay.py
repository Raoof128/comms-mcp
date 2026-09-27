"""The selftest daemon's route to a relay under ``wrangler dev`` (comms v0.3 A48, R5).

``wrangler dev`` serves plain HTTP on loopback, while the relay client speaks only https to its
pinned origin. In the selftest composition alone, this transport carries a request for
``https://127.0.0.1:<port>`` to ``http://127.0.0.1:<port>``; any other host is refused. The
production daemon never builds it.
"""

from __future__ import annotations

import httpx

from comms.transports.net import EgressRefused

__all__ = ["LoopbackRelay"]


class LoopbackRelay(httpx.BaseTransport):
    def __init__(self) -> None:
        self._inner = httpx.HTTPTransport(retries=0)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https" or request.url.host != "127.0.0.1":
            raise EgressRefused
        request.url = request.url.copy_with(scheme="http")
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()
