"""Proposed A50, plan PN-3: outcomes by HTTP status (section 8; A19)."""

import pytest

from comms.core.errors import CommsError
from comms.transports.pinterest.classify import api_read, classify_write, read_refusal
from comms.transports.pinterest.http import GraphResponse, GraphTransportError, PinterestApi

from .fakes import TOKEN, FakePinterest


@pytest.mark.parametrize(
    ("status", "body", "outcome", "code"),
    [
        (200, {"id": "1100000000000000001"}, "SUCCEEDED", None),
        (201, {"id": 1100000000000000001}, "SUCCEEDED", None),
        (200, {"id": "../x"}, "OUTCOME_UNKNOWN", None),
        (200, {}, "OUTCOME_UNKNOWN", None),
        (400, {"code": 1, "message": "bad"}, "FAILED", "INVALID_ARGUMENT"),
        (401, {"code": 2, "message": "x"}, "FAILED", "CREDENTIAL"),
        (403, {"code": 3, "message": "PINNER_DATA_ACCESS_DENIED"}, "FAILED", "NOT_AUTHORIZED"),
        (404, {"code": 4, "message": "x"}, "FAILED", "NOT_FOUND"),
        (409, {"code": 5, "message": "x"}, "FAILED", "INVALID_ARGUMENT"),
        (429, {"code": 6, "message": "x"}, "FAILED", "RATE_LIMITED"),
        (418, {"code": 7, "message": "x"}, "OUTCOME_UNKNOWN", None),
        (500, {"code": 8, "message": "x"}, "OUTCOME_UNKNOWN", None),
        (200, None, "OUTCOME_UNKNOWN", None),
    ],
)
def test_every_status_maps_as_section_8_says(status, body, outcome, code):
    result = classify_write(GraphResponse(status, body))
    assert (result.outcome, result.code) == (outcome, code)
    if outcome == "SUCCEEDED":
        assert result.provider_ref == "1100000000000000001"
    assert "bad" not in repr(result) and "PINNER" not in repr(result)


def test_a_delete_succeeds_on_the_status_alone_and_a_media_id_is_a_ref():
    assert classify_write(GraphResponse(200, {"id": "1"}), ref_key=None).outcome == "SUCCEEDED"
    media = classify_write(GraphResponse(200, {"media_id": "777"}), ref_key="media_id")
    assert media.outcome == "SUCCEEDED" and media.provider_ref == "777"


def test_transport_failures():
    assert classify_write(GraphTransportError("not_sent")).code == "PROVIDER_UNAVAILABLE"
    assert classify_write(GraphTransportError("ambiguous")).outcome == "OUTCOME_UNKNOWN"


def test_reads_refuse_with_fixed_codes_and_a_rate_limit_carries_the_wait():
    assert read_refusal(GraphResponse(401, {})) == "NOT_AUTHORIZED"
    assert read_refusal(GraphResponse(403, {})) == "NOT_AUTHORIZED"
    assert read_refusal(GraphResponse(404, {})) == "NOT_FOUND"
    assert read_refusal(GraphResponse(400, {})) == "INVALID_ARGUMENT"
    assert read_refusal(GraphResponse(502, {})) == "PROVIDER_UNAVAILABLE"
    fake = FakePinterest()
    fake.headers["x-ratelimit-reset"] = "17"
    fake.route("GET", "/v5/boards", 429, {"code": 6, "message": "slow down " + TOKEN})

    class _Store:
        def get(self, item, version):
            return TOKEN.encode()

    api = PinterestApi(_Store(), purpose="pinterest-access-token.main", version=1,
                       transport=fake.transport())  # fmt: skip
    with pytest.raises(CommsError) as refused:
        api_read(api, lambda: api.get("boards"))
    assert refused.value.code == "RATE_LIMITED" and refused.value.retry_after == 17
    assert TOKEN not in str(refused.value)
