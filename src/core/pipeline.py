# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 核心分析流水线
===================================

职责：
1. 管理整个分析流程
2. 协调数据获取、存储、搜索、分析、通知等模块
3. 实现并发控制和异常处理
4. 提供股票分析的核心功能
"""

import logging
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from types import FunctionType as _FunctionType, SimpleNamespace
from typing import List, Dict, Any, Optional, Tuple, Callable

import pandas as pd

from src.config import FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT, get_config, Config
from src.storage import get_db
from data_provider import DataFetcherManager
from data_provider.base import is_bse_code, normalize_stock_code
from data_provider.realtime_types import ChipDistribution
from src.analyzer import (
    GeminiAnalyzer,
    AnalysisResult,
    fill_price_position_if_needed,
    normalize_chip_structure_availability,
    populate_decision_action_fields,
    stabilize_decision_with_structure,
)
from src.notification import NotificationService, NotificationChannel
from src.report_language import (
    get_placeholder_text,
    get_unknown_text,
    infer_decision_type_from_advice,
    localize_confidence_level,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)
from src.search_service import SearchService
from src.analysis_context_pack_prompt import format_analysis_context_pack_prompt_section
from src.analysis_context_pack_overview import render_analysis_context_pack_overview
from src.market_phase_summary import MARKET_PHASE_SUMMARY_KEY, render_market_phase_summary
from src.daily_market_context_guardrail import apply_daily_market_context_guardrail
from src.phase_decision_guardrail import apply_phase_decision_guardrails
from src.services.daily_market_context import (
    DailyMarketContext,
    DailyMarketContextService,
    format_daily_market_context_prompt_section,
)
from src.services.social_sentiment_service import SocialSentimentService
from src.services.intelligence_service import IntelligenceService
from src.services.market_hotspot_service import MarketHotspotService
from src.services.analysis_context_builder import (
    AnalysisContextBuilder,
    PipelineAnalysisArtifacts,
)
from src.services.market_structure_service import MarketStructureService
from src.services.run_diagnostics import (
    PIPELINE_STAGE_NAMES,
    PipelineStageObservation,
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    get_current_diagnostic_context,
    observe_pipeline_stage,
    record_history_run,
    record_llm_run,
    record_llm_run_started,
    record_missing_pipeline_stages_as_skipped,
    record_notification_run,
    record_pipeline_stage,
    reset_run_diagnostic_context,
    sanitize_diagnostic_text,
)
from src.services.decision_signal_extractor import extract_and_persist_from_analysis_result
from src.services.decision_signal_summary import summarize_decision_signal
from src.schemas.request_context import AnalysisRequestContext
from src.utils.sanitize import log_safe_exception
from src.enums import ReportType
from src.stock_analyzer import StockTrendAnalyzer, TrendAnalysisResult
from src.core.trading_calendar import (
    build_market_phase_context,
    get_effective_trading_date,
    get_market_for_stock,
    get_market_now,
    is_market_open,
)
from src.core.pipeline_stage_results import (
    PipelinePersistValue,
    PipelineStageName,
    PipelineStageResult,
    PipelineStageRunner,
    PipelineStageStatus,
)
from src.core.stages.analysis import _AnalysisStageMixin
from src.core.stages.delivery import (
    _DeliveryStageMixin,
    _SINGLE_STOCK_NOTIFY_LOCK_INIT_GUARD,
)
from src.core.stages.orchestration import _OrchestrationStageMixin
from src.core.stages.persistence import (
    _PersistenceStageMixin,
    _symbol_scope_lookup_values,
)
from data_provider.us_index_mapping import is_us_stock_code
logger = logging.getLogger(__name__)

# Keep legacy module exports alive while concrete stages move behind the facade.
_PIPELINE_COMPAT_EXPORTS = (
    activate_run_diagnostic_context,
    AnalysisContextBuilder,
    AnalysisResult,
    apply_daily_market_context_guardrail,
    apply_phase_decision_guardrails,
    as_completed,
    build_market_phase_context,
    ChipDistribution,
    current_diagnostic_snapshot,
    DailyMarketContext,
    DailyMarketContextService,
    date,
    datetime,
    defaultdict,
    ExitStack,
    extract_and_persist_from_analysis_result,
    fill_price_position_if_needed,
    format_daily_market_context_prompt_section,
    format_analysis_context_pack_prompt_section,
    FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
    get_current_diagnostic_context,
    get_effective_trading_date,
    get_market_for_stock,
    get_market_now,
    get_placeholder_text,
    get_unknown_text,
    infer_decision_type_from_advice,
    IntelligenceService,
    is_bse_code,
    is_market_open,
    is_us_stock_code,
    localize_confidence_level,
    localize_operation_advice,
    localize_trend_prediction,
    MARKET_PHASE_SUMMARY_KEY,
    normalize_chip_structure_availability,
    normalize_report_language,
    normalize_stock_code,
    NotificationChannel,
    observe_pipeline_stage,
    pd,
    PIPELINE_STAGE_NAMES,
    PipelineAnalysisArtifacts,
    PipelinePersistValue,
    PipelineStageName,
    PipelineStageObservation,
    PipelineStageResult,
    PipelineStageStatus,
    populate_decision_action_fields,
    record_history_run,
    record_llm_run,
    record_llm_run_started,
    record_missing_pipeline_stages_as_skipped,
    record_notification_run,
    record_pipeline_stage,
    render_analysis_context_pack_overview,
    render_market_phase_summary,
    ReportType,
    reset_run_diagnostic_context,
    sanitize_diagnostic_text,
    SimpleNamespace,
    stabilize_decision_with_structure,
    summarize_decision_signal,
    ThreadPoolExecutor,
    time,
    timedelta,
    timezone,
    TrendAnalysisResult,
    uuid,
    _SINGLE_STOCK_NOTIFY_LOCK_INIT_GUARD,
    _symbol_scope_lookup_values,
)

# 防御性 guard：当实例绕过 __init__（如测试中 __new__）构造时，
# double-check 初始化 _single_stock_notify_lock 仍然线程安全。
_DAILY_MARKET_CONTEXT_SERVICE_LOCK_INIT_GUARD = threading.Lock()
_PIPELINE_STAGE_RUNNER_INIT_GUARD = threading.Lock()
_DEFER_PIPELINE_DELIVERY_OBSERVATION: ContextVar[bool] = ContextVar(
    "defer_pipeline_delivery_observation",
    default=False,
)


class StockAnalysisPipeline:
    """
    股票分析主流程调度器
    
    职责：
    1. 管理整个分析流程
    2. 协调数据获取、存储、搜索、分析、通知等模块
    3. 实现并发控制和异常处理
    """
    
    def __init__(
        self,
        config: Optional[Config] = None,
        max_workers: Optional[int] = None,
        request_context: Optional[AnalysisRequestContext] = None,
        query_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        query_source: Optional[str] = None,
        save_context_snapshot: Optional[bool] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        analysis_skills: Optional[List[str]] = None,
        analysis_phase: str = "auto",
        portfolio_context: Optional[Dict[str, Any]] = None,
        daily_market_context_enabled: Optional[bool] = None,
        daily_market_context_allow_generate: bool = True,
    ):
        """Initialize the analysis pipeline and its request-scoped services.

        Args:
            config: Optional runtime configuration; defaults to the global config.
            max_workers: Optional worker count; defaults to the configured value.
            request_context: Immutable requester provenance and contextual reply targets.
        """
        self.config = config or get_config()
        self.max_workers = max_workers or self.config.max_workers
        self.request_context = request_context
        self.query_id = query_id
        self.trace_id = trace_id or query_id
        self.query_source = self._resolve_query_source(query_source)
        self.save_context_snapshot = (
            self.config.save_context_snapshot if save_context_snapshot is None else save_context_snapshot
        )
        self.progress_callback = progress_callback
        self.analysis_skills = list(analysis_skills) if analysis_skills is not None else None
        self.analysis_phase = analysis_phase or "auto"
        self.portfolio_context = dict(portfolio_context) if isinstance(portfolio_context, dict) else None
        self.daily_market_context_enabled = (
            bool(getattr(self.config, "daily_market_context_enabled", True))
            if daily_market_context_enabled is None
            else bool(daily_market_context_enabled)
        )
        self.daily_market_context_allow_generate = daily_market_context_allow_generate
        
        # 初始化各模块
        self.db = get_db()
        self.fetcher_manager = DataFetcherManager()
        # 不再单独创建 akshare_fetcher，统一使用 fetcher_manager 获取增强数据
        self.trend_analyzer = StockTrendAnalyzer()  # 技术分析器
        self.analyzer = GeminiAnalyzer(config=self.config, skills=self.analysis_skills)
        self.notifier = NotificationService(request_context=request_context)
        self.market_structure_service = MarketStructureService(fetcher_manager=self.fetcher_manager)
        self.market_hotspot_service: Optional[MarketHotspotService] = None
        try:
            self.market_hotspot_service = MarketHotspotService(
                fetcher_manager=self.fetcher_manager,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Market-hotspot initialization failure is safely logged before the optional service is disabled.
            log_safe_exception(
                logger,
                "Market hotspot service initialization failed; continuing without hotspot data",
                exc,
                error_code="pipeline_market_hotspot_service_init_failed",
                level=logging.DEBUG,
            )
        self._single_stock_notify_lock = threading.Lock()
        self._daily_market_context_service_lock = threading.Lock()
        self._pipeline_stage_runner = PipelineStageRunner()
        self._concept_rankings_cache_lock = threading.Lock()
        self._concept_rankings_cache: Dict[str, Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]] = {}
        
        # 初始化搜索服务（可选，初始化失败不应阻断主分析流程）
        try:
            self.search_service = SearchService(
                bocha_keys=self.config.bocha_api_keys,
                tavily_keys=self.config.tavily_api_keys,
                anspire_keys=self.config.anspire_api_keys,
                brave_keys=self.config.brave_api_keys,
                serpapi_keys=self.config.serpapi_keys,
                minimax_keys=self.config.minimax_api_keys,
                searxng_base_urls=self.config.searxng_base_urls,
                searxng_public_instances_enabled=self.config.searxng_public_instances_enabled,
                news_max_age_days=self.config.news_max_age_days,
                news_strategy_profile=getattr(self.config, "news_strategy_profile", "short"),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Search initialization failure is safely logged before the optional service is disabled.
            log_safe_exception(
                logger,
                "Search service initialization failed; continuing without search",
                exc,
                error_code="pipeline_search_service_init_failed",
                level=logging.WARNING,
            )
            self.search_service = None
        
        logger.info("Analysis scheduler initialized: max_workers=%s", self.max_workers)
        logger.info("Technical analysis engine enabled (moving averages, trend, volume and price)")
        # 打印实时行情/筹码配置状态
        if self.config.enable_realtime_quote:
            logger.info(
                "Realtime quotes enabled: source_priority=%s",
                self.config.realtime_source_priority,
            )
        else:
            logger.info("Realtime quotes disabled; historical close prices will be used")
        if self.config.enable_chip_distribution:
            logger.info("Chip-distribution analysis enabled")
        else:
            logger.info("Chip-distribution analysis disabled")
        if self.search_service is None:
            logger.warning("Search service is unavailable because initialization or a dependency failed")
        elif self.search_service.is_available:
            logger.info("Search service enabled")
        else:
            logger.warning("Search service is unavailable because no search capability is configured")

        # 初始化社交舆情服务（仅美股，可选）
        try:
            self.social_sentiment_service = SocialSentimentService(
                api_key=self.config.social_sentiment_api_key,
                api_url=self.config.social_sentiment_api_url,
            )
            if self.social_sentiment_service.is_available:
                logger.info("Social sentiment service enabled (Reddit/X/Polymarket, US stocks only)")
        except Exception as exc:  # broad-exception: fallback_recorded - Social-sentiment initialization failure is safely logged before the optional service is disabled.
            log_safe_exception(
                logger,
                "Social sentiment service initialization failed; continuing without sentiment data",
                exc,
                error_code="pipeline_social_sentiment_service_init_failed",
                level=logging.WARNING,
            )
            self.social_sentiment_service = None


def _clone_stage_descriptor(descriptor: Any) -> Any:
    """Clone a stage descriptor with the legacy facade as its globals."""

    descriptor_type = None
    function = descriptor
    if isinstance(descriptor, staticmethod):
        descriptor_type = staticmethod
        function = descriptor.__func__
    elif isinstance(descriptor, classmethod):
        descriptor_type = classmethod
        function = descriptor.__func__

    if not isinstance(function, _FunctionType):
        raise TypeError("Stage descriptor must wrap a Python function")

    rebound = _FunctionType(
        function.__code__,
        globals(),
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    rebound.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    rebound.__annotations__ = dict(function.__annotations__)
    rebound.__dict__.update(function.__dict__)
    rebound.__doc__ = function.__doc__
    rebound.__module__ = __name__
    rebound.__qualname__ = f"{StockAnalysisPipeline.__qualname__}.{function.__name__}"
    if hasattr(function, "__type_params__"):
        rebound.__type_params__ = function.__type_params__

    if descriptor_type is not None:
        return descriptor_type(rebound)
    return rebound


def _bind_stage_methods(stage_container: Any) -> Tuple[str, ...]:
    """Bind extracted stage descriptors back onto the legacy facade."""

    bound_names: List[str] = []
    rebound_descriptors: Dict[int, Any] = {}
    for name, descriptor in vars(stage_container).items():
        function = (
            descriptor.__func__
            if isinstance(descriptor, (staticmethod, classmethod))
            else descriptor
        )
        if name.startswith("__") or not isinstance(function, _FunctionType):
            continue
        descriptor_id = id(descriptor)
        if descriptor_id not in rebound_descriptors:
            rebound_descriptors[descriptor_id] = _clone_stage_descriptor(descriptor)
        rebound_descriptor = rebound_descriptors[descriptor_id]
        setattr(StockAnalysisPipeline, name, rebound_descriptor)
        bound_names.append(name)
    return tuple(bound_names)


_ANALYSIS_STAGE_METHOD_NAMES = _bind_stage_methods(_AnalysisStageMixin)
_DELIVERY_STAGE_METHOD_NAMES = _bind_stage_methods(_DeliveryStageMixin)
_PERSISTENCE_STAGE_METHOD_NAMES = _bind_stage_methods(_PersistenceStageMixin)
_ORCHESTRATION_STAGE_METHOD_NAMES = _bind_stage_methods(_OrchestrationStageMixin)
