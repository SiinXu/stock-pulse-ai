# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Process-local metrics for prediction resolve ticks (Issue #1104 / #1114 surface)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass(frozen=True)
class PredictionResolveMetricsSnapshot:
    """Point-in-time counters for observability / diagnostics."""

    ticks: int = 0
    claimed: int = 0
    resolved: int = 0
    retried: int = 0
    errors: int = 0
    fetch_calls: int = 0
    fetch_errors: int = 0
    fetch_coalesced_saved: int = 0
    scored: int = 0
    score_rejected_stale_lease: int = 0
    postmortem_enqueued: int = 0
    postmortem_dropped_cap: int = 0
    deferred_by_backpressure: int = 0
    circuit_open_ticks: int = 0
    last_due_count: int = 0
    last_due_lag_seconds: Optional[float] = None
    last_postmortem_queue_depth: int = 0
    last_queue_depths: Dict[str, int] = field(default_factory=dict)
    last_tick_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "ticks": self.ticks,
            "claimed": self.claimed,
            "resolved": self.resolved,
            "retried": self.retried,
            "errors": self.errors,
            "fetch_calls": self.fetch_calls,
            "fetch_errors": self.fetch_errors,
            "fetch_coalesced_saved": self.fetch_coalesced_saved,
            "scored": self.scored,
            "score_rejected_stale_lease": self.score_rejected_stale_lease,
            "postmortem_enqueued": self.postmortem_enqueued,
            "postmortem_dropped_cap": self.postmortem_dropped_cap,
            "deferred_by_backpressure": self.deferred_by_backpressure,
            "circuit_open_ticks": self.circuit_open_ticks,
            "last_due_count": self.last_due_count,
            "last_due_lag_seconds": self.last_due_lag_seconds,
            "last_postmortem_queue_depth": self.last_postmortem_queue_depth,
            "last_queue_depths": dict(self.last_queue_depths),
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
        }


class PredictionResolveMetrics:
    """Thread-safe counter bag updated by ``PredictionBatchResolver``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ticks = 0
        self._claimed = 0
        self._resolved = 0
        self._retried = 0
        self._errors = 0
        self._fetch_calls = 0
        self._fetch_errors = 0
        self._fetch_coalesced_saved = 0
        self._scored = 0
        self._score_rejected_stale_lease = 0
        self._postmortem_enqueued = 0
        self._postmortem_dropped_cap = 0
        self._deferred_by_backpressure = 0
        self._circuit_open_ticks = 0
        self._last_due_count = 0
        self._last_due_lag_seconds: Optional[float] = None
        self._last_postmortem_queue_depth = 0
        self._last_queue_depths: Dict[str, int] = {}
        self._last_tick_at: Optional[datetime] = None

    def record_tick_start(
        self,
        *,
        now: datetime,
        due_count: int,
        due_lag_seconds: Optional[float],
        queue_depths: Dict[str, int],
        postmortem_depth: int,
        circuit_open: bool,
        deferred: int,
    ) -> None:
        with self._lock:
            self._ticks += 1
            self._last_tick_at = now
            self._last_due_count = due_count
            self._last_due_lag_seconds = due_lag_seconds
            self._last_queue_depths = dict(queue_depths)
            self._last_postmortem_queue_depth = postmortem_depth
            if circuit_open:
                self._circuit_open_ticks += 1
            if deferred > 0:
                self._deferred_by_backpressure += deferred

    def add_claimed(self, n: int) -> None:
        with self._lock:
            self._claimed += n

    def add_resolved(self, n: int = 1) -> None:
        with self._lock:
            self._resolved += n

    def add_retried(self, n: int = 1) -> None:
        with self._lock:
            self._retried += n

    def add_errors(self, n: int = 1) -> None:
        with self._lock:
            self._errors += n

    def add_fetch_call(self) -> None:
        with self._lock:
            self._fetch_calls += 1

    def add_fetch_error(self) -> None:
        with self._lock:
            self._fetch_errors += 1

    def add_coalesced_saved(self, n: int) -> None:
        if n <= 0:
            return
        with self._lock:
            self._fetch_coalesced_saved += n

    def add_scored(self, n: int = 1) -> None:
        with self._lock:
            self._scored += n

    def add_score_rejected(self, n: int = 1) -> None:
        with self._lock:
            self._score_rejected_stale_lease += n

    def add_postmortem_enqueued(self, n: int = 1) -> None:
        with self._lock:
            self._postmortem_enqueued += n

    def add_postmortem_dropped(self, n: int = 1) -> None:
        with self._lock:
            self._postmortem_dropped_cap += n

    def snapshot(self) -> PredictionResolveMetricsSnapshot:
        with self._lock:
            return PredictionResolveMetricsSnapshot(
                ticks=self._ticks,
                claimed=self._claimed,
                resolved=self._resolved,
                retried=self._retried,
                errors=self._errors,
                fetch_calls=self._fetch_calls,
                fetch_errors=self._fetch_errors,
                fetch_coalesced_saved=self._fetch_coalesced_saved,
                scored=self._scored,
                score_rejected_stale_lease=self._score_rejected_stale_lease,
                postmortem_enqueued=self._postmortem_enqueued,
                postmortem_dropped_cap=self._postmortem_dropped_cap,
                deferred_by_backpressure=self._deferred_by_backpressure,
                circuit_open_ticks=self._circuit_open_ticks,
                last_due_count=self._last_due_count,
                last_due_lag_seconds=self._last_due_lag_seconds,
                last_postmortem_queue_depth=self._last_postmortem_queue_depth,
                last_queue_depths=dict(self._last_queue_depths),
                last_tick_at=self._last_tick_at,
            )
