"""The Instagram Graph client (proposed A49, D-I6, section 3).

One pinned origin (``https://graph.instagram.com``), one request per call, no retries, no
redirects. The account's access token is read from the secret store once, checked for shape
(the same rule as the WhatsApp client's: comms' own, not Meta's), and sent only in the
``Authorization`` header: never in a URL, a parameter, a log line, a ``repr`` or an error. A
transport error is the fixed ``GraphTransportError`` with no chained httpx exception. Every
node joins a path only as ``me``, a numeric id or a DM thread or message id (letters,
digits, ``_``, ``=`` and ``-``: never path syntax), and every edge is one of a closed set.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import httpx

from comms.core.keys.secrets import SecretStore
from comms.transports.net import pinned_client
from comms.transports.whatsapp.cloud.http import GraphRefused, GraphResponse, GraphTransportError

__all__ = [
    "DEFAULT_API_VERSION",
    "EDGES",
    "GRAPH_IG_ORIGIN",
    "GraphIgApi",
    "GraphRefused",
    "GraphResponse",
    "GraphTransportError",
    "api_version_ok",
]

GRAPH_IG_ORIGIN = "https://graph.instagram.com"
DEFAULT_API_VERSION = "v25.0"  # D-I11: v26.0 is the latest (29 July 2026); v25.0 by default
_VERSION = re.compile(r"\Av[0-9]{2}\.0\Z")
_TOKEN = re.compile(r"\A[A-Za-z0-9_.\-]{20,512}\Z")
# ``me``, a numeric id, or a DM conversation or message id (base64url-like, no path syntax)
_NODE = re.compile(r"\A(?:me|[0-9]{1,20}|[A-Za-z0-9_=-]{16,512})\Z")
EDGES = frozenset(
    {
        "media",
        "media_publish",
        "insights",
        "comments",
        "replies",
        "tags",
        "conversations",
        "messages",
        "content_publishing_limit",
    }
)
_PARAM = re.compile(r"\A[a-z_]{1,32}\Z")
_TIMEOUT = 15.0  # D-I13: a tool makes at most two calls inside the proxy's 30 s


def api_version_ok(value: object) -> bool:
    return isinstance(value, str) and _VERSION.fullmatch(value) is not None


class GraphIgApi:
    def __init__(
        self,
        secrets: SecretStore,
        *,
        purpose: str,
        version: int,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = _TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        try:
            token = secrets.get(purpose, version).decode("ascii")
        except UnicodeDecodeError:
            token = ""
        if not _TOKEN.match(token):
            raise GraphRefused("the access token is malformed")
        if not api_version_ok(api_version):
            raise GraphRefused("the API version is malformed")
        self._token, self._version = token, api_version
        self._client = pinned_client(GRAPH_IG_ORIGIN, timeout=timeout, transport=transport)

    def __repr__(self) -> str:
        return "GraphIgApi(<redacted>)"

    # -- the calls ----------------------------------------------------------------------------

    def me(self, fields: Sequence[str]) -> GraphResponse:
        return self.get("me", params={"fields": ",".join(fields)})

    def get(
        self, node: str, edge: str | None = None, *, params: Mapping[str, str] | None = None
    ) -> GraphResponse:
        return self._call("GET", self._path(node, edge), params=params)

    def post(
        self,
        node: str,
        edge: str | None = None,
        *,
        params: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> GraphResponse:
        return self._call("POST", self._path(node, edge), params=params, body=body)

    def delete(self, node: str) -> GraphResponse:
        return self._call("DELETE", self._path(node, None))

    def refresh(self) -> GraphResponse:
        """``GET /refresh_access_token?grant_type=ig_refresh_token``, the token in the header
        only (A26; gate GI-1 tests that Meta accepts it there). Unversioned, as documented."""
        return self._call("GET", "/refresh_access_token", params={"grant_type": "ig_refresh_token"})

    def close(self) -> None:
        self._client.close()

    # -- plumbing -----------------------------------------------------------------------------

    def _path(self, node: str, edge: str | None) -> str:
        if not isinstance(node, str) or not _NODE.match(node):
            raise ValueError("graph node refused")
        if edge is not None and edge not in EDGES:
            raise ValueError("graph edge refused")
        return f"/{self._version}/{node}" + (f"/{edge}" if edge else "")

    def _call(
        self,
        method: Literal["GET", "POST", "DELETE"],
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> GraphResponse:
        query = dict(params or {})
        if any(not _PARAM.match(k) or k == "access_token" for k in query):
            raise ValueError("graph parameter refused")  # a token never rides in the URL
        stage: Literal["not_sent", "ambiguous"] | None = None
        try:
            response = self._client.request(
                method,
                f"{GRAPH_IG_ORIGIN}{path}",
                params=query,
                json=dict(body) if body is not None else None,
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            stage = "not_sent"
        except httpx.HTTPError:
            stage = "ambiguous"
        if stage is not None:
            raise GraphTransportError(stage)  # outside the handler: no chained error
        try:
            envelope = json.loads(response.content)
        except ValueError:
            envelope = None
        return GraphResponse(response.status_code, envelope if isinstance(envelope, dict) else None)
