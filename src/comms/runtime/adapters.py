"""The adapter registry (comms v0.3 Task C33; A18, A24, A36).

``build_adapters`` builds the four adapters from the credentials active in comms.db, read from
the secret store (``active_credential`` recomputes each id). A missing credential never
crashes: the actor's capability provider still exists and reports ``NOT_CONFIGURED``, and the
actor offers nothing else. The Telegram user actor uses the one Telethon session for delivery,
capability, admin, context and the update stream (which the registry claims, A24). The webhook
ingress is served only when both the app secret and the verify token are configured, and only
as its own listener.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from comms.core.credentials import (
    active_credential,
    active_version,
    is_confirmed,
    record_confirmed,
)
from comms.core.delivery.transport import DeliveryTransport
from comms.core.keys.purposes import instagram_token_purpose
from comms.core.keys.secrets import SecretStore
from comms.core.providers.protocols import ProviderTarget
from comms.runtime.relay import Collector
from comms.transports.instagram import store as instagram_store
from comms.transports.instagram.accounts import AccountRuntime, InstagramAccounts
from comms.transports.instagram.admin import InstagramAdmin
from comms.transports.instagram.capability import InstagramCapability
from comms.transports.instagram.config import InstagramSettings
from comms.transports.instagram.http import GraphIgApi
from comms.transports.profiles import bot_profile, user_profile, whatsapp_profile
from comms.transports.telegram.bot.admin import BotAdmin
from comms.transports.telegram.bot.capability import BotCapability
from comms.transports.telegram.bot.context import BotContext
from comms.transports.telegram.bot.delivery import BotDelivery
from comms.transports.telegram.bot.http import BotApi
from comms.transports.telegram.bot.media import BotMedia
from comms.transports.telegram.bot.updates import BotPoller
from comms.transports.telegram.user.admin import UserAdmin
from comms.transports.telegram.user.capability import UserCapability
from comms.transports.telegram.user.context import UserContext
from comms.transports.telegram.user.delivery import UserDelivery
from comms.transports.telegram.user.media import UserMedia
from comms.transports.telegram.user.updates import UserUpdateConsumer
from comms.transports.whatsapp.cloud.account import WhatsAppCapability, health_of
from comms.transports.whatsapp.cloud.context import WhatsAppContext
from comms.transports.whatsapp.cloud.delivery import WhatsAppDelivery
from comms.transports.whatsapp.cloud.groups import GroupDiscovery, WhatsAppAdmin
from comms.transports.whatsapp.cloud.http import GraphApi
from comms.transports.whatsapp.cloud.media import MediaOps
from comms.transports.whatsapp.cloud.templates import TemplateCatalog, TemplateOps
from comms.transports.whatsapp.relay_client import RelayClient
from comms.transports.whatsapp.webhooks.archive import ArchiveContext
from comms.transports.whatsapp.webhooks.inbox import Inbox
from comms.transports.whatsapp.webhooks.ingress import WebhookIngress
from comms.transports.whatsapp.webhooks.worker import Archive, WebhookWorker

__all__ = ["UPDATE_OWNER", "AdapterSettings", "Adapters", "RelayKeys", "build_adapters"]

UPDATE_OWNER = "update-consumer"
Runner = Callable[[Coroutine[Any, Any, Any]], Any]


@dataclass(frozen=True)
class AdapterSettings:
    telegram_delivery_actor: Literal["telegram_bot", "telegram_user"] = "telegram_bot"
    meta_phone_number_id: str | None = None
    meta_waba_id: str | None = None
    relay_url: str | None = None  # A48: WhatsApp webhooks arrive through the relay
    instagram: InstagramSettings | None = None  # proposed A49


@dataclass(frozen=True)
class RelayKeys:
    """A48: the relay's pull key and the age identities that open its rows (loaded from the key
    slots by the composition root). ``transport`` is the injected network seam."""

    pull_key: bytes = field(repr=False)
    identities: tuple[str, ...] = field(repr=False)
    transport: Any = field(default=None, repr=False)


@dataclass
class Adapters:
    delivery: dict[str, DeliveryTransport] = field(default_factory=dict)
    capability: dict[str, Any] = field(default_factory=dict)
    admin: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    webhook: WebhookIngress | None = None
    inbox: Inbox | None = None
    worker: WebhookWorker | None = None
    updates: UserUpdateConsumer | None = None
    poller: BotPoller | None = None  # D39-PRE E5: fills bot_updates, the bot's local context
    listeners: dict[str, Any] = field(default_factory=dict)
    catalog: TemplateCatalog = field(default_factory=TemplateCatalog)
    # G2 prerequisite: the WhatsApp account's template and media sources, and the WABA target
    # the account tools act on (templates need the business-account id; media only the number)
    graph: GraphApi | None = None  # G8: the Groups API's live reads
    profiles: dict[str, Any] = field(default_factory=dict)  # G8: each account's own profile
    phone: Any = None  # G8: the WhatsApp number's quality and status
    health: Any = None  # A46: the WhatsApp number's messaging health
    templates: TemplateOps | None = None
    media: MediaOps | None = None
    account: ProviderTarget | None = None
    # A47 (H3): each Telegram actor's download of its own ``med_`` (WhatsApp's is ``media``)
    downloads: dict[str, Any] = field(default_factory=dict)
    relay: Collector | None = None  # A48: the relay collector, when a relay is configured
    instagram: InstagramAccounts | None = None  # proposed A49: configured Instagram accounts

    def __repr__(self) -> str:
        return (
            f"Adapters(delivery={sorted(self.delivery)}, capability={sorted(self.capability)},"
            f" listeners={sorted(self.listeners)})"
        )


class _NoSession:
    """The user actor without a session: every capability is NOT_CONFIGURED (AUTH_REQUIRED)."""

    def readiness(self) -> str:
        return "AUTH_REQUIRED"

    async def self_rights(self, peer_type: str, peer_id: int, *, timeout: float) -> Any:
        raise AssertionError("never called without a session")


def _never(coroutine: Coroutine[Any, Any, Any]) -> Any:
    coroutine.close()
    raise AssertionError("the user actor has no session")


def _configured(conn: Any, secrets: SecretStore, purpose: str) -> int | None:
    """The active version, once its stored value checks out; None when not configured."""
    if active_credential(conn, secrets, purpose) is None:
        return None
    row = active_version(conn, purpose)
    return None if row is None else int(row[0])


def build_adapters(
    conn: Any,
    secrets: SecretStore,
    settings: AdapterSettings,
    *,
    clock: Callable[[], datetime],
    monotonic: Callable[[], float],
    archive: Archive | None,
    telegram_session: Any = None,
    run: Runner | None = None,
    relay_keys: RelayKeys | None = None,
) -> Adapters:
    adapters = Adapters()
    telegram = {
        "telegram_bot": _telegram_bot(adapters, conn, secrets, clock),
        "telegram_user": _telegram_user(adapters, conn, telegram_session, run, clock),
    }
    fallback = (
        "telegram_user" if settings.telegram_delivery_actor == "telegram_bot" else "telegram_bot"
    )
    chosen = telegram[settings.telegram_delivery_actor] or telegram[fallback]  # P §10: auto
    if chosen is not None:
        adapters.delivery["telegram"] = chosen
    _whatsapp(adapters, conn, secrets, settings, clock)
    if settings.relay_url is not None:
        _relay(adapters, conn, secrets, clock, archive, settings.relay_url, relay_keys)
    else:
        _webhooks(adapters, conn, secrets, clock, monotonic, archive)
    if settings.instagram is not None:
        _instagram(adapters, conn, secrets, settings.instagram, clock)
    if adapters.graph is not None:  # G8: group reads live, messages from the archive (if any)
        adapters.context["whatsapp_cloud"] = WhatsAppContext(
            adapters.context.get("whatsapp_cloud"), adapters.graph, clock=clock
        )
    return adapters


def _telegram_bot(
    adapters: Adapters, conn: Any, secrets: SecretStore, clock: Callable[[], datetime]
) -> DeliveryTransport | None:
    version = _configured(conn, secrets, "telegram-bot-token")
    if version is None:
        adapters.capability["telegram_bot"] = BotCapability(None, clock=clock)
        return None
    api = BotApi(secrets, version=version)
    adapters.capability["telegram_bot"] = BotCapability.from_api(api, clock=clock)
    files = BotMedia(api, conn)  # A47: downloads and resends read the retained file_id
    adapters.admin["telegram_bot"] = BotAdmin(api, files=files.file_id)
    adapters.context["telegram_bot"] = BotContext(api, conn, clock=clock)
    adapters.poller = BotPoller(api, conn, clock=clock)
    adapters.profiles["telegram_bot"] = bot_profile(api)
    adapters.downloads["telegram_bot"] = files  # A47
    return BotDelivery(api)


def _telegram_user(
    adapters: Adapters, conn: Any, session: Any, run: Runner | None, clock: Callable[[], datetime]
) -> DeliveryTransport | None:
    if session is None or run is None:
        adapters.capability["telegram_user"] = UserCapability(_NoSession(), run=_never, clock=clock)
        return None
    session.claim_updates(UPDATE_OWNER)  # A24: the one consumer of the one session's stream
    adapters.capability["telegram_user"] = UserCapability(session, run=run, clock=clock)
    adapters.admin["telegram_user"] = UserAdmin(session, run=run, clock=clock)
    adapters.profiles["telegram_user"] = user_profile(session, run)
    adapters.context["telegram_user"] = UserContext(session, run=run, clock=clock)
    adapters.downloads["telegram_user"] = UserMedia(session, run=run)  # A47
    adapters.updates = UserUpdateConsumer(conn, clock=clock)
    return UserDelivery(session, run=run)


def _whatsapp(
    adapters: Adapters,
    conn: Any,
    secrets: SecretStore,
    settings: AdapterSettings,
    clock: Callable[[], datetime],
) -> None:
    version = _configured(conn, secrets, "meta-access-token")
    if version is None or settings.meta_phone_number_id is None:
        adapters.capability["whatsapp_cloud"] = WhatsAppCapability(None, None, clock=clock)
        return
    api = GraphApi(
        secrets,
        version=version,
        phone_number_id=settings.meta_phone_number_id,
        waba_id=settings.meta_waba_id,
    )
    discovery = GroupDiscovery(api)
    capability = WhatsAppCapability(api, discovery, clock=clock)
    adapters.capability["whatsapp_cloud"] = capability
    adapters.phone, adapters.health = capability.inspect_phone, health_of(api)
    adapters.admin["whatsapp_cloud"] = WhatsAppAdmin(api, discovery)
    adapters.delivery["whatsapp"] = WhatsAppDelivery(api, catalog=adapters.catalog)
    adapters.media = MediaOps(api)
    adapters.graph = api
    adapters.profiles["whatsapp_cloud"] = whatsapp_profile(api)
    if settings.meta_waba_id is not None:
        adapters.templates = TemplateOps(api)
        adapters.account = ProviderTarget(
            "whatsapp", "whatsapp_cloud", "account", f"waba:{settings.meta_waba_id}"
        )


def _instagram(
    adapters: Adapters,
    conn: Any,
    secrets: SecretStore,
    settings: InstagramSettings,
    clock: Callable[[], datetime],
) -> None:
    """Proposed A49: one ``GraphIgApi`` per alias configured in comms.json, registered
    (``iga_``) and holding an active token. No network here: the identity check is lazy."""
    runtimes: dict[str, AccountRuntime] = {}
    for alias, policy in settings.accounts.items():
        row = instagram_store.account_by_alias(conn, alias)
        purpose = instagram_token_purpose(alias)
        version = _configured(conn, secrets, purpose)
        if row is None or version is None:
            continue
        api = GraphIgApi(
            secrets, purpose=purpose, version=version, api_version=settings.api_version
        )
        runtimes[alias] = AccountRuntime(alias, row.ref, row.id, policy, api, row.user_id)
    accounts = InstagramAccounts(conn, settings, runtimes, clock=clock)
    adapters.instagram = accounts
    adapters.capability["instagram"] = InstagramCapability(accounts, clock=clock)
    if runtimes:
        adapters.admin["instagram"] = InstagramAdmin(accounts, conn, clock=clock)


def _confirmer(conn: Any, versions: dict[str, int]) -> Callable[[str], None]:
    def confirmed(purpose: str) -> None:  # R-E6: once per active version, metadata only
        if not is_confirmed(conn, purpose, versions[purpose]):
            record_confirmed(conn, purpose, versions[purpose])

    return confirmed


def _relay(
    adapters: Adapters,
    conn: Any,
    secrets: SecretStore,
    clock: Callable[[], datetime],
    archive: Archive | None,
    url: str,
    keys: RelayKeys | None,
) -> None:
    """A48: webhooks come from the relay, so no local listener is served; the daemon is still
    the only verifier of Meta's signature (D-R1). The verify token lives in the Worker."""
    secret_version = _configured(conn, secrets, "meta-app-secret")
    if secret_version is None or archive is None or keys is None:
        return  # never collect an event the daemon could not verify and archive
    inbox = Inbox(conn, clock=clock)
    adapters.inbox = inbox
    adapters.worker = WebhookWorker(conn, archive, clock=clock)
    adapters.relay = Collector(
        conn,
        RelayClient(url, keys.pull_key, transport=keys.transport),
        inbox,
        identities=keys.identities,
        app_secret=secrets.get("meta-app-secret", secret_version),
        clock=clock,
        on_verified=_confirmer(conn, {"meta-app-secret": secret_version}),
    )
    adapters.context["whatsapp_cloud"] = ArchiveContext(conn, clock=clock)


def _webhooks(
    adapters: Adapters,
    conn: Any,
    secrets: SecretStore,
    clock: Callable[[], datetime],
    monotonic: Callable[[], float],
    archive: Archive | None,
) -> None:
    secret_version = _configured(conn, secrets, "meta-app-secret")
    token_version = _configured(conn, secrets, "meta-webhook-secret")
    if secret_version is None or token_version is None or archive is None:
        return  # D39-PRE: never accept an event the inbox could not archive
    inbox = Inbox(conn, clock=clock)
    adapters.inbox = inbox
    adapters.worker = WebhookWorker(conn, archive, clock=clock)
    confirmed = _confirmer(
        conn, {"meta-app-secret": secret_version, "meta-webhook-secret": token_version}
    )
    adapters.webhook = WebhookIngress(
        app_secret=secrets.get("meta-app-secret", secret_version),
        verify_token=secrets.get("meta-webhook-secret", token_version).decode("utf-8"),
        accept=inbox.accept,
        clock=monotonic,
        on_confirmed=confirmed,
    )
    # D39-PRE E10b: the comms-native archive is WhatsApp's context source
    adapters.context["whatsapp_cloud"] = ArchiveContext(conn, clock=clock)
    adapters.listeners["webhook"] = adapters.webhook
