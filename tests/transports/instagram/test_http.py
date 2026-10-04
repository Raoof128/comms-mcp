"""Proposed A49, plan IG-1: the pinned Instagram Graph client (D-I6, section 3)."""

import httpx
import pytest

from comms.transports.instagram.http import GRAPH_IG_ORIGIN, GraphIgApi, GraphTransportError
from comms.transports.net import EgressRefused
from comms.transports.whatsapp.cloud.http import GraphRefused

from .fakes import TOKEN, FakeGraph


class _Store:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def get(self, item: str, version: int) -> bytes:
        assert (item, version) == ("meta-ig-access-token.main", 1)
        return self.value


def _api(fake=None, transport=None, token=TOKEN):
    fake = fake or FakeGraph()
    api = GraphIgApi(
        _Store(token.encode()), purpose="meta-ig-access-token.main", version=1,
        transport=transport or fake.transport(),
    )  # fmt: skip
    return api, fake


def test_token_only_in_authorization_header():
    api, fake = _api()
    api.me(("user_id", "username"))
    api.get("17841400000000001", "media", params={"fields": "id", "limit": "25"})
    api.post("17841400000000009", params={"hide": "true"})
    api.delete("17841400000000009")
    api.refresh()
    assert len(fake.requests) == 5
    for request in fake.requests:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert "access_token" not in request.url.params and TOKEN not in str(request.url)
    assert TOKEN not in fake.sent()


def test_every_call_is_versioned_except_the_documented_refresh():
    api, fake = _api()
    api.me(("user_id",))
    api.refresh()
    assert fake.requests[0].url.path == "/v25.0/me"
    assert fake.requests[1].url.path == "/refresh_access_token"
    assert dict(fake.requests[1].url.params) == {"grant_type": "ig_refresh_token"}


def test_graph_ig_pins_origin():
    def escape(request):
        return httpx.Response(200, json={})

    api, _ = _api(transport=httpx.MockTransport(escape))
    api._client.base_url = "https://graph.facebook.com"
    with pytest.raises(EgressRefused):
        api._client.get("https://graph.facebook.com/v25.0/me")
    assert GRAPH_IG_ORIGIN == "https://graph.instagram.com"


@pytest.mark.parametrize(
    ("node", "edge"),
    [
        ("../me", None),
        ("me?x=1", None),
        ("1234", "debug_token"),
        ("abc", None),
        ("a" * 513, None),
        ("a.b/c" * 4, None),
    ],
)
def test_nodes_and_edges_are_closed(node, edge):
    api, fake = _api()
    with pytest.raises(ValueError):
        api.get(node, edge)
    assert fake.requests == []


def test_a_token_parameter_is_refused_before_any_request():
    api, fake = _api()
    with pytest.raises(ValueError):
        api.get("me", params={"access_token": TOKEN})
    assert fake.requests == []


def test_a_malformed_token_or_version_is_refused_and_not_echoed():
    with pytest.raises(GraphRefused) as refused:
        _api(token="short")
    assert "short" not in str(refused.value)
    with pytest.raises(GraphRefused):
        GraphIgApi(
            _Store(TOKEN.encode()), purpose="meta-ig-access-token.main", version=1,
            api_version="latest", transport=FakeGraph().transport(),
        )  # fmt: skip


def test_transport_errors_are_fixed_and_staged():
    def refuse(request):
        raise httpx.ConnectError("boom " + TOKEN, request=request)

    def cut(request):
        raise httpx.ReadTimeout("cut " + TOKEN, request=request)

    for transport, stage in ((refuse, "not_sent"), (cut, "ambiguous")):
        api, _ = _api(transport=httpx.MockTransport(transport))
        with pytest.raises(GraphTransportError) as raised:
            api.me(("user_id",))
        assert raised.value.stage == stage
        assert TOKEN not in str(raised.value) and raised.value.__cause__ is None
        assert raised.value.__suppress_context__ or raised.value.__context__ is None


def test_repr_redacts():
    api, _ = _api()
    assert TOKEN not in repr(api) and repr(api) == "GraphIgApi(<redacted>)"
