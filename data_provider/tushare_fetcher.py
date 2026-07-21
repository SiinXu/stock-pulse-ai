# -*- coding: utf-8 -*-
"""
===================================
TushareFetcher - Backup Data Source 1 (Priority 2)
===================================

Data source: Tushare Pro API
Features: Requires Token, has request quota limits
Advantages: High data quality, stable interface

Rate limiting strategy:
1. Implement "minute call counter"
2. Force sleep to the next minute when exceeding free quota (80 requests/min)
3. Use tenacity to implement exponential backoff retries
"""

import json as _json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

import pandas as pd
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .base import BaseFetcher, DataFetchError, RateLimitError, STANDARD_COLUMNS,is_bse_code, is_st_stock, is_kc_cy_stock, normalize_stock_code, _is_hk_market
from .realtime_types import UnifiedRealtimeQuote, ChipDistribution
from src.config import get_config
from src.utils.sanitize import log_safe_exception, safe_before_sleep_log
import os
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


# ETF code prefixes by exchange
# Shanghai: 51xxxx, 52xxxx, 56xxxx, 58xxxx
# Shenzhen: 15xxxx, 16xxxx, 18xxxx
_ETF_SH_PREFIXES = ('51', '52', '56', '58')
_ETF_SZ_PREFIXES = ('15', '16', '18')
_ETF_ALL_PREFIXES = _ETF_SH_PREFIXES + _ETF_SZ_PREFIXES


def _is_etf_code(stock_code: str) -> bool:
    """
    Check if the code is an ETF fund code.

    ETF code ranges:
    - Shanghai ETF: 51xxxx, 52xxxx, 56xxxx, 58xxxx
    - Shenzhen ETF: 15xxxx, 16xxxx, 18xxxx
    """
    code = normalize_stock_code(stock_code)
    return code.startswith(_ETF_ALL_PREFIXES) and len(code) == 6


def _is_us_code(stock_code: str) -> bool:
    """
    Determine if the code is a U.S. stock.
    
    U.S. stock code rules:
    - 1-5 uppercase letters, such as 'AAPL', 'TSLA'
    - May contain '.', such as 'BRK.B'.
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


class _TushareHttpClient:
    """Lightweight Tushare Pro client that does not require the tushare SDK."""

    def __init__(self, token: str, timeout: int = 30, api_url: str = "http://api.tushare.pro") -> None:
        self._token = token
        self._timeout = timeout
        self._api_url = api_url

    def query(self, api_name: str, fields: str = "", **kwargs) -> pd.DataFrame:
        req_params = {
            "api_name": api_name,
            "token": self._token,
            "params": kwargs,
            "fields": fields,
        }
        res = requests.post(self._api_url, json=req_params, timeout=self._timeout)
        if res.status_code != 200:
            raise Exception(f"Tushare API HTTP {res.status_code}")

        result = _json.loads(res.text)
        if result.get("code") != 0:
            raise Exception(result.get("msg") or f"Tushare API error code {result.get('code')}")

        data = result.get("data") or {}
        columns = data.get("fields") or []
        items = data.get("items") or []
        return pd.DataFrame(items, columns=columns)

    def __getattr__(self, api_name: str):
        if api_name.startswith("_"):
            raise AttributeError(api_name)

        def caller(**kwargs) -> pd.DataFrame:
            return self.query(api_name, **kwargs)

        return caller


class TushareFetcher(BaseFetcher):
    """
    Tushare Pro data source implementation
    
    Priority: 2
    Data source: Tushare Pro API
    
    Key strategy:
    - Call counter per minute to prevent exceeding quota
    - Force wait when exceeding 80 requests/minute
    - retries with exponential backoff after failures
    
    Quota explanation (Tushare free users):
    - Maximum 80 requests per minute
    - Maximum 500 requests per day
    """
    
    name = "TushareFetcher"
    priority = int(os.getenv("TUSHARE_PRIORITY", "2"))  # Default priority, dynamically adjusted in __init__ based on configuration

    def __init__(self, rate_limit_per_minute: int = 80):
        """
        Initialize TushareFetcher

        Args:
            rate_limit_per_minute: maximum requests per minute (default 80, Tushare free quota)
        """
        self.rate_limit_per_minute = rate_limit_per_minute
        self._call_count = 0  # Calls per minute within the current minute
        self._minute_start: Optional[float] = None  # Current counting cycle start time
        self._api: Optional[object] = None  # Tushare API instance
        self.date_list: Optional[List[str]] = None  # Trading day list cache (reverse order, latest date first)
        self._date_list_end: Optional[str] = None  # Cache the corresponding expiration date for cross-day refresh

        # Attempt to initialize API
        self._init_api()

        # Dynamically adjust priority based on API initialization results
        self.priority = self._determine_priority()
    
    def _init_api(self) -> None:
        """
        Initialize Tushare API

        If Token is not configured, this data source will be unavailable.
        This directly uses the built-in HTTP client, avoiding runtime dependency on the tushare SDK.
        Reduce initialization failures due to missing packages in Docker/PyInstaller/multi-virtual environment scenarios.
        """
        config = get_config()

        if not config.tushare_token:
            logger.warning("Tushare Token 未配置，此数据源不可用")
            return

        try:
            self._api = self._build_api_client(config.tushare_token)
            logger.info("Tushare API 初始化成功")
        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare API initialization failed",
                e,
                error_code="tushare_api_initialization_failed",
                level=logging.ERROR,
            )
            self._api = None

    def _build_api_client(self, token: str) -> _TushareHttpClient:
        """
        Build a lightweight Tushare Pro client over direct HTTP requests.

        The project already normalizes all Pro calls through the same request
        contract, so we do not need the official tushare SDK during runtime.
        """
        client = _TushareHttpClient(token=token)
        logger.debug("Tushare API client configured for direct HTTP calls")
        return client

    def _determine_priority(self) -> int:
        """
        Determine priority based on token configuration and API initialization status

        Strategy:
        - Token is configured and API initialization succeeds: Priority -1 (absolute highest, better than efinance)
        - Other cases: Priority 2 (default).

        Returns:
            Priority numbers (0=highest, larger numbers have lower priority).
        """
        config = get_config()

        if config.tushare_token and self._api is not None:
            # Token is configured and API initialization succeeds, raises to highest priority
            logger.info("✅ 检测到 TUSHARE_TOKEN 且 API 初始化成功，Tushare 数据源优先级提升为最高 (Priority -1)")
            return -1

        # Token is not configured or API initialization fails, maintains default priority
        return 2

    def is_available(self) -> bool:
        """
        Check if the data source is available

        Returns:
            True indicates availability, False indicates unavailability
        """
        return self._api is not None

    def _check_rate_limit(self) -> None:
        """
        Check and enforce rate limits
        
        Rate limiting strategy:
        1. Check if it's entering a new minute.
        2. If so, reset the counter
        3. If the number of calls to the current minute exceeds the limit, forcibly sleep.
        """
        current_time = time.time()
        
        # Check if the counter needs to be reset (new minute)
        if self._minute_start is None:
            self._minute_start = current_time
            self._call_count = 0
        elif current_time - self._minute_start >= 60:
            # It has been more than a minute, reset the counter
            self._minute_start = current_time
            self._call_count = 0
            logger.debug("速率限制计数器已重置")
        
        # Check if quota limit has been exceeded.
        if self._call_count >= self.rate_limit_per_minute:
            # Calculate the waiting time (to the next minute)
            elapsed = current_time - self._minute_start
            sleep_time = max(0, 60 - elapsed) + 1  # +1 second buffer
            
            logger.warning(
                f"Tushare 达到速率限制 ({self._call_count}/{self.rate_limit_per_minute} 次/分钟)，"
                f"等待 {sleep_time:.1f} 秒..."
            )
            
            time.sleep(sleep_time)
            
            # Reset counter
            self._minute_start = time.time()
            self._call_count = 0
        
        # Increase call count
        self._call_count += 1
        logger.debug(f"Tushare 当前分钟调用次数: {self._call_count}/{self.rate_limit_per_minute}")

    def _call_api_with_rate_limit(self, method_name: str, **kwargs) -> pd.DataFrame:
        """Wrap Tushare API calls with rate limiting consistently."""
        if self._api is None:
            raise DataFetchError("Tushare API 未初始化，请检查 Token 配置")

        self._check_rate_limit()
        method = getattr(self._api, method_name)
        return method(**kwargs)

    def _get_china_now(self) -> datetime:
        """Returns the current time in Shanghai timezone, convenient for testing cross-day refresh logic."""
        return datetime.now(ZoneInfo("Asia/Shanghai"))

    def _get_trade_dates(self, end_date: Optional[str] = None) -> List[str]:
        """Refresh the trading calendar cache by natural day to avoid continuing to reuse old calendars after cross-day service."""
        if self._api is None:
            return []

        china_now = self._get_china_now()
        requested_end_date = end_date or china_now.strftime("%Y%m%d")

        if self.date_list is not None and self._date_list_end == requested_end_date:
            return self.date_list

        start_date = (china_now - timedelta(days=20)).strftime("%Y%m%d")
        df_cal = self._call_api_with_rate_limit(
            "trade_cal",
            exchange="SSE",
            start_date=start_date,
            end_date=requested_end_date,
        )

        if df_cal is None or df_cal.empty or "cal_date" not in df_cal.columns:
            logger.warning("[Tushare] trade_cal 返回为空，无法更新交易日历缓存")
            self.date_list = []
            self._date_list_end = requested_end_date
            return self.date_list

        trade_dates = sorted(
            df_cal[df_cal["is_open"] == 1]["cal_date"].astype(str).tolist(),
            reverse=True,
        )
        self.date_list = trade_dates
        self._date_list_end = requested_end_date
        return trade_dates

    @staticmethod
    def _pick_trade_date(trade_dates: List[str], use_today: bool) -> Optional[str]:
        """Select the trading day (today or previous trading day) based on available trading days list."""
        if not trade_dates:
            return None
        if use_today or len(trade_dates) == 1:
            return trade_dates[0]
        return trade_dates[1]

    @staticmethod
    def _detect_exchange_hint(stock_code: str) -> Optional[str]:
        """Return SH/SZ/BJ when the raw user input carries an explicit exchange hint."""
        upper = (stock_code or "").strip().upper()
        if upper.startswith(("SH", "SS")) or upper.endswith((".SH", ".SS")):
            return "SH"
        if upper.startswith("SZ") or upper.endswith(".SZ"):
            return "SZ"
        if upper.startswith("BJ") or upper.endswith(".BJ"):
            return "BJ"
        return None

    @classmethod
    def _get_legacy_realtime_symbol(cls, stock_code: str) -> str:
        """Build the legacy tushare symbol while preserving explicit SH/SZ hints."""
        code = normalize_stock_code(stock_code)
        exchange_hint = cls._detect_exchange_hint(stock_code)

        if code == '000001' and exchange_hint == 'SH':
            return 'sh000001'
        if code == '399001':
            return 'sz399001'
        if code == '399006':
            return 'sz399006'
        if code == '000300':
            return 'sh000300'
        if is_bse_code(code):
            return f"bj{code}"
        return code
    
    def _convert_stock_code(self, stock_code: str) -> str:
        """
        Convert A-shares / ETF / Beijing Stock Exchange etc. to Tushare ts_code (excluding Hong Kong stock logic).

        Tushare required format example:
        - Shanghai stocks: 600519.SH
        - Shenzhen stocks: 000001.SZ
        - Shanghai Stock Exchange ETFs: 510050.SH
        - Shenzhen Stock Exchange ETFs: 159919.SZ

        Args:
            stock_code: original code, such as '600519', '000001', '563230'

        Returns:
            Tushare format code, such as '600519.SH', '000001.SZ'
        """
        raw_code = stock_code.strip()
        
        # Already has suffix.
        if '.' in raw_code:
            upper = raw_code.upper()
            code = normalize_stock_code(raw_code)
            exchange_hint = self._detect_exchange_hint(raw_code)
            if exchange_hint in ("SH", "SZ", "BJ") and code.isdigit():
                return f"{code}.{exchange_hint}"

            ts_code = upper
            if ts_code.endswith('.SS'):
                return f"{ts_code[:-3]}.SH"
            return ts_code

        if _is_us_code(raw_code):
            raise DataFetchError(f"TushareFetcher 不支持美股 {raw_code}，请使用 AkshareFetcher 或 YfinanceFetcher")

        if _is_hk_market(raw_code):
            # raise DataFetchError(f"TushareFetcher does not support Hong Kong stocks {raw_code}; use AkshareFetcher")
            return normalize_stock_code(raw_code)

        code = normalize_stock_code(raw_code)
        exchange_hint = self._detect_exchange_hint(raw_code)

        if exchange_hint == "SH":
            return f"{code}.SH"
        if exchange_hint == "SZ":
            return f"{code}.SZ"
        if exchange_hint == "BJ":
            return f"{code}.BJ"

        # ETF: determine exchange by prefix
        if code.startswith(_ETF_SH_PREFIXES) and len(code) == 6:
            return f"{code}.SH"
        if code.startswith(_ETF_SZ_PREFIXES) and len(code) == 6:
            return f"{code}.SZ"
        
        # BSE (Beijing Stock Exchange): 8xxxxx, 4xxxxx, 920xxx
        if is_bse_code(code):
            return f"{code}.BJ"
        
        # Regular stocks
        # Shanghai: 600xxx, 601xxx, 603xxx, 605xxx, 688xxx (STAR Market)
        # Shenzhen: 000xxx, 001xxx, 002xxx, 003xxx, 300xxx, 301xxx (ChiNext)
        if code.startswith(('600', '601', '603', '605', '688')):
            return f"{code}.SH"
        elif code.startswith(('000', '001', '002', '003', '300', '301')):
            return f"{code}.SZ"
        else:
            logger.warning(f"无法确定股票 {code} 的市场，默认使用深市")
            return f"{code}.SZ"

    def _convert_hk_stock_code_for_tushare(self, stock_code: str) -> str:
        """
        Convert user input to Tushare Pro interface required ts_code (including Hong Kong stocks nnnnn.HK)

        - Not HK stocks: use _convert_stock_code (A-shares / ETF / Beijing Stock Exchange).
        - Hong Kong stocks: Convert HK00700, 00700, 00700.HK etc. into a 5-digit number + .HK.
        """
        raw_code = stock_code.strip()
        if _is_hk_market(raw_code):
            if "." in raw_code:
                ts_code = raw_code.upper()
                if ts_code.endswith(".SS"):
                    return f"{ts_code[:-3]}.SH"
                if ts_code.endswith(".HK"):
                    return ts_code
            digits = re.sub(r"\D", "", raw_code)
            if not digits:
                raise DataFetchError(f"无法识别港股代码 {raw_code}")
            code = digits[-5:].rjust(5, "0")
            return f"{code}.HK"
        return self._convert_stock_code(stock_code)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=safe_before_sleep_log(
            logger,
            logging.WARNING,
            event="Tushare daily data retry scheduled",
            error_code="tushare_daily_data_retry",
        ),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Get raw data from Tushare
        
        Select different interfaces based on code type:
        - Regular stocks: daily()
        - ETF Fund: fund_daily()
        
        Process:
        1. Check API availability
        2. Check if it's U.S. stocks (not supported)
        3. Execute rate limit check
        4. Convert stock code format
        5. Select interface and call based on code type:
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
        Standardize Tushare data
        
        Tushare daily / fund_daily Column name returned:
        ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        
        Map to standard column names:
        date, open, high, low, close, volume, amount, pct_chg

        Unit scaling only applies to A-shares (and ETFs using the same unit interface):
        - vol is measured in lots; multiply by 100 to convert it to shares
        - amount is measured in CNY 1,000; multiply by 1,000 to convert it to yuan

        Hong Kong `hk_daily` volume and amount are already at a usable scale and must not be converted this way.
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
        
        # Volume/trading value: convert units only for A-share interfaces; do not convert hk_daily values
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

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        Get stock name
        
        Use Tushare's stock_basic interface to retrieve stock basic information
        
        Args:
            stock_code: stock code
            
        Returns:
            Stock Name, returns None on failure
        """
        if self._api is None:
            logger.warning("Tushare API 未初始化，无法获取股票名称")
            return None

        # Check the cache
        if hasattr(self, '_stock_name_cache') and stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        # Initialize cache
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        try:
            # Rate limit check.
            self._check_rate_limit()
            

            # Select basic information interface based on market/type:
            if _is_hk_market(stock_code):
                ts_code = self._convert_hk_stock_code_for_tushare(stock_code)
                # Hong Kong stocks: Use hk_basic
                df = self._api.hk_basic(
                    ts_code=ts_code,
                    fields='ts_code,name'
                )
            elif _is_etf_code(stock_code):
                ts_code = self._convert_stock_code(stock_code)
                # ETF: Use fund_basic
                df = self._api.fund_basic(
                    ts_code=ts_code,
                    fields='ts_code,name'
                )
            else:
                ts_code = self._convert_stock_code(stock_code)
                # A-shares Stocks: Use stock_basic
                df = self._api.stock_basic(
                    ts_code=ts_code,
                    fields='ts_code,name'
                )
            
            if df is not None and not df.empty:
                name = df.iloc[0]['name']
                self._stock_name_cache[stock_code] = name
                logger.debug(f"Tushare 获取股票名称成功: {stock_code} -> {name}")
                return name
            
        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare stock name lookup failed",
                e,
                error_code="tushare_stock_name_lookup_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
        
        return None
    
    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """
        Get stock list
        
        Use Tushare's stock_basic interface to get a list of A-shares (excluding Hong Kong stocks)
        
        Returns:
            A DataFrame containing code, name, industry, area, market columns, returns None on failure
        """
        if self._api is None:
            logger.warning("Tushare API 未初始化，无法获取股票列表")
            return None
        
        try:
            self._check_rate_limit()

            df = self._api.stock_basic(
                exchange='',
                list_status='L',
                fields='ts_code,name,industry,area,market'
            )

            if df is None or df.empty:
                return None

            df = df.copy()
            df['code'] = df['ts_code'].astype(str).str.split('.').str[0]

            if not hasattr(self, '_stock_name_cache'):
                self._stock_name_cache = {}
            for _, row in df.iterrows():
                self._stock_name_cache[row['code']] = row['name']

            logger.info(f"Tushare 获取股票列表成功: {len(df)} 条")
            return df[['code', 'name', 'industry', 'area', 'market']]

        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare stock list lookup failed",
                e,
                error_code="tushare_stock_list_lookup_failed",
                level=logging.WARNING,
            )

        return None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        Get real-time quotes

        Strategy:
        1. Prefer Pro interface (requires 2000 points): Full data, high stability.
        2. Failure falls back to the old interface: low threshold, less data

        Args:
            stock_code: stock code

        Returns:
            UnifiedRealtimeQuote object, or None on failure
        """
        if self._api is None:
            return None

        # HK stocks not supported by Tushare
        if _is_hk_market(stock_code):
            logger.debug(f"TushareFetcher 跳过港股实时行情 {stock_code}")
            return None

        normalized_code = normalize_stock_code(stock_code)

        from .realtime_types import (
            RealtimeSource,
            safe_float, safe_int
        )

        # Rate limit check.
        self._check_rate_limit()

        # Try Pro interface
        try:
            ts_code = self._convert_stock_code(stock_code)
            # Attempt to call Pro real-time interface (requires points)
            df = self._api.quotation(ts_code=ts_code)

            if df is not None and not df.empty:
                row = df.iloc[0]
                logger.debug(f"Tushare Pro 实时行情获取成功: {stock_code}")

                return UnifiedRealtimeQuote(
                    code=normalized_code,
                    name=str(row.get('name', '')),
                    source=RealtimeSource.TUSHARE,
                    price=safe_float(row.get('price')),
                    change_pct=safe_float(row.get('pct_chg')),  # The Pro interface usually directly returns percentage change
                    change_amount=safe_float(row.get('change')),
                    volume=safe_int(row.get('vol')),
                    amount=safe_float(row.get('amount')),
                    high=safe_float(row.get('high')),
                    low=safe_float(row.get('low')),
                    open_price=safe_float(row.get('open')),
                    pre_close=safe_float(row.get('pre_close')),
                    turnover_rate=safe_float(row.get('turnover_ratio')), # The Pro interface may have turnover rates
                    pe_ratio=safe_float(row.get('pe')),
                    pb_ratio=safe_float(row.get('pb')),
                    total_mv=safe_float(row.get('total_mv')),
                )
        except Exception as e:
            # Log at debug level and continue to the fallback interface
            log_safe_exception(
                logger,
                "Tushare Pro realtime quote unavailable; trying legacy fallback",
                e,
                error_code="tushare_pro_realtime_quote_unavailable",
                level=logging.DEBUG,
                context={"symbol": stock_code},
            )

        # Fallback: try the legacy interface
        try:
            import tushare as ts

            symbol = self._get_legacy_realtime_symbol(stock_code)

            # Call the old real-time interface (ts.get_realtime_quotes)
            df = ts.get_realtime_quotes(symbol)

            if df is None or df.empty:
                return None

            row = df.iloc[0]

            # Calculate Percentage Change
            price = safe_float(row['price'])
            pre_close = safe_float(row['pre_close'])
            change_pct = 0.0
            change_amount = 0.0

            if price and pre_close and pre_close > 0:
                change_amount = price - pre_close
                change_pct = (change_amount / pre_close) * 100

            # Build unified object
            return UnifiedRealtimeQuote(
                code=normalized_code,
                name=str(row['name']),
                source=RealtimeSource.TUSHARE,
                price=price,
                change_pct=round(change_pct, 2),
                change_amount=round(change_amount, 2),
                volume=safe_int(row['volume']) // 100,  # Convert shares to lots
                amount=safe_float(row['amount']),
                high=safe_float(row['high']),
                low=safe_float(row['low']),
                open_price=safe_float(row['open']),
                pre_close=pre_close,
            )

        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare legacy realtime quote failed",
                e,
                error_code="tushare_legacy_realtime_quote_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
            return None

    def get_main_indices(self, region: str = "cn") -> Optional[List[dict]]:
        """
        Get real-time quotes for key indices (Tushare Pro), only supports A-shares.
        """
        if region != "cn":
            return None
        if self._api is None:
            return None

        from .realtime_types import safe_float

        # Index mapping: Tushare code -> name
        indices_map = {
            '000001.SH': '上证指数',
            '399001.SZ': '深证成指',
            '399006.SZ': '创业板指',
            '000688.SH': '科创50',
            '000016.SH': '上证50',
            '000300.SH': '沪深300',
        }

        try:
            self._check_rate_limit()

            # Tushare index_daily retrieves historical data, real-time data needs to be used with other interfaces or estimated
            # Since Tushare free users may not be able to obtain real-time index quotes, this is used as an alternative.
            # Use index_daily to get recent trading data

            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - pd.Timedelta(days=5)).strftime('%Y%m%d')

            results = []

            # Batch retrieve all index data
            for ts_code, name in indices_map.items():
                try:
                    df = self._api.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                    if df is not None and not df.empty:
                        row = df.iloc[0] # Latest day

                        current = safe_float(row['close'])
                        prev_close = safe_float(row['pre_close'])

                        results.append({
                            'code': ts_code.split('.')[0], # Compatible with sh000001 format needs conversion, here keep pure numbers.
                            'name': name,
                            'current': current,
                            'change': safe_float(row['change']),
                            'change_pct': safe_float(row['pct_chg']),
                            'open': safe_float(row['open']),
                            'high': safe_float(row['high']),
                            'low': safe_float(row['low']),
                            'prev_close': prev_close,
                            'volume': safe_float(row['vol']),
                            'amount': safe_float(row['amount']) * 1000, # Convert CNY 1,000 to yuan
                            'amplitude': 0.0 # Tushare index_daily does not return amplitude directly
                        })
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Tushare index quote failed",
                        e,
                        error_code="tushare_index_quote_failed",
                        level=logging.DEBUG,
                        context={"market": "cn", "index_code": ts_code},
                    )
                    continue

            if results:
                return results
            else:
                logger.warning("[Tushare] 未获取到指数行情数据")

        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare market indices fetch failed",
                e,
                error_code="tushare_market_indices_failed",
                level=logging.ERROR,
                context={"market": region},
            )

        return None

    def get_market_stats(self) -> Optional[dict]:
        """
        Get market rise-fall statistics (Tushare Pro)
        2000 points, access ts.pro_api().rt_k twice daily
        API limits see: https://tushare.pro/document/1?doc_id=108
        """
        if self._api is None:
            return None

        try:
            logger.info("[Tushare] ts.pro_api() 获取市场统计...")
            
            # Get the current Shanghai time and determine whether it is within trading hours
            china_now = self._get_china_now()
            current_clock = china_now.strftime("%H:%M")
            current_date = china_now.strftime("%Y%m%d")

            trade_dates = self._get_trade_dates(current_date)
            if not trade_dates:
                return None

            if current_date in trade_dates:
                if current_clock < '09:30' or current_clock > '16:30':
                    use_realtime = False
                else:
                    use_realtime = True
            else:
                use_realtime = False

            # If using live trading, use other data sources such as akshare, efinance.
            if use_realtime:
                try:
                    df = self._call_api_with_rate_limit("rt_k", ts_code='3*.SZ,6*.SH,0*.SZ,92*.BJ')
                    if df is not None and not df.empty:
                        return self._calc_market_stats(df)
                    
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Tushare realtime market statistics fetch failed",
                        e,
                        error_code="tushare_realtime_market_stats_failed",
                        level=logging.ERROR,
                    )
                    return None
            else:

                if current_date not in trade_dates:
                    last_date = self._pick_trade_date(trade_dates, use_today=True)  # Retrieve data from the nearest date
                else:
                    if current_clock < '09:30': 
                        last_date = self._pick_trade_date(trade_dates, use_today=False)  # Retrieve data from the previous day
                    else:  # '> 16:30'
                        last_date = self._pick_trade_date(trade_dates, use_today=True)  # Retrieve data from the current day

                if last_date is None:
                    return None

                try:
                    df = self._call_api_with_rate_limit(
                        "daily",
                        ts_code='3*.SZ,6*.SH,0*.SZ,92*.BJ',
                        start_date=last_date,
                        end_date=last_date,
                    )
                    # To prevent column names with inconsistent capitalization from different interfaces (e.g., rt_k returning lowercase and daily returning uppercase), all column names are converted to lowercase.
                    df.columns = [col.lower() for col in df.columns]

                    # Get stock basic information (including code and name)
                    df_basic = self._call_api_with_rate_limit("stock_basic", fields='ts_code,name')
                    df = pd.merge(df, df_basic, on='ts_code', how='left')
                    # Multiply the values in the 'amount' column from daily by 1000 to align with other data sources
                    if 'amount' in df.columns:
                        df['amount'] = df['amount'] * 1000

                    if df is not None and not df.empty:
                        return self._calc_market_stats(df)
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Tushare daily market statistics fetch failed",
                        e,
                        error_code="tushare_daily_market_stats_failed",
                        level=logging.ERROR,
                    )
                    

            
        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare market statistics fetch failed",
                e,
                error_code="tushare_market_stats_failed",
                level=logging.ERROR,
            )

        return None
    
    def _calc_market_stats(
            self,
            df: pd.DataFrame,
            ) -> Optional[Dict[str, Any]]:
            """Calculate advance/decline statistics from a market DataFrame."""
            import numpy as np

            df = df.copy()
            
            # 1. Extracts basic comparison data: latest price, previous close
            # Compatible with column names returned from different interfaces sina/em efinance tushare xtdata
            code_col = next((c for c in ['代码', '股票代码', 'ts_code','stock_code'] if c in df.columns), None)
            name_col = next((c for c in ['名称', '股票名称','name','name'] if c in df.columns), None)
            close_col = next((c for c in ['最新价', '最新价', 'close','lastPrice'] if c in df.columns), None)
            pre_close_col = next((c for c in ['昨收', '昨日收盘', 'pre_close','lastClose'] if c in df.columns), None)
            amount_col = next((c for c in ['成交额', '成交额', 'amount','amount'] if c in df.columns), None) 
            
            limit_up_count = 0
            limit_down_count = 0
            up_count = 0
            down_count = 0
            flat_count = 0

            for code, name, current_price, pre_close, amount in zip(
                df[code_col], df[name_col], df[close_col], df[pre_close_col], df[amount_col]
            ):
                
                # Pause filtering of efinance's pause data sometimes missing price display as '-', em display as none
                if pd.isna(current_price) or pd.isna(pre_close) or current_price in ['-'] or pre_close in ['-'] or amount == 0:
                    continue
                
                # em and efinance may return strings; convert them to floats
                current_price = float(current_price)
                pre_close = float(pre_close)
                
                # Get pure numeric code without prefix
                pure_code = normalize_stock_code(str(code)) 

                # A. Determine the percentage change of each stock (using pure numeric codes to judge)
                if is_bse_code(pure_code): 
                    ratio = 0.30
                elif is_kc_cy_stock(pure_code): #pure_code.startswith(('688', '30')):
                    ratio = 0.20
                elif is_st_stock(name): #'ST' in str_name:
                    ratio = 0.05
                else:
                    ratio = 0.10

                # B. Calculate A-share limit-up and limit-down prices strictly: previous close * (1 +/- percentage), rounded to two decimals.
                limit_up_price = np.floor(pre_close * (1 + ratio) * 100 + 0.5) / 100.0
                limit_down_price = np.floor(pre_close * (1 - ratio) * 100 + 0.5) / 100.0

                limit_up_price_Tolerance = round(abs(pre_close * (1 + ratio) - limit_up_price), 10)
                limit_down_price_Tolerance = round(abs(pre_close * (1 - ratio) - limit_down_price), 10)

                # C. Exact matching
                if current_price > 0 :
                    is_limit_up = (current_price > 0) and (abs(current_price - limit_up_price) <= limit_up_price_Tolerance)
                    is_limit_down = (current_price > 0) and (abs(current_price - limit_down_price) <= limit_down_price_Tolerance)

                    if is_limit_up:
                        limit_up_count += 1
                    if is_limit_down:
                        limit_down_count += 1

                    if current_price > pre_close:
                        up_count += 1
                    elif current_price < pre_close:
                        down_count += 1
                    else:
                        flat_count += 1
                    
            # Count quantity
            stats = {
                'up_count': up_count,
                'down_count': down_count,
                'flat_count': flat_count,
                'limit_up_count': limit_up_count,
                'limit_down_count': limit_down_count,
                'total_amount': 0.0,
            }
            
            # trading value statistics
            if amount_col and amount_col in df.columns:
                df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
                stats['total_amount'] = (df[amount_col].sum() / 1e8)
                
            return stats

    def get_trade_time(self,early_time='09:30',late_time='16:30') -> Optional[str]:
        '''
        Get the current time to obtain the start date of available data

        Args:
                early_time: Default '09:30'
                late_time: default '16:30'
                'early_time'-'late_time' represents the time period for using the previous trading day's data; other times use today's data.
        Returns:
                start_date: can obtain the start date of the data
        '''
        china_now = self._get_china_now()
        china_date = china_now.strftime("%Y%m%d")
        china_clock = china_now.strftime("%H:%M")

        trade_dates = self._get_trade_dates(china_date)
        if not trade_dates:
            return None

        if china_date in trade_dates:
            if  early_time < china_clock < late_time: # Use the data from the previous trading day's time period
                use_today = False
            else:
                use_today = True
        else:
            # Non-trading day: today is not in trade_dates, trade_dates[0] is the latest trading day
            use_today = True

        start_date = self._pick_trade_date(trade_dates, use_today=use_today)
        if start_date is None:
            return None

        if not use_today:
            logger.info(f"[Tushare] 当前时间 {china_clock} 可能无法获取当天筹码分布，尝试获取前一个交易日的数据 {start_date}")

        return start_date
    
    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[list, list]]:
        """
        Get the rising/falling sector leaderboard (Tushare Pro)
        
        Data source priority:
        1. ts.pro_api().moneyflow_ind_ths (Tonghuashun interface)
        2. Eastmoney interface (ts.pro_api().moneyflow_ind_dc)
        Note: Different industries and sectors have different definitions across each interface, leading to inconsistent results.
        """
        def _get_rank_top_n(df: pd.DataFrame, change_col: str, industry_name: str, n: int) -> Tuple[list, list]:
            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])

            # Top N rising
            top = df.nlargest(n, change_col)
            top_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in top.iterrows()
            ]

            bottom = df.nsmallest(n, change_col)
            bottom_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in bottom.iterrows()
            ]
            return top_sectors, bottom_sectors

        # Today's data is available after 15:30.
        start_date = self.get_trade_time(early_time='00:00', late_time='15:30')
        if not start_date:
            return None

        # Prefer Tonghuashun interface.
        logger.info("[Tushare] ts.pro_api().moneyflow_ind_ths 获取板块排行(同花顺)...")
        try:
            df = self._call_api_with_rate_limit("moneyflow_ind_ths", trade_date=start_date)
            if df is not None and not df.empty:
                change_col = 'pct_change'
                name = 'industry'
                if change_col in df.columns:
                    return _get_rank_top_n(df, change_col, name, n)
        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare THS sector ranking failed; trying Eastmoney fallback",
                e,
                error_code="tushare_ths_sector_ranking_failed",
                level=logging.WARNING,
            )

        # Tonghuashun API failed, fallback to Eastmoney interface.
        logger.info("[Tushare] ts.pro_api().moneyflow_ind_dc 获取板块排行(东财)...")
        try:
            df = self._call_api_with_rate_limit("moneyflow_ind_dc", trade_date=start_date)
            if df is not None and not df.empty:
                df = df[df['content_type'] == '行业']  # Filter out industry sectors
                change_col = 'pct_change'
                name = 'name'
                if change_col in df.columns:
                    return _get_rank_top_n(df, change_col, name, n)
        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare Eastmoney sector ranking failed",
                e,
                error_code="tushare_eastmoney_sector_ranking_failed",
                level=logging.WARNING,
            )
            return None
        
        # Return None when the response is empty or reports an error
        return None
    
    

    
    def get_chip_distribution(self, stock_code: str) -> Optional[ChipDistribution]:
        """
        Get chip distribution data
        
        Data source: ts.pro_api().cyq_chips()
        Includes: profit ratio, average cost, chip concentration
        
        Note: ETFs and indices have no chip distribution data; Hong Kong stocks are unsupported. Both cases return None.
        Less than 5000 points, access up to 15 times daily, up to 5 times per hour
        
        Args:
            stock_code: stock code
            
        Returns:
            ChipDistribution object (latest trading day data), returns None if retrieval fails

        """
        if _is_us_code(stock_code):
            logger.warning(f"[Tushare] TushareFetcher 不支持美股 {stock_code} 的筹码分布")
            return None
        
        if _is_etf_code(stock_code):
            logger.warning(f"[Tushare] TushareFetcher 不支持 ETF {stock_code} 的筹码分布")
            return None

        if _is_hk_market(stock_code):
            logger.warning(f"[Tushare] TushareFetcher 不支持港股 {stock_code} 的筹码分布")
            return None
        
        try:
            # Today's data is available after 19:00.
            start_date = self.get_trade_time(early_time='00:00', late_time='19:00') 
            if not start_date:
                return None

            ts_code = self._convert_stock_code(stock_code)

            df = self._call_api_with_rate_limit(
                "cyq_chips",
                ts_code=ts_code,
                start_date=start_date,
                end_date=start_date,
            )
            if df is not None and not df.empty:
                daily_df = self._call_api_with_rate_limit(
                    "daily",
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=start_date,
                )
                if daily_df is None or daily_df.empty:
                    return None
                current_price = daily_df.iloc[0]['close']
                metrics = self.compute_cyq_metrics(df, current_price)

                chip = ChipDistribution(
                    code=stock_code,
                    date=datetime.strptime(start_date, '%Y%m%d').strftime('%Y-%m-%d'),
                    profit_ratio=metrics['获利比例'],
                    avg_cost=metrics['平均成本'],
                    cost_90_low=metrics['90成本-低'],
                    cost_90_high=metrics['90成本-高'],
                    concentration_90=metrics['90集中度'],
                    cost_70_low=metrics['70成本-低'],
                    cost_70_high=metrics['70成本-高'],
                    concentration_70=metrics['70集中度'],
                )
                
                logger.info(f"[筹码分布] {stock_code} 日期={chip.date}: 获利比例={chip.profit_ratio:.1%}, "
                        f"平均成本={chip.avg_cost}, 90%集中度={chip.concentration_90:.2%}, "
                        f"70%集中度={chip.concentration_70:.2%}")
                return chip

        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare chip distribution fetch failed",
                e,
                error_code="tushare_chip_distribution_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
            return None

    def compute_cyq_metrics(self, df: pd.DataFrame, current_price: float) -> dict:
        """
        Calculate common chip-distribution indicators from Tushare's cyq_chips table.
        :param df: DataFrame containing 'price' and 'percent' columns
        :param current_price: Stock's daily current price/closing price (used to calculate profit ratio)
        :return: Dictionary containing chip-distribution indicators
        """
        import numpy as np
        # 1. Sort by price in ascending order (Tushare data is often returned in descending order)
        df_sorted = df.sort_values(by='price', ascending=True).reset_index(drop=True)

        # 2. Prevent the sum of original data percent from generating floating-point errors, normalized to 100%.
        total_percent = df_sorted['percent'].sum()

        df_sorted['norm_percent'] = df_sorted['percent'] / total_percent * 100

        # 3. Calculate the cumulative distribution of holdings
        df_sorted['cumsum'] = df_sorted['norm_percent'].cumsum()

        # --- Profit Ratio ---
        # The sum of all positions with prices <= current price
        winner_rate = df_sorted[df_sorted['price'] <= current_price]['norm_percent'].sum()

        # --- Average Cost ---
        # Weighted Average Price
        avg_cost = np.average(df_sorted['price'], weights=df_sorted['norm_percent'])

        # --- Helper function: Get the price at specified cumulative ratio ---
        def get_percentile_price(target_pct):
            # Find the index of the first row where cumulative sum is greater than or equal to target percentage.
            idx = df_sorted['cumsum'].searchsorted(target_pct)
            idx = min(idx, len(df_sorted) - 1) # Prevent out-of-bounds access.
            return df_sorted.loc[idx, 'price']

        # --- 90% Cost Area and Concentration ---
        # Remove top and bottom 5%
        cost_90_low = get_percentile_price(5)
        cost_90_high = get_percentile_price(95)
        if (cost_90_high + cost_90_low) != 0:
            concentration_90 = (cost_90_high - cost_90_low) / (cost_90_high + cost_90_low) * 100
        else:
            concentration_90 = 0.0
            
        # --- 70% Cost Area and Concentration ---
        # Trim 15% from each
        cost_70_low = get_percentile_price(15)
        cost_70_high = get_percentile_price(85)
        if (cost_70_high + cost_70_low) != 0:
            concentration_70 = (cost_70_high - cost_70_low) / (cost_70_high + cost_70_low) * 100
        else:
            concentration_70 = 0.0

        # Returns formatted results
        return {
            "获利比例": round(winner_rate/100, 4), # Divide by 100 to match AkShare and return a decimal value.
            "平均成本": round(avg_cost, 4),
            "90成本-低": round(cost_90_low, 4),
            "90成本-高": round(cost_90_high, 4),
            "90集中度": round(concentration_90/100, 4),
            "70成本-低": round(cost_70_low, 4),
            "70成本-高": round(cost_70_high, 4),
            "70集中度": round(concentration_70/100, 4)
        }



if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = TushareFetcher()
    
    try:
        # Test historical data
        df = fetcher.get_daily_data('600519')  # Maotai
        print(f"获取成功，共 {len(df)} 条数据")
        print(df.tail())
        
        # Test stock name
        name = fetcher.get_stock_name('600519')
        print(f"股票名称: {name}")
        
    except Exception as e:
        print(f"获取失败: {e}")

    # Test market statistics
    print("\n" + "=" * 50)
    print("Testing get_market_stats (tushare)")
    print("=" * 50)
    try:
        stats = fetcher.get_market_stats()
        if stats:
            print(f"Market Stats successfully computed:")
            print(f"Up: {stats['up_count']} (Limit Up: {stats['limit_up_count']})")
            print(f"Down: {stats['down_count']} (Limit Down: {stats['limit_down_count']})")
            print(f"Flat: {stats['flat_count']}")
            print(f"Total Amount: {stats['total_amount']:.2f} 亿 (Yi)")
        else:
            print("Failed to compute market stats.")
    except Exception as e:
        print(f"Failed to compute market stats: {e}")


    # Test chip distribution data
    print("\n" + "=" * 50)
    print("测试筹码分布数据获取")
    print("=" * 50)
    try:
        chip = fetcher.get_chip_distribution('600519')  # Maotai
    except Exception as e:
        print(f"[筹码分布] 获取失败: {e}")

    # Test industry sector ranking
    print("\n" + "=" * 50)
    print("测试行业板块排名获取")
    print("=" * 50)
    try:
        rankings = fetcher.get_sector_rankings(n=5)
        if rankings:
            top, bottom = rankings
            print("涨幅榜 Top 5:")
            for sector in top:
                print(f"{sector['name']}: {sector['change_pct']}%")
            print("\n跌幅榜 Top 5:")
            for sector in bottom:
                print(f"{sector['name']}: {sector['change_pct']}%")
        else:
            print("未获取到行业板块排名数据")
    except Exception as e:
        print(f"[行业板块排名] 获取失败: {e}")
