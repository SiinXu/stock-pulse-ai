# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned market-overview routing rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. ``BaseFetcher`` provider methods of the same names stay on
``BaseFetcher``. TickFlow lifecycle (``_get_tickflow_fetcher``, ``close``)
stays on the facade. These descriptors own TickFlow-first
``get_main_indices`` and ``get_market_stats`` capability fallback.
``DataFetcherManager`` remains the public import and patch surface.
"""

from __future__ import annotations

import logging
import time
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
)

from src.utils.sanitize import log_safe_exception

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

logger = logging.getLogger("src.data_provider.base")

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _MarketOverviewMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def get_main_indices(self, region: str = "cn") -> List[Dict[str, Any]]:
        """获取主要指数实时行情（自动切换数据源）"""
        if region == "cn":
            tickflow_fetcher = self._get_tickflow_fetcher()
            if tickflow_fetcher is not None:
                try:
                    data = tickflow_fetcher.get_main_indices(region=region)
                    if data:
                        logger.info("[TickFlowFetcher] 获取指数行情成功")
                        return data
                except Exception as e:  # broad-exception: fallback_recorded - safe log precedes built-in index fallback
                    log_safe_exception(
                        logger,
                        "TickFlow market indices fetch failed",
                        e,
                        error_code="tickflow_market_indices_failed",
                        level=logging.WARNING,
                        context={"market": region},
                    )

        for fetcher in self._get_fetchers_for_capability(
            "main_indices",
            market=region if region in self._DAILY_MARKETS else None,
        ):
            if region == "cn" and fetcher.name == "TickFlowFetcher":
                continue
            try:
                data = fetcher.get_main_indices(region=region)
                if data:
                    logger.info(f"[{fetcher.name}] 获取指数行情成功")
                    return data
            except Exception as e:  # broad-exception: fallback_recorded - safe log precedes index fallback
                log_safe_exception(
                    logger,
                    "Data provider market indices fetch failed",
                    e,
                    error_code="data_provider_market_indices_failed",
                    level=logging.WARNING,
                    context={"market": region, "provider": fetcher.name},
                )
                continue
        return []

    def get_market_stats(self, *, purpose: str = "unspecified") -> Dict[str, Any]:
        """获取市场涨跌统计（自动切换数据源）"""
        logger.info("[MarketStats] component=market_stats action=start purpose=%s", purpose)
        tickflow_fetcher = self._get_tickflow_fetcher()
        if tickflow_fetcher is not None:
            started_at = time.monotonic()
            try:
                data = tickflow_fetcher.get_market_stats()
                elapsed = time.monotonic() - started_at
                if data:
                    logger.info(
                        "[MarketStats] component=market_stats action=provider_success "
                        "purpose=%s provider=TickFlowFetcher elapsed=%.2fs",
                        purpose,
                        elapsed,
                    )
                    return data
                logger.info(
                    "[MarketStats] component=market_stats action=provider_empty "
                    "purpose=%s provider=TickFlowFetcher elapsed=%.2fs",
                    purpose,
                    elapsed,
                )
            except Exception as e:  # broad-exception: fallback_recorded - safe log precedes market-stats fallback
                log_safe_exception(
                    logger,
                    "TickFlow market statistics fetch failed",
                    e,
                    error_code="tickflow_market_stats_failed",
                    level=logging.WARNING,
                    context={"purpose": purpose},
                )

        for fetcher in self._get_fetchers_for_capability(
            "market_stats",
            market="cn",
        ):
            if fetcher.name == "TickFlowFetcher":
                continue
            started_at = time.monotonic()
            try:
                data = fetcher.get_market_stats()
                elapsed = time.monotonic() - started_at
                if data:
                    logger.info(
                        "[MarketStats] component=market_stats action=provider_success "
                        "purpose=%s provider=%s elapsed=%.2fs",
                        purpose,
                        fetcher.name,
                        elapsed,
                    )
                    return data
                logger.info(
                    "[MarketStats] component=market_stats action=provider_empty "
                    "purpose=%s provider=%s elapsed=%.2fs",
                    purpose,
                    fetcher.name,
                    elapsed,
                )
            except Exception as e:  # broad-exception: fallback_recorded - safe log precedes provider fallback
                log_safe_exception(
                    logger,
                    "Data provider market statistics fetch failed",
                    e,
                    error_code="data_provider_market_stats_failed",
                    level=logging.WARNING,
                    context={"purpose": purpose, "provider": fetcher.name},
                )
                continue
        logger.warning("[MarketStats] component=market_stats action=complete status=empty purpose=%s", purpose)
        return {}


EXPECTED_MARKET_OVERVIEW_METHOD_NAMES: Tuple[str, ...] = (
    "get_main_indices",
    "get_market_stats",
)


def bind_market_overview_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind market-overview descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_MarketOverviewMethods).items():
        if name.startswith("__") or _descriptor_function(descriptor) is None:
            continue
        setattr(
            target_class,
            name,
            _clone_facade_descriptor(
                descriptor,
                global_namespace,
                owner_qualname=target_class.__qualname__,
            ),
        )
        bound_names.append(name)
    return tuple(bound_names)


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
