# -*- coding: utf-8 -*-
"""BaseFetcher default market-overview and rankings stubs.

Method bodies are rebound onto ``BaseFetcher`` by the compatibility facade
(ADR-006) so public imports and test patches stay on
``src.data_provider.base``. Each default body is ``return None``. Provider
subclasses that override a name keep their own implementation; do not change
those modules here.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from .facade_bind import bind_methods_from_class

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _MarketStubMethods:
    """Source descriptors rebound onto ``BaseFetcher``."""

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        获取主要指数实时行情

        Args:
            region: 市场区域，cn=A股 us=美股

        Returns:
            List[Dict]: 指数列表，每个元素为字典，包含:
                - code: 指数代码
                - name: 指数名称
                - current: 当前点位
                - change: 涨跌点数
                - change_pct: 涨跌幅(%)
                - volume: 成交量
                - amount: 成交额
        """
        return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """
        获取市场涨跌统计

        Returns:
            Dict: 包含:
                - up_count: 上涨家数
                - down_count: 下跌家数
                - flat_count: 平盘家数
                - limit_up_count: 涨停家数
                - limit_down_count: 跌停家数
                - total_amount: 两市成交额
        """
        return None

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """
        获取板块涨跌榜

        Args:
            n: 返回前n个

        Returns:
            Tuple: (领涨板块列表, 领跌板块列表)
        """
        return None

    def get_concept_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """
        获取概念/题材涨跌榜。

        Returns:
            Tuple: (领涨概念列表, 领跌概念列表)
        """
        return None

    def get_hot_stocks(self, n: int = 10) -> Optional[List[Dict[str, Any]]]:
        """
        获取市场人气股榜。

        Returns:
            List[Dict]: 人气股列表
        """
        return None

    def get_limit_up_pool(
        self,
        date: Optional[str] = None,
        n: int = 20,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取涨停池/连板梯队。

        Args:
            date: YYYYMMDD，默认由具体数据源决定
            n: 返回条数
        """
        return None


EXPECTED_MARKET_STUB_METHOD_NAMES: Tuple[str, ...] = (
    "get_main_indices",
    "get_market_stats",
    "get_sector_rankings",
    "get_concept_rankings",
    "get_hot_stocks",
    "get_limit_up_pool",
)


def bind_market_stub_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind default market-stub descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _MarketStubMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_MARKET_STUB_METHOD_NAMES,
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
