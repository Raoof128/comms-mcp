"""The Meta contract oracle as an httpx transport (comms v0.3 Task C27; design §C.8).

WhatsVault's ``FakeGraph`` (fake_meta.py, ruling R-C27) holds the behaviour; this module only
turns an ``httpx.Request`` into its call and its answer into an ``httpx.Response``.
"""

from __future__ import annotations

import json

import httpx
from whatsvault.providers.fake_meta import FakeGraph

from comms.transports.whatsapp.cloud.http import API_VERSION

PHONE_ID = "106540352242922"
WABA_ID = "102290129340398"
APP_SECRET = b"fixture-app-secret-not-a-real-one"


def oracle(*, groups: str = "available") -> FakeGraph:
    return FakeGraph(
        phone_number_id=PHONE_ID, waba_id=WABA_ID, app_secret=APP_SECRET, groups=groups
    )


# Catalog amendment G8: the Groups API reads and join requests, the business profile and health
# status, answered here in the shapes Meta's reference documents (read 2026-09-26), because
# WhatsVault's FakeGraph (the subtree is not edited) predates them.
GROUP = "120363049891234567"


def _g8(request: httpx.Request) -> tuple[int, dict] | None:
    parts = request.url.path.strip("/").split("/")[1:]  # drop the version
    fields = request.url.params.get("fields", "")
    method = request.method
    if parts == [PHONE_ID] and fields == "health_status":
        return 200, {"health_status": {"can_send_message": "AVAILABLE", "entities": [
            {"entity_type": "PHONE_NUMBER", "id": PHONE_ID, "can_send_message": "AVAILABLE"},
            {"entity_type": "WABA", "id": WABA_ID, "can_send_message": "AVAILABLE"}]},
            "id": PHONE_ID}  # fmt: skip
    if parts == [PHONE_ID, "groups"] and method == "POST":
        # Meta's reference gives no synchronous body; pywa 4.5.0 (which follows Meta's Groups
        # reference) documents ``{"request_id": ...}``, the id the lifecycle webhook echoes (R-G9b)
        return 200, {"messaging_product": "whatsapp", "request_id": "REQ-oracle"}
    if parts == [PHONE_ID, "whatsapp_business_profile"]:
        return 200, {"data": [{"about": "Succulent specialists!", "vertical": "RETAIL",
                               "websites": ["https://example.org"]}]}  # fmt: skip
    if parts[:1] != [GROUP]:
        return None
    if parts == [GROUP] and method == "GET":
        return 200, {"messaging_product": "whatsapp", "id": GROUP, "subject": "Fixture group",
                     "participants": [{"wa_id": "61400000001"}],
                     "total_participant_count": "1"}  # fmt: skip
    if (
        parts == [GROUP]
        and method == "POST"
        and "multipart" in request.headers.get("content-type", "")
    ):
        # the group's picture (G8): Meta reads the part named ``profile_picture_file`` (a JPEG)
        # beside a ``messaging_product`` form field; any other part name is (#100) (R-G9b)
        body = request.content
        if (
            b'name="profile_picture_file"' not in body
            or b"Content-Type: image/jpeg" not in body
            or b'name="messaging_product"' not in body
        ):
            return 400, {"error": {"message": "(#100) Invalid parameter", "code": 100}}
        return 200, {"success": True}
    if parts == [GROUP] and method == "DELETE":
        return 200, {"success": True}
    if parts == [GROUP, "invite_link"] and method == "GET":
        return 200, {"messaging_product": "whatsapp",
                     "invite_link": "https://chat.whatsapp.com/Fixture"}  # fmt: skip
    if parts == [GROUP, "join_requests"]:
        if method == "GET":
            return 200, {"data": [{"join_request_id": "JR1", "wa_id": "61400000001",
                                   "creation_timestamp": "1790000000"}],
                         "paging": {"cursors": {"before": "b", "after": "a"}}}  # fmt: skip
        ids = json.loads(request.content)["join_requests"]
        key = "approved_join_requests" if method == "POST" else "rejected_join_requests"
        return 200, {"messaging_product": "whatsapp", key: ids}
    return None


def _as_fake_version(path: str) -> str:
    """G9 moved the adapter to Graph v26.0; WhatsVault's FakeGraph (the subtree is not edited)
    still routes v21.0. The contract under test is the path after the version, unchanged."""
    return path.replace(f"/{API_VERSION}/", f"/{FakeGraph.VERSION}/", 1)


def oracle_transport(graph: FakeGraph) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        answered = _g8(request)
        if answered is not None:
            status, answer = answered
            return httpx.Response(status, json=answer)
        query = dict(request.url.params)
        status, body, content_type = graph.handle(
            request.method,
            request.url.host,
            _as_fake_version(request.url.path),
            query,
            request.content,
            request.headers.get("content-type", ""),
        )
        if isinstance(body, bytes):
            return httpx.Response(status, content=body, headers={"content-type": content_type})
        return httpx.Response(
            status, content=json.dumps(body).encode(), headers={"content-type": content_type}
        )

    return httpx.MockTransport(handler)
