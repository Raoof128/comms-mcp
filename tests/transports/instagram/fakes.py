"""A recording fake of graph.instagram.com for the Instagram actor's tests (proposed A49)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

TOKEN = "IGAAcanaryTOKENcanaryTOKENcanaryTOKEN0123456789"  # the documented token shape
OTHER_TOKEN = "IGAAotherTOKENotherTOKENotherTOKENother98765"
USER_ID = "17841400000000001"
OTHER_USER_ID = "17841400000000002"
USERNAME = "raouf.studio"

Route = Callable[[httpx.Request], httpx.Response]


class FakeGraph:
    """Routes ``(method, path)`` to a JSON reply; records every request it is sent."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], Route] = {}
        self.user_id = {TOKEN: USER_ID, OTHER_TOKEN: OTHER_USER_ID}

    def route(self, method: str, path: str, status: int = 200, body: Any = None) -> None:
        self.routes[(method, path)] = lambda _request: httpx.Response(status, json=body)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key in self.routes:
            return self.routes[key](request)
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if request.url.path.endswith("/me"):
            if token not in self.user_id:
                return httpx.Response(400, json={"error": {"code": 190, "message": "bad"}})
            return httpx.Response(200, json={"user_id": self.user_id[token], "username": USERNAME})
        if request.url.path == "/refresh_access_token":
            return httpx.Response(
                200, json={"access_token": OTHER_TOKEN if token == TOKEN else TOKEN,
                           "token_type": "bearer", "expires_in": 5184000}
            )  # fmt: skip
        return httpx.Response(404, json={"error": {"code": 100, "message": "no route"}})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def sent(self) -> str:
        """Everything the fake saw on the wire except the Authorization header, as text."""
        parts = []
        for r in self.requests:
            headers = {k: v for k, v in r.headers.items() if k.lower() != "authorization"}
            parts.append(f"{r.method} {r.url} {json.dumps(headers)} {r.content.decode()}")
        return "\n".join(parts)
