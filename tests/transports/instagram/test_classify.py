"""Proposed A49, plan IG-3: Instagram outcomes by explicit table (section 8; A19)."""

import pytest

from comms.transports.instagram.classify import IG_CODES, classify_write, graph_read, read_refusal
from comms.transports.instagram.http import GraphResponse, GraphTransportError

ROWS = {
    (-2, 2207003): ("FAILED", "MEDIA_FETCH_TIMEOUT"),
    (-2, 2207020): ("FAILED", "CONTAINER_EXPIRED"),
    (-1, 2207001): ("OUTCOME_UNKNOWN", None),
    (-1, 2207032): ("FAILED", "CONTAINER_FAILED"),
    (-1, 2207053): ("FAILED", "CONTAINER_FAILED"),
    (1, 2207057): ("FAILED", "INVALID_ARGUMENT"),
    (4, 2207051): ("FAILED", "SPAM_FLAGGED"),
    (9, 2207042): ("FAILED", "PUBLISH_CAP"),
    (24, 2207006): ("FAILED", "NOT_FOUND"),
    (24, 2207008): ("FAILED", "CONTAINER_NOT_READY"),
    (25, 2207050): ("FAILED", "ACCOUNT_RESTRICTED"),
    (100, 2207023): ("FAILED", "INVALID_ARGUMENT"),
    (100, 2207028): ("FAILED", "INVALID_ARGUMENT"),
    (100, 2207040): ("FAILED", "INVALID_ARGUMENT"),
    (100, "INSTAGRAM_PLATFORM_API__INVALID_LOCATION_ID"): ("FAILED", "INVALID_ARGUMENT"),
    (352, 2207026): ("FAILED", "INVALID_ARGUMENT"),
    (9004, 2207052): ("FAILED", "MEDIA_FETCH_FAILED"),
    (9007, 2207027): ("FAILED", "CONTAINER_NOT_READY"),
    (36000, 2207004): ("FAILED", "INVALID_ARGUMENT"),
    (36001, 2207005): ("FAILED", "INVALID_ARGUMENT"),
    (36003, 2207009): ("FAILED", "INVALID_ARGUMENT"),
    (36004, 2207010): ("FAILED", "INVALID_ARGUMENT"),
    (190, 460): ("FAILED", "CREDENTIAL"),
    (4, None): ("FAILED", "RATE_LIMITED"),
    (17, 2446079): ("FAILED", "RATE_LIMITED"),
    (32, None): ("FAILED", "RATE_LIMITED"),
    (613, None): ("FAILED", "RATE_LIMITED"),
}


def _refused(code, subcode):
    error = {"code": code, **({"error_subcode": subcode} if subcode is not None else {})}
    return GraphResponse(400, {"error": error})


@pytest.mark.parametrize(("pair", "expected"), list(ROWS.items()))
def test_every_documented_row(pair, expected):
    result = classify_write(_refused(*pair))
    assert (result.outcome, result.code) == expected


def test_the_table_is_exactly_the_spec_rows():
    assert {k for k in IG_CODES if k[1] is not None} == {
        k for k in ROWS if k[1] is not None and k[0] not in (190, 17)
    }


@pytest.mark.parametrize(
    "outcome",
    [
        _refused(100, 9999999),  # an undocumented pair
        _refused(1, None),
        GraphResponse(500, {"error": {"code": 2}}),
        GraphResponse(400, None),  # not JSON
        GraphResponse(200, {"id": "../x"}),  # a success without a usable id
        GraphTransportError("ambiguous"),
    ],
)
def test_anything_unknown_is_outcome_unknown(outcome):
    assert classify_write(outcome).outcome == "OUTCOME_UNKNOWN"


def test_a_connection_never_made_is_a_refusal_before_acceptance():
    result = classify_write(GraphTransportError("not_sent"))
    assert (result.outcome, result.code) == ("FAILED", "PROVIDER_UNAVAILABLE")


def test_successes_carry_their_ref_or_need_success_true():
    created = classify_write(GraphResponse(200, {"id": "17800000000000001"}))
    assert (created.outcome, created.provider_ref) == ("SUCCEEDED", "17800000000000001")
    assert (
        classify_write(GraphResponse(200, {"success": True}), ref_key=None).outcome == "SUCCEEDED"
    )
    assert classify_write(GraphResponse(200, {"success": False}), ref_key=None).outcome == (
        "OUTCOME_UNKNOWN"
    )
    sent = classify_write(
        GraphResponse(200, {"recipient_id": "1", "message_id": "aWdfZAG1faXRlbToxOk0000"}),
        ref_key="message_id",
    )
    assert sent.outcome == "SUCCEEDED"


@pytest.mark.parametrize(
    ("code", "insights", "expected"),
    [
        (190, False, "NOT_AUTHORIZED"),
        (4, False, "RATE_LIMITED"),
        (100, False, "INVALID_ARGUMENT"),
        (24, False, "NOT_FOUND"),
        (10, True, "NOT_ENOUGH_DATA"),
        (1, True, "INVALID_ARGUMENT"),
        (10, False, "NOT_AUTHORIZED"),
        (77777, False, "PROVIDER_UNAVAILABLE"),
    ],
)
def test_read_refusals_are_fixed_codes(code, insights, expected):
    assert read_refusal(_refused(code, None), insights=insights) == expected


def test_a_read_success_is_its_object():
    assert graph_read(lambda: GraphResponse(200, {"data": []})) == {"data": []}
