# -*- coding: utf-8 -*-
"""yfinance main-index methods: regional index quotes and the shared ticker fetch.

Method bodies are rebound onto ``YfinanceFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.yfinance_fetcher``. Mirrors the domain split of
``akshare_parts``, ``efinance_parts``, and ``tickflow_parts``.

The cluster is self-contained: the six regional/dispatch methods reach only
``_fetch_yf_ticker_data``, which travels with them. No module-level helper
moves; the rebind resolves free names from the facade globals at call time.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.yfinance_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.yfinance_fetcher")
_yfinance_http_guard = None  # type: ignore[assignment]
get_us_index_yf_symbol = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _MainIndicesMethods:
    """Source descriptors rebound onto ``YfinanceFetcher``."""

    def _fetch_yf_ticker_data(self, yf, yf_code: str, name: str, return_code: str) -> Optional[Dict[str, Any]]:
        """
        通过 yfinance 拉取单个指数/股票的行情数据。

        Args:
            yf: yfinance 模块引用
            yf_code: yfinance 使用的代码（如 '000001.SS'、'^GSPC'）
            name: 指数显示名称
            return_code: 写入结果 dict 的 code 字段（如 'sh000001'、'SPX'）

        Returns:
            行情字典，失败时返回 None
        """
        with _yfinance_http_guard():
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
        获取主要指数行情 (Yahoo Finance)，支持 A 股、美股、港股、日股、韩股与台股。
        region=us 时委托给 _get_us_main_indices。
        region=hk 时委托给 _get_hk_main_indices。
        region=jp/kr/tw 时分别委托给对应市场指数方法。
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
        """获取美股主要指数行情（SPX、IXIC、DJI、VIX），复用 _fetch_yf_ticker_data"""
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
        """获取港股主要指数行情（HSI、HSTECH、HSCEI），复用 _fetch_yf_ticker_data"""
        # Yahoo Finance Hong Kong Stock Index Symbol Mapping:
        # - HSI -> ^HSI
        # - HSTECH -> HSTECH.HK (not ^HSTECH)
        # - HSCEI -> ^HSCE (not ^HSCEI)
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
        """获取日本主要指数行情（日经225、TOPIX），复用 _fetch_yf_ticker_data。"""
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
        """获取韩国主要指数行情（KOSPI、KOSDAQ），复用 _fetch_yf_ticker_data。"""
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
        """获取台湾主要指数行情（加权指数 ^TWII、柜买指数 ^TWOII），复用 _fetch_yf_ticker_data。"""
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

EXPECTED_MAIN_INDEX_METHOD_NAMES: Tuple[str, ...] = (
    "_fetch_yf_ticker_data",
    "get_main_indices",
    "_get_us_main_indices",
    "_get_hk_main_indices",
    "_get_jp_main_indices",
    "_get_kr_main_indices",
    "_get_tw_main_indices",
)


def bind_main_indices_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind main-index descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _MainIndicesMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_MAIN_INDEX_METHOD_NAMES,
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
