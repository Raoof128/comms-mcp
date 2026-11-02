"""The Pinterest analytics tables (proposed A50, section 7; D-P9): data only, no network.

The metric names and filters come from the official OpenAPI description (``StandardPinMetricTypes``,
``VideoPinMetricTypes``, the account's ``QuerymetrictypesItems`` and query enums, v5 ``5.28.0``).
``pin_params`` and ``account_params`` turn a tool's arguments into the query Pinterest accepts, or
raise ``ValueError``: dates are ``YYYY-MM-DD``, in order, at most 90 days back and 90 days wide.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

__all__ = [
    "ACCOUNT_METRICS",
    "APP_TYPES",
    "CLAIMED",
    "CONTENT_TYPES",
    "DATA_STATUSES",
    "LOOKBACK_DAYS",
    "PIN_FORMATS",
    "PIN_METRICS",
    "SOURCES",
    "SPAN_DAYS",
    "account_params",
    "pin_params",
]

PIN_METRICS = (
    "IMPRESSION",
    "OUTBOUND_CLICK",
    "PIN_CLICK",
    "SAVE",
    "SAVE_RATE",
    "TOTAL_COMMENTS",
    "TOTAL_REACTIONS",
    "USER_FOLLOW",
    "PROFILE_VISIT",
    "VIDEO_MRC_VIEW",
    "VIDEO_10S_VIEW",
    "QUARTILE_95_PERCENT_VIEW",
    "VIDEO_V50_WATCH_TIME",
    "VIDEO_START",
    "VIDEO_AVG_WATCH_TIME",
)
ACCOUNT_METRICS = (
    "ENGAGEMENT",
    "ENGAGEMENT_RATE",
    "IMPRESSION",
    "OUTBOUND_CLICK",
    "OUTBOUND_CLICK_RATE",
    "PIN_CLICK",
    "PIN_CLICK_RATE",
    "SAVE",
    "SAVE_RATE",
)
APP_TYPES = ("ALL", "MOBILE", "TABLET", "WEB")
CLAIMED = ("BOTH", "CLAIMED", "OTHER")
PIN_FORMATS = (
    "ALL",
    "ORGANIC_IMAGE",
    "ORGANIC_PRODUCT",
    "ORGANIC_VIDEO",
    "ADS_STANDARD",
    "ADS_PRODUCT",
    "ADS_VIDEO",
    "ADS_IDEA",
)
CONTENT_TYPES = ("ALL", "PAID", "ORGANIC")
SOURCES = ("ALL", "YOUR_PINS", "OTHER_PINS")
DATA_STATUSES = (
    "PROCESSING",
    "READY",
    "ESTIMATE",
    "BEFORE_BUSINESS_CREATED",
    "BEFORE_DATA_RETENTION_PERIOD",
    "BEFORE_PIN_DATA_RETENTION_PERIOD",
    "BEFORE_METRIC_START_DATE",
    "BEFORE_CORE_METRIC_START_DATE",
    "BEFORE_PIN_FORMAT_METRIC_START_DATE",
    "BEFORE_AUDIENCE_METRIC_START_DATE",
    "BEFORE_AUDIENCE_MONTHLY_METRIC_START_DATE",
    "BEFORE_VIDEO_METRIC_START_DATE",
    "BEFORE_CONVERSION_METRIC_START_DATE",
    "PURCHASERS_METRIC_SMALLER_THAN_THRESHOLD",
    "IN_BAD_TAG_DATE",
    "BEFORE_PUBLISHED_METRIC_START_DATE",
    "BEFORE_ASSIST_METRIC_START_DATE",
    "BEFORE_PIN_CREATED",
    "BEFORE_ACCOUNT_CLAIMED",
    "BEFORE_DEMOGRAPHIC_FILTERS_START_DATE",
    "AUDIENCE_SEGMENT_SMALLER_THAN_THRESHOLD",
    "AUDIENCE_TOTAL_SMALLER_THAN_THRESHOLD",
    "BEFORE_PRODUCT_GROUP_FILTER_START_DATE",
)
LOOKBACK_DAYS = 90
SPAN_DAYS = 90
_DATE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


def _date(value: object) -> date:
    if not isinstance(value, str) or not _DATE.match(value):
        raise ValueError("date refused")
    return date.fromisoformat(value)


def _range(args: Mapping[str, Any], today: date) -> tuple[str, str]:
    start, end = _date(args.get("start_date")), _date(args.get("end_date"))
    if start > end or end > today:
        raise ValueError("dates out of order")
    if today - start > timedelta(days=LOOKBACK_DAYS) or end - start > timedelta(days=SPAN_DAYS):
        raise ValueError("dates out of range")
    return start.isoformat(), end.isoformat()


def _metrics(value: object, allowed: Sequence[str], *, required: bool) -> str | None:
    if value is None:
        if required:
            raise ValueError("metrics required")
        return None
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= len(allowed)
        or len(set(value)) != len(value)
        or any(m not in allowed for m in value)
    ):
        raise ValueError("metrics refused")
    return ",".join(value)


def _choice(value: object, allowed: Sequence[str], default: str) -> str:
    if value is None:
        return default
    if value not in allowed:
        raise ValueError("filter refused")
    return str(value)


def pin_params(args: Mapping[str, Any], *, today: date) -> dict[str, str]:
    """The query for ``GET /v5/pins/{id}/analytics``."""
    start, end = _range(args, today)
    metrics = _metrics(args.get("metric_types"), PIN_METRICS, required=True)
    assert metrics is not None
    return {
        "start_date": start,
        "end_date": end,
        "metric_types": metrics,
        "app_types": _choice(args.get("app_types"), APP_TYPES, "ALL"),
        "split_field": "NO_SPLIT",
    }


def account_params(args: Mapping[str, Any], *, today: date) -> dict[str, str]:
    """The query for ``GET /v5/user_account/analytics``."""
    start, end = _range(args, today)
    params = {
        "start_date": start,
        "end_date": end,
        "from_claimed_content": _choice(args.get("from_claimed_content"), CLAIMED, "BOTH"),
        "pin_format": _choice(args.get("pin_format"), PIN_FORMATS, "ALL"),
        "app_types": _choice(args.get("app_types"), APP_TYPES, "ALL"),
        "content_type": _choice(args.get("content_type"), CONTENT_TYPES, "ALL"),
        "source": _choice(args.get("source"), SOURCES, "ALL"),
        "split_field": "NO_SPLIT",
    }
    metrics = _metrics(args.get("metric_types"), ACCOUNT_METRICS, required=False)
    if metrics is not None:
        params["metric_types"] = metrics
    return params
