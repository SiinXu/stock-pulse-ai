# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""In-process post-mortem queue with depth observability and concurrency cap.

LLM post-mortems are expensive; the batch resolver enqueues misses here under a
per-tick budget, and consumers drain with a small worker pool. This is not the
full Issue #1103 lesson writer — only the rate-limited queue boundary.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List

from src.services.prediction_resolution.contracts import ClaimScoreResult


@dataclass(frozen=True)
class PostmortemJob:
    prediction_id: str
    score: ClaimScoreResult
    priority: int = 0


@dataclass
class InMemoryPostmortemQueue:
    """Bounded optional queue; depth is always observable."""

    max_depth: int = 10_000
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _items: Deque[PostmortemJob] = field(default_factory=deque, repr=False)
    _seen: set = field(default_factory=set, repr=False)

    def enqueue(
        self,
        *,
        prediction_id: str,
        score: ClaimScoreResult,
        priority: int = 0,
    ) -> bool:
        pid = str(prediction_id or "").strip()
        if not pid:
            return False
        with self._lock:
            if pid in self._seen:
                return False
            if len(self._items) >= self.max_depth:
                return False
            self._seen.add(pid)
            job = PostmortemJob(prediction_id=pid, score=score, priority=int(priority))
            if not self._items:
                self._items.append(job)
                return True
            inserted = False
            for idx, existing in enumerate(self._items):
                if job.priority > existing.priority:
                    self._items.insert(idx, job)
                    inserted = True
                    break
            if not inserted:
                self._items.append(job)
            return True

    def depth(self) -> int:
        with self._lock:
            return len(self._items)

    def pop_batch(self, limit: int) -> List[PostmortemJob]:
        out: List[PostmortemJob] = []
        with self._lock:
            while self._items and len(out) < max(0, int(limit)):
                out.append(self._items.popleft())
        return out

    def try_run(
        self,
        *,
        handler: Callable[[PostmortemJob], Any],
        max_items: int,
    ) -> int:
        jobs = self.pop_batch(max_items)
        ran = 0
        for job in jobs:
            handler(job)
            ran += 1
        return ran

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return {"depth": len(self._items), "seen": len(self._seen)}
