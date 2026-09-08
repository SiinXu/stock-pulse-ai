# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Library-only memory CONSOLIDATION policy (#1119 Slice 3).

Resolves deterministic per-symbol compression of old episodic rows into one
compact ``mode=consolidate`` summary over the existing ``agent_episodes``
store. This library does not create tables, does not UPDATE append-only
episodes, and does not write predictions, decision-memory outcomes, Soul
text, user-note facts, or sidecar opinion/label tables. Persist-path
consolidation (not this module) inserts the admitted summary and a
metadata-only ``episode.consolidate`` EvolutionEvent in the same delete
transaction.

No-policy (missing symbol scope, or neither cutoff nor max_rows) never
writes. Invalid policy fails closed and is never coerced into an unscoped
purge. Callers must not treat ``None`` / bare ``False`` as a decision.
Fewer than two source rows is a persist-path no-op so existing forgetting
can still drop leftovers.

Out of slice: Decision Memory retrieval-score decay, the #1118 layered
store, auto-promotion, new env keys, migrations, public API / Web /
Desktop CRUD, semantic/procedural persistence, and Soul edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence
import uuid

from src.schemas.agent_episode import (
    AGENT_EPISODE_MAX_LESSONS,
    AGENT_EPISODE_MAX_MAX_ROWS,
    AGENT_EPISODE_MAX_RETENTION_DAYS,
    AGENT_EPISODE_MIN_RETENTION_DAYS,
    AgentEpisodeCreate,
    EpisodeLesson,
    EpisodeOutcomeLabels,
)
from src.schemas.memory_write_policy import require_episodic_write

ERROR_CONSOLIDATE_INVALID_SYMBOL = "memory_consolidate_invalid_symbol"
ERROR_CONSOLIDATE_INVALID_CUTOFF = "memory_consolidate_invalid_cutoff"
ERROR_CONSOLIDATE_INVALID_RETENTION_DAYS = "memory_consolidate_invalid_retention_days"
ERROR_CONSOLIDATE_INVALID_MAX_ROWS = "memory_consolidate_invalid_max_rows"
ERROR_CONSOLIDATE_INVALID_NOW = "memory_consolidate_invalid_now"
ERROR_CONSOLIDATE_AMBIGUOUS_CUTOFF = "memory_consolidate_ambiguous_cutoff"
ERROR_CONSOLIDATE_UNSCOPED = "memory_consolidate_unscoped"
ERROR_CONSOLIDATE_INVALID_DRY_RUN = "memory_consolidate_invalid_dry_run"
ERROR_CONSOLIDATE_INVALID_POLICY = "memory_consolidate_invalid_policy"
ERROR_CONSOLIDATE_INVALID_SOURCES = "memory_consolidate_invalid_sources"
EPISODE_CONSOLIDATE_EVENT_TYPE = "episode.consolidate"
EPISODE_CONSOLIDATE_MODE = "consolidate"
CONSOLIDATE_MIN_SOURCE_ROWS = 2


class MemoryConsolidateError(ValueError):
    """Typed rejection for an invalid or unscoped episode consolidate policy."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class EpisodeConsolidateDecision:
    """Typed consolidate decision. Never replaced with ``None`` or bare ``False``."""

    apply: bool
    symbol: Optional[str] = None
    cutoff: Optional[datetime] = None
    max_rows: Optional[int] = None
    dry_run: bool = False
    error_code: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class EpisodeConsolidateResult:
    """Audit result of a consolidate pass. Counts are authoritative, not inferred.

    ``remaining_count`` is always a live COUNT for the resolved scope: the
    named symbol when present, otherwise the whole table for inactive
    no-policy. It is never reported as zero unless that COUNT is zero.
    ``audit_event_id`` and ``summary_episode_id`` are set only after a durable
    summary insert and EvolutionEvent committed with the source DELETE.
    """

    applied: bool
    symbol: Optional[str]
    deleted_count: int
    remaining_count: int
    cutoff: Optional[datetime] = None
    max_rows: Optional[int] = None
    dry_run: bool = False
    audit_event_id: Optional[str] = None
    summary_episode_id: Optional[str] = None
    source_count: int = 0


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _as_utc_aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise MemoryConsolidateError(
            "consolidate source timestamp must be a datetime",
            error_code=ERROR_CONSOLIDATE_INVALID_SOURCES,
        )
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _strict_positive_int(value: Any, *, minimum: int, maximum: int) -> Optional[int]:
    if type(value) is not int or value < minimum or value > maximum:
        return None
    return value


def _inactive(
    *,
    symbol: Optional[str] = None,
    cutoff: Optional[datetime] = None,
    max_rows: Optional[int] = None,
    dry_run: bool = False,
) -> EpisodeConsolidateDecision:
    return EpisodeConsolidateDecision(
        apply=False,
        symbol=symbol,
        cutoff=cutoff,
        max_rows=max_rows,
        dry_run=dry_run,
    )


def _rejected(
    *,
    error_code: str,
    reason: str,
    symbol: Optional[str] = None,
    cutoff: Optional[datetime] = None,
    max_rows: Optional[int] = None,
    dry_run: bool = False,
) -> EpisodeConsolidateDecision:
    return EpisodeConsolidateDecision(
        apply=False,
        symbol=symbol,
        cutoff=cutoff,
        max_rows=max_rows,
        dry_run=dry_run,
        error_code=error_code,
        reason=reason,
    )


def resolve_episode_consolidate_policy(
    *,
    symbol: Any = None,
    cutoff: Any = None,
    retention_days: Any = None,
    now: Any = None,
    max_rows: Any = None,
    dry_run: Any = False,
) -> EpisodeConsolidateDecision:
    """Resolve a per-symbol consolidate policy. Never returns ``None``."""

    if dry_run is False:
        parsed_dry_run = False
    elif dry_run is True:
        parsed_dry_run = True
    else:
        return _rejected(
            error_code=ERROR_CONSOLIDATE_INVALID_DRY_RUN,
            reason="dry_run must be a boolean",
        )

    parsed_symbol: Optional[str]
    if symbol is None:
        parsed_symbol = None
    elif not isinstance(symbol, str):
        return _rejected(
            error_code=ERROR_CONSOLIDATE_INVALID_SYMBOL,
            reason="consolidate symbol must be a string",
            dry_run=parsed_dry_run,
        )
    else:
        stripped = symbol.strip()
        parsed_symbol = stripped or None

    parsed_cutoff: Optional[datetime] = None
    if cutoff is not None and retention_days is not None:
        return _rejected(
            error_code=ERROR_CONSOLIDATE_AMBIGUOUS_CUTOFF,
            reason="pass cutoff or retention_days, not both",
            symbol=parsed_symbol,
            dry_run=parsed_dry_run,
        )
    if cutoff is not None:
        if not isinstance(cutoff, datetime):
            return _rejected(
                error_code=ERROR_CONSOLIDATE_INVALID_CUTOFF,
                reason="consolidate cutoff must be a datetime",
                symbol=parsed_symbol,
                dry_run=parsed_dry_run,
            )
        parsed_cutoff = _as_utc_naive(cutoff)
    elif retention_days is not None:
        parsed_days = _strict_positive_int(
            retention_days,
            minimum=AGENT_EPISODE_MIN_RETENTION_DAYS,
            maximum=AGENT_EPISODE_MAX_RETENTION_DAYS,
        )
        if parsed_days is None:
            return _rejected(
                error_code=ERROR_CONSOLIDATE_INVALID_RETENTION_DAYS,
                reason="retention_days must be an integer in the configured range",
                symbol=parsed_symbol,
                dry_run=parsed_dry_run,
            )
        if not isinstance(now, datetime):
            return _rejected(
                error_code=ERROR_CONSOLIDATE_INVALID_NOW,
                reason="retention_days requires a datetime clock value",
                symbol=parsed_symbol,
                dry_run=parsed_dry_run,
            )
        parsed_cutoff = _as_utc_naive(now) - timedelta(days=parsed_days)

    parsed_max_rows: Optional[int] = None
    if max_rows is not None:
        parsed_max_rows = _strict_positive_int(
            max_rows,
            minimum=1,
            maximum=AGENT_EPISODE_MAX_MAX_ROWS,
        )
        if parsed_max_rows is None:
            return _rejected(
                error_code=ERROR_CONSOLIDATE_INVALID_MAX_ROWS,
                reason="max_rows must be a positive integer at or below the configured ceiling",
                symbol=parsed_symbol,
                cutoff=parsed_cutoff,
                dry_run=parsed_dry_run,
            )

    has_policy = parsed_cutoff is not None or parsed_max_rows is not None
    if not has_policy:
        return _inactive(
            symbol=parsed_symbol,
            dry_run=parsed_dry_run,
        )
    if parsed_symbol is None:
        return _rejected(
            error_code=ERROR_CONSOLIDATE_UNSCOPED,
            reason="consolidating requires an explicit symbol scope",
            cutoff=parsed_cutoff,
            max_rows=parsed_max_rows,
            dry_run=parsed_dry_run,
        )
    return EpisodeConsolidateDecision(
        apply=True,
        symbol=parsed_symbol,
        cutoff=parsed_cutoff,
        max_rows=parsed_max_rows,
        dry_run=parsed_dry_run,
    )


def require_episode_consolidate_policy(**kwargs: Any) -> EpisodeConsolidateDecision:
    decision = resolve_episode_consolidate_policy(**kwargs)
    if decision.error_code:
        raise MemoryConsolidateError(
            decision.reason or "invalid episode consolidate policy",
            error_code=decision.error_code,
        )
    return decision


def _lesson_fingerprint(lesson: EpisodeLesson) -> tuple[str, str, Optional[str]]:
    return (lesson.kind, lesson.severity, lesson.remedy)


def _compact_lessons(sources: Sequence[Any]) -> list[EpisodeLesson]:
    compact: list[EpisodeLesson] = []
    seen: set[tuple[str, str, Optional[str]]] = set()
    for source in sources:
        lessons = getattr(source, "lessons", None) or []
        for lesson in lessons:
            if not isinstance(lesson, EpisodeLesson):
                try:
                    lesson = EpisodeLesson.model_validate(
                        lesson.model_dump(mode="python")
                        if hasattr(lesson, "model_dump")
                        else lesson
                    )
                except (TypeError, ValueError) as exc:
                    raise MemoryConsolidateError(
                        "consolidate source lesson is invalid",
                        error_code=ERROR_CONSOLIDATE_INVALID_SOURCES,
                    ) from exc
            fingerprint = _lesson_fingerprint(lesson)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            compact.append(
                EpisodeLesson.model_validate(
                    {
                        "kind": lesson.kind,
                        "severity": lesson.severity,
                        "claim_ref": lesson.claim_ref,
                        "remedy": lesson.remedy,
                        "source_step": lesson.source_step,
                    }
                )
            )
            if len(compact) >= AGENT_EPISODE_MAX_LESSONS:
                return compact
    return compact


def _count_extra(sources: Sequence[Any]) -> dict[str, str]:
    success_count = 0
    failure_count = 0
    unknown_count = 0
    for source in sources:
        success = getattr(source, "success", None)
        if success is True:
            success_count += 1
        elif success is False:
            failure_count += 1
        else:
            unknown_count += 1
    extra = {
        "source_count": str(len(sources)),
        "success_count": str(success_count),
        "failure_count": str(failure_count),
    }
    if unknown_count:
        extra["unknown_count"] = str(unknown_count)
    return extra


def _shared_market(sources: Sequence[Any]) -> Optional[str]:
    markets = {
        str(market).strip()
        for market in (getattr(source, "market", None) for source in sources)
        if isinstance(market, str) and market.strip()
    }
    if len(markets) == 1:
        return next(iter(markets))
    return None


def _source_window(sources: Sequence[Any]) -> tuple[Optional[datetime], Optional[datetime]]:
    starts: list[datetime] = []
    ends: list[datetime] = []
    for source in sources:
        started = _as_utc_aware(
            getattr(source, "started_at", None) or getattr(source, "created_at", None)
        )
        completed = _as_utc_aware(
            getattr(source, "completed_at", None) or getattr(source, "created_at", None)
        )
        if started is not None:
            starts.append(started)
        if completed is not None:
            ends.append(completed)
    started_at = min(starts) if starts else None
    completed_at = max(ends) if ends else None
    if started_at is not None and completed_at is not None and completed_at < started_at:
        completed_at = started_at
    return started_at, completed_at


def build_episode_consolidate_summary(
    sources: Sequence[Any],
    *,
    symbol: str,
    episode_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> AgentEpisodeCreate:
    """Build one size-capped ``mode=consolidate`` episode from source rows.

    The payload carries counts and compact lessons only: no Soul identity or
    charter text, no user-note facts, and no raw trajectory dump. Callers must
    still pass the result through ``require_episodic_write`` before persist.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise MemoryConsolidateError(
            "consolidating requires an explicit symbol scope",
            error_code=ERROR_CONSOLIDATE_UNSCOPED,
        )
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes, bytearray)):
        raise MemoryConsolidateError(
            "consolidate sources must be a sequence of episodes",
            error_code=ERROR_CONSOLIDATE_INVALID_SOURCES,
        )
    rows = list(sources)
    if len(rows) < CONSOLIDATE_MIN_SOURCE_ROWS:
        raise MemoryConsolidateError(
            "consolidating requires at least two source episodes",
            error_code=ERROR_CONSOLIDATE_INVALID_SOURCES,
        )
    started_at, completed_at = _source_window(rows)
    payload = AgentEpisodeCreate.model_validate(
        {
            "episode_id": episode_id or f"epc-{uuid.uuid4().hex}",
            "run_id": run_id or f"cns-{uuid.uuid4().hex}",
            "mode": EPISODE_CONSOLIDATE_MODE,
            "symbol": symbol.strip(),
            "market": _shared_market(rows),
            "started_at": started_at,
            "completed_at": completed_at,
            "success": None,
            "soul_version": None,
            "soul_hash": None,
            "trajectory_summary": [],
            "lessons": _compact_lessons(rows),
            "outcome_labels": EpisodeOutcomeLabels.model_validate(
                {"extra": _count_extra(rows)}
            ),
            "soul_charter": None,
        }
    )
    return payload


def require_episode_consolidate_summary(
    sources: Sequence[Any],
    *,
    symbol: str,
    episode_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> AgentEpisodeCreate:
    """Build a summary and fail closed unless episodic write admission admits it."""
    summary = build_episode_consolidate_summary(
        sources,
        symbol=symbol,
        episode_id=episode_id,
        run_id=run_id,
    )
    require_episodic_write(summary)
    return summary


__all__ = [
    "CONSOLIDATE_MIN_SOURCE_ROWS",
    "EPISODE_CONSOLIDATE_EVENT_TYPE",
    "EPISODE_CONSOLIDATE_MODE",
    "ERROR_CONSOLIDATE_AMBIGUOUS_CUTOFF",
    "ERROR_CONSOLIDATE_INVALID_CUTOFF",
    "ERROR_CONSOLIDATE_INVALID_DRY_RUN",
    "ERROR_CONSOLIDATE_INVALID_MAX_ROWS",
    "ERROR_CONSOLIDATE_INVALID_NOW",
    "ERROR_CONSOLIDATE_INVALID_POLICY",
    "ERROR_CONSOLIDATE_INVALID_RETENTION_DAYS",
    "ERROR_CONSOLIDATE_INVALID_SOURCES",
    "ERROR_CONSOLIDATE_INVALID_SYMBOL",
    "ERROR_CONSOLIDATE_UNSCOPED",
    "EpisodeConsolidateDecision",
    "EpisodeConsolidateResult",
    "MemoryConsolidateError",
    "build_episode_consolidate_summary",
    "require_episode_consolidate_policy",
    "require_episode_consolidate_summary",
    "resolve_episode_consolidate_policy",
]
