# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""In-memory PredictionWorkStore with exclusive resolving leases.

Mirrors the crash-consistency idea from ``AnalysisTaskQueue`` claim + inflight
checkpoint: a row becomes ``resolving`` under a worker lease before any scoring
side effects, and only that lease owner may complete or release it. Concurrent
``claim_due`` callers never receive the same ``prediction_id``.

Durable SQL stores (A3) should implement the same ``PredictionWorkStore`` port
with ``FOR UPDATE SKIP LOCKED`` (or equivalent) for multi-process deployments.
This memory store is the unit-test double and a single-process fallback.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Dict, List, Mapping, Optional

from src.services.prediction_resolution.contracts import (
    STATUS_DATA_UNAVAILABLE_RETRY,
    STATUS_ERROR,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RESOLVING,
    PredictionWorkItem,
    ResolveOutcome,
    TERMINAL_STATUSES,
)


class InMemoryPredictionWorkStore:
    """Thread-safe in-process store with lease-based claim semantics."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rows: Dict[str, PredictionWorkItem] = {}

    def seed(self, items: List[PredictionWorkItem]) -> None:
        """Insert or replace rows (test helper / bootstrap)."""
        with self._lock:
            for item in items:
                pid = str(item.prediction_id or "").strip()
                if not pid:
                    raise ValueError("prediction_id is required")
                self._rows[pid] = item.with_updates(prediction_id=pid)

    def get(self, prediction_id: str) -> Optional[PredictionWorkItem]:
        with self._lock:
            return self._rows.get(str(prediction_id))

    def list_all(self) -> List[PredictionWorkItem]:
        with self._lock:
            return list(self._rows.values())

    def _is_claimable_locked(self, row: PredictionWorkItem, now: datetime) -> bool:
        if row.status in TERMINAL_STATUSES:
            return False
        if row.status == STATUS_RESOLVING:
            if row.lease_expires_at is None:
                return True
            return row.lease_expires_at <= now
        if row.status == STATUS_DATA_UNAVAILABLE_RETRY:
            if row.next_attempt_at is not None and row.next_attempt_at > now:
                return False
            return row.resolve_after <= now
        if row.status == STATUS_PENDING:
            return row.resolve_after <= now
        return False

    def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        worker_id: str,
        lease_seconds: int,
    ) -> List[PredictionWorkItem]:
        if limit <= 0:
            return []
        owner = str(worker_id or "").strip()
        if not owner:
            raise ValueError("worker_id is required")
        lease_ttl = max(1, int(lease_seconds))
        expires = now + timedelta(seconds=lease_ttl)

        claimed: List[PredictionWorkItem] = []
        with self._lock:
            candidates = sorted(
                (
                    row
                    for row in self._rows.values()
                    if self._is_claimable_locked(row, now)
                ),
                key=lambda r: (r.resolve_after, r.prediction_id),
            )
            for row in candidates:
                if len(claimed) >= limit:
                    break
                # Each claim that will attempt scoring increments attempt_count.
                next_attempt = int(row.attempt_count) + 1
                updated = row.with_updates(
                    status=STATUS_RESOLVING,
                    lease_owner=owner,
                    lease_expires_at=expires,
                    attempt_count=next_attempt,
                )
                self._rows[row.prediction_id] = updated
                claimed.append(updated)
        return claimed

    def complete_resolved(
        self,
        prediction_id: str,
        *,
        worker_id: str,
        outcome: ResolveOutcome,
    ) -> bool:
        """First successful lease-holder wins; others get False (no double score)."""
        pid = str(prediction_id or "").strip()
        owner = str(worker_id or "").strip()
        with self._lock:
            row = self._rows.get(pid)
            if row is None:
                return False
            if row.status == STATUS_RESOLVED:
                return False
            if row.status != STATUS_RESOLVING:
                return False
            if row.lease_owner != owner:
                return False
            self._rows[pid] = row.with_updates(
                status=STATUS_RESOLVED,
                lease_owner=None,
                lease_expires_at=None,
                score_count=int(row.score_count) + 1,
                outcome_label=outcome.aggregate_label,
                outcome_payload={
                    "claim_results": list(outcome.claim_results),
                    "metrics": dict(outcome.metrics),
                    "scored_at": outcome.scored_at.isoformat(),
                    "actuals_provider": outcome.actuals_provider,
                    "worker_id": outcome.worker_id,
                },
                last_error_code=None,
                next_attempt_at=None,
            )
            return True

    def release_for_retry(
        self,
        prediction_id: str,
        *,
        worker_id: str,
        error_code: str,
        next_attempt_at: datetime,
        attempt_count: int,
    ) -> bool:
        pid = str(prediction_id or "").strip()
        owner = str(worker_id or "").strip()
        with self._lock:
            row = self._rows.get(pid)
            if row is None:
                return False
            if row.status in TERMINAL_STATUSES:
                return False
            if row.status == STATUS_RESOLVING and row.lease_owner != owner:
                return False
            self._rows[pid] = row.with_updates(
                status=STATUS_DATA_UNAVAILABLE_RETRY,
                lease_owner=None,
                lease_expires_at=None,
                last_error_code=str(error_code or "data_unavailable"),
                next_attempt_at=next_attempt_at,
                attempt_count=max(int(attempt_count), int(row.attempt_count)),
            )
            return True

    def mark_error(
        self,
        prediction_id: str,
        *,
        worker_id: str,
        error_code: str,
        message: str = "",
    ) -> bool:
        pid = str(prediction_id or "").strip()
        owner = str(worker_id or "").strip()
        with self._lock:
            row = self._rows.get(pid)
            if row is None:
                return False
            if row.status in TERMINAL_STATUSES:
                return False
            if row.status == STATUS_RESOLVING and row.lease_owner not in (None, owner):
                return False
            self._rows[pid] = row.with_updates(
                status=STATUS_ERROR,
                lease_owner=None,
                lease_expires_at=None,
                last_error_code=str(error_code or "error"),
                outcome_payload={"message": message} if message else row.outcome_payload,
                next_attempt_at=None,
            )
            return True

    def count_due(self, *, now: datetime) -> int:
        with self._lock:
            return sum(1 for row in self._rows.values() if self._is_claimable_locked(row, now))

    def oldest_due_at(self, *, now: datetime) -> Optional[datetime]:
        with self._lock:
            due = [
                row.resolve_after
                for row in self._rows.values()
                if self._is_claimable_locked(row, now)
            ]
            if not due:
                return None
            return min(due)

    def queue_depths(self) -> Mapping[str, int]:
        with self._lock:
            depths: Dict[str, int] = {}
            for row in self._rows.values():
                depths[row.status] = depths.get(row.status, 0) + 1
            return depths
