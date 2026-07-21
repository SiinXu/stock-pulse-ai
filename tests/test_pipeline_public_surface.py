"""Guard the compatibility surface of ``src.core.pipeline``."""

import importlib

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()


EXPECTED_PUBLIC_EXPORTS = frozenset(
    """
    AnalysisContextBuilder AnalysisRequestContext AnalysisResult Any Callable
    ChipDistribution Config ContextVar DailyMarketContext
    DailyMarketContextService DataFetcherManager Dict ExitStack
    FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT GeminiAnalyzer
    IntelligenceService List MARKET_PHASE_SUMMARY_KEY MarketHotspotService
    MarketStructureService NotificationChannel NotificationService Optional
    PIPELINE_STAGE_NAMES PipelineAnalysisArtifacts PipelinePersistValue
    PipelineStageName PipelineStageObservation PipelineStageResult
    PipelineStageRunner PipelineStageStatus ReportType SearchService
    SimpleNamespace SocialSentimentService StockAnalysisPipeline
    StockTrendAnalyzer ThreadPoolExecutor TrendAnalysisResult Tuple
    activate_run_diagnostic_context apply_daily_market_context_guardrail
    apply_phase_decision_guardrails as_completed build_market_phase_context
    current_diagnostic_snapshot date datetime defaultdict
    extract_and_persist_from_analysis_result fill_price_position_if_needed
    format_analysis_context_pack_prompt_section
    format_daily_market_context_prompt_section get_config
    get_current_diagnostic_context get_db get_effective_trading_date
    get_market_for_stock get_market_now get_placeholder_text get_unknown_text
    infer_decision_type_from_advice is_bse_code is_market_open
    is_us_stock_code localize_confidence_level localize_operation_advice
    localize_trend_prediction log_safe_exception logger logging
    normalize_chip_structure_availability normalize_report_language
    normalize_stock_code observe_pipeline_stage pd
    populate_decision_action_fields record_history_run record_llm_run
    record_llm_run_started record_missing_pipeline_stages_as_skipped
    record_notification_run record_pipeline_stage
    render_analysis_context_pack_overview render_market_phase_summary
    reset_run_diagnostic_context sanitize_diagnostic_text
    stabilize_decision_with_structure summarize_decision_signal threading time
    timedelta timezone uuid
    """.split()
)

EXPECTED_DELIVERY_METHODS = (
    "_delivery_stage_key",
    "_run_delivery_attempt",
    "_send_single_stock_notification",
    "_save_local_report",
    "_send_notifications",
    "_generate_aggregate_report",
)

EXPECTED_ANALYSIS_METHODS = (
    "analyze_stock",
    "_enhance_context",
    "_attach_belong_boards_to_fundamental_context",
    "_attach_concept_rankings_to_fundamental_context",
    "_get_concept_rankings_for_market",
    "_build_market_structure_context",
    "_ensure_agent_history",
    "_analyze_with_agent",
    "_load_agent_analysis_context",
    "_get_analysis_context_with_market_fallback",
    "_build_analysis_context_from_daily_df",
    "_is_daily_market_context_enabled",
    "_load_daily_market_context",
    "_get_daily_market_context_service_lock",
    "_coerce_daily_market_context_date",
    "_attach_daily_market_context",
    "_agent_result_to_analysis_result",
    "_refresh_decision_action_for_final_result",
    "_agent_dashboard_value",
    "_extract_advice_text_from_dict",
    "_is_agent_placeholder_text",
    "_is_agent_field_missing",
    "_trend_score_fallback",
    "_trend_label_fallback",
    "_trend_signal_fallback",
    "_trend_decision_fallback",
    "_mark_trend_fallback_source",
    "_summary_fallback_from_result",
    "_backfill_agent_dashboard_fields",
    "_stop_loss_fallback_from_trend",
    "_apply_trend_fallback",
    "_is_placeholder_stock_name",
    "_safe_int",
    "_describe_volume_ratio",
    "_compute_ma_status",
    "_augment_historical_with_realtime",
)


def test_pipeline_public_exports_match_pre_split_snapshot():
    """Assert that the facade exports exactly the pre-split public names."""

    pipeline_module = importlib.import_module("src.core.pipeline")

    actual_exports = {
        name for name in vars(pipeline_module) if not name.startswith("_")
    }

    assert actual_exports == EXPECTED_PUBLIC_EXPORTS


def test_pipeline_legacy_entry_point_exposes_delivery_methods():
    """Assert that delivery methods remain available from the legacy class."""

    pipeline_module = importlib.import_module("src.core.pipeline")
    pipeline_class = pipeline_module.StockAnalysisPipeline

    assert pipeline_class.__module__ == "src.core.pipeline"
    assert all(callable(getattr(pipeline_class, name)) for name in EXPECTED_DELIVERY_METHODS)


def test_pipeline_legacy_entry_point_exposes_analysis_methods():
    """Assert that analysis methods remain available from the legacy class."""

    pipeline_module = importlib.import_module("src.core.pipeline")
    pipeline_class = pipeline_module.StockAnalysisPipeline

    assert pipeline_class.__module__ == "src.core.pipeline"
    assert all(callable(getattr(pipeline_class, name)) for name in EXPECTED_ANALYSIS_METHODS)
