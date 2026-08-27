# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned chip-distribution orchestration rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. Pure chip metric helpers stay in ``chip_helpers.py``. Call locks
that enter ``pull_coalesce`` stay in ``daily_source_health``. Stock-name,
rankings, loader/cache, and other manager workflows stay on the facade.
These descriptors own ``get_chip_distribution`` routing, provider
priority, fallback/error behavior, and chip-circuit success/failure/
inconclusive accounting. ``DataFetcherManager`` remains the public import
and patch surface.
"""

from __future__ import annotations

import logging
import time
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    Type,
)

from src.utils.sanitize import log_safe_exception

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
normalize_stock_code = None  # type: ignore[assignment,misc]
_market_tag = None  # type: ignore[assignment,misc]
record_provider_run = None  # type: ignore[assignment,misc]
record_provider_run_started = None  # type: ignore[assignment,misc]
summarize_exception = None  # type: ignore[assignment,misc]
_is_meaningful_chip_distribution = None  # type: ignore[assignment,misc]

logger = logging.getLogger("src.data_provider.base")

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _ChipDistributionMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def get_chip_distribution(self, stock_code: str):
        """
        获取筹码分布数据（带熔断和多数据源降级）

        策略：
        1. 检查配置开关
        2. 检查熔断器状态
        3. 依次尝试多个数据源：数据源优先级与获取daily的数据优先级一致
        4. 所有数据源失败则返回 None（降级兜底）

        Args:
            stock_code: 股票代码

        Returns:
            ChipDistribution 对象，失败则返回 None
        """
        # Normalize code (strip SH/SZ prefix etc.)
        stock_code = normalize_stock_code(stock_code)
        if _market_tag(stock_code) == "crypto":
            logger.debug("[chip distribution] not applicable to crypto asset %s", stock_code)
            return None

        from .realtime_types import get_chip_circuit_breaker

        config = self._get_fundamental_config()

        # Return None immediately when chip distribution is disabled.
        if not config.enable_chip_distribution:
            logger.debug(f"[筹码分布] 功能已禁用，跳过 {stock_code}")
            return None

        circuit_breaker = get_chip_circuit_breaker()

        candidate_fetchers = []
        # Iterate through the manager's capability-filtered priority order.
        for fetcher in self._get_fetchers_for_capability(
            "chip_distribution",
            market=_market_tag(stock_code),
        ):
            # Use only data sources that implement chip-distribution logic.
            if not hasattr(fetcher, 'get_chip_distribution'):
                continue

            fetcher_name = fetcher.name
            # Dynamically generate the key for the circuit breaker, e.g., "TushareFetcher" -> "tushare_chip"
            source_key = f"{fetcher_name.replace('Fetcher', '').lower()}_chip"

            # Check the circuit breaker status
            if not circuit_breaker.is_available(source_key):
                logger.debug(f"[熔断] {fetcher_name} 筹码接口处于熔断状态，尝试下一个")
                continue

            candidate_fetchers.append((fetcher, fetcher_name, source_key))

        for index, (fetcher, fetcher_name, source_key) in enumerate(candidate_fetchers):
            fallback_to = (
                candidate_fetchers[index + 1][1]
                if index + 1 < len(candidate_fetchers)
                else None
            )
            attempt_start = time.time()
            try:
                record_provider_run_started(
                    data_type="chip",
                    provider=fetcher_name,
                    operation="get_chip_distribution",
                )
                chip = self._call_fetcher_method(fetcher, 'get_chip_distribution', stock_code)
                latency_ms = int((time.time() - attempt_start) * 1000)
                if _is_meaningful_chip_distribution(chip):
                    record_provider_run(
                        data_type="chip",
                        provider=fetcher_name,
                        operation="get_chip_distribution",
                        success=True,
                        latency_ms=latency_ms,
                        record_count=1,
                    )
                    circuit_breaker.record_success(source_key)
                    logger.info(f"[筹码分布] {stock_code} 成功获取 (来源: {fetcher_name})")
                    return chip
                else:
                    record_provider_run(
                        data_type="chip",
                        provider=fetcher_name,
                        operation="get_chip_distribution",
                        success=False,
                        latency_ms=latency_ms,
                        error_type="empty",
                        error_message="empty or incomplete chip distribution",
                        fallback_to=fallback_to,
                        record_count=0,
                    )
                    if chip is not None:
                        logger.warning(
                            "[筹码分布] %s 返回字段不完整或占位值，继续尝试下一个数据源",
                            fetcher_name,
                        )
                    # Empty result or placeholder: Release HALF_OPEN probe slot, avoid getting stuck.
                    circuit_breaker.record_inconclusive(source_key)
            except Exception as e:  # broad-exception: fallback_recorded - diagnostics precede chip fallback
                error_type, error_reason = summarize_exception(e)
                record_provider_run(
                    data_type="chip",
                    provider=fetcher_name,
                    operation="get_chip_distribution",
                    success=False,
                    latency_ms=int((time.time() - attempt_start) * 1000),
                    error_type=error_type,
                    error_message=error_reason,
                    fallback_to=fallback_to,
                )
                log_safe_exception(
                    logger,
                    "Data provider chip distribution fetch failed",
                    e,
                    error_code="data_provider_chip_distribution_failed",
                    level=logging.WARNING,
                    context={"symbol": stock_code, "provider": fetcher_name},
                )
                circuit_breaker.record_failure(
                    source_key,
                    "data_provider_chip_distribution_failed",
                )
                continue

        logger.warning(f"[筹码分布] {stock_code} 所有数据源均失败")
        return None


EXPECTED_CHIP_DISTRIBUTION_METHOD_NAMES = (
    "get_chip_distribution",
)


def bind_chip_distribution_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind chip-distribution descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_ChipDistributionMethods).items():
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
