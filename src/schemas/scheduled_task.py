"""Stable domain values for persisted scheduled tasks."""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEDULED_TASK_SCHEMA_VERSION = 1
SCHEDULED_TASK_POLL_INTERVAL_SECONDS = 30
SCHEDULED_TASK_RETRY_DELAY_SECONDS = 30
_DAILY_TIME_PATTERN = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")


class ScheduledTaskType(str, Enum):
    """Task kinds supported by the first scheduling contract."""

    STOCK_ANALYSIS = "stock_analysis"


class ScheduleKind(str, Enum):
    """Recurrence kinds supported by schema version 1."""

    DAILY = "daily"


class NonTradingDayPolicy(str, Enum):
    """Explicit behavior when the selected market has no session."""

    SKIP = "skip"
    RUN = "run"


class ScheduledRunStatus(str, Enum):
    """Aggregate state of one persisted schedule occurrence."""

    DISPATCHING = "dispatching"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"

    @property
    def terminal(self) -> bool:
        return self in {
            ScheduledRunStatus.SUCCEEDED,
            ScheduledRunStatus.FAILED,
            ScheduledRunStatus.SKIPPED,
            ScheduledRunStatus.INTERRUPTED,
        }


ACTIVE_SCHEDULED_RUN_STATUSES = (
    ScheduledRunStatus.DISPATCHING.value,
    ScheduledRunStatus.RUNNING.value,
    ScheduledRunStatus.RETRY_WAIT.value,
)


def validate_daily_time(value: str) -> str:
    """Return a canonical HH:MM value or raise a stable validation error."""
    candidate = str(value or "").strip()
    if not _DAILY_TIME_PATTERN.fullmatch(candidate):
        raise ValueError("schedule time must use 24-hour HH:MM format")
    return candidate


def validate_timezone(value: str) -> str:
    """Return a usable IANA timezone name."""
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("schedule timezone must not be blank")
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("schedule timezone must be a valid IANA timezone") from exc
    return candidate


def as_utc_naive(value: datetime) -> datetime:
    """Normalize a datetime to the UTC-naive storage convention."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def as_utc_aware(value: datetime) -> datetime:
    """Normalize a storage datetime to an aware UTC value."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def next_daily_run_at(
    *,
    schedule_time: str,
    timezone_name: str,
    after: datetime,
) -> datetime:
    """Return the first daily occurrence strictly after ``after`` in UTC."""
    canonical_time = validate_daily_time(schedule_time)
    canonical_timezone = validate_timezone(timezone_name)
    after_utc = as_utc_aware(after)
    local_after = after_utc.astimezone(ZoneInfo(canonical_timezone))
    hour, minute = (int(part) for part in canonical_time.split(":"))
    candidate = datetime.combine(
        local_after.date(),
        time(hour=hour, minute=minute),
        tzinfo=ZoneInfo(canonical_timezone),
    )
    if candidate <= local_after:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def scheduled_local_date(
    scheduled_for: datetime,
    *,
    timezone_name: str,
):
    """Return the calendar date represented by a UTC schedule occurrence."""
    canonical_timezone = validate_timezone(timezone_name)
    return as_utc_aware(scheduled_for).astimezone(
        ZoneInfo(canonical_timezone)
    ).date()


__all__ = [
    "ACTIVE_SCHEDULED_RUN_STATUSES",
    "NonTradingDayPolicy",
    "SCHEDULED_TASK_POLL_INTERVAL_SECONDS",
    "SCHEDULED_TASK_RETRY_DELAY_SECONDS",
    "SCHEDULED_TASK_SCHEMA_VERSION",
    "ScheduleKind",
    "ScheduledRunStatus",
    "ScheduledTaskType",
    "as_utc_aware",
    "as_utc_naive",
    "next_daily_run_at",
    "scheduled_local_date",
    "validate_daily_time",
    "validate_timezone",
]
