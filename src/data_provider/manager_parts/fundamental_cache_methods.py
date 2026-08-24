# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned fundamental aggregation cache key, prune, and in-flight coalesce.

These descriptors are rebound onto ``DataFetcherManager`` by the compatibility
facade. Cache maps, locks, and CN/offshore aggregation loaders remain on the
facade. This is instance-local and is not the 5s realtime/chip process helper.
"""

from __future__ import annotations

import copy
import threading
import time
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    Type,
)

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
normalize_stock_code = None  # type: ignore[assignment,misc]
_market_tag = None  # type: ignore[assignment,misc]

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _FundamentalInflightSlot:
    """Shared in-flight result box; owner exceptions unblock waiters."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._result: Any = None
        self._error: Optional[BaseException] = None

    def set_result(self, value: Any) -> None:
        self._result = value
        self._error = None
        self._event.set()

    def set_exception(self, exc: BaseException) -> None:
        self._error = exc
        self._result = None
        self._event.set()

    def wait(self) -> Any:
        self._event.wait()
        if self._error is not None:
            raise self._error
        return self._result


def _clone_fundamental_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        return copy.deepcopy(value)
    except (TypeError, AttributeError, RecursionError, copy.Error):
        return value


def _manager_now_ts(manager: Any) -> float:
    clock = getattr(manager, "_fundamental_cache_clock", None)
    if callable(clock):
        return float(clock())
    return time.time()


def _manager_wall_now(manager: Any) -> datetime:
    clock = getattr(manager, "_fundamental_cache_wall_clock", None)
    if callable(clock):
        current = clock()
    else:
        current = datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _as_of_bucket(ttl_seconds: int, now: datetime) -> str:
    bucket_ttl = max(1, int(ttl_seconds))
    epoch = int(now.timestamp())
    bucket = epoch - (epoch % bucket_ttl)
    return datetime.fromtimestamp(bucket, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _budget_bucket(budget_seconds: Optional[float]) -> str:
    if budget_seconds is None:
        return "default"
    try:
        budget = max(0.0, float(budget_seconds))
    except (TypeError, ValueError):
        budget = 0.0
    # 100ms bucket to balance cache reuse and scenario isolation.
    return str(int(round(budget * 10)))


def _begin_fundamental_inflight(
    *,
    lock: threading.RLock,
    cache: Dict[str, Dict[str, Any]],
    inflight: Dict[str, _FundamentalInflightSlot],
    key: str,
    ttl_seconds: int,
    now_ts: float,
) -> Tuple[_FundamentalInflightSlot, bool]:
    with lock:
        if ttl_seconds > 0:
            item = cache.get(key)
            if item is not None:
                age = now_ts - float(item.get("ts", 0))
                if age <= ttl_seconds:
                    ready = _FundamentalInflightSlot()
                    ready.set_result(item.get("context"))
                    return ready, False
        existing = inflight.get(key)
        if existing is not None:
            return existing, False
        slot = _FundamentalInflightSlot()
        inflight[key] = slot
        return slot, True


def _end_fundamental_inflight(
    *,
    lock: threading.RLock,
    inflight: Dict[str, _FundamentalInflightSlot],
    key: str,
    slot: _FundamentalInflightSlot,
) -> None:
    with lock:
        current = inflight.get(key)
        if current is slot:
            inflight.pop(key, None)


class _FundamentalCacheMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def _get_fundamental_cache_key(
        self,
        stock_code: str,
        budget_seconds: Optional[float] = None,
        *,
        market: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        now: Optional[datetime] = None,
        _as_of=_as_of_bucket,
        _wall=_manager_wall_now,
        _budget=_budget_bucket,
    ) -> str:
        """Build the fundamental cache key: symbol, market, budget, as_of."""
        normalized_code = normalize_stock_code(stock_code)
        if market is None or not str(market).strip():
            market_tag = str(_market_tag(normalized_code) or "").strip() or "cn"
        else:
            market_tag = str(market).strip()
        if ttl_seconds is None:
            from src.config import get_config

            ttl_seconds = int(
                getattr(get_config(), "fundamental_cache_ttl_seconds", 120)
            )
        as_of = _as_of(
            int(ttl_seconds),
            now if now is not None else _wall(self),
        )
        budget_bucket = _budget(budget_seconds)
        return (
            f"{normalized_code}|market={market_tag}"
            f"|budget={budget_bucket}|as_of={as_of}"
        )

    def _prune_fundamental_cache(
        self,
        ttl_seconds: int,
        max_entries: int,
        *,
        _now=_manager_now_ts,
    ) -> None:
        """Prune expired and overflow fundamental cache items."""
        with self._fundamental_cache_lock:
            if not self._fundamental_cache:
                return

            now_ts = _now(self)
            if ttl_seconds > 0:
                cache_items = list(self._fundamental_cache.items())
                expired_keys = [
                    key
                    for key, value in cache_items
                    if now_ts - float(value.get("ts", 0)) > ttl_seconds
                ]
                for key in expired_keys:
                    self._fundamental_cache.pop(key, None)

            if max_entries > 0 and len(self._fundamental_cache) > max_entries:
                overflow = len(self._fundamental_cache) - max_entries
                sorted_items = sorted(
                    list(self._fundamental_cache.items()),
                    key=lambda item: float(item[1].get("ts", 0)),
                )
                for key, _ in sorted_items[:overflow]:
                    self._fundamental_cache.pop(key, None)

    def _get_or_load_fundamental_context(
        self,
        stock_code: str,
        budget_seconds: Optional[float],
        loader: Callable[[], Any],
        *,
        market: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        cache_max_entries: Optional[int] = None,
        _begin=_begin_fundamental_inflight,
        _end=_end_fundamental_inflight,
        _clone=_clone_fundamental_value,
        _now=_manager_now_ts,
    ) -> Any:
        """Lookup, coalesce in-flight, and maybe store one fundamental context."""
        if cache_ttl is None or cache_max_entries is None:
            from src.config import get_config

            config = get_config()
            if cache_ttl is None:
                cache_ttl = int(config.fundamental_cache_ttl_seconds)
            if cache_max_entries is None:
                cache_max_entries = max(
                    0, int(getattr(config, "fundamental_cache_max_entries", 256))
                )
        cache_ttl = int(cache_ttl)
        cache_max_entries = max(0, int(cache_max_entries))
        inflight = getattr(self, "_fundamental_inflight", None)
        if inflight is None:
            self._fundamental_inflight = {}
            inflight = self._fundamental_inflight
        cache_key = self._get_fundamental_cache_key(
            stock_code,
            budget_seconds,
            market=market,
            ttl_seconds=cache_ttl,
        )
        if cache_ttl > 0:
            self._prune_fundamental_cache(cache_ttl, cache_max_entries)

        slot, is_owner = _begin(
            lock=self._fundamental_cache_lock,
            cache=self._fundamental_cache,
            inflight=inflight,
            key=cache_key,
            ttl_seconds=cache_ttl,
            now_ts=_now(self),
        )
        if not is_owner:
            return _clone(slot.wait())

        try:
            value = loader()
            if cache_ttl > 0 and self._should_cache_fundamental_context(value):
                with self._fundamental_cache_lock:
                    self._fundamental_cache[cache_key] = {
                        "ts": _now(self),
                        "context": _clone(value),
                    }
                self._prune_fundamental_cache(cache_ttl, cache_max_entries)
            slot.set_result(_clone(value))
            return value
        except BaseException as exc:  # broad-exception: cleanup - owner must unblock waiters
            slot.set_exception(exc)
            raise
        finally:
            _end(
                lock=self._fundamental_cache_lock,
                inflight=inflight,
                key=cache_key,
                slot=slot,
            )


EXPECTED_FUNDAMENTAL_CACHE_METHOD_NAMES = (
    "_get_fundamental_cache_key",
    "_prune_fundamental_cache",
    "_get_or_load_fundamental_context",
)


def bind_fundamental_cache_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind fundamental cache descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_FundamentalCacheMethods).items():
        if name.startswith("__") or _descriptor_function(descriptor) is None:
            continue
        setattr(
            target_class,
            name,
            _clone_facade_descriptor(
                descriptor,
                global_namespace,
                owner_qualname=target_class.__qualname__,
            ),
        )
        bound_names.append(name)
    return tuple(bound_names)


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    """Register the loaded facade assembly callback for owner reloads."""

    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""

    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
