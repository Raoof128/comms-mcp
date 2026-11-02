"""Proposed A50, plan PN-1: the pinned Pinterest client and the token exchange (D-P2, D-P4,
D-P6, section 3)."""

import base64

import httpx
import pytest

from comms.transports.net import EgressRefused
from comms.transports.pinterest.http import (
    PINTEREST_ORIGIN,
    SANDBOX_ORIGIN,
    GraphRefused,
    GraphTransportError,
    PinterestApi,
    TokenRefused,
    authorize_url,
    exchange_token,
)

from .fakes import APP_ID, APP_SECRET, CODE, REFRESH, TOKEN, FakePinterest


class _Store:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def get(self, item: str, version: int) -> bytes:
        assert (item, version) == ("pinterest-access-token.main", 1)
        return self.value


def _api(fake=None, transport=None, token=TOKEN, sandbox=False):
    fake = fake or FakePinterest()
    api = PinterestApi(
        _Store(token.encode()), purpose="pinterest-access-token.main", version=1,
        sandbox=sandbox, transport=transport or fake.transport(),
    )  # fmt: skip
    return api, fake


def test_token_only_in_authorization_header_and_every_path_is_v5():
    api, fake = _api()
    api.me()
    api.get("boards", params={"page_size": "25", "privacy": "ALL"})
    api.get("pins/{id}", "123")
    api.post("pins", body={"board_id": "1"})
    api.patch("pins/{id}", "123", body={"title": "t"})
    api.delete("pins/{id}", "123")
    assert [r.url.path for r in fake.requests] == [
        "/v5/user_account", "/v5/boards", "/v5/pins/123", "/v5/pins", "/v5/pins/123", "/v5/pins/123"
    ]  # fmt: skip
    for request in fake.requests:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert "access_token" not in request.url.params and TOKEN not in str(request.url)
    assert TOKEN not in fake.sent()


def test_the_rate_limit_headers_are_kept_as_numbers():
    api, _fake = _api()
    api.me()
    assert (api.last_rate_limit.limit, api.last_rate_limit.remaining, api.last_rate_limit.reset) == (
        100, 99, 1
    )  # fmt: skip


def test_pins_origin_and_the_sandbox_twin():
    def escape(request):
        return httpx.Response(200, json={})

    api, _ = _api(transport=httpx.MockTransport(escape))
    with pytest.raises(EgressRefused):
        api._client.get("https://api-sandbox.pinterest.com/v5/user_account")
    sandbox, fake = _api(sandbox=True)
    sandbox.me()
    assert fake.requests[0].url.host == "api-sandbox.pinterest.com"
    assert (PINTEREST_ORIGIN, SANDBOX_ORIGIN) == (
        "https://api.pinterest.com", "https://api-sandbox.pinterest.com"
    )  # fmt: skip


@pytest.mark.parametrize(
    ("resource", "ident"),
    [
        ("../user_account", None),
        ("boards", "123"),  # a resource without an id, given one
        ("pins/{id}", None),  # a resource with an id, given none
        ("pins/{id}", "abc"),
        ("pins/{id}", "1" * 25),
        ("ad_accounts", None),
        ("oauth/token", None),
    ],
)
def test_resources_and_ids_are_closed(resource, ident):
    api, fake = _api()
    with pytest.raises(ValueError):
        api.get(resource, ident)
    assert fake.requests == []


def test_a_token_parameter_is_refused_before_any_request():
    api, fake = _api()
    with pytest.raises(ValueError):
        api.get("boards", params={"access_token": TOKEN})
    assert fake.requests == []


def test_a_malformed_token_is_refused_and_not_echoed():
    with pytest.raises(GraphRefused) as refused:
        _api(token="short")
    assert "short" not in str(refused.value)


def test_transport_errors_are_fixed_and_staged():
    def refuse(request):
        raise httpx.ConnectError("boom " + TOKEN, request=request)

    def cut(request):
        raise httpx.ReadTimeout("cut " + TOKEN, request=request)

    for transport, stage in ((refuse, "not_sent"), (cut, "ambiguous")):
        api, _ = _api(transport=httpx.MockTransport(transport))
        with pytest.raises(GraphTransportError) as raised:
            api.me()
        assert raised.value.stage == stage
        assert TOKEN not in str(raised.value) and raised.value.__cause__ is None


def test_repr_redacts():
    api, _ = _api()
    assert TOKEN not in repr(api) and repr(api) == "PinterestApi(<redacted>)"


# -- the token exchange --------------------------------------------------------------------------


def test_exchange_sends_basic_auth_and_the_documented_form():
    fake = FakePinterest()
    grant = exchange_token(
        APP_ID, APP_SECRET.encode(), code=CODE, redirect_uri="https://example.com/cb",
        transport=fake.transport(),
    )  # fmt: skip
    (request,) = fake.requests
    assert request.url == "https://api.pinterest.com/v5/oauth/token"
    basic = base64.b64encode(f"{APP_ID}:{APP_SECRET}".encode()).decode()
    assert request.headers["authorization"] == f"Basic {basic}"
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    form = dict(httpx.QueryParams(request.content.decode()))
    assert form == {"continuous_refresh": "true", "grant_type": "authorization_code",
                    "code": CODE, "redirect_uri": "https://example.com/cb"}  # fmt: skip
    assert grant.access_token == TOKEN.encode() and grant.refresh_token == REFRESH.encode()
    assert (grant.access_expires_in, grant.refresh_expires_in) == (2592000, 5184000)
    assert TOKEN not in repr(grant) and REFRESH not in repr(grant)


def test_refresh_sends_the_refresh_grant_and_keeps_a_missing_refresh_token():
    fake = FakePinterest()
    fake.grant = {"access_token": TOKEN, "expires_in": 2592000, "token_type": "bearer"}
    grant = exchange_token(
        APP_ID, APP_SECRET.encode(), refresh_token=REFRESH.encode(), transport=fake.transport()
    )
    form = dict(httpx.QueryParams(fake.requests[0].content.decode()))
    assert form == {"continuous_refresh": "true", "grant_type": "refresh_token",
                    "refresh_token": REFRESH}  # fmt: skip
    assert grant.refresh_token is None and grant.refresh_expires_in is None


def test_exchange_refuses_a_non_grant_without_echoing_it():
    fake = FakePinterest()
    fake.grant = {"access_token": "x", "expires_in": 1, "token_type": "bearer"}
    with pytest.raises(TokenRefused) as refused:
        exchange_token(APP_ID, APP_SECRET.encode(), code=CODE, redirect_uri="https://e.com/",
                       transport=fake.transport())  # fmt: skip
    assert APP_SECRET not in str(refused.value)
    with pytest.raises(GraphRefused):
        exchange_token("abc", APP_SECRET.encode(), code=CODE, redirect_uri="https://e.com/")
    with pytest.raises(GraphRefused):
        exchange_token(APP_ID, b"short", code=CODE, redirect_uri="https://e.com/")
    with pytest.raises(ValueError):
        exchange_token(APP_ID, APP_SECRET.encode())


def test_the_authorize_url_names_the_five_scopes():
    url = authorize_url(APP_ID, "https://example.com/cb", "st4te")
    assert url.startswith("https://www.pinterest.com/oauth/?client_id=1234567&")
    assert "response_type=code" in url and "state=st4te" in url
    assert (
        "boards%3Aread%2Cboards%3Awrite%2Cpins%3Aread%2Cpins%3Awrite%2Cuser_accounts%3Aread" in url
    )
    assert "secret" not in url
