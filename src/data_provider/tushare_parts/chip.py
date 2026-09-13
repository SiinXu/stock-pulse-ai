# -*- coding: utf-8 -*-
"""Tushare chip-distribution helpers: cyq_chips fetch and CYQ metric parser.

Method bodies are rebound onto ``TushareFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.tushare_fetcher``.

No sibling method moves. Identity/availability helpers and the
``date_list`` / ``_date_list_end`` instance cache stay on the facade.
Trade-calendar helpers, the rate-limited API client, and symbol converters
are reached through ``self`` at call time.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.tushare_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tushare_fetcher")
ChipDistribution = None  # type: ignore[assignment]
_is_us_code = None  # type: ignore[assignment]
_is_etf_code = None  # type: ignore[assignment]
_is_hk_market = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _ChipMethods:
    """Source descriptors rebound onto ``TushareFetcher``."""

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


EXPECTED_CHIP_METHOD_NAMES: Tuple[str, ...] = (
    "get_chip_distribution",
    "compute_cyq_metrics",
)


def bind_chip_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind chip-distribution descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _ChipMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_CHIP_METHOD_NAMES,
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
