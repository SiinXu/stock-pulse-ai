"""Guard the compatibility surface of ``src.core.pipeline``."""

import importlib
from types import CodeType

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

EXPECTED_PERSISTENCE_METHODS = (
    "_build_context_snapshot",
    "_persist_analysis_history_stage",
    "_extract_decision_signal_after_history_save",
    "_build_notification_run_snapshot",
    "_activate_delivery_diagnostic_context",
    "_merge_delivery_diagnostic_snapshot",
    "_refresh_saved_diagnostic_snapshot",
    "_load_persisted_intelligence_context",
    "_build_legacy_analysis_artifacts",
    "_build_agent_analysis_artifacts",
    "_build_analysis_context_pack_outputs",
    "_without_runtime_prompt_context",
    "_without_market_phase_context",
    "_safe_to_dict",
    "_build_query_context",
)

EXPECTED_ORCHESTRATION_METHODS = (
    "_emit_progress",
    "_get_pipeline_stage_runner",
    "_run_pipeline_stage",
    "_finish_pipeline_stage",
    "_record_pipeline_stage_result",
    "fetch_and_save_stock_data",
    "_resolve_resume_target_date",
    "_resolve_query_source",
    "process_single_stock",
    "_process_single_stock_for_batch",
    "run",
)


def _referenced_global_names(code: CodeType):
    """Return global-name candidates from a function and its nested code."""

    names = set(code.co_names)
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            names.update(_referenced_global_names(constant))
    return names


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
    assert all(
        callable(getattr(pipeline_class, name))
        for name in EXPECTED_DELIVERY_METHODS
    )


def test_pipeline_legacy_entry_point_exposes_analysis_methods():
    """Assert that analysis methods remain available from the legacy class."""

    pipeline_module = importlib.import_module("src.core.pipeline")
    pipeline_class = pipeline_module.StockAnalysisPipeline

    assert pipeline_class.__module__ == "src.core.pipeline"
    assert all(callable(getattr(pipeline_class, name)) for name in EXPECTED_ANALYSIS_METHODS)


def test_pipeline_legacy_entry_point_exposes_remaining_stage_methods():
    """Assert that persistence and orchestration remain on the legacy class."""

    pipeline_module = importlib.import_module("src.core.pipeline")
    pipeline_class = pipeline_module.StockAnalysisPipeline
    expected_methods = EXPECTED_PERSISTENCE_METHODS + EXPECTED_ORCHESTRATION_METHODS

    assert pipeline_class.__bases__ == (object,)
    assert all(callable(getattr(pipeline_class, name)) for name in expected_methods)


def test_pipeline_extracted_descriptors_preserve_facade_contract():
    """Assert that every stage descriptor retains its legacy facade contract."""

    pipeline_module = importlib.import_module("src.core.pipeline")
    pipeline_class = pipeline_module.StockAnalysisPipeline
    pipeline_globals = vars(pipeline_module)
    stage_groups = (
        (
            "_ANALYSIS_STAGE_METHOD_NAMES",
            "_AnalysisStageMixin",
            EXPECTED_ANALYSIS_METHODS,
        ),
        (
            "_DELIVERY_STAGE_METHOD_NAMES",
            "_DeliveryStageMixin",
            EXPECTED_DELIVERY_METHODS,
        ),
        (
            "_PERSISTENCE_STAGE_METHOD_NAMES",
            "_PersistenceStageMixin",
            EXPECTED_PERSISTENCE_METHODS,
        ),
        (
            "_ORCHESTRATION_STAGE_METHOD_NAMES",
            "_OrchestrationStageMixin",
            EXPECTED_ORCHESTRATION_METHODS,
        ),
    )

    for names_attribute, container_attribute, expected_names in stage_groups:
        assert getattr(pipeline_module, names_attribute) == expected_names
        source_container = getattr(pipeline_module, container_attribute)
        for name in expected_names:
            descriptor = pipeline_class.__dict__[name]
            source_descriptor = source_container.__dict__[name]
            assert descriptor.__class__ is source_descriptor.__class__
            function = (
                descriptor.__func__
                if isinstance(descriptor, (staticmethod, classmethod))
                else descriptor
            )
            source_function = (
                source_descriptor.__func__
                if isinstance(source_descriptor, (staticmethod, classmethod))
                else source_descriptor
            )
            assert function.__globals__ is pipeline_globals
            assert function.__code__ is source_function.__code__
            assert function.__defaults__ == source_function.__defaults__
            assert function.__kwdefaults__ == source_function.__kwdefaults__
            assert function.__annotations__ == source_function.__annotations__
            assert function.__closure__ == source_function.__closure__
            assert function.__dict__ == source_function.__dict__
            assert function.__doc__ == source_function.__doc__
            assert getattr(function, "__type_params__", ()) == getattr(
                source_function,
                "__type_params__",
                (),
            )
            assert function.__module__ == "src.core.pipeline"
            assert function.__name__ == source_function.__name__
            assert (
                function.__qualname__
                == f"StockAnalysisPipeline.{source_function.__name__}"
            )
            source_globals = source_function.__globals__
            for global_name in _referenced_global_names(function.__code__):
                if global_name in source_globals:
                    assert global_name in pipeline_globals

    assert (
        pipeline_class.__dict__["_without_market_phase_context"]
        is pipeline_class.__dict__["_without_runtime_prompt_context"]
    )
    assert (
        pipeline_module._SINGLE_STOCK_NOTIFY_LOCK_INIT_GUARD
        is pipeline_module._DeliveryStageMixin._send_single_stock_notification.__globals__[
            "_SINGLE_STOCK_NOTIFY_LOCK_INIT_GUARD"
        ]
    )


def test_pipeline_analysis_methods_resolve_legacy_facade_globals(monkeypatch):
    """Assert that every extracted method retains legacy global lookup semantics."""

    pipeline_module = importlib.import_module("src.core.pipeline")
    pipeline_class = pipeline_module.StockAnalysisPipeline
    pipeline_globals = vars(pipeline_module)

    assert pipeline_module._ANALYSIS_STAGE_METHOD_NAMES == EXPECTED_ANALYSIS_METHODS
    for name in EXPECTED_ANALYSIS_METHODS:
        descriptor = pipeline_class.__dict__[name]
        function = (
            descriptor.__func__
            if isinstance(descriptor, (staticmethod, classmethod))
            else descriptor
        )
        assert function.__globals__ is pipeline_globals
        assert function.__module__ == "src.core.pipeline"
        assert function.__qualname__ == f"StockAnalysisPipeline.{name}"

    sentinel = object()
    monkeypatch.setattr(
        pipeline_module,
        "populate_decision_action_fields",
        lambda *args, **kwargs: sentinel,
    )

    assert pipeline_class._refresh_decision_action_for_final_result(
        object(),
        report_type="simple",
        previous_operation_advice=None,
    ) is sentinel
