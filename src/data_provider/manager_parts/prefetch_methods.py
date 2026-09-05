# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned prefetch methods rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. Facade ``__init__`` / ``__del__`` and TickFlow lifecycle stay on
the facade or their existing owners. These descriptors own
``prefetch_realtime_quotes`` and ``prefetch_daily_klines``.
Config is resolved through rebound ``self._get_fundamental_config()`` (not
bare ``get_config()``). ``DataFetcherManager`` remains the public import
and patch surface.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
)

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
logger = None  # type: ignore[assignment,misc]
logging = None  # type: ignore[assignment,misc]
log_safe_exception = None  # type: ignore[assignment,misc]
normalize_stock_code = None  # type: ignore[assignment,misc]

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _PrefetchMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def prefetch_realtime_quotes(self, stock_codes: List[str]) -> int:
        """
        批量预取实时行情数据（在分析开始前调用）

        策略：
        1. 检查优先级中是否包含适合预取的数据源（efinance/akshare_em/tushare/tickflow）
        2. 如果不包含，跳过预取（新浪/腾讯是单股票查询，无需预取）
        3. 如果自选股数量 >= 5 且使用可预取数据源，则预取填充缓存

        这样做的好处：
        - 使用新浪/腾讯时：每只股票独立查询，无全量拉取问题
        - 使用 efinance/东财/Tushare 时：预取一次，后续缓存命中
        - 使用 TickFlow 时：按当前自选股批量预取，避免逐股重复请求

        Args:
            stock_codes: 待分析的股票代码列表

        Returns:
            预取的股票数量（0 表示跳过预取）
        """
        if self.is_market_data_local_only():
            logger.debug(
                "[prefetch] component=realtime_prefetch action=skip reason=local_only"
            )
            return 0

        # Normalize all codes
        stock_codes = [normalize_stock_code(c) for c in stock_codes]

        config = self._get_fundamental_config()

        # Issue #455: PREFETCH_REALTIME_QUOTES=false Can disable pre-fetching, Avoid pulling the entire market
        if not getattr(config, "prefetch_realtime_quotes", True):
            logger.debug("[预取] component=realtime_prefetch action=skip reason=disabled")
            return 0

        # If real-time market data is disabled, skip prefetching.
        if not config.enable_realtime_quote:
            logger.debug("[预取] component=realtime_prefetch action=skip reason=realtime_quote_disabled")
            return 0

        # Check if priority includes suitable data sources for batch prefetching
        # efinance/akshare_em/tushare Populate the full market cache with a single call.;
        # tickflow retrieves current watchlist stocks in cache via symbols batch interface.
        priority = config.realtime_source_priority.lower()
        prefetch_sources = ['efinance', 'akshare_em', 'tushare', 'tickflow']

        # If the top two sources in priority are not prefetchable data sources, skip prefetch
        # Since Sina/ Tencent are single-stock queries, no prefetching is needed
        priority_list = [s.strip() for s in priority.split(',')]
        first_prefetch_source_index = None
        for i, source in enumerate(priority_list):
            if source in prefetch_sources:
                first_prefetch_source_index = i
                break

        # If no cacheable data source is available or it ranks after the 3rd position, skip fetching.
        if first_prefetch_source_index is None or first_prefetch_source_index >= 2:
            logger.info(
                "[预取] component=realtime_prefetch action=skip reason=no_early_prefetch_source priority=%s",
                priority,
            )
            return 0

        # If the number of stocks is less than 5, do not perform batch fetching (individual queries are more efficient).
        if len(stock_codes) < 5:
            logger.info(
                "[预取] component=realtime_prefetch action=skip reason=small_batch "
                "stock_count=%d threshold=5 prefetch_source=%s",
                len(stock_codes),
                priority_list[first_prefetch_source_index],
            )
            return 0

        prefetch_source = priority_list[first_prefetch_source_index]
        logger.info(
            "[预取] component=realtime_prefetch action=start stock_count=%d prefetch_source=%s first_code=%s",
            len(stock_codes),
            prefetch_source,
            stock_codes[0],
        )

        # TickFlow uses symbols batch interface; other prefetch sources trigger their own cache upon the first query.
        if prefetch_source == "tickflow":
            fetcher = self._get_fetcher_by_name("TickFlowFetcher", capability="realtime_quote")
            if fetcher is None or not hasattr(fetcher, "prefetch_realtime_quotes"):
                logger.info(
                    "[prefetch] component=realtime_prefetch action=skip reason=tickflow_unavailable"
                )
                return 0
            try:
                return int(
                    self._call_fetcher_method(
                        fetcher,
                        "prefetch_realtime_quotes",
                        stock_codes,
                        batch_size=getattr(config, "tickflow_batch_size", 100),
                    )
                    or 0
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Safe diagnostics preserve per-symbol fallback after optional TickFlow prefetch fails.
                log_safe_exception(
                    logger,
                    "TickFlow realtime quote prefetch failed",
                    exc,
                    error_code="tickflow_realtime_prefetch_failed",
                    level=logging.WARNING,
                )
                return 0

        try:
            # Use the first stock to trigger full data pull.
            first_code = stock_codes[0]
            quote = self.get_realtime_quote(first_code)

            if quote:
                logger.info(
                    "[预取] component=realtime_prefetch action=complete status=success "
                    "stock_count=%d prefetch_source=%s",
                    len(stock_codes),
                    prefetch_source,
                )
                return len(stock_codes)
            else:
                logger.warning(
                    "[预取] component=realtime_prefetch action=complete status=failed "
                    "stock_count=%d prefetch_source=%s fallback=per_stock",
                    len(stock_codes),
                    prefetch_source,
                )
                return 0

        except Exception as e:  # broad-exception: fallback_recorded - Safe diagnostics preserve per-symbol fallback after optional realtime prefetch fails.
            log_safe_exception(
                logger,
                "Realtime quote prefetch failed",
                e,
                error_code="realtime_quote_prefetch_failed",
                level=logging.ERROR,
                context={"provider": prefetch_source},
            )
            return 0

    def prefetch_daily_klines(self, stock_codes: List[str], days: int = 30) -> int:
        """Batch-prefetch TickFlow daily K-lines without changing per-stock callers."""
        if self.is_market_data_local_only():
            logger.debug(
                "[prefetch] component=daily_kline_prefetch action=skip reason=local_only"
            )
            return 0
        fetcher = self._get_fetcher_by_name("TickFlowFetcher", capability="daily_data")
        if fetcher is None or not hasattr(fetcher, "prefetch_daily_klines"):
            return 0

        try:
            return int(
                self._call_fetcher_method(
                    fetcher,
                    "prefetch_daily_klines",
                    stock_codes,
                    days=days,
                )
                or 0
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Safe diagnostics preserve per-symbol fallback after optional daily prefetch fails.
            log_safe_exception(
                logger,
                "TickFlow daily K-line prefetch failed",
                exc,
                error_code="tickflow_daily_kline_prefetch_failed",
                level=logging.WARNING,
            )
            return 0


EXPECTED_PREFETCH_METHOD_NAMES: Tuple[str, ...] = (
    "prefetch_realtime_quotes",
    "prefetch_daily_klines",
)


def bind_prefetch_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind prefetch descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_PrefetchMethods).items():
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
