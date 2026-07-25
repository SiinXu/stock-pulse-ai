"""Stable domain values for persisted scheduled tasks."""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEDULED_TASK_SCHEMA_VERSION = 1
SCHEDULED_TASK_POLL_INTERVAL_SECONDS = 30
SCHEDULED_TASK_RETRY_DELAY_SECONDS = 30
SCHEDULED_NOTIFICATION_STATUSES = frozenset({
    "not_requested",
    "ok",
    "degraded",
    "failed",
    "skipped",
    "not_configured",
    "unknown",
})
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
    schedule_timezone = ZoneInfo(canonical_timezone)
    local_after = after_utc.astimezone(schedule_timezone)
    hour, minute = (int(part) for part in canonical_time.split(":"))
    wall_time = time(hour=hour, minute=minute)

    # A local wall time can map to two UTC instants during a fall-back fold, or
    # to no instant during a spring-forward gap. A daily definition runs at most
    # once per local date, so the earliest valid instant is canonical.
    for day_offset in range(4):
        wall_datetime = datetime.combine(
            local_after.date() + timedelta(days=day_offset),
            wall_time,
        )
        valid_instants = set()
        for fold in (0, 1):
            local_candidate = wall_datetime.replace(
                tzinfo=schedule_timezone,
                fold=fold,
            )
            candidate_utc = local_candidate.astimezone(timezone.utc)
            round_trip = candidate_utc.astimezone(schedule_timezone)
            if round_trip.replace(tzinfo=None) == wall_datetime:
                valid_instants.add(candidate_utc)
        if valid_instants:
            candidate_utc = min(valid_instants)
            if candidate_utc > after_utc:
                return candidate_utc.replace(tzinfo=None)

    raise RuntimeError("Unable to resolve the next daily schedule occurrence")


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
    "SCHEDULED_NOTIFICATION_STATUSES",
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
