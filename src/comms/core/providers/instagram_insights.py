"""The Instagram insights tables (proposed A49, section 7) ✅ 🔧: data only.

One copy, in core, because both the MCP catalog (its enums) and the Instagram adapter (its
validation) read them, and the MCP package never imports an adapter. The adapter's insights
module states the rules these tables encode.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = [
    "ACCOUNT_METRICS",
    "BREAKDOWNS",
    "DEMOGRAPHICS",
    "DEMOGRAPHIC_BREAKDOWNS",
    "IMPRESSIONS_BEFORE",
    "MEDIA_GROUPS",
    "MEDIA_METRICS",
    "TIMEFRAMES",
    "TIME_SERIES",
]

MEDIA_GROUPS: dict[str, frozenset[str]] = {
    "common": frozenset(
        {"reach", "views", "likes", "comments", "saved", "shares", "reposts", "total_interactions"}
    ),
    "feed": frozenset({"follows", "profile_visits", "profile_activity", "impressions"}),
    "reels": frozenset(
        {"ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "reels_skip_rate"}
    ),
}
MEDIA_METRICS = frozenset().union(*MEDIA_GROUPS.values())
IMPRESSIONS_BEFORE = datetime(2024, 7, 2, tzinfo=UTC)

DEMOGRAPHICS = frozenset({"follower_demographics", "engaged_audience_demographics"})
ACCOUNT_METRICS = frozenset(
    {
        "accounts_engaged",
        "comments",
        "likes",
        "profile_links_taps",
        "reach",
        "replies",
        "reposts",
        "saves",
        "shares",
        "total_interactions",
        "views",
        "follows_and_unfollows",
        *DEMOGRAPHICS,
    }
)
TIME_SERIES = frozenset({"reach"})
TIMEFRAMES = frozenset({"this_week", "this_month"})
# follow_type and follower_type: Meta's own page spells it both ways (gate GI-5 decides).
BREAKDOWNS = frozenset(
    {"contact_button_type", "follow_type", "follower_type", "media_product_type", "age", "city",
     "country", "gender"}
)  # fmt: skip
DEMOGRAPHIC_BREAKDOWNS = frozenset({"age", "city", "country", "gender"})
