# -*- coding: utf-8 -*-
"""
===================================
数据源基类与管理器
===================================

设计模式：策略模式 (Strategy Pattern)
- BaseFetcher: 抽象基类，定义统一接口
- DataFetcherManager: 策略管理器，实现自动切换

防封禁策略：
1. 每个 Fetcher 内置流控逻辑
2. 失败自动切换到下一个数据源
3. 指数退避重试机制
"""

import json as _json
import inspect  # rebound money-flow descriptors resolve this name
import logging
import os
import random
import time
from dataclasses import replace  # rebound money-flow descriptors resolve this name
from threading import BoundedSemaphore, RLock, Thread, local
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Tuple,
)

import pandas as pd
import numpy as np
from src.data.stock_index_loader import get_index_stock_name
from src.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name
from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text
from .daily_cache import (  # noqa: F401
    CachedCandidateRejected,
    DailyCacheKey,
    DailyDataCache,
    MarketDataResolveResult,
    MarketDataFetchMode,
    REQUIRED_DAILY_COLUMNS,
)
from .fundamental_adapter import AkshareFundamentalAdapter
from .yfinance_fundamental_adapter import YfinanceFundamentalAdapter
from .realtime_types import CircuitBreaker, UnifiedRealtimeQuote
from . import field_trust as _field_trust

if TYPE_CHECKING:
    from .plugin_registry import DataProviderRegistration

# Configure logging
logger = logging.getLogger(__name__)


# Health/circuit defaults and env parsers are owned by
# ``manager_parts.daily_source_health`` and re-exported immediately below so
# class attributes and rebound methods still resolve names on this facade.
from .manager_parts.daily_source_health import (  # noqa: E402
    _PROVIDER_ADAPTIVE_PRIORITY_ENABLED_DEFAULT,
    _PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES_DEFAULT,
    _PROVIDER_CIRCUIT_COOLDOWN_SECONDS_DEFAULT,
    _PROVIDER_CIRCUIT_ENABLED_DEFAULT,
    _PROVIDER_CIRCUIT_FAILURE_THRESHOLD_DEFAULT,
    _PROVIDER_DAILY_HEALTH_SCHEMA_VERSION,
    _PROVIDER_HEALTH_WINDOW_SIZE_DEFAULT,
    _read_bool_env,
    _read_non_negative_float_env,
    _read_positive_int_env,
)

# Lazy module-level diagnostic seams. Construction resolves the same defaults
# without a module-level ``src.services.run_diagnostics`` import edge.
_default_provider_run_recorder = None
_default_provider_run_started_recorder = None


def record_provider_run(**kwargs):
    """Call-time provider-run diagnostic seam (lazy default wiring).

    Tests may patch this name. ``DataFetcherManager`` construction also resolves
    and stores the recorder pair on the instance.
    """
    global _default_provider_run_recorder, _default_provider_run_started_recorder
    if _default_provider_run_recorder is None:
        from .manager_parts.provider_run_wiring import load_default_provider_run_recorders

        _default_provider_run_recorder, started = load_default_provider_run_recorders()
        if _default_provider_run_started_recorder is None:
            _default_provider_run_started_recorder = started
    return _default_provider_run_recorder(**kwargs)


def record_provider_run_started(**kwargs):
    """Call-time provider-start diagnostic seam (lazy default wiring)."""
    global _default_provider_run_recorder, _default_provider_run_started_recorder
    if _default_provider_run_started_recorder is None:
        from .manager_parts.provider_run_wiring import load_default_provider_run_recorders

        run_fn, _default_provider_run_started_recorder = (
            load_default_provider_run_recorders()
        )
        if _default_provider_run_recorder is None:
            _default_provider_run_recorder = run_fn
    return _default_provider_run_started_recorder(**kwargs)


# Standardized Column Name Definition
STANDARD_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']


# Typed failures + exception summary helpers live in errors.py.
# Chip metric helpers live in chip_helpers.py.
# Re-export here so data_provider.base remains the compatibility facade
# (ADR-006): public names, patch targets, and existing imports stay stable.
from .errors import (  # noqa: E402
    CircuitOpenError,
    DataFetchError,
    DataSourceUnavailableError,
    RateLimitError,
    summarize_exception,
    unwrap_exception,
)
from .chip_helpers import (  # noqa: E402
    _coerce_chip_metric,
    _is_meaningful_chip_distribution,
)

# Symbol / market normalization helpers live in symbol_normalization.py.
# Re-export here so data_provider.base remains the compatibility facade
# (ADR-006): public names, patch targets, and existing imports stay stable.
from . import symbol_normalization as _symbol_normalization  # noqa: E402

ETF_PREFIXES = _symbol_normalization.ETF_PREFIXES
_is_etf_code = _symbol_normalization._is_etf_code
_is_hk_market = _symbol_normalization._is_hk_market
_is_jp_market = _symbol_normalization._is_jp_market
_is_kr_market = _symbol_normalization._is_kr_market
_is_tw_market = _symbol_normalization._is_tw_market
_is_us_market = _symbol_normalization._is_us_market
_market_tag = _symbol_normalization._market_tag
canonical_stock_code = _symbol_normalization.canonical_stock_code
is_bse_code = _symbol_normalization.is_bse_code
is_kc_cy_stock = _symbol_normalization.is_kc_cy_stock
is_st_stock = _symbol_normalization.is_st_stock
normalize_stock_code = _symbol_normalization.normalize_stock_code


class DataProvider(ABC):
    """Stable daily-market-data interface implemented by provider plugins."""

    name: str = "DataProvider"
    priority: int = 99
    allow_empty_daily_data: bool = False

    def _manager_call_identity(self) -> object:
        """Return the mutable provider state serialized by the manager."""

        return self

    def _manager_plugin_registration(
        self,
    ) -> Optional["DataProviderRegistration"]:
        """Return immutable plugin eligibility pinned to this adapter."""

        return None

    def _manager_plugin_priority(self) -> Optional[int]:
        """Return plugin registration priority pinned to this adapter."""

        return None

    def _manager_bind_plugin_priority(self, priority: int) -> None:
        """Bind manager metadata when this is a stable plugin adapter."""

        del priority

    @abstractmethod
    def get_daily_data(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30,
    ) -> pd.DataFrame:
        """Return normalized daily data for one stock code."""


class BaseFetcher(DataProvider):
    """
    数据源抽象基类
    
    职责：
    1. 定义统一的数据获取接口
    2. 提供数据标准化方法
    3. 实现通用的技术指标计算
    
    子类实现：
    - _fetch_raw_data(): 从具体数据源获取原始数据
    - _normalize_data(): 将原始数据转换为标准格式
    """
    
    name: str = "BaseFetcher"
    priority: int = 99  # Lower priority numbers have higher priority.
    allow_empty_daily_data: bool = False
    
    @abstractmethod
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从数据源获取原始数据（子类必须实现）
        
        Args:
            stock_code: 股票代码，如 '600519', '000001'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            
        Returns:
            原始数据 DataFrame（列名因数据源而异）
        """
        pass
    
    @abstractmethod
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化数据列名（子类必须实现）

        将不同数据源的列名统一为：
        ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        """
        pass

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

    # Rebound from base_parts.daily_pipeline after the class is built.
    get_daily_data = None
    
    _clean_data = None
    
    _calculate_indicators = None
    
    @staticmethod
    def random_sleep(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """
        智能随机休眠（Jitter）
        
        防封禁策略：模拟人类行为的随机延迟
        在请求之间加入不规则的等待时间
        """
        sleep_time = random.uniform(min_seconds, max_seconds)
        logger.debug(f"随机休眠 {sleep_time:.2f} 秒...")
        time.sleep(sleep_time)


class DataFetcherManager:
    """
    数据源策略管理器
    
    职责：
    1. 管理多个数据源（按优先级排序）
    2. 自动故障切换（Failover）
    3. 提供统一的数据获取接口
    
    切换策略：
    - 优先使用高优先级数据源
    - 失败后自动切换到下一个
    - 所有数据源都失败时抛出异常
    """

    # Rebound from _capability_catalog after the compatibility class is built.
    _DAILY_MARKET_FETCHER_SUPPORT = None
    _BUILTIN_DATA_PROVIDER_IDS = None
    _BUILTIN_DATA_PROVIDER_PLUGIN_ID = None
    _DAILY_MARKETS = None
    _daily_source_health = CircuitBreaker(
        failure_threshold=_PROVIDER_CIRCUIT_FAILURE_THRESHOLD_DEFAULT,
        cooldown_seconds=_PROVIDER_CIRCUIT_COOLDOWN_SECONDS_DEFAULT,
        health_window_size=_PROVIDER_HEALTH_WINDOW_SIZE_DEFAULT,
        enabled=_PROVIDER_CIRCUIT_ENABLED_DEFAULT,
    )
    _daily_health_handoff = local()
    _CONCEPT_RANKINGS_CACHE_TTL_SECONDS = 300.0
    _CONCEPT_RANKINGS_EMPTY_CACHE_TTL_SECONDS = 30.0
    _concept_rankings_cache_lock = RLock()
    _concept_rankings_cache: Dict[int, Tuple[float, List[Dict], List[Dict]]] = {}

    def __init__(
        self,
        fetchers: Optional[List[DataProvider]] = None,
        *,
        provider_run_recorder: Optional[Callable[..., None]] = None,
        provider_run_started_recorder: Optional[Callable[..., None]] = None,
        extension_contracts: Optional[Mapping[str, Any]] = None,
    ):
        """
        初始化管理器
        
        Args:
            fetchers: 数据源列表（可选，默认按优先级自动创建）
            provider_run_recorder: Optional diagnostic recorder (defaults to
                production run-diagnostics wiring resolved at construction).
            provider_run_started_recorder: Optional start-event recorder pair.
            extension_contracts: Optional non-data_provider extension contracts
                merged into the manager-owned plugin registry (composition roots
                use this when PLUGIN_DATA_PROVIDER_AUTO_BIND is enabled).
        """
        from .manager_parts.provider_run_wiring import resolve_provider_run_recorders

        (
            self._provider_run_recorder,
            self._provider_run_started_recorder,
        ) = resolve_provider_run_recorders(
            provider_run_recorder,
            provider_run_started_recorder,
        )
        # Align lazy module-level seams with construction defaults without a
        # module-level import of ``src.services.run_diagnostics``.
        global _default_provider_run_recorder, _default_provider_run_started_recorder
        if provider_run_recorder is None and _default_provider_run_recorder is None:
            _default_provider_run_recorder = self._provider_run_recorder
        if (
            provider_run_started_recorder is None
            and _default_provider_run_started_recorder is None
        ):
            _default_provider_run_started_recorder = self._provider_run_started_recorder
        self._configure_daily_source_health()
        self._configure_daily_adaptive_priority()
        from .plugin_registry import _DataProviderPluginRuntime

        self._fetchers: List[DataProvider] = []
        self._fetchers_lock = RLock()
        self._fetchers_by_name: Dict[str, DataProvider] = {}
        self._fetcher_call_locks: Dict[int, RLock] = {}
        self._fetcher_call_locks_lock = RLock()
        self._data_provider_runtime = _DataProviderPluginRuntime(
            self._BUILTIN_DATA_PROVIDER_IDS,
            additional_contracts=extension_contracts,
        )
        self._registered_fetchers: Dict[str, DataProvider] = {}
        self._provider_priorities: Dict[int, int] = {}
        self._fetcher_static_order: Dict[int, int] = {}
        self._next_fetcher_static_order = 0
        self._builtin_provider_handles = []
        self._stock_name_cache: Dict[str, str] = {}
        self._stock_name_cache_lock = RLock()
        self._daily_data_cache: Optional[DailyDataCache] = None
        self._money_flow_cache: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        self._money_flow_cache_lock = RLock()
        self._money_flow_cache_hits = 0
        self._money_flow_cache_misses = 0
        self._money_flow_circuit = CircuitBreaker(
            failure_threshold=2,
            cooldown_seconds=60.0,
            health_window_size=20,
        )
        
        if fetchers:
            # Preserve compatibility-input names and historical priority order.
            self._data_provider_runtime.reserve_provider_names(
                fetcher.name for fetcher in fetchers
            )
            with self._fetchers_lock:
                self._fetchers = list(fetchers)
                for fetcher in self._fetchers:
                    self._assign_fetcher_static_order_locked(fetcher)
                self._sort_fetchers_locked()
                self._refresh_fetcher_indexes_locked()
        else:
            # Default data source will be lazily loaded on first use
            self._init_default_fetchers()
        self._fundamental_adapter = AkshareFundamentalAdapter()
        self._yfinance_fundamental_adapter = YfinanceFundamentalAdapter()
        self._tickflow_fetcher = None
        self._tickflow_api_key: Optional[str] = None
        self._tickflow_lock = RLock()
        self._fundamental_cache: Dict[str, Dict[str, Any]] = {}
        self._fundamental_cache_lock = RLock()
        self._fundamental_inflight: Dict[str, Any] = {}
        self._fundamental_timeout_worker_limit = 8
        self._fundamental_timeout_slots = BoundedSemaphore(self._fundamental_timeout_worker_limit)

    # Rebound from manager_parts.daily_source_health after the class is built.
    _ensure_concurrency_guards = None

    plugin_registry = None
    data_provider_runtime = None
    _assign_fetcher_static_order_locked = None
    _provider_priority = None
    _sort_fetchers_locked = None
    _remove_registered_fetcher_locked = None
    _sync_registered_data_providers = None
    _get_fetchers_snapshot = None
    _provider_plugin_registration = None
    _provider_supports_capability = None
    _get_fetchers_for_capability = None
    _refresh_fetcher_indexes_locked = None
    _get_fetcher_by_name = None
    _call_availability_probe = None
    _is_fetcher_available = None

    _get_fetcher_call_lock = None
    _call_fetcher_method = None

    _filter_daily_fetchers_for_market = None
    _filter_fetchers_by_capability = None

    _daily_health_key = None
    _mark_daily_health_recorded = None
    _consume_daily_health_recorded = None
    _configure_daily_source_health = None
    _configure_daily_adaptive_priority = None
    _daily_adaptive_sort_key = None
    _order_daily_fetchers = None
    _is_daily_source_available = None
    _daily_source_unavailable_error = None
    _record_daily_source_success = None
    _record_daily_source_failure = None
    _next_daily_fallback_name = None
    _next_named_daily_fallback_name = None
    _record_daily_source_circuit_skip = None
    get_daily_source_health_snapshot = None
    get_daily_provider_health_report = None
    log_daily_provider_health_report = None
    reset_daily_source_health = None

    # Rebound from manager_parts.daily_cache_methods after the class is built.
    _get_daily_data_cache = None
    is_market_data_local_only = None
    _daily_adjustment_identity = None
    _daily_cache_key = None
    _record_daily_cache_result = None
    _validate_daily_candidate = None
    get_daily_cache_stats = None
    invalidate_daily_cache = None
    _get_cached_stock_name = None
    _cache_stock_name = None

    # Rebound from manager_parts.tickflow_lifecycle_methods after the class is built.
    _get_tickflow_fetcher = None
    close = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # Best-effort cleanup during interpreter shutdown.
            pass

    # Rebound from manager_parts.belong_board_methods after the class is built.
    _try_scalar_isna = None
    _is_missing_board_value = None
    _normalize_belong_boards = None

    _register_builtin_data_provider = None

    def _init_default_fetchers(self) -> None:
        """
        初始化默认数据源列表

        优先级动态调整逻辑：
        - 如果配置了 TUSHARE_TOKEN：实例化 TushareFetcher，并按其内部逻辑提升优先级
        - 如果配置了 Longbridge OAuth 或 Legacy 凭据：实例化 LongbridgeFetcher 作为美股/港股兜底
        - 未配置的可选数据源不实例化，避免在批量拉取时反复探测无效源
        - 默认优先级：
          0. EfinanceFetcher (Priority 0) - 最高优先级
          1. AkshareFetcher (Priority 1)
          2. PytdxFetcher (Priority 2) - 通达信
          3. BaostockFetcher (Priority 3)
          4. YfinanceFetcher (Priority 4)
          5. TencentFetcher (Priority 5) - A 股最终兜底
        """
        from src.config import get_config
        from .efinance_fetcher import EfinanceFetcher
        from .tencent_fetcher import TencentFetcher
        from .akshare_fetcher import AkshareFetcher
        from .tushare_fetcher import TushareFetcher
        from .tickflow_fetcher import TickFlowFetcher
        from .pytdx_fetcher import PytdxFetcher
        from .baostock_fetcher import BaostockFetcher
        from .yfinance_fetcher import YfinanceFetcher
        from .longbridge_fetcher import LongbridgeFetcher
        config = get_config()
        # Create all data source instances (priority is determined in each Fetcher's __init__)
        efinance = EfinanceFetcher()
        tencent = TencentFetcher()
        akshare = AkshareFetcher()
        pytdx = PytdxFetcher()      # Tongdaxin data source (configurable with PYTDX_HOST/PYTDX_PORT)
        baostock = BaostockFetcher()
        yfinance = YfinanceFetcher()
        optional_fetchers: List[BaseFetcher] = []

        tushare_token = (getattr(config, "tushare_token", None) or "").strip()
        if tushare_token:
            optional_fetchers.append(TushareFetcher())  # Automatically adjusts priority when a token is configured
        else:
            logger.debug("[数据源初始化] 跳过未配置的 TushareFetcher")

        tickflow_api_key = (getattr(config, "tickflow_api_key", None) or "").strip()
        if tickflow_api_key:
            optional_fetchers.append(
                TickFlowFetcher(
                    api_key=tickflow_api_key,
                    kline_adjust=getattr(config, "tickflow_kline_adjust", "none"),
                    batch_daily_enabled=getattr(config, "tickflow_batch_daily_enabled", True),
                    batch_size=getattr(config, "tickflow_batch_size", 100),
                    priority=getattr(config, "tickflow_priority", 2),
                )
            )
        else:
            logger.debug("[data source init] skip TickFlowFetcher because TICKFLOW_API_KEY is not configured")

        if LongbridgeFetcher.has_configured_credentials(config):
            optional_fetchers.append(LongbridgeFetcher())  # Longbridge (U.S./Hong Kong stock fallback, lazy loading)
        else:
            logger.debug("[数据源初始化] 跳过未配置的 LongbridgeFetcher")

        finnhub_api_key = (getattr(config, "finnhub_api_key", None) or "").strip()
        if finnhub_api_key:
            from .finnhub_fetcher import FinnhubFetcher
            optional_fetchers.append(FinnhubFetcher())
        else:
            logger.debug("[数据源初始化] 跳过未配置的 FinnhubFetcher")

        alphavantage_api_key = (getattr(config, "alphavantage_api_key", None) or "").strip()
        if alphavantage_api_key:
            from .alphavantage_fetcher import AlphaVantageFetcher
            optional_fetchers.append(AlphaVantageFetcher())
        else:
            logger.debug("[数据源初始化] 跳过未配置的 AlphaVantageFetcher")

        for fetcher in (
            efinance,
            akshare,
            pytdx,
            baostock,
            yfinance,
            tencent,
            *optional_fetchers,
        ):
            self._register_builtin_data_provider(fetcher)

        # The provider is default-off and must only be activated by an explicit
        # boolean value.  Partial config doubles (and older config objects) may
        # synthesize truthy attributes for unknown fields.
        if getattr(config, "crypto_provider_enabled", False) is True:
            from .crypto_coingecko_fetcher import build_crypto_provider_registration

            crypto_registration = build_crypto_provider_registration(config=config)
            self._builtin_provider_handles.append(
                self._data_provider_runtime.register_builtin(
                    registration=crypto_registration,
                    priority=getattr(config, "crypto_coingecko_priority", 10),
                    plugin_id=self._BUILTIN_DATA_PROVIDER_PLUGIN_ID,
                )
            )
        else:
            logger.debug("[data source init] skip CoinGecko because crypto provider is disabled")
        self._sync_registered_data_providers()

        # Build the priority summary from the synchronized registry snapshot.
        priority_info = ", ".join(
            f"{fetcher.name}(P{self._provider_priority(fetcher)})"
            for fetcher in self._get_fetchers_snapshot()
        )
        logger.info(f"已初始化 {len(self._fetchers)} 个数据源（按优先级）: {priority_info}")
    
    add_fetcher = None

    available_fetchers = None
    
    def prefetch_realtime_quotes(self, stock_codes: List[str]) -> int:
        """
        批量预取实时行情数据（在分析开始前调用）
        
        策略：
        1. 检查优先级中是否包含适合预取的数据源（efinance/akshare_em/tushare/tickflow）
        2. 如果不包含，跳过预取（新浪/腾讯是单股票查询，无需预取）
        3. 如果自选股数量 >= 5 且使用可预取数据源，则预取填充缓存
        
        这样做的好处：
        - 使用新浪/腾讯时：每只股票独立查询，无全量拉取问题
        - 使用 efinance/东财/Tushare 时：预取一次，后续缓存命中
        - 使用 TickFlow 时：按当前自选股批量预取，避免逐股重复请求
        
        Args:
            stock_codes: 待分析的股票代码列表
            
        Returns:
            预取的股票数量（0 表示跳过预取）
        """
        if self.is_market_data_local_only():
            logger.debug(
                "[prefetch] component=realtime_prefetch action=skip reason=local_only"
            )
            return 0

        # Normalize all codes
        stock_codes = [normalize_stock_code(c) for c in stock_codes]

        from src.config import get_config

        config = get_config()

        # Issue #455: PREFETCH_REALTIME_QUOTES=false Can disable pre-fetching, Avoid pulling the entire market
        if not getattr(config, "prefetch_realtime_quotes", True):
            logger.debug("[预取] component=realtime_prefetch action=skip reason=disabled")
            return 0

        # If real-time market data is disabled, skip prefetching.
        if not config.enable_realtime_quote:
            logger.debug("[预取] component=realtime_prefetch action=skip reason=realtime_quote_disabled")
            return 0
        
        # Check if priority includes suitable data sources for batch prefetching
        # efinance/akshare_em/tushare Populate the full market cache with a single call.;
        # tickflow retrieves current watchlist stocks in cache via symbols batch interface.
        priority = config.realtime_source_priority.lower()
        prefetch_sources = ['efinance', 'akshare_em', 'tushare', 'tickflow']
        
        # If the top two sources in priority are not prefetchable data sources, skip prefetch
        # Since Sina/ Tencent are single-stock queries, no prefetching is needed
        priority_list = [s.strip() for s in priority.split(',')]
        first_prefetch_source_index = None
        for i, source in enumerate(priority_list):
            if source in prefetch_sources:
                first_prefetch_source_index = i
                break
        
        # If no cacheable data source is available or it ranks after the 3rd position, skip fetching.
        if first_prefetch_source_index is None or first_prefetch_source_index >= 2:
            logger.info(
                "[预取] component=realtime_prefetch action=skip reason=no_early_prefetch_source priority=%s",
                priority,
            )
            return 0
        
        # If the number of stocks is less than 5, do not perform batch fetching (individual queries are more efficient).
        if len(stock_codes) < 5:
            logger.info(
                "[预取] component=realtime_prefetch action=skip reason=small_batch "
                "stock_count=%d threshold=5 prefetch_source=%s",
                len(stock_codes),
                priority_list[first_prefetch_source_index],
            )
            return 0
        
        prefetch_source = priority_list[first_prefetch_source_index]
        logger.info(
            "[预取] component=realtime_prefetch action=start stock_count=%d prefetch_source=%s first_code=%s",
            len(stock_codes),
            prefetch_source,
            stock_codes[0],
        )
        
        # TickFlow uses symbols batch interface; other prefetch sources trigger their own cache upon the first query.
        if prefetch_source == "tickflow":
            fetcher = self._get_fetcher_by_name("TickFlowFetcher", capability="realtime_quote")
            if fetcher is None or not hasattr(fetcher, "prefetch_realtime_quotes"):
                logger.info(
                    "[prefetch] component=realtime_prefetch action=skip reason=tickflow_unavailable"
                )
                return 0
            try:
                return int(
                    self._call_fetcher_method(
                        fetcher,
                        "prefetch_realtime_quotes",
                        stock_codes,
                        batch_size=getattr(config, "tickflow_batch_size", 100),
                    )
                    or 0
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Safe diagnostics preserve per-symbol fallback after optional TickFlow prefetch fails.
                log_safe_exception(
                    logger,
                    "TickFlow realtime quote prefetch failed",
                    exc,
                    error_code="tickflow_realtime_prefetch_failed",
                    level=logging.WARNING,
                )
                return 0

        try:
            # Use the first stock to trigger full data pull.
            first_code = stock_codes[0]
            quote = self.get_realtime_quote(first_code)
            
            if quote:
                logger.info(
                    "[预取] component=realtime_prefetch action=complete status=success "
                    "stock_count=%d prefetch_source=%s",
                    len(stock_codes),
                    prefetch_source,
                )
                return len(stock_codes)
            else:
                logger.warning(
                    "[预取] component=realtime_prefetch action=complete status=failed "
                    "stock_count=%d prefetch_source=%s fallback=per_stock",
                    len(stock_codes),
                    prefetch_source,
                )
                return 0
                
        except Exception as e:  # broad-exception: fallback_recorded - Safe diagnostics preserve per-symbol fallback after optional realtime prefetch fails.
            log_safe_exception(
                logger,
                "Realtime quote prefetch failed",
                e,
                error_code="realtime_quote_prefetch_failed",
                level=logging.ERROR,
                context={"provider": prefetch_source},
            )
            return 0

    def prefetch_daily_klines(self, stock_codes: List[str], days: int = 30) -> int:
        """Batch-prefetch TickFlow daily K-lines without changing per-stock callers."""
        if self.is_market_data_local_only():
            logger.debug(
                "[prefetch] component=daily_kline_prefetch action=skip reason=local_only"
            )
            return 0
        fetcher = self._get_fetcher_by_name("TickFlowFetcher", capability="daily_data")
        if fetcher is None or not hasattr(fetcher, "prefetch_daily_klines"):
            return 0

        try:
            return int(
                self._call_fetcher_method(
                    fetcher,
                    "prefetch_daily_klines",
                    stock_codes,
                    days=days,
                )
                or 0
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Safe diagnostics preserve per-symbol fallback after optional daily prefetch fails.
            log_safe_exception(
                logger,
                "TickFlow daily K-line prefetch failed",
                exc,
                error_code="tickflow_daily_kline_prefetch_failed",
                level=logging.WARNING,
            )
            return 0

    # Rebound from manager_parts.realtime_field_trust_methods after class build.
    # Rebound from manager_parts.realtime_quote_methods after class build.

    # Fields worth supplementing from secondary sources when the primary
    # source returns None for them. Ordered by importance.
    _SUPPLEMENT_FIELDS = [
        'volume_ratio', 'turnover_rate',
        'pe_ratio', 'pb_ratio', 'total_mv', 'circ_mv',
        'amplitude',
        # ETF premium/discount references (Issue #173); optional when any source has them.
        'iopv', 'nav',
    ]

    # Rebound from manager_parts.chip_distribution_methods after class build.
    get_chip_distribution = None

    _MONEY_FLOW_CACHE_TTL_SECONDS = 600.0
    _MONEY_FLOW_STALE_TTL_SECONDS = 86400.0
    _MONEY_FLOW_CACHE_MAX_ENTRIES = 256

    # Rebound from manager_parts.money_flow_methods after the class is built.
    _money_flow_timestamp = None
    get_money_flow = None

    # Rebound from manager_parts.stock_name_methods after the class is built.
    get_stock_name = None

    # Rebound from manager_parts.belong_board_methods after the class is built.
    get_belong_boards = None

    # Rebound from manager_parts.stock_name_methods after the class is built.
    prefetch_stock_names = None
    batch_get_stock_names = None

    # Rebound from manager_parts.market_overview_methods after the class is built.
    get_main_indices = None
    get_market_stats = None

    # Rebound from manager_parts.fundamental_timeout_methods after the class is built.
    _run_with_timeout = None
    _run_with_retry = None

    _get_fundamental_config = None  # rebound from manager_parts.fundamental_context_methods

    # Rebound from manager_parts.fundamental_payload_methods after the class is built.
    _normalize_source_chain = None
    _block_status = None
    _build_fundamental_block = None
    _has_meaningful_payload = None
    _infer_block_status = None
    _should_cache_fundamental_context = None
    _build_market_not_supported = None

    # Rebound from manager_parts.fundamental_loader_methods after the class is built.
    _build_offshore_fundamental_context = None

    # Rebound from manager_parts.fundamental_outcome_methods after the class is built.
    build_failed_fundamental_context = None
    build_validation_rejected_fundamental_context = None

    # Rebound from manager_parts.fundamental_loader_methods after the class is built.
    get_fundamental_context = None

    # Rebound from manager_parts.fundamental_cn_context_methods after the class is built.
    get_capital_flow_context = None
    get_dragon_tiger_context = None
    get_board_context = None

    # Rebound from manager_parts.rankings_methods after the class is built.
    _get_sector_rankings_with_meta = None
    get_sector_rankings = None
    _copy_ranking_rows = None
    clear_concept_rankings_cache_for_tests = None
    get_concept_rankings = None
    get_hot_stocks = None
    get_limit_up_pool = None


# Keep ``src.data_provider.base.DataFetcherManager`` as the ADR-006 compatibility
# facade while focused parts own inventory, daily health/cache/execution, realtime,
# chip, money-flow, fundamental cache/loaders/Config accessor/CN sub-blocks/
# payload helpers, timeout/retry workers, failed/rejected outcome builders,
# stock-name, rankings, TickFlow lifecycle, market-overview, and belong-board.
# Rebinding preserves method globals and patch seams.
from . import _capability_catalog as _capability_catalog_module  # noqa: E402
from .manager_parts import daily_cache_methods as _daily_cache_methods_module  # noqa: E402
from .manager_parts import daily_source_health as _daily_source_health_module  # noqa: E402
from .manager_parts import (  # noqa: E402
    belong_board_methods as _belong_board_methods_module,
    chip_distribution_methods as _chip_distribution_methods_module,
    daily_provider_execution as _daily_provider_execution_module,
    fundamental_cache_methods as _fundamental_cache_methods_module,
    fundamental_cn_context_methods as _fundamental_cn_context_methods_module,
    fundamental_context_methods as _fundamental_context_methods_module,
    fundamental_loader_methods as _fundamental_loader_methods_module,
    fundamental_outcome_methods as _fundamental_outcome_methods_module,
    fundamental_payload_methods as _fundamental_payload_methods_module,
    fundamental_timeout_methods as _fundamental_timeout_methods_module,
    market_overview_methods as _market_overview_methods_module,
    money_flow_cache_methods as _money_flow_cache_methods_module,
    money_flow_methods as _money_flow_methods_module,
    rankings_methods as _rankings_methods_module,
    realtime_field_trust_methods as _realtime_field_trust_methods_module,
    realtime_quote_methods as _realtime_quote_methods_module,
    stock_name_methods as _stock_name_methods_module,
    tickflow_lifecycle_methods as _tickflow_lifecycle_methods_module,
)

_EXPECTED_CAPABILITY_CATALOG_METHOD_NAMES = (
    "plugin_registry",
    "data_provider_runtime",
    "_assign_fetcher_static_order_locked",
    "_provider_priority",
    "_sort_fetchers_locked",
    "_remove_registered_fetcher_locked",
    "_sync_registered_data_providers",
    "_get_fetchers_snapshot",
    "_provider_plugin_registration",
    "_provider_supports_capability",
    "_get_fetchers_for_capability",
    "_refresh_fetcher_indexes_locked",
    "_get_fetcher_by_name",
    "_call_availability_probe",
    "_is_fetcher_available",
    "_filter_daily_fetchers_for_market",
    "_filter_fetchers_by_capability",
    "_register_builtin_data_provider",
    "add_fetcher",
    "available_fetchers",
)


def _assemble_capability_catalog_facade(
    catalog_module=_capability_catalog_module,
    expected_method_names=_EXPECTED_CAPABILITY_CATALOG_METHOD_NAMES,
) -> None:
    constant_names = catalog_module._reset_capability_inventory()
    for constant_name in constant_names:
        setattr(
            DataFetcherManager,
            constant_name,
            getattr(catalog_module, constant_name),
        )

    bound_method_names = catalog_module.bind_capability_catalog_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != expected_method_names:
        raise ImportError(
            "Unexpected DataFetcherManager capability catalog methods: "
            f"{bound_method_names!r}"
        )


def _assemble_daily_source_health_facade(
    health_module=_daily_source_health_module,
) -> None:
    bound_method_names = health_module.bind_daily_source_health_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != health_module.EXPECTED_DAILY_SOURCE_HEALTH_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager daily source health methods: "
            f"{bound_method_names!r}"
        )


def _assemble_daily_cache_methods_facade(
    cache_module=_daily_cache_methods_module,
) -> None:
    bound_method_names = cache_module.bind_daily_cache_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != cache_module.EXPECTED_DAILY_CACHE_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager daily cache methods: "
            f"{bound_method_names!r}"
        )


def _assemble_daily_provider_execution_facade(
    execution_module=_daily_provider_execution_module,
) -> None:
    bound_method_names = execution_module.bind_daily_provider_execution_facade(
        DataFetcherManager,
        globals(),
    )
    if (
        bound_method_names
        != execution_module.EXPECTED_DAILY_PROVIDER_EXECUTION_METHOD_NAMES
    ):
        raise ImportError(
            "Unexpected DataFetcherManager daily provider execution methods: "
            f"{bound_method_names!r}"
        )


def _assemble_realtime_field_trust_methods_facade(
    realtime_module=_realtime_field_trust_methods_module,
) -> None:
    bound_method_names = realtime_module.bind_realtime_field_trust_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if (
        bound_method_names
        != realtime_module.EXPECTED_REALTIME_FIELD_TRUST_METHOD_NAMES
    ):
        raise ImportError(
            "Unexpected DataFetcherManager realtime field-trust methods: "
            f"{bound_method_names!r}"
        )


def _assemble_realtime_quote_methods_facade(
    quote_module=_realtime_quote_methods_module,
) -> None:
    bound_method_names = quote_module.bind_realtime_quote_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != quote_module.EXPECTED_REALTIME_QUOTE_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager realtime quote methods: "
            f"{bound_method_names!r}"
        )


def _assemble_chip_distribution_methods_facade(
    chip_module=_chip_distribution_methods_module,
) -> None:
    bound_method_names = chip_module.bind_chip_distribution_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != chip_module.EXPECTED_CHIP_DISTRIBUTION_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager chip-distribution methods: "
            f"{bound_method_names!r}"
        )


def _assemble_stock_name_methods_facade(
    stock_name_module=_stock_name_methods_module,
) -> None:
    bound_method_names = stock_name_module.bind_stock_name_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != stock_name_module.EXPECTED_STOCK_NAME_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager stock-name methods: "
            f"{bound_method_names!r}"
        )


def _assemble_money_flow_cache_methods_facade(
    cache_module=_money_flow_cache_methods_module,
) -> None:
    bound_method_names = cache_module.bind_money_flow_cache_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != cache_module.EXPECTED_MONEY_FLOW_CACHE_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager money-flow cache methods: "
            f"{bound_method_names!r}"
        )


def _assemble_money_flow_methods_facade(
    money_flow_module=_money_flow_methods_module,
) -> None:
    bound_method_names = money_flow_module.bind_money_flow_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != money_flow_module.EXPECTED_MONEY_FLOW_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager money-flow methods: "
            f"{bound_method_names!r}"
        )


def _assemble_fundamental_cache_methods_facade(
    cache_module=_fundamental_cache_methods_module,
) -> None:
    bound_method_names = cache_module.bind_fundamental_cache_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != cache_module.EXPECTED_FUNDAMENTAL_CACHE_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager fundamental cache methods: "
            f"{bound_method_names!r}"
        )


def _assemble_fundamental_loader_methods_facade(
    loader_module=_fundamental_loader_methods_module,
) -> None:
    bound_method_names = loader_module.bind_fundamental_loader_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != loader_module.EXPECTED_FUNDAMENTAL_LOADER_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager fundamental loader methods: "
            f"{bound_method_names!r}"
        )


def _assemble_fundamental_context_methods_facade(context_module=_fundamental_context_methods_module) -> None:
    bound = context_module.bind_fundamental_context_methods_facade(DataFetcherManager, globals())
    if bound != context_module.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES:
        raise ImportError(f"Unexpected DataFetcherManager fundamental context methods: {bound!r}")


def _assemble_fundamental_cn_context_methods_facade(
    cn_context_module=_fundamental_cn_context_methods_module,
) -> None:
    bound_method_names = cn_context_module.bind_fundamental_cn_context_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != cn_context_module.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager CN fundamental context methods: "
            f"{bound_method_names!r}"
        )


def _assemble_belong_board_methods_facade(
    board_module=_belong_board_methods_module,
) -> None:
    bound_method_names = board_module.bind_belong_board_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != board_module.EXPECTED_BELONG_BOARD_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager belong-board methods: "
            f"{bound_method_names!r}"
        )


def _assemble_fundamental_payload_methods_facade(
    payload_module=_fundamental_payload_methods_module,
) -> None:
    bound_method_names = payload_module.bind_fundamental_payload_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != payload_module.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager fundamental payload methods: "
            f"{bound_method_names!r}"
        )


def _assemble_fundamental_timeout_methods_facade(
    timeout_module=_fundamental_timeout_methods_module,
) -> None:
    bound_method_names = timeout_module.bind_fundamental_timeout_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != timeout_module.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager fundamental timeout methods: "
            f"{bound_method_names!r}"
        )


def _assemble_fundamental_outcome_methods_facade(
    outcome_module=_fundamental_outcome_methods_module,
) -> None:
    bound_method_names = outcome_module.bind_fundamental_outcome_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != outcome_module.EXPECTED_FUNDAMENTAL_OUTCOME_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager fundamental outcome methods: "
            f"{bound_method_names!r}"
        )


def _assemble_rankings_methods_facade(
    rankings_module=_rankings_methods_module,
) -> None:
    bound_method_names = rankings_module.bind_rankings_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if bound_method_names != rankings_module.EXPECTED_RANKINGS_METHOD_NAMES:
        raise ImportError(
            "Unexpected DataFetcherManager rankings methods: "
            f"{bound_method_names!r}"
        )


def _assemble_tickflow_lifecycle_methods_facade(
    tickflow_lifecycle_module=_tickflow_lifecycle_methods_module,
) -> None:
    bound_method_names = tickflow_lifecycle_module.bind_tickflow_lifecycle_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if (
        bound_method_names
        != tickflow_lifecycle_module.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES
    ):
        raise ImportError(
            "Unexpected DataFetcherManager TickFlow lifecycle methods: "
            f"{bound_method_names!r}"
        )


def _assemble_market_overview_methods_facade(
    market_overview_module=_market_overview_methods_module,
) -> None:
    bound_method_names = market_overview_module.bind_market_overview_methods_facade(
        DataFetcherManager,
        globals(),
    )
    if (
        bound_method_names
        != market_overview_module.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES
    ):
        raise ImportError(
            "Unexpected DataFetcherManager market-overview methods: "
            f"{bound_method_names!r}"
        )


def _assemble_data_fetcher_manager_facades(
    assemble_capability=_assemble_capability_catalog_facade,
    assemble_health=_assemble_daily_source_health_facade,
    assemble_daily_cache=_assemble_daily_cache_methods_facade,
    assemble_daily_execution=_assemble_daily_provider_execution_facade,
    assemble_realtime=_assemble_realtime_field_trust_methods_facade,
    assemble_realtime_quote=_assemble_realtime_quote_methods_facade,
    assemble_chip=_assemble_chip_distribution_methods_facade,
    assemble_stock_name=_assemble_stock_name_methods_facade,
    assemble_money_flow=_assemble_money_flow_cache_methods_facade,
    assemble_money_flow_methods=_assemble_money_flow_methods_facade,
    assemble_fundamental=_assemble_fundamental_cache_methods_facade,
    assemble_fundamental_loaders=_assemble_fundamental_loader_methods_facade,
    assemble_fundamental_context=_assemble_fundamental_context_methods_facade,
    assemble_fundamental_cn_context=_assemble_fundamental_cn_context_methods_facade,
    assemble_belong_board=_assemble_belong_board_methods_facade,
    assemble_fundamental_payload=_assemble_fundamental_payload_methods_facade,
    assemble_fundamental_timeout=_assemble_fundamental_timeout_methods_facade,
    assemble_fundamental_outcome=_assemble_fundamental_outcome_methods_facade,
    assemble_rankings=_assemble_rankings_methods_facade,
    assemble_tickflow_lifecycle=_assemble_tickflow_lifecycle_methods_facade,
    assemble_market_overview=_assemble_market_overview_methods_facade,
) -> None:
    assemble_capability()
    assemble_health()
    assemble_daily_cache()
    assemble_daily_execution()
    assemble_realtime()
    assemble_realtime_quote()
    assemble_chip()
    assemble_stock_name()
    assemble_money_flow()
    assemble_money_flow_methods()
    assemble_fundamental()
    assemble_fundamental_loaders()
    assemble_fundamental_context()
    assemble_fundamental_cn_context()
    assemble_belong_board()
    assemble_fundamental_payload()
    assemble_fundamental_timeout()
    assemble_fundamental_outcome()
    assemble_rankings()
    assemble_tickflow_lifecycle()
    assemble_market_overview()
    from .manager_parts.data_validation_wiring import install_facade_validation_wrappers
    install_facade_validation_wrappers(DataFetcherManager)


_assemble_data_fetcher_manager_facades()
_capability_catalog_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_daily_source_health_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_daily_cache_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_daily_provider_execution_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_realtime_field_trust_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_realtime_quote_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_chip_distribution_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_stock_name_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_money_flow_cache_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_money_flow_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_fundamental_cache_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_fundamental_loader_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_fundamental_context_methods_module._install_facade_reload_hook(_assemble_data_fetcher_manager_facades)
_fundamental_cn_context_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_belong_board_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_fundamental_payload_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_fundamental_timeout_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_fundamental_outcome_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_rankings_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_tickflow_lifecycle_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)
_market_overview_methods_module._install_facade_reload_hook(
    _assemble_data_fetcher_manager_facades
)

del (
    _EXPECTED_CAPABILITY_CATALOG_METHOD_NAMES,
    _assemble_capability_catalog_facade,
    _assemble_daily_source_health_facade,
    _assemble_daily_cache_methods_facade,
    _assemble_daily_provider_execution_facade,
    _assemble_realtime_field_trust_methods_facade,
    _assemble_realtime_quote_methods_facade,
    _assemble_chip_distribution_methods_facade,
    _assemble_stock_name_methods_facade,
    _assemble_money_flow_cache_methods_facade,
    _assemble_money_flow_methods_facade,
    _assemble_fundamental_cache_methods_facade,
    _assemble_fundamental_loader_methods_facade,
    _assemble_fundamental_context_methods_facade,
    _assemble_fundamental_cn_context_methods_facade,
    _assemble_belong_board_methods_facade,
    _assemble_fundamental_payload_methods_facade,
    _assemble_fundamental_timeout_methods_facade,
    _assemble_fundamental_outcome_methods_facade,
    _assemble_rankings_methods_facade,
    _assemble_tickflow_lifecycle_methods_facade,
    _assemble_market_overview_methods_facade,
    _assemble_data_fetcher_manager_facades,
    _capability_catalog_module,
    _daily_source_health_module,
    _daily_cache_methods_module,
    _daily_provider_execution_module,
    _realtime_field_trust_methods_module,
    _realtime_quote_methods_module,
    _chip_distribution_methods_module,
    _stock_name_methods_module,
    _money_flow_cache_methods_module,
    _money_flow_methods_module,
    _rankings_methods_module,
    _tickflow_lifecycle_methods_module,
    _market_overview_methods_module,
    _fundamental_cache_methods_module,
    _fundamental_loader_methods_module,
    _fundamental_context_methods_module,
    _fundamental_cn_context_methods_module,
    _belong_board_methods_module,
    _fundamental_payload_methods_module,
    _fundamental_timeout_methods_module,
    _fundamental_outcome_methods_module,
)


# ``base_parts.daily_pipeline`` owns the BaseFetcher daily template method.
# Rebinding preserves method globals so existing patches against this module
# continue to intercept moved implementations, and every provider subclass
# inherits the rebound descriptors unchanged.
from .base_parts import daily_pipeline as _daily_pipeline_module  # noqa: E402
from .base_parts.daily_pipeline import _DailyPipelineMethods  # noqa: E402
from .base_parts.facade_bind import bind_methods_from_class as _bind_base_parts  # noqa: E402


def _assemble_base_fetcher_facade() -> None:
    """Bind capability-domain method bodies onto the abstract base class."""

    _bind_base_parts(
        _DailyPipelineMethods,
        BaseFetcher,
        globals(),
        expected_names=_daily_pipeline_module.EXPECTED_DAILY_PIPELINE_METHOD_NAMES,
    )


_assemble_base_fetcher_facade()


def _install_base_parts_reload_hooks() -> None:
    """Keep an owner reload able to rebuild and rebind both sides of the seam."""

    for module in (_daily_pipeline_module,):
        module._FACADE_RELOAD_HOOK = _assemble_base_fetcher_facade  # type: ignore[attr-defined]


_install_base_parts_reload_hooks()
