"""The typed egress matrix (comms v0.3 Task D36; A44, G19): what each tool's output may carry.

Every tool declares its content classes, and the sweep holds the running system to them:

- ``refs`` — opaque refs, states, counts, digests, times: every tool.
- ``body`` — provider message text, only inside ``untrusted_text``: the content reads.
- ``names`` — provider display names, only inside ``untrusted``: reads that list people.
- ``identity`` — a provider identity (a phone number, a chat or user id, an object id): only
  ``comms_admin_identity_inspect``, and only for the ref the owner names.

No tool may carry a secret (a token, a seed, an OAuth code or secret, key material).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from comms.mcp.catalog import TOOL_CATALOG

__all__ = ["CLASSES", "EGRESS_MATRIX"]

CLASSES = frozenset({"refs", "body", "names", "identity"})
_BODY = frozenset(
    {
        "comms_context_get",
        "comms_context_recent",
        "comms_context_around_message",
        "comms_context_thread",
        "comms_context_search",
        "comms_context_page",
        "comms_message_get",
        "comms_message_recent",
        "comms_message_search",
        "comms_message_context",
        "comms_group_context",
        "comms_context_person",  # G5
        "comms_instagram_media_list",  # proposed A49: captions, comments, DMs
        "comms_instagram_media_get",  # proposed A49: captions, comments, DMs
        "comms_instagram_story_list",  # proposed A49: captions, comments, DMs
        "comms_instagram_comment_list",  # proposed A49: captions, comments, DMs
        "comms_instagram_comment_replies",  # proposed A49: captions, comments, DMs
        "comms_instagram_tag_list",  # proposed A49: captions, comments, DMs
        "comms_instagram_conversation_messages",  # proposed A49: captions, comments, DMs
        "comms_instagram_publish_preview",  # proposed A49: captions, comments, DMs
        # proposed A50: board descriptions and Pin descriptions
        "comms_pinterest_board_list",
        "comms_pinterest_board_get",
        "comms_pinterest_board_pins",
        "comms_pinterest_pin_list",
        "comms_pinterest_pin_get",
        "comms_pinterest_pin_preview",
    }
)
_PINTEREST_NAMES = frozenset(
    {  # proposed A50: every Pinterest tool echoes the account's username; boards their names
        "comms_pinterest_account_list",
        "comms_pinterest_whoami",
        "comms_pinterest_profile_get",
        "comms_pinterest_board_list",
        "comms_pinterest_board_get",
        "comms_pinterest_board_pins",
        "comms_pinterest_pin_list",
        "comms_pinterest_pin_get",
        "comms_pinterest_pin_analytics",
        "comms_pinterest_account_analytics",
        "comms_pinterest_media_status",
        "comms_pinterest_publish_quota",
        "comms_pinterest_pin_preview",
        "comms_pinterest_board_create",
        "comms_pinterest_video_upload",
        "comms_pinterest_pin_create",
        "comms_pinterest_pin_update",
        "comms_pinterest_pin_delete",
    }
)
_NAMES = frozenset(
    {
        "comms_group_members_list",
        "comms_group_admins_list",
        "comms_context_get",
        "comms_group_context",
        # catalog amendment G2: people's labels, owner-typed but model-visible
        "comms_directory_recipient_list",
        "comms_directory_recipient_get",
        "comms_context_person",  # G5: senders' names, under untrusted
        "comms_group_join_requests_list",  # G6: requesters' names, under untrusted
        "comms_group_invite_list",  # G6: invite links' names
        "comms_group_topic_list",  # G6: topic names
        "comms_group_topic_get",
        "comms_account_profile",  # G8: what each account calls itself
        "comms_whatsapp_health_status",  # A46: Meta's notes
        "comms_instagram_account_list",  # proposed A49: usernames and labels
        "comms_instagram_whoami",  # proposed A49: usernames and labels
        "comms_instagram_profile_get",  # proposed A49: usernames and labels
        "comms_instagram_media_list",  # proposed A49: usernames and labels
        "comms_instagram_media_get",  # proposed A49: usernames and labels
        "comms_instagram_media_insights",  # proposed A49: usernames and labels
        "comms_instagram_account_insights",  # proposed A49: usernames and labels
        "comms_instagram_story_list",  # proposed A49: usernames and labels
        "comms_instagram_story_insights",  # proposed A49: usernames and labels
        "comms_instagram_comment_list",  # proposed A49: usernames and labels
        "comms_instagram_comment_replies",  # proposed A49: usernames and labels
        "comms_instagram_tag_list",  # proposed A49: usernames and labels
        "comms_instagram_conversation_list",  # proposed A49: usernames and labels
        "comms_instagram_conversation_messages",  # proposed A49: usernames and labels
        "comms_instagram_publish_quota",  # proposed A49: usernames and labels
        "comms_instagram_publish_preview",  # proposed A49: usernames and labels
        "comms_instagram_container_create",  # proposed A49: the account's username
        "comms_instagram_carousel_create",  # proposed A49: the account's username
        "comms_instagram_publish",  # proposed A49: the account's username
        "comms_instagram_comment_reply",  # proposed A49: the account's username
        "comms_instagram_comment_hide",  # proposed A49: the account's username
        "comms_instagram_comments_enabled_set",  # proposed A49: the account's username
        "comms_instagram_comment_delete",  # proposed A49: the account's username
        "comms_instagram_message_send",  # proposed A49: the account's username
        *_PINTEREST_NAMES,
    }
)
_IDENTITY = frozenset({"comms_admin_identity_inspect"})


def _classes(name: str) -> frozenset[str]:
    classes = {"refs"}
    if name in _BODY:
        classes.add("body")
    if name in _NAMES:
        classes.add("names")
    if name in _IDENTITY:
        classes.add("identity")
    return frozenset(classes)


EGRESS_MATRIX: Mapping[str, frozenset[str]] = MappingProxyType(
    {spec.name: _classes(spec.name) for spec in TOOL_CATALOG}
)
