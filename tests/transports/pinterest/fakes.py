"""A recording fake of api.pinterest.com and the upload host for the Pinterest actor's tests
(proposed A50)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

TOKEN = "pina_canaryACCESScanaryACCESScanaryACCESS0123"  # the documented token shape
OTHER_TOKEN = "pina_otherACCESSotherACCESSotherACCESS98765"
REFRESH = "pinr_canaryREFRESHcanaryREFRESHcanaryREFRESH01"
OTHER_REFRESH = "pinr_otherREFRESHotherREFRESHotherREFRESH0202"
APP_SECRET = "canaryAPPSECRETcanaryAPPSECRET01"
APP_ID = "1234567"
CODE = "canaryCODEcanaryCODE0001"
USER_ID = "900000000000000001"
OTHER_USER_ID = "900000000000000002"
USERNAME = "raouf.pinner"
UPLOAD_HOST = "https://pinterest-media-upload.s3-accelerate.amazonaws.com/"

Route = Callable[[httpx.Request], httpx.Response]


class FakePinterest:
    """Routes ``(method, path)`` to a JSON reply; records every request it is sent. The upload
    host answers 204 to a POST without a bearer; the token endpoint grants documented tokens."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], Route] = {}
        self.user_id = {TOKEN: USER_ID, OTHER_TOKEN: OTHER_USER_ID}
        self.grant: dict[str, Any] = {
            "access_token": TOKEN,
            "refresh_token": REFRESH,
            "response_type": "authorization_code",
            "token_type": "bearer",
            "expires_in": 2592000,
            "refresh_token_expires_in": 5184000,
            "scope": "boards:read boards:write pins:read pins:write user_accounts:read",
        }
        self.upload_status = 204
        self.headers = {
            "x-ratelimit-limit": "100, 100;w=1, 1000;w=60",
            "x-ratelimit-remaining": "99",
            "x-ratelimit-reset": "1",
        }

    def route(self, method: str, path: str, status: int = 200, body: Any = None) -> None:
        self.routes[(method, path)] = lambda _request: httpx.Response(
            status, json=body, headers=self.headers
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host.endswith("amazonaws.com"):
            if "authorization" in request.headers:
                return httpx.Response(403, text="no bearer here")
            return httpx.Response(self.upload_status)
        key = (request.method, request.url.path)
        if key in self.routes:
            return self.routes[key](request)
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if request.url.path == "/v5/oauth/token":
            if not request.headers.get("authorization", "").startswith("Basic "):
                return httpx.Response(401, json={"code": 2, "message": "no app"})
            return httpx.Response(200, json=self.grant, headers=self.headers)
        if request.url.path == "/v5/user_account":
            if token not in self.user_id:
                return httpx.Response(401, json={"code": 2, "message": "bad token"})
            return httpx.Response(
                200,
                json={"id": self.user_id[token], "username": USERNAME, "account_type": "BUSINESS"},
                headers=self.headers,
            )
        return httpx.Response(404, json={"code": 2, "message": "no route"})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def sent(self) -> str:
        """Everything the fake saw on the wire except the Authorization header, as text."""
        parts = []
        for r in self.requests:
            headers = {k: v for k, v in r.headers.items() if k.lower() != "authorization"}
            parts.append(
                f"{r.method} {r.url} {json.dumps(headers)} {r.content[:4096].decode('latin-1')}"
            )
        return "\n".join(parts)
