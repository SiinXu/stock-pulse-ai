# -*- coding: utf-8 -*-
"""
===================================
TushareFetcher - 备用数据源 1 (Priority 2)
===================================

Compatibility facade for the Tushare provider (ADR-006 / Issue #1068).

Data source: Tushare Pro API (dig-the-rabbit)
Requires a token and enforces a per-minute request quota.

Implementation ownership lives under ``data_provider.tushare_parts`` by
capability domain (client, symbols, history, stock_identity, market_boards,
realtime, trade_time). This module remains the stable import and monkeypatch surface so
provider registration, tests, fixture scripts, and diagnostics keep working
without behavior changes.

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
from .tushare_parts import stock_identity as _stock_identity_module
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
from .tushare_parts import market_boards as _market_boards_module
from .tushare_parts import realtime as _realtime_module
from .tushare_parts import trade_time as _trade_time_module
from .tushare_parts.history import _HistoryMethods
from .tushare_parts.market_boards import _MarketBoardsMethods
from .tushare_parts.realtime import _RealtimeMethods
from .tushare_parts.stock_identity import _StockIdentityMethods
from .tushare_parts.trade_time import _TradeTimeMethods
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

    # Rebound from tushare_parts.trade_time after the class is built.
    _get_china_now = None

    _get_trade_dates = None

    _pick_trade_date = None

    # Rebound from tushare_parts.realtime after the class is built.
    _get_legacy_realtime_symbol = None

    get_realtime_quote = None

    # Rebound from tushare_parts.market_boards after the class is built.
    get_main_indices = None

    get_market_stats = None
    
    _calc_market_stats = None

    # Rebound from tushare_parts.trade_time after the class is built.
    get_trade_time = None
    
    get_sector_rankings = None
    
    

    
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

_EXPECTED_STOCK_IDENTITY_METHOD_NAMES = (
    "get_stock_name",
    "get_stock_list",
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

    global _ClientMethods, _HistoryMethods, _RealtimeMethods, _StockIdentityMethods, _SymbolMethods, _TradeTimeMethods
    _ClientMethods = _client_module._ClientMethods
    _SymbolMethods = _symbols_module._SymbolMethods
    _HistoryMethods = _history_module._HistoryMethods
    _StockIdentityMethods = _stock_identity_module._StockIdentityMethods
    _RealtimeMethods = _realtime_module._RealtimeMethods
    _TradeTimeMethods = _trade_time_module._TradeTimeMethods
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
    bind_methods_from_class(
        _StockIdentityMethods,
        TushareFetcher,
        globals(),
        expected_names=_EXPECTED_STOCK_IDENTITY_METHOD_NAMES,
    )
    bind_methods_from_class(
        _MarketBoardsMethods,
        TushareFetcher,
        globals(),
        expected_names=_market_boards_module.EXPECTED_MARKET_BOARD_METHOD_NAMES,
    )
    bind_methods_from_class(
        _RealtimeMethods,
        TushareFetcher,
        globals(),
        expected_names=_realtime_module.EXPECTED_REALTIME_METHOD_NAMES,
    )
    bind_methods_from_class(
        _TradeTimeMethods,
        TushareFetcher,
        globals(),
        expected_names=_trade_time_module.EXPECTED_TRADE_TIME_METHOD_NAMES,
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
        _stock_identity_module,
        _market_boards_module,
        _realtime_module,
        _trade_time_module,
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
