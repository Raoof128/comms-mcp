"""``comms selftest-daemon``: the real daemon over deterministic, always-accepting providers.

D39-PRE Task E6 (the injected seam; no test flag in a production path). The daemon, its
state, its listeners, its admin socket and its workers are the production ones; only the
adapter factory differs. Every provider here is local and deterministic:

- admin writes go through the real adapters' ``validate`` (so a malformed request is still
  refused exactly as in production) and then succeed with a synthetic provider ref;
- every capability is ``AVAILABLE``;
- context sources serve fixed synthetic pages under the provenance each actor really has;
- campaign delivery accepts every job;
- the bot actor is the real Bot API poller and local context over a scripted HTTP transport
  (three messages in the chat ``channel:1234567890``, served by the stored offset, so a restart
  never re-ingests), so group context reads are ``telegram_local`` from the real retained
  updates (D39-PRE E11c);
- with a webhook port configured, the real webhook pipeline (inbox, worker, the comms archive,
  the ingress) runs with fixed selftest secrets;
- proposed A49: with Instagram accounts in comms.json, the real Instagram adapters (accounts,
  capability, the admin adapter, the publishing ledger) and the operator commands run over a
  scripted graph.instagram.com (``_InstagramGraph``): one public account that has one post with
  one comment, one live Story, one DM thread with a message an hour old, and containers that
  finish at once.

Nothing here opens a socket beyond the daemon's own listeners, or reads a credential; any other
provider transport that is touched fails loudly (``_Unreachable``).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from comms.core import timeutil
from comms.core.canonical import jcs_dumps
from comms.core.delivery.transport import (
    DeliveryIntent,
    DeliveryResult,
    FrozenDelivery,
    PreparedPayload,
    ResultKind,
    Skip,
)
from comms.core.providers.capability import Capability as C
from comms.core.providers.capability import CapabilityState as S
from comms.core.providers.protocols import (
    CapabilitySnapshot,
    ContextPage,
    ContextQuery,
    ProviderResult,
    ProviderTarget,
    SemanticOperation,
)
from comms.runtime.adapters import Adapters, instagram_adapters
from comms.runtime.relay import Collector
from comms.runtime.selftest_relay import LoopbackRelay
from comms.runtime.settings import DaemonSettings
from comms.runtime.state import CommsState
from comms.transports.telegram.bot.admin import BotAdmin
from comms.transports.telegram.bot.context import BotContext
from comms.transports.telegram.bot.http import BotApi
from comms.transports.telegram.bot.media import BotMedia
from comms.transports.telegram.bot.updates import BotPoller
from comms.transports.telegram.peers import marked_chat_id
from comms.transports.telegram.user.admin import UserAdmin
from comms.transports.whatsapp.cloud.groups import WhatsAppAdmin
from comms.transports.whatsapp.numbers import e164
from comms.transports.whatsapp.relay_client import RelayClient
from comms.transports.whatsapp.webhooks.archive import ArchiveContext, CommsArchive
from comms.transports.whatsapp.webhooks.inbox import Inbox
from comms.transports.whatsapp.webhooks.ingress import WebhookIngress
from comms.transports.whatsapp.webhooks.worker import WebhookWorker

__all__ = ["selftest_adapters"]

_ACTORS = ("telegram_bot", "telegram_user", "whatsapp_cloud")
_serial = itertools.count(1)


class _Unreachable:
    """A provider transport the selftest never reaches: any use is a defect."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError("selftest: a provider transport was reached")


def _no_run(coroutine: Coroutine[Any, Any, Any]) -> Any:
    coroutine.close()
    raise AssertionError("selftest: an MTProto call was attempted")


def _created(capability: C) -> str | None:
    n = next(_serial)
    return {
        C.INVITE_CREATE: f"https://t.me/+Selftest{n:06d}",
        C.GROUP_INVITE_RESET: f"https://chat.whatsapp.com/Selftest{n:06d}",
        C.TOPIC_CREATE: str(n),
        C.MESSAGE_SEND: str(1000 + n),
        C.MESSAGE_SEND_MEDIA: str(2000 + n),  # A47: a media send names its new message too
        C.MESSAGE_FORWARD: str(3000 + n),
        C.GROUP_CREATE: str(-(10**12 + n)),  # a new supergroup's marked id
        C.MEDIA_UPLOAD: f"upload:photo:{n}:1:00",  # the user account's uploaded file
        C.TEMPLATE_CREATE: str(9_000_000 + n),
    }.get(capability)


class _Accepting:
    """Real validation, then success."""

    def __init__(self, validator: Any) -> None:
        self._validator = validator

    def validate(self, op: SemanticOperation, target: ProviderTarget) -> None:
        self._validator.validate(op, target)

    def invoke(self, op: SemanticOperation, target: ProviderTarget, key: str) -> ProviderResult:
        return ProviderResult("SUCCEEDED", None, provider_ref=_created(op.capability))


class _Available:
    def snapshot(self, actor: str, target: ProviderTarget) -> CapabilitySnapshot:
        stamp = timeutil.iso(datetime.now(UTC))
        return CapabilitySnapshot(
            actor, target.destination_ref, dict.fromkeys(C, S.AVAILABLE), stamp
        )


class _Pages:
    def __init__(self, provenance: str) -> None:
        self._provenance = provenance

    def read(self, query: ContextQuery) -> ContextPage:
        if query.kind == "members":
            return ContextPage((), self._provenance, None)
        start = int(query.args.get("cursor") or 1000)
        stamp = timeutil.iso(datetime.now(UTC))
        items = tuple(
            {
                "source": self._provenance,
                "observed_at": stamp,
                "message_id": start - i,
                "sent_at": stamp,
                "sender_id": "1",
                "chat_id": query.target.identity,
                "untrusted": {"text": f"selftest message {start - i}", "sender_name": "Selftest"},
            }
            for i in range(3)
        )
        return ContextPage(items, self._provenance, str(start - 3) if start > 991 else None)


class _AcceptingDelivery:
    def __init__(self, name: str, normalize: Callable[[str], str]) -> None:
        self.name, self._normalize = name, normalize

    def normalize(self, platform_identity: str) -> str:
        return self._normalize(platform_identity)

    def prepare(self, intent: DeliveryIntent, send_at: datetime) -> PreparedPayload | Skip:
        data = jcs_dumps(
            {
                "content": dict(intent.content),
                "send_at": timeutil.iso(send_at),
                "to": intent.identity,
            }
        )
        return PreparedPayload(data=data, digest=hashlib.sha256(data).hexdigest())

    def still_valid(self, payload: PreparedPayload, now: datetime) -> bool | str:
        return True

    def deliver(self, delivery: FrozenDelivery) -> DeliveryResult:
        return DeliveryResult(
            ResultKind.ACCEPTED, provider_message_ref=f"{self.name}-{next(_serial)}"
        )


# Public selftest constants: a selftest daemon is never a production daemon.
SELFTEST_APP_SECRET = b"selftest-app-secret-0000000000000"
SELFTEST_VERIFY_TOKEN = "selftest-verify-token-00000000000"
SELFTEST_CHAT = -1001234567890  # channel:1234567890, marked
_SELFTEST_BOT = "1:selftest"  # the token shape the pinned client checks; no real bot


# A47 (H6): one retained document the selftest bot can download (D39-A)
SELFTEST_DOCUMENT = b"%PDF-1.7 selftest document " + bytes(range(256)) * 400
_DOCUMENT = {"file_id": "BQAC-selftest-doc", "file_unique_id": "AgAD-selftest",
             "mime_type": "application/pdf", "file_size": len(SELFTEST_DOCUMENT)}  # fmt: skip


def _bot_updates() -> list[dict[str, Any]]:
    def update(n: int, **body: Any) -> dict[str, Any]:
        return {
            "update_id": n,
            "message": {
                "message_id": 100 + n,
                "date": 1758800000 + n,
                "chat": {"id": SELFTEST_CHAT, "type": "supergroup", "title": "MQ Society"},
                "from": {"id": 42, "is_bot": False, "first_name": "Sara"},
                **body,
            },
        }

    texts = [update(n, text=f"selftest update {n}") for n in (1, 2, 3)]
    return [*texts, update(4, document=_DOCUMENT, caption="selftest document")]


def _bot_transport() -> Any:
    import httpx

    def handle(request: Any) -> Any:
        if request.url.path.startswith("/file/bot"):  # A47: the one file the selftest holds
            return httpx.Response(200, content=SELFTEST_DOCUMENT)
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getFile":
            result: Any = {**_DOCUMENT, "file_path": "documents/file_4.pdf"}
            return httpx.Response(200, json={"ok": True, "result": result})
        if method == "getUpdates":
            offset = int((json.loads(request.content or b"{}") or {}).get("offset") or 0)
            result = [u for u in _bot_updates() if u["update_id"] >= offset]
        elif method == "getMe":
            result = {"id": 1, "is_bot": True, "first_name": "selftest"}
        elif method == "getChat":  # the group's own reads, in the Bot API's shapes (A47 H6)
            result = {"id": SELFTEST_CHAT, "type": "supergroup", "title": "MQ Society",
                      "permissions": {"can_send_messages": True, "can_pin_messages": False}}  # fmt: skip
        elif method == "getChatAdministrators":
            result = [{"status": "creator",
                       "user": {"id": 42, "is_bot": False, "first_name": "Sara"}}]  # fmt: skip
        elif method == "getChatMember":
            asked = (json.loads(request.content or b"{}") or {}).get("user_id")
            result = {"status": "member",
                      "user": {"id": asked, "is_bot": False, "first_name": "Member"}}  # fmt: skip
        elif method == "getChatMemberCount":
            result = 3
        else:
            result = True
        return httpx.Response(200, json={"ok": True, "result": result})

    return httpx.MockTransport(handle)


SELFTEST_IG_USER = "17841400000000099"  # proposed A49: the scripted account's user id
_IG_MEDIA, _IG_COMMENT, _IG_PERSON = "17900000000000099", "17800000000000099", "9876500099"
_IG_STORY = "17900000000000199"  # R-IG11: one live Story
_IG_THREAD = "aWdfZAG06MTpJR01lc3NhZA2VUaHJlYWQ6c2VsZnRlc3Q"
_IG_MESSAGE = "aWdfZAG1faXRlbToxOklHTWVzc2FnZAselftest01"


class _InstagramGraph:
    """A scripted graph.instagram.com (proposed A49), one per daemon process so the containers
    it made survive a reload. Every answer has Meta's documented shape; anything else is 404."""

    def __init__(self) -> None:
        self._ids = itertools.count(int(time.time() * 1000))  # numeric, unique per run
        self.containers: set[str] = set()
        self.media = {_IG_MEDIA}

    def _item(self, media: str) -> dict[str, Any]:
        return {"id": media, "media_type": "IMAGE", "timestamp": "2026-10-01T10:00:00+0000",
                "like_count": 2, "comments_count": 1, "is_comment_enabled": True,
                "username": "selftest.studio", "permalink": "https://www.instagram.com/p/self/"}  # fmt: skip

    def handle(self, request: Any) -> Any:
        import httpx

        method, parts = request.method, request.url.path.strip("/").split("/")
        node, edge = (parts[1] if len(parts) > 1 else ""), (parts[2] if len(parts) > 2 else None)
        ok = {"success": True}
        if parts == ["refresh_access_token"]:
            body: Any = {"access_token": "IGAAselftestREFRESHED" + "0" * 32,
                         "token_type": "bearer", "expires_in": 5184000}  # fmt: skip
        elif method == "GET" and node == "me" and edge is None:
            body = {"user_id": SELFTEST_IG_USER, "username": "selftest.studio",
                    "account_type": "BUSINESS", "followers_count": 3, "follows_count": 1,
                    "media_count": len(self.media), "name": "Selftest"}  # fmt: skip
        elif method == "GET" and node == SELFTEST_IG_USER and edge == "stories":
            body = {"data": [self._item(_IG_STORY)]}
        elif method == "GET" and node == _IG_STORY and edge is None:
            body = self._item(_IG_STORY)
        elif method == "GET" and node == "me" and edge == "media":
            body = {"data": [self._item(m) for m in sorted(self.media)]}
        elif method == "GET" and node == "me" and edge == "conversations":
            body = {"data": [{"id": _IG_THREAD, "participants": {"data": [
                {"id": _IG_PERSON, "username": "selftest.customer"}]}}]}  # fmt: skip
        elif method == "GET" and node == _IG_THREAD:
            body = {"messages": {"data": [{"id": _IG_MESSAGE}]}}
        elif method == "GET" and node == _IG_MESSAGE:
            stamp = datetime.fromtimestamp(time.time() - 3600, UTC)
            body = {"id": _IG_MESSAGE, "from": {"id": _IG_PERSON}, "message": "selftest hello",
                    "created_time": stamp.strftime("%Y-%m-%dT%H:%M:%S+0000")}  # fmt: skip
        elif method == "GET" and node in self.media and edge is None:
            body = self._item(node)
        elif method == "GET" and edge == "insights":
            body = {"data": [{"name": request.url.params.get("metric", "reach").split(",")[0],
                              "period": "day", "values": [{"value": 5}],
                              "total_value": {"value": 5}}]}  # fmt: skip
        elif method == "GET" and node in self.media and edge == "comments":
            body = {"data": [{"id": _IG_COMMENT, "text": "selftest comment",
                              "username": "selftest.fan", "timestamp": "2026-10-01T11:00:00+0000"}]}  # fmt: skip
        elif method == "GET" and edge in ("replies", "tags"):
            body = {"data": [self._item(_IG_MEDIA)] if edge == "tags" else []}
        elif method == "GET" and edge == "content_publishing_limit":
            body = {"data": [{"quota_usage": 0,
                              "config": {"quota_total": 50, "quota_duration": 86400}}]}  # fmt: skip
        elif method == "GET" and node in self.containers:
            body = {"id": node, "status_code": "FINISHED"}
        elif method == "POST" and node == SELFTEST_IG_USER and edge == "media":
            made = str(next(self._ids))
            self.containers.add(made)
            body = {"id": made}
        elif method == "POST" and node == SELFTEST_IG_USER and edge == "media_publish":
            made = str(next(self._ids))
            self.media.add(made)
            body = {"id": made}
        elif method == "POST" and node == SELFTEST_IG_USER and edge == "messages":
            body = {"recipient_id": _IG_PERSON, "message_id": _IG_MESSAGE + "R"}
        elif method == "POST" and node == _IG_COMMENT and edge == "replies":
            body = {"id": str(next(self._ids))}
        elif method in ("POST", "DELETE") and node in (_IG_COMMENT, *self.media) and edge is None:
            body = ok
        else:
            return httpx.Response(404, json={"error": {"code": 100, "message": "selftest"}})
        return httpx.Response(200, json=body)


_INSTAGRAM_GRAPH: _InstagramGraph | None = None


def _instagram_transport() -> Any:
    import httpx

    global _INSTAGRAM_GRAPH
    if _INSTAGRAM_GRAPH is None:
        _INSTAGRAM_GRAPH = _InstagramGraph()
    return httpx.MockTransport(_INSTAGRAM_GRAPH.handle)


class _OneSecret:
    def get(self, item: str, version: int) -> bytes:
        return _SELFTEST_BOT.encode()


def selftest_adapters(state: CommsState, settings: DaemonSettings) -> Adapters:
    def clock() -> datetime:
        return datetime.now(UTC)

    unreachable: Any = _Unreachable()
    admins = {
        "telegram_bot": _Accepting(BotAdmin(unreachable)),
        "telegram_user": _Accepting(UserAdmin(unreachable, run=_no_run, clock=clock)),
        "whatsapp_cloud": _Accepting(WhatsAppAdmin(unreachable, unreachable)),
    }
    store: Any = _OneSecret()
    api = BotApi(store, version=1, transport=_bot_transport())
    adapters = Adapters(
        delivery={
            "telegram": _AcceptingDelivery("telegram", marked_chat_id),
            "whatsapp": _AcceptingDelivery("whatsapp", e164),
        },
        capability=dict.fromkeys(_ACTORS, _Available()),
        admin=dict(admins),
        context={"telegram_bot": BotContext(api, state.conn, clock=clock)},
        downloads={"telegram_bot": BotMedia(api, state.conn)},  # A47: the real downloader
    )
    adapters.poller = BotPoller(api, state.conn, clock=clock)
    if settings.webhook_port is not None:
        inbox = Inbox(state.conn, clock=clock)
        adapters.inbox = inbox
        adapters.worker = WebhookWorker(
            state.conn, CommsArchive(state.conn, clock=clock), clock=clock
        )
        adapters.webhook = WebhookIngress(
            app_secret=SELFTEST_APP_SECRET,
            verify_token=SELFTEST_VERIFY_TOKEN,
            accept=inbox.accept,
            clock=time.monotonic,
        )
        adapters.listeners["webhook"] = adapters.webhook
        adapters.context["whatsapp_cloud"] = ArchiveContext(state.conn, clock=clock)
    elif settings.adapter.relay_url is not None:  # A48 (R5): a relay under `wrangler dev`
        from comms.runtime.assemble import relay_keys

        keys = relay_keys(state)
        inbox = Inbox(state.conn, clock=clock)
        adapters.inbox = inbox
        adapters.worker = WebhookWorker(
            state.conn, CommsArchive(state.conn, clock=clock), clock=clock
        )
        adapters.relay = Collector(
            state.conn,
            RelayClient(settings.adapter.relay_url, keys.pull_key, transport=LoopbackRelay()),
            inbox,
            identities=keys.identities,
            app_secret=SELFTEST_APP_SECRET,
            clock=clock,
        )
        adapters.context["whatsapp_cloud"] = ArchiveContext(state.conn, clock=clock)
    if settings.adapter.instagram is not None:  # proposed A49: the real adapters, scripted Graph
        instagram_adapters(
            adapters, state.conn, state.secrets, settings.adapter.instagram, clock,
            transport=_instagram_transport(),
        )  # fmt: skip
    return adapters
