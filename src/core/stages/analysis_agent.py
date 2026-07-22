# -*- coding: utf-8 -*-
"""Provide Agent execution and daily-context stages."""

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


class _AgentAnalysisStageMixin:
    """Provide Agent execution and daily-context stages."""

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
        except Exception as e:  # broad-exception: fallback_recorded - History prefetch failure is logged before agent analysis continues.
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
        Analyze a single stock using Agent mode.
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

            # Run Agent
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

            # Convert to AnalysisResult
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

            # Save news intelligence to database (Agent tool results are only for LLM context, not persisted, Fixes #396)
            # Use search_stock_news (consistent with Agent tool call logic), only 1 API call, no extra delay
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

            # Save an analysis history record
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
        except Exception as exc:  # broad-exception: fallback_recorded - Context load failure is logged before a missing-data context is returned.
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
        except Exception as exc:  # broad-exception: fallback_recorded - Regional fetch failure is logged before the stored-context fallback.
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
        except Exception as exc:  # broad-exception: fallback_recorded - Regional persistence failure is logged before in-memory context construction.
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



# Keep AST-preserved static self-references valid when this private source
# container is inspected or invoked directly.
StockAnalysisPipeline = _AgentAnalysisStageMixin
