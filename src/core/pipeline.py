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
from types import SimpleNamespace
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
from src.core.stages.delivery import _DeliveryStageMixin
from data_provider.us_index_mapping import is_us_stock_code
logger = logging.getLogger(__name__)

# Keep legacy module exports alive while concrete stages move behind the facade.
_PIPELINE_COMPAT_EXPORTS = (
    defaultdict,
    ExitStack,
    NotificationChannel,
    record_notification_run,
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
    
    def analyze_stock(
        self,
        code: str,
        report_type: ReportType,
        query_id: str,
        current_time: Optional[datetime] = None,
    ) -> Optional[AnalysisResult]:
        """
        分析单只股票（增强版：含量比、换手率、筹码分析、多维度情报）
        
        流程：
        1. 获取实时行情（量比、换手率）- 通过 DataFetcherManager 自动故障切换
        2. 获取筹码分布 - 通过 DataFetcherManager 带熔断保护
        3. 进行趋势分析（基于交易理念）
        4. 多维度情报搜索（最新消息+风险排查+业绩预期）
        5. 从数据库获取分析上下文
        6. 调用 AI 进行综合分析
        
        Args:
            query_id: 查询链路关联 id
            code: 股票代码
            report_type: 报告类型
            current_time: 本轮运行冻结的参考时间，用于统一市场阶段上下文
            
        Returns:
            AnalysisResult 或 None（如果分析失败）
        """
        stock_name = code
        active_stage: Optional[PipelineStageObservation] = None
        try:
            daily_market_context_enabled = self._is_daily_market_context_enabled()
            active_stage = observe_pipeline_stage(
                "fetch",
                input_summary={
                    "stock_code": code,
                    "operation": "assemble_market_inputs",
                    "realtime_enabled": bool(self.config.enable_realtime_quote),
                    "chip_enabled": bool(self.config.enable_chip_distribution),
                    "daily_market_context_enabled": daily_market_context_enabled,
                },
                retryable=True,
            )
            portfolio_context = getattr(self, "portfolio_context", None)
            if not isinstance(portfolio_context, dict):
                portfolio_context = None
            market = get_market_for_stock(normalize_stock_code(code))
            market_phase_context = build_market_phase_context(
                market=market,
                current_time=current_time,
                trigger_source=self.query_source,
                analysis_phase=getattr(self, "analysis_phase", "auto"),
            )
            market_phase_context_dict = market_phase_context.to_dict()
            market_phase_summary = render_market_phase_summary(market_phase_context_dict)
            report_language = normalize_report_language(getattr(self.config, "report_language", "zh"))
            daily_market_target_date = self._coerce_daily_market_context_date(
                getattr(market_phase_context, "effective_daily_bar_date", None)
                or market_phase_context_dict.get("effective_daily_bar_date")
            )
            if daily_market_target_date is None:
                daily_market_target_date = get_effective_trading_date(
                    market,
                    current_time=current_time,
                )
            daily_market_context = self._load_daily_market_context(
                market,
                target_date=daily_market_target_date,
            )

            self._emit_progress(18, f"{code}：正在获取行情与筹码数据")
            # 获取股票名称（先走轻量名称路径，后续若 realtime_quote 有 name 再覆盖）
            stock_name = self.fetcher_manager.get_stock_name(code, allow_realtime=False)

            # Step 1: 获取实时行情（量比、换手率等）- 使用统一入口，自动故障切换
            realtime_quote = None
            try:
                if self.config.enable_realtime_quote:
                    realtime_quote = self.fetcher_manager.get_realtime_quote(code, log_final_failure=False)
                    if realtime_quote:
                        # 使用实时行情返回的真实股票名称
                        if realtime_quote.name:
                            stock_name = realtime_quote.name
                        # 兼容不同数据源的字段（有些数据源可能没有 volume_ratio）
                        volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
                        turnover_rate = getattr(realtime_quote, 'turnover_rate', None)
                        logger.info(
                            "%s(%s) realtime quote: price=%s volume_ratio=%s "
                            "turnover_rate=%s%% source=%s",
                            stock_name,
                            code,
                            realtime_quote.price,
                            volume_ratio,
                            turnover_rate,
                            realtime_quote.source.value
                            if hasattr(realtime_quote, "source")
                            else "unknown",
                        )
                    else:
                        logger.warning(
                            "%s(%s) all realtime quote sources failed; using historical close price",
                            stock_name,
                            code,
                        )
                else:
                    logger.info(
                        "%s(%s) realtime quotes are disabled; using historical close price",
                        stock_name,
                        code,
                    )
            except Exception as e:  # broad-exception: fallback_recorded - Realtime failure is safely logged before historical-price fallback.
                log_safe_exception(
                    logger,
                    "Realtime quote retrieval failed; using historical close data",
                    e,
                    error_code="pipeline_realtime_quote_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )

            # 如果还是没有名称，使用代码作为名称
            if not stock_name:
                stock_name = f'股票{code}'

            # Step 2: 获取筹码分布 - 使用统一入口，带熔断保护
            chip_data = None
            try:
                chip_data = self.fetcher_manager.get_chip_distribution(code)
                if chip_data:
                    logger.info(
                        "%s(%s) chip distribution: profit_ratio=%.1f%% concentration_90=%.2f%%",
                        stock_name,
                        code,
                        chip_data.profit_ratio * 100,
                        chip_data.concentration_90 * 100,
                    )
                else:
                    logger.debug(
                        "%s(%s) chip-distribution data is unavailable or disabled",
                        stock_name,
                        code,
                    )
            except Exception as e:  # broad-exception: fallback_recorded - Chip-data failure is safely logged before optional-input degradation.
                log_safe_exception(
                    logger,
                    "Chip distribution retrieval failed",
                    e,
                    error_code="pipeline_chip_distribution_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )

            # If agent mode is explicitly enabled, or specific agent skills are configured, use the Agent analysis pipeline.
            # NOTE: use config.agent_mode (explicit opt-in) instead of
            # config.is_agent_available() so that users who only configured an
            # API Key for the traditional analysis path are not silently
            # switched to Agent mode (which is slower and more expensive).
            use_agent = getattr(self.config, 'agent_mode', False)
            if not use_agent:
                if self.analysis_skills:
                    use_agent = True
                    logger.info(f"{stock_name}({code}) Auto-enabled agent mode due to request skills: {self.analysis_skills}")
            if not use_agent:
                # Auto-enable agent mode when specific skills are configured (e.g., scheduled task with strategy)
                configured_skills = getattr(self.config, 'agent_skills', [])
                if configured_skills and configured_skills != ['all']:
                    use_agent = True
                    logger.info(f"{stock_name}({code}) Auto-enabled agent mode due to configured skills: {configured_skills}")

            self._emit_progress(32, f"{stock_name}：正在聚合基本面与趋势数据")

            # Step 2.5: 基本面能力聚合（统一入口，异常降级）
            # - 失败时返回 partial/failed，不影响既有技术面/新闻链路
            # - 关闭开关时仍返回 not_supported 结构
            fundamental_context = None
            try:
                fundamental_context = self.fetcher_manager.get_fundamental_context(
                    code,
                    budget_seconds=getattr(
                        self.config,
                        'fundamental_stage_timeout_seconds',
                        FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
                    ),
                )
            except Exception as e:  # broad-exception: fallback_recorded - Fundamental failure is safely logged before a failed-context fallback is built.
                log_safe_exception(
                    logger,
                    "Fundamental data aggregation failed",
                    e,
                    error_code="pipeline_fundamental_aggregation_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )
                fundamental_context = self.fetcher_manager.build_failed_fundamental_context(code, str(e))

            fundamental_context = self._attach_belong_boards_to_fundamental_context(
                code,
                fundamental_context,
            )
            market_structure_context = self._build_market_structure_context(
                code=code,
                stock_name=stock_name,
                market=market,
                fundamental_context=fundamental_context,
                trade_date=daily_market_target_date,
                market_phase_summary=market_phase_summary,
            )

            # P0: write-only snapshot, fail-open, no read dependency on this table.
            try:
                self.db.save_fundamental_snapshot(
                    query_id=query_id,
                    code=code,
                    payload=fundamental_context,
                    source_chain=fundamental_context.get("source_chain", []),
                    coverage=fundamental_context.get("coverage", {}),
                )
            except Exception as e:  # broad-exception: optional_metadata - The write-only fundamental snapshot is non-authoritative and safely logged.
                log_safe_exception(
                    logger,
                    "Fundamental snapshot persistence failed",
                    e,
                    error_code="pipeline_fundamental_snapshot_save_failed",
                    level=logging.DEBUG,
                    context={"stock_code": code},
                )

            # Step 3: 趋势分析（基于交易理念）— 在 Agent 分支之前执行，供两条路径共用
            trend_result: Optional[TrendAnalysisResult] = None
            try:
                from src.services.history_loader import get_frozen_target_date
                _mkt = get_market_for_stock(normalize_stock_code(code))
                frozen = get_frozen_target_date()
                end_date = frozen if frozen else get_market_now(_mkt).date()
                start_date = end_date - timedelta(days=89)  # ~60 trading days for MA60
                historical_bars = self.db.get_data_range(code, start_date, end_date)
                if historical_bars:
                    df = pd.DataFrame([bar.to_dict() for bar in historical_bars])
                    # Issue #234: Augment with realtime for intraday MA calculation
                    if self.config.enable_realtime_quote and realtime_quote:
                        df = self._augment_historical_with_realtime(df, realtime_quote, code)
                    trend_result = self.trend_analyzer.analyze(df, code)
                    logger.info(
                        "%s(%s) trend analysis: status=%s buy_signal=%s score=%s",
                        stock_name,
                        code,
                        trend_result.trend_status.value,
                        trend_result.buy_signal.value,
                        trend_result.signal_score,
                    )
            except Exception as e:  # broad-exception: fallback_recorded - Trend failure is safely logged before analysis continues without trend input.
                log_safe_exception(
                    logger,
                    "Trend analysis failed",
                    e,
                    error_code="pipeline_trend_analysis_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )

            fundamental_status = (
                str(fundamental_context.get("status") or "").lower()
                if isinstance(fundamental_context, dict)
                else "missing"
            )
            fetch_degraded = bool(
                (self.config.enable_realtime_quote and realtime_quote is None)
                or (
                    getattr(self.config, "enable_chip_distribution", False)
                    and chip_data is None
                )
                or fundamental_status in {"failed", "partial", "missing"}
                or trend_result is None
                or (
                    daily_market_context_enabled
                    and daily_market_context is None
                )
            )
            fetch_result = (
                PipelineStageResult.degraded(
                    PipelineStageName.FETCH,
                    {
                        "realtime_quote": realtime_quote,
                        "chip_data": chip_data,
                        "fundamental_context": fundamental_context,
                        "trend_result": trend_result,
                        "daily_market_context": daily_market_context,
                    },
                    reason=(
                        "One or more market inputs were unavailable; "
                        "analysis continued with existing fallbacks."
                    ),
                    retryable=True,
                )
                if fetch_degraded
                else PipelineStageResult.success(
                    PipelineStageName.FETCH,
                    {
                        "realtime_quote": realtime_quote,
                        "chip_data": chip_data,
                        "fundamental_context": fundamental_context,
                        "trend_result": trend_result,
                        "daily_market_context": daily_market_context,
                    },
                )
            )
            self._finish_pipeline_stage(
                active_stage,
                fetch_result,
                output_summary={
                    "realtime_available": realtime_quote is not None,
                    "chip_available": chip_data is not None,
                    "fundamental_status": fundamental_status or "available",
                    "trend_available": trend_result is not None,
                    "daily_market_context_enabled": daily_market_context_enabled,
                    "daily_market_context_available": daily_market_context is not None,
                },
            )
            active_stage = None

            if use_agent:
                logger.info("%s(%s) running analysis in Agent mode", stock_name, code)
                self._emit_progress(58, f"{stock_name}：正在切换 Agent 分析链路")
                return self._analyze_with_agent(
                    code,
                    report_type,
                    query_id,
                    stock_name,
                    realtime_quote,
                    chip_data,
                    fundamental_context,
                    trend_result,
                    market_phase_context=market_phase_context_dict,
                    market_phase_summary=market_phase_summary,
                    daily_market_context=daily_market_context,
                    portfolio_context=portfolio_context,
                    market_structure_context=market_structure_context,
                )

            # Step 4: 多维度情报搜索（最新消息+风险排查+业绩预期）
            active_stage = observe_pipeline_stage(
                "intelligence",
                input_summary={
                    "stock_code": code,
                    "market": market or "cn",
                    "remote_search_available": bool(
                        self.search_service is not None
                        and self.search_service.is_available
                    ),
                },
                retryable=True,
            )
            news_context = None
            fresh_intelligence_available = False
            persisted_intelligence_context = self._load_persisted_intelligence_context(
                code=code,
                stock_name=stock_name,
                market=market or "cn",
            )
            news_result_count: Optional[int] = None
            self._emit_progress(46, f"{stock_name}：正在检索新闻与舆情")
            if self.search_service is not None and self.search_service.is_available:
                logger.info("%s(%s) starting multi-dimensional intelligence search", stock_name, code)

                # 使用多维度搜索（最多5次搜索）
                intel_results = self.search_service.search_comprehensive_intel(
                    stock_code=code,
                    stock_name=stock_name,
                    max_searches=5
                )

                # 格式化情报报告
                if intel_results:
                    news_context = self.search_service.format_intel_report(intel_results, stock_name)
                    total_results = sum(
                        len(r.results) for r in intel_results.values() if r.success
                    )
                    news_result_count = total_results
                    fresh_intelligence_available = bool(
                        total_results > 0 and news_context
                    )
                    logger.info(
                        "%s(%s) intelligence search completed: result_count=%s",
                        stock_name,
                        code,
                        total_results,
                    )
                    logger.debug(
                        "%s(%s) formatted intelligence summary: character_count=%s",
                        stock_name,
                        code,
                        len(news_context or ""),
                    )

                    # 保存新闻情报到数据库（用于后续复盘与查询）
                    try:
                        query_context = self._build_query_context(query_id=query_id)
                        for dim_name, response in intel_results.items():
                            if response and response.success and response.results:
                                self.db.save_news_intel(
                                    code=code,
                                    name=stock_name,
                                    dimension=dim_name,
                                    query=response.query,
                                    response=response,
                                    query_context=query_context
                                )
                    except Exception as e:  # broad-exception: optional_metadata - Intelligence evidence remains usable when its optional cache write fails.
                        log_safe_exception(
                            logger,
                            "News intelligence persistence failed",
                            e,
                            error_code="pipeline_news_intelligence_save_failed",
                            level=logging.WARNING,
                            context={"stock_code": code},
                        )
            else:
                logger.info(
                    "%s(%s) search service unavailable; skipping intelligence search",
                    stock_name,
                    code,
                )

            # Step 4.5: Social sentiment intelligence (US stocks only)
            if self.social_sentiment_service is not None and self.social_sentiment_service.is_available and is_us_stock_code(code):
                try:
                    social_context = self.social_sentiment_service.get_social_context(code)
                    if social_context:
                        fresh_intelligence_available = True
                        logger.info(f"{stock_name}({code}) Social sentiment data retrieved")
                        if news_context:
                            news_context = news_context + "\n\n" + social_context
                        else:
                            news_context = social_context
                except Exception as e:  # broad-exception: fallback_recorded - Social-intelligence failure is safely logged before optional-input degradation.
                    log_safe_exception(
                        logger,
                        "Social sentiment retrieval failed",
                        e,
                        error_code="pipeline_social_sentiment_fetch_failed",
                        level=logging.WARNING,
                        context={"stock_code": code},
                    )

            if persisted_intelligence_context:
                news_context = (
                    f"{news_context}\n\n{persisted_intelligence_context}"
                    if news_context
                    else persisted_intelligence_context
                )

            remote_search_available = bool(
                self.search_service is not None
                and self.search_service.is_available
            )
            using_persisted_fallback = bool(
                persisted_intelligence_context
                and not fresh_intelligence_available
            )
            remote_search_empty = bool(
                remote_search_available
                and (news_result_count is None or news_result_count <= 0)
            )
            intelligence_degraded = bool(
                not news_context
                or using_persisted_fallback
                or not remote_search_available
                or remote_search_empty
            )
            intelligence_degradation_reason = None
            if not news_context:
                intelligence_degradation_reason = (
                    "No intelligence evidence was available; analysis continued without it."
                )
            elif using_persisted_fallback:
                intelligence_degradation_reason = (
                    "Fresh intelligence was unavailable; persisted evidence was used."
                )
            elif not remote_search_available:
                intelligence_degradation_reason = (
                    "Remote intelligence search was unavailable; analysis continued with available evidence."
                )
            elif remote_search_empty:
                intelligence_degradation_reason = (
                    "Remote intelligence search returned no fresh results; analysis continued with available evidence."
                )
            intelligence_result = (
                PipelineStageResult.degraded(
                    PipelineStageName.INTELLIGENCE,
                    news_context,
                    reason=intelligence_degradation_reason,
                    retryable=True,
                )
                if intelligence_degraded
                else PipelineStageResult.success(
                    PipelineStageName.INTELLIGENCE,
                    news_context,
                )
            )
            self._finish_pipeline_stage(
                active_stage,
                intelligence_result,
                output_summary={
                    "intelligence_available": bool(news_context),
                    "fresh_intelligence_available": fresh_intelligence_available,
                    "remote_result_count": news_result_count,
                    "persisted_evidence_available": bool(
                        persisted_intelligence_context
                    ),
                    "using_persisted_fallback": using_persisted_fallback,
                },
            )
            active_stage = None

            # Step 5: 获取分析上下文（技术面数据）
            active_stage = observe_pipeline_stage(
                "context",
                input_summary={
                    "stock_code": code,
                    "has_realtime": realtime_quote is not None,
                    "has_chip": chip_data is not None,
                    "has_fundamentals": isinstance(fundamental_context, dict),
                    "has_intelligence": bool(news_context),
                },
                retryable=True,
            )
            self._emit_progress(58, f"{stock_name}：正在整理分析上下文")
            context = self._get_analysis_context_with_market_fallback(code)
            context_used_missing_fallback = context is None

            if context is None:
                logger.warning(
                    "%s(%s) historical data unavailable; analysis will use news and realtime quotes only",
                    stock_name,
                    code,
                )
                _mkt_date = get_market_now(
                    get_market_for_stock(normalize_stock_code(code))
                ).date()
                context = {
                    'code': code,
                    'stock_name': stock_name,
                    'date': _mkt_date.isoformat(),
                    'data_missing': True,
                    'today': {},
                    'yesterday': {}
                }
            
            # Step 6: 增强上下文数据（添加实时行情、筹码、趋势分析结果、股票名称）
            enhanced_context = self._enhance_context(
                context, 
                realtime_quote, 
                chip_data,
                trend_result,
                stock_name,  # 传入股票名称
                fundamental_context,
                market_phase_context=market_phase_context_dict,
                portfolio_context=portfolio_context,
            )
            enhanced_context["market_phase_context"] = market_phase_context_dict
            self._attach_daily_market_context(
                enhanced_context,
                daily_market_context,
                report_language=report_language,
            )
            if portfolio_context is not None:
                enhanced_context["portfolio_context"] = dict(portfolio_context)
            if isinstance(market_structure_context, dict):
                enhanced_context["market_structure_context"] = market_structure_context
            
            # Step 7: 调用 AI 分析（传入增强的上下文和新闻）
            (
                analysis_context_pack_summary,
                analysis_context_pack_overview,
            ) = self._build_analysis_context_pack_outputs(
                self._build_legacy_analysis_artifacts(
                    code=code,
                    stock_name=stock_name,
                    market=market,
                    phase=market_phase_context_dict,
                    context=context,
                    enhanced_context=enhanced_context,
                    realtime_quote=realtime_quote,
                    trend_result=trend_result,
                    chip_data=chip_data,
                    fundamental_context=fundamental_context,
                    news_context=news_context,
                    news_result_count=news_result_count,
                    query_id=query_id,
                    portfolio_context=portfolio_context,
                ),
                report_language=report_language,
                code=code,
                query_id=query_id,
            )
            pack_counts = (
                analysis_context_pack_overview.get("counts", {})
                if isinstance(analysis_context_pack_overview, dict)
                else {}
            )
            degraded_block_count = sum(
                max(0, count)
                for status in (
                    "missing",
                    "fallback",
                    "stale",
                    "estimated",
                    "partial",
                    "fetch_failed",
                )
                for count in (pack_counts.get(status),)
                if isinstance(count, int) and not isinstance(count, bool)
            )
            context_pack_available = bool(analysis_context_pack_summary)
            context_degraded = bool(
                not context_pack_available
                or context_used_missing_fallback
                or degraded_block_count
            )
            context_degradation_reason = (
                "ContextPack output generation was unavailable."
                if not context_pack_available
                else (
                    "ContextPack contains missing or fallback inputs."
                    if context_degraded
                    else None
                )
            )
            context_result = (
                PipelineStageResult.degraded(
                    PipelineStageName.CONTEXT,
                    enhanced_context,
                    reason=context_degradation_reason,
                    retryable=True,
                )
                if context_degraded
                else PipelineStageResult.success(
                    PipelineStageName.CONTEXT,
                    enhanced_context,
                )
            )
            self._finish_pipeline_stage(
                active_stage,
                context_result,
                output_summary={
                    "context_pack_available": context_pack_available,
                    "degraded_block_count": degraded_block_count,
                    "historical_context_fallback": context_used_missing_fallback,
                },
            )
            active_stage = None
            llm_progress_state = {"last_progress": 64}

            def _on_llm_stream(chars_received: int) -> None:
                dynamic_progress = min(92, 64 + min(chars_received // 80, 28))
                if dynamic_progress <= llm_progress_state["last_progress"]:
                    return
                llm_progress_state["last_progress"] = dynamic_progress
                self._emit_progress(
                    dynamic_progress,
                    f"{stock_name}：LLM 正在生成分析结果（已接收 {chars_received} 字符）",
                )

            active_stage = observe_pipeline_stage(
                "analyze",
                input_summary={
                    "stock_code": code,
                    "mode": "legacy",
                    "report_type": report_type.value,
                    "context_pack_available": bool(analysis_context_pack_summary),
                },
                retryable=True,
            )
            self._emit_progress(64, f"{stock_name}：正在请求 LLM 生成报告")
            llm_started_at = time.monotonic()
            try:
                record_llm_run_started(
                    model=getattr(self.config, "litellm_model", None),
                    call_type="analysis",
                )
                result = self.analyzer.analyze(
                    enhanced_context,
                    news_context=news_context,
                    progress_callback=self._emit_progress,
                    stream_progress_callback=_on_llm_stream,
                    analysis_context_pack_summary=analysis_context_pack_summary,
                )
                llm_duration_ms = int((time.monotonic() - llm_started_at) * 1000)
                record_llm_run(
                    success=bool(result and getattr(result, "success", True)),
                    model=getattr(result, "model_used", None) if result else None,
                    call_type="analysis",
                    duration_ms=llm_duration_ms,
                    error_type=(
                        None
                        if result and getattr(result, "success", True)
                        else "AnalysisResultError"
                    ),
                    error_message=(
                        getattr(result, "error_message", None)
                        if result and not getattr(result, "success", True)
                        else ("LLM returned empty result" if result is None else None)
                    ),
                )
            except Exception as exc:
                record_llm_run(
                    success=False,
                    model=getattr(self.config, "litellm_model", None),
                    call_type="analysis",
                    duration_ms=int((time.monotonic() - llm_started_at) * 1000),
                    error_type=type(exc).__name__,
                    error_message=exc,
                )
                raise

            # Step 7.5: 填充分析时的价格信息到 result
            if result:
                self._emit_progress(94, f"{stock_name}：正在校验并整理分析结果")
                result.query_id = query_id
                realtime_data = enhanced_context.get('realtime', {})
                result.current_price = realtime_data.get('price')
                result.change_pct = realtime_data.get('change_pct')

            # Step 7.6: chip_structure fallback (Issue #589) and unavailable collapse
            if result:
                normalize_chip_structure_availability(result, chip_data)

            # Step 7.7: price_position fallback
            if result:
                fill_price_position_if_needed(result, trend_result, realtime_quote)
                action_source_advice = getattr(result, "operation_advice", None)
                stabilize_decision_with_structure(result, trend_result, fundamental_context)
                adjustments = apply_phase_decision_guardrails(
                    result,
                    market_phase_summary=market_phase_summary,
                    analysis_context_pack_overview=analysis_context_pack_overview,
                    report_language=getattr(result, "report_language", None)
                    or getattr(self.config, "report_language", "zh"),
                )
                if adjustments:
                    logger.info("[phase_decision_guardrail] Applied adjustments for %s: %s", code, adjustments)
                market_context_adjustments = apply_daily_market_context_guardrail(
                    result,
                    daily_market_context=enhanced_context.get("daily_market_context"),
                    report_language=getattr(result, "report_language", None)
                    or getattr(self.config, "report_language", "zh"),
                )
                if market_context_adjustments:
                    logger.info(
                        "[daily_market_context_guardrail] Applied adjustments for %s: %s",
                        code,
                        market_context_adjustments,
                    )
                if isinstance(fundamental_context, dict):
                    result.fundamental_context = fundamental_context
                if isinstance(market_structure_context, dict):
                    result.market_structure_context = market_structure_context
                result.market_phase_summary = market_phase_summary
                result.analysis_context_pack_overview = analysis_context_pack_overview
                self._refresh_decision_action_for_final_result(
                    result,
                    report_type=report_type.value,
                    previous_operation_advice=action_source_advice,
                )

            analysis_succeeded = bool(result and getattr(result, "success", True))
            analysis_degradation_reason = (
                getattr(result, "error_message", None)
                if result is not None and not analysis_succeeded
                else ("Analysis returned no result." if result is None else None)
            )
            analysis_stage_result = (
                PipelineStageResult.success(PipelineStageName.ANALYZE, result)
                if analysis_succeeded
                else PipelineStageResult.failed(
                    PipelineStageName.ANALYZE,
                    value=result,
                    retryable=True,
                    reason=analysis_degradation_reason,
                )
            )
            self._finish_pipeline_stage(
                active_stage,
                analysis_stage_result,
                output_summary={
                    "analysis_result_available": result is not None,
                    "analysis_success": analysis_succeeded,
                    "model": getattr(result, "model_used", None) if result else None,
                },
            )
            active_stage = None

            # Step 8: 保存分析历史记录
            if result and result.success:
                active_stage = observe_pipeline_stage(
                    "persist",
                    input_summary={
                        "stock_code": code,
                        "query_id": query_id,
                        "report_type": report_type.value,
                        "save_context_snapshot": bool(self.save_context_snapshot),
                    },
                    retryable=True,
                )

                def _legacy_context_snapshot() -> Dict[str, Any]:
                    self._emit_progress(97, f"{stock_name}：正在保存分析报告")
                    return self._build_context_snapshot(
                        enhanced_context=enhanced_context,
                        news_content=news_context,
                        news_result_count=news_result_count,
                        realtime_quote=realtime_quote,
                        chip_data=chip_data,
                        analysis_context_pack_overview=analysis_context_pack_overview,
                        market_phase_summary=market_phase_summary,
                    )

                persistence_result = self._persist_analysis_history_stage(
                    result=result,
                    query_id=query_id,
                    report_type=report_type.value,
                    news_content=news_context,
                    context_snapshot_factory=_legacy_context_snapshot,
                    portfolio_context=portfolio_context,
                    failure_reason="Analysis history was not saved.",
                    failure_message="Analysis history persistence failed",
                    failure_error_code="pipeline_analysis_history_save_failed",
                )
                persistence_value = persistence_result.value
                self._finish_pipeline_stage(
                    active_stage,
                    persistence_result,
                    output_summary={
                        "history_saved": bool(
                            persistence_value and persistence_value.saved
                        ),
                        "analysis_history_id": (
                            persistence_value.history_id
                            if persistence_value is not None
                            else None
                        ),
                        "reused": persistence_result.reused,
                    },
                )
                active_stage = None
                context_snapshot = (
                    persistence_value.context_snapshot
                    if persistence_value is not None
                    else {}
                )
                latest_diagnostic_snapshot = current_diagnostic_snapshot()
                if latest_diagnostic_snapshot is not None:
                    context_snapshot["diagnostics"] = latest_diagnostic_snapshot
                    result.diagnostic_context_snapshot = context_snapshot
                if persistence_value is not None and persistence_value.history_id:
                    self._refresh_saved_diagnostic_snapshot(result=result)
            else:
                self._record_pipeline_stage_result(
                    PipelineStageResult.skipped(
                        PipelineStageName.PERSIST,
                        reason="analysis_unsuccessful",
                    ),
                    input_summary={
                        "stock_code": code,
                        "query_id": query_id,
                    },
                    output_summary={"reason": "analysis_unsuccessful"},
                )

            return result

        except Exception as e:  # broad-exception: fallback_recorded - Analysis failures are safely logged and isolated to the current stock.
            if active_stage is not None and not active_stage.finished:
                self._finish_pipeline_stage(
                    active_stage,
                    PipelineStageResult.failed(
                        active_stage.stage,
                        error=e,
                        retryable=active_stage.retryable,
                    ),
                )
            log_safe_exception(
                logger,
                "Stock analysis failed",
                e,
                error_code="pipeline_stock_analysis_failed",
                context={"stock_code": code},
            )
            return None
    
    def _enhance_context(
        self,
        context: Dict[str, Any],
        realtime_quote,
        chip_data: Optional[ChipDistribution],
        trend_result: Optional[TrendAnalysisResult],
        stock_name: str = "",
        fundamental_context: Optional[Dict[str, Any]] = None,
        market_phase_context: Optional[Dict[str, Any]] = None,
        portfolio_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        增强分析上下文
        
        将实时行情、筹码分布、趋势分析结果、股票名称添加到上下文中
        
        Args:
            context: 原始上下文
            realtime_quote: 实时行情数据（UnifiedRealtimeQuote 或 None）
            chip_data: 筹码分布数据
            trend_result: 趋势分析结果
            stock_name: 股票名称
            market_phase_context: 已构建的市场阶段上下文，用于标记盘中 partial bar
            
        Returns:
            增强后的上下文
        """
        enhanced = context.copy()
        enhanced["report_language"] = normalize_report_language(getattr(self.config, "report_language", "zh"))
        
        # 添加股票名称
        if stock_name:
            enhanced['stock_name'] = stock_name
        elif realtime_quote and getattr(realtime_quote, 'name', None):
            enhanced['stock_name'] = realtime_quote.name
        if isinstance(portfolio_context, dict):
            enhanced["portfolio_context"] = dict(portfolio_context)

        # 将运行时搜索窗口透传给 analyzer，避免与全局配置重新读取产生窗口不一致
        enhanced['news_window_days'] = getattr(self.search_service, "news_window_days", 3)
        
        # 添加实时行情（兼容不同数据源的字段差异）
        if realtime_quote:
            # 使用 getattr 安全获取字段，缺失字段返回 None 或默认值
            volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
            quote_source = getattr(realtime_quote, 'source', None)
            quote_source_name = getattr(quote_source, 'value', quote_source)
            quote_source_name = str(quote_source_name) if quote_source_name is not None else None
            enhanced['realtime'] = {
                'name': getattr(realtime_quote, 'name', ''),
                'price': getattr(realtime_quote, 'price', None),
                'change_pct': getattr(realtime_quote, 'change_pct', None),
                'volume_ratio': volume_ratio,
                'volume_ratio_desc': self._describe_volume_ratio(volume_ratio) if volume_ratio else '无数据',
                'turnover_rate': getattr(realtime_quote, 'turnover_rate', None),
                'pe_ratio': getattr(realtime_quote, 'pe_ratio', None),
                'pb_ratio': getattr(realtime_quote, 'pb_ratio', None),
                'total_mv': getattr(realtime_quote, 'total_mv', None),
                'circ_mv': getattr(realtime_quote, 'circ_mv', None),
                'change_60d': getattr(realtime_quote, 'change_60d', None),
                'source': quote_source_name,
                'fetched_at': getattr(realtime_quote, 'fetched_at', None),
                'provider_timestamp': getattr(realtime_quote, 'provider_timestamp', None),
                'is_stale': getattr(realtime_quote, 'is_stale', None),
                'stale_seconds': getattr(realtime_quote, 'stale_seconds', None),
                'fallback_from': getattr(realtime_quote, 'fallback_from', None),
            }
            # 移除 None 值以减少上下文大小
            enhanced['realtime'] = {k: v for k, v in enhanced['realtime'].items() if v is not None}
        
        # 添加筹码分布
        if chip_data:
            current_price = getattr(realtime_quote, 'price', 0) if realtime_quote else 0
            enhanced['chip'] = {
                'profit_ratio': chip_data.profit_ratio,
                'avg_cost': chip_data.avg_cost,
                'concentration_90': chip_data.concentration_90,
                'concentration_70': chip_data.concentration_70,
                'chip_status': chip_data.get_chip_status(current_price or 0),
            }
        
        # 添加趋势分析结果
        if trend_result:
            enhanced['trend_analysis'] = {
                'trend_status': trend_result.trend_status.value,
                'ma_alignment': trend_result.ma_alignment,
                'trend_strength': trend_result.trend_strength,
                'bias_ma5': trend_result.bias_ma5,
                'bias_ma10': trend_result.bias_ma10,
                'volume_status': trend_result.volume_status.value,
                'volume_trend': trend_result.volume_trend,
                'buy_signal': trend_result.buy_signal.value,
                'signal_score': trend_result.signal_score,
                'signal_reasons': trend_result.signal_reasons,
                'risk_factors': trend_result.risk_factors,
            }

        # Issue #234：盘中分析使用实时 OHLC 与趋势 MA 覆盖 today。
        # 防护条件：trend_result.ma5 > 0 表示 MA 计算已成功且数据量充足。
        if realtime_quote and trend_result and trend_result.ma5 > 0:
            price = getattr(realtime_quote, 'price', None)
            if price is not None and price > 0:
                yesterday_close = None
                if enhanced.get('yesterday') and isinstance(enhanced['yesterday'], dict):
                    yesterday_close = enhanced['yesterday'].get('close')
                orig_today = enhanced.get('today') or {}
                market_today = get_market_now(
                    get_market_for_stock(normalize_stock_code(enhanced.get('code', '')))
                ).date().isoformat()
                source = getattr(realtime_quote, 'source', None)
                source_name = getattr(source, 'value', source)
                source_name = str(source_name) if source_name is not None else 'unknown'
                open_p = getattr(realtime_quote, 'open_price', None) or getattr(
                    realtime_quote, 'pre_close', None
                ) or yesterday_close or orig_today.get('open') or price
                high_p = getattr(realtime_quote, 'high', None) or price
                low_p = getattr(realtime_quote, 'low', None) or price
                vol = getattr(realtime_quote, 'volume', None)
                amt = getattr(realtime_quote, 'amount', None)
                pct = getattr(realtime_quote, 'change_pct', None)
                fetched_at = getattr(realtime_quote, 'fetched_at', None)
                provider_timestamp = getattr(realtime_quote, 'provider_timestamp', None)
                fallback_from = getattr(realtime_quote, 'fallback_from', None)
                realtime_today = {
                    'close': price,
                    'open': open_p,
                    'high': high_p,
                    'low': low_p,
                    'ma5': trend_result.ma5,
                    'ma10': trend_result.ma10,
                    'ma20': trend_result.ma20,
                    'date': market_today,
                    'data_source': f"realtime:{source_name}",
                    'realtime_source': source_name,
                    'is_estimated': True,
                }
                estimated_fields = [
                    'close', 'open', 'high', 'low', 'ma5', 'ma10', 'ma20',
                ]
                if vol is not None:
                    realtime_today['volume'] = vol
                    estimated_fields.append('volume')
                if amt is not None:
                    realtime_today['amount'] = amt
                    estimated_fields.append('amount')
                if pct is not None:
                    realtime_today['pct_chg'] = pct
                    estimated_fields.append('pct_chg')
                realtime_today['estimated_fields'] = estimated_fields
                if isinstance(market_phase_context, dict) and "is_partial_bar" in market_phase_context:
                    realtime_today['is_partial_bar'] = market_phase_context.get("is_partial_bar")
                if fetched_at is not None:
                    realtime_today['fetched_at'] = fetched_at
                if provider_timestamp is not None:
                    realtime_today['provider_timestamp'] = provider_timestamp
                if fallback_from is not None:
                    realtime_today['fallback_from'] = fallback_from
                realtime_owned_fields = {
                    'open', 'high', 'low', 'close',
                    'volume', 'amount', 'pct_chg', 'pctChg',
                    'date', 'data_source', 'dataSource', 'source',
                    'realtime_source', 'realtimeSource',
                    'is_partial_bar', 'isPartialBar', 'is_estimated',
                    'isEstimated', 'estimated_fields', 'estimatedFields',
                    'fetched_at', 'fetchedAt', 'provider_timestamp',
                    'providerTimestamp', 'fallback_from', 'fallbackFrom',
                }
                for k, v in orig_today.items():
                    if k not in realtime_today and k not in realtime_owned_fields and v is not None:
                        realtime_today[k] = v
                enhanced['today'] = realtime_today
                enhanced['ma_status'] = self._compute_ma_status(
                    price, trend_result.ma5, trend_result.ma10, trend_result.ma20
                )
                enhanced['date'] = market_today
                if yesterday_close is not None:
                    try:
                        yc = float(yesterday_close)
                        if yc > 0:
                            enhanced['price_change_ratio'] = round(
                                (price - yc) / yc * 100, 2
                            )
                    except (TypeError, ValueError):
                        pass
                if vol is not None and enhanced.get('yesterday'):
                    yest_vol = enhanced['yesterday'].get('volume') if isinstance(
                        enhanced['yesterday'], dict
                    ) else None
                    if yest_vol is not None:
                        try:
                            yv = float(yest_vol)
                            if yv > 0:
                                enhanced['volume_change_ratio'] = round(
                                    float(vol) / yv, 2
                                )
                        except (TypeError, ValueError):
                            pass

        # ETF/index flag for analyzer prompt (Fixes #274)
        enhanced['is_index_etf'] = SearchService.is_index_or_etf(
            context.get('code', ''), enhanced.get('stock_name', stock_name)
        )

        # P0: append unified fundamental block; keep as additional context only
        enhanced["fundamental_context"] = (
            fundamental_context
            if isinstance(fundamental_context, dict)
            else self.fetcher_manager.build_failed_fundamental_context(
                context.get("code", ""),
                "invalid fundamental context",
            )
        )

        return enhanced

    def _attach_belong_boards_to_fundamental_context(
        self,
        code: str,
        fundamental_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Attach A-share board membership as a top-level supplemental field.

        Keep this as a shallow copy so cached fundamental contexts are not
        mutated in place after retrieval.
        """
        if isinstance(fundamental_context, dict):
            enriched_context = dict(fundamental_context)
        else:
            enriched_context = self.fetcher_manager.build_failed_fundamental_context(
                code,
                "invalid fundamental context",
            )

        market = enriched_context.get("market")
        if not isinstance(market, str) or not market.strip():
            market = get_market_for_stock(normalize_stock_code(code))

        existing_boards = enriched_context.get("belong_boards")
        existing_board_list = list(existing_boards) if isinstance(existing_boards, list) else None
        if existing_board_list:
            enriched_context["belong_boards"] = existing_board_list
            self._attach_concept_rankings_to_fundamental_context(code, enriched_context, market)
            return enriched_context

        boards_block = enriched_context.get("boards")
        boards_status = boards_block.get("status") if isinstance(boards_block, dict) else None
        coverage = enriched_context.get("coverage")
        boards_coverage = coverage.get("boards") if isinstance(coverage, dict) else None

        # For HK/US: the offshore adapter already populates belong_boards from
        # yfinance sector/industry. Don't overwrite it (and we have no AkShare
        # 板块 endpoint for those markets anyway). Default to [] when callers
        # pass a minimal context without the key.
        if market != "cn":
            enriched_context["belong_boards"] = existing_board_list or []
            return enriched_context

        if boards_status == "not_supported" or boards_coverage == "not_supported":
            enriched_context["belong_boards"] = existing_board_list or []
            return enriched_context

        boards: List[Dict[str, Any]] = []
        try:
            raw_boards = self.fetcher_manager.get_belong_boards(code)
            if isinstance(raw_boards, list):
                boards = raw_boards
        except Exception as e:
            log_safe_exception(
                logger,
                "Related board attachment failed; continuing without board data",
                e,
                error_code="pipeline_related_boards_attach_failed",
                level=logging.DEBUG,
                context={"stock_code": code},
            )

        enriched_context["belong_boards"] = boards or existing_board_list or []
        self._attach_concept_rankings_to_fundamental_context(code, enriched_context, market)
        return enriched_context

    def _attach_concept_rankings_to_fundamental_context(
        self,
        code: str,
        enriched_context: Dict[str, Any],
        market: str,
    ) -> None:
        """Attach concept/theme rankings for A-share related-board signals."""
        if market != "cn" or isinstance(enriched_context.get("concept_boards"), dict):
            return

        top_concepts, bottom_concepts = self._get_concept_rankings_for_market(market)

        concept_data: Dict[str, Any] = {
            "top": top_concepts,
            "bottom": bottom_concepts,
        }
        if not top_concepts and not bottom_concepts:
            # Empty lists are removed while fundamental contexts are merged.
            # Keep a non-empty internal marker so downstream consumers can
            # distinguish an attempted empty result from a missing preload.
            concept_data["fetch_attempted"] = True
        enriched_context["concept_boards"] = {
            "status": "ok" if top_concepts and bottom_concepts else "partial",
            "data": concept_data,
        }

    def _get_concept_rankings_for_market(
        self,
        market: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fetch market-wide concept rankings once per pipeline run."""
        if market != "cn":
            return [], []

        service = getattr(self, "market_hotspot_service", None)
        if service is None:
            try:
                service = MarketHotspotService(fetcher_manager=self.fetcher_manager)
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "Concept ranking service initialization failed; continuing without rankings",
                    exc,
                    error_code="pipeline_concept_ranking_service_init_failed",
                    level=logging.DEBUG,
                    context={"market": market},
                )
                service = None
            else:
                self.market_hotspot_service = service

        cache = getattr(self, "_concept_rankings_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._concept_rankings_cache = cache

        lock = getattr(self, "_concept_rankings_cache_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._concept_rankings_cache_lock = lock

        with lock:
            if market in cache:
                top_concepts, bottom_concepts = cache[market]
                return list(top_concepts), list(bottom_concepts)

            top_concepts: List[Dict[str, Any]] = []
            bottom_concepts: List[Dict[str, Any]] = []
            try:
                if service is None:
                    fetch_rankings = getattr(self.fetcher_manager, "get_concept_rankings", None)
                    if callable(fetch_rankings):
                        rankings = fetch_rankings(5)
                        if isinstance(rankings, tuple) and len(rankings) == 2:
                            raw_top, raw_bottom = rankings
                            if isinstance(raw_top, list):
                                top_concepts = list(raw_top)
                            if isinstance(raw_bottom, list):
                                bottom_concepts = list(raw_bottom)
                else:
                    top_concepts, bottom_concepts = service.get_concept_rankings(5)
            except Exception as e:
                log_safe_exception(
                    logger,
                    "Concept ranking attachment failed; continuing without rankings",
                    e,
                    error_code="pipeline_concept_rankings_attach_failed",
                    level=logging.DEBUG,
                    context={"market": market},
                )

            cache[market] = (top_concepts, bottom_concepts)
            return list(top_concepts), list(bottom_concepts)

    def _build_market_structure_context(
        self,
        *,
        code: str,
        stock_name: str,
        market: str,
        fundamental_context: Optional[Dict[str, Any]],
        trade_date: Any = None,
        market_phase_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build market structure context without blocking the main analysis."""
        service = getattr(self, "market_structure_service", None)
        if service is None:
            try:
                service = MarketStructureService(fetcher_manager=self.fetcher_manager)
                self.market_structure_service = service
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "Market structure service initialization failed; continuing without structure data",
                    exc,
                    error_code="pipeline_market_structure_service_init_failed",
                    level=logging.DEBUG,
                    context={"stock_code": code},
                )
                return None
        try:
            return service.build_context(
                code=code,
                stock_name=stock_name,
                market=market,
                fundamental_context=fundamental_context,
                trade_date=trade_date,
                market_phase_summary=market_phase_summary,
            )
        except Exception as exc:
            log_safe_exception(
                logger,
                "Market structure context generation failed; continuing without structure data",
                exc,
                error_code="pipeline_market_structure_context_failed",
                level=logging.DEBUG,
                context={"stock_code": code},
            )
            return None

    def _ensure_agent_history(self, code: str, min_days: int = 240) -> None:
        """Ensure at least *min_days* of K-line history is in DB for agent tools."""
        from src.services.history_loader import get_frozen_target_date

        target = get_frozen_target_date()
        if target is None:
            target = self._resolve_resume_target_date(code)
        start = target - timedelta(days=int(min_days * 1.8))
        bars = self.db.get_data_range(code, start, target)
        if bars and len(bars) >= min(min_days, 200):
            logger.debug("[%s] Agent history: %d bars in DB, sufficient", code, len(bars))
            return
        try:
            df, source = self.fetcher_manager.get_daily_data(code, days=min_days)
            if df is not None and not df.empty:
                self.db.save_daily_data(df, code, source)
                logger.info("[%s] Prefetched %d rows of history for agent (source: %s)", code, len(df), source)
        except Exception as e:
            log_safe_exception(
                logger,
                "Agent history prefetch failed",
                e,
                error_code="pipeline_agent_history_prefetch_failed",
                level=logging.WARNING,
                context={"stock_code": code},
            )

    def _analyze_with_agent(
        self, 
        code: str, 
        report_type: ReportType, 
        query_id: str,
        stock_name: str,
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution],
        fundamental_context: Optional[Dict[str, Any]] = None,
        trend_result: Optional[TrendAnalysisResult] = None,
        *,
        market_phase_context: Optional[Dict[str, Any]] = None,
        market_phase_summary: Optional[Dict[str, Any]] = None,
        daily_market_context: Optional[DailyMarketContext] = None,
        portfolio_context: Optional[Dict[str, Any]] = None,
        market_structure_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[AnalysisResult]:
        """
        使用 Agent 模式分析单只股票。
        """
        active_stage: Optional[PipelineStageObservation] = None
        try:
            from src.agent.factory import build_agent_executor
            report_language = normalize_report_language(getattr(self.config, "report_language", "zh"))

            requested_skills = (
                self.analysis_skills
                if self.analysis_skills is not None
                else (getattr(self.config, 'agent_skills', None) or None)
            )
            # Build executor from shared factory (ToolRegistry and SkillManager prototype are cached)
            executor = build_agent_executor(self.config, requested_skills)

            # Build initial context to avoid redundant tool calls
            initial_context = {
                "stock_code": code,
                "stock_name": stock_name,
                "report_type": report_type.value,
                "report_language": report_language,
                "fundamental_context": fundamental_context,
            }
            if isinstance(portfolio_context, dict):
                initial_context["portfolio_context"] = dict(portfolio_context)
            if self.analysis_skills is not None:
                initial_context["skills"] = self.analysis_skills
            if market_phase_context is not None:
                initial_context["market_phase_context"] = market_phase_context
            if isinstance(market_structure_context, dict):
                initial_context["market_structure_context"] = market_structure_context
            self._attach_daily_market_context(
                initial_context,
                daily_market_context,
                report_language=report_language,
            )
            
            if realtime_quote:
                initial_context["realtime_quote"] = self._safe_to_dict(realtime_quote)
            if chip_data:
                initial_context["chip_distribution"] = self._safe_to_dict(chip_data)
            if trend_result:
                initial_context["trend_result"] = self._safe_to_dict(trend_result)

            active_stage = observe_pipeline_stage(
                "intelligence",
                input_summary={
                    "stock_code": code,
                    "mode": "agent",
                    "social_sentiment_available": bool(
                        self.social_sentiment_service is not None
                        and self.social_sentiment_service.is_available
                        and is_us_stock_code(code)
                    ),
                },
                retryable=True,
            )
            fresh_intelligence_available = False

            # Agent path: inject social sentiment as news_context so both
            # executor (_build_user_message) and orchestrator (ctx.set_data)
            # can consume it through the existing news_context channel
            if self.social_sentiment_service is not None and self.social_sentiment_service.is_available and is_us_stock_code(code):
                try:
                    social_context = self.social_sentiment_service.get_social_context(code)
                    if social_context:
                        fresh_intelligence_available = True
                        existing = initial_context.get("news_context")
                        if existing:
                            initial_context["news_context"] = existing + "\n\n" + social_context
                        else:
                            initial_context["news_context"] = social_context
                        logger.info(f"[{code}] Agent mode: social sentiment data injected into news_context")
                except Exception as e:  # broad-exception: fallback_recorded - Social-intelligence failure is safely logged before optional-input degradation.
                    log_safe_exception(
                        logger,
                        "Agent social sentiment retrieval failed",
                        e,
                        error_code="pipeline_agent_social_sentiment_fetch_failed",
                        level=logging.WARNING,
                        context={"stock_code": code},
                    )

            persisted_intelligence_context = self._load_persisted_intelligence_context(
                code=code,
                stock_name=stock_name,
                market=get_market_for_stock(normalize_stock_code(code)) or "cn",
            )
            if persisted_intelligence_context:
                existing = initial_context.get("news_context")
                initial_context["news_context"] = (
                    f"{existing}\n\n{persisted_intelligence_context}"
                    if existing
                    else persisted_intelligence_context
                )
                logger.info(f"[{code}] Agent mode: local intelligence evidence injected into news_context")

            agent_intelligence_available = bool(initial_context.get("news_context"))
            using_persisted_fallback = bool(
                persisted_intelligence_context
                and not fresh_intelligence_available
            )
            agent_intelligence_degraded = bool(
                not agent_intelligence_available or using_persisted_fallback
            )
            agent_intelligence_reason = (
                "No intelligence evidence was available to the Agent context."
                if not agent_intelligence_available
                else (
                    "Fresh intelligence was unavailable; persisted evidence was used."
                    if using_persisted_fallback
                    else None
                )
            )
            intelligence_result = (
                PipelineStageResult.degraded(
                    PipelineStageName.INTELLIGENCE,
                    initial_context.get("news_context"),
                    reason=agent_intelligence_reason,
                    retryable=True,
                )
                if agent_intelligence_degraded
                else PipelineStageResult.success(
                    PipelineStageName.INTELLIGENCE,
                    initial_context.get("news_context"),
                )
            )
            self._finish_pipeline_stage(
                active_stage,
                intelligence_result,
                output_summary={
                    "intelligence_available": agent_intelligence_available,
                    "fresh_intelligence_available": fresh_intelligence_available,
                    "persisted_evidence_available": bool(
                        persisted_intelligence_context
                    ),
                    "using_persisted_fallback": using_persisted_fallback,
                },
            )
            active_stage = None

            # Issue #1066: ensure deep history is in DB before agent tools run
            active_stage = observe_pipeline_stage(
                "context",
                input_summary={
                    "stock_code": code,
                    "mode": "agent",
                    "has_realtime": realtime_quote is not None,
                    "has_chip": chip_data is not None,
                    "has_fundamentals": isinstance(fundamental_context, dict),
                    "has_intelligence": agent_intelligence_available,
                },
                retryable=True,
            )
            self._ensure_agent_history(code)

            analysis_context = self._load_agent_analysis_context(code, stock_name)
            market = get_market_for_stock(normalize_stock_code(code))
            (
                analysis_context_pack_summary,
                analysis_context_pack_overview,
            ) = self._build_analysis_context_pack_outputs(
                self._build_agent_analysis_artifacts(
                    code=code,
                    stock_name=stock_name,
                    market=market,
                    phase=market_phase_context,
                    initial_context=initial_context,
                    fundamental_context=fundamental_context,
                    query_id=query_id,
                    base_context=analysis_context,
                    portfolio_context=portfolio_context,
                ),
                report_language=report_language,
                code=code,
                query_id=query_id,
            )
            if analysis_context_pack_summary:
                initial_context["analysis_context_pack_summary"] = analysis_context_pack_summary

            agent_pack_counts = (
                analysis_context_pack_overview.get("counts", {})
                if isinstance(analysis_context_pack_overview, dict)
                else {}
            )
            agent_degraded_block_count = sum(
                max(0, count)
                for status in (
                    "missing",
                    "fallback",
                    "stale",
                    "estimated",
                    "partial",
                    "fetch_failed",
                )
                for count in (agent_pack_counts.get(status),)
                if isinstance(count, int) and not isinstance(count, bool)
            )
            agent_context_pack_available = bool(analysis_context_pack_summary)
            agent_context_degraded = bool(
                not agent_context_pack_available or agent_degraded_block_count
            )
            agent_context_reason = (
                "Agent ContextPack output generation was unavailable."
                if not agent_context_pack_available
                else (
                    "Agent ContextPack contains missing or fallback inputs."
                    if agent_context_degraded
                    else None
                )
            )
            context_result = (
                PipelineStageResult.degraded(
                    PipelineStageName.CONTEXT,
                    initial_context,
                    reason=agent_context_reason,
                    retryable=True,
                )
                if agent_context_degraded
                else PipelineStageResult.success(
                    PipelineStageName.CONTEXT,
                    initial_context,
                )
            )
            self._finish_pipeline_stage(
                active_stage,
                context_result,
                output_summary={
                    "context_pack_available": agent_context_pack_available,
                    "degraded_block_count": agent_degraded_block_count,
                },
            )
            active_stage = None

            # 运行 Agent
            if report_language in ("en", "ko"):
                message = f"Analyze stock {code} ({stock_name}) and return the full decision dashboard JSON."
            else:
                message = f"请分析股票 {code} ({stock_name})，并生成决策仪表盘报告。"
            active_stage = observe_pipeline_stage(
                "analyze",
                input_summary={
                    "stock_code": code,
                    "mode": "agent",
                    "report_type": report_type.value,
                    "context_pack_available": bool(analysis_context_pack_summary),
                },
                retryable=True,
            )
            llm_started_at = time.monotonic()
            try:
                record_llm_run_started(
                    model=getattr(self.config, "agent_litellm_model", None),
                    call_type="agent_analysis",
                )
                agent_result = executor.run(message, context=initial_context)
            except Exception as exc:
                record_llm_run(
                    success=False,
                    model=getattr(self.config, "agent_litellm_model", None),
                    call_type="agent_analysis",
                    duration_ms=int((time.monotonic() - llm_started_at) * 1000),
                    error_type=type(exc).__name__,
                    error_message=exc,
                )
                raise

            # 转换为 AnalysisResult
            result = self._agent_result_to_analysis_result(
                agent_result,
                code,
                stock_name,
                report_type,
                query_id,
                trend_result=trend_result,
            )
            record_llm_run(
                success=bool(result and getattr(result, "success", True)),
                model=getattr(result, "model_used", None) if result else getattr(agent_result, "model", None),
                call_type="agent_analysis",
                duration_ms=int((time.monotonic() - llm_started_at) * 1000),
                error_type=(
                    None
                    if result and getattr(result, "success", True)
                    else "AgentResultError"
                ),
                error_message=(
                    getattr(result, "error_message", None)
                    if result and not getattr(result, "success", True)
                    else ("Agent returned empty result" if result is None else None)
                ),
            )
            if result:
                result.query_id = query_id
            # Agent weak integrity: placeholder fill only, no LLM retry
            if result and getattr(self.config, "report_integrity_enabled", False):
                from src.analyzer import check_content_integrity, apply_placeholder_fill

                pass_integrity, missing = check_content_integrity(
                    result,
                    require_phase_decision=isinstance(market_phase_summary, dict),
                )
                if not pass_integrity:
                    apply_placeholder_fill(result, missing)
                    logger.info(
                        "[LLM integrity] integrity_mode=agent_weak missing required fields; "
                        "placeholders applied: %s",
                        missing,
                    )
            # chip_structure fallback (Issue #589), before save_analysis_history
            if result and chip_data is not None:
                normalize_chip_structure_availability(result, chip_data)

            # price_position fallback (same as non-agent path Step 7.7)
            if result:
                fill_price_position_if_needed(result, trend_result, realtime_quote)
                realtime_data = initial_context.get("realtime_quote", {})
                if isinstance(realtime_data, dict):
                    result.current_price = realtime_data.get("price")
                    result.change_pct = realtime_data.get("change_pct")
                action_source_advice = getattr(result, "operation_advice", None)
                stabilize_decision_with_structure(result, trend_result, fundamental_context)
                adjustments = apply_phase_decision_guardrails(
                    result,
                    market_phase_summary=market_phase_summary,
                    analysis_context_pack_overview=analysis_context_pack_overview,
                    report_language=getattr(result, "report_language", None)
                    or getattr(self.config, "report_language", "zh"),
                )
                if adjustments:
                    logger.info("[phase_decision_guardrail] Applied agent adjustments for %s: %s", code, adjustments)
                market_context_adjustments = apply_daily_market_context_guardrail(
                    result,
                    daily_market_context=initial_context.get("daily_market_context"),
                    report_language=getattr(result, "report_language", None)
                    or getattr(self.config, "report_language", "zh"),
                )
                if market_context_adjustments:
                    logger.info(
                        "[daily_market_context_guardrail] Applied agent adjustments for %s: %s",
                        code,
                        market_context_adjustments,
                    )
                if isinstance(fundamental_context, dict):
                    result.fundamental_context = fundamental_context
                if isinstance(market_structure_context, dict):
                    result.market_structure_context = market_structure_context
                result.market_phase_summary = market_phase_summary
                result.analysis_context_pack_overview = analysis_context_pack_overview
                self._refresh_decision_action_for_final_result(
                    result,
                    report_type=report_type.value,
                    previous_operation_advice=action_source_advice,
                )

            agent_analysis_succeeded = bool(
                result and getattr(result, "success", True)
            )
            agent_analysis_reason = (
                getattr(result, "error_message", None)
                if result is not None and not agent_analysis_succeeded
                else (
                    "Agent analysis returned no result."
                    if result is None
                    else None
                )
            )
            analysis_stage_result = (
                PipelineStageResult.success(PipelineStageName.ANALYZE, result)
                if agent_analysis_succeeded
                else PipelineStageResult.failed(
                    PipelineStageName.ANALYZE,
                    value=result,
                    retryable=True,
                    reason=agent_analysis_reason,
                )
            )
            self._finish_pipeline_stage(
                active_stage,
                analysis_stage_result,
                output_summary={
                    "analysis_result_available": result is not None,
                    "analysis_success": agent_analysis_succeeded,
                    "model": getattr(result, "model_used", None) if result else None,
                },
            )
            active_stage = None

            resolved_stock_name = result.name if result and result.name else stock_name

            # 保存新闻情报到数据库（Agent 工具结果仅用于 LLM 上下文，未持久化，Fixes #396）
            # 使用 search_stock_news（与 Agent 工具调用逻辑一致），仅 1 次 API 调用，无额外延迟
            if self.search_service is not None and self.search_service.is_available:
                try:
                    news_response = self.search_service.search_stock_news(
                        stock_code=code,
                        stock_name=resolved_stock_name,
                        max_results=5
                    )
                    if news_response.success and news_response.results:
                        query_context = self._build_query_context(query_id=query_id)
                        self.db.save_news_intel(
                            code=code,
                            name=resolved_stock_name,
                            dimension="latest_news",
                            query=news_response.query,
                            response=news_response,
                            query_context=query_context
                        )
                        logger.info(
                            "[%s] Agent mode persisted news intelligence: result_count=%s",
                            code,
                            len(news_response.results),
                        )
                except Exception as e:  # broad-exception: optional_metadata - Agent intelligence remains usable when its optional cache write fails.
                    log_safe_exception(
                        logger,
                        "Agent news intelligence persistence failed",
                        e,
                        error_code="pipeline_agent_news_intelligence_save_failed",
                        level=logging.WARNING,
                        context={"stock_code": code},
                    )

            # 保存分析历史记录
            if result and result.success:
                active_stage = observe_pipeline_stage(
                    "persist",
                    input_summary={
                        "stock_code": code,
                        "query_id": query_id,
                        "report_type": report_type.value,
                        "mode": "agent",
                        "save_context_snapshot": bool(self.save_context_snapshot),
                    },
                    retryable=True,
                )

                def _agent_context_snapshot() -> Dict[str, Any]:
                    context_snapshot = self._build_context_snapshot(
                        enhanced_context={
                            **self._without_runtime_prompt_context(initial_context),
                            "stock_name": resolved_stock_name,
                        },
                        news_content=initial_context.get("news_context"),
                        realtime_quote=realtime_quote,
                        chip_data=chip_data,
                        analysis_context_pack_overview=analysis_context_pack_overview,
                        market_phase_summary=market_phase_summary,
                    )
                    context_snapshot["stock_name"] = resolved_stock_name
                    return context_snapshot

                persistence_result = self._persist_analysis_history_stage(
                    result=result,
                    query_id=query_id,
                    report_type=report_type.value,
                    news_content=None,
                    context_snapshot_factory=_agent_context_snapshot,
                    portfolio_context=portfolio_context,
                    failure_reason="Agent analysis history was not saved.",
                    failure_message="Agent analysis history persistence failed",
                    failure_error_code="pipeline_agent_analysis_history_save_failed",
                )
                persistence_value = persistence_result.value
                self._finish_pipeline_stage(
                    active_stage,
                    persistence_result,
                    output_summary={
                        "history_saved": bool(
                            persistence_value and persistence_value.saved
                        ),
                        "analysis_history_id": (
                            persistence_value.history_id
                            if persistence_value is not None
                            else None
                        ),
                        "reused": persistence_result.reused,
                    },
                )
                active_stage = None
                agent_context_snapshot = (
                    persistence_value.context_snapshot
                    if persistence_value is not None
                    else {}
                )
                latest_diagnostic_snapshot = current_diagnostic_snapshot()
                if latest_diagnostic_snapshot is not None:
                    agent_context_snapshot["diagnostics"] = latest_diagnostic_snapshot
                    result.diagnostic_context_snapshot = agent_context_snapshot
                if persistence_value is not None and persistence_value.history_id:
                    self._refresh_saved_diagnostic_snapshot(result=result)
            else:
                self._record_pipeline_stage_result(
                    PipelineStageResult.skipped(
                        PipelineStageName.PERSIST,
                        reason="analysis_unsuccessful",
                    ),
                    input_summary={
                        "stock_code": code,
                        "query_id": query_id,
                        "mode": "agent",
                    },
                    output_summary={"reason": "analysis_unsuccessful"},
                )

            return result

        except Exception as e:  # broad-exception: fallback_recorded - Agent failures are safely logged and isolated to the current stock.
            if active_stage is not None and not active_stage.finished:
                self._finish_pipeline_stage(
                    active_stage,
                    PipelineStageResult.failed(
                        active_stage.stage,
                        error=e,
                        retryable=active_stage.retryable,
                    ),
                )
            log_safe_exception(
                logger,
                "Agent stock analysis failed",
                e,
                error_code="pipeline_agent_analysis_failed",
                context={"stock_code": code},
            )
            return None

    def _load_agent_analysis_context(self, code: str, stock_name: str) -> Dict[str, Any]:
        """Load daily-bar context for Agent pack summaries without blocking analysis."""
        try:
            context = self._get_analysis_context_with_market_fallback(code)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Agent analysis context load failed; marking daily bars as missing",
                exc,
                error_code="pipeline_agent_analysis_context_load_failed",
                level=logging.WARNING,
                context={"stock_code": code},
            )
            context = None

        if isinstance(context, dict) and context:
            enriched = dict(context)
            enriched.setdefault("code", code)
            if stock_name:
                enriched.setdefault("stock_name", stock_name)
            return enriched

        return {
            "code": code,
            "stock_name": stock_name,
            "data_missing": True,
            "today": {},
            "yesterday": {},
        }

    def _get_analysis_context_with_market_fallback(self, code: str) -> Optional[Dict[str, Any]]:
        """Load analysis context, fetching JP/KR/TW daily bars when DB has no context."""
        context = self.db.get_analysis_context(code)
        if isinstance(context, dict) and context:
            return context

        market = get_market_for_stock(normalize_stock_code(code))
        if market not in {"jp", "kr", "tw"}:
            return context

        try:
            df, source_name = self.fetcher_manager.get_daily_data(code, days=60)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Regional daily data fallback fetch failed",
                exc,
                error_code="pipeline_regional_daily_fallback_fetch_failed",
                level=logging.WARNING,
                context={"stock_code": code, "market": market},
            )
            return context

        if df is None or df.empty:
            logger.warning("[%s] JP/KR daily fallback returned empty data", code)
            return context

        try:
            self.db.save_daily_data(df, code, source_name)
            refreshed = self.db.get_analysis_context(code)
            if isinstance(refreshed, dict) and refreshed:
                return refreshed
        except Exception as exc:
            log_safe_exception(
                logger,
                "Regional daily data fallback persistence failed",
                exc,
                error_code="pipeline_regional_daily_fallback_persistence_failed",
                level=logging.WARNING,
                context={"stock_code": code, "market": market},
            )

        return self._build_analysis_context_from_daily_df(code, df)

    def _build_analysis_context_from_daily_df(self, code: str, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if df is None or df.empty:
            return None

        frame = df.copy()
        frame.columns = [str(column).lower() for column in frame.columns]
        if "date" in frame.columns:
            frame = frame.sort_values("date")
        frame = frame.tail(2)
        rows = frame.to_dict(orient="records")
        if not rows:
            return None

        def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
            normalized: Dict[str, Any] = {"code": row.get("code") or code}
            for key in ("open", "high", "low", "close", "volume", "amount", "pct_chg", "ma5", "ma10", "ma20", "volume_ratio"):
                value = row.get(key)
                if pd.notna(value):
                    normalized[key] = float(value)
            row_date = row.get("date")
            if hasattr(row_date, "date"):
                row_date = row_date.date()
            normalized["date"] = row_date.isoformat() if hasattr(row_date, "isoformat") else str(row_date)
            return normalized

        today = normalize_row(rows[-1])
        context: Dict[str, Any] = {
            "code": code,
            "date": today.get("date"),
            "today": today,
        }
        if len(rows) > 1:
            yesterday = normalize_row(rows[-2])
            context["yesterday"] = yesterday
            yesterday_volume = yesterday.get("volume")
            if yesterday_volume:
                context["volume_change_ratio"] = round(float(today.get("volume", 0)) / float(yesterday_volume), 2)
            yesterday_close = yesterday.get("close")
            if yesterday_close:
                context["price_change_ratio"] = round(
                    (float(today.get("close", 0)) - float(yesterday_close)) / float(yesterday_close) * 100,
                    2,
                )
            context["ma_status"] = self.db._analyze_ma_status(SimpleNamespace(**today))

        return context

    def _is_daily_market_context_enabled(self) -> bool:
        """Return whether stock analysis expects daily market context."""
        return bool(
            getattr(self, "daily_market_context_enabled", True) is True
            and getattr(self.config, "daily_market_context_enabled", True) is True
            and getattr(self.config, "market_review_enabled", None) is True
        )

    def _load_daily_market_context(
        self,
        market: str,
        *,
        force_refresh: bool = False,
        target_date: Optional[date] = None,
    ) -> Optional[DailyMarketContext]:
        """Load/generate today's market context when market review is explicitly enabled."""
        if not self._is_daily_market_context_enabled():
            return None

        try:
            service = getattr(self, "_daily_market_context_service", None)
            if service is None:
                service_lock = self._get_daily_market_context_service_lock()
                with service_lock:
                    service = getattr(self, "_daily_market_context_service", None)
                    if service is None:
                        service = DailyMarketContextService(db_manager=self.db)
                        self._daily_market_context_service = service
            get_context_kwargs = {
                "region": market,
                "config": self.config,
                "notifier": self.notifier,
                "analyzer": self.analyzer,
                "search_service": self.search_service,
                "force_refresh": force_refresh,
                "allow_generate": getattr(self, "daily_market_context_allow_generate", True),
                "target_date": target_date,
            }
            current_query_id = getattr(self, "query_id", None)
            if isinstance(current_query_id, str) and current_query_id.strip():
                get_context_kwargs["current_query_id"] = current_query_id
            return service.get_context(**get_context_kwargs)
        except Exception as exc:  # broad-exception: fallback_recorded - Daily context failure is safely logged before stock analysis continues without it.
            log_safe_exception(
                logger,
                "Daily market context load failed; continuing stock analysis",
                exc,
                error_code="pipeline_daily_market_context_load_failed",
                level=logging.WARNING,
                context={"market": market},
            )
            return None

    def _get_daily_market_context_service_lock(self) -> threading.Lock:
        service_lock = getattr(self, "_daily_market_context_service_lock", None)
        if service_lock is not None:
            return service_lock
        with _DAILY_MARKET_CONTEXT_SERVICE_LOCK_INIT_GUARD:
            service_lock = getattr(self, "_daily_market_context_service_lock", None)
            if service_lock is None:
                service_lock = threading.Lock()
                self._daily_market_context_service_lock = service_lock
            return service_lock

    @staticmethod
    def _coerce_daily_market_context_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

    @staticmethod
    def _attach_daily_market_context(
        target_context: Dict[str, Any],
        daily_market_context: Optional[DailyMarketContext],
        *,
        report_language: str,
    ) -> None:
        """Attach only the safe daily market summary to runtime analysis context."""
        if daily_market_context is None:
            return
        safe_context = daily_market_context.to_safe_dict()
        prompt_section = format_daily_market_context_prompt_section(
            safe_context,
            report_language=report_language,
        )
        if not prompt_section:
            return
        target_context["daily_market_context"] = safe_context
        target_context["daily_market_context_summary"] = prompt_section

    def _agent_result_to_analysis_result(
        self,
        agent_result,
        code: str,
        stock_name: str,
        report_type: ReportType,
        query_id: str,
        trend_result: Optional[TrendAnalysisResult] = None,
    ) -> AnalysisResult:
        """
        将 AgentResult 转换为 AnalysisResult。
        """
        report_language = normalize_report_language(getattr(self.config, "report_language", "zh"))
        dash = None
        result = AnalysisResult(
            code=code,
            name=stock_name,
            sentiment_score=50,
            trend_prediction=get_unknown_text(report_language),
            operation_advice=localize_operation_advice("观望", report_language),
            confidence_level=localize_confidence_level("medium", report_language),
            report_language=report_language,
            success=agent_result.success,
            error_message=agent_result.error or None,
            data_sources=f"agent:{agent_result.provider}",
            model_used=agent_result.model or None,
        )

        if agent_result.success and agent_result.dashboard:
            dash = agent_result.dashboard
            ai_stock_name = str(dash.get("stock_name", "")).strip()
            if ai_stock_name and self._is_placeholder_stock_name(stock_name, code):
                result.name = ai_stock_name

            nested_dashboard = dash.get("dashboard") if isinstance(dash, dict) else None

            raw_score = self._agent_dashboard_value(
                dash,
                nested_dashboard,
                "sentiment_score",
                scalar=True,
            )
            if self._is_agent_field_missing(raw_score, scalar=True):
                fallback_score = self._trend_score_fallback(trend_result)
                if fallback_score is not None:
                    result.sentiment_score = fallback_score
                    self._mark_trend_fallback_source(result)
            else:
                result.sentiment_score = self._safe_int(raw_score, 50)

            raw_trend = self._agent_dashboard_value(
                dash,
                nested_dashboard,
                "trend_prediction",
                scalar=True,
                expect_text=True,
            )
            if self._is_agent_field_missing(raw_trend, scalar=True, expect_text=True):
                trend_label = self._trend_label_fallback(
                    trend_result,
                    report_language,
                )
                if trend_label:
                    result.trend_prediction = trend_label
                    self._mark_trend_fallback_source(result)
            else:
                result.trend_prediction = str(raw_trend)

            raw_advice = self._agent_dashboard_value(
                dash,
                nested_dashboard,
                "operation_advice",
                scalar=True,
                allow_dict=True,
                expect_text=True,
            )
            extracted_advice = ""
            if isinstance(raw_advice, dict):
                # LLM may return {"no_position": "...", "has_position": "..."}
                extracted_advice = self._extract_advice_text_from_dict(raw_advice)
                if extracted_advice:
                    result.operation_advice = localize_operation_advice(
                        extracted_advice,
                        report_language,
                    )
                else:
                    signal_label = self._trend_signal_fallback(
                        trend_result,
                        report_language,
                    )
                    if signal_label:
                        result.operation_advice = signal_label
                        self._mark_trend_fallback_source(result)
            elif not self._is_agent_field_missing(
                raw_advice,
                scalar=True,
                allow_dict=True,
                expect_text=True,
            ):
                result.operation_advice = str(raw_advice) if raw_advice else (localize_operation_advice("观望", report_language))
            else:
                signal_label = self._trend_signal_fallback(trend_result, report_language)
                if signal_label:
                    result.operation_advice = signal_label
                    self._mark_trend_fallback_source(result)
            from src.agent.protocols import normalize_decision_signal

            raw_decision = self._agent_dashboard_value(
                dash,
                nested_dashboard,
                "decision_type",
                scalar=True,
                expect_text=True,
            )
            if self._is_agent_field_missing(raw_decision, scalar=True, expect_text=True):
                trend_decision = self._trend_decision_fallback(trend_result)
                decision_from_advice = infer_decision_type_from_advice(
                    result.operation_advice,
                    default="",
                )
                if decision_from_advice:
                    result.decision_type = decision_from_advice
                    if (
                        self._is_agent_field_missing(
                            raw_advice,
                            scalar=True,
                            allow_dict=True,
                            expect_text=True,
                        )
                        and not extracted_advice
                        and trend_decision
                    ):
                        self._mark_trend_fallback_source(result)
                else:
                    result.decision_type = trend_decision or "hold"
                    if trend_decision:
                        self._mark_trend_fallback_source(result)
            else:
                result.decision_type = normalize_decision_signal(raw_decision)
            result.confidence_level = localize_confidence_level(
                self._agent_dashboard_value(dash, nested_dashboard, "confidence_level")
                or result.confidence_level,
                report_language,
            )
            raw_summary = self._agent_dashboard_value(
                dash,
                nested_dashboard,
                "analysis_summary",
                scalar=True,
                expect_text=True,
            )
            if not self._is_agent_field_missing(raw_summary, scalar=True, expect_text=True):
                result.analysis_summary = str(raw_summary)
            else:
                result.analysis_summary = self._summary_fallback_from_result(result, report_language)
            top_level_phase_decision = dash.get("phase_decision") if isinstance(dash, dict) else None
            if isinstance(nested_dashboard, dict) and isinstance(top_level_phase_decision, dict):
                nested_dashboard = dict(nested_dashboard)
                nested_dashboard.setdefault("phase_decision", top_level_phase_decision)

            # The AI returns a top-level dict that contains a nested 'dashboard' sub-key
            # with core_conclusion / battle_plan / intelligence.  AnalysisResult's helper
            # methods (get_sniper_points, get_core_conclusion, etc.) expect that inner
            # structure, so we unwrap it here.
            result.dashboard = nested_dashboard or dash
            self._backfill_agent_dashboard_fields(result, trend_result, report_language)
        else:
            self._apply_trend_fallback(result, trend_result, report_language)
            if trend_result is not None:
                result.analysis_summary = (
                    result.analysis_summary
                    or self._summary_fallback_from_result(result, report_language)
                )
                self._backfill_agent_dashboard_fields(result, trend_result, report_language)
            if not result.error_message:
                result.error_message = (
                    "Agent failed to generate a valid decision dashboard" if report_language == "en"
                    else "에이전트가 유효한 결정 대시보드를 생성하지 못했습니다" if report_language == "ko"
                    else "Agent 未能生成有效的决策仪表盘"
                )

        explicit_action = dash.get("action") if isinstance(dash, dict) else None
        if explicit_action is None and isinstance(getattr(result, "dashboard", None), dict):
            explicit_action = result.dashboard.get("action")
        return populate_decision_action_fields(result, explicit_action=explicit_action)

    @staticmethod
    def _refresh_decision_action_for_final_result(
        result: AnalysisResult,
        *,
        report_type: Any,
        previous_operation_advice: Any,
    ) -> AnalysisResult:
        previous_advice = str(previous_operation_advice or "").strip()
        current_advice = str(getattr(result, "operation_advice", None) or "").strip()
        explicit_action = current_advice if previous_advice != current_advice else None
        return populate_decision_action_fields(
            result,
            explicit_action=explicit_action,
            report_type=report_type,
            use_existing_action=(previous_advice == current_advice),
            align_with_score=(previous_advice == current_advice),
        )

    @staticmethod
    def _agent_dashboard_value(
        dash: Dict[str, Any],
        nested_dashboard: Any,
        key: str,
        *,
        scalar: bool = False,
        allow_dict: bool = False,
        expect_text: bool = False,
    ) -> Any:
        """Read a scalar from top-level agent payload, then nested dashboard fallback."""
        value = dash.get(key) if isinstance(dash, dict) else None
        if isinstance(nested_dashboard, dict) and StockAnalysisPipeline._is_agent_field_missing(
            value,
            scalar=scalar,
            allow_dict=allow_dict,
            expect_text=expect_text,
        ):
            nested_value = nested_dashboard.get(key)
            if not StockAnalysisPipeline._is_agent_field_missing(
                nested_value,
                scalar=scalar,
                allow_dict=allow_dict,
                expect_text=expect_text,
            ):
                value = nested_value
        return value

    @staticmethod
    def _extract_advice_text_from_dict(raw_advice: dict) -> str:
        for field in ("has_position", "no_position"):
            if isinstance(raw_advice.get(field), str):
                text = raw_advice[field].strip()
                if not StockAnalysisPipeline._is_agent_placeholder_text(text):
                    return text

        for value in raw_advice.values():
            if isinstance(value, str):
                text = value.strip()
                if not StockAnalysisPipeline._is_agent_placeholder_text(text):
                    return text

        return ""

    @staticmethod
    def _is_agent_placeholder_text(text: str) -> bool:
        if not text:
            return True
        return text.lower() in {"n/a", "na", "none", "null", "unknown", "tbd"} or text in {
            "未知",
            "待补充",
            "数据缺失",
            "无",
        }

    @staticmethod
    def _is_agent_field_missing(
        value: Any,
        *,
        scalar: bool = False,
        allow_dict: bool = False,
        expect_text: bool = False,
    ) -> bool:
        if scalar and isinstance(value, dict):
            if not allow_dict or not value:
                return True
            return not StockAnalysisPipeline._extract_advice_text_from_dict(value)
        if value is None:
            return True
        if expect_text and scalar:
            if not isinstance(value, str):
                return True
        if isinstance(value, str):
            text = value.strip()
            return StockAnalysisPipeline._is_agent_placeholder_text(text)
        if isinstance(value, dict):
            if scalar:
                return not allow_dict
            return not value
        if scalar and isinstance(value, (list, tuple, set)):
            return True
        return False

    @staticmethod
    def _trend_score_fallback(trend_result: Optional[TrendAnalysisResult]) -> Optional[int]:
        if trend_result is None:
            return None
        try:
            score = int(getattr(trend_result, "signal_score", 0))
        except (TypeError, ValueError):
            return None
        return score if score > 0 else None

    @staticmethod
    def _trend_label_fallback(
        trend_result: Optional[TrendAnalysisResult],
        report_language: str = "zh",
    ) -> str:
        if trend_result is None:
            return ""
        trend_status = getattr(trend_result, "trend_status", None)
        value = getattr(trend_status, "value", None) or str(trend_status or "").strip()
        if report_language != "en":
            return value
        return localize_trend_prediction(value, report_language)

    @staticmethod
    def _trend_signal_fallback(
        trend_result: Optional[TrendAnalysisResult],
        report_language: str = "zh",
    ) -> str:
        if trend_result is None:
            return ""
        buy_signal = getattr(trend_result, "buy_signal", None)
        value = getattr(buy_signal, "value", None) or str(buy_signal or "").strip()
        return localize_operation_advice(value, report_language)

    @staticmethod
    def _trend_decision_fallback(trend_result: Optional[TrendAnalysisResult]) -> Optional[str]:
        if trend_result is None:
            return None
        signal_name = getattr(getattr(trend_result, "buy_signal", None), "name", "").lower()
        return {
            "strong_buy": "buy",
            "buy": "buy",
            "hold": "hold",
            "wait": "hold",
            "sell": "sell",
            "strong_sell": "sell",
        }.get(signal_name)

    @staticmethod
    def _mark_trend_fallback_source(result: AnalysisResult) -> None:
        if "trend:fallback" in (result.data_sources or ""):
            return
        result.data_sources = (
            f"{result.data_sources},trend:fallback"
            if result.data_sources
            else "trend:fallback"
        )

    @staticmethod
    def _summary_fallback_from_result(result: AnalysisResult, report_language: str) -> str:
        trend = (result.trend_prediction or "").strip()
        advice = (result.operation_advice or "").strip()
        if trend and advice:
            if report_language == "en":
                return f"Trend view: {trend}; action advice: {advice}."
            if report_language == "ko":
                return f"추세 결론: {trend}; 대응 전략: {advice}."
            return f"趋势结论：{trend}；操作建议：{advice}。"
        return ""

    def _backfill_agent_dashboard_fields(
        self,
        result: AnalysisResult,
        trend_result: Optional[TrendAnalysisResult],
        report_language: str,
    ) -> None:
        if not isinstance(result.dashboard, dict):
            result.dashboard = {}
        dashboard = result.dashboard

        for key in (
            "sentiment_score",
            "trend_prediction",
            "operation_advice",
            "decision_type",
            "confidence_level",
            "analysis_summary",
        ):
            current = dashboard.get(key)
            if key == "sentiment_score":
                if self._is_agent_field_missing(current, scalar=True):
                    dashboard[key] = getattr(result, key)
            elif self._is_agent_field_missing(current, scalar=True, expect_text=True):
                dashboard[key] = getattr(result, key)

        core = dashboard.get("core_conclusion")
        if not isinstance(core, dict):
            core = {}
            dashboard["core_conclusion"] = core
        if self._is_agent_field_missing(core.get("one_sentence"), scalar=True):
            core["one_sentence"] = result.analysis_summary or self._summary_fallback_from_result(
                result,
                report_language,
            ) or (
                "Analysis pending" if report_language == "en"
                else "분석 보완 예정" if report_language == "ko"
                else "分析待补充"
            )

        intelligence = dashboard.get("intelligence")
        if not isinstance(intelligence, dict):
            intelligence = {}
            dashboard["intelligence"] = intelligence
        risk_alerts = intelligence.get("risk_alerts")
        if (
            "risk_alerts" not in intelligence
            or self._is_agent_field_missing(risk_alerts)
            or not isinstance(risk_alerts, list)
        ):
            risk_factors = getattr(trend_result, "risk_factors", None) or []
            intelligence["risk_alerts"] = list(risk_factors)

        if result.decision_type in ("buy", "hold"):
            battle = dashboard.get("battle_plan")
            if not isinstance(battle, dict):
                battle = {}
                dashboard["battle_plan"] = battle
            sniper_points = battle.get("sniper_points")
            if not isinstance(sniper_points, dict):
                sniper_points = {}
                battle["sniper_points"] = sniper_points
            if self._is_agent_field_missing(sniper_points.get("stop_loss"), scalar=True):
                sniper_points["stop_loss"] = self._stop_loss_fallback_from_trend(
                    trend_result,
                    report_language,
                )

    @staticmethod
    def _stop_loss_fallback_from_trend(
        trend_result: Optional[TrendAnalysisResult],
        report_language: str,
    ) -> Any:
        levels = getattr(trend_result, "support_levels", None) if trend_result else None
        if levels:
            return levels[0]
        return get_placeholder_text(report_language)

    @staticmethod
    def _apply_trend_fallback(
        result: AnalysisResult,
        trend_result: Optional[TrendAnalysisResult],
        report_language: str,
    ) -> None:
        if trend_result is None:
            result.sentiment_score = 50
            result.operation_advice = localize_operation_advice("观望", report_language)
            return

        score = getattr(trend_result, "signal_score", None)
        try:
            numeric_score = int(score)
        except (TypeError, ValueError):
            numeric_score = 50
        result.sentiment_score = numeric_score if numeric_score > 0 else 50

        trend_label = StockAnalysisPipeline._trend_label_fallback(trend_result, report_language)
        if trend_label:
            result.trend_prediction = trend_label

        buy_signal = getattr(trend_result, "buy_signal", None)
        signal_label = StockAnalysisPipeline._trend_signal_fallback(
            trend_result,
            report_language,
        )
        if signal_label:
            result.operation_advice = signal_label
        else:
            result.operation_advice = localize_operation_advice("观望", report_language)

        from src.agent.protocols import normalize_decision_signal

        signal_name = getattr(buy_signal, "name", "").lower()
        signal_to_decision = {
            "strong_buy": "buy",
            "buy": "buy",
            "hold": "hold",
            "wait": "hold",
            "sell": "sell",
            "strong_sell": "sell",
        }
        result.decision_type = signal_to_decision.get(signal_name, result.decision_type or "hold")
        result.decision_type = normalize_decision_signal(result.decision_type)
        result.data_sources = f"{result.data_sources},trend:fallback" if result.data_sources else "trend:fallback"

    @staticmethod
    def _is_placeholder_stock_name(name: str, code: str) -> bool:
        """Return True when the stock name is missing or placeholder-like."""
        if not name:
            return True
        normalized = str(name).strip()
        if not normalized:
            return True
        if normalized == code:
            return True
        if normalized.startswith("股票"):
            return True
        if "Unknown" in normalized:
            return True
        return False

    @staticmethod
    def _safe_int(value: Any, default: int = 50) -> int:
        """安全地将值转换为整数。"""
        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            import re
            match = re.search(r'-?\d+', value)
            if match:
                return int(match.group())
        return default
    
    def _describe_volume_ratio(self, volume_ratio: float) -> str:
        """
        量比描述
        
        量比 = 当前成交量 / 过去5日平均成交量
        """
        if volume_ratio < 0.5:
            return "极度萎缩"
        elif volume_ratio < 0.8:
            return "明显萎缩"
        elif volume_ratio < 1.2:
            return "正常"
        elif volume_ratio < 2.0:
            return "温和放量"
        elif volume_ratio < 3.0:
            return "明显放量"
        else:
            return "巨量"

    @staticmethod
    def _compute_ma_status(close: float, ma5: float, ma10: float, ma20: float) -> str:
        """
        Compute MA alignment status from price and MA values.
        Logic mirrors storage._analyze_ma_status (Issue #234).
        """
        close = close or 0
        ma5 = ma5 or 0
        ma10 = ma10 or 0
        ma20 = ma20 or 0
        if close > ma5 > ma10 > ma20 > 0:
            return "多头排列 📈"
        elif close < ma5 < ma10 < ma20 and ma20 > 0:
            return "空头排列 📉"
        elif close > ma5 and ma5 > ma10:
            return "短期向好 🔼"
        elif close < ma5 and ma5 < ma10:
            return "短期走弱 🔽"
        else:
            return "震荡整理 ↔️"

    def _augment_historical_with_realtime(
        self, df: pd.DataFrame, realtime_quote: Any, code: str
    ) -> pd.DataFrame:
        """
        使用当日实时行情补齐历史 OHLCV，用于盘中 MA 计算。
        Issue #234：技术指标使用实时价格，而不是沿用昨日收盘价。
        """
        if df is None or df.empty or 'close' not in df.columns:
            return df
        if realtime_quote is None:
            return df
        price = getattr(realtime_quote, 'price', None)
        if price is None or not (isinstance(price, (int, float)) and price > 0):
            return df

        # 非交易日可跳过实时补齐；异常情况下保持失败开放。
        enable_realtime_tech = getattr(
            self.config, 'enable_realtime_technical_indicators', True
        )
        if not enable_realtime_tech:
            return df
        market = get_market_for_stock(code)
        market_today = get_market_now(market).date()
        if market and not is_market_open(market, market_today):
            return df

        last_val = df['date'].max()
        last_date = (
            last_val.date() if hasattr(last_val, 'date') else
            (last_val if isinstance(last_val, date) else pd.Timestamp(last_val).date())
        )
        yesterday_close = float(df.iloc[-1]['close']) if len(df) > 0 else price
        open_p = getattr(realtime_quote, 'open_price', None) or getattr(
            realtime_quote, 'pre_close', None
        ) or yesterday_close
        high_p = getattr(realtime_quote, 'high', None) or price
        low_p = getattr(realtime_quote, 'low', None) or price
        vol = getattr(realtime_quote, 'volume', None) or 0
        amt = getattr(realtime_quote, 'amount', None)
        pct = getattr(realtime_quote, 'change_pct', None)

        if last_date >= market_today:
            # 使用实时收盘价更新最后一行；先复制，避免修改调用方传入的 df。
            df = df.copy()
            idx = df.index[-1]
            df.loc[idx, 'close'] = price
            if open_p is not None:
                df.loc[idx, 'open'] = open_p
            if high_p is not None:
                df.loc[idx, 'high'] = high_p
            if low_p is not None:
                df.loc[idx, 'low'] = low_p
            if vol:
                df.loc[idx, 'volume'] = vol
            if amt is not None:
                df.loc[idx, 'amount'] = amt
            if pct is not None:
                df.loc[idx, 'pct_chg'] = pct
        else:
            # 追加一行虚拟的当日实时 K 线。
            new_row = {
                'code': code,
                'date': market_today,
                'open': open_p,
                'high': high_p,
                'low': low_p,
                'close': price,
                'volume': vol,
                'amount': amt if amt is not None else 0,
                'pct_chg': pct if pct is not None else 0,
            }
            new_df = pd.DataFrame([new_row])
            df = pd.concat([df, new_df], ignore_index=True)
        return df

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
