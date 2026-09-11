# -*- coding: utf-8 -*-
"""efinance stock-path daily fetch and normalize methods.

Method bodies are rebound onto ``EfinanceFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.efinance_fetcher``. Tenacity retry is re-applied on the
facade after bind, only for ``_fetch_raw_data``.

UA/rate-limit helpers and ``_build_history_failure_message`` stay on the
facade; rebound bodies reach them through ``self`` or facade globals. ETF
history remains in ``efinance_parts.etf``; this cluster only owns the stock
path plus the daily orchestrator that dispatches to ETF vs stock.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.efinance_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.efinance_fetcher")
DataFetchError = Exception  # type: ignore[assignment,misc]
RateLimitError = Exception  # type: ignore[assignment,misc]
EASTMONEY_HISTORY_ENDPOINT = ""  # type: ignore[assignment]
STANDARD_COLUMNS = ()  # type: ignore[assignment]
_is_us_code = None  # type: ignore[assignment]
_is_hk_market = None  # type: ignore[assignment]
_is_etf_code = None  # type: ignore[assignment]
_ef_call_with_timeout = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _HistoryMethods:
    """Source descriptors rebound onto ``EfinanceFetcher``."""

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从 efinance 获取原始数据

        根据代码类型自动选择 API：
        - 美股：不支持，抛出异常让 DataFetcherManager 切换到其他数据源
        - 普通股票：使用 ef.stock.get_quote_history()
        - ETF 基金：使用 ef.stock.get_quote_history()（ETF 是交易所证券，使用股票 K 线接口）

        流程：
        1. 判断代码类型（美股/股票/ETF）
        2. 设置随机 User-Agent
        3. 执行速率限制（随机休眠）
        4. 调用对应的 efinance API
        5. 处理返回数据
        """
        # U.S. Stocks are not supported, throwing an exception to switch DataFetcherManager to AkshareFetcher/YfinanceFetcher
        if _is_us_code(stock_code):
            raise DataFetchError(f"EfinanceFetcher 不支持美股 {stock_code}，请使用 AkshareFetcher 或 YfinanceFetcher")

        # The historical K-line interface for efinance may return unexpected market data on Hong Kong stock codes.
        # Explicitly skip and pass to AkShare/Tushare/YFinance/Longbridge etc. Hong Kong stock paths as fallback.
        if _is_hk_market(stock_code):
            raise DataFetchError(f"EfinanceFetcher 不支持港股日线 {stock_code}，请使用 AkshareFetcher 或其他港股数据源")

        # Choose different retrieval methods based on code type:
        if _is_etf_code(stock_code):
            return self._fetch_etf_data(stock_code, start_date, end_date)
        else:
            return self._fetch_stock_data(stock_code, start_date, end_date)

    def _fetch_stock_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取普通 A 股历史数据

        数据来源：ef.stock.get_quote_history()

        API 参数说明：
        - stock_codes: 股票代码
        - beg: 开始日期，格式 'YYYYMMDD'
        - end: 结束日期，格式 'YYYYMMDD'
        - klt: 周期，101=日线
        - fqt: 复权方式，1=前复权
        """
        import efinance as ef

        # Anti-ban strategy 1: Random User-Agent
        self._set_random_user_agent()

        # Anti-ban strategy 2: Forced sleep
        self._enforce_rate_limit()

        # Format date (efinance uses YYYYMMDD format)
        beg_date = start_date.replace('-', '')
        end_date_fmt = end_date.replace('-', '')

        logger.info(f"[API调用] ef.stock.get_quote_history(stock_codes={stock_code}, "
                   f"beg={beg_date}, end={end_date_fmt}, klt=101, fqt=1)")

        api_start = time.time()
        try:
            # Call efinance to get A-shares daily data
            # klt=101 get daily line data
            # fqt=1 get forward-adjusted
            df = _ef_call_with_timeout(
                ef.stock.get_quote_history,
                stock_codes=stock_code,
                beg=beg_date,
                end=end_date_fmt,
                klt=101,  # Daily line
                fqt=1,    # forward-adjusted.
                timeout=60,
            )

            api_elapsed = time.time() - api_start

            # Record the data summary
            if df is not None and not df.empty:
                logger.info(
                    "[API返回] Eastmoney 历史K线成功: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
                    f"range={beg_date}~{end_date_fmt}, rows={len(df)}, elapsed={api_elapsed:.2f}s"
                )
                logger.info(f"[API返回] 列名: {list(df.columns)}")
                if '日期' in df.columns:
                    logger.info(f"[API返回] 日期范围: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API返回] 最新3条数据:\n{df.tail(3).to_string()}")
            else:
                logger.warning(
                    "[API返回] Eastmoney 历史K线为空: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
                    f"range={beg_date}~{end_date_fmt}, elapsed={api_elapsed:.2f}s"
                )

            return df

        except Exception as e:
            api_elapsed = time.time() - api_start
            category, failure_message = self._build_history_failure_message(
                stock_code=stock_code,
                beg_date=beg_date,
                end_date=end_date_fmt,
                exc=e,
                elapsed=api_elapsed,
            )

            if category == "rate_limit_or_anti_bot":
                log_safe_exception(
                    logger,
                    "Efinance rate limit detected",
                    e,
                    error_code="efinance_rate_limit_detected",
                    level=logging.WARNING,
                    context={
                        "symbol": stock_code,
                        "endpoint": EASTMONEY_HISTORY_ENDPOINT,
                        "category": category,
                    },
                )
                raise RateLimitError(f"efinance 可能被限流: {failure_message}") from e

            log_safe_exception(
                logger,
                "Efinance historical data fetch failed",
                e,
                error_code="efinance_history_fetch_failed",
                level=logging.ERROR,
                context={
                    "symbol": stock_code,
                    "endpoint": EASTMONEY_HISTORY_ENDPOINT,
                    "category": category,
                },
            )
            raise DataFetchError(f"efinance 获取数据失败: {failure_message}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化 efinance 数据

        efinance 返回的列名（中文）：
        股票名称, 股票代码, 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率

        需要映射到标准列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()

        # Column mapping (efinance Chinese column names -> standard English column names)
        column_mapping = {
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
            '涨跌幅': 'pct_chg',
            '股票代码': 'code',
            '股票名称': 'name',
        }

        # Rename column.
        df = df.rename(columns=column_mapping)

        # Fallback: if OHLC columns are missing (e.g. very old data path), fill from close
        if 'close' in df.columns and 'open' not in df.columns:
            df['open'] = df['close']
            df['high'] = df['close']
            df['low'] = df['close']

        # Fill volume and amount if missing
        if 'volume' not in df.columns:
            df['volume'] = 0
        if 'amount' not in df.columns:
            df['amount'] = 0

        # If there is no 'code' column, manually add it
        if 'code' not in df.columns:
            df['code'] = stock_code

        # Keep only required columns.
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]

        return df


EXPECTED_HISTORY_METHOD_NAMES: Tuple[str, ...] = (
    "_fetch_raw_data",
    "_fetch_stock_data",
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
