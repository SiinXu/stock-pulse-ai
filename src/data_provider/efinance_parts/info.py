# -*- coding: utf-8 -*-
"""efinance per-symbol info, belong-board, and enhanced-data methods.

Method bodies are rebound onto ``EfinanceFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.efinance_fetcher``.

UA/rate-limit helpers stay on the facade; rebound bodies reach them through
``self``. Module-level timeout helpers stay on the facade so already-extracted
owners keep resolving them from facade globals.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.efinance_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.efinance_fetcher")
_ef_call_with_timeout = None  # type: ignore[assignment]
_EF_CALL_TIMEOUT = 0  # type: ignore[assignment]
FuturesTimeoutError = TimeoutError  # type: ignore[assignment,misc]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _InfoMethods:
    """Source descriptors rebound onto ``EfinanceFetcher``."""

    def get_base_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票基本信息
        
        数据来源：ef.stock.get_base_info()
        包含：市盈率、市净率、所处行业、总市值、流通市值、ROE、净利率等
        
        Args:
            stock_code: 股票代码
            
        Returns:
            包含基本信息的字典，获取失败返回 None
        """
        import efinance as ef
        
        try:
            # Anti-ban strategy
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API调用] ef.stock.get_base_info(stock_codes={stock_code}) 获取基本信息...")
            import time as _time
            api_start = _time.time()
            
            info = _ef_call_with_timeout(ef.stock.get_base_info, stock_code)
            
            api_elapsed = _time.time() - api_start
            logger.info(f"[API返回] ef.stock.get_base_info 成功, 耗时 {api_elapsed:.2f}s")
            
            if info is None:
                logger.warning(f"[API返回] 未获取到 {stock_code} 的基本信息")
                return None
            
            # Convert to Dictionary
            if isinstance(info, pd.Series):
                return info.to_dict()
            elif isinstance(info, pd.DataFrame):
                if not info.empty:
                    return info.iloc[0].to_dict()
            
            return None
            
        except Exception as e:  # broad-exception: fallback_recorded - Safe diagnostics are recorded before base-info failover.
            log_safe_exception(
                logger,
                "Efinance stock base information fetch failed",
                e,
                error_code="efinance_stock_base_info_failed",
                level=logging.ERROR,
                context={"symbol": stock_code},
            )
            return None
    
    def get_belong_board(self, stock_code: str) -> Optional[pd.DataFrame]:
        """
        获取股票所属板块
        
        数据来源：ef.stock.get_belong_board()
        
        Args:
            stock_code: 股票代码
            
        Returns:
            所属板块 DataFrame，获取失败返回 None
        """
        import efinance as ef
        
        try:
            # Anti-ban strategy
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API调用] ef.stock.get_belong_board(stock_code={stock_code}) 获取所属板块...")
            import time as _time
            api_start = _time.time()
            
            df = _ef_call_with_timeout(ef.stock.get_belong_board, stock_code)
            
            api_elapsed = _time.time() - api_start
            
            if df is not None and not df.empty:
                logger.info(f"[API返回] ef.stock.get_belong_board 成功: 返回 {len(df)} 个板块, 耗时 {api_elapsed:.2f}s")
                return df
            else:
                logger.warning(f"[API返回] 未获取到 {stock_code} 的板块信息")
                return None
            
        except FuturesTimeoutError:
            logger.warning(f"[超时] ef.stock.get_belong_board({stock_code}) 超过 {_EF_CALL_TIMEOUT}s，跳过")
            return None
        except Exception as e:  # broad-exception: fallback_recorded - Safe diagnostics are recorded before board-membership failover.
            log_safe_exception(
                logger,
                "Efinance stock board membership fetch failed",
                e,
                error_code="efinance_stock_board_membership_failed",
                level=logging.ERROR,
                context={"symbol": stock_code},
            )
            return None
    
    def get_enhanced_data(self, stock_code: str, days: int = 60) -> Dict[str, Any]:
        """
        获取增强数据（历史K线 + 实时行情 + 基本信息）
        
        Args:
            stock_code: 股票代码
            days: 历史数据天数
            
        Returns:
            包含所有数据的字典
        """
        result = {
            'code': stock_code,
            'daily_data': None,
            'realtime_quote': None,
            'base_info': None,
            'belong_board': None,
        }
        
        # Get daily line data
        try:
            df = self.get_daily_data(stock_code, days=days)
            result['daily_data'] = df
        except Exception as e:  # broad-exception: fallback_recorded - Safe diagnostics are recorded before daily-data failover.
            log_safe_exception(
                logger,
                "Efinance daily data fetch failed",
                e,
                error_code="efinance_daily_data_failed",
                level=logging.ERROR,
                context={"symbol": stock_code},
            )
        
        # Get real-time quotes
        result['realtime_quote'] = self.get_realtime_quote(stock_code)
        
        # Get basic information
        result['base_info'] = self.get_base_info(stock_code)
        
        # Get sector
        result['belong_board'] = self.get_belong_board(stock_code)
        
        return result


EXPECTED_INFO_METHOD_NAMES: Tuple[str, ...] = (
    "get_base_info",
    "get_belong_board",
    "get_enhanced_data",
)


def bind_info_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind per-symbol info descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _InfoMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_INFO_METHOD_NAMES,
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
