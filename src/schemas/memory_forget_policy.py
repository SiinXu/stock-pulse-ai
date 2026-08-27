# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Library-only memory FORGETTING policy (#1119 Slice 2).

Resolves deterministic per-symbol episode retention over the existing
``agent_episodes`` store. This library does not create tables, does not
UPDATE append-only episodes, and does not write predictions, decision-memory
outcomes, or sidecar opinion/label tables. Persist-path forgetting (not this
module) appends a metadata-only ``episode.forget`` EvolutionEvent in the
same delete transaction.

No-policy (missing symbol scope, or neither cutoff nor max_rows) never
deletes. Invalid policy fails closed and is never coerced into an unscoped
purge. Callers must not treat ``None`` / bare ``False`` as a decision.

Out of slice: consolidation, Decision Memory retrieval-score decay, the
#1118 layered store, auto-promotion, new env keys, migrations, and public
API / Web / Desktop CRUD.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.schemas.agent_episode import (
    AGENT_EPISODE_MAX_MAX_ROWS,
    AGENT_EPISODE_MAX_RETENTION_DAYS,
    AGENT_EPISODE_MIN_RETENTION_DAYS,
)

ERROR_FORGET_INVALID_SYMBOL = "memory_forget_invalid_symbol"
ERROR_FORGET_INVALID_CUTOFF = "memory_forget_invalid_cutoff"
ERROR_FORGET_INVALID_RETENTION_DAYS = "memory_forget_invalid_retention_days"
ERROR_FORGET_INVALID_MAX_ROWS = "memory_forget_invalid_max_rows"
ERROR_FORGET_INVALID_NOW = "memory_forget_invalid_now"
ERROR_FORGET_AMBIGUOUS_CUTOFF = "memory_forget_ambiguous_cutoff"
ERROR_FORGET_UNSCOPED = "memory_forget_unscoped"
ERROR_FORGET_INVALID_DRY_RUN = "memory_forget_invalid_dry_run"
ERROR_FORGET_INVALID_POLICY = "memory_forget_invalid_policy"
EPISODE_FORGET_EVENT_TYPE = "episode.forget"


class MemoryForgetError(ValueError):
    """Typed rejection for an invalid or unscoped episode forget policy."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class EpisodeForgetDecision:
    """Typed forget decision. Never replaced with ``None`` or bare ``False``."""

    apply: bool
    symbol: Optional[str] = None
    cutoff: Optional[datetime] = None
    max_rows: Optional[int] = None
    dry_run: bool = False
    error_code: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class EpisodeForgetResult:
    """Audit result of a forget pass. Counts are authoritative, not inferred.

    ``remaining_count`` is always a live COUNT for the resolved scope: the
    named symbol when present, otherwise the whole table for inactive
    no-policy. It is never reported as zero unless that COUNT is zero.
    ``audit_event_id`` is set only after a durable EvolutionEvent insert
    committed with the DELETE.
    """

    applied: bool
    symbol: Optional[str]
    deleted_count: int
    remaining_count: int
    cutoff: Optional[datetime] = None
    max_rows: Optional[int] = None
    dry_run: bool = False
    audit_event_id: Optional[str] = None


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


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
) -> EpisodeForgetDecision:
    return EpisodeForgetDecision(
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
) -> EpisodeForgetDecision:
    return EpisodeForgetDecision(
        apply=False,
        symbol=symbol,
        cutoff=cutoff,
        max_rows=max_rows,
        dry_run=dry_run,
        error_code=error_code,
        reason=reason,
    )


def resolve_episode_forget_policy(
    *,
    symbol: Any = None,
    cutoff: Any = None,
    retention_days: Any = None,
    now: Any = None,
    max_rows: Any = None,
    dry_run: Any = False,
) -> EpisodeForgetDecision:
    """Resolve a per-symbol forget policy. Never returns ``None``."""

    if dry_run is False:
        parsed_dry_run = False
    elif dry_run is True:
        parsed_dry_run = True
    else:
        return _rejected(
            error_code=ERROR_FORGET_INVALID_DRY_RUN,
            reason="dry_run must be a boolean",
        )

    parsed_symbol: Optional[str]
    if symbol is None:
        parsed_symbol = None
    elif not isinstance(symbol, str):
        return _rejected(
            error_code=ERROR_FORGET_INVALID_SYMBOL,
            reason="forget symbol must be a string",
            dry_run=parsed_dry_run,
        )
    else:
        stripped = symbol.strip()
        parsed_symbol = stripped or None

    parsed_cutoff: Optional[datetime] = None
    if cutoff is not None and retention_days is not None:
        return _rejected(
            error_code=ERROR_FORGET_AMBIGUOUS_CUTOFF,
            reason="pass cutoff or retention_days, not both",
            symbol=parsed_symbol,
            dry_run=parsed_dry_run,
        )
    if cutoff is not None:
        if not isinstance(cutoff, datetime):
            return _rejected(
                error_code=ERROR_FORGET_INVALID_CUTOFF,
                reason="forget cutoff must be a datetime",
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
                error_code=ERROR_FORGET_INVALID_RETENTION_DAYS,
                reason="retention_days must be an integer in the configured range",
                symbol=parsed_symbol,
                dry_run=parsed_dry_run,
            )
        if not isinstance(now, datetime):
            return _rejected(
                error_code=ERROR_FORGET_INVALID_NOW,
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
                error_code=ERROR_FORGET_INVALID_MAX_ROWS,
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
            error_code=ERROR_FORGET_UNSCOPED,
            reason="forgetting requires an explicit symbol scope",
            cutoff=parsed_cutoff,
            max_rows=parsed_max_rows,
            dry_run=parsed_dry_run,
        )
    return EpisodeForgetDecision(
        apply=True,
        symbol=parsed_symbol,
        cutoff=parsed_cutoff,
        max_rows=parsed_max_rows,
        dry_run=parsed_dry_run,
    )


def require_episode_forget_policy(**kwargs: Any) -> EpisodeForgetDecision:
    decision = resolve_episode_forget_policy(**kwargs)
    if decision.error_code:
        raise MemoryForgetError(
            decision.reason or "invalid episode forget policy",
            error_code=decision.error_code,
        )
    return decision


__all__ = [
    "ERROR_FORGET_AMBIGUOUS_CUTOFF",
    "ERROR_FORGET_INVALID_CUTOFF",
    "ERROR_FORGET_INVALID_DRY_RUN",
    "ERROR_FORGET_INVALID_MAX_ROWS",
    "ERROR_FORGET_INVALID_NOW",
    "ERROR_FORGET_INVALID_POLICY",
    "ERROR_FORGET_INVALID_RETENTION_DAYS",
    "ERROR_FORGET_INVALID_SYMBOL",
    "ERROR_FORGET_UNSCOPED",
    "EPISODE_FORGET_EVENT_TYPE",
    "EpisodeForgetDecision",
    "EpisodeForgetResult",
    "MemoryForgetError",
    "require_episode_forget_policy",
    "resolve_episode_forget_policy",
]
