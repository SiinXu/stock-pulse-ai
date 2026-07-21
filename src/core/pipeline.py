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
from src.core.stages.delivery import _DeliveryStageMixin
from data_provider.us_index_mapping import is_us_stock_code
logger = logging.getLogger(__name__)

# Keep legacy module exports alive while concrete stages move behind the facade.
_PIPELINE_COMPAT_EXPORTS = (
    apply_daily_market_context_guardrail,
    apply_phase_decision_guardrails,
    build_market_phase_context,
    current_diagnostic_snapshot,
    DailyMarketContext,
    DailyMarketContextService,
    defaultdict,
    ExitStack,
    fill_price_position_if_needed,
    format_daily_market_context_prompt_section,
    FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
    get_market_now,
    get_placeholder_text,
    get_unknown_text,
    infer_decision_type_from_advice,
    is_market_open,
    is_us_stock_code,
    localize_confidence_level,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_chip_structure_availability,
    normalize_report_language,
    NotificationChannel,
    pd,
    populate_decision_action_fields,
    record_llm_run,
    record_llm_run_started,
    record_notification_run,
    render_market_phase_summary,
    SimpleNamespace,
    stabilize_decision_with_structure,
    timedelta,
)

# 防御性 guard：当实例绕过 __init__（如测试中 __new__）构造时，
# double-check 初始化 _single_stock_notify_lock 仍然线程安全。
_DAILY_MARKET_CONTEXT_SERVICE_LOCK_INIT_GUARD = threading.Lock()
_PIPELINE_STAGE_RUNNER_INIT_GUARD = threading.Lock()
_DEFER_PIPELINE_DELIVERY_OBSERVATION: ContextVar[bool] = ContextVar(
    "defer_pipeline_delivery_observation",
    default=False,
)


def _symbol_scope_lookup_values(code: str, market: str) -> List[str]:
    """Return accepted persisted-intelligence symbol spellings for lookup."""
    raw = str(code or "").strip()
    normalized = normalize_stock_code(raw) if raw else ""
    values: List[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            values.append(text)

    def add_case_variants(value: str) -> None:
        text = str(value or "").strip()
        if not text:
            return
        add(text)
        add(text.upper())
        add(text.lower())

    add_case_variants(normalized)
    add_case_variants(raw)

    normalized_upper = normalized.upper()
    if normalized_upper.startswith("HK") and normalized_upper[2:].isdigit():
        digits = normalized_upper[2:]
        trimmed_digits = digits.lstrip("0") or digits
        add_case_variants(normalized_upper)
        add_case_variants(digits)
        add_case_variants(trimmed_digits)
        add_case_variants(f"HK{trimmed_digits}")
        add_case_variants(f"{trimmed_digits}.HK")
        add_case_variants(f"{digits}.HK")
        return values

    if (market or "").strip().lower() != "cn":
        return values
    if not (normalized.isdigit() and len(normalized) == 6):
        return values

    raw_upper = raw.upper()
    exchange = ""
    if raw_upper.startswith(("SH", "SS")) or raw_upper.endswith((".SH", ".SS")):
        exchange = "SH"
    elif raw_upper.startswith("SZ") or raw_upper.endswith(".SZ"):
        exchange = "SZ"
    elif raw_upper.startswith("BJ") or raw_upper.endswith(".BJ"):
        exchange = "BJ"
    elif is_bse_code(normalized):
        exchange = "BJ"
    elif normalized.startswith(("5", "6", "9")):
        exchange = "SH"
    else:
        exchange = "SZ"

    add_case_variants(f"{exchange}{normalized}")
    add_case_variants(f"{exchange}.{normalized}")
    add_case_variants(f"{normalized}.{exchange}")
    if exchange == "SH":
        add_case_variants(f"SS.{normalized}")
        add_case_variants(f"{normalized}.SS")
    return values


class StockAnalysisPipeline(_DeliveryStageMixin):
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

    def _emit_progress(self, progress: int, message: str) -> None:
        """Best-effort bridge from pipeline stages to task SSE progress."""
        callback = getattr(self, "progress_callback", None)
        if callback is None:
            return
        try:
            callback(progress, message)
        except Exception as exc:
            query_id = getattr(self, "query_id", None)
            log_safe_exception(
                logger,
                "Pipeline progress callback failed",
                exc,
                error_code="pipeline_progress_callback_failed",
                level=logging.WARNING,
                context={"progress": progress, "query_id": query_id},
            )

    def _get_pipeline_stage_runner(self) -> PipelineStageRunner:
        """Return the request-scoped runner, including for lightweight test instances."""
        runner = getattr(self, "_pipeline_stage_runner", None)
        if isinstance(runner, PipelineStageRunner):
            return runner
        with _PIPELINE_STAGE_RUNNER_INIT_GUARD:
            runner = getattr(self, "_pipeline_stage_runner", None)
            if not isinstance(runner, PipelineStageRunner):
                runner = PipelineStageRunner()
                self._pipeline_stage_runner = runner
        return runner

    def _run_pipeline_stage(
        self,
        stage: PipelineStageName,
        operation: Callable[[], Any],
        *,
        retryable: bool = False,
        side_effect_key: Optional[Any] = None,
    ) -> PipelineStageResult[Any]:
        """Execute one stage through the typed result and retry-fence contract."""
        return self._get_pipeline_stage_runner().run(
            stage,
            operation,
            retryable=retryable,
            side_effect_key=side_effect_key,
        )

    def _finish_pipeline_stage(
        self,
        observation: PipelineStageObservation,
        result: PipelineStageResult[Any],
        *,
        output_summary: Optional[Dict[str, Any]] = None,
    ) -> PipelineStageResult[Any]:
        """Record a typed result through the existing diagnostic observation."""
        self._get_pipeline_stage_runner().record(result)
        observation.finish(
            status=result.status.value,
            output_summary=output_summary,
            degradation_reason=result.degradation_reason,
            retryable=result.retryable,
            error=result.error,
        )
        return result

    def _record_pipeline_stage_result(
        self,
        result: PipelineStageResult[Any],
        *,
        input_summary: Optional[Dict[str, Any]] = None,
        output_summary: Optional[Dict[str, Any]] = None,
    ) -> PipelineStageResult[Any]:
        """Record a typed result for a stage without an active timer."""
        self._get_pipeline_stage_runner().record(result)
        record_pipeline_stage(
            stage=result.stage.value,
            status=result.status.value,
            input_summary=input_summary,
            output_summary=output_summary,
            degradation_reason=result.degradation_reason,
            retryable=result.retryable,
            error_type=(
                type(result.error).__name__
                if result.error is not None
                else None
            ),
            error_message=result.error,
        )
        return result

    def fetch_and_save_stock_data(
        self, 
        code: str,
        force_refresh: bool = False,
        current_time: Optional[datetime] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        获取并保存单只股票数据
        
        断点续传逻辑：
        1. 检查数据库是否已有最新可复用交易日数据
        2. 如果有且不强制刷新，则跳过网络请求
        3. 否则从数据源获取并保存
        
        Args:
            code: 股票代码
            force_refresh: 是否强制刷新（忽略本地缓存）
            current_time: 本轮运行冻结的参考时间，用于统一断点续传目标交易日判断
            
        Returns:
            Tuple[是否成功, 错误信息]
        """
        stock_name = code
        try:
            # 首先获取股票名称
            stock_name = self.fetcher_manager.get_stock_name(code, allow_realtime=False)

            target_date = self._resolve_resume_target_date(
                code, current_time=current_time
            )

            # 断点续传检查：如果最新可复用交易日的数据已存在，则跳过
            if not force_refresh and self.db.has_today_data(code, target_date):
                logger.info(
                    "%s(%s) already has data for %s; skipping fetch for resumability",
                    stock_name,
                    code,
                    target_date,
                )
                return True, None

            # 从数据源获取数据
            logger.info("%s(%s) fetching market data", stock_name, code)
            df, source_name = self.fetcher_manager.get_daily_data(code, days=30)

            if df is None or df.empty:
                return False, "获取数据为空"

            # 保存到数据库
            saved_count = self.db.save_daily_data(df, code, source_name)
            logger.info(
                "%s(%s) market data saved: source=%s rows_added=%s",
                stock_name,
                code,
                source_name,
                saved_count,
            )

            return True, None

        except Exception as e:
            error_msg = f"获取/保存数据失败: {str(e)}"
            log_safe_exception(
                logger,
                "Market data fetch or persistence failed",
                e,
                error_code="pipeline_market_data_fetch_or_save_failed",
                context={"stock_code": code},
            )
            return False, error_msg

    def _build_context_snapshot(
        self,
        enhanced_context: Dict[str, Any],
        news_content: Optional[str],
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution],
        news_result_count: Optional[int] = None,
        analysis_context_pack_overview: Optional[Dict[str, Any]] = None,
        market_phase_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        构建分析上下文快照
        """
        snapshot = {
            "enhanced_context": self._without_runtime_prompt_context(enhanced_context),
            "news_content": news_content,
            "realtime_quote_raw": self._safe_to_dict(realtime_quote),
            "chip_distribution_raw": self._safe_to_dict(chip_data),
        }
        market_structure_context = enhanced_context.get("market_structure_context")
        if isinstance(market_structure_context, dict):
            snapshot["market_structure_context"] = market_structure_context
        if news_content is not None:
            snapshot["news_retrieval_content"] = news_content
        if news_result_count is not None:
            snapshot["news_result_count"] = news_result_count
        if analysis_context_pack_overview is not None:
            snapshot["analysis_context_pack_overview"] = analysis_context_pack_overview
        if market_phase_summary is not None:
            snapshot[MARKET_PHASE_SUMMARY_KEY] = market_phase_summary
        diagnostic_snapshot = current_diagnostic_snapshot()
        if diagnostic_snapshot is not None:
            snapshot["diagnostics"] = diagnostic_snapshot
        if self.analysis_skills is not None:
            snapshot["skills"] = list(self.analysis_skills)
        return snapshot

    def _persist_analysis_history_stage(
        self,
        *,
        result: AnalysisResult,
        query_id: str,
        report_type: str,
        news_content: Optional[str],
        context_snapshot_factory: Callable[[], Dict[str, Any]],
        portfolio_context: Optional[Dict[str, Any]],
        failure_reason: str,
        failure_message: str,
        failure_error_code: str,
    ) -> PipelineStageResult[PipelinePersistValue]:
        """Persist one analysis once for a stable query and return its stage result."""

        def _persist() -> PipelineStageResult[PipelinePersistValue]:
            context_snapshot: Dict[str, Any] = {}
            saved_history_id: Any = None
            persistence_error: Optional[BaseException] = None
            try:
                context_snapshot = context_snapshot_factory()
                result.diagnostic_context_snapshot = context_snapshot
                saved_history_id = self.db.save_analysis_history(
                    result=result,
                    query_id=query_id,
                    report_type=report_type,
                    news_content=news_content,
                    context_snapshot=context_snapshot,
                    save_snapshot=self.save_context_snapshot,
                )
                valid_saved_history_id = (
                    isinstance(saved_history_id, int)
                    and not isinstance(saved_history_id, bool)
                    and saved_history_id > 0
                )
                if valid_saved_history_id:
                    self._extract_decision_signal_after_history_save(
                        result=result,
                        query_id=query_id,
                        source_report_id=saved_history_id,
                        report_type=report_type,
                        context_snapshot=context_snapshot,
                        portfolio_context=portfolio_context,
                    )
            except Exception as exc:  # broad-exception: fallback_recorded - History failure remains isolated after the side-effect fence records whether a write committed.
                persistence_error = exc
                valid_saved_history_id = False
                record_history_run(
                    report_saved=False,
                    metadata_saved=False,
                    error_message=exc,
                )
                log_safe_exception(
                    logger,
                    failure_message,
                    exc,
                    error_code=failure_error_code,
                    level=logging.WARNING,
                    context={"stock_code": getattr(result, "code", None)},
                )

            persistence_succeeded = bool(saved_history_id)
            value = PipelinePersistValue(
                saved=persistence_succeeded,
                history_id=(
                    saved_history_id if valid_saved_history_id else None
                ),
                context_snapshot=context_snapshot,
            )
            if persistence_succeeded:
                return PipelineStageResult(
                    stage=PipelineStageName.PERSIST,
                    status=PipelineStageStatus.SUCCESS,
                    value=value,
                    side_effect_committed=True,
                    error=persistence_error,
                )
            return PipelineStageResult.failed(
                PipelineStageName.PERSIST,
                value=value,
                error=persistence_error,
                retryable=True,
                reason=failure_reason,
            )

        persistence_result = self._get_pipeline_stage_runner().run(
            PipelineStageName.PERSIST,
            _persist,
            retryable=True,
            side_effect_key=(
                "analysis_history",
                query_id,
                getattr(result, "code", None),
                report_type,
            ),
        )
        if not persistence_result.reused:
            persistence_value = persistence_result.value
            if persistence_result.error is None:
                record_history_run(
                    report_saved=bool(persistence_value and persistence_value.saved),
                    metadata_saved=bool(persistence_value and persistence_value.saved),
                    analysis_history_id=(
                        persistence_value.history_id
                        if persistence_value is not None
                        else None
                    ),
                )
        return persistence_result

    def _extract_decision_signal_after_history_save(
        self,
        *,
        result: AnalysisResult,
        query_id: str,
        source_report_id: int,
        report_type: str,
        context_snapshot: Dict[str, Any],
        portfolio_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Best-effort DecisionSignal extraction after analysis history is saved."""

        assert (
            isinstance(source_report_id, int)
            and not isinstance(source_report_id, bool)
            and source_report_id > 0
        )

        try:
            diagnostic_context = get_current_diagnostic_context()
            trace_id = (
                getattr(diagnostic_context, "trace_id", None)
                or getattr(self, "trace_id", None)
                or query_id
            )
            signal_result = extract_and_persist_from_analysis_result(
                result,
                context_snapshot=context_snapshot,
                source_report_id=source_report_id,
                trace_id=str(trace_id),
                query_source=getattr(self, "query_source", None) or "system",
                report_type=report_type,
                portfolio_context=portfolio_context,
                profile_source="auto_default",
            )
            if isinstance(signal_result, dict):
                summary = summarize_decision_signal(
                    signal_result.get("item"),
                    report_language=getattr(result, "report_language", None),
                )
                if summary:
                    setattr(result, "decision_signal_summary", summary)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Decision signal extraction failed after history save",
                exc,
                error_code="pipeline_decision_signal_extraction_failed",
                level=logging.WARNING,
                context={
                    "query_id": query_id,
                    "stock_code": getattr(result, "code", None),
                },
            )

    @staticmethod
    def _build_notification_run_snapshot(
        *,
        channel: str,
        status: str,
        success: bool,
        attempts: int = 1,
        error_message: Optional[Any] = None,
    ) -> Dict[str, Any]:
        payload = {
            "channel": channel,
            "status": status,
            "success": success,
            "attempts": attempts,
            "created_at": datetime.now().isoformat(),
        }
        sanitized_error = sanitize_diagnostic_text(error_message)
        if sanitized_error:
            payload["error_message_sanitized"] = sanitized_error
        return payload

    def _activate_delivery_diagnostic_context(
        self,
        results: List[AnalysisResult],
    ):
        """Activate an isolated delivery trace nested under any caller context."""
        try:
            first_result = results[0] if results else None
            context_snapshot = (
                getattr(first_result, "diagnostic_context_snapshot", None)
                if first_result is not None
                else None
            )
            existing_diagnostics = (
                context_snapshot.get("diagnostics")
                if isinstance(context_snapshot, dict)
                else None
            )
            single_result = len(results) == 1
            inherited_trace_id = (
                existing_diagnostics.get("trace_id")
                if single_result and isinstance(existing_diagnostics, dict)
                else None
            )
            inherited_query_id = (
                getattr(first_result, "query_id", None)
                if single_result and first_result is not None
                else None
            )
            delivery_id = (
                getattr(self, "trace_id", None)
                or getattr(self, "query_id", None)
                or inherited_trace_id
                or f"delivery_{uuid.uuid4().hex}"
            )
            return activate_run_diagnostic_context(
                trace_id=delivery_id,
                query_id=(
                    getattr(self, "query_id", None)
                    or inherited_query_id
                    or delivery_id
                ),
                stock_code=(
                    getattr(first_result, "code", None)
                    if single_result and first_result is not None
                    else None
                ),
                trigger_source=getattr(self, "query_source", None),
                scope="pipeline_delivery",
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Delivery context failures are logged and leave delivery behavior unchanged.
            log_safe_exception(
                logger,
                "Pipeline delivery diagnostic context activation failed",
                exc,
                error_code="pipeline_delivery_context_activation_failed",
                level=logging.WARNING,
                context={"result_count": len(results)},
            )
            return None

    @staticmethod
    def _merge_delivery_diagnostic_snapshot(
        item: AnalysisResult,
        delivery_snapshot: Dict[str, Any],
        notification_run: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge delivery-only runs into one result without replacing analysis runs."""
        raw_context_snapshot = getattr(item, "diagnostic_context_snapshot", None)
        context_snapshot = (
            dict(raw_context_snapshot)
            if isinstance(raw_context_snapshot, dict)
            else {}
        )
        raw_diagnostics = context_snapshot.get("diagnostics")
        diagnostics = dict(raw_diagnostics) if isinstance(raw_diagnostics, dict) else {}
        diagnostics.setdefault(
            "trace_id",
            getattr(item, "trace_id", None)
            or getattr(item, "query_id", None)
            or delivery_snapshot.get("trace_id"),
        )
        diagnostics.setdefault("query_id", getattr(item, "query_id", None))
        diagnostics.setdefault("stock_code", getattr(item, "code", None))

        for field_name in ("notification_runs", "pipeline_stage_runs"):
            raw_existing_runs = diagnostics.get(field_name)
            existing_runs = (
                list(raw_existing_runs)
                if isinstance(raw_existing_runs, list)
                else []
            )
            if field_name == "notification_runs":
                candidate_runs = (
                    [notification_run] if notification_run is not None else []
                )
            else:
                candidates = delivery_snapshot.get(field_name)
                candidate_runs = (
                    list(candidates) if isinstance(candidates, list) else []
                )
            for candidate in candidate_runs:
                if not isinstance(candidate, dict):
                    continue
                payload = dict(candidate)
                if field_name == "notification_runs" and not payload.get("trace_id"):
                    payload["trace_id"] = delivery_snapshot.get("trace_id")
                if payload not in existing_runs:
                    existing_runs.append(payload)
            diagnostics[field_name] = existing_runs

        context_snapshot["diagnostics"] = diagnostics
        item.diagnostic_context_snapshot = context_snapshot
        return diagnostics

    def _refresh_saved_diagnostic_snapshot(
        self,
        *,
        result: Optional[AnalysisResult] = None,
        results: Optional[List[AnalysisResult]] = None,
        fallback_code: Optional[str] = None,
        notification_run: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Patch persisted history with the latest fail-open diagnostic snapshot."""
        if not getattr(self, "save_context_snapshot", True):
            return

        db = getattr(self, "db", None)
        updater = getattr(db, "update_analysis_history_diagnostics", None)
        if not callable(updater):
            return

        diagnostic_snapshot = current_diagnostic_snapshot()
        target_results = list(results or ([] if result is None else [result]))
        if diagnostic_snapshot is not None and (
            results is not None
            or diagnostic_snapshot.get("scope") == "pipeline_delivery"
        ):
            for item in target_results:
                query_id = (
                    getattr(item, "query_id", None)
                    or getattr(self, "query_id", None)
                )
                if not query_id:
                    continue
                code = getattr(item, "code", None) or fallback_code
                try:
                    merged_diagnostics = self._merge_delivery_diagnostic_snapshot(
                        item,
                        diagnostic_snapshot,
                        notification_run,
                    )
                    updater(
                        query_id=query_id,
                        code=code,
                        diagnostics=merged_diagnostics,
                    )
                except Exception as exc:  # broad-exception: optional_metadata - Delivery diagnostics are best-effort and cannot change delivery outcomes.
                    log_safe_exception(
                        logger,
                        "Delivery diagnostic snapshot update failed; continuing without the update",
                        exc,
                        error_code="pipeline_delivery_snapshot_update_failed",
                        level=logging.WARNING,
                        context={"query_id": query_id, "stock_code": code},
                    )
            return

        if diagnostic_snapshot is not None:
            query_id = (
                diagnostic_snapshot.get("query_id")
                or getattr(result, "query_id", None)
                or getattr(self, "query_id", None)
            )
            code = (
                getattr(result, "code", None)
                or fallback_code
                or diagnostic_snapshot.get("stock_code")
            )
            if not query_id:
                return
            try:
                updater(query_id=query_id, code=code, diagnostics=diagnostic_snapshot)
            except Exception as exc:  # broad-exception: optional_metadata - Run diagnostics are best-effort and cannot change analysis outcomes.
                log_safe_exception(
                    logger,
                    "Run diagnostic snapshot update failed; continuing without the update",
                    exc,
                    error_code="pipeline_diagnostic_snapshot_update_failed",
                    level=logging.WARNING,
                    context={"query_id": query_id, "stock_code": code},
                )
            return

        if notification_run is None:
            return

        for item in target_results:
            query_id = getattr(item, "query_id", None) or getattr(self, "query_id", None)
            if not query_id:
                continue
            code = getattr(item, "code", None) or fallback_code
            try:
                updater(
                    query_id=query_id,
                    code=code,
                    notification_runs=[notification_run],
                )
            except Exception as exc:  # broad-exception: optional_metadata - Notification diagnostics are best-effort and cannot change delivery outcomes.
                log_safe_exception(
                    logger,
                    "Notification diagnostic snapshot update failed; continuing without the update",
                    exc,
                    error_code="pipeline_notification_snapshot_update_failed",
                    level=logging.WARNING,
                    context={"query_id": query_id, "stock_code": code},
                )

    def _load_persisted_intelligence_context(
        self,
        *,
        code: str,
        stock_name: str,
        market: str,
        limit: int = 6,
    ) -> Optional[str]:
        """Load locally persisted intelligence as fail-open evidence context."""
        try:
            service = IntelligenceService(config=self.config)
            service.refresh_auto_sources()
            days = max(1, int(self.config.get_effective_news_window_days() or 1))
            collected: list[Dict[str, Any]] = []
            seen_urls: set[str] = set()
            symbol_filters = [
                {"scope_type": "symbol", "scope_value": scope_value, "market": market}
                for scope_value in _symbol_scope_lookup_values(code, market)
            ]
            for filters in symbol_filters + [{"scope_type": "market", "market": market}]:
                payload = service.list_items(published_days=days, page=1, page_size=limit, **filters)
                for item in payload.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    collected.append(item)
                    if len(collected) >= limit:
                        break
                if len(collected) >= limit:
                    break
            if not collected:
                return None
            lines = [f"## 本地资讯证据池（{stock_name}/{code}）"]
            for idx, item in enumerate(collected[:limit], 1):
                title = str(item.get("title") or "未命名资讯").strip()
                summary = str(item.get("summary") or "").strip()
                source = str(item.get("source") or item.get("source_name") or "local-intel").strip()
                published = str(item.get("published_at") or "").strip()
                url = str(item.get("url") or "").strip()
                meta = " / ".join(part for part in (source, published) if part)
                lines.append(f"{idx}. {title}" + (f"（{meta}）" if meta else ""))
                if summary:
                    lines.append(f"   摘要：{summary[:220]}")
                if url and not url.startswith("no-url:intel:"):
                    lines.append(f"   来源：{url}")
            return "\n".join(lines)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Local intelligence evidence load failed; continuing without local evidence",
                exc,
                error_code="pipeline_local_intelligence_load_failed",
                level=logging.DEBUG,
                context={"stock_code": code, "market": market},
            )
            return None

    def _build_legacy_analysis_artifacts(
        self,
        *,
        code: str,
        stock_name: str,
        market: str,
        phase: Optional[Dict[str, Any]],
        context: Dict[str, Any],
        enhanced_context: Dict[str, Any],
        realtime_quote: Any,
        trend_result: Optional[TrendAnalysisResult],
        chip_data: Optional[ChipDistribution],
        fundamental_context: Optional[Dict[str, Any]],
        news_context: Optional[str],
        news_result_count: Optional[int],
        query_id: str,
        portfolio_context: Optional[Dict[str, Any]] = None,
    ) -> PipelineAnalysisArtifacts:
        return PipelineAnalysisArtifacts(
            code=code,
            stock_name=stock_name,
            market=market,
            phase=phase,
            base_context=context,
            enhanced_context=enhanced_context,
            realtime_quote=realtime_quote,
            trend_result=trend_result,
            chip_data=chip_data,
            fundamental_context=fundamental_context,
            news_context=news_context,
            news_result_count=news_result_count,
            metadata={
                "query_id": query_id,
                "trigger_source": self.query_source,
            },
            portfolio_context=dict(portfolio_context) if isinstance(portfolio_context, dict) else None,
        )

    def _build_agent_analysis_artifacts(
        self,
        *,
        code: str,
        stock_name: str,
        market: str,
        phase: Optional[Dict[str, Any]],
        initial_context: Dict[str, Any],
        fundamental_context: Optional[Dict[str, Any]],
        query_id: str,
        base_context: Optional[Dict[str, Any]] = None,
        portfolio_context: Optional[Dict[str, Any]] = None,
    ) -> PipelineAnalysisArtifacts:
        context_candidate = base_context
        if not isinstance(context_candidate, dict):
            context_candidate = initial_context.get("analysis_context")
        if isinstance(context_candidate, dict) and context_candidate:
            daily_context = dict(context_candidate)
            daily_context.setdefault("code", code)
            if stock_name:
                daily_context.setdefault("stock_name", stock_name)
        else:
            daily_context = {
                "code": code,
                "stock_name": stock_name,
                "data_missing": True,
                "today": {},
                "yesterday": {},
            }

        return PipelineAnalysisArtifacts(
            code=code,
            stock_name=stock_name,
            market=market,
            phase=phase,
            base_context=daily_context,
            enhanced_context={},
            realtime_quote=initial_context.get("realtime_quote"),
            trend_result=initial_context.get("trend_result"),
            chip_data=initial_context.get("chip_distribution"),
            fundamental_context=fundamental_context,
            news_context=initial_context.get("news_context"),
            news_result_count=None,
            metadata={
                "query_id": query_id,
                "trigger_source": self.query_source,
            },
            portfolio_context=dict(portfolio_context) if isinstance(portfolio_context, dict) else None,
        )

    def _build_analysis_context_pack_outputs(
        self,
        artifacts: PipelineAnalysisArtifacts,
        *,
        report_language: str,
        code: str,
        query_id: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        try:
            pack = AnalysisContextBuilder.build(artifacts)
            summary = format_analysis_context_pack_prompt_section(
                pack,
                report_language=report_language,
            )
            overview = render_analysis_context_pack_overview(
                pack,
                report_language=report_language,
            )
            return summary, overview
        except Exception as exc:
            log_safe_exception(
                logger,
                "Analysis context pack output generation failed",
                exc,
                error_code="pipeline_analysis_context_pack_failed",
                level=logging.WARNING,
                context={"stock_code": code, "query_id": query_id},
            )
            return "", None

    @staticmethod
    def _without_runtime_prompt_context(context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a shallow copy without runtime-only prompt context.

        Market phase and AnalysisContextPack summaries are prompt inputs only.
        P4 stores only the separately rendered public overview at snapshot top level.
        """
        sanitized = dict(context)
        sanitized.pop("market_phase_context", None)
        sanitized.pop("portfolio_context", None)
        sanitized.pop("analysis_context_pack", None)
        sanitized.pop("analysis_context_pack_summary", None)
        sanitized.pop("daily_market_context_summary", None)
        enhanced_context = sanitized.get("enhanced_context")
        if isinstance(enhanced_context, dict):
            enhanced_context = dict(enhanced_context)
            enhanced_context.pop("daily_market_context_summary", None)
            sanitized["enhanced_context"] = enhanced_context
        return sanitized

    _without_market_phase_context = _without_runtime_prompt_context

    @staticmethod
    def _resolve_resume_target_date(
        code: str, current_time: Optional[datetime] = None
    ) -> date:
        """
        Resolve the trading date used by checkpoint/resume checks.
        """
        market = get_market_for_stock(normalize_stock_code(code))
        return get_effective_trading_date(market, current_time=current_time)

    @staticmethod
    def _safe_to_dict(value: Any) -> Optional[Dict[str, Any]]:
        """
        安全转换为字典
        """
        if value is None:
            return None
        if hasattr(value, "to_dict"):
            try:
                return value.to_dict()
            except Exception:
                return None
        if hasattr(value, "__dict__"):
            try:
                return dict(value.__dict__)
            except Exception:
                return None
        return None

    def _resolve_query_source(self, query_source: Optional[str] = None) -> str:
        """Resolve the request source using explicit, Bot, Web, then system precedence.

        An explicit source wins. Otherwise an application request context identifies
        a Bot request, a query id identifies a Web request, and all other calls are
        classified as system work.
        """
        if query_source:
            return query_source
        if getattr(self, "request_context", None):
            return "bot"
        if getattr(self, "query_id", None):
            return "web"
        return "system"

    def _build_query_context(self, query_id: Optional[str] = None) -> Dict[str, str]:
        """Build the low-sensitivity requester provenance persisted with a query."""
        effective_query_id = query_id or self.query_id or ""

        context: Dict[str, str] = {
            "query_id": effective_query_id,
            "query_source": self.query_source or "",
        }

        request_context = getattr(self, "request_context", None)
        if request_context:
            context.update({
                "requester_platform": request_context.requester_platform,
                "requester_user_id": request_context.requester_user_id,
                "requester_user_name": request_context.requester_user_name,
                "requester_chat_id": request_context.requester_chat_id,
                "requester_message_id": request_context.requester_message_id,
                "requester_query": request_context.requester_query,
            })

        return context
    
    def process_single_stock(
        self,
        code: str,
        skip_analysis: bool = False,
        single_stock_notify: bool = False,
        report_type: ReportType = ReportType.SIMPLE,
        analysis_query_id: Optional[str] = None,
        current_time: Optional[datetime] = None,
    ) -> Optional[AnalysisResult]:
        """
        处理单只股票的完整流程

        包括：
        1. 获取数据
        2. 保存数据
        3. AI 分析
        4. 单股推送（可选，#55）

        此方法会被线程池调用，需要处理好异常

        Args:
            analysis_query_id: 查询链路关联 id
            code: 股票代码
            skip_analysis: 是否跳过 AI 分析
            single_stock_notify: 是否启用单股推送模式（每分析完一只立即推送）
            report_type: 报告类型枚举（从配置读取，Issue #119）
            current_time: 本轮运行冻结的参考时间，用于统一断点续传目标交易日判断

        Returns:
            AnalysisResult 或 None
        """
        logger.info("========== Processing %s ==========", code)

        from src.services.history_loader import set_frozen_target_date, reset_frozen_target_date
        effective_query_id = analysis_query_id or getattr(self, "query_id", None) or uuid.uuid4().hex
        effective_trace_id = getattr(self, "trace_id", None) or effective_query_id
        diag_token = None
        frozen_target_token = None
        if get_current_diagnostic_context() is None:
            diag_token = activate_run_diagnostic_context(
                trace_id=effective_trace_id,
                query_id=effective_query_id,
                stock_code=code,
                trigger_source=getattr(self, "query_source", None),
            )
        try:
            with observe_pipeline_stage(
                "resolve",
                input_summary={
                    "stock_code": code,
                    "query_source": getattr(self, "query_source", None),
                },
                retryable=False,
            ) as resolve_stage:
                def _resolve_target() -> Tuple[date, Any]:
                    target_date = self._resolve_resume_target_date(
                        code,
                        current_time=current_time,
                    )
                    return target_date, set_frozen_target_date(target_date)

                resolve_result = self._run_pipeline_stage(
                    PipelineStageName.RESOLVE,
                    _resolve_target,
                    retryable=False,
                )
                resolved_value = resolve_result.value
                self._finish_pipeline_stage(
                    resolve_stage,
                    resolve_result,
                    output_summary=(
                        {
                            "query_id": effective_query_id,
                            "target_date": resolved_value[0].isoformat(),
                        }
                        if resolved_value is not None
                        else None
                    ),
                )
                frozen_td, frozen_target_token = resolve_result.unwrap()
        except Exception:
            record_missing_pipeline_stages_as_skipped(
                PIPELINE_STAGE_NAMES,
                input_summary={"stock_code": code},
                reason="stock_resolution_failed",
            )
            reset_run_diagnostic_context(diag_token)
            if frozen_target_token is not None:
                reset_frozen_target_date(frozen_target_token)
            raise

        try:
            self._emit_progress(12, f"{code}：正在准备分析任务")
            # Step 1: 获取并保存数据
            with observe_pipeline_stage(
                "fetch",
                input_summary={
                    "stock_code": code,
                    "operation": "prepare_daily_data",
                    "force_refresh": False,
                },
                retryable=True,
            ) as fetch_stage:
                def _prepare_daily_data() -> PipelineStageResult[Any]:
                    stage_value = self.fetch_and_save_stock_data(
                        code,
                        current_time=current_time,
                    )
                    data_ready, stage_error = stage_value
                    if data_ready:
                        return PipelineStageResult.success(
                            PipelineStageName.FETCH,
                            stage_value,
                        )
                    return PipelineStageResult.degraded(
                        PipelineStageName.FETCH,
                        stage_value,
                        reason=stage_error,
                        retryable=True,
                    )

                fetch_result = self._run_pipeline_stage(
                    PipelineStageName.FETCH,
                    _prepare_daily_data,
                    retryable=True,
                )
                fetch_value = fetch_result.value
                self._finish_pipeline_stage(
                    fetch_stage,
                    fetch_result,
                    output_summary={
                        "data_ready": bool(fetch_value and fetch_value[0]),
                    },
                )
                success, error = fetch_result.unwrap()
            
            if not success:
                logger.warning("[%s] Market data preparation failed", code)
                # 即使获取失败，也尝试用已有数据分析
            else:
                self._emit_progress(16, f"{code}：行情数据准备完成")
            
            # Step 2: AI 分析
            if skip_analysis:
                logger.info("[%s] Skipping AI analysis in dry-run mode", code)
                for stage_name in (
                    "intelligence",
                    "context",
                    "analyze",
                    "persist",
                    "render",
                    "dispatch",
                ):
                    self._record_pipeline_stage_result(
                        PipelineStageResult.skipped(
                            PipelineStageName(stage_name),
                            reason="analysis_disabled",
                        ),
                        input_summary={
                            "stock_code": code,
                            "mode": "dry_run",
                        },
                        output_summary={"reason": "analysis_disabled"},
                    )
                return None
            
            analyze_kwargs = {"query_id": effective_query_id}
            if current_time is not None:
                analyze_kwargs["current_time"] = current_time
            result = self.analyze_stock(code, report_type, **analyze_kwargs)
            
            if result and result.success:
                logger.info(
                    "[%s] Analysis completed: sentiment_score=%s",
                    code,
                    result.sentiment_score,
                )
                
                # 单股推送模式（#55）：每分析完一只股票立即推送
                if single_stock_notify:
                    self._send_single_stock_notification(
                        result,
                        report_type=report_type,
                        fallback_code=code,
                    )
            elif result:
                logger.warning("[%s] Analysis returned an unsuccessful result", code)

            missing_stage_count = 0
            if result and result.success:
                if (
                    not single_stock_notify
                    and not _DEFER_PIPELINE_DELIVERY_OBSERVATION.get()
                ):
                    missing_stage_count = record_missing_pipeline_stages_as_skipped(
                        ("render", "dispatch"),
                        input_summary={"stock_code": code},
                        reason="stock_delivery_not_requested",
                    )
            else:
                missing_stage_count = record_missing_pipeline_stages_as_skipped(
                    (
                        "intelligence",
                        "context",
                        "analyze",
                        "persist",
                        "render",
                        "dispatch",
                    ),
                    input_summary={"stock_code": code},
                    reason="analysis_unsuccessful",
                )
            if missing_stage_count and result and result.success:
                self._refresh_saved_diagnostic_snapshot(
                    result=result,
                    fallback_code=code,
                )
            
            return result
            
        except Exception as e:  # broad-exception: fallback_recorded - Per-stock failures are safely logged so the batch can continue.
            # 捕获所有异常，确保单股失败不影响整体
            record_missing_pipeline_stages_as_skipped(
                PIPELINE_STAGE_NAMES,
                input_summary={"stock_code": code},
                reason="stock_processing_failed",
            )
            log_safe_exception(
                logger,
                "Stock processing failed",
                e,
                error_code="pipeline_stock_processing_failed",
                context={"stock_code": code},
            )
            return None
        finally:
            reset_run_diagnostic_context(diag_token)
            if frozen_target_token is not None:
                reset_frozen_target_date(frozen_target_token)

    def _process_single_stock_for_batch(
        self,
        code: str,
        **kwargs,
    ) -> Optional[AnalysisResult]:
        """Run one stock while deferring delivery observations to the batch trace."""
        token = _DEFER_PIPELINE_DELIVERY_OBSERVATION.set(True)
        try:
            return self.process_single_stock(code, **kwargs)
        finally:
            _DEFER_PIPELINE_DELIVERY_OBSERVATION.reset(token)
    
    def run(
        self,
        stock_codes: Optional[List[str]] = None,
        dry_run: bool = False,
        send_notification: bool = True,
        merge_notification: bool = False,
        current_time: Optional[datetime] = None,
    ) -> List[AnalysisResult]:
        """
        运行完整的分析流程

        流程：
        1. 获取待分析的股票列表
        2. 使用线程池并发处理
        3. 收集分析结果
        4. 发送通知

        Args:
            stock_codes: 股票代码列表（可选，默认使用配置中的自选股）
            dry_run: 是否仅获取数据不分析
            send_notification: 是否发送推送通知
            merge_notification: 是否合并推送（跳过本次推送，由 main 层合并个股+大盘后统一发送，Issue #190）
            current_time: 本轮运行冻结的参考时间；为空时在 run 内生成

        Returns:
            分析结果列表
        """
        start_time = time.time()
        
        # 使用配置中的股票列表
        if stock_codes is None:
            self.config.refresh_stock_list()
            stock_codes = self.config.stock_list
        
        if not stock_codes:
            logger.error("No watchlist is configured; set STOCK_LIST in the environment file")
            return []
        
        logger.info("===== Starting analysis for %s stocks =====", len(stock_codes))
        logger.info("Stock list: %s", ", ".join(stock_codes))
        logger.info(
            "Concurrency=%s mode=%s",
            self.max_workers,
            "data-only" if dry_run else "full-analysis",
        )

        # 冻结本轮运行的统一参考时间，避免跨市场收盘边界时同批股票使用不同目标交易日。
        resume_reference_time = current_time or datetime.now(timezone.utc)
        
        # === 批量预取实时行情（优化：避免每只股票都触发全量拉取）===
        # 只有股票数量 >= 5 时才进行预取，少量股票直接逐个查询更高效
        if len(stock_codes) >= 5:
            daily_prefetch_count = self.fetcher_manager.prefetch_daily_klines(stock_codes, days=30)
            if daily_prefetch_count > 0:
                logger.info(
                    "[prefetch] component=daily_kline_prefetch action=complete "
                    "provider=TickFlowFetcher cached=%d stock_count=%d",
                    daily_prefetch_count,
                    len(stock_codes),
                )

            prefetch_count = self.fetcher_manager.prefetch_realtime_quotes(stock_codes)
            if prefetch_count > 0:
                logger.info(
                    "Bulk realtime prefetch enabled: stock_count=%s cache_entries=%s",
                    len(stock_codes),
                    prefetch_count,
                )

        # Issue #455: 预取股票名称，避免并发分析时显示「股票xxxxx」
        # dry_run 仅做数据拉取，不需要名称预取，避免额外网络开销
        if not dry_run:
            self.fetcher_manager.prefetch_stock_names(stock_codes, use_bulk=False)

        # 单股推送模式（#55）：从配置读取
        single_stock_notify = getattr(self.config, 'single_stock_notify', False)
        # Issue #119: 从配置读取报告类型
        report_type_str = getattr(self.config, 'report_type', 'simple').lower()
        if report_type_str == 'brief':
            report_type = ReportType.BRIEF
        elif report_type_str == 'full':
            report_type = ReportType.FULL
        else:
            report_type = ReportType.SIMPLE
        # Issue #128: 从配置读取分析间隔
        analysis_delay = getattr(self.config, 'analysis_delay', 0)

        if single_stock_notify:
            logger.info(
                "Single-stock notification mode enabled; analysis remains concurrent and "
                "notifications are serialized while collecting results: report_type=%s",
                report_type_str,
            )
        
        results: List[AnalysisResult] = []
        
        # 使用线程池并发处理
        # 注意：max_workers 设置较低（默认3）以避免触发反爬
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任务
            future_to_code = {
                executor.submit(
                    self._process_single_stock_for_batch,
                    code,
                    skip_analysis=dry_run,
                    single_stock_notify=False,
                    report_type=report_type,  # Issue #119: 传递报告类型
                    analysis_query_id=uuid.uuid4().hex,
                    current_time=resume_reference_time,
                ): code
                for code in stock_codes
            }
            
            # 收集结果
            for idx, future in enumerate(as_completed(future_to_code)):
                code = future_to_code[future]
                try:
                    result = future.result()
                    if result and result.success:
                        results.append(result)
                        if single_stock_notify and send_notification and not dry_run:
                            delivery_diag_token = (
                                self._activate_delivery_diagnostic_context([result])
                            )
                            try:
                                self._send_single_stock_notification(
                                    result,
                                    report_type=report_type,
                                    fallback_code=code,
                                )
                            finally:
                                reset_run_diagnostic_context(delivery_diag_token)
                    elif result and not result.success:
                        logger.warning(
                            "[%s] Unsuccessful analysis result excluded from aggregate output",
                            code,
                        )

                    # Issue #128: 分析间隔 - 在个股分析和大盘分析之间添加延迟
                    if idx < len(stock_codes) - 1 and analysis_delay > 0:
                        # 注意：此 sleep 发生在“主线程收集 future 的循环”中，
                        # 并不会阻止线程池中的任务同时发起网络请求。
                        # 因此它对降低并发请求峰值的效果有限；真正的峰值主要由 max_workers 决定。
                        # 该行为目前保留（按需求不改逻辑）。
                        logger.debug(
                            "Waiting %s seconds before collecting the next stock result",
                            analysis_delay,
                        )
                        time.sleep(analysis_delay)

                except Exception as e:  # broad-exception: fallback_recorded - Worker failures are safely logged and the remaining stock tasks continue.
                    log_safe_exception(
                        logger,
                        "Stock analysis task failed",
                        e,
                        error_code="pipeline_stock_task_failed",
                        context={"stock_code": code},
                    )
        
        # 统计
        elapsed_time = time.time() - start_time
        
        # dry-run 模式下，数据获取成功即视为成功
        if dry_run:
            # 检查哪些股票的最新可复用交易日数据已存在
            success_count = sum(
                1
                for code in stock_codes
                if self.db.has_today_data(
                    code,
                    self._resolve_resume_target_date(
                        code, current_time=resume_reference_time
                    ),
                )
            )
            fail_count = len(stock_codes) - success_count
        else:
            success_count = len(results)
            fail_count = len(stock_codes) - success_count
        
        logger.info("===== Analysis completed =====")
        logger.info(
            "Analysis summary: succeeded=%s failed=%s elapsed_seconds=%.2f",
            success_count,
            fail_count,
            elapsed_time,
        )
        
        delivery_diag_token = (
            self._activate_delivery_diagnostic_context(results)
            if results and not dry_run
            else None
        )
        try:
            # Always save the report locally, independently of notification delivery.
            if results and not dry_run:
                self._save_local_report(results, report_type)
                self._refresh_saved_diagnostic_snapshot(results=results)
            else:
                render_skip_reason = (
                    "dry_run" if dry_run else "no_successful_results"
                )
                self._record_pipeline_stage_result(
                    PipelineStageResult.skipped(
                        PipelineStageName.RENDER,
                        reason=render_skip_reason,
                    ),
                    input_summary={
                        "result_count": len(results),
                        "dry_run": dry_run,
                        "report_type": report_type.value,
                    },
                    output_summary={"reason": render_skip_reason},
                )

            if not (results and send_notification and not dry_run):
                dispatch_skip_reason = (
                    "dry_run"
                    if dry_run
                    else (
                        "notification_disabled"
                        if not send_notification
                        else "no_successful_results"
                    )
                )
                self._record_pipeline_stage_result(
                    PipelineStageResult.skipped(
                        PipelineStageName.DISPATCH,
                        reason=dispatch_skip_reason,
                    ),
                    input_summary={
                        "result_count": len(results),
                        "dry_run": dry_run,
                        "send_notification": send_notification,
                    },
                    output_summary={"reason": dispatch_skip_reason},
                )
                if results and not dry_run:
                    self._refresh_saved_diagnostic_snapshot(results=results)

            # Deliver notifications; single-stock mode skips duplicate aggregate delivery.
            if results and send_notification and not dry_run:
                if single_stock_notify:
                    # Save the aggregate report without delivering it again.
                    logger.info(
                        "Single-stock notification mode: skipping aggregate delivery and saving locally"
                    )
                    self._send_notifications(results, report_type, skip_push=True)
                elif merge_notification:
                    # Issue #190: defer delivery until stock and market reports are combined.
                    logger.info(
                        "Combined-delivery mode: deferring delivery until stock and market reports are merged"
                    )
                    self._send_notifications(results, report_type, skip_push=True)
                else:
                    self._send_notifications(results, report_type)
        finally:
            reset_run_diagnostic_context(delivery_diag_token)
        
        return results


def _clone_analysis_stage_descriptor(descriptor: Any) -> Any:
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
        raise TypeError("Analysis stage descriptor must wrap a Python function")

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

    if descriptor_type is not None:
        return descriptor_type(rebound)
    return rebound


def _bind_analysis_stage_methods() -> Tuple[str, ...]:
    """Bind every extracted analysis method back onto the legacy facade."""

    bound_names: List[str] = []
    for name, descriptor in vars(_AnalysisStageMixin).items():
        function = (
            descriptor.__func__
            if isinstance(descriptor, (staticmethod, classmethod))
            else descriptor
        )
        if name.startswith("__") or not isinstance(function, _FunctionType):
            continue
        setattr(
            StockAnalysisPipeline,
            name,
            _clone_analysis_stage_descriptor(descriptor),
        )
        bound_names.append(name)
    return tuple(bound_names)


_ANALYSIS_STAGE_METHOD_NAMES = _bind_analysis_stage_methods()
