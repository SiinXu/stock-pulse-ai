# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned rankings orchestration rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. ``BaseFetcher`` provider methods of the same names stay on
``BaseFetcher``. ``get_main_indices`` and ``get_market_stats`` stay on the
facade. Concept-rankings TTL/lock/dict class attributes stay on the facade.
``get_board_context`` stays on the facade and still calls rebound
``_get_sector_rankings_with_meta``. These descriptors own sector/concept
ranking aggregation, hot-stock and limit-up pool routing, and the
concept-rankings cache read/write path. ``DataFetcherManager`` remains the
public import and patch surface.
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

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
summarize_exception = None  # type: ignore[assignment,misc]

logger = logging.getLogger("src.data_provider.base")

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _RankingsMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def _get_sector_rankings_with_meta(
            self,
            n: int = 5,
        ) -> Tuple[List[Dict], List[Dict], List[Dict[str, Any]], str]:
            """Get sector rankings with ordered fallback chain metadata."""
            source_chain: List[Dict[str, Any]] = []
            last_error = ""

            # Iterate through the manager's capability-filtered priority order.
            for fetcher in self._get_fetchers_for_capability(
                "sector_rankings",
                market="cn",
            ):
                if not hasattr(fetcher, 'get_sector_rankings'):
                    continue

                start = time.time()
                try:
                    data = fetcher.get_sector_rankings(n)
                    duration_ms = int((time.time() - start) * 1000)
                    if data and data[0] is not None and data[1] is not None:
                        source_chain.append(
                            {
                                "provider": fetcher.name,
                                "result": "ok",
                                "duration_ms": duration_ms,
                            }
                        )
                        logger.info(f"[{fetcher.name}] 获取板块排行成功")
                        return data[0], data[1], source_chain, ""

                    last_error = f"{fetcher.name}返回空结果"
                    source_chain.append(
                        {
                            "provider": fetcher.name,
                            "result": "empty",
                            "duration_ms": duration_ms,
                            "error": last_error,
                        }
                    )
                except Exception as e:  # broad-exception: fallback_recorded - source chain records ranking fallback
                    error_type, error_reason = summarize_exception(e)
                    last_error = f"{fetcher.name} ({error_type}) {error_reason}"
                    duration_ms = int((time.time() - start) * 1000)
                    source_chain.append(
                        {
                            "provider": fetcher.name,
                            "result": "failed",
                            "duration_ms": duration_ms,
                            "error": error_reason,
                        }
                    )
                    log_safe_exception(
                        logger,
                        "Data provider sector ranking fetch failed",
                        e,
                        error_code="data_provider_sector_ranking_failed",
                        level=logging.WARNING,
                        context={"provider": fetcher.name},
                    )

            return [], [], source_chain, last_error

    def get_sector_rankings(self, n: int = 5) -> Tuple[List[Dict], List[Dict]]:
        """获取板块涨跌榜（自动切换数据源）"""
        # Preserve the required fallback order: AkShare (EM) -> AkShare (Sina) -> Tushare -> efinance.
        top, bottom, _, last_error = self._get_sector_rankings_with_meta(n)
        if top or bottom:
            return top, bottom
        logger.warning("All data providers returned no sector rankings")
        return [], []

    @staticmethod
    def _copy_ranking_rows(rows: List[Dict]) -> List[Dict]:
        return [dict(row) if isinstance(row, dict) else row for row in rows or []]

    @classmethod
    def clear_concept_rankings_cache_for_tests(cls) -> None:
        with cls._concept_rankings_cache_lock:
            cls._concept_rankings_cache.clear()

    def get_concept_rankings(self, n: int = 5) -> Tuple[List[Dict], List[Dict]]:
        """获取概念/题材涨跌榜（自动切换数据源）。"""
        try:
            normalized_n = int(n)
        except (TypeError, ValueError):
            normalized_n = 5
        if normalized_n <= 0:
            normalized_n = 5

        last_error = ""
        now = time.monotonic()

        with self.__class__._concept_rankings_cache_lock:
            cached = self.__class__._concept_rankings_cache.get(normalized_n)
            if cached and cached[0] > now:
                logger.debug("[概念排行] 命中共享缓存 n=%s", normalized_n)
                return self._copy_ranking_rows(cached[1]), self._copy_ranking_rows(cached[2])

            top: List[Dict] = []
            bottom: List[Dict] = []
            for fetcher in self._get_fetchers_for_capability(
                "concept_rankings",
                market="cn",
            ):
                try:
                    data = fetcher.get_concept_rankings(normalized_n)
                    if data and (data[0] or data[1]):
                        top = data[0] or []
                        bottom = data[1] or []
                        logger.info(f"[{fetcher.name}] 获取概念排行成功")
                        break
                    last_error = f"{fetcher.name}返回空结果"
                except Exception as e:  # broad-exception: fallback_recorded - safe log precedes concept fallback
                    error_type, error_reason = summarize_exception(e)
                    last_error = f"{fetcher.name} ({error_type}) {error_reason}"
                    log_safe_exception(
                        logger,
                        "Data provider concept ranking fetch failed",
                        e,
                        error_code="data_provider_concept_ranking_failed",
                        level=logging.WARNING,
                        context={"provider": fetcher.name},
                    )

            if not top and not bottom and last_error:
                logger.warning("All data providers returned no concept rankings")

            ttl = (
                self.__class__._CONCEPT_RANKINGS_CACHE_TTL_SECONDS
                if top or bottom
                else self.__class__._CONCEPT_RANKINGS_EMPTY_CACHE_TTL_SECONDS
            )
            cached_top = self._copy_ranking_rows(top)
            cached_bottom = self._copy_ranking_rows(bottom)
            self.__class__._concept_rankings_cache[normalized_n] = (
                time.monotonic() + ttl,
                cached_top,
                cached_bottom,
            )
            return self._copy_ranking_rows(cached_top), self._copy_ranking_rows(cached_bottom)

    def get_hot_stocks(self, n: int = 10) -> List[Dict[str, Any]]:
        """获取市场人气股榜（自动切换数据源）。"""
        last_error = ""
        for fetcher in self._get_fetchers_for_capability(
            "hot_stocks",
            market="cn",
        ):
            try:
                data = fetcher.get_hot_stocks(n)
                if data:
                    logger.info(f"[{fetcher.name}] 获取人气股成功")
                    return data[:n]
                last_error = f"{fetcher.name}返回空结果"
            except Exception as e:  # broad-exception: fallback_recorded - safe log precedes hot-stock fallback
                error_type, error_reason = summarize_exception(e)
                last_error = f"{fetcher.name} ({error_type}) {error_reason}"
                log_safe_exception(
                    logger,
                    "Data provider hot stock fetch failed",
                    e,
                    error_code="data_provider_hot_stock_fetch_failed",
                    level=logging.WARNING,
                    context={"provider": fetcher.name},
                )
        if last_error:
            logger.warning("All data providers returned no hot stocks")
        return []

    def get_limit_up_pool(
        self,
        date: Optional[str] = None,
        n: int = 20,
    ) -> List[Dict[str, Any]]:
        """获取涨停池与连板梯队（自动切换数据源）。"""
        last_error = ""
        for fetcher in self._get_fetchers_for_capability(
            "limit_up_pool",
            market="cn",
        ):
            try:
                data = fetcher.get_limit_up_pool(date=date, n=n)
                if data:
                    logger.info(f"[{fetcher.name}] 获取涨停池成功")
                    return data[:n]
                last_error = f"{fetcher.name}返回空结果"
            except Exception as e:  # broad-exception: fallback_recorded - safe log precedes limit-up fallback
                error_type, error_reason = summarize_exception(e)
                last_error = f"{fetcher.name} ({error_type}) {error_reason}"
                log_safe_exception(
                    logger,
                    "Data provider limit-up pool fetch failed",
                    e,
                    error_code="data_provider_limit_up_pool_failed",
                    level=logging.WARNING,
                    context={"provider": fetcher.name},
                )
        if last_error:
            logger.warning("All data providers returned no limit-up pool data")
        return []

EXPECTED_RANKINGS_METHOD_NAMES: Tuple[str, ...] = (
    "_get_sector_rankings_with_meta",
    "get_sector_rankings",
    "_copy_ranking_rows",
    "clear_concept_rankings_cache_for_tests",
    "get_concept_rankings",
    "get_hot_stocks",
    "get_limit_up_pool",
)


def bind_rankings_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind rankings descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_RankingsMethods).items():
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
