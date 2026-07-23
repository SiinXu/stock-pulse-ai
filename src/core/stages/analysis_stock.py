# -*- coding: utf-8 -*-
"""Provide end-to-end stock analysis orchestration."""

import logging
import threading
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from data_provider.base import normalize_stock_code
from data_provider.realtime_types import ChipDistribution
from data_provider.us_index_mapping import is_us_stock_code
from src.analyzer import (
    AnalysisResult,
    fill_price_position_if_needed,
    normalize_chip_structure_availability,
    populate_decision_action_fields,
    stabilize_decision_with_structure,
)
from src.config import FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT
from src.core.pipeline_stage_results import (
    PipelineStageName,
    PipelineStageResult,
)
from src.core.trading_calendar import (
    build_market_phase_context,
    get_effective_trading_date,
    get_market_for_stock,
    get_market_now,
    is_market_open,
)
from src.daily_market_context_guardrail import apply_daily_market_context_guardrail
from src.enums import ReportType
from src.market_phase_summary import render_market_phase_summary
from src.phase_decision_guardrail import apply_phase_decision_guardrails
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
from src.services.daily_market_context import (
    DailyMarketContext,
    DailyMarketContextService,
    format_daily_market_context_prompt_section,
)
from src.services.market_hotspot_service import MarketHotspotService
from src.services.market_structure_service import MarketStructureService
from src.services.run_diagnostics import (
    PipelineStageObservation,
    current_diagnostic_snapshot,
    observe_pipeline_stage,
    record_llm_run,
    record_llm_run_started,
)
from src.stock_analyzer import TrendAnalysisResult
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger("src.core.pipeline")
_DAILY_MARKET_CONTEXT_SERVICE_LOCK_INIT_GUARD = threading.Lock()


class _StockAnalysisStageMixin:
    """Provide end-to-end stock analysis orchestration."""

    def _maybe_build_decision_reflection(
        self,
        *,
        code: str,
        market: Optional[str],
    ) -> Optional[Any]:
        """Build a historical decision reflection, or None.

        Gated by ``decision_memory_enabled`` for zero overhead when disabled, and
        fail-open: any error degrades to None so memory never breaks analysis.
        """
        if not getattr(self.config, "decision_memory_enabled", True):
            return None
        try:
            from src.services.decision_memory_service import DecisionMemoryService

            return DecisionMemoryService().build_reflection(
                stock_code=code,
                market=market,
                lookback=int(getattr(self.config, "decision_memory_lookback", 5)),
                min_age_days=int(getattr(self.config, "decision_memory_min_age_days", 3)),
                min_samples=int(getattr(self.config, "decision_memory_min_samples", 5)),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Decision memory is advisory; failure must not break analysis.
            log_safe_exception(
                logger,
                "Decision memory reflection build failed",
                exc,
                error_code="pipeline_decision_memory_failed",
                level=logging.WARNING,
                context={"stock_code": code},
            )
            return None

    def analyze_stock(
        self,
        code: str,
        report_type: ReportType,
        query_id: str,
        current_time: Optional[datetime] = None,
    ) -> Optional[AnalysisResult]:
        """
        分析单只股票（增强版：含量比、换手率、筹码分析、多维度情报）
\x20\x20\x20\x20\x20\x20\x20\x20
        流程：
        1. 获取实时行情（量比、换手率）- 通过 DataFetcherManager 自动故障切换
        2. 获取筹码分布 - 通过 DataFetcherManager 带熔断保护
        3. 进行趋势分析（基于交易理念）
        4. 多维度情报搜索（最新消息+风险排查+业绩预期）
        5. 从数据库获取分析上下文
        6. 调用 AI 进行综合分析
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            query_id: 查询链路关联 id
            code: 股票代码
            report_type: 报告类型
            current_time: 本轮运行冻结的参考时间，用于统一市场阶段上下文
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
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
            # Get stock name (first try light name path, then overwrite with realtime_quote.name if available)
            stock_name = self.fetcher_manager.get_stock_name(code, allow_realtime=False)

            # Step 1: Get real-time quotes (volume ratio, turnover rate, etc.) - Use a unified entry with automatic failover
            realtime_quote = None
            try:
                if self.config.enable_realtime_quote:
                    realtime_quote = self.fetcher_manager.get_realtime_quote(code, log_final_failure=False)
                    if realtime_quote:
                        # Use the actual stock name returned from real-time market data.
                        if realtime_quote.name:
                            stock_name = realtime_quote.name
                        # Compatible with fields from different data sources (some data sources may not have volume_ratio).
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

            # If a name is still not available, use the code as the name.
            if not stock_name:
                stock_name = f'股票{code}'

            # Step 2: Get Position Distribution - Using a Unified Entry with Circuit Protection
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

            # Step 2.5: Fundamental Capability Aggregation (unified entry, exception degradation)
            # - Return partial/failed if timeout, does not affect existing technical indicator/news link
            # - Return not_supported structure when the switch is closed.
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

            # Step 3: Trend Analysis (Based on Trading Philosophy) – Execute before the Agent branch, shared by two paths
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

            # Step 4: Multi-Dimensional Intelligence Search (Latest News + Risk Assessment + Earnings Expectations)
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

                # Use multi-dimensional search (up to 5 searches)
                intel_results = self.search_service.search_comprehensive_intel(
                    stock_code=code,
                    stock_name=stock_name,
                    max_searches=5
                )

                # Format the intelligence report
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

                    # Save news intelligence to database (for subsequent review and querying)
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

            # Step 5: Get Analytical Context (Technical Face Data)
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

            # Step 6: Add real-time quotes, chip distribution, trend analysis, and the stock name to the context.
            enhanced_context = self._enhance_context(
                context,
                realtime_quote,
                chip_data,
                trend_result,
                stock_name,  # Pass in stock name
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

            # Step 6.5: Historical decision memory & reflection (Issue #118).
            # Injects past signal outcomes for this stock into the prompt so the
            # model can calibrate confidence; never alters direction. Zero extra
            # work when disabled or when the stock has no evaluated history.
            decision_reflection = self._maybe_build_decision_reflection(
                code=code,
                market=market,
            )
            if decision_reflection is not None:
                from src.services.decision_memory_service import (
                    format_decision_memory_prompt_section,
                )

                enhanced_context["decision_memory_reflection_prompt"] = (
                    format_decision_memory_prompt_section(
                        decision_reflection,
                        report_language=report_language,
                    )
                )

            # Step 7: Call AI Analysis (Pass in Enhanced Context and News)
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

            # Step 7.5: Populate Price Information into result during analysis
            if result:
                self._emit_progress(94, f"{stock_name}：正在校验并整理分析结果")
                result.query_id = query_id
                realtime_data = enhanced_context.get('realtime', {})
                result.current_price = realtime_data.get('price')
                result.change_pct = realtime_data.get('change_pct')
                result.decision_reflection = decision_reflection

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

            # Step 8: Save analysis history records
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



# Keep AST-preserved static self-references valid when this private source
# container is inspected or invoked directly.
StockAnalysisPipeline = _StockAnalysisStageMixin
