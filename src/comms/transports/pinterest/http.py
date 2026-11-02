"""The Pinterest REST API v5 client (proposed A50, D-P2, D-P6, section 3).

One pinned origin per account (``https://api.pinterest.com``, or the sandbox host for an account
marked ``sandbox``), one request per call, no retries, no redirects. The access token is read from
the secret store once, checked for shape (comms' own rule), and sent only in the ``Authorization``
header: never in a URL, a parameter, a log line, a ``repr`` or an error. Every path is one of a
closed set of resources, and every id joins a path only as digits. The rate-limit headers of the
last answer are kept as numbers (``RateLimit``), never the body.

``exchange_token`` is the one OAuth call (``POST /v5/oauth/token`` with ``Authorization: Basic``
over the app id and secret): the secret is read for that call and dropped, and the tokens it
answers are returned to the caller, never kept here. Transport errors are the shared
``GraphTransportError`` (``not_sent`` or ``ambiguous``) with no chained httpx exception.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlencode

import httpx

from comms.core.keys.secrets import SecretStore
from comms.transports.net import pinned_client
from comms.transports.whatsapp.cloud.http import GraphRefused, GraphResponse, GraphTransportError

__all__ = [
    "AUTHORIZE_URL",
    "PINTEREST_ORIGIN",
    "RESOURCES",
    "SANDBOX_ORIGIN",
    "SCOPES",
    "GraphRefused",
    "GraphResponse",
    "GraphTransportError",
    "PinterestApi",
    "RateLimit",
    "TokenGrant",
    "TokenRefused",
    "authorize_url",
    "exchange_token",
]

PINTEREST_ORIGIN = "https://api.pinterest.com"
SANDBOX_ORIGIN = "https://api-sandbox.pinterest.com"
AUTHORIZE_URL = "https://www.pinterest.com/oauth/"
SCOPES = ("boards:read", "boards:write", "pins:read", "pins:write", "user_accounts:read")
_V5 = "/v5"
_TOKEN = re.compile(r"\A[A-Za-z0-9_.\-]{20,2048}\Z")
_SECRET = re.compile(r"\A[\x21-\x7e]{16,256}\Z")  # printable ASCII, no whitespace
_APP_ID = re.compile(r"\A[0-9]{1,32}\Z")
_ID = re.compile(r"\A[0-9]{1,24}\Z")
_PARAM = re.compile(r"\A[a-z_]{1,32}\Z")
_CODE = re.compile(r"\A[A-Za-z0-9_.\-]{8,2048}\Z")
# The closed set of resources: the key is the resource name, the value whether it takes an id.
RESOURCES: Mapping[str, bool] = {
    "user_account": False,
    "user_account/analytics": False,
    "boards": False,
    "boards/{id}": True,
    "boards/{id}/pins": True,
    "pins": False,
    "pins/{id}": True,
    "pins/{id}/analytics": True,
    "media": False,
    "media/{id}": True,
}
_TIMEOUT = 15.0  # D-P13: at most three calls inside the proxy's 30 s


@dataclass(frozen=True)
class RateLimit:
    """What Pinterest's ``x-ratelimit-*`` headers said on the last answer: numbers only."""

    limit: int | None
    remaining: int | None
    reset: int | None


@dataclass(frozen=True)
class TokenGrant:
    """What ``oauth/token`` answered. Values never appear in a ``repr``."""

    access_token: bytes = field(repr=False)
    access_expires_in: int
    refresh_token: bytes | None = field(repr=False)
    refresh_expires_in: int | None


class TokenRefused(Exception):
    """Pinterest did not grant tokens, or answered something that is not a grant. Fixed
    messages; never a code, a token or Pinterest's text."""


def _number(value: str | None) -> int | None:
    if value is None:
        return None
    head = value.split(",", 1)[0].strip()  # ``100, 100;w=1, 1000;w=60``: the first number
    return int(head) if head.isdigit() and len(head) <= 12 else None


def authorize_url(app_id: str, redirect_uri: str, state: str) -> str:
    """The owner's authorization URL (D-P4): the five scopes, ``response_type=code``."""
    if not _APP_ID.match(app_id):
        raise ValueError("app_id refused")
    query = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "state": state,
    }
    return AUTHORIZE_URL + "?" + urlencode(query)


def exchange_token(
    app_id: str,
    app_secret: bytes,
    *,
    code: str | None = None,
    refresh_token: bytes | None = None,
    redirect_uri: str | None = None,
    sandbox: bool = False,
    timeout: float = _TIMEOUT,
    transport: httpx.BaseTransport | None = None,
) -> TokenGrant:
    """One ``POST /v5/oauth/token``: an authorization code (with its redirect URI), or a refresh
    token. ``TokenRefused`` on any answer that is not a grant; ``GraphTransportError`` on none."""
    try:
        secret = app_secret.decode("ascii")
    except UnicodeDecodeError:
        secret = ""
    if not _APP_ID.match(app_id) or not _SECRET.match(secret):
        raise GraphRefused("the app credentials are malformed")
    if (code is None) == (refresh_token is None):
        raise ValueError("one of a code or a refresh token")
    form: dict[str, str] = {"continuous_refresh": "true"}
    if code is not None:
        if not _CODE.match(code) or not isinstance(redirect_uri, str) or not redirect_uri:
            raise GraphRefused("the authorization code is malformed")
        form.update(grant_type="authorization_code", code=code, redirect_uri=redirect_uri)
    else:
        assert refresh_token is not None
        try:
            refresh = refresh_token.decode("ascii")
        except UnicodeDecodeError:
            refresh = ""
        if not _TOKEN.match(refresh):
            raise GraphRefused("the refresh token is malformed")
        form.update(grant_type="refresh_token", refresh_token=refresh)
    basic = base64.b64encode(f"{app_id}:{secret}".encode("ascii")).decode("ascii")
    origin = SANDBOX_ORIGIN if sandbox else PINTEREST_ORIGIN
    client = pinned_client(origin, timeout=timeout, transport=transport)
    try:
        response = _request(
            client, "POST", f"{origin}{_V5}/oauth/token", data=form,
            headers={"Authorization": f"Basic {basic}"},
        )  # fmt: skip
    finally:
        client.close()
    return _grant(response)


def _grant(response: GraphResponse) -> TokenGrant:
    body = response.envelope or {}
    access, expires = body.get("access_token"), body.get("expires_in")
    refresh, refresh_expires = body.get("refresh_token"), body.get("refresh_token_expires_in")
    if (
        response.http_status not in (200, 201)
        or not isinstance(access, str)
        or not _TOKEN.match(access)
        or isinstance(expires, bool)
        or not isinstance(expires, int)
        or not 0 < expires <= 366 * 86400
    ):
        raise TokenRefused("Pinterest did not grant a token")
    if refresh is not None and (not isinstance(refresh, str) or not _TOKEN.match(refresh)):
        raise TokenRefused("Pinterest answered a malformed refresh token")
    if refresh_expires is not None and (
        isinstance(refresh_expires, bool)
        or not isinstance(refresh_expires, int)
        or not 0 < refresh_expires <= 366 * 86400
    ):
        refresh_expires = None
    return TokenGrant(
        access.encode("ascii"),
        expires,
        None if refresh is None else refresh.encode("ascii"),
        refresh_expires,
    )


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    params: Mapping[str, str] | None = None,
    body: Mapping[str, Any] | None = None,
    data: Mapping[str, str] | None = None,
    headers: Mapping[str, str],
) -> GraphResponse:
    stage: Literal["not_sent", "ambiguous"] | None = None
    try:
        response = client.request(
            method,
            url,
            params=dict(params or {}),
            json=dict(body) if body is not None else None,
            data=dict(data) if data is not None else None,
            headers=dict(headers),
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


class PinterestApi:
    def __init__(
        self,
        secrets: SecretStore,
        *,
        purpose: str,
        version: int,
        sandbox: bool = False,
        timeout: float = _TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        try:
            token = secrets.get(purpose, version).decode("ascii")
        except UnicodeDecodeError:
            token = ""
        if not _TOKEN.match(token):
            raise GraphRefused("the access token is malformed")
        self._token = token
        self.origin = SANDBOX_ORIGIN if sandbox else PINTEREST_ORIGIN
        self.sandbox = sandbox
        self._client = pinned_client(self.origin, timeout=timeout, transport=transport)
        self.last_rate_limit: RateLimit | None = None

    def __repr__(self) -> str:
        return "PinterestApi(<redacted>)"

    # -- the calls ----------------------------------------------------------------------------

    def me(self) -> GraphResponse:
        return self.get("user_account")

    def get(
        self, resource: str, ident: str | None = None, *, params: Mapping[str, str] | None = None
    ) -> GraphResponse:
        return self._call("GET", self._path(resource, ident), params=params)

    def post(
        self, resource: str, ident: str | None = None, *, body: Mapping[str, Any] | None = None
    ) -> GraphResponse:
        return self._call("POST", self._path(resource, ident), body=body)

    def patch(self, resource: str, ident: str, *, body: Mapping[str, Any]) -> GraphResponse:
        return self._call("PATCH", self._path(resource, ident), body=body)

    def delete(self, resource: str, ident: str) -> GraphResponse:
        return self._call("DELETE", self._path(resource, ident))

    def close(self) -> None:
        self._client.close()

    # -- plumbing -----------------------------------------------------------------------------

    @staticmethod
    def _path(resource: str, ident: str | None) -> str:
        takes_id = RESOURCES.get(resource)
        if takes_id is None or takes_id != (ident is not None):
            raise ValueError("pinterest resource refused")
        if ident is not None and (not isinstance(ident, str) or not _ID.match(ident)):
            raise ValueError("pinterest id refused")
        return _V5 + "/" + (resource.replace("{id}", ident) if ident is not None else resource)

    def _call(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> GraphResponse:
        query = dict(params or {})
        if any(not _PARAM.match(k) or k == "access_token" for k in query):
            raise ValueError("pinterest parameter refused")  # a token never rides in the URL
        stage: Literal["not_sent", "ambiguous"] | None = None
        try:
            response = self._client.request(
                method,
                f"{self.origin}{path}",
                params=query,
                json=dict(body) if body is not None else None,
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            stage = "not_sent"
        except httpx.HTTPError:
            stage = "ambiguous"
        if stage is not None:
            raise GraphTransportError(stage)
        self.last_rate_limit = RateLimit(
            _number(response.headers.get("x-ratelimit-limit")),
            _number(response.headers.get("x-ratelimit-remaining")),
            _number(response.headers.get("x-ratelimit-reset")),
        )
        try:
            envelope = json.loads(response.content) if response.content else {}
        except ValueError:
            envelope = None
        return GraphResponse(response.status_code, envelope if isinstance(envelope, dict) else None)
