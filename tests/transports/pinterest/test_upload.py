"""Proposed A50, plan PN-1: the one upload of a video to Pinterest's signed URL (D-P6, D-P8)."""

import httpx
import pytest

from comms.transports.net import EgressRefused
from comms.transports.pinterest.upload import check_target, upload_video

from .fakes import UPLOAD_HOST, FakePinterest

FIELDS = {"key": "uploads/1", "policy": "cG9saWN5", "x-amz-signature": "0" * 64,
          "Content-Type": "multipart/form-data"}  # fmt: skip


def test_the_upload_is_one_multipart_post_without_a_bearer():
    fake = FakePinterest()
    url, fields = check_target(UPLOAD_HOST, FIELDS)
    assert upload_video(url, fields, b"\x00\x00\x00 ftypmp42", "video/mp4",
                        transport=fake.transport()) == "ok"  # fmt: skip
    (request,) = fake.requests
    assert request.url == UPLOAD_HOST and "authorization" not in request.headers
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    for name, value in FIELDS.items():
        assert f'name="{name}"'.encode() in body and value.encode() in body
    assert b'filename="video.mp4"' in body and b"ftypmp42" in body


def test_a_4xx_is_refused_and_a_5xx_is_unknown():
    fake = FakePinterest()
    url, fields = check_target(UPLOAD_HOST, FIELDS)
    fake.upload_status = 403
    assert upload_video(url, fields, b"x", "video/mp4", transport=fake.transport()) == "refused"
    fake.upload_status = 500
    assert upload_video(url, fields, b"x", "video/mp4", transport=fake.transport()) == "unknown"

    def cut(request):
        raise httpx.ReadTimeout("cut", request=request)

    assert (
        upload_video(url, fields, b"x", "video/mp4", transport=httpx.MockTransport(cut))
        == "unknown"
    )


@pytest.mark.parametrize(
    ("url", "fields"),
    [
        ("https://evil.example.com/", FIELDS),
        ("http://pinterest-media-upload.s3-accelerate.amazonaws.com/", FIELDS),
        ("https://user@pinterest-media-upload.s3-accelerate.amazonaws.com/", FIELDS),
        ("https://amazonaws.com.evil.example/", FIELDS),
        (UPLOAD_HOST, {}),
        (UPLOAD_HOST, {"bad name": "x"}),
        (UPLOAD_HOST, {"key": 1}),
        (UPLOAD_HOST, {f"f{i}": "x" for i in range(40)}),
        (None, FIELDS),
    ],
)
def test_a_target_outside_the_contract_is_refused_before_any_request(url, fields):
    with pytest.raises(ValueError):
        check_target(url, fields)


def test_the_upload_client_never_leaves_the_suffix_even_if_handed_a_url():
    fake = FakePinterest()
    with pytest.raises(EgressRefused):
        upload_video("https://evil.example.com/", FIELDS, b"x", "video/mp4",
                     transport=fake.transport())  # fmt: skip
    assert fake.requests == []
    with pytest.raises(ValueError):
        upload_video(UPLOAD_HOST, FIELDS, b"x", "image/png", transport=fake.transport())
