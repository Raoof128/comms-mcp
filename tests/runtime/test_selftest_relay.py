"""Spec A48 (Task R5): the selftest daemon's loopback route to a relay under ``wrangler dev``."""

import ast
from pathlib import Path

import httpx
import pytest

from comms.runtime.selftest_relay import LoopbackRelay
from comms.transports.net import EgressRefused

ROOT = Path(__file__).resolve().parents[2]


class Recorder(httpx.BaseTransport):
    def __init__(self):
        self.urls = []

    def handle_request(self, request):
        self.urls.append(str(request.url))
        return httpx.Response(200)


def _route(url: str) -> list[str]:
    transport = LoopbackRelay()
    transport._inner = Recorder()
    transport.handle_request(httpx.Request("POST", url))
    return transport._inner.urls


def test_https_loopback_becomes_plain_http_on_the_same_port():
    assert _route("https://127.0.0.1:8799/pull") == ["http://127.0.0.1:8799/pull"]


@pytest.mark.parametrize(
    "url",
    ["https://comms-relay.example.workers.dev/pull", "http://127.0.0.1:8799/pull",
     "https://localhost:8799/pull", "https://127.0.0.2:8799/pull"],
)  # fmt: skip
def test_anything_else_is_refused(url):
    with pytest.raises(EgressRefused):
        _route(url)


def test_only_the_selftest_builds_it():
    users = [
        p.relative_to(ROOT / "src" / "comms").as_posix()
        for p in (ROOT / "src" / "comms").rglob("*.py")
        if "__pycache__" not in p.parts and "selftest_relay" in p.read_text(encoding="utf-8")
        and p.name != "selftest_relay.py"
    ]  # fmt: skip
    assert users == ["runtime/selftest.py"]
    tree = ast.parse((ROOT / "src" / "comms" / "runtime" / "selftest.py").read_text("utf-8"))
    assert any(isinstance(n, ast.ImportFrom) and n.module == "comms.runtime.selftest_relay"
               for n in ast.walk(tree))  # fmt: skip
