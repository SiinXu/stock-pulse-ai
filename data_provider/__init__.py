# -*- coding: utf-8 -*-
"""
===================================
Data source strategy layer - package initialization
===================================

This package implements strategy pattern management for multiple data sources, achieving:
1. Provide a unified data retrieval interface
2. Automatic failover
3. Anti-ban control strategy

Data source priority (dynamically adjusted):
[Configured TUSHARE_TOKEN Time]
1. TushareFetcher (Priority 0) - 🔥 Highest priority?(Dynamic scaling)
2. EfinanceFetcher (Priority 0) - Same priority
3. AkshareFetcher (Priority 1) - From? akshare library
4. PytdxFetcher (Priority 2) - from the pytdx library (Toutuantun)
5. BaostockFetcher (Priority 3) - From? baostock library
6. YfinanceFetcher (Priority 4) - From? yfinance library

[Not configured? TUSHARE_TOKEN Time]
1. EfinanceFetcher (Priority 0) - Highest priority, from the efinance library
2. AkshareFetcher (Priority 1) - From? akshare library
3. PytdxFetcher (Priority 2) - from the pytdx library (Toutuantun)
4. TushareFetcher (Priority 2) - From the tushare library (unavailable)
5. BaostockFetcher (Priority 3) - From? baostock library
6. YfinanceFetcher (Priority 4) - From? yfinance library
7. LongbridgeFetcher (Priority 5) - Longbridge OpenAPI (U.S./Hong Kong stocks fallback).

Tip: Lower priority numbers have higher priority; same priority is sorted by initialization order.
"""

from .base import BaseFetcher, DataFetcherManager
from .efinance_fetcher import EfinanceFetcher
from .tencent_fetcher import TencentFetcher
from .akshare_fetcher import AkshareFetcher, is_hk_stock_code
from .tushare_fetcher import TushareFetcher
from .pytdx_fetcher import PytdxFetcher
from .baostock_fetcher import BaostockFetcher
from .yfinance_fetcher import YfinanceFetcher
from .longbridge_fetcher import LongbridgeFetcher
from .finnhub_fetcher import FinnhubFetcher
from .alphavantage_fetcher import AlphaVantageFetcher
from .us_index_mapping import is_us_index_code, is_us_stock_code, get_us_index_yf_symbol, US_INDEX_MAPPING

__all__ = [
    'BaseFetcher',
    'DataFetcherManager',
    'EfinanceFetcher',
    'TencentFetcher',
    'AkshareFetcher',
    'TushareFetcher',
    'PytdxFetcher',
    'BaostockFetcher',
    'YfinanceFetcher',
    'LongbridgeFetcher',
    'FinnhubFetcher',
    'AlphaVantageFetcher',
    'is_us_index_code',
    'is_us_stock_code',
    'is_hk_stock_code',
    'get_us_index_yf_symbol',
    'US_INDEX_MAPPING',
]
