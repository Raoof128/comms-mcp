"""The Pinterest tables (proposed A50, section 4.1; schema v12): accounts, object refs, the video
uploads, and the publication ledger.

An account binds a ``pna_`` to its alias and Pinterest user id once and for all (a trigger
refuses a change; a removed account keeps its row). An object row is one ``pnb_`` or ``pnp_``
per (account, kind, provider identity), stable across restarts. A media row is one ``pnv_`` per
video upload comms made. A publication row is one Pin ``pin_create`` made: the daily budget's
ledger. Identities live only inside SQLCipher ``comms.db`` and never in a ``repr``;
``comms.core.identities`` is their one reader for the owner. Every write here runs in the
caller's transaction or its own ``write_tx``, never nested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from comms.core import refs, timeutil
from comms.core.errors import CommsError
from comms.core.storage.db import write_tx

__all__ = [
    "MEDIA_STATUSES",
    "Account",
    "Media",
    "account_by_alias",
    "account_by_ref",
    "live_accounts",
    "mark_identity_checked",
    "mark_media",
    "media",
    "media_by_ref",
    "object_ref",
    "publications_since",
    "record_media",
    "record_publication",
    "register_account",
    "remove_account",
    "resolve_object",
    "set_expiry",
]

_KIND_PREFIX = {"board": "pinterest_board", "pin": "pinterest_pin"}
MEDIA_STATUSES = frozenset({"registered", "processing", "succeeded", "failed"})


@dataclass(frozen=True)
class Account:
    id: int
    ref: str
    alias: str
    user_id: str = field(repr=False)
    obtained_at: str = ""
    access_expires_at: str = ""
    refresh_expires_at: str = ""
    last_identity_check_at: str | None = None


@dataclass(frozen=True)
class Media:
    id: int
    ref: str
    account_id: int
    media_id: str = field(repr=False)
    created_at: str = ""
    status: str | None = None


_ACCOUNT_COLUMNS = (
    "id, ref, alias, user_id, obtained_at, access_expires_at, refresh_expires_at,"
    " last_identity_check_at"
)
_MEDIA_COLUMNS = "id, ref, account_id, media_id, created_at, status"


def _account(row: Any) -> Account | None:
    return None if row is None else Account(*row)


def account_by_alias(conn: Any, alias: str) -> Account | None:
    row = conn.execute(
        f"SELECT {_ACCOUNT_COLUMNS} FROM pinterest_accounts WHERE alias = ? AND removed_at IS NULL",
        (alias,),
    ).fetchone()
    return _account(row)


def account_by_ref(conn: Any, ref: str) -> Account | None:
    row = conn.execute(
        f"SELECT {_ACCOUNT_COLUMNS} FROM pinterest_accounts WHERE ref = ? AND removed_at IS NULL",
        (ref,),
    ).fetchone()
    return _account(row)


def live_accounts(conn: Any) -> list[Account]:
    rows = conn.execute(
        f"SELECT {_ACCOUNT_COLUMNS} FROM pinterest_accounts WHERE removed_at IS NULL ORDER BY alias"
    ).fetchall()
    return [Account(*row) for row in rows]


def register_account(
    conn: Any,
    alias: str,
    user_id: str,
    *,
    now: datetime,
    access_lifetime: timedelta,
    refresh_lifetime: timedelta,
) -> str:
    """In the caller's audited transaction: a new ``pna_`` for a live alias and user id."""
    stamp = timeutil.iso(now)
    ref = refs.mint("pinterest_account")
    conn.execute(
        "INSERT INTO pinterest_accounts (ref, alias, user_id, obtained_at, access_expires_at,"
        " refresh_expires_at, last_identity_check_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ref,
            alias,
            user_id,
            stamp,
            timeutil.iso(now + access_lifetime),
            timeutil.iso(now + refresh_lifetime),
            stamp,
            stamp,
        ),
    )
    return ref


def remove_account(conn: Any, ref: str, *, now: datetime) -> None:
    """In the caller's audited transaction."""
    conn.execute(
        "UPDATE pinterest_accounts SET removed_at = ? WHERE ref = ? AND removed_at IS NULL",
        (timeutil.iso(now), ref),
    )


def set_expiry(
    conn: Any,
    ref: str,
    *,
    now: datetime,
    access_lifetime: timedelta,
    refresh_lifetime: timedelta | None,
) -> None:
    """In the caller's audited transaction: the refreshed tokens' lifetimes from now (the
    refresh token's only when Pinterest answered a new one)."""
    conn.execute(
        "UPDATE pinterest_accounts SET obtained_at = ?, access_expires_at = ?,"
        " refresh_expires_at = coalesce(?, refresh_expires_at) WHERE ref = ?",
        (
            timeutil.iso(now),
            timeutil.iso(now + access_lifetime),
            None if refresh_lifetime is None else timeutil.iso(now + refresh_lifetime),
            ref,
        ),
    )


def mark_identity_checked(conn: Any, ref: str, *, now: datetime) -> None:
    with write_tx(conn):
        conn.execute(
            "UPDATE pinterest_accounts SET last_identity_check_at = ? WHERE ref = ?",
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
            "SELECT id, ref FROM pinterest_objects WHERE account_id = ? AND kind = ?"
            " AND provider_identity = ?",
            (account_id, kind, identity),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE pinterest_objects SET last_seen_at = ? WHERE id = ?", (stamp, row[0])
            )
            return str(row[1])
        ref = refs.mint(_KIND_PREFIX[kind])
        conn.execute(
            "INSERT INTO pinterest_objects (ref, account_id, kind, provider_identity, created_at,"
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
        "SELECT provider_identity FROM pinterest_objects WHERE ref = ? AND kind = ?"
        " AND account_id = ?",
        (ref, kind, account_id),
    ).fetchone()
    if row is None:
        raise CommsError("NOT_FOUND")
    return str(row[0])


# -- video uploads -----------------------------------------------------------------------------


def record_media(conn: Any, account_id: int, media_id: str, *, now: datetime, status: str) -> str:
    """One ``pnv_`` per upload comms registered, in its own transaction (an executor
    ``on_created``)."""
    if status not in MEDIA_STATUSES:
        raise CommsError("INVALID_ARGUMENT")
    with write_tx(conn):
        row = conn.execute(
            "SELECT ref FROM pinterest_media WHERE account_id = ? AND media_id = ?",
            (account_id, media_id),
        ).fetchone()
        if row is not None:
            return str(row[0])
        ref = refs.mint("pinterest_media")
        conn.execute(
            "INSERT INTO pinterest_media (ref, account_id, media_id, created_at, status)"
            " VALUES (?, ?, ?, ?, ?)",
            (ref, account_id, media_id, timeutil.iso(now), status),
        )
    return ref


def media(conn: Any, ref: object, account_id: int) -> Media:
    try:
        refs.check(ref, "pinterest_media")
    except ValueError:
        raise CommsError("INVALID_ARGUMENT") from None
    row = conn.execute(
        f"SELECT {_MEDIA_COLUMNS} FROM pinterest_media WHERE ref = ? AND account_id = ?",
        (ref, account_id),
    ).fetchone()
    if row is None:
        raise CommsError("NOT_FOUND")
    return Media(*row)


def media_by_ref(conn: Any, ref: str) -> Media | None:
    row = conn.execute(
        f"SELECT {_MEDIA_COLUMNS} FROM pinterest_media WHERE ref = ?", (ref,)
    ).fetchone()
    return None if row is None else Media(*row)


def mark_media(conn: Any, ref: str, status: str) -> None:
    if status not in MEDIA_STATUSES:
        raise CommsError("INVALID_ARGUMENT")
    with write_tx(conn):
        conn.execute("UPDATE pinterest_media SET status = ? WHERE ref = ?", (status, ref))


# -- the publication ledger --------------------------------------------------------------------


def record_publication(conn: Any, account_id: int, pin_ref: str, *, now: datetime) -> None:
    """One row per Pin ``pin_create`` made, in its own transaction; a repeat is a no-op."""
    with write_tx(conn):
        row = conn.execute(
            "SELECT id FROM pinterest_objects WHERE ref = ? AND account_id = ? AND kind = 'pin'",
            (pin_ref, account_id),
        ).fetchone()
        if row is None:
            raise CommsError("NOT_FOUND")
        conn.execute(
            "INSERT OR IGNORE INTO pinterest_publications (account_id, object_id, created_at)"
            " VALUES (?, ?, ?)",
            (account_id, row[0], timeutil.iso(now)),
        )


def publications_since(conn: Any, account_id: int, since: datetime) -> int:
    """How many Pins comms created for the account at or after ``since`` (the budget)."""
    row = conn.execute(
        "SELECT count(*) FROM pinterest_publications WHERE account_id = ? AND created_at >= ?",
        (account_id, timeutil.iso(since)),
    ).fetchone()
    return int(row[0])
