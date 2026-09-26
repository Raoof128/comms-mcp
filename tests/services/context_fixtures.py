"""Shared context-engine test doubles (D8, D10, D11): a paging source and a clock."""

from comms.core.providers.protocols import ContextPage, ContextRefused


class Source:
    """A context source double: pages of message items, every call counted."""

    def __init__(self, provenance="telegram_live", per_page=3, pages=100, refuse=None):
        self.provenance, self.per_page, self.pages, self.refuse = (
            provenance,
            per_page,
            pages,
            refuse,
        )
        self.queries = []

    def read(self, query):
        self.queries.append(query)
        if self.refuse:
            raise ContextRefused(self.refuse)
        stamp = {"source": self.provenance, "observed_at": "2026-09-25T00:00:00.000000Z"}
        if query.kind == "member":  # G6: the real sources' shapes
            item = {**stamp, "user_id": int(query.args["user_id"]), "role": "member",
                    "status": "member"}  # fmt: skip
            return ContextPage((item,), self.provenance)
        if query.kind == "permissions":
            item = {**stamp, "permissions": {"can_send_messages": True, "can_pin_messages": False}}
            return ContextPage((item,), self.provenance)
        if query.kind == "admins":
            item = {**stamp, "user_id": 42, "role": "creator", "untrusted": {"name": "Ali"}}
            return ContextPage((item,), self.provenance)
        if query.kind in ("invites", "join_requests", "topics", "topic", "admin_log"):
            item = {  # G6: the user source's list shapes, provider ids included
                "invites": {"link": "https://t.me/+AbCdEf", "usage": 2, "usage_limit": None,
                            "expires_at": None, "revoked": False, "primary": True,
                            "request_needed": False, "requested": None,
                            "untrusted": {"title": "Main"}},
                "join_requests": {"user_id": 908180, "requested_at": "2026-09-25T00:00:00Z",
                                  "untrusted": {"name": "Ali"}},
                "topics": {"topic_id": 9, "closed": False, "pinned": True, "hidden": False,
                           "untrusted": {"name": "Events"}},
                "topic": {"topic_id": 9, "closed": True, "untrusted": {"name": "Events"}},
                "admin_log": {"event_id": 50, "at": "2026-09-25T00:00:00Z", "user_id": 908180,
                              "action": "ChannelAdminLogEventActionChangeTitle"},
            }[query.kind]  # fmt: skip
            return ContextPage(({**stamp, **item},), self.provenance)
        start = int(query.args.get("cursor") or 1000)
        items = tuple(
            {
                "source": self.provenance,
                "observed_at": "2026-09-25T00:00:00.000000Z",
                "message_id": start - i,
                "sent_at": "2026-09-24T12:00:00Z",
                "sender_id": "42",
                "chat_id": query.target.identity,
                "untrusted": {"text": f"hello {start - i}", "sender_name": "Ali"},
            }
            for i in range(self.per_page)
        )
        more = len(self.queries) < self.pages
        return ContextPage(items, self.provenance, str(start - self.per_page) if more else None)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t
