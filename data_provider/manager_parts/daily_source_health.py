# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Daily provider health, circuit, concurrency, and adaptive-priority methods.

Extracted from :mod:`data_provider.base` behind an ADR-006 compatibility facade.
``DataFetcherManager`` remains the public import and patch surface; these
descriptors are rebound onto that class with the facade global namespace so
existing call sites and tests keep working without behavior changes.
"""

from __future__ import annotations

import json as _json
import logging
import os
import time
from datetime import datetime, timezone
from threading import RLock
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
)

import numpy as np
import pandas as pd

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

from ..realtime_types import CircuitBreaker
from ..symbol_normalization import _market_tag, normalize_stock_code

if TYPE_CHECKING:
    from data_provider.base import BaseFetcher, DataProvider

# Facade-only symbols cannot be imported from ``data_provider.base`` while that
# module is still assembling this part (circular import). Declare anchors so
# flake8 F821 is clean; rebound methods resolve the real objects from the
# ``data_provider.base`` global namespace.
CircuitOpenError = None  # type: ignore[assignment,misc]
record_provider_run = None  # type: ignore[assignment,misc]

logger = logging.getLogger("data_provider.base")

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)

_PROVIDER_CIRCUIT_ENABLED_DEFAULT = True
_PROVIDER_CIRCUIT_FAILURE_THRESHOLD_DEFAULT = 3
_PROVIDER_CIRCUIT_COOLDOWN_SECONDS_DEFAULT = 300.0
_PROVIDER_HEALTH_WINDOW_SIZE_DEFAULT = 20
_PROVIDER_ADAPTIVE_PRIORITY_ENABLED_DEFAULT = True
_PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES_DEFAULT = 3
_PROVIDER_DAILY_HEALTH_SCHEMA_VERSION = "provider_daily_health_v1"


def _read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    logger.warning("Invalid boolean configuration name=%s; using default", name)
    return default


def _read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Invalid integer configuration name=%s; using default", name)
        return default
    if value < 1:
        logger.warning("Out-of-range integer configuration name=%s; using default", name)
        return default
    return value


def _read_non_negative_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning("Invalid numeric configuration name=%s; using default", name)
        return default
    if not np.isfinite(value) or value < 0:
        logger.warning("Out-of-range numeric configuration name=%s; using default", name)
        return default
    return value


class _DailySourceHealthMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def _ensure_concurrency_guards(self) -> None:
        """Lazily initialize thread-safety primitives for test scaffolds using __new__."""
        if not hasattr(self, "_fetchers") or self._fetchers is None:
            self._fetchers = []
        if not hasattr(self, "_fetchers_lock") or self._fetchers_lock is None:
            self._fetchers_lock = RLock()
        if not hasattr(self, "_fetchers_by_name") or self._fetchers_by_name is None:
            self._fetchers_by_name = {}
        if not hasattr(self, "_fetcher_call_locks") or self._fetcher_call_locks is None:
            self._fetcher_call_locks = {}
        if not hasattr(self, "_fetcher_call_locks_lock") or self._fetcher_call_locks_lock is None:
            self._fetcher_call_locks_lock = RLock()
        if not hasattr(self, "_data_provider_runtime"):
            self._data_provider_runtime = None
        if not hasattr(self, "_registered_fetchers") or self._registered_fetchers is None:
            self._registered_fetchers = {}
        if not hasattr(self, "_provider_priorities") or self._provider_priorities is None:
            self._provider_priorities = {}
        if not hasattr(self, "_fetcher_static_order") or self._fetcher_static_order is None:
            self._fetcher_static_order = {}
        if not hasattr(self, "_next_fetcher_static_order"):
            self._next_fetcher_static_order = 0
        if not hasattr(self, "_builtin_provider_handles"):
            self._builtin_provider_handles = []
        if not hasattr(self, "_stock_name_cache") or self._stock_name_cache is None:
            self._stock_name_cache = {}
        if not hasattr(self, "_stock_name_cache_lock") or self._stock_name_cache_lock is None:
            self._stock_name_cache_lock = RLock()
        if not hasattr(self, "_daily_data_cache"):
            self._daily_data_cache = None
        if not hasattr(self, "_daily_adaptive_priority_enabled"):
            self._daily_adaptive_priority_enabled = _PROVIDER_ADAPTIVE_PRIORITY_ENABLED_DEFAULT
        if not hasattr(self, "_daily_adaptive_priority_min_samples"):
            self._daily_adaptive_priority_min_samples = _PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES_DEFAULT

    def _get_fetcher_call_lock(self, fetcher: BaseFetcher) -> RLock:
        self._ensure_concurrency_guards()
        lock_owner = (
            fetcher._manager_call_identity()
            if isinstance(fetcher, DataProvider)
            else fetcher
        )
        fetcher_id = id(lock_owner)
        with self._fetcher_call_locks_lock:
            lock = self._fetcher_call_locks.get(fetcher_id)
            if lock is None:
                lock = RLock()
                self._fetcher_call_locks[fetcher_id] = lock
            return lock

    def _call_fetcher_method(self, fetcher: BaseFetcher, method_name: str, *args, **kwargs):
        """Serialize shared fetcher state access through manager-owned per-instance locks."""
        validation_instrument_type = kwargs.pop("_validation_instrument_type", None)
        method = getattr(fetcher, method_name)
        result_validator = kwargs.pop("_manager_result_validator", None)
        with self._get_fetcher_call_lock(fetcher):
            if method_name == "get_realtime_quote":
                result = method(*args, **kwargs)
                if result is not None:
                    from data_provider.data_validation import validate_and_annotate

                    stock_code = kwargs.get("stock_code") or (args[0] if args else "")
                    validate_and_annotate(
                        result,
                        data_type="realtime_quote",
                        market=_market_tag(normalize_stock_code(str(stock_code))),
                        stock_code=str(stock_code),
                        provider=fetcher.name,
                        instrument_type=(
                            validation_instrument_type
                            or getattr(result, "instrument_type", None)
                        ),
                    )
                return result
            if method_name != "get_daily_data":
                if result_validator is not None:
                    raise ValueError(
                        "_manager_result_validator is only supported for get_daily_data"
                    )
                return method(*args, **kwargs)

            stock_code = kwargs.get("stock_code") or (args[0] if args else "")
            market = _market_tag(normalize_stock_code(str(stock_code)))
            health_key = self._daily_health_key(fetcher, market)
            if not self._daily_source_health.is_available(health_key):
                self._mark_daily_health_recorded(health_key)
                logger.info(
                    "provider_health event=circuit_skip_after_queue data_type=daily_data provider=%s",
                    sanitize_diagnostic_text(fetcher.name, max_length=120),
                )
                raise CircuitOpenError(
                    f"[{fetcher.name}] provider circuit is in cooldown"
                )

            started_at = time.monotonic()
            try:
                result = method(*args, **kwargs)
                if result_validator is not None:
                    result = result_validator(result)
                if isinstance(result, pd.DataFrame) and not result.empty:
                    from data_provider.data_validation import validate_and_annotate

                    validate_and_annotate(
                        result,
                        data_type="daily_data",
                        market=market,
                        stock_code=str(stock_code),
                        provider=fetcher.name,
                        instrument_type=(
                            validation_instrument_type
                            or result.attrs.get("instrument_type")
                        ),
                    )
            except Exception as exc:
                latency_ms = (time.monotonic() - started_at) * 1000.0
                if type(exc).__name__ == "DataValidationRejected":
                    self._daily_source_health.record_quality_failure(
                        health_key,
                        latency_ms=latency_ms,
                    )
                else:
                    self._daily_source_health.record_failure(
                        health_key,
                        error="data_provider_daily_data_attempt_failed",
                        latency_ms=latency_ms,
                    )
                self._mark_daily_health_recorded(health_key)
                raise

            latency_ms = (time.monotonic() - started_at) * 1000.0
            if isinstance(result, pd.DataFrame):
                if result.empty:
                    self._daily_source_health.record_quality_failure(
                        health_key,
                        latency_ms=latency_ms,
                    )
                else:
                    self._daily_source_health.record_success(
                        health_key,
                        latency_ms=latency_ms,
                    )
                self._mark_daily_health_recorded(health_key)
            elif result is None:
                self._daily_source_health.record_quality_failure(
                    health_key,
                    latency_ms=latency_ms,
                )
            return result

    @classmethod
    def _daily_health_key(cls, fetcher: BaseFetcher, market: str) -> str:
        return f"daily_data:{market}:{fetcher.name}"

    @classmethod
    def _mark_daily_health_recorded(cls, health_key: str) -> None:
        pending = getattr(cls._daily_health_handoff, "pending", None)
        if pending is None:
            pending = {}
            cls._daily_health_handoff.pending = pending
        pending[health_key] = pending.get(health_key, 0) + 1

    @classmethod
    def _consume_daily_health_recorded(cls, health_key: str) -> bool:
        pending = getattr(cls._daily_health_handoff, "pending", None)
        if not pending or pending.get(health_key, 0) < 1:
            return False
        remaining = pending[health_key] - 1
        if remaining:
            pending[health_key] = remaining
        else:
            pending.pop(health_key, None)
        return True

    @classmethod
    def _configure_daily_source_health(cls) -> None:
        cls._daily_source_health.configure(
            enabled=_read_bool_env(
                "PROVIDER_CIRCUIT_BREAKER_ENABLED",
                _PROVIDER_CIRCUIT_ENABLED_DEFAULT,
            ),
            failure_threshold=_read_positive_int_env(
                "PROVIDER_CIRCUIT_FAILURE_THRESHOLD",
                _PROVIDER_CIRCUIT_FAILURE_THRESHOLD_DEFAULT,
            ),
            cooldown_seconds=_read_non_negative_float_env(
                "PROVIDER_CIRCUIT_COOLDOWN_SECONDS",
                _PROVIDER_CIRCUIT_COOLDOWN_SECONDS_DEFAULT,
            ),
            health_window_size=_read_positive_int_env(
                "PROVIDER_HEALTH_WINDOW_SIZE",
                _PROVIDER_HEALTH_WINDOW_SIZE_DEFAULT,
            ),
        )

    def _configure_daily_adaptive_priority(self) -> None:
        self._daily_adaptive_priority_enabled = _read_bool_env(
            "PROVIDER_ADAPTIVE_PRIORITY_ENABLED",
            _PROVIDER_ADAPTIVE_PRIORITY_ENABLED_DEFAULT,
        )
        self._daily_adaptive_priority_min_samples = _read_positive_int_env(
            "PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES",
            _PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES_DEFAULT,
        )

    @staticmethod
    def _daily_adaptive_sort_key(
        snapshot: Dict[str, Any],
        static_index: int,
    ) -> Tuple[float, float, float, int]:
        latency = snapshot.get("average_latency_ms")
        return (
            -float(snapshot.get("health_score", 0.0)),
            -float(snapshot.get("success_rate", 0.0)),
            float(latency) if latency is not None else float("inf"),
            static_index,
        )

    def _order_daily_fetchers(
        self,
        fetchers: List[DataProvider],
        market: str,
    ) -> List[DataProvider]:
        """Adapt contiguous eligible peers without crossing static or health anchors."""
        self._ensure_concurrency_guards()
        static_order = list(fetchers)
        if not self._daily_adaptive_priority_enabled or len(static_order) < 2:
            return static_order

        snapshots: Dict[int, Dict[str, Any]] = {}
        for static_index, fetcher in enumerate(static_order):
            health_key = self._daily_health_key(fetcher, market)
            snapshots[static_index] = self._daily_source_health.get_snapshot(health_key)[health_key]

        selected_order = list(static_order)
        eligible_count = 0
        run_positions: List[int] = []

        def rank_run() -> None:
            if len(run_positions) < 2:
                run_positions.clear()
                return
            ranked_positions = sorted(
                run_positions,
                key=lambda position: self._daily_adaptive_sort_key(
                    snapshots[position],
                    position,
                ),
            )
            for target_position, ranked_position in zip(run_positions, ranked_positions):
                selected_order[target_position] = static_order[ranked_position]
            run_positions.clear()

        for position, fetcher in enumerate(static_order):
            snapshot = snapshots[position]
            eligible = (
                snapshot["state"] == CircuitBreaker.CLOSED
                and snapshot["sample_count"]
                >= self._daily_adaptive_priority_min_samples
            )
            if not eligible:
                rank_run()
                continue

            if (
                run_positions
                and self._provider_priority(static_order[run_positions[-1]])
                != self._provider_priority(fetcher)
            ):
                rank_run()
            run_positions.append(position)
            eligible_count += 1
        rank_run()

        if selected_order != static_order:
            health_summary = [
                {
                    "provider": sanitize_diagnostic_text(fetcher.name, max_length=120),
                    "priority": self._provider_priority(fetcher),
                    "sample_count": snapshots[index]["sample_count"],
                    "success_rate": snapshots[index]["success_rate"],
                    "average_latency_ms": snapshots[index]["average_latency_ms"],
                    "health_score": snapshots[index]["health_score"],
                }
                for index, fetcher in enumerate(static_order)
            ]
            logger.info(
                "provider_priority event=adaptive_reorder data_type=daily_data market=%s "
                "min_samples=%d eligible_count=%d static_order=%s selected_order=%s health=%s",
                market,
                self._daily_adaptive_priority_min_samples,
                eligible_count,
                ",".join(
                    sanitize_diagnostic_text(fetcher.name, max_length=120)
                    for fetcher in static_order
                ),
                ",".join(
                    sanitize_diagnostic_text(fetcher.name, max_length=120)
                    for fetcher in selected_order
                ),
                _json.dumps(health_summary, sort_keys=True, separators=(",", ":")),
            )
        return selected_order

    @classmethod
    def _is_daily_source_available(
        cls,
        fetcher: BaseFetcher,
        market: str,
    ) -> bool:
        key = cls._daily_health_key(fetcher, market)
        if cls._daily_source_health.can_attempt(key):
            return True
        snapshot = cls._daily_source_health.get_snapshot(key)[key]
        logger.info(
            "provider_health event=circuit_skip data_type=daily_data market=%s "
            "provider=%s cooldown_remaining_seconds=%.3f health_score=%.2f",
            market,
            fetcher.name,
            snapshot["cooldown_remaining_seconds"],
            snapshot["health_score"],
        )
        return False

    @staticmethod
    def _daily_source_unavailable_error(fetcher: BaseFetcher) -> str:
        return f"[{fetcher.name}] (CircuitOpen) 数据源短期熔断"

    @classmethod
    def _record_daily_source_success(
        cls,
        fetcher: BaseFetcher,
        market: str,
        latency_ms: Optional[int] = None,
    ) -> None:
        health_key = cls._daily_health_key(fetcher, market)
        if cls._consume_daily_health_recorded(health_key):
            return
        cls._daily_source_health.record_success(
            health_key,
            latency_ms=latency_ms,
        )

    @classmethod
    def _record_daily_source_failure(
        cls,
        fetcher: BaseFetcher,
        market: str,
        error: str,
        latency_ms: Optional[int] = None,
    ) -> None:
        health_key = cls._daily_health_key(fetcher, market)
        if cls._consume_daily_health_recorded(health_key):
            return
        cls._daily_source_health.record_failure(
            health_key,
            error=error,
            latency_ms=latency_ms,
        )

    @classmethod
    def _next_daily_fallback_name(
        cls,
        fetchers: List[BaseFetcher],
        start_index: int,
        market: str,
    ) -> Optional[str]:
        for candidate in fetchers[start_index:]:
            health_key = cls._daily_health_key(candidate, market)
            if cls._daily_source_health.can_attempt(health_key):
                return candidate.name
        return None

    @classmethod
    def _next_named_daily_fallback_name(
        cls,
        source_order: List[str],
        start_index: int,
        fetchers: List[BaseFetcher],
        market: str,
    ) -> Optional[str]:
        fetchers_by_name = {fetcher.name: fetcher for fetcher in fetchers}
        for source_name in source_order[start_index:]:
            candidate = fetchers_by_name.get(source_name)
            if candidate is None:
                continue
            health_key = cls._daily_health_key(candidate, market)
            if cls._daily_source_health.can_attempt(health_key):
                return candidate.name
        return None

    @classmethod
    def _record_daily_source_circuit_skip(
        cls,
        fetcher: BaseFetcher,
        market: str,
        fallback_to: Optional[str],
    ) -> None:
        key = cls._daily_health_key(fetcher, market)
        snapshot = cls._daily_source_health.get_snapshot(key)[key]
        record_provider_run(
            data_type="daily_data",
            provider=fetcher.name,
            operation="get_daily_data",
            success=False,
            latency_ms=0,
            error_type="CircuitOpen",
            error_message="provider cooldown active",
            fallback_to=fallback_to,
            record_count=0,
        )
        logger.info(
            "provider_failover event=skip_open data_type=daily_data market=%s "
            "provider=%s fallback_to=%s health_score=%.2f",
            market,
            fetcher.name,
            fallback_to or "none",
            snapshot["health_score"],
        )

    @classmethod
    def get_daily_source_health_snapshot(cls) -> Dict[str, Dict[str, Any]]:
        """Return the current process-local daily provider health snapshot."""
        return cls._daily_source_health.get_snapshot()

    def get_daily_provider_health_report(
        self,
        market: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a JSON-serializable daily-provider health report for operators."""
        self._ensure_concurrency_guards()
        market_filter = str(market or "").strip().lower()
        if market_filter and market_filter not in self._DAILY_MARKETS:
            raise ValueError("market must be one of: cn, hk, us, jp, kr, tw")
        fetchers_by_name = {
            fetcher.name: fetcher
            for fetcher in self._get_fetchers_snapshot()
        }
        providers: List[Dict[str, Any]] = []
        for source, snapshot in self._daily_source_health.get_snapshot().items():
            source_parts = source.split(":", 2)
            if len(source_parts) != 3 or source_parts[0] != "daily_data":
                continue
            source_market, provider_name = source_parts[1], source_parts[2]
            if market_filter and source_market != market_filter:
                continue
            fetcher = fetchers_by_name.get(provider_name)
            registration = (
                None
                if fetcher is None
                else self._provider_plugin_registration(fetcher)
            )
            supported_markets = (
                registration.markets
                if registration is not None
                else self._DAILY_MARKET_FETCHER_SUPPORT.get(provider_name)
            )
            providers.append(
                {
                    "data_type": "daily_data",
                    "market": source_market,
                    "provider": sanitize_diagnostic_text(provider_name, max_length=120),
                    "static_priority": (
                        None
                        if fetcher is None
                        else self._provider_priority(fetcher)
                    ),
                    "supported_markets": (
                        sorted(supported_markets)
                        if supported_markets is not None
                        else None
                    ),
                    **{
                        key: value
                        for key, value in snapshot.items()
                        if key != "source"
                    },
                }
            )

        providers.sort(
            key=lambda item: (
                item["market"],
                item["static_priority"] is None,
                item["static_priority"] if item["static_priority"] is not None else 0,
                item["provider"],
            )
        )
        return {
            "schema_version": _PROVIDER_DAILY_HEALTH_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "market": market_filter or "all",
            "adaptive_priority": {
                "enabled": self._daily_adaptive_priority_enabled,
                "min_samples": self._daily_adaptive_priority_min_samples,
                "boundary": "equal_static_priority_after_capability_filtering",
            },
            "provider_count": len(providers),
            "providers": providers,
        }

    def log_daily_provider_health_report(
        self,
        market: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Write and return a structured, secret-free daily-provider health report."""
        report = self.get_daily_provider_health_report(market=market)
        logger.info(
            "provider_health event=snapshot data_type=daily_data market=%s payload=%s",
            report["market"],
            _json.dumps(report, sort_keys=True, separators=(",", ":")),
        )
        return report

    @classmethod
    def reset_daily_source_health(cls) -> None:
        """Reset daily source health state for tests/admin diagnostics."""
        cls._daily_source_health.reset()
        cls._daily_health_handoff.pending = {}


def _resolve_annotations(
    function: FunctionType,
    global_namespace: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve annotations exactly as they were defined in the legacy facade."""

    data_provider_type = global_namespace["DataProvider"]
    base_fetcher_type = global_namespace["BaseFetcher"]
    legacy_types = {
        "DataProvider": data_provider_type,
        "BaseFetcher": base_fetcher_type,
        "List[DataProvider]": List[data_provider_type],
        "Optional[DataProvider]": Optional[data_provider_type],
        "List[BaseFetcher]": List[base_fetcher_type],
        "RLock": RLock,
        "Dict[str, Dict[str, Any]]": Dict[str, Dict[str, Any]],
        "Dict[str, Any]": Dict[str, Any],
        "Optional[str]": Optional[str],
        "Optional[int]": Optional[int],
        "Tuple[float, float, float, int]": Tuple[float, float, float, int],
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


EXPECTED_DAILY_SOURCE_HEALTH_METHOD_NAMES = (
    "_ensure_concurrency_guards",
    "_get_fetcher_call_lock",
    "_call_fetcher_method",
    "_daily_health_key",
    "_mark_daily_health_recorded",
    "_consume_daily_health_recorded",
    "_configure_daily_source_health",
    "_configure_daily_adaptive_priority",
    "_daily_adaptive_sort_key",
    "_order_daily_fetchers",
    "_is_daily_source_available",
    "_daily_source_unavailable_error",
    "_record_daily_source_success",
    "_record_daily_source_failure",
    "_next_daily_fallback_name",
    "_next_named_daily_fallback_name",
    "_record_daily_source_circuit_skip",
    "get_daily_source_health_snapshot",
    "get_daily_provider_health_report",
    "log_daily_provider_health_report",
    "reset_daily_source_health",
)


def bind_daily_source_health_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind health/circuit descriptors without changing the manager interface."""

    bound_names = []
    for name, descriptor in vars(_DailySourceHealthMethods).items():
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
    # Reinstall final-exit validation after each facade bind/reload.
    try:
        from .data_validation_wiring import ensure_validation_wrappers

        ensure_validation_wrappers(target_class)
    except Exception as exc:  # broad-exception: fallback_recorded - validation install must not break imports
        log_safe_exception(
            logger,
            "data validation wrapper install skipped",
            exc,
            error_code="data_validation_install",
            level=logging.WARNING,
        )
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
