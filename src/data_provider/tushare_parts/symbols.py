# -*- coding: utf-8 -*-
"""Tushare provider symbol / market classification helpers.

Pure helpers and ts_code conversion methods extracted from
``data_provider.tushare_fetcher`` (Issue #1068). External callers must keep
importing from ``data_provider.tushare_fetcher``.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from src.data_provider.base import DataFetchError, is_bse_code, normalize_stock_code, _is_hk_market

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``data_provider.tushare_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tushare_fetcher")

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


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
    判断代码是否为美股
    
    美股代码规则：
    - 1-5个大写字母，如 'AAPL', 'TSLA'
    - 可能包含 '.'，如 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


class _SymbolMethods:
    """Source descriptors rebound onto ``TushareFetcher``."""

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

    def _convert_stock_code(self, stock_code: str) -> str:
        """
        转换 A 股 / ETF / 北交所等为 Tushare ts_code（不含港股逻辑）。

        Tushare 要求的格式示例：
        - 沪市股票：600519.SH
        - 深市股票：000001.SZ
        - 沪市 ETF：510050.SH
        - 深市 ETF：159919.SZ

        Args:
            stock_code: 原始代码，如 '600519', '000001', '563230'

        Returns:
            Tushare 格式代码，如 '600519.SH', '000001.SZ'
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
            # raise DataFetchError(f"TushareFetcher 不支持港股 {raw_code}，请使用 AkshareFetcher")
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
        将用户输入转为 Tushare Pro 接口所需的 ts_code（含港股 nnnnn.HK）。

        - 非港股：委托 _convert_stock_code（A 股 / ETF / 北交所等）。
        - 港股：从 HK00700、00700、00700.HK 等形式归一为 5 位数字 + .HK。
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


def _rebind_loaded_facade() -> None:
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
