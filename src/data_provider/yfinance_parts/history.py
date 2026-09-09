# -*- coding: utf-8 -*-
"""yfinance daily/history fetch and normalize methods.

Method bodies are rebound onto ``YfinanceFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.yfinance_fetcher``. Tenacity retry is re-applied on the
facade after bind, only for ``_fetch_raw_data``. Mirrors ``tushare_parts.history``
and the domain split of ``realtime`` / ``main_indices`` in this package.

Symbol conversion, US/JP/KR/TW classifiers, and the HTTP guard stay on the
facade; this cluster reaches them through ``self`` or facade globals at call
time. No sibling method moves.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.yfinance_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.yfinance_fetcher")
DataFetchError = Exception  # type: ignore[assignment,misc]
STANDARD_COLUMNS = ()  # type: ignore[assignment]
_yfinance_http_guard = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _HistoryMethods:
    """Source descriptors rebound onto ``YfinanceFetcher``."""

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从 Yahoo Finance 获取原始数据

        使用 yfinance.download() 获取历史数据

        流程：
        1. 转换股票代码格式
        2. 调用 yfinance API
        3. 处理返回数据
        """
        # Convert Code Format
        yf_code = self._convert_stock_code(stock_code)

        logger.debug(f"调用 yfinance.download({yf_code}, {start_date}, {end_date})")

        try:
            with _yfinance_http_guard():
                import yfinance as yf

                # Use yfinance to download data
                df = yf.download(
                    tickers=yf_code,
                    start=start_date,
                    end=end_date,
                    progress=False,  # Disable progress bar
                    auto_adjust=True,  # Automatically adjust prices for splits and dividends.
                    multi_level_index=True
                )

                # Filter yf_code columns, avoid confusion of data for multiple stocks
                if isinstance(df.columns, pd.MultiIndex) and len(df.columns) > 1:
                    ticker_level = df.columns.get_level_values(1)
                    mask = ticker_level == yf_code
                    if mask.any():
                        df = df.loc[:, mask].copy()

                if df.empty:
                    raise DataFetchError(f"Yahoo Finance 未查询到 {stock_code} 的数据")

                return df

        except Exception as e:  # broad-exception: fallback_recorded - Map provider I/O failure to DataFetchError for manager fallback.
            if isinstance(e, DataFetchError):
                raise
            log_safe_exception(
                logger,
                "Yfinance daily HTTP request failed",
                e,
                error_code="yfinance_daily_http_failed",
                level=logging.DEBUG,
                context={"symbol": stock_code},
            )
            raise DataFetchError(f"Yahoo Finance 获取数据失败: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化 Yahoo Finance 数据

        yfinance 返回的列名：
        Open, High, Low, Close, Volume（索引是日期）

        注意：新版 yfinance 返回 MultiIndex 列名，如 ('Close', 'AMD')
        需要先扁平化列名再进行处理

        需要映射到标准列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()

        # Handle MultiIndex column names (new yfinance format)
        # For example: ('Close', 'AMD') -> 'Close'
        if isinstance(df.columns, pd.MultiIndex):
            logger.debug("检测到 MultiIndex 列名，进行扁平化处理")
            # Get first-level column names (Price level: Close, High, Low, etc.)
            df.columns = df.columns.get_level_values(0)

        # Reset index, change date from index to column
        df = df.reset_index()

        # Column name mapping (yfinance uses Title Case)
        column_mapping = {
            'Date': 'date',
            'Datetime': 'date',
            'datetime': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
        }

        df = df.rename(columns=column_mapping)
        if 'date' not in df.columns:
            index_col = df.columns[0] if len(df.columns) else None
            if index_col is not None:
                candidate = df[index_col]
                if pd.api.types.is_datetime64_any_dtype(candidate):
                    df = df.rename(columns={index_col: 'date'})
                elif not pd.api.types.is_numeric_dtype(candidate):
                    parsed_dates = pd.to_datetime(candidate, errors='coerce')
                    if parsed_dates.notna().any():
                        df = df.rename(columns={index_col: 'date'})
                        df['date'] = parsed_dates

        # Calculate Percentage Change (because yfinance does not directly provide)
        if 'close' in df.columns:
            df['pct_chg'] = df['close'].pct_change() * 100
            df['pct_chg'] = df['pct_chg'].fillna(0).round(2)

        # Estimate trading value because yfinance does not provide it directly.
        # Trading value is approximately volume times average price.
        if 'volume' in df.columns and 'close' in df.columns:
            df['amount'] = df['volume'] * df['close']
        else:
            df['amount'] = 0

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
