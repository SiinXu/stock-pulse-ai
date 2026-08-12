# -*- coding: utf-8 -*-
"""AkShare money-flow, chip-distribution, and enhanced-data methods.

Method bodies are rebound onto ``AkshareFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``data_provider.akshare_fetcher``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger("data_provider.akshare_fetcher")
ChipDistribution = None  # type: ignore[assignment,misc]
get_chip_circuit_breaker = None  # type: ignore[assignment]
_is_etf_code = None  # type: ignore[assignment]
_is_hk_code = None  # type: ignore[assignment]
safe_float = None  # type: ignore[assignment]
_akshare_call_with_timeout = None  # type: ignore[assignment]
_is_us_code = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _EnhancedMethods:
    """Source descriptors rebound onto ``AkshareFetcher``."""

    def get_money_flow(self, stock_code: str, days: int = 5):
        """
        Fetch A-share individual main-force / large-order money flow.

        Data source: ak.stock_individual_fund_flow (Eastmoney).
        Non-CN symbols return None without network I/O.

        Args:
            stock_code: Stock code
            days: History window hint for multi-day rollups

        Returns:
            MoneyFlowSnapshot for the latest session, or None
        """
        from .money_flow_akshare import fetch_akshare_individual_money_flow

        def _run_with_process_timeout(func, **kwargs):
            timeout = kwargs.pop("timeout", 12.0)
            call_name = kwargs.pop("call_name", "akshare_money_flow")
            return _akshare_call_with_timeout(
                func,
                timeout=timeout,
                call_name=call_name,
                **kwargs,
            )

        return fetch_akshare_individual_money_flow(
            stock_code,
            history_days=days,
            rate_limit=self._enforce_rate_limit,
            timeout_runner=_run_with_process_timeout,
        )

    def get_chip_distribution(self, stock_code: str) -> Optional[ChipDistribution]:
        """
        获取筹码分布数据
        
        数据来源：ak.stock_cyq_em()
        包含：获利比例、平均成本、筹码集中度
        
        注意：ETF/指数没有筹码分布数据，会直接返回 None
        
        Args:
            stock_code: 股票代码
            
        Returns:
            ChipDistribution 对象（最新一天的数据），获取失败返回 None
        """
        import akshare as ak

        # No chip distribution data for U.S. stocks (Akshare does not support it)
        if _is_us_code(stock_code):
            logger.debug(f"[API跳过] {stock_code} 是美股，无筹码分布数据")
            return None

        # No chip distribution data available for Hong Kong stocks (stock_cyq_em is exclusive to A-shares).
        if _is_hk_code(stock_code):
            logger.debug(f"[API跳过] {stock_code} 是港股，无筹码分布数据")
            return None

        # ETFs/Indices do not have chip distribution data
        if _is_etf_code(stock_code):
            logger.debug(f"[API跳过] {stock_code} 是 ETF/指数，无筹码分布数据")
            return None
        
        try:
            # Anti-ban strategy
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API调用] ak.stock_cyq_em(symbol={stock_code}) 获取筹码分布...")
            import time as _time
            api_start = _time.time()
            
            df = ak.stock_cyq_em(symbol=stock_code)
            
            api_elapsed = _time.time() - api_start
            
            if df.empty:
                logger.warning(f"[API返回] ak.stock_cyq_em 返回空数据, 耗时 {api_elapsed:.2f}s")
                return None
            
            logger.info(f"[API返回] ak.stock_cyq_em 成功: 返回 {len(df)} 天数据, 耗时 {api_elapsed:.2f}s")
            logger.debug(f"[API返回] 筹码数据列名: {list(df.columns)}")
            
            # Get latest day's data
            latest = df.iloc[-1]
            
            # Use unified conversion functions in realtime_types.py
            chip = ChipDistribution(
                code=stock_code,
                date=str(latest.get('日期', '')),
                profit_ratio=safe_float(latest.get('获利比例')),
                avg_cost=safe_float(latest.get('平均成本')),
                cost_90_low=safe_float(latest.get('90成本-低')),
                cost_90_high=safe_float(latest.get('90成本-高')),
                concentration_90=safe_float(latest.get('90集中度')),
                cost_70_low=safe_float(latest.get('70成本-低')),
                cost_70_high=safe_float(latest.get('70成本-高')),
                concentration_70=safe_float(latest.get('70集中度')),
            )
            
            logger.info(f"[筹码分布] {stock_code} 日期={chip.date}: 获利比例={chip.profit_ratio:.1%}, "
                       f"平均成本={chip.avg_cost}, 90%集中度={chip.concentration_90:.2%}, "
                       f"70%集中度={chip.concentration_70:.2%}")
            return chip
            
        except Exception as e:
            log_safe_exception(
                logger,
                "Akshare chip distribution fetch failed",
                e,
                error_code="akshare_chip_distribution_failed",
                level=logging.ERROR,
                context={"symbol": stock_code},
            )
            return None

    def get_enhanced_data(self, stock_code: str, days: int = 60) -> Dict[str, Any]:
        """
        获取增强数据（历史K线 + 实时行情 + 筹码分布）
        
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
            'chip_distribution': None,
        }
        
        # Get daily line data
        try:
            df = self.get_daily_data(stock_code, days=days)
            result['daily_data'] = df
        except Exception as e:
            log_safe_exception(
                logger,
                "Akshare daily data fetch failed",
                e,
                error_code="akshare_daily_data_failed",
                level=logging.ERROR,
                context={"symbol": stock_code},
            )
        
        # Get real-time quotes
        result['realtime_quote'] = self.get_realtime_quote(stock_code)
        
        # Get chip distribution
        result['chip_distribution'] = self.get_chip_distribution(stock_code)
        
        return result



def _rebind_loaded_facade() -> None:
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
