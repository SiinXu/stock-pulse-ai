# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned daily provider execution and cache-resolve orchestration.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. Health/circuit state stays in ``daily_source_health``; layered cache
storage stays in ``daily_cache.py`` and cache helpers stay in
``daily_cache_methods``. These descriptors own the public ``get_daily_data``
entry, one-provider call validation, and the fallback execution loop.
``DataFetcherManager`` remains the public import and patch surface.
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

import pandas as pd

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
DataFetchError = None  # type: ignore[assignment,misc]
DataProvider = None  # type: ignore[assignment,misc]
MarketDataFetchMode = None  # type: ignore[assignment,misc]
REQUIRED_DAILY_COLUMNS = None  # type: ignore[assignment,misc]
normalize_stock_code = None  # type: ignore[assignment,misc]
_market_tag = None  # type: ignore[assignment,misc]
_is_hk_market = None  # type: ignore[assignment,misc]
_is_jp_market = None  # type: ignore[assignment,misc]
_is_kr_market = None  # type: ignore[assignment,misc]
_is_tw_market = None  # type: ignore[assignment,misc]
record_provider_run = None  # type: ignore[assignment,misc]
record_provider_run_started = None  # type: ignore[assignment,misc]
summarize_exception = None  # type: ignore[assignment,misc]

logger = logging.getLogger("src.data_provider.base")

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _DailyProviderExecutionMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def _call_daily_data_provider(
        self,
        fetcher: DataProvider,
        *,
        stock_code: str,
        start_date: Optional[str],
        end_date: Optional[str],
        days: int,
        validation_instrument_type: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """Call one provider and reject unusable normalized daily schemas."""

        def _validate_result(frame: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
            if frame is None or frame.empty:
                return frame
            missing_columns = [
                column for column in REQUIRED_DAILY_COLUMNS if column not in frame.columns
            ]
            if missing_columns:
                raise DataFetchError(
                    f"[{fetcher.name}] daily data is missing required columns: "
                    f"{','.join(missing_columns)}"
                )
            if not pd.to_datetime(frame["date"], errors="coerce").notna().any():
                raise DataFetchError(
                    f"[{fetcher.name}] daily data has no valid date values"
                )
            return frame

        return self._call_fetcher_method(
            fetcher,
            "get_daily_data",
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            days=days,
            _manager_result_validator=_validate_result,
            _validation_instrument_type=validation_instrument_type,
        )

    def get_daily_data(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30,
    ) -> Tuple[pd.DataFrame, str]:
        """Resolve daily bars through the configured local-first contract.

        This is the single orchestration owner. The provider-chain method below
        retains market eligibility, plugin routing, adaptive/circuit state,
        diagnostics, and per-provider fallback, but it performs no cache reads,
        writes, or stale fallback of its own.
        """
        from .us_index_mapping import is_us_index_code, is_us_stock_code

        normalized_code = normalize_stock_code(stock_code)
        request_start = time.time()
        cache_key = self._daily_cache_key(
            normalized_code,
            start_date,
            end_date,
            days,
            adjustment=self._daily_adjustment_identity(),
        )
        daily_cache = self._get_daily_data_cache()
        network_fetch = None
        if daily_cache.fetch_mode is not MarketDataFetchMode.LOCAL_ONLY:
            network_fetch = lambda: self._get_daily_data_from_providers(
                normalized_code,
                start_date=start_date,
                end_date=end_date,
                days=days,
            )

        result = daily_cache.resolve(
            cache_key,
            network_fetch=network_fetch,
            required_fields=REQUIRED_DAILY_COLUMNS,
            cached_candidate_validator=lambda frame, source_name: self._validate_daily_candidate(
                frame,
                stock_code=normalized_code,
                source_name=source_name,
            ),
        )

        if result.from_cache:
            self._record_daily_cache_result(result, request_start)
        if result.is_stale:
            is_us_index = is_us_index_code(normalized_code)
            is_us = is_us_index or is_us_stock_code(normalized_code)
            is_hk = (not is_us) and _is_hk_market(normalized_code)
            is_jp = (not is_us) and (not is_hk) and _is_jp_market(normalized_code)
            is_kr = (not is_us) and (not is_hk) and _is_kr_market(normalized_code)
            is_tw = (
                (not is_us)
                and (not is_hk)
                and (not is_jp)
                and (not is_kr)
                and _is_tw_market(normalized_code)
            )
            market = (
                "us"
                if is_us
                else "hk"
                if is_hk
                else "jp"
                if is_jp
                else "kr"
                if is_kr
                else "tw"
                if is_tw
                else "cn"
            )
            logger.warning(
                "provider_failover event=stale_cache data_type=daily_data symbol=%s "
                "market=%s source=%s stale_seconds=%d provider_failure_count=%d",
                sanitize_diagnostic_text(normalized_code, max_length=80),
                market,
                sanitize_diagnostic_text(result.source_name, max_length=120),
                int(result.age_seconds),
                result.provider_failure_count,
            )
        return result.frame, result.source_name

    def _get_daily_data_from_providers(
        self, 
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30
    ) -> Tuple[pd.DataFrame, str]:
        """
        Fetch daily data from the existing provider fallback chain exactly once.
        
        故障切换策略：
        1. 美股指数/美股股票直接路由到 YfinanceFetcher
        2. 其他代码从最高优先级数据源开始尝试
        3. 捕获异常后自动切换到下一个
        4. 记录每个数据源的失败原因
        5. 所有数据源失败后抛出详细异常
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            days: 获取天数
            
        Returns:
            Tuple[DataFrame, str]: (数据, 成功的数据源名称)
            
        Raises:
            DataFetchError: 所有数据源都失败时抛出
        """
        from .us_index_mapping import is_us_index_code, is_us_stock_code

        # Normalize code (strip SH/SZ prefix etc.)
        stock_code = normalize_stock_code(stock_code)
        market = _market_tag(stock_code)
        from src.data_provider.data_validation import infer_instrument_type

        instrument_type = infer_instrument_type(stock_code)

        request_start = time.time()
        fetchers = self._get_fetchers_snapshot()
        errors = []
        provider_failure_count = 0

        # Quick path: Use dedicated data source routing for US stocks; filter out data sources that do not support Hong Kong daily lines for Hong Kong stocks
        #   - Configure Longbridge credentials: Longbridge is preferred, YFinance/AkShare fallback.
        #   - Without Longbridge credentials: prefer YFinance for U.S. stocks and the generic fetcher loop for Hong Kong stocks.
        #   - U.S. stock indices: Always use YFinance as the primary source (Longbridge does not provide index candles)
        is_us_index = is_us_index_code(stock_code)
        is_us = is_us_index or is_us_stock_code(stock_code)
        is_hk = (not is_us) and _is_hk_market(stock_code)
        is_jp = (not is_us) and (not is_hk) and _is_jp_market(stock_code)
        is_kr = (not is_us) and (not is_hk) and _is_kr_market(stock_code)
        is_tw = (not is_us) and (not is_hk) and _is_tw_market(stock_code)
        market = _market_tag(stock_code)
        fetchers = self._filter_daily_fetchers_for_market(fetchers, market)
        fetchers = self._filter_fetchers_by_capability(fetchers, capability="daily_data")
        if not is_us:
            fetchers = self._order_daily_fetchers(fetchers, market)
        total_fetchers = len(fetchers)

        if total_fetchers == 0:
            market_label = "加密资产" if market == "crypto" else "美股指数" if is_us_index else "美股" if is_us else "港股" if is_hk else "台股" if is_tw else "A股"
            error_summary = f"{market_label} {stock_code} 获取失败:\n暂无可用数据源"
            logger.error(f"[数据源终止] {stock_code} 获取失败: {error_summary}")
            raise DataFetchError(error_summary, provider_failure_count=0)

        # US stocks (including US stock indices) use dedicated routing; Hong Kong stocks use the standard data source loop
        # Failover chain: Finnhub(P2) -> AlphaVantage(P3) -> Yfinance(P4) -> Longbridge(P5)
        # When Longbridge preferred: Longbridge -> Finnhub -> AlphaVantage -> Yfinance
        if is_us:
            prefer_lb = self._longbridge_preferred(capability="daily_data") and not is_us_index
            if is_us_index:
                # Always use YFinance for the index (Longbridge does not provide index K-lines)
                source_order = ["YfinanceFetcher", "FinnhubFetcher"]
            elif prefer_lb:
                source_order = ["LongbridgeFetcher", "FinnhubFetcher", "AlphaVantageFetcher", "YfinanceFetcher"]
            else:
                source_order = ["FinnhubFetcher", "AlphaVantageFetcher", "YfinanceFetcher", "LongbridgeFetcher"]
            pin_first = bool(is_us_index or prefer_lb)
            source_order = self._order_us_sources_by_priority(
                source_order,
                pin_first=pin_first,
            )
            source_order.extend(
                fetcher.name
                for fetcher in fetchers
                if (
                    fetcher.name not in source_order
                    and self._provider_plugin_registration(fetcher) is not None
                )
            )
            market_label = "美股指数" if is_us_index else "美股"

            for order_index, src_name in enumerate(source_order):
                fallback_to = self._next_named_daily_fallback_name(
                    source_order,
                    order_index + 1,
                    fetchers,
                    market,
                )
                for attempt, fetcher in enumerate(fetchers, start=1):
                    if fetcher.name != src_name:
                        continue
                    if not self._is_daily_source_available(fetcher, market):
                        provider_failure_count += 1
                        self._record_daily_source_circuit_skip(
                            fetcher,
                            market,
                            fallback_to,
                        )
                        errors.append(self._daily_source_unavailable_error(fetcher))
                        break
                    attempt_start = time.time()
                    try:
                        role = "首选" if src_name == source_order[0] else "兜底"
                        logger.info(
                            f"[数据源尝试 {attempt}/{total_fetchers}] [{fetcher.name}] "
                            f"{market_label} {stock_code} {role}路由..."
                        )
                        record_provider_run_started(
                            data_type="daily_data",
                            provider=fetcher.name,
                            operation="get_daily_data",
                        )
                        df = self._call_daily_data_provider(
                            fetcher,
                            stock_code=stock_code,
                            start_date=start_date,
                            end_date=end_date,
                            days=days,
                            validation_instrument_type=instrument_type,
                        )
                        if df is not None and not df.empty:
                            duration_ms = int((time.time() - attempt_start) * 1000)
                            record_provider_run(
                                data_type="daily_data",
                                provider=fetcher.name,
                                operation="get_daily_data",
                                success=True,
                                latency_ms=duration_ms,
                                cache_hit=False,
                                record_count=len(df),
                            )
                            elapsed = time.time() - request_start
                            logger.info(
                                f"[数据源完成] {stock_code} 使用 [{fetcher.name}] 获取成功: "
                                f"rows={len(df)}, elapsed={elapsed:.2f}s"
                            )
                            self._record_daily_source_success(fetcher, market)
                            return df, fetcher.name
                        duration_ms = int((time.time() - attempt_start) * 1000)
                        provider_failure_count += 1
                        record_provider_run(
                            data_type="daily_data",
                            provider=fetcher.name,
                            operation="get_daily_data",
                            success=False,
                            latency_ms=duration_ms,
                            error_type="empty",
                            error_message="empty result",
                            fallback_to=fallback_to,
                            record_count=0,
                        )
                        # Quality failure (empty/None): do not open the exception circuit,
                        # but still surface a per-provider line in the final DataFetchError.
                        empty_kind = "empty frame" if df is not None and df.empty else "none result"
                        errors.append(f"[{fetcher.name}] (empty) {empty_kind}")
                        if df is not None and df.empty:
                            self._record_daily_source_success(fetcher, market)
                    except Exception as e:  # broad-exception: fallback_recorded - safe provider-run and log precede failover
                        provider_failure_count += 1
                        error_type, error_reason = summarize_exception(e)
                        error_msg = f"[{fetcher.name}] ({error_type}) {error_reason}"
                        duration_ms = int((time.time() - attempt_start) * 1000)
                        record_provider_run(
                            data_type="daily_data",
                            provider=fetcher.name,
                            operation="get_daily_data",
                            success=False,
                            latency_ms=duration_ms,
                            error_type=error_type,
                            error_message=error_reason,
                            fallback_to=fallback_to,
                        )
                        log_safe_exception(
                            logger,
                            "Data provider daily data attempt failed",
                            e,
                            error_code="data_provider_daily_data_attempt_failed",
                            level=logging.WARNING,
                            context={
                                "symbol": stock_code,
                                "provider": fetcher.name,
                                "market": market,
                                "attempt": attempt,
                            },
                        )
                        self._record_daily_source_failure(
                            fetcher,
                            market,
                            "data_provider_daily_data_attempt_failed",
                        )
                        errors.append(error_msg)
                    break

            error_summary = f"{market_label} {stock_code} 获取失败:\n" + "\n".join(errors)
            logger.error(
                "All eligible data providers failed daily data request symbol=%s market=%s",
                stock_code,
                market,
            )
            raise DataFetchError(
                error_summary,
                provider_failure_count=provider_failure_count,
            )

        for attempt, fetcher in enumerate(fetchers, start=1):
            fallback_to = self._next_daily_fallback_name(
                fetchers,
                attempt,
                market,
            )
            if not self._is_daily_source_available(fetcher, market):
                provider_failure_count += 1
                self._record_daily_source_circuit_skip(
                    fetcher,
                    market,
                    fallback_to,
                )
                errors.append(self._daily_source_unavailable_error(fetcher))
                continue
            attempt_start = time.time()
            try:
                logger.info(f"[数据源尝试 {attempt}/{total_fetchers}] [{fetcher.name}] 获取 {stock_code}...")
                record_provider_run_started(
                    data_type="daily_data",
                    provider=fetcher.name,
                    operation="get_daily_data",
                )
                df = self._call_daily_data_provider(
                    fetcher,
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    days=days,
                    validation_instrument_type=instrument_type,
                )
                
                if df is not None and not df.empty:
                    duration_ms = int((time.time() - attempt_start) * 1000)
                    record_provider_run(
                        data_type="daily_data",
                        provider=fetcher.name,
                        operation="get_daily_data",
                        success=True,
                        latency_ms=duration_ms,
                        cache_hit=False,
                        record_count=len(df),
                    )
                    elapsed = time.time() - request_start
                    logger.info(
                        f"[数据源完成] {stock_code} 使用 [{fetcher.name}] 获取成功: "
                        f"rows={len(df)}, elapsed={elapsed:.2f}s"
                    )
                    self._record_daily_source_success(fetcher, market)
                    return df, fetcher.name
                duration_ms = int((time.time() - attempt_start) * 1000)
                provider_failure_count += 1
                record_provider_run(
                    data_type="daily_data",
                    provider=fetcher.name,
                    operation="get_daily_data",
                    success=False,
                    latency_ms=duration_ms,
                    error_type="empty",
                    error_message="empty result",
                    fallback_to=fallback_to,
                    record_count=0,
                )
                # Quality failure (empty/None): keep circuit closed for empty frames,
                # but still surface a per-provider line in the final DataFetchError.
                empty_kind = "empty frame" if df is not None and df.empty else "none result"
                errors.append(f"[{fetcher.name}] (empty) {empty_kind}")
                if df is not None and df.empty:
                    self._record_daily_source_success(fetcher, market)

            except Exception as e:  # broad-exception: fallback_recorded - safe provider-run and log precede failover
                provider_failure_count += 1
                error_type, error_reason = summarize_exception(e)
                error_msg = f"[{fetcher.name}] ({error_type}) {error_reason}"
                duration_ms = int((time.time() - attempt_start) * 1000)
                record_provider_run(
                    data_type="daily_data",
                    provider=fetcher.name,
                    operation="get_daily_data",
                    success=False,
                    latency_ms=duration_ms,
                    error_type=error_type,
                    error_message=error_reason,
                    fallback_to=fallback_to,
                )
                log_safe_exception(
                    logger,
                    "Data provider daily data attempt failed",
                    e,
                    error_code="data_provider_daily_data_attempt_failed",
                    level=logging.WARNING,
                    context={
                        "symbol": stock_code,
                        "provider": fetcher.name,
                        "market": market,
                        "attempt": attempt,
                    },
                )
                self._record_daily_source_failure(
                    fetcher,
                    market,
                    "data_provider_daily_data_attempt_failed",
                )
                errors.append(error_msg)
                if fallback_to is not None:
                    logger.info(
                        "[数据源切换] %s: [%s] -> [%s]",
                        stock_code,
                        fetcher.name,
                        fallback_to,
                    )
                # Try the next data source
                continue
        
        # All data sources failed
        error_summary = f"所有数据源获取 {stock_code} 失败:\n" + "\n".join(errors)
        logger.error(
            "All data providers failed daily data request symbol=%s market=%s",
            stock_code,
            market,
        )
        raise DataFetchError(
            error_summary,
            provider_failure_count=provider_failure_count,
        )

    def _order_us_sources_by_priority(
        self,
        source_order: list,
        *,
        pin_first: bool,
    ) -> list:
        """Stable-sort builtin US daily names by live fetcher priority.

        Named US routes remain the starting chain. When ``pin_first`` is true,
        the first name stays at the head (YFinance for US indexes, Longbridge
        when preferred) and only the remainder is sorted. Names missing from
        the fetcher snapshot sort last. Empty input is returned unchanged.
        Plugin names are not passed in; the caller appends the plugin tail
        after this sort.
        """
        if not source_order:
            return list(source_order)

        priority_by_name = {
            fetcher.name: fetcher.priority
            for fetcher in self._get_fetchers_snapshot()
        }
        missing_priority = 10 ** 9

        def _priority(name: str) -> int:
            return priority_by_name.get(name, missing_priority)

        if pin_first:
            head = source_order[0]
            return [head] + sorted(source_order[1:], key=_priority)
        return sorted(source_order, key=_priority)


EXPECTED_DAILY_PROVIDER_EXECUTION_METHOD_NAMES = (
    "_call_daily_data_provider",
    "get_daily_data",
    "_get_daily_data_from_providers",
    "_order_us_sources_by_priority",
)


def bind_daily_provider_execution_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind daily execution descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_DailyProviderExecutionMethods).items():
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
