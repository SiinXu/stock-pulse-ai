# -*- coding: utf-8 -*-
"""efinance UA rotation, request pacing, and history-failure formatting.

Method bodies are rebound onto ``EfinanceFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.efinance_fetcher``. ``_build_history_failure_message``
stays a ``staticmethod``; ``_set_random_user_agent`` keeps the choose-and-log
contract and does not write request headers.

The timeout helper and error classifier remain reachable through facade
globals after clone; code classifiers and ``USER_AGENTS`` still stay on
the facade.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Dict, Optional, Tuple, Type

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.efinance_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.efinance_fetcher")
USER_AGENTS = []  # type: ignore[assignment]
_classify_eastmoney_error = None  # type: ignore[assignment]
EASTMONEY_HISTORY_ENDPOINT = ""  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _RateLimitMethods:
    """Source descriptors rebound onto ``EfinanceFetcher``."""

    @staticmethod
    def _build_history_failure_message(
        stock_code: str,
        beg_date: str,
        end_date: str,
        exc: Exception,
        elapsed: float,
        is_etf: bool = False,
    ) -> Tuple[str, str]:
        category, detail = _classify_eastmoney_error(exc)
        instrument_type = "ETF" if is_etf else "stock"
        message = (
            "Eastmoney 历史K线接口失败: "
            f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
            f"market_type={instrument_type}, range={beg_date}~{end_date}, "
            f"category={category}, error_type={type(exc).__name__}, elapsed={elapsed:.2f}s, detail={detail}"
        )
        return category, message

    def _set_random_user_agent(self) -> None:
        """
        设置随机 User-Agent
        
        通过修改 requests Session 的 headers 实现
        这是关键的反爬策略之一
        """
        try:
            random_ua = random.choice(USER_AGENTS)
            logger.debug(f"设置 User-Agent: {random_ua[:50]}...")
        except Exception as e:  # broad-exception: fallback_recorded - User-agent selection failure is safely logged before continuing without a header write.
            log_safe_exception(
                logger,
                "Efinance user agent selection failed",
                e,
                error_code="efinance_user_agent_selection_failed",
                level=logging.DEBUG,
            )

    def _enforce_rate_limit(self) -> None:
        """
        强制执行速率限制
        
        策略：
        1. 检查距离上次请求的时间间隔
        2. 如果间隔不足，补充休眠时间
        3. 然后再执行随机 jitter 休眠
        """
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            min_interval = self.sleep_min
            if elapsed < min_interval:
                additional_sleep = min_interval - elapsed
                logger.debug(f"补充休眠 {additional_sleep:.2f} 秒")
                time.sleep(additional_sleep)

        # Apply a random jitter delay
        self.random_sleep(self.sleep_min, self.sleep_max)
        self._last_request_time = time.time()


EXPECTED_RATE_LIMIT_METHOD_NAMES: Tuple[str, ...] = (
    "_build_history_failure_message",
    "_set_random_user_agent",
    "_enforce_rate_limit",
)


def bind_rate_limit_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind UA, rate-limit, and history-failure descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _RateLimitMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_RATE_LIMIT_METHOD_NAMES,
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
