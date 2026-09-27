"""Spec A48 (Task R3): the relay client — one pinned origin, signed, bounded, fixed errors."""

import httpx
import pytest

from comms.transports.net import EgressRefused
from comms.transports.whatsapp.relay_client import RelayClient, RelayRefused, RelayUnavailable

ORIGIN = "https://comms-relay.example.workers.dev"
KEY = b"k" * 32


def _client(handler):
    return RelayClient(ORIGIN, KEY, transport=httpx.MockTransport(handler))


def test_only_an_https_origin_is_accepted():
    for bad in ("http://comms-relay.example.workers.dev", ORIGIN + "/pull", "ftp://x"):
        with pytest.raises(ValueError):
            RelayClient(bad, KEY)
    with pytest.raises(ValueError, match="32 bytes"):
        RelayClient(ORIGIN, b"short")


def test_a_redirect_is_not_followed():
    client = _client(lambda r: httpx.Response(302, headers={"location": "https://evil.example/"}))
    with pytest.raises(RelayRefused) as refused:
        client.pull(0)
    assert refused.value.status == 302


def test_another_host_is_refused():
    client = RelayClient(ORIGIN, KEY, transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(EgressRefused):
        client._client.post("https://evil.example/pull")


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b'{"rows": [], "purged_through": 0, "depth": 0}',
        b'{"rows": [], "purged_through": -1, "depth": 0, "oldest_received_at": null}',
        b'{"rows": [{"seq": 1}], "purged_through": 0, "depth": 1, "oldest_received_at": 1}',
        b'{"rows": [], "rows": [], "purged_through": 0, "depth": 0, "oldest_received_at": null}',
    ],
)
def test_a_malformed_page_is_unavailable_not_a_crash(payload):
    client = _client(lambda r: httpx.Response(200, content=payload))
    with pytest.raises(RelayUnavailable, match="malformed"):
        client.pull(0)


def test_an_oversized_answer_is_refused():
    client = _client(lambda r: httpx.Response(200, content=b"x" * (4 * 1024 * 1024 + 1)))
    with pytest.raises(RelayUnavailable, match="response"):
        client.pull(0)


def test_errors_and_repr_carry_no_url_or_key():
    def down(request):
        raise httpx.ConnectError("boom " + ORIGIN)

    with pytest.raises(RelayUnavailable) as unavailable:
        _client(down).pull(0)
    text = str(unavailable.value) + repr(_client(down))
    assert "comms-relay" not in text and KEY.hex() not in text
