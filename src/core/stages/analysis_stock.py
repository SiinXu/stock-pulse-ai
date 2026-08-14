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
from src.core.contracts import (
    AnalyzeStageInput,
    AnalyzeStageOutput,
    FetchMarketInputsOutput,
    FetchStageInput,
    build_run_context,
)
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
from src.services.sentiment_pipeline_service import SentimentPipelineService
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
            run_context = getattr(self, "_current_run_context", None)
            if run_context is None or getattr(run_context, "stock_code", None) != code:
                run_context = build_run_context(
                    query_id=query_id,
                    trace_id=getattr(self, "trace_id", None) or query_id,
                    stock_code=code,
                    report_type=report_type,
                    query_source=getattr(self, "query_source", None),
                    current_time=current_time,
                    analysis_phase=str(getattr(self, "analysis_phase", "auto") or "auto"),
                    portfolio_context=getattr(self, "portfolio_context", None),
                    save_context_snapshot=bool(
                        getattr(self, "save_context_snapshot", False)
                    ),
                )
            fetch_input = FetchStageInput(
                stock_code=code,
                operation="assemble_market_inputs",
                current_time=current_time,
                realtime_enabled=bool(self.config.enable_realtime_quote),
                chip_enabled=bool(self.config.enable_chip_distribution),
                daily_market_context_enabled=daily_market_context_enabled,
                run=run_context,
            )
            active_stage = observe_pipeline_stage(
                "fetch",
                input_summary=fetch_input.to_input_summary(),
                retryable=True,
            )
            portfolio_context = getattr(self, "portfolio_context", None)
            if not isinstance(portfolio_context, dict):
                portfolio_context = None
            market = get_market_for_stock(normalize_stock_code(code))
            run_context = run_context.with_market(market)
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

            # Steps 1–2.5: dependency-free market inputs (realtime / chip / money-flow /
            # fundamental). Parallel when enabled; same provider-governed call sites
            # and deterministic merge order when serial (Issue #1126).
            (
                realtime_quote,
                chip_data,
                money_flow_data,
                fundamental_context,
                stock_name,
            ) = self._fetch_dependency_free_market_inputs(
                code=code,
                stock_name=stock_name,
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
                from src.utils.indicator_periods import periods_from_config
                from src.services.history_loader import get_frozen_target_date
                _mkt = get_market_for_stock(normalize_stock_code(code))
                frozen = get_frozen_target_date()
                end_date = frozen if frozen else get_market_now(_mkt).date()
                # Lookback scales with configured indicator periods (defaults ≈ MA60/MACD).
                # stock_daily_window_resolver is for backtest eval windows only and is unchanged.
                indicator_periods = periods_from_config(self.config)
                lookback_calendar_days = indicator_periods.required_history_calendar_days()
                start_date = end_date - timedelta(days=lookback_calendar_days)
                historical_bars = self.db.get_data_range(code, start_date, end_date)
                if historical_bars:
                    df = pd.DataFrame([bar.to_dict() for bar in historical_bars])
                    # Issue #234: Augment with realtime for intraday MA calculation
                    if self.config.enable_realtime_quote and realtime_quote:
                        df = self._augment_historical_with_realtime(df, realtime_quote, code)
                    # Issue #185: reject non-finite OHLCV before indicator synthesis.
                    from data_provider.data_validation import prepare_indicator_inputs

                    df, input_validation = prepare_indicator_inputs(
                        df,
                        market=_mkt,
                        stock_code=code,
                        provider="trend_analysis",
                    )
                    # Degrade only when the cleaned frame is empty or every row was
                    # rejected. Validation-disabled path leaves clean_rows unset.
                    clean_rows = input_validation.context.get("clean_rows")
                    inputs_unusable = (
                        df is None
                        or (hasattr(df, "empty") and bool(df.empty))
                        or (clean_rows is not None and int(clean_rows) == 0)
                    )
                    if inputs_unusable:
                        logger.warning(
                            "%s(%s) trend analysis skipped: indicator inputs failed validation",
                            stock_name,
                            code,
                        )
                        trend_result = None
                    else:
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
                or fundamental_status in {
                    "failed",
                    "partial",
                    "missing",
                    "validation_rejected",
                }
                or trend_result is None
                or (
                    daily_market_context_enabled
                    and daily_market_context is None
                )
            )
            market_inputs = FetchMarketInputsOutput(
                realtime_quote=realtime_quote,
                chip_data=chip_data,
                fundamental_context=fundamental_context,
                trend_result=trend_result,
                daily_market_context=daily_market_context,
            )
            fetch_result = (
                PipelineStageResult.degraded(
                    PipelineStageName.FETCH,
                    market_inputs,
                    reason=(
                        "One or more market inputs were unavailable; "
                        "analysis continued with existing fallbacks."
                    ),
                    retryable=True,
                )
                if fetch_degraded
                else PipelineStageResult.success(
                    PipelineStageName.FETCH,
                    market_inputs,
                )
            )
            self._finish_pipeline_stage(
                active_stage,
                fetch_result,
                output_summary=market_inputs.to_output_summary(
                    fundamental_status=fundamental_status or "available",
                    daily_market_context_enabled=daily_market_context_enabled,
                ),
            )
            active_stage = None
            analyze_input = AnalyzeStageInput(
                stock_code=code,
                report_type=report_type,
                query_id=query_id,
                current_time=current_time,
                stock_name=stock_name,
                market_inputs=market_inputs,
                run=run_context.with_stock_name(stock_name),
            )
            # Retain for later stage diagnostics without changing control flow.
            self._current_analyze_input = analyze_input

            if use_agent:
                logger.info("%s(%s) running analysis in Agent mode", stock_name, code)
                self._emit_progress(58, f"{stock_name}：正在切换 Agent 分析链路")
                market_regime_context = self._build_market_regime_context(
                    code=code,
                    market=market,
                    trend_result=trend_result,
                )
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
                    market_regime_context=market_regime_context,
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
            intel_results: Optional[Dict[str, Any]] = None
            sentiment_snapshot: Optional[Dict[str, Any]] = None
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

            # First-class sentiment evidence from already-fetched news/events only.
            # Explicit degradation when sources are missing; never blocks analysis.
            try:
                window_days = 7
                try:
                    window_days = max(
                        1,
                        int(self.config.get_effective_news_window_days() or 7),
                    )
                except Exception:  # broad-exception: optional_metadata - window fallback keeps scoring usable
                    window_days = int(
                        getattr(self.config, "news_max_age_days", 7) or 7
                    )
                sentiment_service = SentimentPipelineService(window_days=window_days)
                sentiment_model = sentiment_service.build_from_intel_results(
                    stock_code=code,
                    stock_name=stock_name,
                    market=market or "cn",
                    intel_results=intel_results,
                    remote_search_available=remote_search_available,
                    news_context=news_context,
                )
                sentiment_snapshot = sentiment_model.to_public_dict()
                logger.info(
                    "%s(%s) sentiment evidence: status=%s score=%s label=%s freshness=%s",
                    stock_name,
                    code,
                    sentiment_model.status,
                    sentiment_model.score,
                    sentiment_model.label,
                    sentiment_model.freshness,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - sentiment is optional evidence
                log_safe_exception(
                    logger,
                    "Sentiment pipeline failed; continuing without sentiment evidence",
                    exc,
                    error_code="pipeline_sentiment_snapshot_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )
                sentiment_snapshot = SentimentPipelineService().build_unavailable(
                    stock_code=code,
                    stock_name=stock_name,
                    market=market or "cn",
                    reason_code="scoring_failed",
                    gaps=["scoring_failed"],
                ).to_public_dict()
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
                money_flow_data=money_flow_data,
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

            market_regime_context = self._build_market_regime_context(
                code=code,
                market=market,
                trend_result=trend_result,
            )
            if isinstance(market_regime_context, dict):
                enhanced_context["market_regime_context"] = market_regime_context

            # Step 6.5: Historical decision memory & reflection (Issue #118).
            # Injects past signal outcomes for this stock into the prompt so the
            # model can calibrate confidence; never alters direction. Gated for
            # zero overhead when disabled, and fail-open so memory never breaks
            # analysis.
            decision_reflection = None
            if getattr(self.config, "decision_memory_enabled", True):
                try:
                    from src.services.decision_memory_service import (
                        DecisionMemoryService,
                        format_decision_memory_prompt_section,
                    )

                    decision_reflection = DecisionMemoryService().build_reflection(
                        stock_code=code,
                        market=market,
                        lookback=int(getattr(self.config, "decision_memory_lookback", 5)),
                        min_age_days=int(getattr(self.config, "decision_memory_min_age_days", 3)),
                        min_samples=int(getattr(self.config, "decision_memory_min_samples", 5)),
                    )
                    if decision_reflection is not None:
                        enhanced_context["decision_memory_reflection_prompt"] = (
                            format_decision_memory_prompt_section(
                                decision_reflection,
                                report_language=report_language,
                            )
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
                    decision_reflection = None

            try:
                from src.services.investment_framework_prompt import (
                    inject_framework_into_analysis_context,
                )

                inject_framework_into_analysis_context(
                    enhanced_context,
                    report_language=report_language,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Framework inject is optional research context.
                log_safe_exception(
                    logger,
                    "Personal investment framework inject failed",
                    exc,
                    error_code="pipeline_investment_framework_inject_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )

            try:
                from src.agent.evolution.error_patterns import (
                    inject_error_patterns_into_analysis_context,
                )

                inject_error_patterns_into_analysis_context(
                    enhanced_context,
                    config=self.config,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Optional checklist failures are logged and omitted.
                log_safe_exception(
                    logger,
                    "Error-pattern checklist injection failed",
                    exc,
                    error_code="pipeline_error_pattern_injection_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )

            try:
                from src.services.research_persona_prompt import (
                    inject_research_persona_into_analysis_context,
                )

                inject_research_persona_into_analysis_context(
                    enhanced_context,
                    config=self.config,
                    report_language=report_language,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Research persona is optional.
                log_safe_exception(
                    logger,
                    "Research persona inject failed",
                    exc,
                    error_code="pipeline_research_persona_inject_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
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
                    money_flow_data=money_flow_data,
                    sentiment_snapshot=sentiment_snapshot,
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

            from src.agent.multi_model_consensus import (
                is_multi_model_consensus_enabled,
                public_multi_model_comparison_payload,
                resolve_consensus_models_for_run,
                run_multi_model_consensus_analysis,
            )

            multi_model_enabled = is_multi_model_consensus_enabled(self.config)
            multi_model_candidates: list = []
            multi_model_budget_meta: dict = {}
            if multi_model_enabled:
                multi_model_candidates, multi_model_budget_meta = (
                    resolve_consensus_models_for_run(self.config)
                )
            use_multi_model = multi_model_enabled and len(multi_model_candidates) >= 2

            active_stage = observe_pipeline_stage(
                "analyze",
                input_summary={
                    "stock_code": code,
                    "mode": "legacy_multi_model" if use_multi_model else "legacy",
                    "report_type": report_type.value,
                    "context_pack_available": bool(analysis_context_pack_summary),
                    "multi_model_consensus": bool(use_multi_model),
                    "multi_model_count": len(multi_model_candidates) if use_multi_model else 0,
                    "multi_model_budget_enforced": bool(
                        multi_model_budget_meta.get("budget_enforced")
                    )
                    if multi_model_enabled
                    else False,
                },
                retryable=True,
            )
            self._emit_progress(64, f"{stock_name}：正在请求 LLM 生成报告")
            llm_started_at = time.monotonic()
            multi_model_comparison = None
            try:
                if use_multi_model:
                    self._emit_progress(
                        64,
                        f"{stock_name}：多模型共识对比（{len(multi_model_candidates)} 模型）",
                    )
                    result, multi_model_comparison = run_multi_model_consensus_analysis(
                        analyzer=self.analyzer,
                        config=self.config,
                        context=enhanced_context,
                        news_context=news_context,
                        analysis_context_pack_summary=analysis_context_pack_summary,
                        progress_callback=self._emit_progress,
                        stream_progress_callback=_on_llm_stream,
                        record_llm_run=record_llm_run,
                        record_llm_run_started=record_llm_run_started,
                    )
                    if multi_model_comparison is None:
                        # Models could not be resolved; fall back to single-model path.
                        use_multi_model = False
                    elif result is None:
                        # Multi-model was attempted and every model failed: do not spend
                        # another full single-model call on top of the failed fan-out.
                        use_multi_model = True

                if not use_multi_model:
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
                elif result is not None and multi_model_comparison is not None:
                    # Ensure product payload is present even if runner attached a private copy.
                    public_payload = public_multi_model_comparison_payload(
                        multi_model_comparison
                    )
                    if public_payload is not None:
                        dashboard = getattr(result, "dashboard", None)
                        if not isinstance(dashboard, dict):
                            dashboard = {}
                            result.dashboard = dashboard
                        dashboard["multi_model_comparison"] = public_payload
                        # Preserve honesty flags the runner already stamped.
                        handling = public_payload.get("disagreement_handling") or {}
                        if handling.get("high_disagreement"):
                            dashboard["multi_model_high_disagreement"] = True
                        degradation = public_payload.get("degradation")
                        if isinstance(degradation, dict) and degradation.get("annotation"):
                            dashboard["multi_model_degradation"] = {
                                "annotation": degradation.get("annotation"),
                                "reason": degradation.get("reason"),
                                "failed_models": list(
                                    degradation.get("failed_models") or []
                                )[:5],
                            }
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
                if isinstance(market_regime_context, dict):
                    result.market_regime_context = market_regime_context
                result.market_phase_summary = market_phase_summary
                result.analysis_context_pack_overview = analysis_context_pack_overview
                self._refresh_decision_action_for_final_result(
                    result,
                    report_type=report_type.value,
                    previous_operation_advice=action_source_advice,
                )
                info_quality_adjustments = self._apply_info_quality_constraints(
                    result,
                    analysis_context_pack_overview=analysis_context_pack_overview,
                )
                if info_quality_adjustments:
                    logger.info(
                        "[info_quality] Applied constraints for %s: %s",
                        code,
                        info_quality_adjustments,
                    )
                    self._refresh_decision_action_for_final_result(
                        result,
                        report_type=report_type.value,
                        previous_operation_advice=action_source_advice,
                    )

            analyze_output = AnalyzeStageOutput.from_result(result)
            analysis_succeeded = analyze_output.analysis_success
            analysis_degradation_reason = (
                getattr(result, "error_message", None)
                if result is not None and not analysis_succeeded
                else ("Analysis returned no result." if result is None else None)
            )
            # Keep historical value shape (AnalysisResult) for zero behavior change.
            analysis_stage_result = (
                PipelineStageResult.success(
                    PipelineStageName.ANALYZE,
                    analyze_output.as_legacy_value(),
                )
                if analysis_succeeded
                else PipelineStageResult.failed(
                    PipelineStageName.ANALYZE,
                    value=analyze_output.as_legacy_value(),
                    retryable=True,
                    reason=analysis_degradation_reason,
                )
            )
            self._finish_pipeline_stage(
                active_stage,
                analysis_stage_result,
                output_summary=analyze_output.to_output_summary(),
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
                        sentiment_snapshot=sentiment_snapshot,
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
                    prediction_mode="analysis",
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

    def _fetch_dependency_free_market_inputs(
        self,
        *,
        code: str,
        stock_name: str,
    ) -> Tuple[Any, Optional[ChipDistribution], Any, Optional[Dict[str, Any]], str]:
        """Fetch realtime/chip/money-flow/fundamental inputs with optional parallelism.

        Each branch still calls ``DataFetcherManager`` (provider fallback, cache,
        circuit, validation). Parallel mode only coordinates independent call
        sites; disable via ``ANALYSIS_PARALLEL_FETCH_ENABLED=false`` for serial
        declaration-order execution (Issue #1126).
        """
        from data_provider.data_validation import DataValidationRejected
        from src.services.parallel_data_fetch import (
            FetchTask,
            is_parallel_fetch_enabled,
            limits_from_config,
            run_parallel_fetches,
        )

        name_holder = {"value": stock_name}

        def _pull_realtime():
            if not self.config.enable_realtime_quote:
                logger.info(
                    "%s(%s) realtime quotes are disabled; using historical close price",
                    name_holder["value"],
                    code,
                )
                return None
            try:
                quote = self.fetcher_manager.get_realtime_quote(
                    code, log_final_failure=False
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Realtime failure is safely logged before historical-price fallback.
                log_safe_exception(
                    logger,
                    "Realtime quote retrieval failed; using historical close data",
                    exc,
                    error_code="pipeline_realtime_quote_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )
                return None
            if not quote:
                logger.warning(
                    "%s(%s) all realtime quote sources failed; using historical close price",
                    name_holder["value"],
                    code,
                )
                return None
            if getattr(quote, "name", None):
                name_holder["value"] = quote.name
            volume_ratio = getattr(quote, "volume_ratio", None)
            turnover_rate = getattr(quote, "turnover_rate", None)
            logger.info(
                "%s(%s) realtime quote: price=%s volume_ratio=%s "
                "turnover_rate=%s%% source=%s",
                name_holder["value"],
                code,
                quote.price,
                volume_ratio,
                turnover_rate,
                quote.source.value if hasattr(quote, "source") else "unknown",
            )
            return quote

        def _pull_chip():
            try:
                chip = self.fetcher_manager.get_chip_distribution(code)
            except Exception as exc:  # broad-exception: fallback_recorded - Chip-data failure is safely logged before optional-input degradation.
                log_safe_exception(
                    logger,
                    "Chip distribution retrieval failed",
                    exc,
                    error_code="pipeline_chip_distribution_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )
                return None
            if chip:
                logger.info(
                    "%s(%s) chip distribution: profit_ratio=%.1f%% concentration_90=%.2f%%",
                    name_holder["value"],
                    code,
                    chip.profit_ratio * 100,
                    chip.concentration_90 * 100,
                )
            else:
                logger.debug(
                    "%s(%s) chip-distribution data is unavailable or disabled",
                    name_holder["value"],
                    code,
                )
            return chip

        def _pull_money_flow():
            if not getattr(self.config, "smartmoney_enabled", False):
                return None
            try:
                money_flow = self.fetcher_manager.get_money_flow(code)
            except Exception as exc:  # broad-exception: fallback_recorded - money-flow is optional and must not block analysis.
                log_safe_exception(
                    logger,
                    "SmartMoney money flow retrieval failed",
                    exc,
                    error_code="pipeline_money_flow_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )
                return None
            if money_flow is not None:
                snapshot = getattr(money_flow, "snapshot", None)
                logger.info(
                    "%s(%s) money flow: status=%s main_net_inflow=%s source=%s",
                    name_holder["value"],
                    code,
                    getattr(getattr(money_flow, "status", None), "value", None),
                    getattr(snapshot, "main_net_inflow", None),
                    getattr(snapshot, "source", None),
                )
            return money_flow

        def _pull_fundamental():
            try:
                return self.fetcher_manager.get_fundamental_context(
                    code,
                    budget_seconds=getattr(
                        self.config,
                        "fundamental_stage_timeout_seconds",
                        FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
                    ),
                )
            except DataValidationRejected as rejection:
                log_safe_exception(
                    logger,
                    "Fundamental data rejected by validation policy",
                    rejection,
                    error_code="pipeline_fundamental_validation_rejected",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )
                return self.fetcher_manager.build_validation_rejected_fundamental_context(
                    code,
                    rejection,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Fundamental failure is safely logged before a failed-context fallback is built.
                log_safe_exception(
                    logger,
                    "Fundamental data aggregation failed",
                    exc,
                    error_code="pipeline_fundamental_aggregation_failed",
                    level=logging.WARNING,
                    context={"stock_code": code},
                )
                return self.fetcher_manager.build_failed_fundamental_context(
                    code, str(exc)
                )

        # Declaration order is the merge order into stage IO / AgentContext.
        # Disabled optional capabilities are omitted so they do not consume slots.
        tasks = [
            FetchTask(
                key="realtime_quote",
                fn=_pull_realtime,
                provider_key="realtime",
                optional=True,
            ),
            FetchTask(
                key="chip_distribution",
                fn=_pull_chip,
                provider_key="chip",
                optional=True,
            ),
        ]
        if getattr(self.config, "smartmoney_enabled", False):
            tasks.append(
                FetchTask(
                    key="money_flow",
                    fn=_pull_money_flow,
                    provider_key="money_flow",
                    optional=True,
                )
            )
        tasks.append(
            FetchTask(
                key="fundamental_context",
                fn=_pull_fundamental,
                provider_key="fundamental",
                optional=True,
            )
        )
        report = run_parallel_fetches(
            tasks,
            enabled=is_parallel_fetch_enabled(self.config),
            limits=limits_from_config(self.config),
        )
        logger.debug(
            "%s(%s) dependency-free market fetch wave: %s",
            name_holder["value"],
            code,
            report.to_diagnostics(),
        )

        values = report.values_by_key()
        realtime_quote = values.get("realtime_quote")
        chip_data = values.get("chip_distribution")
        money_flow_data = values.get("money_flow")
        fundamental_context = values.get("fundamental_context")

        resolved_name = name_holder["value"]
        if not resolved_name:
            resolved_name = f"股票{code}"
        return (
            realtime_quote,
            chip_data,
            money_flow_data,
            fundamental_context,
            resolved_name,
        )






# Keep AST-preserved static self-references valid when this private source
# container is inspected or invoked directly.
StockAnalysisPipeline = _StockAnalysisStageMixin
