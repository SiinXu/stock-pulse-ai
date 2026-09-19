# -*- coding: utf-8 -*-
"""Baostock daily history methods: raw fetch and normalize.

Method bodies are rebound onto ``BaostockFetcher`` by the compatibility
facade (ADR-006) so free-name lookups and test patches stay on
``src.data_provider.baostock_fetcher``. Tenacity ``provider_retry`` is
re-applied on the facade after bind, only for ``_fetch_raw_data``.

Connection ownership stays on the facade. ``_get_baostock``,
``_baostock_session``, and ``_convert_stock_code`` are reached through
``self`` at call time.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.baostock_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.baostock_fetcher")
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
    """Source descriptors rebound onto ``BaostockFetcher``."""

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从 Baostock 获取原始数据
        
        使用 query_history_k_data_plus() 获取日线数据
        
        流程：
        1. 检查是否为美股（不支持）
        2. 使用上下文管理器管理连接
        3. 转换股票代码格式
        4. 调用 API 查询数据 (bounded by request timeout)
        5. 将结果转换为 DataFrame
        """
        # U.S. stocks are not supported, Throw an exception to allow DataFetcherManager Switch to another data source
        if _is_us_code(stock_code):
            raise DataFetchError(f"BaostockFetcher 不支持美股 {stock_code}，请使用 AkshareFetcher 或 YfinanceFetcher")

        # Hong Kong stocks are not supported, Raise an exception to allow DataFetcherManager Switch to another data source
        if _is_hk_market(stock_code):
            raise DataFetchError(f"BaostockFetcher 不支持港股 {stock_code}，请使用 AkshareFetcher")

        # Beijing Stock Exchange is not supported, throwing an exception to switch DataFetcherManager to other data sources
        if is_bse_code(stock_code):
            raise DataFetchError(
                f"BaostockFetcher 不支持北交所 {stock_code}，将自动切换其他数据源"
            )
        
        # Convert Code Format
        bs_code = self._convert_stock_code(stock_code)
        
        logger.debug(f"调用 Baostock query_history_k_data_plus({bs_code}, {start_date}, {end_date})")

        def _query() -> pd.DataFrame:
            with self._baostock_session() as bs:
                # Query daily data
                # adjustflag: 1-backward-adjusted, 2-forward-adjusted, 3-unadjusted
                rs = bs.query_history_k_data_plus(
                    code=bs_code,
                    fields="date,open,high,low,close,volume,amount,pctChg",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",  # Daily line
                    adjustflag="2"  # forward-adjusted.
                )

                if rs.error_code != '0':
                    raise DataFetchError(f"Baostock 查询失败: {rs.error_msg}")

                # Convert to DataFrame
                data_list = []
                while rs.next():
                    data_list.append(rs.get_row_data())

                if not data_list:
                    raise DataFetchError(f"Baostock 未查询到 {stock_code} 的数据")

                return pd.DataFrame(data_list, columns=rs.fields)

        try:
            return call_with_timeout(
                _query,
                timeout=self._request_timeout_seconds,
                call_name="baostock.query_history_k_data_plus",
            )
        except DEFAULT_RETRYABLE_EXCEPTIONS:
            # Preserve retryable exceptions for provider_retry; do not wrap.
            raise
        except DataFetchError:
            raise
        except Exception as e:  # broad-exception: fallback_recorded - Map library failures to DataFetchError for manager fallback.
            log_safe_exception(
                logger,
                "Baostock raw data fetch failed",
                e,
                error_code="baostock_raw_data_fetch_failed",
                level=logging.DEBUG,
            )
            raise DataFetchError(f"Baostock 获取数据失败: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化 Baostock 数据
        
        Baostock 返回的列名：
        date, open, high, low, close, volume, amount, pctChg
        
        需要映射到标准列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # Column name mapping (only process pctChg)
        column_mapping = {
            'pctChg': 'pct_chg',
        }
        
        df = df.rename(columns=column_mapping)
        
        # Numeric type conversion (Baostock returns are all strings)
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
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
