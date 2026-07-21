# -*- coding: utf-8 -*-
"""Analysis and context stages for the stock analysis pipeline."""

import logging
import sys
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
    fill_price_position_if_needed as _fill_price_position_if_needed_impl,
    normalize_chip_structure_availability,
    populate_decision_action_fields,
    stabilize_decision_with_structure as _stabilize_decision_with_structure_impl,
)
from src.config import FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT
from src.core.pipeline_stage_results import (
    PipelineStageName,
    PipelineStageResult,
)
from src.core.trading_calendar import (
    build_market_phase_context as _build_market_phase_context_impl,
    get_effective_trading_date as _get_effective_trading_date_impl,
    get_market_for_stock as _get_market_for_stock_impl,
    get_market_now as _get_market_now_impl,
    is_market_open as _is_market_open_impl,
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
from src.search_service import SearchService as _SearchServiceImpl
from src.services.daily_market_context import (
    DailyMarketContext,
    DailyMarketContextService as _DailyMarketContextServiceImpl,
    format_daily_market_context_prompt_section,
)
from src.services.market_hotspot_service import MarketHotspotService
from src.services.market_structure_service import MarketStructureService
from src.services.run_diagnostics import (
    PipelineStageObservation,
    current_diagnostic_snapshot as _current_diagnostic_snapshot_impl,
    observe_pipeline_stage,
    record_llm_run,
    record_llm_run_started,
)
from src.stock_analyzer import TrendAnalysisResult
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger("src.core.pipeline")
_DAILY_MARKET_CONTEXT_SERVICE_LOCK_INIT_GUARD = threading.Lock()


def _resolve_legacy_symbol(name: str, fallback: Any) -> Any:
    """Resolve a symbol through the legacy pipeline patch surface."""

    pipeline_module = sys.modules.get("src.core.pipeline")
    return getattr(pipeline_module, name, fallback)


class _LegacySymbolProxy:
    """Forward calls and attributes through the legacy pipeline module."""

    def __init__(self, name: str, fallback: Any):
        """Store the legacy symbol name and its production fallback."""

        self._name = name
        self._fallback = fallback

    def _resolve(self) -> Any:
        """Return the currently active legacy symbol."""

        return _resolve_legacy_symbol(self._name, self._fallback)

    def __call__(self, *args, **kwargs):
        """Invoke the currently active legacy symbol."""

        return self._resolve()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Read an attribute from the currently active legacy symbol."""

        return getattr(self._resolve(), name)


def build_market_phase_context(*args, **kwargs):
    """Call the legacy market-phase builder patch seam."""

    resolver = _resolve_legacy_symbol(
        "build_market_phase_context",
        _build_market_phase_context_impl,
    )
    return resolver(*args, **kwargs)


def current_diagnostic_snapshot(*args, **kwargs):
    """Call the legacy diagnostic snapshot patch seam."""

    resolver = _resolve_legacy_symbol(
        "current_diagnostic_snapshot",
        _current_diagnostic_snapshot_impl,
    )
    return resolver(*args, **kwargs)


def fill_price_position_if_needed(*args, **kwargs):
    """Call the legacy price-position patch seam."""

    resolver = _resolve_legacy_symbol(
        "fill_price_position_if_needed",
        _fill_price_position_if_needed_impl,
    )
    return resolver(*args, **kwargs)


def get_effective_trading_date(*args, **kwargs):
    """Call the legacy effective-date patch seam."""

    resolver = _resolve_legacy_symbol(
        "get_effective_trading_date",
        _get_effective_trading_date_impl,
    )
    return resolver(*args, **kwargs)


def get_market_for_stock(*args, **kwargs):
    """Call the legacy market-resolution patch seam."""

    resolver = _resolve_legacy_symbol(
        "get_market_for_stock",
        _get_market_for_stock_impl,
    )
    return resolver(*args, **kwargs)


def get_market_now(*args, **kwargs):
    """Call the legacy market-clock patch seam."""

    resolver = _resolve_legacy_symbol("get_market_now", _get_market_now_impl)
    return resolver(*args, **kwargs)


def is_market_open(*args, **kwargs):
    """Call the legacy market-open patch seam."""

    resolver = _resolve_legacy_symbol("is_market_open", _is_market_open_impl)
    return resolver(*args, **kwargs)


def stabilize_decision_with_structure(*args, **kwargs):
    """Call the legacy decision-stabilization patch seam."""

    resolver = _resolve_legacy_symbol(
        "stabilize_decision_with_structure",
        _stabilize_decision_with_structure_impl,
    )
    return resolver(*args, **kwargs)


DailyMarketContextService = _LegacySymbolProxy(
    "DailyMarketContextService",
    _DailyMarketContextServiceImpl,
)
SearchService = _LegacySymbolProxy("SearchService", _SearchServiceImpl)


class _AnalysisStageMixin:
    """Provide stock analysis, context, and result-normalization stages."""

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
\x20\x20\x20\x20\x20\x20\x20\x20
        将实时行情、筹码分布、趋势分析结果、股票名称添加到上下文中
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            context: 原始上下文
            realtime_quote: 实时行情数据（UnifiedRealtimeQuote 或 None）
            chip_data: 筹码分布数据
            trend_result: 趋势分析结果
            stock_name: 股票名称
            market_phase_context: 已构建的市场阶段上下文，用于标记盘中 partial bar
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
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
        except Exception as e:  # broad-exception: fallback_recorded - Board lookup failure is logged before continuing without board data.
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
            except Exception as exc:  # broad-exception: fallback_recorded - Ranking service failure is logged before using the fetcher fallback.
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
            except Exception as e:  # broad-exception: fallback_recorded - Ranking failure is logged before returning empty rankings.
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
            except Exception as exc:  # broad-exception: fallback_recorded - Structure service failure is logged before omitting optional context.
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
        except Exception as exc:  # broad-exception: fallback_recorded - Structure build failure is logged before omitting optional context.
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
\x20\x20\x20\x20\x20\x20\x20\x20
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


StockAnalysisPipeline = _LegacySymbolProxy(
    "StockAnalysisPipeline",
    _AnalysisStageMixin,
)
