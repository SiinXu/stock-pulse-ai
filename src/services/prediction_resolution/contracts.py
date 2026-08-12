# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Minimal work-item contracts for batch prediction resolution.

Full PredictionRecord schema and persistence belong to Issues #1101 / #1108 /
storage tracks. This module only defines the surface the batch resolver needs
so A1–A5 can be swapped in without changing lease or coalesce semantics.

Status names align with A1 (`pending` / `resolving` / `resolved` / `expired` /
`error`) plus an operational retry state used while waiting for the next
bounded `data_unavailable` attempt.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, List, Mapping, Optional, Protocol, Sequence, Tuple

# Lifecycle statuses observed by the batch resolver.
STATUS_PENDING = "pending"
STATUS_RESOLVING = "resolving"
STATUS_RESOLVED = "resolved"
STATUS_EXPIRED = "expired"
STATUS_ERROR = "error"
STATUS_DATA_UNAVAILABLE_RETRY = "data_unavailable_retry"

CLAIMABLE_STATUSES = frozenset(
    {
        STATUS_PENDING,
        STATUS_DATA_UNAVAILABLE_RETRY,
        # Expired leases are reclaimable while still marked resolving.
        STATUS_RESOLVING,
    }
)

TERMINAL_STATUSES = frozenset(
    {
        STATUS_RESOLVED,
        STATUS_EXPIRED,
        STATUS_ERROR,
    }
)

# Deterministic aggregate labels produced by ClaimScorer (A5). The batch layer
# treats data_unavailable as non-terminal for scoring (retry path) and never
# invents hit/miss when the fetcher fails.
OUTCOME_HIT = "hit"
OUTCOME_MISS = "miss"
OUTCOME_PARTIAL = "partial"
OUTCOME_DATA_UNAVAILABLE = "data_unavailable"

OutcomeLabel = str


@dataclass(frozen=True)
class PredictionWorkItem:
    """One claimable prediction row for the resolve queue.

    Fields mirror the subset of PredictionRecord required for lease claim,
    coalesce, scoring, and retry. Extra payload stays opaque.
    """

    prediction_id: str
    symbol: str
    market: str
    as_of_date: date
    resolve_after: datetime
    claims: Tuple[Mapping[str, Any], ...] = ()
    status: str = STATUS_PENDING
    attempt_count: int = 0
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    next_attempt_at: Optional[datetime] = None
    last_error_code: Optional[str] = None
    score_count: int = 0
    outcome_label: Optional[str] = None
    outcome_payload: Optional[Mapping[str, Any]] = None
    created_at: Optional[datetime] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def with_updates(self, **kwargs: Any) -> "PredictionWorkItem":
        return replace(self, **kwargs)


@dataclass(frozen=True)
class ActualsSnapshot:
    """Normalized actuals for one (symbol, market, as_of) group."""

    symbol: str
    market: str
    as_of_date: date
    fields: Mapping[str, Any] = field(default_factory=dict)
    provider: str = "unknown"
    fetched_at: Optional[datetime] = None


@dataclass(frozen=True)
class DataUnavailable:
    """Typed fetcher failure — never fabricate prices or hit/miss."""

    error_code: str
    message: str = ""
    retryable: bool = True


@dataclass(frozen=True)
class ClaimScoreResult:
    """Output of ClaimScorer for one prediction under fixed actuals."""

    aggregate_label: str
    claim_results: Tuple[Mapping[str, Any], ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)
    needs_postmortem: bool = False


@dataclass(frozen=True)
class ResolveOutcome:
    """Durable write-back payload after a successful score."""

    prediction_id: str
    aggregate_label: str
    claim_results: Tuple[Mapping[str, Any], ...]
    metrics: Mapping[str, Any]
    scored_at: datetime
    actuals_provider: str
    worker_id: str


class PredictionWorkStore(Protocol):
    """Port for claim/complete/retry of due predictions.

    Implementations must make claim and complete atomic so concurrent workers
    cannot score the same prediction twice. SQL stores should use
    ``FOR UPDATE SKIP LOCKED`` (or equivalent) for ``claim_due``.
    """

    def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        worker_id: str,
        lease_seconds: int,
    ) -> List[PredictionWorkItem]:
        """Atomically claim up to ``limit`` due rows under a resolving lease."""
        ...

    def complete_resolved(
        self,
        prediction_id: str,
        *,
        worker_id: str,
        outcome: ResolveOutcome,
    ) -> bool:
        """Mark resolved if ``worker_id`` still holds the lease. Idempotent."""
        ...

    def release_for_retry(
        self,
        prediction_id: str,
        *,
        worker_id: str,
        error_code: str,
        next_attempt_at: datetime,
        attempt_count: int,
    ) -> bool:
        """Release lease and schedule a bounded retry (data_unavailable path)."""
        ...

    def mark_error(
        self,
        prediction_id: str,
        *,
        worker_id: str,
        error_code: str,
        message: str = "",
    ) -> bool:
        """Terminal error when retries are exhausted or the row is unrecoverable."""
        ...

    def count_due(self, *, now: datetime) -> int:
        """Number of rows eligible for claim (pending / retry-ready / expired lease)."""
        ...

    def oldest_due_at(self, *, now: datetime) -> Optional[datetime]:
        """``resolve_after`` of the oldest eligible due row, if any."""
        ...

    def queue_depths(self) -> Mapping[str, int]:
        """Status histogram for observability (pending, resolving, retry, …)."""
        ...


class ActualsFetcherPort(Protocol):
    """Server-side actuals path (Issue #1110). Never invents prices."""

    def fetch(
        self,
        *,
        symbol: str,
        market: str,
        as_of_date: date,
    ) -> ActualsSnapshot | DataUnavailable: ...


class ClaimScorerPort(Protocol):
    """Pure deterministic scorer (Issue #1111). No I/O."""

    def score(
        self,
        claims: Sequence[Mapping[str, Any]],
        actuals: ActualsSnapshot,
    ) -> ClaimScoreResult: ...


class PostmortemQueuePort(Protocol):
    """Budgeted miss post-mortem queue (Issue #1103). Separate concurrency pool."""

    def enqueue(
        self,
        *,
        prediction_id: str,
        score: ClaimScoreResult,
        priority: int = 0,
    ) -> bool: ...

    def depth(self) -> int: ...

    def try_run(
        self,
        *,
        handler: Any,
        max_items: int,
    ) -> int:
        """Optional drain hook; default implementations may no-op."""
        ...
