# -*- coding: utf-8 -*-
"""Tushare daily/history fetch orchestration methods.

Method bodies are rebound onto ``TushareFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``data_provider.tushare_fetcher``. Tenacity retry is re-applied on the facade
after bind, only for ``_fetch_raw_data``.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import pandas as pd

from src.utils.sanitize import log_safe_exception

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``data_provider.tushare_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tushare_fetcher")
DataFetchError = Exception  # type: ignore[assignment,misc]
RateLimitError = Exception  # type: ignore[assignment,misc]
STANDARD_COLUMNS = ()  # type: ignore[assignment]
_is_us_code = None  # type: ignore[assignment]
_is_etf_code = None  # type: ignore[assignment]
_is_hk_market = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _HistoryMethods:
    """Source descriptors rebound onto ``TushareFetcher``."""

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从 Tushare 获取原始数据
        
        根据代码类型选择不同接口：
        - 普通股票：daily()
        - ETF 基金：fund_daily()
        
        流程：
        1. 检查 API 是否可用
        2. 检查是否为美股（不支持）
        3. 执行速率限制检查
        4. 转换股票代码格式
        5. 根据代码类型选择接口并调用
        """
        if self._api is None:
            raise DataFetchError("Tushare API 未初始化，请检查 Token 配置")

        # US stocks not supported
        if _is_us_code(stock_code):
            raise DataFetchError(f"TushareFetcher 不支持美股 {stock_code}，请使用 AkshareFetcher 或 YfinanceFetcher")

        # Rate-limit check
        self._check_rate_limit()

        is_hk = _is_hk_market(stock_code)
         # Determine if it's an ETF / Hong Kong stock, to select different interfaces.
        is_etf = _is_etf_code(stock_code)
        if is_hk:
            ts_code = self._convert_hk_stock_code_for_tushare(stock_code)
            api_name = "hk_daily"
        else:
            ts_code = self._convert_stock_code(stock_code)
            api_name = "fund_daily" if is_etf else "daily"

        # Convert date format (Tushare requires YYYYMMDD)
        ts_start = start_date.replace('-', '')
        ts_end = end_date.replace('-', '')



        logger.debug(f"调用 Tushare {api_name}({ts_code}, {ts_start}, {ts_end})")

        try:
            if is_hk:
                # Hong Kong stocks uses the hk_daily interface.
                df = self._api.hk_daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )
            elif is_etf:
                # ETF uses fund_daily interface
                df = self._api.fund_daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )
            else:
                # Regular A-share stocks use daily interface
                df = self._api.daily(
                    ts_code=ts_code,
                    start_date=ts_start,
                    end_date=ts_end,
                )

            return df

        except Exception as e:
            error_msg = str(e).lower()

            # Check quota limit
            if any(keyword in error_msg for keyword in ['quota', '配额', 'limit', '权限']):
                log_safe_exception(
                    logger,
                    "Tushare rate limit detected",
                    e,
                    error_code="tushare_rate_limit_detected",
                    level=logging.WARNING,
                    context={"symbol": stock_code},
                )
                raise RateLimitError(f"Tushare 配额超限: {e}") from e

            raise DataFetchError(f"Tushare 获取数据失败: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化 Tushare 数据
        
        Tushare daily / fund_daily 返回的列名：
        ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        
        需要映射到标准列名：
        date, open, high, low, close, volume, amount, pct_chg

        单位缩放仅适用于 A 股（及 ETF 等使用同一套单位的接口）：
        - vol 按「手」计，乘以 100 转为「股」
        - amount 按「千元」计，乘以 1000 转为「元」

        港股 hk_daily 返回的 vol / amount 已是可直接使用的量级，不做上述缩放。
        """
        df = df.copy()
        is_hk = _is_hk_market(stock_code)

        # Column name mapping
        column_mapping = {
            'trade_date': 'date',
            'vol': 'volume',
            # open, high, low, close, amount, pct_chg duplicate names
        }

        df = df.rename(columns=column_mapping)

        # Convert date format (YYYYMMDD -> YYYY-MM-DD)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')

        # Convert volume/trading-value units only for A-share APIs; Hong Kong hk_daily values need no conversion.
        if 'volume' in df.columns and not is_hk:
            df['volume'] = df['volume'] * 100

        if 'amount' in df.columns and not is_hk:
            df['amount'] = df['amount'] * 1000

        # Add stock code column
        df['code'] = stock_code

        # Keep only required columns.
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]

        return df


def _rebind_loaded_facade() -> None:
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
