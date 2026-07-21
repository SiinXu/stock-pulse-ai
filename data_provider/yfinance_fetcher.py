# -*- coding: utf-8 -*-
"""
===================================
YfinanceFetcher - fallback data source (Priority 4)
===================================

Data source: Yahoo Finance (through yfinance library)
Characteristics: International data source, may have delays or missing data
Fallback safeguard when all domestic data sources fail.

Key strategy:
1. Automatically convert A-shares code to yfinance format (.SS / .SZ)
2. Handle Yahoo Finance data format differences
3. retries with exponential backoff after failures
"""

import csv
import logging
from datetime import datetime
from io import StringIO
from typing import Optional, List, Dict, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS, is_bse_code
from .realtime_types import UnifiedRealtimeQuote, RealtimeSource
from .us_index_mapping import get_us_index_yf_symbol, is_us_stock_code
from src.services.market_symbol_utils import get_suffix_market, is_suffix_market_symbol
from src.utils.sanitize import log_safe_exception, safe_before_sleep_log

# Optional local stock mapping patch can be imported, if missing, use empty dictionary as fallback.
try:
    from src.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name
except (ImportError, ModuleNotFoundError):
    STOCK_NAME_MAP = {}

    def is_meaningful_stock_name(name: str | None, stock_code: str) -> bool:
        """Basic signature validation fallback"""
        if not name:
            return False
        n = str(name).strip()
        return bool(n and n.upper() != str(stock_code).strip().upper())

import os

logger = logging.getLogger(__name__)


class YfinanceFetcher(BaseFetcher):
    """
    Yahoo Finance Data source implementation

    Priority: 4 (lowest, as fallback).
    Data source: Yahoo Finance

    Key strategy:
    - Automatically convert stock code format
    - Handle time zone and data format differences
    - retries with exponential backoff after failures

    Notes:
    - A-shares data may have delays
    - Some stocks may have no data
    - Data accuracy may differ slightly from domestic sources
    """

    name = "YfinanceFetcher"
    priority = int(os.getenv("YFINANCE_PRIORITY", "4"))

    def __init__(self):
        """Initialize YfinanceFetcher"""
        pass

    @staticmethod
    def _is_jp_kr_suffix_stock(stock_code: str) -> bool:
        """Return True for supported JP/KR suffix-only Yahoo symbols."""
        return is_suffix_market_symbol(stock_code, "jp") or is_suffix_market_symbol(stock_code, "kr")

    @staticmethod
    def _is_tw_suffix_stock(stock_code: str) -> bool:
        """Return True for supported Taiwan suffix-only Yahoo symbols (TWSE `.TW` / TPEx `.TWO`).

        Taiwan base codes are 4-6 digits (common stocks 4, ETFs/others up to 6,
        e.g. 00878 / 006208), wider than the JP `.T` range.
        """
        return is_suffix_market_symbol(stock_code, "tw")

    def _convert_stock_code(self, stock_code: str) -> str:
        """
        Convert stock codes to Yahoo Finance format

        Yahoo Finance Code format:
        - A-shares Hong Kong stocks: 600519.SS (Shanghai Stock Exchange)
        - A-shares Shenzhen Stock Exchange: 000001.SZ (Shenzhen Stock Exchange)
        - Hong Kong stocks: 0700.HK (Hong Kong Stock Exchange)
        - U.S. stocks: AAPL, TSLA, GOOGL (no suffix required)

        Args:
            stock_code: Original code, If '600519', 'hk00700', 'AAPL'

        Returns:
            Yahoo Finance Code format

        Examples:
            >>> fetcher._convert_stock_code('600519')
            '600519.SS'
            >>> fetcher._convert_stock_code('hk00700')
            '0700.HK'
            >>> fetcher._convert_stock_code('AAPL')
            'AAPL'
        """
        code = stock_code.strip().upper()

        # U.S. stocks indices: map to Yahoo Finance symbols (e.g., SPX -> ^GSPC)
        yf_symbol, _ = get_us_index_yf_symbol(code)
        if yf_symbol:
            logger.debug(f"识别为美股指数: {code} -> {yf_symbol}")
            return yf_symbol

        # U.S. stocks: 1-5 uppercase letters (optional .X suffix)
        if is_us_stock_code(code):
            logger.debug(f"识别为美股代码: {code}")
            return code

        # Japanese/Korean/Taiwan stocks MVP: Explicit Yahoo Finance suffix-only code, pass through to Yahoo as is.
        if self._is_jp_kr_suffix_stock(code) or self._is_tw_suffix_stock(code):
            logger.debug(f"识别为日韩台 Yahoo suffix 代码: {code}")
            return code

        # Hong Kong stocks: hk prefix -> .HK suffix
        if code.startswith('HK'):
            hk_code = code[2:].lstrip('0') or '0'  # Remove leading0, But retain at least one0
            hk_code = hk_code.zfill(4)  # Pad to 4 digits.
            logger.debug(f"转换港股代码: {stock_code} -> {hk_code}.HK")
            return f"{hk_code}.HK"

        # Case with suffix already included
        if '.SS' in code or '.SZ' in code or '.HK' in code or '.BJ' in code:
            return code

        # Remove possible '.SH' suffix
        code = code.replace('.SH', '')

        # ETF: Shanghai ETF (51xx, 52xx, 56xx, 58xx) -> .SS; Shenzhen ETF (15xx, 16xx, 18xx) -> .SZ
        if len(code) == 6:
            if code.startswith(('51', '52', '56', '58')):
                return f"{code}.SS"
            if code.startswith(('15', '16', '18')):
                return f"{code}.SZ"

        # BSE (Beijing Stock Exchange): 8xxxxx, 4xxxxx, 920xxx
        if is_bse_code(code):
            base = code.split('.')[0] if '.' in code else code
            return f"{base}.BJ"

        # A-shares: Determine the market based on code prefix
        if code.startswith(('600', '601', '603', '688')):
            return f"{code}.SS"
        elif code.startswith(('000', '002', '300')):
            return f"{code}.SZ"
        else:
            logger.warning(f"无法确定股票 {code} 的市场，默认使用深市")
            return f"{code}.SZ"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=safe_before_sleep_log(
            logger,
            logging.WARNING,
            event="Yfinance daily data retry scheduled",
            error_code="yfinance_daily_data_retry",
        ),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Get raw data from Yahoo Finance

        Use yfinance.download() to get historical data

        Process:
        1. Convert stock code format
        2. Call yfinance API
        3. Process returned data
        """
        import yfinance as yf

        # Convert Code Format
        yf_code = self._convert_stock_code(stock_code)

        logger.debug(f"调用 yfinance.download({yf_code}, {start_date}, {end_date})")

        try:
            # Use yfinance to download data
            df = yf.download(
                tickers=yf_code,
                start=start_date,
                end=end_date,
                progress=False,  # Disable progress bar
                auto_adjust=True,  # Automatically adjust price (reprice)
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

        except Exception as e:
            if isinstance(e, DataFetchError):
                raise
            raise DataFetchError(f"Yahoo Finance 获取数据失败: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        Standardize Yahoo Finance data

        yfinance column names:
        Open, High, Low, Close, Volume(Index is date)

        Note: The new yfinance returns MultiIndex column names, such as ('Close', 'AMD').
        Need to flatten column names first before processing

        Map to standard column names:
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

        # Calculate Volume (yfinance does not provide, using an estimated trading value)
        # trading value ≈ Volume * Average Price
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

    def _fetch_yf_ticker_data(self, yf, yf_code: str, name: str, return_code: str) -> Optional[Dict[str, Any]]:
        """
        Fetch stock/index data using yfinance.

        Args:
            yf: yfinance module reference
            yf_code: yfinance Used code(If '000001.SS', '^GSPC')
            name: Index Display Name
            return_code: code field of the written result dict (such as 'sh000001', 'SPX')

        Returns:
            Market dictionary, returns None on failure.
        """
        ticker = yf.Ticker(yf_code)
        # Retrieve data from the last two days to calculate percentage change.
        hist = ticker.history(period='2d')
        if hist.empty:
            return None
        today_row = hist.iloc[-1]
        prev_row = hist.iloc[-2] if len(hist) > 1 else today_row
        price = float(today_row['Close'])
        prev_close = float(prev_row['Close'])
        change = price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0
        high = float(today_row['High'])
        low = float(today_row['Low'])
        # Amplitude = (High - Low) / Previous Close * 100
        amplitude = ((high - low) / prev_close * 100) if prev_close else 0
        return {
            'code': return_code,
            'name': name,
            'current': price,
            'change': change,
            'change_pct': change_pct,
            'open': float(today_row['Open']),
            'high': high,
            'low': low,
            'prev_close': prev_close,
            'volume': float(today_row['Volume']),
            'amount': 0.0,  # Yahoo Finance does not provide accurate trading value
            'amplitude': amplitude,
        }

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        Get quote data for key indices (Yahoo Finance), supports A-shares, U.S. stocks, Hong Kong stocks, Japanese stocks, Korean stocks and Taiwanese stocks.
        region=us Delegate To _get_us_main_indices.
        region=hk Delegate To _get_hk_main_indices.
        region=jp/kr/tw Delegate to Corresponding Market Index Method.
        """
        import yfinance as yf

        if region == "us":
            return self._get_us_main_indices(yf)
        if region == "hk":
            return self._get_hk_main_indices(yf)
        if region == "jp":
            return self._get_jp_main_indices(yf)
        if region == "kr":
            return self._get_kr_main_indices(yf)
        if region == "tw":
            return self._get_tw_main_indices(yf)

        # A-shares index: akshare code -> (yfinance code, display name)
        yf_mapping = {
            'sh000001': ('000001.SS', '上证指数'),
            'sz399001': ('399001.SZ', '深证成指'),
            'sz399006': ('399006.SZ', '创业板指'),
            'sh000688': ('000688.SS', '科创50'),
            'sh000016': ('000016.SS', '上证50'),
            'sh000300': ('000300.SS', '沪深300'),
        }

        results = []
        try:
            for ak_code, (yf_code, name) in yf_mapping.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_code, name, ak_code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 获取指数 {name} 成功")
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Yfinance index quote failed",
                        e,
                        error_code="yfinance_index_quote_failed",
                        level=logging.WARNING,
                        context={"market": "cn", "index_code": ak_code, "symbol": yf_code},
                    )

            if results:
                logger.info(f"[Yfinance] 成功获取 {len(results)} 个 A 股指数行情")
                return results

        except Exception as e:
            log_safe_exception(
                logger,
                "Yfinance market indices fetch failed",
                e,
                error_code="yfinance_market_indices_failed",
                level=logging.ERROR,
                context={"market": "cn"},
            )

        return None

    def _get_us_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """Get major indices of U.S. stock market data(SPX, IXIC, DJI, VIX), Reusability _fetch_yf_ticker_data"""
        # Core U.S. Stock Indices Required for Main Market Review
        us_indices = ['SPX', 'IXIC', 'DJI', 'VIX']
        results = []
        try:
            for code in us_indices:
                yf_symbol, name = get_us_index_yf_symbol(code)
                if not yf_symbol:
                    continue
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 获取美股指数 {name} 成功")
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Yfinance index quote failed",
                        e,
                        error_code="yfinance_index_quote_failed",
                        level=logging.WARNING,
                        context={"market": "us", "index_code": code, "symbol": yf_symbol},
                    )

            if results:
                logger.info(f"[Yfinance] 成功获取 {len(results)} 个美股指数行情")
                return results

        except Exception as e:
            log_safe_exception(
                logger,
                "Yfinance market indices fetch failed",
                e,
                error_code="yfinance_market_indices_failed",
                level=logging.ERROR,
                context={"market": "us"},
            )

        return None

    def _get_hk_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """Get Hong Kong stock main index quotes (HSI, HSTECH, HSCEI), reuse _fetch_yf_ticker_data"""
        # Yahoo Finance Hong Kong Stock Index Symbol Mapping:
        # - HSI -> ^HSI
        # - HSTECH -> HSTECH.HK(False ^HSTECH)
        # - HSCEI -> ^HSCE(False ^HSCEI)
        # This mapping is hardcoded in offline unit tests tests/test_yfinance_hk_indices.py to avoid non-deterministic failure due to online dependencies.
        hk_indices = {
            'HSI': ('^HSI', '恒生指数'),
            'HSTECH': ('HSTECH.HK', '恒生科技指数'),
            'HSCEI': ('^HSCE', '国企指数'),
        }
        results = []
        try:
            for code, (yf_symbol, name) in hk_indices.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 获取港股指数 {name} 成功")
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Yfinance index quote failed",
                        e,
                        error_code="yfinance_index_quote_failed",
                        level=logging.WARNING,
                        context={"market": "hk", "index_code": code, "symbol": yf_symbol},
                    )

            if results:
                logger.info(f"[Yfinance] 成功获取 {len(results)} 个港股指数行情")
                return results

        except Exception as e:
            log_safe_exception(
                logger,
                "Yfinance market indices fetch failed",
                e,
                error_code="yfinance_market_indices_failed",
                level=logging.ERROR,
                context={"market": "hk"},
            )

        return None

    def _get_jp_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """Get Japanese major index market data (Nikkei 225, TOPIX), reuse _fetch_yf_ticker_data."""
        jp_indices = {
            'N225': ('^N225', '日经225'),
            'TOPX': ('^TOPX', '东证指数'),
        }
        results = []
        try:
            for code, (yf_symbol, name) in jp_indices.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 获取日本指数 {name} 成功")
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Yfinance index quote failed",
                        e,
                        error_code="yfinance_index_quote_failed",
                        level=logging.WARNING,
                        context={"market": "jp", "index_code": code, "symbol": yf_symbol},
                    )
            if results:
                logger.info(f"[Yfinance] 成功获取 {len(results)} 个日本指数行情")
                return results
        except Exception as e:
            log_safe_exception(
                logger,
                "Yfinance market indices fetch failed",
                e,
                error_code="yfinance_market_indices_failed",
                level=logging.ERROR,
                context={"market": "jp"},
            )
        return None

    def _get_kr_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """Retrieve Korean major index data (KOSPI, KOSDAQ), reusing _fetch_yf_ticker_data."""
        kr_indices = {
            'KS11': ('^KS11', 'KOSPI'),
            'KQ11': ('^KQ11', 'KOSDAQ'),
        }
        results = []
        try:
            for code, (yf_symbol, name) in kr_indices.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 获取韩国指数 {name} 成功")
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Yfinance index quote failed",
                        e,
                        error_code="yfinance_index_quote_failed",
                        level=logging.WARNING,
                        context={"market": "kr", "index_code": code, "symbol": yf_symbol},
                    )
            if results:
                logger.info(f"[Yfinance] 成功获取 {len(results)} 个韩国指数行情")
                return results
        except Exception as e:
            log_safe_exception(
                logger,
                "Yfinance market indices fetch failed",
                e,
                error_code="yfinance_market_indices_failed",
                level=logging.ERROR,
                context={"market": "kr"},
            )
        return None

    def _get_tw_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """Get Taiwan's major index quotes (weighted index ^TWII, cash market index ^TWOII), reuse _fetch_yf_ticker_data."""
        tw_indices = {
            'TWII': ('^TWII', '台湾加权指数'),
            'TWOII': ('^TWOII', '台湾柜买指数'),
        }
        results = []
        try:
            for code, (yf_symbol, name) in tw_indices.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug(f"[Yfinance] 获取台湾指数 {name} 成功")
                except Exception as e:
                    log_safe_exception(
                        logger,
                        "Yfinance index quote failed",
                        e,
                        error_code="yfinance_index_quote_failed",
                        level=logging.WARNING,
                        context={"market": "tw", "index_code": code, "symbol": yf_symbol},
                    )
            if results:
                logger.info(f"[Yfinance] 成功获取 {len(results)} 个台湾指数行情")
                return results
        except Exception as e:
            log_safe_exception(
                logger,
                "Yfinance market indices fetch failed",
                e,
                error_code="yfinance_market_indices_failed",
                level=logging.ERROR,
                context={"market": "tw"},
            )
        return None

    def _is_us_stock(self, stock_code: str) -> bool:
        """
        Determine if the code is a U.S. stock (excluding U.S. indices).

        Delegate the is_us_stock_code() function to the us_index_mapping module.
        """
        return is_us_stock_code(stock_code)

    def _get_us_stock_quote_from_stooq(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        Use Stooq as a keyless fallback for real-time U.S. stock quotes.

        Stooq provides the latest daily trading data, with lower accuracy than real-time tick data; however, it works in Yahoo / yfinance
        When rate-limited, provide usable price for the Web UI; if yesterday's closing price can be obtained, also provide derived indicators such as percentage change.
        """
        symbol = stock_code.strip().upper()
        stooq_symbol = f"{symbol.lower()}.us"
        url = f"https://stooq.com/q/l/?s={stooq_symbol}"
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; StockPulse/1.0; +https://github.com/SiinXu/stock-pulse-ai)",
                "Accept": "text/plain,text/csv,*/*",
            },
        )

        try:
            with urlopen(request, timeout=15) as response:
                payload = response.read().decode("utf-8", "ignore").strip()
        except (HTTPError, URLError, TimeoutError) as exc:
            log_safe_exception(
                logger,
                "Stooq realtime quote request failed",
                exc,
                error_code="stooq_realtime_quote_request_failed",
                level=logging.WARNING,
                context={"symbol": symbol},
            )
            return None

        if not payload or payload.upper().startswith("NO DATA"):
            logger.warning(f"[Stooq] 无法获取 {symbol} 的行情数据")
            return None

        def _fetch_prev_close() -> Optional[float]:
            history_url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
            history_request = Request(
                history_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; StockPulse/1.0; +https://github.com/SiinXu/stock-pulse-ai)",
                    "Accept": "text/plain,text/csv,*/*",
                },
            )
            try:
                with urlopen(history_request, timeout=15) as response:
                    history_payload = response.read().decode("utf-8", "ignore").strip()
            except (HTTPError, URLError, TimeoutError) as exc:
                log_safe_exception(
                    logger,
                    "Stooq daily history request failed",
                    exc,
                    error_code="stooq_daily_history_request_failed",
                    level=logging.DEBUG,
                    context={"symbol": symbol},
                )
                return None

            if not history_payload or history_payload.upper().startswith("NO DATA"):
                return None

            try:
                reader = csv.reader(StringIO(history_payload))
                header = next(reader, None)
                if not header:
                    return None

                header_tokens = [cell.strip().lower() for cell in header]
                has_header = "close" in header_tokens and "date" in header_tokens
                if not has_header:
                    return None

                date_index = header_tokens.index("date")
                close_index = header_tokens.index("close")

                daily_rows: list[tuple[datetime, float]] = []
                for row in reader:
                    if not row:
                        continue
                    date_text = row[date_index].strip() if len(row) > date_index else ""
                    close_text = row[close_index].strip() if len(row) > close_index else ""
                    if not date_text or not close_text:
                        continue
                    try:
                        dt = datetime.strptime(date_text, "%Y-%m-%d")
                        close_val = float(close_text)
                    except Exception:
                        continue
                    daily_rows.append((dt, close_val))

                if len(daily_rows) < 2:
                    return None

                daily_rows.sort(key=lambda item: item[0])
                return daily_rows[-2][1]
            except Exception:
                return None

        try:
            reader = csv.reader(StringIO(payload))
            first_row = next(reader, None)
            if first_row is None:
                raise ValueError(f"unexpected Stooq payload: {payload}")

            normalized_first_row = [cell.strip() for cell in first_row]
            header_tokens = {cell.lower() for cell in normalized_first_row if cell}
            has_header = 'open' in header_tokens and 'close' in header_tokens
            row = next(reader, None) if has_header else first_row
            if row is None:
                raise ValueError(f"unexpected Stooq payload: {payload}")

            normalized_row = [cell.strip() for cell in row]
            while normalized_row and normalized_row[-1] == '':
                normalized_row.pop()

            if len(normalized_row) >= 8:
                open_index, high_index, low_index, price_index, volume_index = 3, 4, 5, 6, 7
            elif len(normalized_row) >= 7:
                open_index, high_index, low_index, price_index, volume_index = 2, 3, 4, 5, 6
            else:
                raise ValueError(f"unexpected Stooq payload: {payload}")

            open_price = float(normalized_row[open_index])
            high = float(normalized_row[high_index])
            low = float(normalized_row[low_index])
            price = float(normalized_row[price_index])
            volume = int(float(normalized_row[volume_index]))

            prev_close = _fetch_prev_close()
            change_amount = None
            change_pct = None
            amplitude = None
            if prev_close is not None and prev_close > 0:
                change_amount = price - prev_close
                change_pct = (change_amount / prev_close) * 100
                amplitude = ((high - low) / prev_close) * 100

            quote = UnifiedRealtimeQuote(
                code=symbol,
                name=STOCK_NAME_MAP.get(symbol, ''),
                source=RealtimeSource.STOOQ,
                price=price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=volume,
                amount=None,
                volume_ratio=None,
                turnover_rate=None,
                amplitude=round(amplitude, 2) if amplitude is not None else None,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=prev_close,
                pe_ratio=None,
                pb_ratio=None,
                total_mv=None,
                circ_mv=None,
            )
            logger.info(f"[Stooq] 获取美股 {symbol} 兜底行情成功: 价格={price}")
            return quote
        except Exception as exc:
            log_safe_exception(
                logger,
                "Stooq realtime quote parsing failed",
                exc,
                error_code="stooq_realtime_quote_parsing_failed",
                level=logging.WARNING,
                context={"symbol": symbol},
            )
            return None

    def _get_us_index_realtime_quote(
        self,
        user_code: str,
        yf_symbol: str,
        index_name: str,
    ) -> Optional[UnifiedRealtimeQuote]:
        """
        Get realtime quote for US index (e.g. SPX -> ^GSPC).

        Args:
            user_code: User input code (e.g. SPX)
            yf_symbol: Yahoo Finance symbol (e.g. ^GSPC)
            index_name: Chinese name for the index

        Returns:
            UnifiedRealtimeQuote or None
        """
        import yfinance as yf

        try:
            logger.debug(f"[Yfinance] 获取美股指数 {user_code} ({yf_symbol}) 实时行情")
            ticker = yf.Ticker(yf_symbol)

            try:
                info = ticker.fast_info
                if info is None:
                    raise ValueError("fast_info is None")
                price = getattr(info, 'lastPrice', None) or getattr(info, 'last_price', None)
                prev_close = getattr(info, 'previousClose', None) or getattr(info, 'previous_close', None)
                open_price = getattr(info, 'open', None)
                high = getattr(info, 'dayHigh', None) or getattr(info, 'day_high', None)
                low = getattr(info, 'dayLow', None) or getattr(info, 'day_low', None)
                volume = getattr(info, 'lastVolume', None) or getattr(info, 'last_volume', None)
            except Exception:
                logger.debug("[Yfinance] fast_info 失败，尝试 history 方法")
                hist = ticker.history(period='2d')
                if hist.empty:
                    logger.warning(f"[Yfinance] 无法获取 {yf_symbol} 的数据")
                    return None
                today = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else today
                price = float(today['Close'])
                prev_close = float(prev['Close'])
                open_price = float(today['Open'])
                high = float(today['High'])
                low = float(today['Low'])
                volume = int(today['Volume'])

            change_amount = None
            change_pct = None
            if price is not None and prev_close is not None and prev_close > 0:
                change_amount = price - prev_close
                change_pct = (change_amount / prev_close) * 100

            amplitude = None
            if high is not None and low is not None and prev_close is not None and prev_close > 0:
                amplitude = ((high - low) / prev_close) * 100

            try:
                ticker_info = ticker.info or {}
            except Exception:
                ticker_info = {}
            missing_fields = [
                field
                for field, value in {
                    "price": price,
                    "prev_close": prev_close,
                    "volume": volume,
                    "amount": None,
                    "pe_ratio": None,
                    "pb_ratio": None,
                }.items()
                if value is None
            ]

            quote = UnifiedRealtimeQuote(
                code=user_code,
                name=index_name or user_code,
                source=RealtimeSource.FALLBACK,
                market="us",
                currency=str(ticker_info.get("currency") or "").upper() or None,
                data_quality="partial" if missing_fields else "ok",
                missing_fields=missing_fields or None,
                price=price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=volume,
                amount=None,
                volume_ratio=None,
                turnover_rate=None,
                amplitude=round(amplitude, 2) if amplitude is not None else None,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=prev_close,
                pe_ratio=None,
                pb_ratio=None,
                total_mv=None,
                circ_mv=None,
            )
            logger.info(f"[Yfinance] 获取美股指数 {user_code} 实时行情成功: 价格={price}")
            return quote
        except Exception as e:
            log_safe_exception(
                logger,
                "Yfinance US index realtime quote failed",
                e,
                error_code="yfinance_us_index_realtime_quote_failed",
                level=logging.WARNING,
                context={"index_code": user_code, "symbol": yf_symbol},
            )
            return None

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        Get U.S. stocks/Real-time market data for U.S. stocks

        Supports US stocks (AAPL, TSLA) and US stock indices (SPX, DJI, etc.).
        Data source: yfinance Ticker.info

        Args:
            stock_code: U.S. stocks Code or Index Code, If 'AMD', 'AAPL', 'SPX', 'DJI'

        Returns:
            UnifiedRealtimeQuote object, or None on failure
        """
        import yfinance as yf

        # U.S. stocks indices: use mapping (SPX -> ^GSPC)
        yf_symbol, index_name = get_us_index_yf_symbol(stock_code)
        if yf_symbol:
            return self._get_us_index_realtime_quote(
                user_code=stock_code.strip().upper(),
                yf_symbol=yf_symbol,
                index_name=index_name,
            )

        # Handles US stocks or JP/KR/TW suffix-only stocks
        if not (
            self._is_us_stock(stock_code)
            or self._is_jp_kr_suffix_stock(stock_code)
            or self._is_tw_suffix_stock(stock_code)
        ):
            logger.debug(f"[Yfinance] {stock_code} 不是美股或日韩 suffix 代码，跳过")
            return None

        try:
            symbol = self._convert_stock_code(stock_code)
            is_us_symbol = self._is_us_stock(symbol)
            suffix_market = get_suffix_market(symbol)
            logger.debug(f"[Yfinance] 获取 {symbol} 实时行情")

            ticker = yf.Ticker(symbol)

            # Attempt to fetch fast_info (faster, but fewer fields)
            try:
                info = ticker.fast_info
                if info is None:
                    raise ValueError("fast_info is None")

                price = getattr(info, 'lastPrice', None) or getattr(info, 'last_price', None)
                prev_close = getattr(info, 'previousClose', None) or getattr(info, 'previous_close', None)
                open_price = getattr(info, 'open', None)
                high = getattr(info, 'dayHigh', None) or getattr(info, 'day_high', None)
                low = getattr(info, 'dayLow', None) or getattr(info, 'day_low', None)
                volume = getattr(info, 'lastVolume', None) or getattr(info, 'last_volume', None)
                market_cap = getattr(info, 'marketCap', None) or getattr(info, 'market_cap', None)

            except Exception:
                # Fallback to the history method to get the latest data
                logger.debug("[Yfinance] fast_info 失败，尝试 history 方法")
                hist = ticker.history(period='2d')
                if hist.empty:
                    if is_us_symbol:
                        logger.warning(f"[Yfinance] 无法获取 {symbol} 的数据，尝试 Stooq 兜底")
                        return self._get_us_stock_quote_from_stooq(symbol)
                    logger.warning(f"[Yfinance] 无法获取 {symbol} 的数据")
                    return None

                today = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else today

                price = float(today['Close'])
                prev_close = float(prev['Close'])
                open_price = float(today['Open'])
                high = float(today['High'])
                low = float(today['Low'])
                volume = int(today['Volume'])
                market_cap = None

            # Calculate Percentage Change
            change_amount = None
            change_pct = None
            if price is not None and prev_close is not None and prev_close > 0:
                change_amount = price - prev_close
                change_pct = (change_amount / prev_close) * 100

            # Calculate Amplitude
            amplitude = None
            if high is not None and low is not None and prev_close is not None and prev_close > 0:
                amplitude = ((high - low) / prev_close) * 100

            # Get stock name and provider metadata
            try:
                ticker_info = ticker.info or {}
            except Exception:
                ticker_info = {}
            try:
                info_name = ticker_info.get('shortName', '') or ticker_info.get('longName', '') or ''
                name = info_name if is_meaningful_stock_name(info_name, symbol) else STOCK_NAME_MAP.get(symbol, '')
            except Exception:
                name = STOCK_NAME_MAP.get(symbol, '')

            # Reuse the ticker_info fetched above for valuation; no extra request.
            # Imported locally (module still has no module-level dependency on the
            # fundamental adapter) to keep the module import block unchanged.
            from .yfinance_fundamental_adapter import _safe_float
            pe_ratio = _safe_float(ticker_info.get('trailingPE'))
            pb_ratio = _safe_float(ticker_info.get('priceToBook'))

            missing_fields = [
                field
                for field, value in {
                    "price": price,
                    "prev_close": prev_close,
                    "volume": volume,
                    "amount": None,
                    "pe_ratio": pe_ratio,
                    "pb_ratio": pb_ratio,
                }.items()
                if value is None
            ]
            quote = UnifiedRealtimeQuote(
                code=symbol,
                name=name,
                source=RealtimeSource.FALLBACK,
                market=suffix_market or ("us" if is_us_symbol else None),
                currency=str(ticker_info.get("currency") or "").upper() or None,
                data_quality="partial" if missing_fields else "ok",
                missing_fields=missing_fields or None,
                price=price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=volume,
                amount=None,  # yfinance does not directly provide trading value
                volume_ratio=None,
                turnover_rate=None,
                amplitude=round(amplitude, 2) if amplitude is not None else None,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=prev_close,
                pe_ratio=pe_ratio,
                pb_ratio=pb_ratio,
                total_mv=market_cap,
                circ_mv=None,
            )

            logger.info(f"[Yfinance] 获取 {symbol} 实时行情成功: 价格={price}")
            return quote

        except Exception as e:  # broad-exception: fallback_recorded - failure is logged, then degraded to Stooq (US) or None
            is_us = self._is_us_stock(stock_code)
            log_safe_exception(
                logger,
                "Yfinance US realtime quote failed; trying Stooq fallback"
                if is_us
                else "Yfinance realtime quote failed",
                e,
                error_code="yfinance_us_realtime_quote_failed"
                if is_us
                else "yfinance_realtime_quote_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
            if is_us:
                return self._get_us_stock_quote_from_stooq(stock_code)
            return None


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.DEBUG)

    fetcher = YfinanceFetcher()

    try:
        df = fetcher.get_daily_data('600519')  # Maotai
        print(f"获取成功，共 {len(df)} 条数据")
        print(df.tail())
    except Exception as e:
        print(f"获取失败: {e}")
