# -*- coding: utf-8 -*-
"""
===================================
YfinanceFetcher - 兜底数据源 (Priority 4)
===================================

数据来源：Yahoo Finance（通过 yfinance 库）
特点：国际数据源、可能有延迟或缺失
定位：当所有国内数据源都失败时的最后保障

关键策略：
1. 自动将 A 股代码转换为 yfinance 格式（.SS / .SZ）
2. 处理 Yahoo Finance 的数据格式差异
3. 失败后指数退避重试
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
from src.security.outbound_policy import OutboundPolicyError, guard_outbound_urls
from src.services.market_symbol_utils import get_suffix_market, is_suffix_market_symbol
from src.utils.sanitize import log_safe_exception, safe_before_sleep_log

# Optional local stock mapping patch can be imported, if missing, use empty dictionary as fallback.
try:
    from src.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name
except (ImportError, ModuleNotFoundError):
    STOCK_NAME_MAP = {}

    def is_meaningful_stock_name(name: str | None, stock_code: str) -> bool:
        """简单的名称有效性校验兜底"""
        if not name:
            return False
        n = str(name).strip()
        return bool(n and n.upper() != str(stock_code).strip().upper())

import os

logger = logging.getLogger(__name__)

# Hosts owned by the yfinance SDK and the Stooq urllib fallback. LOCAL_ONLY_MODE
# rejects these at guard entry; strict_dns is off so extra Yahoo CDN hosts used
# when the flag is off do not become unexpected-target failures.
_YFINANCE_OUTBOUND_URLS = (
    "https://query1.finance.yahoo.com/",
    "https://query2.finance.yahoo.com/",
    "https://stooq.com/",
)


def _yfinance_http_guard():
    return guard_outbound_urls(_YFINANCE_OUTBOUND_URLS, strict_dns=False)


class YfinanceFetcher(BaseFetcher):
    """
    Yahoo Finance 数据源实现

    优先级：4（最低，作为兜底）
    数据来源：Yahoo Finance

    关键策略：
    - 自动转换股票代码格式
    - 处理时区和数据格式差异
    - 失败后指数退避重试

    注意事项：
    - A 股数据可能有延迟
    - 某些股票可能无数据
    - 数据精度可能与国内源略有差异
    """

    name = "YfinanceFetcher"
    priority = int(os.getenv("YFINANCE_PRIORITY", "4"))

    def __init__(self):
        """初始化 YfinanceFetcher"""
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
        转换股票代码为 Yahoo Finance 格式

        Yahoo Finance 代码格式：
        - A股沪市：600519.SS (Shanghai Stock Exchange)
        - A股深市：000001.SZ (Shenzhen Stock Exchange)
        - 港股：0700.HK (Hong Kong Stock Exchange)
        - 美股：AAPL, TSLA, GOOGL (无需后缀)

        Args:
            stock_code: 原始代码，如 '600519', 'hk00700', 'AAPL'

        Returns:
            Yahoo Finance 格式代码

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

        # Bare Hong Kong codes use four or five digits. A-share and BSE codes
        # are six digits, so this branch cannot shadow their market routing.
        if code.isdigit() and 4 <= len(code) <= 5:
            hk_code = (code.lstrip('0') or '0').zfill(4)
            logger.debug(f"识别裸港股代码: {stock_code} -> {hk_code}.HK")
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

    # Rebound from yfinance_parts.history after the class is built.
    _fetch_raw_data = None

    _normalize_data = None

    # Rebound from yfinance_parts.main_indices after the class is built.
    _fetch_yf_ticker_data = None

    get_main_indices = None

    _get_us_main_indices = None

    _get_hk_main_indices = None

    _get_jp_main_indices = None

    _get_kr_main_indices = None

    _get_tw_main_indices = None

    def _is_us_stock(self, stock_code: str) -> bool:
        """
        判断代码是否为美股股票（排除美股指数）。

        委托给 us_index_mapping 模块的 is_us_stock_code()。
        """
        return is_us_stock_code(stock_code)

    # Rebound from yfinance_parts.realtime after the class is built.
    _get_us_stock_quote_from_stooq = None

    _get_us_index_realtime_quote = None

    get_realtime_quote = None


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.DEBUG)

    fetcher = YfinanceFetcher()

    try:
        df = fetcher.get_daily_data('600519')  # Maotai
        print(f"获取成功，共 {len(df)} 条数据")
        print(df.tail())
    except Exception as e:  # broad-exception: optional_metadata - demo CLI prints failure and exits the snippet.
        print(f"获取失败: {e}")


# Keep ``src.data_provider.yfinance_fetcher.YfinanceFetcher`` as the ADR-006
# compatibility facade while ``yfinance_parts`` owns main-index, realtime,
# and daily history bodies.
# Rebinding preserves method globals so existing patches against this module
# continue to intercept moved implementations.
from .yfinance_parts import history as _history_module  # noqa: E402
from .yfinance_parts import main_indices as _main_indices_module  # noqa: E402
from .yfinance_parts import realtime as _realtime_module  # noqa: E402
from .yfinance_parts.history import _HistoryMethods  # noqa: E402
from .yfinance_parts.main_indices import _MainIndicesMethods  # noqa: E402
from .yfinance_parts.realtime import _RealtimeMethods  # noqa: E402
from .yfinance_parts.facade_bind import bind_methods_from_class  # noqa: E402


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
            event="Yfinance daily data retry scheduled",
            error_code="yfinance_daily_data_retry",
        ),
    )(bound)


def _assemble_yfinance_fetcher_facade() -> None:
    """Bind capability-domain method bodies onto the public fetcher class."""

    global _HistoryMethods, _MainIndicesMethods, _RealtimeMethods
    _HistoryMethods = _history_module._HistoryMethods
    _MainIndicesMethods = _main_indices_module._MainIndicesMethods
    _RealtimeMethods = _realtime_module._RealtimeMethods
    bind_methods_from_class(
        _HistoryMethods,
        YfinanceFetcher,
        globals(),
        expected_names=_history_module.EXPECTED_HISTORY_METHOD_NAMES,
        post_bind=_apply_history_retry,
    )
    bind_methods_from_class(
        _MainIndicesMethods,
        YfinanceFetcher,
        globals(),
        expected_names=_main_indices_module.EXPECTED_MAIN_INDEX_METHOD_NAMES,
    )
    bind_methods_from_class(
        _RealtimeMethods,
        YfinanceFetcher,
        globals(),
        expected_names=_realtime_module.EXPECTED_REALTIME_METHOD_NAMES,
    )
    # Rebound methods are assigned after class body evaluation; clear ABC
    # abstracts that are now implemented so instantiation matches the legacy
    # monofile class (BaseFetcher marks _fetch_raw_data / _normalize_data).
    abstracts = set(getattr(YfinanceFetcher, "__abstractmethods__", ()))
    if abstracts:
        abstracts.difference_update(
            {
                name
                for name in (
                    "_fetch_raw_data",
                    "_normalize_data",
                    "get_daily_data",
                )
                if callable(getattr(YfinanceFetcher, name, None))
            }
        )
        abstracts = {
            name
            for name in abstracts
            if name not in YfinanceFetcher.__dict__
            or getattr(YfinanceFetcher.__dict__[name], "__isabstractmethod__", False)
        }
        YfinanceFetcher.__abstractmethods__ = frozenset(abstracts)


_assemble_yfinance_fetcher_facade()


def _install_part_reload_hooks() -> None:
    """Keep an owner reload able to rebuild and rebind every owner module."""

    for module in (_history_module, _main_indices_module, _realtime_module):
        module._FACADE_RELOAD_HOOK = _assemble_yfinance_fetcher_facade  # type: ignore[attr-defined]


_install_part_reload_hooks()
