# -*- coding: utf-8 -*-
"""
===================================
PytdxFetcher - DingTalk data source (Priority 2)
===================================

data source: Tushita Finance Quote Server(pytdx database)
Characteristics: Free, no Token required, direct connection to market servers
Advantages: Real-time data, stable, no quota limits

Key strategy:
1. Automatic server switching across multiple servers
2. Automatically reconnect if connection times out.
3. retries with exponential backoff after failures
"""

import logging
import re
import time
from contextlib import contextmanager
from typing import Optional, Generator, List, Tuple

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.utils.sanitize import log_safe_exception, safe_before_sleep_log

from .base import (
    BaseFetcher,
    DataFetchError,
    DataSourceUnavailableError,
    STANDARD_COLUMNS,
    is_bse_code,
    normalize_stock_code,
    _is_hk_market,
)
import os

logger = logging.getLogger(__name__)

_PYTDX_CONNECTION_COOLDOWN_SECONDS = 15.0


def _parse_hosts_from_env() -> Optional[List[Tuple[str, int]]]:
    """
    Build DingTalk server list from environment variables.

    Priority:
    1. PYTDX_SERVERS: Comma-separated "ip:port,ip:port"(If "192.168.1.1:7709,10.0.0.1:7709")
    2. PYTDX_HOST + PYTDX_PORT: Single server
    3. Returns None if none are configured (caller uses DEFAULT_HOSTS).
    """
    servers = os.getenv("PYTDX_SERVERS", "").strip()
    if servers:
        result = []
        for part in servers.split(","):
            part = part.strip()
            if ":" in part:
                host, port_str = part.rsplit(":", 1)
                host, port_str = host.strip(), port_str.strip()
                if host and port_str:
                    try:
                        result.append((host, int(port_str)))
                    except ValueError:
                        logger.warning(f"Invalid PYTDX_SERVERS entry: {part}")
            else:
                logger.warning(f"Invalid PYTDX_SERVERS entry (missing port): {part}")
        if result:
            return result

    host = os.getenv("PYTDX_HOST", "").strip()
    port_str = os.getenv("PYTDX_PORT", "").strip()
    if host and port_str:
        try:
            return [(host, int(port_str))]
        except ValueError:
            logger.warning(f"Invalid PYTDX_HOST/PYTDX_PORT: {host}:{port_str}")

    return None


def _is_us_code(stock_code: str) -> bool:
    """
    Determine if the code is a U.S. stock.
    
    U.S. stock code rules:
    - 1-5 uppercase letters, such as 'AAPL', 'TSLA'
    - May contain '.', such as 'BRK.B'.
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


class PytdxFetcher(BaseFetcher):
    """
    Trading master data source implementation
    
    Priority: 2 (same level as Tushare).
    data source: Tushita Finance Quote Server
    
    Key strategy:
    - Automatically select the optimal server
    - Automatically switch servers if connection fails.
    - retries with exponential backoff after failures
    
    Pytdx Features:
    - Free, no registration required
    - Directly connect to market data server
    - Supports real-time quotes and historical data
    - Supports stock name query
    """
    
    name = "PytdxFetcher"
    priority = int(os.getenv("PYTDX_PRIORITY", "2"))
    
    # Default Tiger Brokers data server list
    DEFAULT_HOSTS = [
        ("119.147.212.81", 7709),  # Shenzhen
        ("112.74.214.43", 7727),   # Shenzhen
        ("221.231.141.60", 7709),  # Shanghai
        ("101.227.73.20", 7709),   # Shanghai
        ("101.227.77.254", 7709),  # Shanghai
        ("14.215.128.18", 7709),   # Guangzhou
        ("59.173.18.140", 7709),   # Wuhan
        ("180.153.39.51", 7709),   # Hangzhou
    ]
    # Pytdx get_security_list returns at most 1000 items per page
    SECURITY_LIST_PAGE_SIZE = 1000
    
    def __init__(self, hosts: Optional[List[Tuple[str, int]]] = None):
        """
        Initialize PytdxFetcher

        Args:
            hosts: server list [(host, port), ...]. If not passed in, use environment variables first
                   PYTDX_SERVERS(ip:port,ip:port)Or PYTDX_HOST+PYTDX_PORT,
                   Otherwise, use the built-in DEFAULT_HOSTS.
        """
        if hosts is not None:
            self._hosts = hosts
        else:
            env_hosts = _parse_hosts_from_env()
            self._hosts = env_hosts if env_hosts else self.DEFAULT_HOSTS
        self._api = None
        self._connected = False
        self._current_host_idx = 0
        self._stock_list_cache = None  # Stock List Cache
        self._stock_name_cache = {}    # Stock Name Cache {code: name}
        self._unavailable_until = 0.0
        self._last_unavailable_reason = ""

    def _is_in_connection_cooldown(self) -> bool:
        return time.time() < self._unavailable_until

    def _mark_connection_cooldown(self, reason: str) -> None:
        self._unavailable_until = time.time() + _PYTDX_CONNECTION_COOLDOWN_SECONDS
        self._last_unavailable_reason = str(reason or "").strip()
        logger.info(
            "Pytdx 连接失败，进入冷却 %.0fs: %s",
            _PYTDX_CONNECTION_COOLDOWN_SECONDS,
            self._last_unavailable_reason or "unknown",
        )

    def is_available_for_request(self, capability: str = "") -> bool:
        return not self._is_in_connection_cooldown()
    
    def _get_pytdx(self):
        """
        Lazy load pytdx module
        
        Import only on the first use to avoid errors if not installed.
        """
        try:
            from pytdx.hq import TdxHq_API
            return TdxHq_API
        except ImportError:
            logger.warning("pytdx 未安装，请运行: pip install pytdx")
            return None
    
    @contextmanager
    def _pytdx_session(self) -> Generator:
        """
        Pytdx Connection Context Manager
        
        Ensure:
        1. Automatically connect when context is entered.
        2. Disconnect automatically when exiting context
        3. Disconnect correctly even in abnormal situations
        
        Using example:
            with self._pytdx_session() as api:
                # Execute data queries here
        """
        if self._is_in_connection_cooldown():
            raise DataSourceUnavailableError(
                f"Pytdx temporarily unavailable: {self._last_unavailable_reason or 'connection cooldown'}"
            )

        TdxHq_API = self._get_pytdx()
        if TdxHq_API is None:
            raise DataFetchError("pytdx 库未安装")
        
        api = TdxHq_API()
        connected = False
        
        try:
            # Attempt to connect to the server (automatically selects the optimal one)
            for i in range(len(self._hosts)):
                host_idx = (self._current_host_idx + i) % len(self._hosts)
                host, port = self._hosts[host_idx]
                
                try:
                    if api.connect(host, port, time_out=5):
                        connected = True
                        self._current_host_idx = host_idx
                        logger.debug(f"Pytdx 连接成功: {host}:{port}")
                        break
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Pytdx server connection failed",
                        e,
                        error_code="pytdx_server_connection_failed",
                        level=logging.DEBUG,
                        context={"host": host, "port": port},
                    )
                    continue
            
            if not connected:
                self._mark_connection_cooldown("Pytdx 无法连接任何服务器")
                raise DataFetchError("Pytdx 无法连接任何服务器")
            
            yield api
            
        finally:
            # Ensure connection is broken
            try:
                api.disconnect()
                logger.debug("Pytdx 连接已断开")
            except Exception as e:
                log_safe_exception(
                    logger,
                    "Pytdx disconnect failed",
                    e,
                    error_code="pytdx_disconnect_failed",
                    level=logging.WARNING,
                )
    
    def _get_market_code(self, stock_code: str) -> Tuple[int, str]:
        """
        Determine the market based on stock code.
        
        Pytdx Market Code:
        - 0: Shenzhen
        - 1: Shanghai
        
        Args:
            stock_code: stock code
            
        Returns:
            (market, code) Tuple
        """
        raw_code = stock_code.strip()
        upper = raw_code.upper()
        prefix, separator, suffix = raw_code.partition(".")
        if separator and prefix:
            prefix_upper = prefix.strip().upper()
            if prefix_upper in ('SH', 'SS'):
                normalized = normalize_stock_code(suffix.strip())
                if normalized.isdigit() and len(normalized) == 6:
                    return 1, normalized
            if prefix_upper == 'SZ':
                normalized = normalize_stock_code(suffix.strip())
                if normalized.isdigit() and len(normalized) == 6:
                    return 0, normalized

        code = normalize_stock_code(raw_code)

        if upper.startswith(('SH', 'SS')) or upper.endswith(('.SH', '.SS')):
            return 1, code
        if upper.startswith('SZ') or upper.endswith('.SZ'):
            return 0, code
        
        # Determine the market based on code prefix
        # Shanghai: 60xxxx, 68xxxx (STAR Market)
        # Shenzhen: 00xxxx, 30xxxx (ChiNext), 002xxx (SME Board)
        if code.startswith(('60', '68')):
            return 1, code  # Shanghai
        else:
            return 0, code  # Shenzhen

    def _build_stock_list_cache(self, api) -> None:
        """
        Build a full stock code -> name cache from paginated security lists.
        """
        self._stock_list_cache = {}

        for market in (0, 1):
            start = 0
            while True:
                stocks = api.get_security_list(market, start) or []
                for stock in stocks:
                    code = stock.get('code')
                    name = stock.get('name')
                    if code and name:
                        self._stock_list_cache[code] = name

                if len(stocks) < self.SECURITY_LIST_PAGE_SIZE:
                    break

                start += self.SECURITY_LIST_PAGE_SIZE
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=safe_before_sleep_log(
            logger,
            logging.WARNING,
            event="Pytdx daily data retry scheduled",
            error_code="pytdx_daily_data_retry",
        ),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Get raw data from DingTalk.
        
        Use `get_security_bars()` to get daily data.
        
        Process:
        1. Check if it's U.S. stocks (not supported)
        2. Use a context manager to manage the connection
        3. Determine market code.
        4. Call API to get K line data
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
        
        with self._pytdx_session() as api:
            try:
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
                
            except Exception as e:
                if isinstance(e, DataFetchError):
                    raise
                raise DataFetchError(f"Pytdx 获取数据失败: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        Standardize Pytdx data
        
        Column names returned by Pytdx:
        datetime, open, high, low, close, vol, amount
        
        Map to standard column names:
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
    
    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        Get stock name
        
        Args:
            stock_code: stock code
            
        Returns:
            Stock Name, returns None on failure
        """
        # Hong Kong stocks are not supported (pytdx does not include Hong Kong stock data)
        if _is_hk_market(stock_code):
            return None

        # Check cache
        if stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        try:
            market, code = self._get_market_code(stock_code)
            
            with self._pytdx_session() as api:
                # Get stock list (caching)
                if self._stock_list_cache is None:
                    self._build_stock_list_cache(api)
                
                # Search for stock name
                name = self._stock_list_cache.get(code)
                if name:
                    self._stock_name_cache[stock_code] = name
                    return name
                
                # Attempt to use get_finance_info
                finance_info = api.get_finance_info(market, code)
                if finance_info and 'name' in finance_info:
                    name = finance_info['name']
                    self._stock_name_cache[stock_code] = name
                    return name
                
        except Exception as e:
            log_safe_exception(
                logger,
                "Pytdx stock name lookup failed",
                e,
                error_code="pytdx_stock_name_lookup_failed",
                level=logging.DEBUG,
                context={"symbol": stock_code},
            )
        
        return None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[dict]:
        """
        Get real-time quotes
        
        Args:
            stock_code: stock code
            
        Returns:
            Real-time quote data dictionary, failure returns None
        """
        if is_bse_code(stock_code):
            raise DataFetchError(
                f"PytdxFetcher 不支持北交所 {stock_code}，将自动切换其他数据源"
            )
        try:
            market, code = self._get_market_code(stock_code)
            
            with self._pytdx_session() as api:
                data = api.get_security_quotes([(market, code)])
                
                if data and len(data) > 0:
                    quote = data[0]
                    return {
                        'code': stock_code,
                        'name': quote.get('name', ''),
                        'price': quote.get('price', 0),
                        'open': quote.get('open', 0),
                        'high': quote.get('high', 0),
                        'low': quote.get('low', 0),
                        'pre_close': quote.get('last_close', 0),
                        'volume': quote.get('vol', 0),
                        'amount': quote.get('amount', 0),
                        'bid_prices': [quote.get(f'bid{i}', 0) for i in range(1, 6)],
                        'ask_prices': [quote.get(f'ask{i}', 0) for i in range(1, 6)],
                    }
        except Exception as e:
            log_safe_exception(
                logger,
                "Pytdx realtime quote failed",
                e,
                error_code="pytdx_realtime_quote_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
        
        return None


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = PytdxFetcher()
    
    try:
        # Test historical data
        df = fetcher.get_daily_data('600519')  # Maotai
        print(f"获取成功，共 {len(df)} 条数据")
        print(df.tail())
        
        # Test stock name
        name = fetcher.get_stock_name('600519')
        print(f"股票名称: {name}")
        
        # Test real-time quotes
        quote = fetcher.get_realtime_quote('600519')
        print(f"实时行情: {quote}")
        
    except Exception as e:
        print(f"获取失败: {e}")
