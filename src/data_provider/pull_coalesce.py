# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Process-local short-TTL cache and in-flight coalesce for provider pulls.

Issue #1292: reuse the ActualsFetcher lock + shared-slot + TTL pattern without
forking that class or wrapping daily L2 persistence, circuit breakers, or
fallback order. Keys are ``(provider, normalized symbol, as_of, capability)``.

Manager paths currently wired: realtime quotes and chip-distribution pulls.

Only successful results are stored. Failures, empty results, cancellations, and
timeouts never become a cached success. A waiter that times out or is abandoned
does not cancel shared in-flight work.
"""

from __future__ import annotations

import copy
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from src.data_provider.symbol_normalization import normalize_stock_code

DEFAULT_TTL_SECONDS = 5.0
DEFAULT_MAX_ENTRIES = 512
REALTIME_QUOTE_CAPABILITY = "realtime_quote"
CHIP_DISTRIBUTION_CAPABILITY = "chip_distribution"

CacheKey = Tuple[str, str, str, str]
Loader = Callable[[], Any]
SuccessPredicate = Callable[[Any], bool]


class _InflightSlot:
    """Shared in-flight result box without a cancel API that could poison waiters."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._result: Any = None
        self._error: Optional[BaseException] = None
        self._done = False

    def set_result(self, value: Any) -> None:
        self._result = value
        self._error = None
        self._done = True
        self._event.set()

    def set_exception(self, exc: BaseException) -> None:
        self._error = exc
        self._result = None
        self._done = True
        self._event.set()

    def wait(self, timeout: Optional[float] = None) -> Any:
        if not self._event.wait(timeout):
            raise TimeoutError("provider pull in-flight wait timed out")
        if self._error is not None:
            raise self._error
        return self._result


class ProviderPullCoalesce:
    """Bounded process-local TTL cache with in-flight coalescing."""

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Optional[Callable[[], float]] = None,
        wall_clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        ttl_value = float(ttl_seconds)
        max_value = float(max_entries)
        if (
            isinstance(ttl_seconds, bool)
            or not math.isfinite(ttl_value)
            or ttl_value <= 0
        ):
            raise ValueError("ttl_seconds must be positive")
        if (
            isinstance(max_entries, bool)
            or not math.isfinite(max_value)
            or max_value <= 0
            or not max_value.is_integer()
        ):
            raise ValueError("max_entries must be a positive integer")

        self._ttl_seconds = ttl_value
        self._max_entries = int(max_value)
        self._clock = clock or time.monotonic
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self._cache: Dict[CacheKey, Tuple[float, Any]] = {}
        self._inflight: Dict[CacheKey, _InflightSlot] = {}
        self._hits = 0
        self._misses = 0
        self._coalesced = 0
        self._stores = 0
        self._loads = 0

    @staticmethod
    def build_key(
        *,
        provider: str,
        symbol: str,
        as_of: str,
        capability: str,
    ) -> CacheKey:
        provider_key = str(provider or "").strip()
        symbol_key = normalize_stock_code(str(symbol or "").strip())
        as_of_key = str(as_of or "").strip()
        capability_key = str(capability or "").strip().lower()
        if not provider_key:
            raise ValueError("provider is required")
        if not symbol_key:
            raise ValueError("symbol is required")
        if not as_of_key:
            raise ValueError("as_of is required")
        if not capability_key:
            raise ValueError("capability is required")
        return (provider_key, symbol_key, as_of_key, capability_key)

    def current_as_of(self, now: Optional[datetime] = None) -> str:
        """Return a conservative UTC as_of bucket aligned to the TTL window."""
        current = now or self._wall_clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        else:
            current = current.astimezone(timezone.utc)
        ttl_seconds = max(1, int(self._ttl_seconds))
        epoch = int(current.timestamp())
        bucket = epoch - (epoch % ttl_seconds)
        return datetime.fromtimestamp(bucket, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    def get_or_load(
        self,
        *,
        provider: str,
        symbol: str,
        as_of: Optional[str] = None,
        capability: str,
        loader: Loader,
        is_success: Optional[SuccessPredicate] = None,
        wait_timeout: Optional[float] = None,
    ) -> Any:
        key = self.build_key(
            provider=provider,
            symbol=symbol,
            as_of=as_of if as_of is not None else self.current_as_of(),
            capability=capability,
        )
        cached = self._cache_get(key)
        if cached is not None:
            return self._clone(cached)

        slot, is_owner = self._begin_inflight(key)
        if not is_owner:
            return self._clone(slot.wait(wait_timeout))

        try:
            self._record_load()
            value = loader()
            if self._should_store(value, is_success):
                self._cache_put(key, self._clone(value))
            # Waiters receive a snapshot clone. The owner returns the original
            # object so manager supplement / field-trust can keep mutating it.
            slot.set_result(self._clone(value))
            return value
        except BaseException as exc:  # broad-exception: cleanup - owner must unblock waiters before propagating cancellation
            slot.set_exception(exc)
            raise
        finally:
            self._end_inflight(key, slot)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._cache),
                "inflight": len(self._inflight),
                "hits": self._hits,
                "misses": self._misses,
                "coalesced": self._coalesced,
                "stores": self._stores,
                "loads": self._loads,
                "max_entries": self._max_entries,
            }

    def _should_store(
        self,
        value: Any,
        is_success: Optional[SuccessPredicate],
    ) -> bool:
        if is_success is not None:
            return bool(is_success(value))
        return value is not None

    def _cache_get(self, key: CacheKey) -> Any:
        now = self._clock()
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._cache.pop(key, None)
                return None
            self._hits += 1
            return value

    def _cache_put(self, key: CacheKey, value: Any) -> None:
        expires_at = self._clock() + self._ttl_seconds
        with self._lock:
            if len(self._cache) >= self._max_entries and key not in self._cache:
                oldest = next(iter(self._cache), None)
                if oldest is not None:
                    self._cache.pop(oldest, None)
            self._cache[key] = (expires_at, value)
            self._stores += 1

    def _begin_inflight(self, key: CacheKey) -> Tuple[_InflightSlot, bool]:
        with self._lock:
            # Re-check under the same lock as the claim so a caller that
            # missed cache, then paused while another owner stored and
            # cleared the slot, cannot become a new owner of a warm entry.
            cached = self._cache_get(key)
            if cached is not None:
                ready = _InflightSlot()
                ready.set_result(cached)
                return ready, False
            existing = self._inflight.get(key)
            if existing is not None:
                self._coalesced += 1
                return existing, False
            slot = _InflightSlot()
            self._inflight[key] = slot
            self._misses += 1
            return slot, True

    def _end_inflight(self, key: CacheKey, slot: _InflightSlot) -> None:
        with self._lock:
            current = self._inflight.get(key)
            if current is slot:
                self._inflight.pop(key, None)

    def _record_load(self) -> None:
        with self._lock:
            self._loads += 1

    @staticmethod
    def _clone(value: Any) -> Any:
        if value is None:
            return None
        try:
            return copy.deepcopy(value)
        except (TypeError, AttributeError, RecursionError, copy.Error):
            return value


_LOCK = threading.Lock()
_INSTANCE: Optional[ProviderPullCoalesce] = None


def get_provider_pull_coalesce() -> ProviderPullCoalesce:
    """Return the process-local singleton used by wired provider pull paths."""
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = ProviderPullCoalesce()
        return _INSTANCE


def reset_provider_pull_coalesce_for_tests(
    *,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    clock: Optional[Callable[[], float]] = None,
    wall_clock: Optional[Callable[[], datetime]] = None,
) -> ProviderPullCoalesce:
    """Replace the process-local singleton (tests only)."""
    global _INSTANCE
    with _LOCK:
        _INSTANCE = ProviderPullCoalesce(
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
            clock=clock,
            wall_clock=wall_clock,
        )
        return _INSTANCE


def realtime_quote_is_success(value: Any) -> bool:
    """Return True only for quotes that already have basic price data."""
    if value is None:
        return False
    has_basic_data = getattr(value, "has_basic_data", None)
    if callable(has_basic_data):
        return bool(has_basic_data())
    return True


def coalesce_provider_pull(
    *,
    provider: str,
    symbol: str,
    as_of: Optional[str] = None,
    capability: str,
    loader: Loader,
    is_success: Optional[SuccessPredicate] = None,
    wait_timeout: Optional[float] = None,
) -> Any:
    """Load through the process-local singleton."""
    return get_provider_pull_coalesce().get_or_load(
        provider=provider,
        symbol=symbol,
        as_of=as_of,
        capability=capability,
        loader=loader,
        is_success=is_success,
        wait_timeout=wait_timeout,
    )
