# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""In-process sliding-window rate limiter shared by governed read surfaces.

Matches the MCP ``PerPrincipalToolRateLimiter`` contract (principal + action key,
60-second window) so REST research/read APIs reuse the same governance pattern
without opening a second ungated port.
"""

from __future__ import annotations

from collections import defaultdict, deque
import threading
import time


class RateLimitExceeded(RuntimeError):
    """Raised when a principal exhausts a per-action request budget."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message)
        self.code = "rate_limited"


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window limiter keyed by ``(principal, action)``."""

    def __init__(self, *, limit_per_minute: int, window_seconds: float = 60.0) -> None:
        if limit_per_minute < 1:
            raise ValueError("limit_per_minute must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit_per_minute = int(limit_per_minute)
        self.window_seconds = float(window_seconds)
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def consume(self, principal: str, action: str) -> None:
        """Record one event or raise ``RateLimitExceeded``."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        key = (str(principal or "anonymous"), str(action or "default"))
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit_per_minute:
                raise RateLimitExceeded(
                    f"Rate limit exceeded for {key[1]} ({self.limit_per_minute}/min)"
                )
            events.append(now)


__all__ = ["RateLimitExceeded", "SlidingWindowRateLimiter"]
