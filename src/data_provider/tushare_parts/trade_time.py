# -*- coding: utf-8 -*-
"""Tushare trade-calendar helpers: China clock, calendar cache, and trade date.

Method bodies are rebound onto ``TushareFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.tushare_fetcher``.

No sibling method moves. Chip distribution, identity/availability helpers,
and the ``date_list`` / ``_date_list_end`` instance cache stay on the facade.
The rate-limited API client (``_api``, ``_call_api_with_rate_limit``) is
reached through ``self`` at call time. ``_pick_trade_date`` remains a
``staticmethod``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Type
from zoneinfo import ZoneInfo

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.tushare_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tushare_fetcher")

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _TradeTimeMethods:
    """Source descriptors rebound onto ``TushareFetcher``."""

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


EXPECTED_TRADE_TIME_METHOD_NAMES: Tuple[str, ...] = (
    "_get_china_now",
    "_get_trade_dates",
    "_pick_trade_date",
    "get_trade_time",
)


def bind_trade_time_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind trade-calendar descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _TradeTimeMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_TRADE_TIME_METHOD_NAMES,
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
