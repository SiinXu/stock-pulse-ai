# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned stock-name lookup rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. Stock-name memory cache helpers stay in ``daily_cache_methods``.
Bulk/prefetch entry points (``prefetch_stock_names``,
``batch_get_stock_names``), the static ``STOCK_NAME_MAP`` / index lookup
helpers, rankings, loader/cache, and other manager workflows stay on the
facade. These descriptors own single-code ``get_stock_name`` routing:
cache/static/index precedence, the local-only short circuit, the optional
realtime probe, provider capability ordering with the US-capable
allow-list, and the all-sources-failed fallback.
``DataFetcherManager`` remains the public import and patch surface.
"""

from __future__ import annotations

import logging
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
STOCK_NAME_MAP = None  # type: ignore[assignment,misc]
is_meaningful_stock_name = None  # type: ignore[assignment,misc]
get_index_stock_name = None  # type: ignore[assignment,misc]

logger = logging.getLogger("src.data_provider.base")

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _StockNameMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def get_stock_name(self, stock_code: str, allow_realtime: bool = True) -> Optional[str]:
        """
        获取股票中文名称（自动切换数据源）
        
        尝试从多个数据源获取股票名称：
        1. 先从内存缓存中获取（如果有）
        2. 再尝试本地维护映射与 stocks.index.json 索引
        3. 然后按需查询实时行情
        4. 依次尝试各个数据源的 get_stock_name 方法
        
        Args:
            stock_code: 股票代码
            allow_realtime: Whether to query realtime quote first. Set False when
                caller only wants lightweight prefetch without triggering heavy
                realtime source calls.
            
        Returns:
            股票中文名称，所有数据源都失败则返回 None
        """
        raw_stock_code = (stock_code or "").strip()
        # Normalize code (strip SH/SZ prefix etc.)
        stock_code = normalize_stock_code(stock_code)
        static_name = STOCK_NAME_MAP.get(stock_code)

        # 1. Check cache
        cached_name = self._get_cached_stock_name(stock_code)
        if cached_name is not None:
            return cached_name
        
        if is_meaningful_stock_name(static_name, stock_code):
            return self._cache_stock_name(stock_code, static_name) or static_name

        index_name = get_index_stock_name(stock_code)
        if is_meaningful_stock_name(index_name, stock_code):
            return self._cache_stock_name(stock_code, index_name) or index_name

        # Stock-name fallbacks are provider-backed. In market-data local-only
        # mode, retain local maps/caches above but never enter a provider or
        # realtime callback merely to decorate an otherwise local analysis.
        if self.is_market_data_local_only():
            return ""

        # 2. Attempt to fetch from real-time quotes (fastest, can be disabled on demand)
        if allow_realtime:
            quote = self.get_realtime_quote(raw_stock_code or stock_code, log_final_failure=False)
            if quote and hasattr(quote, 'name') and is_meaningful_stock_name(getattr(quote, 'name', ''), stock_code):
                name = quote.name
                self._cache_stock_name(stock_code, name)
                logger.info(f"[股票名称] 从实时行情获取: {stock_code} -> {name}")
                return name

        # 3. Try each data source sequentially
        from .akshare_fetcher import _is_us_code
        is_us = _is_us_code(stock_code)
        _US_CAPABLE_FETCHERS = {"YfinanceFetcher", "LongbridgeFetcher", "FinnhubFetcher", "AlphaVantageFetcher"}
        for fetcher in self._get_fetchers_for_capability(
            "stock_name",
            market=_market_tag(stock_code),
        ):
            if not hasattr(fetcher, 'get_stock_name'):
                continue
            is_plugin = self._provider_plugin_registration(fetcher) is not None
            if is_us and fetcher.name not in _US_CAPABLE_FETCHERS and not is_plugin:
                continue
            if not self._is_fetcher_available(fetcher, capability="stock_name"):
                continue
            try:
                name = self._call_fetcher_method(fetcher, 'get_stock_name', stock_code)
                if is_meaningful_stock_name(name, stock_code):
                    self._cache_stock_name(stock_code, name)
                    logger.info(f"[股票名称] 从 {fetcher.name} 获取: {stock_code} -> {name}")
                    return name
            except Exception as e:  # broad-exception: fallback_recorded - safe log precedes stock-name fallback
                log_safe_exception(
                    logger,
                    "Data provider stock name lookup failed",
                    e,
                    error_code="data_provider_stock_name_lookup_failed",
                    level=logging.DEBUG,
                    context={"symbol": stock_code, "provider": fetcher.name},
                )
                continue

        # 4. All data sources failed
        logger.warning(f"[股票名称] 所有数据源都无法获取 {stock_code} 的名称")
        return ""


EXPECTED_STOCK_NAME_METHOD_NAMES = (
    "get_stock_name",
)


def bind_stock_name_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind stock-name descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_StockNameMethods).items():
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
