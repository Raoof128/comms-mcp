"""The Instagram insights tables and their validation (proposed A49, section 7) ✅ 🔧.

Meta answers an unsupported metric or breakdown combination with "An unknown error has
occurred", so a request is checked here first and asks for one metric group at a time.

Media (period always ``lifetime``; this path cannot read ``media_product_type``, so a group is
checked against ``media_type``):

- ``common``: Feed and Reels.
- ``feed``: Feed and Story only (the gauntlet's correction): never for a video, which may be a
  Reel; ``impressions`` only for media created before 2 July 2024.
- ``reels``: Reels only, so only for a ``VIDEO``.
- ``crossposted_views`` and ``facebook_views`` throw for a reel not shared to Facebook and are
  never requested; ``engagement`` does not exist.

Account: ``period=day``; the demographics are ``lifetime`` with a ``timeframe`` of ``this_week``
or ``this_month`` (the others are unsupported since v20.0); only ``reach`` has
``time_series``; a breakdown only with ``total_value``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from comms.core.providers.instagram_insights import (
    ACCOUNT_METRICS,
    BREAKDOWNS,
    DEMOGRAPHIC_BREAKDOWNS,
    DEMOGRAPHICS,
    IMPRESSIONS_BEFORE,
    MEDIA_GROUPS,
    MEDIA_METRICS,
    TIME_SERIES,
    TIMEFRAMES,
)

__all__ = ["account_params", "media_params"]


def _group(metrics: Sequence[str]) -> str:
    groups = {name for name, members in MEDIA_GROUPS.items() if set(metrics) & members}
    if not metrics or set(metrics) - MEDIA_METRICS or len(groups - {"common"}) > 1:
        raise ValueError("one metric group per request")
    return (groups - {"common"}).pop() if groups - {"common"} else "common"


def media_params(
    metrics: Sequence[str], media_type: str, created: datetime, breakdown: str | None
) -> dict[str, str]:
    """The query for ``GET /<media>/insights``; ``ValueError`` for a combination Meta refuses."""
    group = _group(metrics)
    if group == "reels" and media_type != "VIDEO":
        raise ValueError("Reels metrics need a video")
    if group == "feed" and media_type == "VIDEO":
        raise ValueError("Feed-only metrics are refused for a video, which may be a Reel")
    if "impressions" in metrics and created >= IMPRESSIONS_BEFORE:
        raise ValueError("impressions exist only for media created before 2 July 2024")
    if breakdown is not None and (
        breakdown != "action_type" or list(metrics) != ["profile_activity"]
    ):
        raise ValueError("action_type breaks down profile_activity alone")
    params = {"metric": ",".join(metrics)}
    if breakdown is not None:
        params["breakdown"] = breakdown
    return params


def account_params(args: dict[str, Any]) -> dict[str, str]:
    """The query for ``GET /<IG_ID>/insights``; ``ValueError`` for what Meta refuses."""
    metrics = list(args.get("metrics") or ())
    metric_type = args.get("metric_type", "total_value")
    breakdown, timeframe = args.get("breakdown"), args.get("timeframe")
    if not metrics or set(metrics) - ACCOUNT_METRICS or len(metrics) != len(set(metrics)):
        raise ValueError("unknown or repeated metric")
    demographic = set(metrics) & DEMOGRAPHICS
    if demographic and set(metrics) - DEMOGRAPHICS:
        raise ValueError("demographics are requested alone")
    if metric_type not in ("total_value", "time_series"):
        raise ValueError("metric_type")
    if metric_type == "time_series" and (set(metrics) - TIME_SERIES or breakdown is not None):
        raise ValueError("only reach has a time series, and never with a breakdown")
    if breakdown is not None and breakdown not in BREAKDOWNS:
        raise ValueError("breakdown")
    if demographic:
        if timeframe not in TIMEFRAMES or breakdown not in DEMOGRAPHIC_BREAKDOWNS:
            raise ValueError("demographics need this_week or this_month and a breakdown")
        params = {"metric": ",".join(metrics), "period": "lifetime", "metric_type": "total_value",
                  "timeframe": timeframe, "breakdown": breakdown}  # fmt: skip
        return params
    if timeframe is not None or breakdown in DEMOGRAPHIC_BREAKDOWNS:
        raise ValueError("timeframe and demographic breakdowns are for demographics")
    params = {"metric": ",".join(metrics), "period": "day", "metric_type": metric_type}
    if breakdown is not None:
        params["breakdown"] = breakdown
    for key in ("since", "until"):
        value = args.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(key)
            params[key] = str(value)
    return params
