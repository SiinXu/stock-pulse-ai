"""Guard the second-stage analysis facade compatibility contract."""

import importlib
from pathlib import Path
import subprocess
import sys
from types import CodeType
import typing

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()


EXPECTED_PUBLIC_EXPORTS = frozenset(
    """
    AnalysisResult Any ChipDistribution DailyMarketContext
    DailyMarketContextService Dict FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT
    List MarketHotspotService MarketStructureService Optional PipelineStageName
    PipelineStageObservation PipelineStageResult ReportType SearchService
    SimpleNamespace StockAnalysisPipeline TrendAnalysisResult Tuple
    apply_daily_market_context_guardrail apply_phase_decision_guardrails
    build_market_phase_context current_diagnostic_snapshot date datetime
    fill_price_position_if_needed format_daily_market_context_prompt_section
    get_effective_trading_date get_market_for_stock get_market_now
    get_placeholder_text get_unknown_text infer_decision_type_from_advice
    is_market_open is_us_stock_code localize_confidence_level
    localize_operation_advice localize_trend_prediction log_safe_exception
    logger logging normalize_chip_structure_availability
    normalize_report_language normalize_stock_code observe_pipeline_stage pd
    populate_decision_action_fields record_llm_run record_llm_run_started
    render_market_phase_summary stabilize_decision_with_structure threading
    time timedelta
    """.split()
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

IMPLEMENTATION_GROUPS = (
    (
        "src.core.stages.analysis_stock",
        "_StockAnalysisStageMixin",
        EXPECTED_ANALYSIS_METHODS[:1],
    ),
    (
        "src.core.stages.analysis_context",
        "_AnalysisContextStageMixin",
        EXPECTED_ANALYSIS_METHODS[1:6],
    ),
    (
        "src.core.stages.analysis_agent",
        "_AgentAnalysisStageMixin",
        EXPECTED_ANALYSIS_METHODS[6:16],
    ),
    (
        "src.core.stages.analysis_results",
        "_AnalysisResultStageMixin",
        EXPECTED_ANALYSIS_METHODS[16:],
    ),
)


def _descriptor_function(descriptor):
    """Return the Python function wrapped by a stage descriptor."""

    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    return descriptor


def _referenced_global_names(code: CodeType):
    """Return global-name candidates from a function and nested code."""

    names = set(code.co_names)
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            names.update(_referenced_global_names(constant))
    return names


def test_analysis_facade_exports_and_method_order_match_pre_split_snapshot():
    """Preserve the analysis module exports and descriptor order."""

    analysis_module = importlib.import_module("src.core.stages.analysis")
    actual_exports = {
        name for name in vars(analysis_module) if not name.startswith("_")
    }

    assert actual_exports == EXPECTED_PUBLIC_EXPORTS
    assert (
        analysis_module._ANALYSIS_STAGE_METHOD_NAMES
        == EXPECTED_ANALYSIS_METHODS
    )
    assert analysis_module._AnalysisStageMixin.__bases__ == (object,)
    assert (
        analysis_module.StockAnalysisPipeline
        is analysis_module._AnalysisStageMixin
    )


def test_analysis_facade_descriptors_preserve_complete_binding_contract():
    """Preserve globals, metadata, source code, and class ownership."""

    analysis_module = importlib.import_module("src.core.stages.analysis")
    facade_class = analysis_module._AnalysisStageMixin
    facade_globals = vars(analysis_module)
    expected_containers = []

    for module_name, class_name, expected_names in IMPLEMENTATION_GROUPS:
        source_module = importlib.import_module(module_name)
        source_container = getattr(source_module, class_name)
        expected_containers.append(source_container)

        actual_names = tuple(
            name
            for name, descriptor in vars(source_container).items()
            if not name.startswith("__")
            and callable(_descriptor_function(descriptor))
        )
        assert actual_names == expected_names
        assert source_module.StockAnalysisPipeline is source_container

        for name in expected_names:
            descriptor = facade_class.__dict__[name]
            source_descriptor = source_container.__dict__[name]
            function = _descriptor_function(descriptor)
            source_function = _descriptor_function(source_descriptor)

            assert descriptor.__class__ is source_descriptor.__class__
            assert function.__globals__ is facade_globals
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
            assert function.__module__ == "src.core.stages.analysis"
            assert function.__name__ == source_function.__name__
            assert (
                function.__qualname__
                == f"_AnalysisStageMixin.{source_function.__name__}"
            )

            source_globals = source_function.__globals__
            for global_name in _referenced_global_names(function.__code__):
                if global_name in source_globals:
                    assert global_name in facade_globals

    assert analysis_module._ANALYSIS_STAGE_CONTAINERS == tuple(
        expected_containers
    )
    lock_function = _descriptor_function(
        facade_class.__dict__["_get_daily_market_context_service_lock"]
    )
    assert (
        lock_function.__globals__[
            "_DAILY_MARKET_CONTEXT_SERVICE_LOCK_INIT_GUARD"
        ]
        is analysis_module._DAILY_MARKET_CONTEXT_SERVICE_LOCK_INIT_GUARD
    )


def test_analysis_facade_patch_intercepts_rebound_method_globals(monkeypatch):
    """Keep representative dependency patches effective at the facade."""

    analysis_module = importlib.import_module("src.core.stages.analysis")
    sentinel = object()
    monkeypatch.setattr(
        analysis_module,
        "populate_decision_action_fields",
        lambda *args, **kwargs: sentinel,
    )

    assert analysis_module._AnalysisStageMixin._refresh_decision_action_for_final_result(
        object(),
        report_type="simple",
        previous_operation_advice=None,
    ) is sentinel


def test_analysis_facade_and_source_type_hints_resolve():
    """Keep runtime type-hint lookup valid through both module layers."""

    analysis_module = importlib.import_module("src.core.stages.analysis")
    facade_class = analysis_module._AnalysisStageMixin

    for module_name, class_name, expected_names in IMPLEMENTATION_GROUPS:
        source_container = getattr(importlib.import_module(module_name), class_name)
        for name in expected_names:
            facade_function = _descriptor_function(
                facade_class.__dict__[name]
            )
            source_function = _descriptor_function(
                source_container.__dict__[name]
            )
            typing.get_type_hints(source_function)
            typing.get_type_hints(facade_function)


def test_analysis_and_pipeline_facades_rebind_after_reload():
    """Rebuild both facade layers from reloaded implementation containers."""

    repository_root = Path(__file__).resolve().parents[1]
    script = """
import importlib
from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()
results = importlib.reload(
    importlib.import_module("src.core.stages.analysis_results")
)
analysis = importlib.reload(
    importlib.import_module("src.core.stages.analysis")
)
assert analysis._AnalysisResultStageMixin is results._AnalysisResultStageMixin
for name in analysis._ANALYSIS_STAGE_METHOD_NAMES:
    descriptor = analysis._AnalysisStageMixin.__dict__[name]
    function = (
        descriptor.__func__
        if isinstance(descriptor, (staticmethod, classmethod))
        else descriptor
    )
    assert function.__globals__ is vars(analysis)

pipeline = importlib.reload(importlib.import_module("src.core.pipeline"))
assert pipeline._ANALYSIS_STAGE_METHOD_NAMES == analysis._ANALYSIS_STAGE_METHOD_NAMES
for name in pipeline._ANALYSIS_STAGE_METHOD_NAMES:
    descriptor = pipeline.StockAnalysisPipeline.__dict__[name]
    function = (
        descriptor.__func__
        if isinstance(descriptor, (staticmethod, classmethod))
        else descriptor
    )
    assert function.__globals__ is vars(pipeline)
    assert function.__module__ == "src.core.pipeline"
    assert function.__qualname__ == f"StockAnalysisPipeline.{name}"
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
