# -*- coding: utf-8 -*-
"""Pytdx daily history methods: raw fetch and normalize.

Method bodies are rebound onto ``PytdxFetcher`` by the compatibility
facade (ADR-006) so free-name lookups and test patches stay on
``src.data_provider.pytdx_fetcher``. Tenacity ``provider_retry`` is
re-applied on the facade after bind, only for ``_fetch_raw_data``.

Connection ownership stays on the facade. ``_get_pytdx``,
``_pytdx_session``, cooldown helpers, and ``_get_market_code`` are
reached through ``self`` at call time.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.pytdx_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.pytdx_fetcher")
DataFetchError = Exception  # type: ignore[assignment,misc]
STANDARD_COLUMNS = ()  # type: ignore[assignment]
DEFAULT_RETRYABLE_EXCEPTIONS = ()  # type: ignore[assignment]
_is_us_code = None  # type: ignore[assignment]
_is_hk_market = None  # type: ignore[assignment]
is_bse_code = None  # type: ignore[assignment]
call_with_timeout = None  # type: ignore[assignment]
log_safe_exception = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _HistoryMethods:
    """Source descriptors rebound onto ``PytdxFetcher``."""

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从通达信获取原始数据
        
        使用 get_security_bars() 获取日线数据
        
        流程：
        1. 检查是否为美股（不支持）
        2. 使用上下文管理器管理连接
        3. 判断市场代码
        4. 调用 API 获取 K 线数据 (bounded by request timeout)
        """
        # U.S. stocks are not supported, Throw an exception to allow DataFetcherManager Switch to another data source
        if _is_us_code(stock_code):
            raise DataFetchError(f"PytdxFetcher 不支持美股 {stock_code}，请使用 AkshareFetcher 或 YfinanceFetcher")

        # Hong Kong stocks are not supported, Raise an exception to allow DataFetcherManager Switch to another data source
        if _is_hk_market(stock_code):
            raise DataFetchError(f"PytdxFetcher 不支持港股 {stock_code}，请使用 AkshareFetcher")

        # Beijing Stock Exchange is not supported, throwing an exception to switch DataFetcherManager to other data sources
        if is_bse_code(stock_code):
            raise DataFetchError(
                f"PytdxFetcher 不支持北交所 {stock_code}，将自动切换其他数据源"
            )
        
        market, code = self._get_market_code(stock_code)
        
        # Calculate the estimated number of trading days to obtain
        from datetime import datetime as dt
        start_dt = dt.strptime(start_date, '%Y-%m-%d')
        end_dt = dt.strptime(end_date, '%Y-%m-%d')
        days = (end_dt - start_dt).days
        count = min(max(days * 5 // 7 + 10, 30), 800)  # Estimate the trading day, up to 800 entries
        
        logger.debug(f"调用 Pytdx get_security_bars(market={market}, code={code}, count={count})")

        def _query() -> pd.DataFrame:
            with self._pytdx_session() as api:
                # Get daily K-line data
                # category: 9-day line, 0-5 minutes, 1-15 minutes, 2-30 minutes, 3-1 hour
                data = api.get_security_bars(
                    category=9,  # Daily line
                    market=market,
                    code=code,
                    start=0,  # From latest.
                    count=count
                )

                if data is None or len(data) == 0:
                    raise DataFetchError(f"Pytdx 未查询到 {stock_code} 的数据")

                # Convert to DataFrame
                df = api.to_df(data)

                # Filter date range
                df['datetime'] = pd.to_datetime(df['datetime'])
                df = df[(df['datetime'] >= start_date) & (df['datetime'] <= end_date)]

                return df

        try:
            return call_with_timeout(
                _query,
                timeout=self._request_timeout_seconds,
                call_name="pytdx.get_security_bars",
            )
        except DEFAULT_RETRYABLE_EXCEPTIONS:
            # Preserve retryable exceptions for provider_retry; do not wrap.
            raise
        except DataFetchError:
            raise
        except Exception as e:  # broad-exception: fallback_recorded - Map library failures to DataFetchError for manager fallback.
            log_safe_exception(
                logger,
                "Pytdx raw data fetch failed",
                e,
                error_code="pytdx_raw_data_fetch_failed",
                level=logging.DEBUG,
            )
            raise DataFetchError(f"Pytdx 获取数据失败: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化 Pytdx 数据
        
        Pytdx 返回的列名：
        datetime, open, high, low, close, vol, amount
        
        需要映射到标准列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # Column name mapping
        column_mapping = {
            'datetime': 'date',
            'vol': 'volume',
        }
        
        df = df.rename(columns=column_mapping)
        
        # Calculate Percentage Change (pytdx does not return percentage change, need to calculate it yourself)
        if 'pct_chg' not in df.columns and 'close' in df.columns:
            df['pct_chg'] = df['close'].pct_change() * 100
            df['pct_chg'] = df['pct_chg'].fillna(0).round(2)
        
        # Add stock code column
        df['code'] = stock_code
        
        # Keep only required columns.
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df


EXPECTED_HISTORY_METHOD_NAMES: Tuple[str, ...] = (
    "_fetch_raw_data",
    "_normalize_data",
)


def bind_history_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind daily-history descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _HistoryMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_HISTORY_METHOD_NAMES,
    )


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
