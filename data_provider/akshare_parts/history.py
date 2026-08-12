# -*- coding: utf-8 -*-
"""AkShare daily/history fetch orchestration methods.

Method bodies are rebound onto ``AkshareFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``data_provider.akshare_fetcher``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

import logging
import random
import time
from datetime import datetime

import pandas as pd

from src.utils.sanitize import log_safe_exception

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``data_provider.akshare_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("data_provider.akshare_fetcher")
USER_AGENTS = []  # type: ignore[assignment]
DataFetchError = Exception  # type: ignore[assignment,misc]
RateLimitError = Exception  # type: ignore[assignment,misc]
STANDARD_COLUMNS = ()  # type: ignore[assignment]
_is_us_code = None  # type: ignore[assignment]
_is_hk_code = None  # type: ignore[assignment]
_is_etf_code = None  # type: ignore[assignment]
_to_sina_tx_symbol = None  # type: ignore[assignment]
_akshare_call_with_timeout = None  # type: ignore[assignment]
is_bse_code = None  # type: ignore[assignment]
normalize_stock_code = None  # type: ignore[assignment]
retry = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _HistoryMethods:
    """Source descriptors rebound onto ``AkshareFetcher``."""

    def _set_random_user_agent(self) -> None:
        """
        设置随机 User-Agent
        
        通过修改 requests Session 的 headers 实现
        这是关键的反爬策略之一
        """
        try:
            import akshare as ak
            # akshare uses requests internally; we influence it through environment variables or direct setting
            # akshare may not directly expose the session, here fake_useragent is used as a supplement
            random_ua = random.choice(USER_AGENTS)
            logger.debug(f"设置 User-Agent: {random_ua[:50]}...")
        except Exception as e:
            log_safe_exception(
                logger,
                "Akshare user agent selection failed",
                e,
                error_code="akshare_user_agent_selection_failed",
                level=logging.DEBUG,
            )

    def _enforce_rate_limit(self) -> None:
        """
        强制执行速率限制
        
        策略：
        1. 检查距离上次请求的时间间隔
        2. 如果间隔不足，补充休眠时间
        3. 然后再执行随机 jitter 休眠
        """
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            min_interval = self.sleep_min
            if elapsed < min_interval:
                additional_sleep = min_interval - elapsed
                logger.debug(f"补充休眠 {additional_sleep:.2f} 秒")
                time.sleep(additional_sleep)
        
        # Apply a random jitter delay
        self.random_sleep(self.sleep_min, self.sleep_max)
        self._last_request_time = time.time()

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从 Akshare 获取原始数据
        
        根据代码类型自动选择 API：
        - 美股：不支持，抛出异常由 YfinanceFetcher 处理（Issue #311）
        - 港股：使用 ak.stock_hk_hist()
        - ETF 基金：使用 ak.fund_etf_hist_em()
        - 普通 A 股：使用 ak.stock_zh_a_hist()
        
        流程：
        1. 判断代码类型（美股/港股/ETF/A股）
        2. 设置随机 User-Agent
        3. 执行速率限制（随机休眠）
        4. 调用对应的 akshare API
        5. 处理返回数据
        """
        # Choose different retrieval methods based on code type:
        if _is_us_code(stock_code):
            # U.S. stocks: price adjustment in AkShare's stock_us_daily API has known issues (see Issue #311).
            # Handled by YfinanceFetcher to ensure consistent adjusted prices
            raise DataFetchError(
                f"AkshareFetcher 不支持美股 {stock_code}，请使用 YfinanceFetcher 获取正确的复权价格"
            )
        elif _is_hk_code(stock_code):
            return self._fetch_hk_data(stock_code, start_date, end_date)
        elif _is_etf_code(stock_code):
            return self._fetch_etf_data(stock_code, start_date, end_date)
        else:
            return self._fetch_stock_data(stock_code, start_date, end_date)

    def _fetch_stock_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取普通 A 股历史数据

        策略：
        1. 优先尝试东方财富接口 (ak.stock_zh_a_hist)
        2. 失败后尝试新浪财经接口 (ak.stock_zh_a_daily)
        3. 最后尝试腾讯财经接口 (ak.stock_zh_a_hist_tx)
        """
        # Try each source in order
        methods = [
            (self._fetch_stock_data_em, "东方财富"),
            (self._fetch_stock_data_sina, "新浪财经"),
            (self._fetch_stock_data_tx, "腾讯财经"),
        ]

        last_error = None

        for fetch_method, source_name in methods:
            try:
                logger.info(f"[数据源] 尝试使用 {source_name} 获取 {stock_code}...")
                df = fetch_method(stock_code, start_date, end_date)

                if df is not None and not df.empty:
                    logger.info(f"[数据源] {source_name} 获取成功")
                    return df
            except Exception as e:
                last_error = e
                log_safe_exception(
                    logger,
                    "Akshare historical data source failed",
                    e,
                    error_code="akshare_history_source_failed",
                    level=logging.WARNING,
                    context={"symbol": stock_code, "source": source_name},
                )
                # Try the next one

        # All failed
        raise DataFetchError(f"Akshare 所有渠道获取失败: {last_error}")

    def _fetch_stock_data_em(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取普通 A 股历史数据 (东方财富)
        数据来源：ak.stock_zh_a_hist()
        """
        import akshare as ak

        # Anti-ban strategy 1: Random User-Agent
        self._set_random_user_agent()

        # Anti-ban strategy 2: Forced sleep
        self._enforce_rate_limit()

        logger.info(f"[API调用] ak.stock_zh_a_hist(symbol={stock_code}, ...)")

        try:
            import time as _time
            api_start = _time.time()

            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )

            api_elapsed = _time.time() - api_start

            if df is not None and not df.empty:
                logger.info(f"[API返回] ak.stock_zh_a_hist 成功: {len(df)} 行, 耗时 {api_elapsed:.2f}s")
                return df
            else:
                logger.warning(f"[API返回] ak.stock_zh_a_hist 返回空数据")
                return pd.DataFrame()

        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '频率', 'rate', '限制']):
                raise RateLimitError(f"Akshare(EM) 可能被限流: {e}") from e
            raise e

    def _fetch_stock_data_sina(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取普通 A 股历史数据 (新浪财经)
        数据来源：ak.stock_zh_a_daily()
        """
        import akshare as ak

        # Convert Code Format: sh600000, sz000001, bj920748
        symbol = _to_sina_tx_symbol(stock_code)

        self._enforce_rate_limit()

        try:
            df = _akshare_call_with_timeout(
                ak.stock_zh_a_daily,
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq",
                timeout=self._history_call_timeout,
                call_name="ak.stock_zh_a_daily",
            )

            # Standardized Sina data column names
            # Sina returns: date, open, high, low, close, volume, amount, outstanding_share, turnover
            if df is not None and not df.empty:
                # Ensure the date column exists
                if 'date' in df.columns:
                    df = df.rename(columns={'date': '日期'})

                # Map other columns to match the expected format of _normalize_data
                # Expected data: Date, Open, Close, High, Low, Volume, Turnover,
                rename_map = {
                    'open': '开盘', 'high': '最高', 'low': '最低',
                    'close': '收盘', 'volume': '成交量', 'amount': '成交额'
                }
                df = df.rename(columns=rename_map)

                # Calculate Percentage Change (Sina interface may not return)
                if '收盘' in df.columns:
                    df['涨跌幅'] = df['收盘'].pct_change() * 100
                    df['涨跌幅'] = df['涨跌幅'].fillna(0)

                return df
            return pd.DataFrame()

        except Exception as e:
            raise e

    def _fetch_stock_data_tx(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取普通 A 股历史数据 (腾讯财经)
        数据来源：ak.stock_zh_a_hist_tx()
        """
        import akshare as ak

        # Convert Code Format: sh600000, sz000001, bj920748
        symbol = _to_sina_tx_symbol(stock_code)

        self._enforce_rate_limit()

        try:
            df = _akshare_call_with_timeout(
                ak.stock_zh_a_hist_tx,
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq",
                timeout=self._history_call_timeout,
                call_name="ak.stock_zh_a_hist_tx",
            )

            # Standardized Tencent data column names
            # Tencent returns: date, open, close, high, low, volume, amount
            if df is not None and not df.empty:
                rename_map = {
                    'date': '日期', 'open': '开盘', 'high': '最高',
                    'low': '最低', 'close': '收盘', 'volume': '成交量',
                    'amount': '成交额'
                }
                df = df.rename(columns=rename_map)

                # Tencent data typically includes '涨跌幅', and calculates if it is missing.
                if 'pct_chg' in df.columns:
                    df = df.rename(columns={'pct_chg': '涨跌幅'})
                elif '收盘' in df.columns:
                    df['涨跌幅'] = df['收盘'].pct_change() * 100
                    df['涨跌幅'] = df['涨跌幅'].fillna(0)

                return df
            return pd.DataFrame()

        except Exception as e:
            raise e

    def _fetch_etf_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取 ETF 基金历史数据
        
        数据来源：ak.fund_etf_hist_em()
        
        Args:
            stock_code: ETF 代码，如 '512400', '159883'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            ETF 历史数据 DataFrame
        """
        import akshare as ak
        
        # Anti-ban strategy 1: Random User-Agent
        self._set_random_user_agent()
        
        # Anti-ban strategy 2: Forced sleep
        self._enforce_rate_limit()
        
        logger.info(f"[API调用] ak.fund_etf_hist_em(symbol={stock_code}, period=daily, "
                   f"start_date={start_date.replace('-', '')}, end_date={end_date.replace('-', '')}, adjust=qfq)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # Call akshare to get ETF daily data
            df = ak.fund_etf_hist_em(
                symbol=stock_code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"  # forward-adjusted.
            )
            
            api_elapsed = _time.time() - api_start
            
            # Record the data summary
            if df is not None and not df.empty:
                logger.info(f"[API返回] ak.fund_etf_hist_em 成功: 返回 {len(df)} 行数据, 耗时 {api_elapsed:.2f}s")
                logger.info(f"[API返回] 列名: {list(df.columns)}")
                logger.info(f"[API返回] 日期范围: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API返回] 最新3条数据:\n{df.tail(3).to_string()}")
            else:
                logger.warning(f"[API返回] ak.fund_etf_hist_em 返回空数据, 耗时 {api_elapsed:.2f}s")
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Detect anti-crawler ban
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '频率', 'rate', '限制']):
                log_safe_exception(
                    logger,
                    "Akshare rate limit detected",
                    e,
                    error_code="akshare_rate_limit_detected",
                    level=logging.WARNING,
                    context={"symbol": stock_code, "instrument_type": "etf"},
                )
                raise RateLimitError(f"Akshare 可能被限流: {e}") from e
            
            raise DataFetchError(f"Akshare 获取 ETF 数据失败: {e}") from e

    def _fetch_us_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取美股历史数据
        
        数据来源：ak.stock_us_daily()（新浪财经接口）
        
        Args:
            stock_code: 美股代码，如 'AMD', 'AAPL', 'TSLA'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            美股历史数据 DataFrame
        """
        import akshare as ak
        
        # Anti-ban strategy 1: Random User-Agent
        self._set_random_user_agent()
        
        # Anti-ban strategy 2: Forced sleep
        self._enforce_rate_limit()
        
        # U.S. stocks use all uppercase codes directly
        symbol = stock_code.strip().upper()
        
        logger.info(f"[API调用] ak.stock_us_daily(symbol={symbol}, adjust=qfq)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # Call akshare to get U.S. stocks daily data
            # stock_us_daily returns all historical data, subsequent filtering by date is required
            df = ak.stock_us_daily(
                symbol=symbol,
                adjust="qfq"  # forward-adjusted.
            )
            
            api_elapsed = _time.time() - api_start
            
            # Record the data summary
            if df is not None and not df.empty:
                logger.info(f"[API返回] ak.stock_us_daily 成功: 返回 {len(df)} 行数据, 耗时 {api_elapsed:.2f}s")
                logger.info(f"[API返回] 列名: {list(df.columns)}")
                
                # Filter by date.
                df['date'] = pd.to_datetime(df['date'])
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
                
                if not df.empty:
                    logger.info(f"[API返回] 过滤后日期范围: {df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')}")
                    logger.debug(f"[API返回] 最新3条数据:\n{df.tail(3).to_string()}")
                else:
                    logger.warning(f"[API返回] 过滤后数据为空，日期范围 {start_date} ~ {end_date} 无数据")
                
                # Convert columns named in Chinese format to match _normalize_data
                # stock_us_daily Return: date, open, high, low, close, volume
                rename_map = {
                    'date': '日期',
                    'open': '开盘',
                    'high': '最高',
                    'low': '最低',
                    'close': '收盘',
                    'volume': '成交量',
                }
                df = df.rename(columns=rename_map)
                
                # Calculate percentage change (U.S. stocks API does not directly return)
                if '收盘' in df.columns:
                    df['涨跌幅'] = df['收盘'].pct_change() * 100
                    df['涨跌幅'] = df['涨跌幅'].fillna(0)
                
                # Estimate the trading value (U.S. stocks interface does not return)
                if '成交量' in df.columns and '收盘' in df.columns:
                    df['成交额'] = df['成交量'] * df['收盘']
                else:
                    df['成交额'] = 0
                
                return df
            else:
                logger.warning(f"[API返回] ak.stock_us_daily 返回空数据, 耗时 {api_elapsed:.2f}s")
                return pd.DataFrame()
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Detect anti-crawler ban
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '频率', 'rate', '限制']):
                log_safe_exception(
                    logger,
                    "Akshare rate limit detected",
                    e,
                    error_code="akshare_rate_limit_detected",
                    level=logging.WARNING,
                    context={"symbol": stock_code, "market": "us"},
                )
                raise RateLimitError(f"Akshare 可能被限流: {e}") from e
            
            raise DataFetchError(f"Akshare 获取美股数据失败: {e}") from e

    def _fetch_hk_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取港股历史数据
        
        数据来源：ak.stock_hk_hist()
        
        Args:
            stock_code: 港股代码，如 '00700', '01810'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            港股历史数据 DataFrame
        """
        import akshare as ak
        
        # Anti-ban strategy 1: Random User-Agent
        self._set_random_user_agent()
        
        # Anti-ban strategy 2: Forced sleep
        self._enforce_rate_limit()
        
        # Ensure code formatting is correct (5-digit number)
        code = stock_code.lower().replace('hk', '').zfill(5)
        
        logger.info(f"[API调用] ak.stock_hk_hist(symbol={code}, period=daily, "
                   f"start_date={start_date.replace('-', '')}, end_date={end_date.replace('-', '')}, adjust=qfq)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # Call akshare to get Hong Kong stocks daily data
            df = ak.stock_hk_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"  # forward-adjusted.
            )
            
            api_elapsed = _time.time() - api_start
            
            # Record the data summary
            if df is not None and not df.empty:
                logger.info(f"[API返回] ak.stock_hk_hist 成功: 返回 {len(df)} 行数据, 耗时 {api_elapsed:.2f}s")
                logger.info(f"[API返回] 列名: {list(df.columns)}")
                logger.info(f"[API返回] 日期范围: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API返回] 最新3条数据:\n{df.tail(3).to_string()}")
            else:
                logger.warning(f"[API返回] ak.stock_hk_hist 返回空数据, 耗时 {api_elapsed:.2f}s")
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Detect anti-crawler ban
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '频率', 'rate', '限制']):
                log_safe_exception(
                    logger,
                    "Akshare rate limit detected",
                    e,
                    error_code="akshare_rate_limit_detected",
                    level=logging.WARNING,
                    context={"symbol": stock_code, "market": "hk"},
                )
                raise RateLimitError(f"Akshare 可能被限流: {e}") from e
            
            raise DataFetchError(f"Akshare 获取港股数据失败: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化 Akshare 数据
        
        Akshare 返回的列名（中文）：
        日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
        
        需要映射到标准列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # Column name mapping (Akshare Chinese column names -> standard English column names)
        column_mapping = {
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
            '涨跌幅': 'pct_chg',
        }
        
        # Rename column.
        df = df.rename(columns=column_mapping)
        
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
