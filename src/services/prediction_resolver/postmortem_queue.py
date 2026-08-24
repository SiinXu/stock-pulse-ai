# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded, priority-aware hand-off for optional prediction postmortems."""

from __future__ import annotations

import heapq
import itertools
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping


@dataclass(frozen=True)
class PostmortemJob:
    prediction_id: str
    outcome: Dict[str, Any]
    priority: int


class InMemoryPostmortemQueue:
    """Process-local bounded queue with deterministic priority and deduplication.

    The queue deliberately does not run work on enqueue. Scheduler and CLI
    drain it after a non-overlap tick with a separately capped worker pool.
    """

    def __init__(self, *, max_depth: int = 10_000) -> None:
        if isinstance(max_depth, bool) or not isinstance(max_depth, int):
            raise ValueError("max_depth must be an integer")
        if not 1 <= max_depth <= 100_000:
            raise ValueError("max_depth must be between 1 and 100000")
        self._max_depth = max_depth
        self._lock = threading.Lock()
        self._sequence = itertools.count()
        self._items: List[tuple[int, int, PostmortemJob]] = []
        self._seen: set[str] = set()

    def enqueue(
        self,
        *,
        prediction_id: str,
        outcome: Mapping[str, Any],
        priority: int = 0,
    ) -> bool:
        canonical_id = str(prediction_id or "").strip()
        if not canonical_id:
            return False
        job = PostmortemJob(
            prediction_id=canonical_id,
            outcome=dict(outcome),
            priority=int(priority),
        )
        with self._lock:
            if canonical_id in self._seen or len(self._seen) >= self._max_depth:
                return False
            self._seen.add(canonical_id)
            heapq.heappush(
                self._items,
                (-job.priority, next(self._sequence), job),
            )
        return True

    def depth(self) -> int:
        with self._lock:
            return len(self._items)

    def pop_batch(self, limit: int) -> List[PostmortemJob]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        jobs: List[PostmortemJob] = []
        with self._lock:
            while self._items and len(jobs) < max(0, limit):
                job = heapq.heappop(self._items)[2]
                self._seen.discard(job.prediction_id)
                jobs.append(job)
        return jobs

    def _take_for_drain(self, limit: int) -> List[PostmortemJob]:
        """Take jobs while retaining their dedupe/capacity reservations."""
        jobs: List[PostmortemJob] = []
        with self._lock:
            while self._items and len(jobs) < max(0, limit):
                jobs.append(heapq.heappop(self._items)[2])
        return jobs

    def drain(
        self,
        *,
        handler: Callable[[PostmortemJob], Any],
        max_items: int,
        max_workers: int = 2,
    ) -> int:
        """Run a bounded batch in a separate, explicitly capped worker pool."""
        if isinstance(max_items, bool) or not isinstance(max_items, int):
            raise ValueError("max_items must be an integer")
        if isinstance(max_workers, bool) or not isinstance(max_workers, int):
            raise ValueError("max_workers must be an integer")
        if not 1 <= max_workers <= 16:
            raise ValueError("max_workers must be between 1 and 16")
        jobs = self._take_for_drain(max_items)
        if not jobs:
            return 0
        completed: List[PostmortemJob] = []
        failed: List[tuple[PostmortemJob, Exception]] = []
        with ThreadPoolExecutor(
            max_workers=min(max_workers, len(jobs)),
            thread_name_prefix="prediction-postmortem",
        ) as pool:
            futures = [(job, pool.submit(handler, job)) for job in jobs]
            for job, future in futures:
                try:
                    future.result()
                except Exception as exc:  # broad-exception: cleanup - requeue before raising
                    failed.append((job, exc))
                else:
                    completed.append(job)

        with self._lock:
            for job in completed:
                self._seen.discard(job.prediction_id)
            for job, _exc in failed:
                heapq.heappush(
                    self._items,
                    (-job.priority, next(self._sequence), job),
                )
        if failed:
            raise RuntimeError(
                f"{len(failed)} postmortem job(s) failed and were requeued"
            ) from failed[0][1]
        return len(completed)

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return {
                "depth": len(self._items),
                "seen": len(self._seen),
                "max_depth": self._max_depth,
            }
