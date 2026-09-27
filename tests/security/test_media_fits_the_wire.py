"""A47 (H6, found by driving the real daemon): every file-carrying tool call fits the wire.

A tool call crosses one HTTP ``/mcp`` request (``max_request_bytes`` 65,536) or one admin-socket
frame for the stdio proxy (``MAX_FRAME_BYTES`` 64 KiB), and so does its answer. G8 set a chunk
at 48 KiB raw, whose base64 alone is 65,536 bytes, and allowed 512 KiB inline: neither could
ever cross. This test builds the largest request and answer each schema allows and requires
both to fit, with room for the envelope, on both routes.
"""

import inspect
import json

from comms.mcp.catalog import TOOL_CATALOG
from comms.mcp.http import build_http_app
from comms.services.uploads import CHUNK_MAX, INLINE_MAX
from comms.transports.telegram.ipc.framing import MAX_FRAME_BYTES

BY_NAME = {spec.name: spec for spec in TOOL_CATALOG}
HTTP_MAX = inspect.signature(build_http_app).parameters["max_request_bytes"].default
WIRE = min(HTTP_MAX, MAX_FRAME_BYTES)
B64 = (CHUNK_MAX + 2) // 3 * 4


def _request(name, arguments):
    """The JSON-RPC envelope an MCP client sends, with a bearer-lease-sized id."""
    return json.dumps({"jsonrpc": "2.0", "id": "x" * 64, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}}).encode()  # fmt: skip


def _largest_b64(spec):
    return spec.input_schema["properties"]["data_b64"]["maxLength"]


def test_the_raw_limits_are_one_and_fit():
    assert CHUNK_MAX == INLINE_MAX == 32 * 1024
    assert B64 < WIRE - 4096  # room for the envelope and every other argument


def test_every_data_b64_input_is_bounded_to_fit():
    carriers = [s for s in TOOL_CATALOG if "data_b64" in s.input_schema.get("properties", {})]
    assert {s.name for s in carriers} == {
        "comms_media_stage_chunk", "comms_media_upload", "comms_group_info_set_photo",
        "comms_message_send_media"}  # fmt: skip
    for spec in carriers:
        assert _largest_b64(spec) == B64, spec.name
        biggest = {"data_b64": "A" * _largest_b64(spec), "mime": "m" * 128,
                   "upload": "upl_" + "a" * 26, "seq": 2**31, "request_id": "req_" + "a" * 26,
                   "group": "grp_" + "a" * 26, "kind": "document", "caption": "c" * 1024,
                   "actor": "telegram_user"}  # fmt: skip
        known = {k: v for k, v in biggest.items() if k in spec.input_schema["properties"]}
        assert len(_request(spec.name, known)) < WIRE, spec.name


def test_a_download_slice_and_its_answer_fit():
    spec = BY_NAME["comms_media_download"]
    assert spec.input_schema["properties"]["length"]["maximum"] == CHUNK_MAX
    answer = {"jsonrpc": "2.0", "id": "x" * 64, "result": {"structuredContent": {
        "media": "med_" + "a" * 26, "mime": "m" * 128, "size": 16 * 1024 * 1024,
        "sha256": "f" * 64, "offset": 16 * 1024 * 1024, "data_b64": "A" * B64,
        "complete": False}, "content": [], "isError": False}}  # fmt: skip
    assert spec.output_schema["properties"]["data_b64"]["maxLength"] == B64
    assert len(json.dumps(answer).encode()) < WIRE
