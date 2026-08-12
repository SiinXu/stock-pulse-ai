# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Lightweight opt-in performance span collector.

Design goals:
- Default off: :func:`perf_span` returns immediately without allocating when
  collection is disabled and no collector is active.
- Fail-open: recording never raises into caller control flow.
- Bounded: keep at most ``MAX_SPANS`` spans per collector to cap memory.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Mapping, Optional

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

MAX_SPANS = 500
_ENABLED_CACHE: Optional[bool] = None
_ENABLED_OVERRIDE: Optional[bool] = None

_CURRENT_COLLECTOR: ContextVar[Optional["PerfCollector"]] = ContextVar(
    "perf_collector",
    default=None,
)


@dataclass(frozen=True)
class PerfSpan:
    """One recorded timing span."""

    name: str
    duration_ms: float
    category: str = ""
    attrs: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "duration_ms": round(float(self.duration_ms), 3),
        }
        if self.category:
            data["category"] = self.category
        if self.attrs:
            data["attrs"] = dict(self.attrs)
        return data


class PerfCollector:
    """Process-local, bounded list of performance spans for one run."""

    def __init__(self, *, max_spans: int = MAX_SPANS) -> None:
        self._max_spans = max(1, int(max_spans))
        self._spans: List[PerfSpan] = []
        self._dropped = 0
        self._lock = threading.Lock()

    def record(
        self,
        name: str,
        duration_ms: float,
        *,
        category: str = "",
        attrs: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Append one span, dropping oldest when the bound is exceeded."""
        span = PerfSpan(
            name=str(name or "unnamed"),
            duration_ms=max(0.0, float(duration_ms)),
            category=str(category or ""),
            attrs=dict(attrs or {}),
        )
        with self._lock:
            if len(self._spans) >= self._max_spans:
                self._spans.pop(0)
                self._dropped += 1
            self._spans.append(span)

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot of recorded spans."""
        with self._lock:
            spans = [span.to_dict() for span in self._spans]
            dropped = self._dropped
        by_name: Dict[str, Dict[str, float]] = {}
        for span in spans:
            bucket = by_name.setdefault(
                span["name"],
                {"count": 0, "total_ms": 0.0, "max_ms": 0.0},
            )
            duration = float(span["duration_ms"])
            bucket["count"] += 1
            bucket["total_ms"] = round(bucket["total_ms"] + duration, 3)
            bucket["max_ms"] = round(max(bucket["max_ms"], duration), 3)
        for bucket in by_name.values():
            count = int(bucket["count"]) or 1
            bucket["avg_ms"] = round(bucket["total_ms"] / count, 3)
        return {
            "span_count": len(spans),
            "dropped": dropped,
            "spans": spans,
            "by_name": by_name,
        }

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()
            self._dropped = 0


def clear_enabled_cache() -> None:
    """Clear the cached config flag (tests / config reload)."""
    global _ENABLED_CACHE
    _ENABLED_CACHE = None


def set_collection_enabled_override(enabled: Optional[bool]) -> None:
    """Force enable/disable without consulting Config (None clears override)."""
    global _ENABLED_OVERRIDE
    _ENABLED_OVERRIDE = enabled
    clear_enabled_cache()


def is_perf_collection_enabled() -> bool:
    """Return whether performance span collection is enabled (default off)."""
    global _ENABLED_CACHE
    if _ENABLED_OVERRIDE is not None:
        return bool(_ENABLED_OVERRIDE)
    if _ENABLED_CACHE is not None:
        return _ENABLED_CACHE
    enabled = False
    try:
        from src.application_services import get_application_services

        config = get_application_services().config
        enabled = bool(getattr(config, "perf_collection_enabled", False))
    except Exception as exc:  # broad-exception: fallback_recorded - Config lookup must not block callers.
        log_safe_exception(
            logger,
            "Perf collection enabled flag lookup failed; defaulting off",
            exc,
            error_code="perf_collection_enabled_lookup_failed",
            level=logging.DEBUG,
        )
        enabled = False
    _ENABLED_CACHE = enabled
    return enabled


def is_perf_profile_enabled() -> bool:
    """Return whether optional cProfile wrapping is enabled (default off)."""
    try:
        from src.application_services import get_application_services

        config = get_application_services().config
        return bool(getattr(config, "perf_profile_enabled", False))
    except Exception as exc:  # broad-exception: fallback_recorded - Config lookup must not block callers.
        log_safe_exception(
            logger,
            "Perf profile enabled flag lookup failed; defaulting off",
            exc,
            error_code="perf_profile_enabled_lookup_failed",
            level=logging.DEBUG,
        )
        return False


def get_current_collector() -> Optional[PerfCollector]:
    """Return the active context-local collector, if any."""
    return _CURRENT_COLLECTOR.get()


def activate_collector(
    collector: Optional[PerfCollector] = None,
) -> tuple[PerfCollector, Token]:
    """Activate a collector for the current context. Returns (collector, token)."""
    active = collector if collector is not None else PerfCollector()
    token = _CURRENT_COLLECTOR.set(active)
    return active, token


def reset_collector(token: Token) -> None:
    """Restore the previous collector context."""
    _CURRENT_COLLECTOR.reset(token)


def record_span(
    name: str,
    duration_ms: float,
    *,
    category: str = "",
    attrs: Optional[Mapping[str, Any]] = None,
) -> None:
    """Record a span when collection is enabled and a collector is active."""
    if not is_perf_collection_enabled():
        return
    collector = get_current_collector()
    if collector is None:
        return
    try:
        collector.record(name, duration_ms, category=category, attrs=attrs)
    except Exception as exc:  # broad-exception: fallback_recorded - Perf recording must not break callers.
        log_safe_exception(
            logger,
            "Perf span record failed",
            exc,
            error_code="perf_span_record_failed",
            level=logging.DEBUG,
            context={"name": str(name or "")},
        )


@contextmanager
def perf_span(
    name: str,
    *,
    category: str = "",
    attrs: Optional[Mapping[str, Any]] = None,
) -> Iterator[None]:
    """Time a block when collection is active; otherwise a zero-overhead no-op."""
    if get_current_collector() is None:
        yield None
        return
    if not is_perf_collection_enabled():
        yield None
        return
    started = time.perf_counter()
    try:
        yield None
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        record_span(name, duration_ms, category=category, attrs=attrs)
