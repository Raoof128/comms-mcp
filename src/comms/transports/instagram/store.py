"""The Instagram tables (proposed A49, R-IG2; schema v10): accounts, the container ledger, and
the object refs.

An account binds an ``iga_`` to its alias and Instagram user id once and for all (a trigger
refuses a change; a removed account keeps its row). A container row is one ``igk_`` per Meta
container, the 400-per-24-hours budget's ledger. An object row is one ``igm_``, ``igc_`` or
``igp_`` per (account, kind, provider identity), stable across restarts. Identities live only
inside SQLCipher ``comms.db`` and never in a ``repr``; ``comms.core.identities`` is their one
reader for the owner. Every write here runs in the caller's transaction or its own
``write_tx``, never nested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from comms.core import refs, timeutil
from comms.core.errors import CommsError
from comms.core.storage.db import write_tx

__all__ = [
    "Account",
    "Container",
    "account_by_alias",
    "account_by_ref",
    "container",
    "containers_since",
    "live_accounts",
    "mark_container",
    "mark_identity_checked",
    "object_ref",
    "record_container",
    "register_account",
    "remove_account",
    "resolve_object",
    "set_expiry",
]

_KIND_PREFIX = {
    "media": "instagram_media",
    "comment": "instagram_comment",
    "person": "instagram_person",
}
_CONTAINER_KINDS = frozenset({"image", "reel", "story", "carousel", "child"})  # story: R-IG10
_STATUSES = frozenset({"IN_PROGRESS", "FINISHED", "ERROR", "EXPIRED", "PUBLISHED"})


@dataclass(frozen=True)
class Account:
    id: int
    ref: str
    alias: str
    user_id: str = field(repr=False)
    obtained_at: str
    expires_at: str
    last_identity_check_at: str | None


@dataclass(frozen=True)
class Container:
    id: int
    ref: str
    account_id: int
    kind: str
    creation_id: str = field(repr=False)
    created_at: str
    status: str | None
    media_ref: str | None


_ACCOUNT_COLUMNS = "id, ref, alias, user_id, obtained_at, expires_at, last_identity_check_at"
_CONTAINER_COLUMNS = "id, ref, account_id, kind, creation_id, created_at, status, media_ref"


def _account(row: Any) -> Account | None:
    return None if row is None else Account(*row)


def account_by_alias(conn: Any, alias: str) -> Account | None:
    row = conn.execute(
        f"SELECT {_ACCOUNT_COLUMNS} FROM instagram_accounts WHERE alias = ? AND removed_at IS NULL",
        (alias,),
    ).fetchone()
    return _account(row)


def account_by_ref(conn: Any, ref: str) -> Account | None:
    row = conn.execute(
        f"SELECT {_ACCOUNT_COLUMNS} FROM instagram_accounts WHERE ref = ? AND removed_at IS NULL",
        (ref,),
    ).fetchone()
    return _account(row)


def live_accounts(conn: Any) -> list[Account]:
    rows = conn.execute(
        f"SELECT {_ACCOUNT_COLUMNS} FROM instagram_accounts WHERE removed_at IS NULL ORDER BY alias"
    ).fetchall()
    return [Account(*row) for row in rows]


def register_account(
    conn: Any, alias: str, user_id: str, *, now: datetime, lifetime: timedelta
) -> str:
    """In the caller's audited transaction: a new ``iga_`` for a live alias and user id."""
    stamp = timeutil.iso(now)
    ref = refs.mint("instagram_account")
    conn.execute(
        "INSERT INTO instagram_accounts (ref, alias, user_id, obtained_at, expires_at,"
        " last_identity_check_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ref, alias, user_id, stamp, timeutil.iso(now + lifetime), stamp, stamp),
    )
    return ref


def remove_account(conn: Any, ref: str, *, now: datetime) -> None:
    """In the caller's audited transaction."""
    conn.execute(
        "UPDATE instagram_accounts SET removed_at = ? WHERE ref = ? AND removed_at IS NULL",
        (timeutil.iso(now), ref),
    )


def set_expiry(conn: Any, ref: str, *, now: datetime, lifetime: timedelta) -> None:
    """In the caller's audited transaction: a refreshed token's lifetime from now."""
    conn.execute(
        "UPDATE instagram_accounts SET obtained_at = ?, expires_at = ? WHERE ref = ?",
        (timeutil.iso(now), timeutil.iso(now + lifetime), ref),
    )


def mark_identity_checked(conn: Any, ref: str, *, now: datetime) -> None:
    with write_tx(conn):
        conn.execute(
            "UPDATE instagram_accounts SET last_identity_check_at = ? WHERE ref = ?",
            (timeutil.iso(now), ref),
        )


# -- objects -----------------------------------------------------------------------------------


def object_ref(conn: Any, account_id: int, kind: str, identity: str, *, now: datetime) -> str:
    """The object's ref: the existing one (its ``last_seen_at`` refreshed) or a new one."""
    if kind not in _KIND_PREFIX or not isinstance(identity, str) or not 1 <= len(identity) <= 64:
        raise CommsError("INVALID_ARGUMENT")
    stamp = timeutil.iso(now)
    with write_tx(conn):
        row = conn.execute(
            "SELECT id, ref FROM instagram_objects WHERE account_id = ? AND kind = ?"
            " AND provider_identity = ?",
            (account_id, kind, identity),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE instagram_objects SET last_seen_at = ? WHERE id = ?", (stamp, row[0])
            )
            return str(row[1])
        ref = refs.mint(_KIND_PREFIX[kind])
        conn.execute(
            "INSERT INTO instagram_objects (ref, account_id, kind, provider_identity, created_at,"
            " last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
            (ref, account_id, kind, identity, stamp, stamp),
        )
    return ref


def resolve_object(conn: Any, ref: object, kind: str, account_id: int) -> str:
    """The provider identity behind ``ref``; ``NOT_FOUND`` for another kind or account."""
    try:
        refs.check(ref, _KIND_PREFIX[kind])
    except (ValueError, KeyError):
        raise CommsError("INVALID_ARGUMENT") from None
    row = conn.execute(
        "SELECT provider_identity FROM instagram_objects WHERE ref = ? AND kind = ?"
        " AND account_id = ?",
        (ref, kind, account_id),
    ).fetchone()
    if row is None:
        raise CommsError("NOT_FOUND")
    return str(row[0])


# -- the container ledger ----------------------------------------------------------------------


def record_container(
    conn: Any, account_id: int, kind: str, creation_id: str, *, now: datetime
) -> str:
    """One ``igk_`` per Meta container, in its own transaction (an executor ``on_created``)."""
    if kind not in _CONTAINER_KINDS:
        raise CommsError("INVALID_ARGUMENT")
    with write_tx(conn):
        row = conn.execute(
            "SELECT ref FROM instagram_containers WHERE account_id = ? AND creation_id = ?",
            (account_id, creation_id),
        ).fetchone()
        if row is not None:
            return str(row[0])
        ref = refs.mint("instagram_container")
        conn.execute(
            "INSERT INTO instagram_containers (ref, account_id, kind, creation_id, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (ref, account_id, kind, creation_id, timeutil.iso(now)),
        )
    return ref


def container(conn: Any, ref: object, account_id: int) -> Container:
    try:
        refs.check(ref, "instagram_container")
    except ValueError:
        raise CommsError("INVALID_ARGUMENT") from None
    row = conn.execute(
        f"SELECT {_CONTAINER_COLUMNS} FROM instagram_containers WHERE ref = ? AND account_id = ?",
        (ref, account_id),
    ).fetchone()
    if row is None:
        raise CommsError("NOT_FOUND")
    return Container(*row)


def containers_since(conn: Any, account_id: int, since: datetime) -> int:
    """How many containers the account created at or after ``since`` (the 400 budget)."""
    row = conn.execute(
        "SELECT count(*) FROM instagram_containers WHERE account_id = ? AND created_at >= ?",
        (account_id, timeutil.iso(since)),
    ).fetchone()
    return int(row[0])


def mark_container(conn: Any, ref: str, status: str, media_ref: str | None = None) -> None:
    if status not in _STATUSES:
        raise CommsError("INVALID_ARGUMENT")
    with write_tx(conn):
        conn.execute(
            "UPDATE instagram_containers SET status = ?, media_ref = coalesce(?, media_ref)"
            " WHERE ref = ?",
            (status, media_ref, ref),
        )
