# -*- coding: utf-8 -*-
"""
===================================
TushareFetcher - 备用数据源 1 (Priority 2)
===================================

Compatibility facade for the Tushare provider (ADR-006 / Issue #1068).

Data source: Tushare Pro API (dig-the-rabbit)
Requires a token and enforces a per-minute request quota.

Implementation ownership lives under ``data_provider.tushare_parts`` by
capability domain (client, symbols, history). This module remains the
stable import and monkeypatch surface so provider registration, tests,
fixture scripts, and diagnostics keep working without behavior changes.

流控策略：
1. 实现"每分钟调用计数器"
2. 超过免费配额（80次/分）时，强制休眠到下一分钟
3. 使用 tenacity 实现指数退避重试
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
from src.security.outbound_policy import safe_post
from src.utils.sanitize import log_safe_exception, safe_before_sleep_log
import os
from zoneinfo import ZoneInfo

from .tushare_parts import client as _client_module
from .tushare_parts import history as _history_module
from .tushare_parts import symbols as _symbols_module
from .tushare_parts.client import (
    _ClientMethods,
    _TUSHARE_DEFAULT_API_URL,
    _TushareHttpClient,
    _resolve_tushare_api_url,
)
from .tushare_parts.facade_bind import (
    _clone_facade_descriptor,
    bind_methods_from_class,
)
from .tushare_parts.history import _HistoryMethods
from .tushare_parts.symbols import (
    _ETF_ALL_PREFIXES,
    _ETF_SH_PREFIXES,
    _ETF_SZ_PREFIXES,
    _SymbolMethods,
    _is_etf_code,
    _is_us_code,
)

logger = logging.getLogger(__name__)


class TushareFetcher(BaseFetcher):
    """
    Tushare Pro 数据源实现
    
    优先级：2
    数据来源：Tushare Pro API
    
    关键策略：
    - 每分钟调用计数器，防止超出配额
    - 超过 80 次/分钟时强制等待
    - 失败后指数退避重试
    
    配额说明（Tushare 免费用户）：
    - 每分钟最多 80 次请求
    - 每天最多 500 次请求
    """
    
    name = "TushareFetcher"
    priority = int(os.getenv("TUSHARE_PRIORITY", "2"))  # Default priority, dynamically adjusted in __init__ based on configuration

    def __init__(self, rate_limit_per_minute: int = 80):
        """
        初始化 TushareFetcher

        Args:
            rate_limit_per_minute: 每分钟最大请求数（默认80，Tushare免费配额）
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

    def _determine_priority(self) -> int:
        """
        根据 Token 配置和 API 初始化状态确定优先级

        策略：
        - Token 配置且 API 初始化成功：优先级 -1（绝对最高，优于 efinance）
        - 其他情况：优先级 2（默认）

        Returns:
            优先级数字（0=最高，数字越大优先级越低）
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
        检查数据源是否可用

        Returns:
            True 表示可用，False 表示不可用
        """
        return self._api is not None

    def _get_china_now(self) -> datetime:
        """返回上海时区当前时间，方便测试覆盖跨日刷新逻辑。"""
        return datetime.now(ZoneInfo("Asia/Shanghai"))

    def _get_trade_dates(self, end_date: Optional[str] = None) -> List[str]:
        """按自然日刷新交易日历缓存，避免服务跨日后继续复用旧日历。"""
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
        """根据可用交易日列表选择当天或前一交易日。"""
        if not trade_dates:
            return None
        if use_today or len(trade_dates) == 1:
            return trade_dates[0]
        return trade_dates[1]

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

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        获取股票名称
        
        使用 Tushare 的 stock_basic 接口获取股票基本信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票名称，失败返回 None
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
        获取股票列表
        
        使用 Tushare 的 stock_basic 接口获取 A 股列表（不含港股）。
        
        Returns:
            包含 code, name, industry, area, market 列的 DataFrame，失败返回 None
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
        获取实时行情

        策略：
        1. 优先尝试 Pro 接口（需要2000积分）：数据全，稳定性高
        2. 失败降级到旧版接口：门槛低，数据较少

        Args:
            stock_code: 股票代码

        Returns:
            UnifiedRealtimeQuote 对象，失败返回 None
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
        获取主要指数实时行情 (Tushare Pro)，仅支持 A 股
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
        获取市场涨跌统计 (Tushare Pro)
        2000积分 每天访问该接口 ts.pro_api().rt_k 两次
        接口限制见：https://tushare.pro/document/1?doc_id=108
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
            """从行情 DataFrame 计算涨跌统计。"""
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
        获取当前时间可以获得数据的开始时间日期

        Args:
                early_time: 默认 '09:30'
                late_time: 默认 '16:30'
                early_time-late_time 之间为使用上一个交易日数据的时间段，其他时间为使用当天数据的时间段
        Returns:
                start_date: 可以获得数据的开始日期
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
        获取行业板块涨跌榜 (Tushare Pro)
        
        数据源优先级：
        1. 同花顺接口 (ts.pro_api().moneyflow_ind_ths)
        2. 东财接口 (ts.pro_api().moneyflow_ind_dc)
        注意：每个接口的行业分类和板块定义不同，会导致结果两者不一致
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
        获取筹码分布数据
        
        数据来源：ts.pro_api().cyq_chips()
        包含：获利比例、平均成本、筹码集中度
        
        注意：ETF/指数没有筹码分布数据，会直接返回 None；港股不支持，直接返回 None。
        5000积分以下每天访问15次,每小时访问5次
        
        Args:
            stock_code: 股票代码
            
        Returns:
            ChipDistribution 对象（最新交易日的数据），获取失败返回 None

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
        基于 Tushare 的筹码分布明细表 (cyq_chips) 计算常用筹码指标  
        :param df: 包含 'price' 和 'percent' 列的 DataFrame  
        :param current_price: 股票当天的当前价/收盘价 (用于计算获利比例)  
        :return: 包含各项筹码指标的字典  
        """
        import numpy as np
        # 1. Sort by price in ascending order (Tushare data is often returned in descending order)
        df_sorted = df.sort_values(by='price', ascending=True).reset_index(drop=True)

        # 2. Prevent the sum of original data percent from generating floating-point errors, normalized to 100%.
        total_percent = df_sorted['percent'].sum()

        df_sorted['norm_percent'] = df_sorted['percent'] / total_percent * 100

        # 3. Calculate the cumulative chip distribution.
        df_sorted['cumsum'] = df_sorted['norm_percent'].cumsum()

        # --- Profit Ratio ---
        # Sum the chips whose prices are at or below the current price.
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



_EXPECTED_CLIENT_METHOD_NAMES = (
    "_init_api",
    "_build_api_client",
    "_check_rate_limit",
    "_call_api_with_rate_limit",
)

_EXPECTED_SYMBOL_METHOD_NAMES = (
    "_detect_exchange_hint",
    "_convert_stock_code",
    "_convert_hk_stock_code_for_tushare",
)

_EXPECTED_HISTORY_METHOD_NAMES = (
    "_fetch_raw_data",
    "_normalize_data",
)

_HTTP_CLIENT_METHOD_NAMES = (
    "__init__",
    "query",
    "__getattr__",
)


def _apply_history_retry(name: str, bound):
    """Re-apply the historical tenacity policy after facade cloning."""

    if name != "_fetch_raw_data":
        return bound
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=safe_before_sleep_log(
            logger,
            logging.WARNING,
            event="Tushare daily data retry scheduled",
            error_code="tushare_daily_data_retry",
        ),
    )(bound)


def _bind_http_client_facade() -> None:
    """Clone HTTP client methods so patches on this module intercept them."""

    global _TushareHttpClient
    _TushareHttpClient = _client_module._TushareHttpClient
    ns = globals()
    for name in _HTTP_CLIENT_METHOD_NAMES:
        descriptor = vars(_TushareHttpClient)[name]
        bound = _clone_facade_descriptor(
            descriptor,
            ns,
            owner_qualname=_TushareHttpClient.__qualname__,
        )
        setattr(_TushareHttpClient, name, bound)


def _assemble_tushare_fetcher_facade() -> None:
    """Bind capability-domain method bodies onto the public fetcher class."""

    global _ClientMethods, _HistoryMethods, _SymbolMethods
    _ClientMethods = _client_module._ClientMethods
    _SymbolMethods = _symbols_module._SymbolMethods
    _HistoryMethods = _history_module._HistoryMethods
    _bind_http_client_facade()
    bind_methods_from_class(
        _ClientMethods,
        TushareFetcher,
        globals(),
        expected_names=_EXPECTED_CLIENT_METHOD_NAMES,
    )
    bind_methods_from_class(
        _SymbolMethods,
        TushareFetcher,
        globals(),
        expected_names=_EXPECTED_SYMBOL_METHOD_NAMES,
    )
    bind_methods_from_class(
        _HistoryMethods,
        TushareFetcher,
        globals(),
        expected_names=_EXPECTED_HISTORY_METHOD_NAMES,
        post_bind=_apply_history_retry,
    )
    # Rebound methods are assigned after class body evaluation; clear ABC
    # abstracts that are now implemented so instantiation matches the legacy
    # monofile class (BaseFetcher marks _fetch_raw_data / _normalize_data).
    abstracts = set(getattr(TushareFetcher, "__abstractmethods__", ()))
    if abstracts:
        abstracts.difference_update(
            {
                name
                for name in (
                    "_fetch_raw_data",
                    "_normalize_data",
                    "get_daily_data",
                )
                if callable(getattr(TushareFetcher, name, None))
            }
        )
        abstracts = {
            name
            for name in abstracts
            if name not in TushareFetcher.__dict__
            or getattr(TushareFetcher.__dict__[name], "__isabstractmethod__", False)
        }
        TushareFetcher.__abstractmethods__ = frozenset(abstracts)


_assemble_tushare_fetcher_facade()


def _install_part_reload_hooks() -> None:
    for module in (
        _client_module,
        _symbols_module,
        _history_module,
    ):
        module._FACADE_RELOAD_HOOK = _assemble_tushare_fetcher_facade  # type: ignore[attr-defined]


_install_part_reload_hooks()


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
        
    except Exception as exc:  # broad-exception: fallback_recorded - Manual smoke failure is logged safely.
        logger.error(
            "Tushare manual daily-data check failed error_type=%s",
            type(exc).__name__,
        )

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
    except Exception as exc:  # broad-exception: fallback_recorded - Manual smoke failure is logged safely.
        logger.error(
            "Tushare manual market-stats check failed error_type=%s",
            type(exc).__name__,
        )


    # Test chip distribution data
    print("\n" + "=" * 50)
    print("测试筹码分布数据获取")
    print("=" * 50)
    try:
        chip = fetcher.get_chip_distribution('600519')  # Kweichow Moutai
    except Exception as exc:  # broad-exception: fallback_recorded - Manual smoke failure is logged safely.
        logger.error(
            "Tushare manual chip-distribution check failed error_type=%s",
            type(exc).__name__,
        )

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
    except Exception as exc:  # broad-exception: fallback_recorded - Manual smoke failure is logged safely.
        logger.error(
            "Tushare manual sector-ranking check failed error_type=%s",
            type(exc).__name__,
        )
