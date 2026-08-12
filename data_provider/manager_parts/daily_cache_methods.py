# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned daily cache orchestration methods.

Extracted from :mod:`data_provider.base` behind an ADR-006 compatibility facade.
``DataFetcherManager`` remains the public import and patch surface; these
descriptors are rebound onto that class with the facade global namespace so
existing call sites and tests keep working without behavior changes.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from types import FunctionType
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    Type,
)

import pandas as pd

from ..daily_cache import (
    CachedCandidateRejected,
    DailyCacheKey,
    DailyDataCache,
    MarketDataFetchMode,
    MarketDataResolveResult,
)

# Facade-only symbols cannot be imported from ``data_provider.base`` while that
# module is still assembling this part (circular import). Declare anchors so
# flake8 F821 is clean; rebound methods resolve the real objects from the
# ``data_provider.base`` global namespace.
canonical_stock_code = None  # type: ignore[assignment,misc]
normalize_stock_code = None  # type: ignore[assignment,misc]
_market_tag = None  # type: ignore[assignment,misc]
record_provider_run = None  # type: ignore[assignment,misc]

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _DailyCacheMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def _get_daily_data_cache(self) -> DailyDataCache:
        self._ensure_concurrency_guards()
        with self._fetchers_lock:
            if self._daily_data_cache is None:
                self._daily_data_cache = DailyDataCache.from_env()
            return self._daily_data_cache

    def is_market_data_local_only(self) -> bool:
        """Return whether manager-owned market-data helpers must avoid providers."""

        return self._get_daily_data_cache().fetch_mode is MarketDataFetchMode.LOCAL_ONLY

    def _daily_adjustment_identity(self) -> str:
        """Return the active adjustment policy that partitions persistent bars."""

        for fetcher in self._get_fetchers_snapshot():
            if fetcher.name != "TickFlowFetcher":
                continue
            adjustment = str(getattr(fetcher, "kline_adjust", "none") or "none")
            return f"tickflow:{adjustment.strip().lower()}"
        return "provider_default"

    @staticmethod
    def _daily_cache_key(
        stock_code: str,
        start_date: Optional[str],
        end_date: Optional[str],
        days: int,
        *,
        adjustment: str = "provider_default",
    ) -> DailyCacheKey:
        effective_end = end_date or datetime.now().strftime("%Y-%m-%d")
        effective_start = start_date
        if effective_start is None:
            start_dt = datetime.strptime(effective_end, "%Y-%m-%d") - timedelta(days=days * 2)
            effective_start = start_dt.strftime("%Y-%m-%d")
        return DailyCacheKey(
            symbol=canonical_stock_code(stock_code),
            start_date=effective_start,
            end_date=effective_end,
            days=days,
            adjustment=adjustment,
            allow_end_rollover=end_date is None,
        )

    @staticmethod
    def _record_daily_cache_result(
        cache_result: MarketDataResolveResult,
        request_start: float,
    ) -> None:
        record_provider_run(
            data_type="daily_data",
            provider=cache_result.source_name,
            operation="get_daily_data",
            success=True,
            latency_ms=int((time.time() - request_start) * 1000),
            cache_hit=True,
            stale_seconds=int(cache_result.age_seconds),
            record_count=len(cache_result.frame),
        )

    @staticmethod
    def _validate_daily_candidate(
        frame: pd.DataFrame,
        *,
        stock_code: str,
        source_name: str,
    ) -> pd.DataFrame:
        """Apply the active quality policy to provider and cached candidates."""
        from data_provider.data_validation import (
            DataValidationRejected,
            infer_instrument_type,
            validate_and_annotate,
        )

        try:
            validate_and_annotate(
                frame,
                data_type="daily_data",
                market=_market_tag(normalize_stock_code(stock_code)),
                stock_code=stock_code,
                provider=source_name,
                instrument_type=(
                    frame.attrs.get("instrument_type")
                    or infer_instrument_type(stock_code)
                ),
            )
        except DataValidationRejected as exc:
            raise CachedCandidateRejected(
                "cached daily-data candidate rejected by active quality policy"
            ) from exc
        return frame

    def get_daily_cache_stats(self) -> Dict[str, int]:
        """Return manager-local daily cache hit, miss, and lifecycle counters."""
        return self._get_daily_data_cache().stats_snapshot()

    def invalidate_daily_cache(self, stock_code: Optional[str] = None) -> int:
        """Invalidate daily cache entries for one symbol, or every symbol when omitted."""
        normalized = (
            None
            if stock_code is None
            else canonical_stock_code(normalize_stock_code(stock_code))
        )
        return self._get_daily_data_cache().invalidate(normalized)

    def _get_cached_stock_name(self, stock_code: str) -> Optional[str]:
        self._ensure_concurrency_guards()
        with self._stock_name_cache_lock:
            return self._stock_name_cache.get(stock_code)

    def _cache_stock_name(self, stock_code: str, name: Optional[str]) -> Optional[str]:
        if name is None:
            return None
        self._ensure_concurrency_guards()
        with self._stock_name_cache_lock:
            self._stock_name_cache[stock_code] = name
        return name


def _resolve_annotations(
    function: FunctionType,
    global_namespace: Dict[str, Any],
) -> Dict[str, Any]:
    """Map annotation objects through the facade global namespace when present."""

    legacy_types = {
        "DailyDataCache": global_namespace.get("DailyDataCache", DailyDataCache),
        "DailyCacheKey": global_namespace.get("DailyCacheKey", DailyCacheKey),
        "MarketDataResolveResult": global_namespace.get(
            "MarketDataResolveResult", MarketDataResolveResult
        ),
        "Optional[str]": Optional[str],
        "Dict[str, int]": Dict[str, int],
        "pd.DataFrame": pd.DataFrame,
    }
    return {
        name: legacy_types.get(annotation, annotation)
        for name, annotation in function.__annotations__.items()
    }


def _clone_facade_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    qualname: str,
) -> FunctionType:
    """Clone one method so global lookups retain ``data_provider.base`` seams."""

    cloned = FunctionType(
        function.__code__,
        global_namespace,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    cloned.__annotations__ = _resolve_annotations(function, global_namespace)
    cloned.__dict__.update(function.__dict__)
    cloned.__doc__ = function.__doc__
    cloned.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    cloned.__module__ = str(global_namespace["__name__"])
    cloned.__qualname__ = qualname
    if hasattr(function, "__type_params__"):
        cloned.__type_params__ = function.__type_params__
    return cloned


def _descriptor_function(descriptor: Any) -> Optional[FunctionType]:
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    if isinstance(descriptor, FunctionType):
        return descriptor
    return None


def _clone_facade_descriptor(
    descriptor: Any,
    global_namespace: Dict[str, Any],
    *,
    owner_qualname: str,
) -> Any:
    def clone(function: Optional[FunctionType]) -> Optional[FunctionType]:
        if function is None:
            return None
        return _clone_facade_function(
            function,
            global_namespace,
            qualname=f"{owner_qualname}.{function.__name__}",
        )

    if isinstance(descriptor, staticmethod):
        return staticmethod(clone(descriptor.__func__))
    if isinstance(descriptor, classmethod):
        return classmethod(clone(descriptor.__func__))
    if isinstance(descriptor, property):
        return property(
            clone(descriptor.fget),
            clone(descriptor.fset),
            clone(descriptor.fdel),
            descriptor.__doc__,
        )
    return clone(descriptor)


EXPECTED_DAILY_CACHE_METHOD_NAMES = (
    "_get_daily_data_cache",
    "is_market_data_local_only",
    "_daily_adjustment_identity",
    "_daily_cache_key",
    "_record_daily_cache_result",
    "_validate_daily_candidate",
    "get_daily_cache_stats",
    "invalidate_daily_cache",
    "_get_cached_stock_name",
    "_cache_stock_name",
)


def bind_daily_cache_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind daily-cache descriptors without changing the manager interface."""

    bound_names = []
    for name, descriptor in vars(_DailyCacheMethods).items():
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
