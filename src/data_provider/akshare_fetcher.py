# -*- coding: utf-8 -*-
"""
===================================
AkshareFetcher - 主数据源 (Priority 1)
===================================

Compatibility facade for the AkShare provider (ADR-006 / Issue #1068).

Data sources:
1. Eastmoney crawlers via the akshare library (default)
2. Sina Finance interfaces (fallback)
3. Tencent Finance interfaces (fallback)

Implementation ownership lives under ``data_provider.akshare_parts`` by
capability domain (symbols, timeout client, history, realtime quotes,
market boards, enhanced data, realtime cache). This module remains the
stable import and monkeypatch surface so provider registration, tests,
and diagnostics keep working without behavior changes.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.patches.eastmoney_patch import eastmoney_patch
from src.config import get_config
from src.security.outbound_policy import safe_get
from src.utils.sanitize import log_safe_exception, safe_before_sleep_log
from .base import (
    BaseFetcher,
    DataFetchError,
    RateLimitError,
    STANDARD_COLUMNS,
    is_bse_code,
    is_st_stock,
    is_kc_cy_stock,
    normalize_stock_code,
)
from .realtime_types import (
    UnifiedRealtimeQuote,
    ChipDistribution,
    RealtimeSource,
    get_realtime_circuit_breaker,
    get_chip_circuit_breaker,
    safe_float,
    safe_int,
)
from .us_index_mapping import is_us_index_code, is_us_stock_code
from .akshare_parts.realtime_cache import (
    _etf_realtime_cache,
    _realtime_cache,
    get_a_share_snapshot_if_fresh,
    get_etf_snapshot_if_fresh,
    get_hk_cache,
    hk_refresh_lock,
    lookup_hk_em_snapshot,
    record_hk_refresh_failure,
    record_hk_refresh_success,
    store_a_share_snapshot,
    store_etf_snapshot,
)
from .akshare_parts.symbols import (
    _is_etf_code,
    _is_hk_code,
    _is_us_code,
    _to_sina_tx_symbol,
    is_hk_stock_code,
)
from .akshare_parts.parse_tencent import (
    _normalize_tencent_volume,
    _parse_tencent_amount,
)
from .akshare_parts.realtime_errors import (
    _build_realtime_failure_message,
    _classify_realtime_http_error,
)
from .akshare_parts import timeout_client as _timeout_client_module
from .akshare_parts import enhanced as _enhanced_module
from .akshare_parts import history as _history_module
from .akshare_parts import market_boards as _market_boards_module
from .akshare_parts import realtime_quotes as _realtime_quotes_module
from .akshare_parts.facade_bind import (
    _clone_facade_function,
    bind_methods_from_class,
)
from .akshare_parts.enhanced import _EnhancedMethods
from .akshare_parts.history import _HistoryMethods
from .akshare_parts.market_boards import _MarketBoardsMethods
from .akshare_parts.realtime_quotes import _RealtimeQuotesMethods

# Constants re-exported with identical values; timeout callables are cloned
# below so free-name lookups (multiprocessing, sibling helpers) stay on this
# facade module for established monkeypatch seams.
_AKSHARE_HISTORY_CALL_TIMEOUT = _timeout_client_module._AKSHARE_HISTORY_CALL_TIMEOUT
_AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE = (
    _timeout_client_module._AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE
)
_AKSHARE_TIMEOUT_PROCESS_START_METHOD = (
    _timeout_client_module._AKSHARE_TIMEOUT_PROCESS_START_METHOD
)


# Keep the old RealtimeQuote alias for backward compatibility
RealtimeQuote = UnifiedRealtimeQuote


logger = logging.getLogger(__name__)

SINA_REALTIME_ENDPOINT = "hq.sinajs.cn/list"
TENCENT_REALTIME_ENDPOINT = "qt.gtimg.cn/q"

# User-Agent pool, used for random rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Re-exported from akshare_parts.realtime_cache for test/patch parity:
# Tests and diagnostics target src.data_provider.akshare_fetcher._realtime_cache
# and _etf_realtime_cache (same process-local dict objects).

# Pure helpers and timeout client symbols are re-exported above so the canonical
# ``src.data_provider.akshare_fetcher`` public surface stays stable.


class AkshareFetcher(BaseFetcher):
    """
    Akshare 数据源实现

    优先级：1（最高）
    数据来源：东方财富网爬虫

    防护策略：
    - 每次请求前随机休眠 2.0-5.0 秒
    - 随机 User-Agent 轮换
    - 失败后指数退避重试（最多3次）

    Implementation methods for history / realtime / market boards / enhanced
    data are rebound from ``data_provider.akshare_parts`` (Issue #1068).
    """

    money_flow_calibration_identity = (
        "eastmoney_em_order_size_buckets_v1;amount_unit=unknown;ratio_unit=percent"
    )

    name = "AkshareFetcher"
    priority = int(os.getenv("AKSHARE_PRIORITY", "1"))

    def __init__(self, sleep_min: float = 2.0, sleep_max: float = 5.0):
        """
        初始化 AkshareFetcher

        Args:
            sleep_min: 最小休眠时间（秒）
            sleep_max: 最大休眠时间（秒）
        """
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max
        self._last_request_time: Optional[float] = None
        self._history_call_timeout = _AKSHARE_HISTORY_CALL_TIMEOUT
        # Only execute patch operation when Eastmoney patch is enabled
        if get_config().enable_eastmoney_patch:
            eastmoney_patch()


_EXPECTED_HISTORY_METHOD_NAMES = (
    "_set_random_user_agent",
    "_enforce_rate_limit",
    "_fetch_raw_data",
    "_fetch_stock_data",
    "_fetch_stock_data_em",
    "_fetch_stock_data_sina",
    "_fetch_stock_data_tx",
    "_fetch_etf_data",
    "_fetch_us_data",
    "_fetch_hk_data",
    "_normalize_data",
)

_EXPECTED_REALTIME_METHOD_NAMES = (
    "get_realtime_quote",
    "_get_stock_realtime_quote_em",
    "_get_stock_realtime_quote_sina",
    "_get_stock_realtime_quote_tencent",
    "_get_etf_realtime_quote",
    "_get_hk_realtime_quote",
)

_EXPECTED_ENHANCED_METHOD_NAMES = (
    "get_money_flow",
    "get_chip_distribution",
    "get_enhanced_data",
)

_EXPECTED_MARKET_BOARD_METHOD_NAMES = (
    "get_main_indices",
    "get_market_stats",
    "_calc_market_stats",
    "get_sector_rankings",
    "get_concept_rankings",
    "get_hot_stocks",
    "_get_eastmoney_hot_stocks",
    "_get_eastmoney_hot_up_stocks",
    "_get_xueqiu_hot_stocks",
    "get_limit_up_pool",
    "_normalize_limit_time_value",
    "_safe_float",
    "_safe_int",
    "_find_first_column",
    "_find_column_containing",
)


def _apply_history_retry(name: str, bound):
    """Re-apply the historical tenacity policy after facade cloning."""

    if name != "_fetch_raw_data":
        return bound
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=safe_before_sleep_log(
            logger,
            logging.WARNING,
            event="Akshare daily data retry scheduled",
            error_code="akshare_daily_data_retry",
        ),
    )(bound)


def _bind_timeout_client_facade() -> None:
    """Clone timeout helpers so patches on this module intercept them."""

    global _akshare_call_with_timeout
    global _akshare_timeout_worker
    global _terminate_akshare_process

    ns = globals()
    _terminate_akshare_process = _clone_facade_function(
        _timeout_client_module._terminate_akshare_process,
        ns,
        qualname="_terminate_akshare_process",
    )
    _akshare_timeout_worker = _clone_facade_function(
        _timeout_client_module._akshare_timeout_worker,
        ns,
        qualname="_akshare_timeout_worker",
    )
    _akshare_call_with_timeout = _clone_facade_function(
        _timeout_client_module._akshare_call_with_timeout,
        ns,
        qualname="_akshare_call_with_timeout",
    )


def _assemble_akshare_fetcher_facade() -> None:
    """Bind capability-domain method bodies onto the public fetcher class."""

    _bind_timeout_client_facade()
    bind_methods_from_class(
        _HistoryMethods,
        AkshareFetcher,
        globals(),
        expected_names=_EXPECTED_HISTORY_METHOD_NAMES,
        post_bind=_apply_history_retry,
    )
    bind_methods_from_class(
        _RealtimeQuotesMethods,
        AkshareFetcher,
        globals(),
        expected_names=_EXPECTED_REALTIME_METHOD_NAMES,
    )
    bind_methods_from_class(
        _EnhancedMethods,
        AkshareFetcher,
        globals(),
        expected_names=_EXPECTED_ENHANCED_METHOD_NAMES,
    )
    bind_methods_from_class(
        _MarketBoardsMethods,
        AkshareFetcher,
        globals(),
        expected_names=_EXPECTED_MARKET_BOARD_METHOD_NAMES,
    )
    # Rebound methods are assigned after class body evaluation; clear ABC
    # abstracts that are now implemented so instantiation matches the legacy
    # monofile class (BaseFetcher marks _fetch_raw_data / _normalize_data).
    abstracts = set(getattr(AkshareFetcher, "__abstractmethods__", ()))
    if abstracts:
        abstracts.difference_update(
            {
                name
                for name in (
                    "_fetch_raw_data",
                    "_normalize_data",
                    "get_daily_data",
                )
                if callable(getattr(AkshareFetcher, name, None))
            }
        )
        # Any remaining names that are now concrete on the class.
        abstracts = {
            name
            for name in abstracts
            if name not in AkshareFetcher.__dict__
            or getattr(AkshareFetcher.__dict__[name], "__isabstractmethod__", False)
        }
        AkshareFetcher.__abstractmethods__ = frozenset(abstracts)


_assemble_akshare_fetcher_facade()


def _install_part_reload_hooks() -> None:
    for module in (
        _history_module,
        _realtime_quotes_module,
        _enhanced_module,
        _market_boards_module,
    ):
        module._FACADE_RELOAD_HOOK = _assemble_akshare_fetcher_facade  # type: ignore[attr-defined]


_install_part_reload_hooks()
