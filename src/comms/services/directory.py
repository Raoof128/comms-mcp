"""Location and audience services over the 5b-4 directory (comms v0.3 Task D16; P §31, G16).

Every write runs through ``MutationExecutor.local`` with the caller's ``req_`` id (the core's
``*_in_tx`` bodies), so a replay returns the stored result and creates nothing twice. An
audience that would contain itself is refused before anything is recorded. ``audience.resolve``
returns counts and endpoint refs — never a delivery identity.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from comms.core.audit.writer import AuditWriter
from comms.core.campaigns import directory as d
from comms.core.campaigns import directory_views as views
from comms.core.campaigns.drafts import TRANSPORTS
from comms.core.campaigns.resolve import resolve_targets
from comms.core.errors import CommsError
from comms.services.local import effect, mapped, next_cursor, page_args, run_local
from comms.services.mutations import CallContext, MutationExecutor

__all__ = ["RESOLVE_ENDPOINTS_MAX", "DirectoryService", "IdentityRule"]

RESOLVE_ENDPOINTS_MAX = 500
_NAME_MAX = 200


def _name(name: object) -> str:
    if not isinstance(name, str) or not name.strip() or len(name) > _NAME_MAX:
        raise CommsError("INVALID_ARGUMENT")
    return name


@dataclass(frozen=True)
class IdentityRule:
    """One transport's identity rule for one directory kind (G3, G4): ``platform`` turns the
    owner's input into the stored platform identity, ``canonical`` into the delivery identity.
    Both raise ``ValueError``; the runtime supplies them, so services import no transport."""

    platform: Callable[[str], str]
    canonical: Callable[[str], str]


def _ref(value: object, prefix: str) -> str:
    """A ref of one kind, or NOT_FOUND before anything is recorded (D16)."""
    if not isinstance(value, str) or not value.startswith(prefix):
        raise CommsError("NOT_FOUND")
    return value


class DirectoryService:
    def __init__(
        self,
        writer: AuditWriter,
        executor: MutationExecutor,
        rules: Mapping[tuple[str, str], IdentityRule] | None = None,
        bind: Callable[[str, str], str] | None = None,
    ) -> None:
        self._writer, self._executor = writer, executor
        self._rules, self._bind = rules or {}, bind

    def _identity(self, kind: str, transport: object, raw: object) -> tuple[str, str, str]:
        """``(platform identity, canonical identity, keyed binding)``, or INVALID_ARGUMENT
        before anything is recorded. The raw identity never reaches an error or a digest."""
        rule = self._rules.get((kind, transport)) if isinstance(transport, str) else None
        if rule is None or not isinstance(raw, str):
            raise CommsError("INVALID_ARGUMENT")
        try:
            platform = rule.platform(raw)
            canonical = rule.canonical(platform)
        except (ValueError, KeyError):
            raise CommsError("INVALID_ARGUMENT") from None
        if self._bind is None:
            raise CommsError("NOT_CONFIGURED")
        return platform, canonical, self._bind(str(transport), canonical)

    # -- locations ------------------------------------------------------------------------

    def location_create(self, ctx: CallContext, name: str, request_id: str) -> dict[str, Any]:
        name = _name(name)
        return run_local(
            self._executor,
            ctx,
            "comms_location_create",
            {},
            {"name": name},
            request_id,
            lambda tx: {"location": d.add_location_in_tx(tx.conn, name, now=tx.now)},
        )

    def location_update(
        self, ctx: CallContext, location: str, name: str, request_id: str
    ) -> dict[str, Any]:
        return self._rename(ctx, "comms_location_update", "location", location, name, request_id)

    def location_enable(self, ctx: CallContext, location: str, request_id: str) -> dict[str, Any]:
        return self._enabled(ctx, "comms_location_enable", location, True, request_id)

    def location_disable(self, ctx: CallContext, location: str, request_id: str) -> dict[str, Any]:
        return self._enabled(ctx, "comms_location_disable", location, False, request_id)

    def location_get(self, location: str) -> dict[str, Any]:
        return mapped(lambda: views.location_view(self._writer.conn, location))  # type: ignore[no-any-return]

    def location_list(self, *, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        size, before = page_args(limit, cursor)
        items, more = views.list_locations(self._writer.conn, limit=size, before=before)
        items = [{**i, "enabled": bool(i["enabled"])} for i in items]
        return {"items": items, "next_cursor": next_cursor(more)}

    # -- audiences ------------------------------------------------------------------------

    def audience_create(self, ctx: CallContext, name: str, request_id: str) -> dict[str, Any]:
        name = _name(name)
        return run_local(
            self._executor,
            ctx,
            "comms_audience_create",
            {},
            {"name": name},
            request_id,
            lambda tx: {"audience": d.add_audience_in_tx(tx.conn, name, now=tx.now)},
        )

    def audience_update(
        self, ctx: CallContext, audience: str, name: str, request_id: str
    ) -> dict[str, Any]:
        return self._rename(ctx, "comms_audience_update", "audience", audience, name, request_id)

    def audience_add(
        self, ctx: CallContext, audience: str, member: str, request_id: str
    ) -> dict[str, Any]:
        return run_local(
            self._executor,
            ctx,
            "comms_audience_add",
            {"audience": audience, "member": member},
            {},
            request_id,
            effect(lambda tx: d.add_audience_member_in_tx(tx.conn, audience, member)),
        )

    def audience_remove(
        self, ctx: CallContext, audience: str, member: str, request_id: str
    ) -> dict[str, Any]:
        return run_local(
            self._executor,
            ctx,
            "comms_audience_remove",
            {"audience": audience, "member": member},
            {},
            request_id,
            effect(lambda tx: d.remove_audience_member_in_tx(tx.conn, audience, member)),
        )

    def audience_get(self, audience: str) -> dict[str, Any]:
        return mapped(lambda: views.audience_view(self._writer.conn, audience))  # type: ignore[no-any-return]

    def audience_list(self, *, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        size, before = page_args(limit, cursor)
        items, more = views.list_audiences(self._writer.conn, limit=size, before=before)
        return {"items": items, "next_cursor": next_cursor(more)}

    def audience_resolve(self, audience: str) -> dict[str, Any]:
        """Who the audience reaches today, as counts and endpoint refs."""

        def resolve() -> dict[str, Any]:
            views.audience_view(self._writer.conn, audience)  # NOT_FOUND before resolving
            candidates = resolve_targets(self._writer.conn, {"audiences": [audience]}, TRANSPORTS)
            by_transport: dict[str, int] = {}
            endpoints: set[str] = set()
            for candidate in candidates:
                by_transport[candidate.transport] = by_transport.get(candidate.transport, 0) + 1
                endpoints.update(candidate.endpoint_refs)
            listed = sorted(endpoints)
            return {
                "audience": audience,
                "count": len(candidates),
                "by_transport": by_transport,
                "endpoints": listed[:RESOLVE_ENDPOINTS_MAX],
                "truncated": len(listed) > RESOLVE_ENDPOINTS_MAX,
            }

        return mapped(resolve)  # type: ignore[no-any-return]

    # -- people (catalog amendment G2) ---------------------------------------------------

    def recipient_create(
        self, ctx: CallContext, display_name: str, request_id: str
    ) -> dict[str, Any]:
        label = _name(display_name)
        return run_local(
            self._executor,
            ctx,
            "comms_directory_recipient_create",
            {},
            {"display_name": label},
            request_id,
            lambda tx: {
                "recipient": d.add_recipient_in_tx(tx.conn, now=tx.now, display_name=label)
            },
        )

    def recipient_update(
        self, ctx: CallContext, recipient: str, display_name: str, request_id: str
    ) -> dict[str, Any]:
        label = _name(display_name)
        return run_local(
            self._executor,
            ctx,
            "comms_directory_recipient_update",
            {"recipient": _ref(recipient, "rcp_")},
            {"display_name": label},
            request_id,
            effect(lambda tx: d.set_display_name_in_tx(tx.conn, recipient, label)),
        )

    def recipient_enable(self, ctx: CallContext, recipient: str, request_id: str) -> dict[str, Any]:
        return self._recipient_enabled(ctx, "enable", recipient, True, request_id)

    def recipient_disable(
        self, ctx: CallContext, recipient: str, request_id: str
    ) -> dict[str, Any]:
        return self._recipient_enabled(ctx, "disable", recipient, False, request_id)

    def recipient_get(self, recipient: str) -> dict[str, Any]:
        return mapped(lambda: views.recipient_view(self._writer.conn, recipient))  # type: ignore[no-any-return]

    def recipient_list(self, *, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        size, before = page_args(limit, cursor)
        items, more = views.list_recipients(self._writer.conn, limit=size, before=before)
        return {"items": items, "next_cursor": next_cursor(more)}

    def _recipient_enabled(
        self, ctx: CallContext, verb: str, recipient: str, enabled: bool, request_id: str
    ) -> dict[str, Any]:
        return run_local(
            self._executor,
            ctx,
            f"comms_directory_recipient_{verb}",
            {"recipient": _ref(recipient, "rcp_")},
            {},
            request_id,
            effect(lambda tx: d.set_enabled_in_tx(tx.conn, recipient, enabled, now=tx.now)),
        )

    # -- contact points (catalog amendment G3) ---------------------------------------------

    def contact_add(
        self, ctx: CallContext, recipient: str, transport: str, identity: str, request_id: str
    ) -> dict[str, Any]:
        """A person's number or Telegram user id: input only, never echoed (A26, D1)."""
        platform, _canonical, binding = self._identity("contact", transport, identity)
        rule = self._rules[("contact", transport)]
        return run_local(
            self._executor,
            ctx,
            "comms_directory_contact_add",
            {"recipient": _ref(recipient, "rcp_")},
            {"transport": transport, "identity_binding": binding},
            request_id,
            lambda tx: {
                "contact": d.add_contact_point_in_tx(
                    tx.conn, recipient, transport, platform, normalize=rule.canonical, now=tx.now
                )
            },
        )

    def contact_disable(self, ctx: CallContext, contact: str, request_id: str) -> dict[str, Any]:
        return run_local(
            self._executor,
            ctx,
            "comms_directory_contact_disable",
            {"contact": _ref(contact, "rct_")},
            {},
            request_id,
            effect(lambda tx: d.set_enabled_in_tx(tx.conn, contact, False, now=tx.now)),
        )

    def contact_opt_out(self, ctx: CallContext, contact: str, request_id: str) -> dict[str, Any]:
        """Recorded once, permanent: campaigns skip it and it is never re-added (G3)."""
        return run_local(
            self._executor,
            ctx,
            "comms_directory_contact_opt_out",
            {"contact": _ref(contact, "rct_")},
            {},
            request_id,
            effect(lambda tx: d.opt_out_in_tx(tx.conn, contact, now=tx.now)),
        )

    # -- destinations and location membership (catalog amendment G4) ----------------------

    def destination_create(
        self,
        ctx: CallContext,
        location: str,
        transport: str,
        identity: str,
        name: str,
        request_id: str,
    ) -> dict[str, Any]:
        """A chat campaigns and group tools can reach; its identity is input only. A group gets
        its ``grp_`` in the same transaction (E11b); a private chat has none."""
        label = _name(name)
        platform, _canonical, binding = self._identity("destination", transport, identity)
        rule = self._rules[("destination", transport)]

        def create(tx: Any) -> dict[str, Any]:
            destination = d.add_destination_in_tx(
                tx.conn, location, transport, platform, label, normalize=rule.canonical, now=tx.now
            )
            row = tx.conn.execute(
                "SELECT g.ref FROM groups g JOIN destinations x ON x.id = g.destination_id"
                " WHERE x.ref = ?",
                (destination,),
            ).fetchone()
            return {"destination": destination, "group": None if row is None else row[0]}

        return run_local(
            self._executor,
            ctx,
            "comms_directory_destination_create",
            {"location": _ref(location, "loc_")},
            {"transport": transport, "identity_binding": binding, "name": label},
            request_id,
            create,
        )

    def destination_disable(
        self, ctx: CallContext, destination: str, request_id: str
    ) -> dict[str, Any]:
        return run_local(
            self._executor,
            ctx,
            "comms_directory_destination_disable",
            {"destination": _ref(destination, "dst_")},
            {},
            request_id,
            effect(lambda tx: d.set_enabled_in_tx(tx.conn, destination, False, now=tx.now)),
        )

    def location_member_add(
        self, ctx: CallContext, location: str, recipient: str, request_id: str
    ) -> dict[str, Any]:
        return self._membership(ctx, "add", location, recipient, request_id)

    def location_member_remove(
        self, ctx: CallContext, location: str, recipient: str, request_id: str
    ) -> dict[str, Any]:
        return self._membership(ctx, "remove", location, recipient, request_id)

    def _membership(
        self, ctx: CallContext, verb: str, location: str, recipient: str, request_id: str
    ) -> dict[str, Any]:
        change = d.add_location_member_in_tx if verb == "add" else d.remove_location_member_in_tx
        return run_local(
            self._executor,
            ctx,
            f"comms_location_member_{verb}",
            {"location": _ref(location, "loc_"), "recipient": _ref(recipient, "rcp_")},
            {},
            request_id,
            effect(lambda tx: change(tx.conn, location, recipient)),
        )

    # -- shared ---------------------------------------------------------------------------

    def _rename(
        self, ctx: CallContext, tool: str, kind: str, ref: str, name: str, request_id: str
    ) -> dict[str, Any]:
        name = _name(name)
        return run_local(
            self._executor,
            ctx,
            tool,
            {kind: ref},
            {"name": name},
            request_id,
            effect(lambda tx: d.rename_in_tx(tx.conn, ref, name)),
        )

    def _enabled(
        self, ctx: CallContext, tool: str, location: str, enabled: bool, request_id: str
    ) -> dict[str, Any]:
        if not isinstance(location, str) or not location.startswith("loc_"):
            raise CommsError("INVALID_ARGUMENT")  # these tools act on locations only
        return run_local(
            self._executor,
            ctx,
            tool,
            {"location": location},
            {},
            request_id,
            effect(lambda tx: d.set_enabled_in_tx(tx.conn, location, enabled, now=tx.now)),
        )
