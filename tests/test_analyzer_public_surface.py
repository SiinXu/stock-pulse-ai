"""Guard the compatibility surface of :mod:`src.analyzer`."""

import importlib
import subprocess
import sys
import textwrap
from types import CodeType, FunctionType
from typing import get_type_hints


EXPECTED_PUBLIC_EXPORTS = frozenset(
    """
    AnalysisReportSchema AnalysisResult Any CANONICAL_DECISION_SCALE_PROMPT_ZH
    CORE_TRADING_SKILL_POLICY_ZH Callable Config Dict GeminiAnalyzer GenerationBackend
    GenerationError GenerationErrorCode HERMES_CHANNEL_NAME LITELLM_BACKEND_ID
    LOCAL_CLI_GENERATION_BACKEND_IDS List Optional Router STOCK_NAME_MAP Tuple
    apply_litellm_generation_params apply_placeholder_fill apply_prompt_cache_hints
    attach_legacy_message_stability_audit attach_message_hmacs build_action_fields
    build_hermes_redaction_values build_provider_cache_route_context
    call_litellm_with_param_recovery canonicalize_hermes_model_ref
    check_content_integrity create_generation_backend dataclass detect_market
    exception_chain_redaction_values extra_litellm_params extract_usage_payload
    fill_chip_structure_if_needed fill_price_position_if_needed
    filter_non_hermes_deployments filter_prompt_cache_telemetry
    format_daily_market_context_prompt_section format_market_phase_prompt_section
    format_market_structure_prompt_section get_analyzer get_api_keys_for_model
    get_chip_unavailable_text get_config get_configured_llm_models get_market_guidelines
    get_market_role get_no_data_text get_placeholder_text get_signal_level
    get_stock_name_multi_source get_thinking_extra_body get_unknown_text
    hermes_blocked_route_candidates infer_decision_type_from_advice
    is_chip_placeholder_value is_masked_secret_placeholder json litellm
    localize_chip_health localize_confidence_level localize_operation_advice
    localize_trend_prediction log_safe_exception logger logging math
    normalize_chip_structure_availability normalize_litellm_usage
    normalize_report_language normalize_report_signal_attribution
    open_hermes_no_proxy_client persist_llm_usage populate_decision_action_fields re
    redact_diagnostic_text register_fallback_model_pricing repair_json
    resolve_fallback_litellm_wire_models resolve_generation_backend_id
    resolve_generation_fallback_backend_id resolve_news_window_days
    resolved_model_provider_identity route_deployment_origins route_has_hermes
    sanitize_hermes_error_text sanitize_shared_diagnostic_text score_band_metadata
    should_persist_usage_telemetry stabilize_decision_with_structure
    strip_leading_think_wrapper time
    """.split()
)

EXPECTED_PRIVATE_NAMES = frozenset(
    """
    _AllModelsFailedError _BEARISH_TREND_HINTS _BULLISH_TREND_HINTS
    _CAPITAL_FLOW_UNAVAILABLE_STATUS _CHIP_KEYS _LiteLLMStreamError
    _NEGATION_BREAK_CHARS _NEGATION_LOOKBACK_CHARS _NEGATION_MAX_GAP_CHARS
    _NEGATION_SCOPE_BREAK_TOKENS _NEGATION_TOKENS _PRICE_POS_KEYS
    _RISK_WARNING_PLACEHOLDER_TEXTS _SINGLE_CHAR_NEGATION_GAP_PREFIXES
    _STRUCTURAL_RISK_PHRASE_HINTS _WEAK_BEARISH_TREND_HINTS _WEAK_BULLISH_TREND_HINTS
    _apply_hold_watch_dashboard _as_dict_for_decision_guard
    _bound_hold_watch_sentiment_score _build_chip_structure_from_data _capital_flow_bias
    _capital_flow_bias_with_status _capital_flow_status_for_stability
    _coerce_chip_metric _coerce_numeric_value _contains_trend_hint _derive_chip_health
    _downgrade_buy_without_capital_flow _downgrade_to_structural_hold
    _filter_conflicting_trend_items _first_list_value _first_numeric_value
    _has_meaningful_chip_data _has_structural_risk_alert _infer_trend_direction
    _is_meaningful_text _is_significant_structural_risk _is_value_placeholder
    _legacy_audit_marker_specs _legacy_market_group _localized_text
    _mark_chip_structure_unavailable _normalize_prompt_reason_items
    _normalize_risk_warning_values _phase_aware_quote_labels
    _record_decision_score_calibration _safe_float _sanitize_trend_analysis_for_prompt
    _set_decision_stability_unavailable _set_structural_hold_wording
    _should_hide_regular_session_ohlc _sync_stability_dashboard_fields
    _today_has_realtime_overlay _today_looks_complete_daily_bar
    """.split()
)

EXPECTED_RESULT_FUNCTIONS = (
    "_localized_text",
    "_normalize_risk_warning_values",
    "check_content_integrity",
    "apply_placeholder_fill",
    "_is_value_placeholder",
    "_is_meaningful_text",
    "_safe_float",
    "_coerce_chip_metric",
    "_normalize_prompt_reason_items",
    "_contains_trend_hint",
    "_infer_trend_direction",
    "_filter_conflicting_trend_items",
    "_sanitize_trend_analysis_for_prompt",
    "_derive_chip_health",
    "_build_chip_structure_from_data",
    "_has_meaningful_chip_data",
    "_mark_chip_structure_unavailable",
    "normalize_chip_structure_availability",
    "fill_chip_structure_if_needed",
    "fill_price_position_if_needed",
    "stabilize_decision_with_structure",
    "_has_structural_risk_alert",
    "_is_significant_structural_risk",
    "_sync_stability_dashboard_fields",
    "_as_dict_for_decision_guard",
    "_first_list_value",
    "_coerce_numeric_value",
    "_first_numeric_value",
    "_capital_flow_bias",
    "_capital_flow_bias_with_status",
    "_capital_flow_status_for_stability",
    "_set_decision_stability_unavailable",
    "_record_decision_score_calibration",
    "_bound_hold_watch_sentiment_score",
    "_apply_hold_watch_dashboard",
    "_downgrade_buy_without_capital_flow",
    "_downgrade_to_structural_hold",
    "_set_structural_hold_wording",
    "get_stock_name_multi_source",
)

EXPECTED_RESULT_CONSTANTS = (
    "_CHIP_KEYS",
    "_RISK_WARNING_PLACEHOLDER_TEXTS",
    "_STRUCTURAL_RISK_PHRASE_HINTS",
    "_CAPITAL_FLOW_UNAVAILABLE_STATUS",
    "_BULLISH_TREND_HINTS",
    "_WEAK_BULLISH_TREND_HINTS",
    "_BEARISH_TREND_HINTS",
    "_WEAK_BEARISH_TREND_HINTS",
    "_NEGATION_TOKENS",
    "_NEGATION_BREAK_CHARS",
    "_NEGATION_LOOKBACK_CHARS",
    "_NEGATION_MAX_GAP_CHARS",
    "_NEGATION_SCOPE_BREAK_TOKENS",
    "_SINGLE_CHAR_NEGATION_GAP_PREFIXES",
    "_PRICE_POS_KEYS",
)

EXPECTED_RESULT_ANNOTATIONS = (
    "_CHIP_KEYS",
    "_BULLISH_TREND_HINTS",
    "_WEAK_BULLISH_TREND_HINTS",
    "_BEARISH_TREND_HINTS",
    "_WEAK_BEARISH_TREND_HINTS",
    "_NEGATION_TOKENS",
    "_NEGATION_BREAK_CHARS",
    "_NEGATION_SCOPE_BREAK_TOKENS",
    "_SINGLE_CHAR_NEGATION_GAP_PREFIXES",
)


def _referenced_global_names(code: CodeType):
    """Return global-name candidates from a function and nested code."""

    names = set(code.co_names)
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            names.update(_referenced_global_names(constant))
    return names


def test_analyzer_facade_preserves_pre_split_names():
    """Keep the complete legacy public and single-underscore surfaces stable."""

    analyzer = importlib.import_module("src.analyzer")

    assert {
        name for name in vars(analyzer) if not name.startswith("_")
    } == EXPECTED_PUBLIC_EXPORTS
    assert {
        name
        for name in vars(analyzer)
        if name.startswith("_") and not name.startswith("__")
    } == EXPECTED_PRIVATE_NAMES


def test_analysis_result_remains_defined_by_legacy_facade():
    """Preserve dataclass identity, reflection, and import metadata."""

    analyzer = importlib.import_module("src.analyzer")

    assert analyzer.AnalysisResult.__module__ == "src.analyzer"
    assert analyzer.AnalysisResult.__qualname__ == "AnalysisResult"
    assert analyzer.AnalysisResult.__bases__ == (object,)


def test_result_processing_functions_preserve_facade_contract():
    """Bind every moved helper to the complete legacy facade globals."""

    analyzer = importlib.import_module("src.analyzer")
    source = importlib.import_module("src.analyzer_parts.result_processing")
    facade_globals = vars(analyzer)

    for name in EXPECTED_RESULT_FUNCTIONS:
        function = facade_globals[name]
        source_function = vars(source)[name]
        assert isinstance(function, FunctionType)
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
        assert function.__module__ == "src.analyzer"
        assert function.__name__ == name
        assert function.__qualname__ == name
        source_globals = source_function.__globals__
        for global_name in _referenced_global_names(function.__code__):
            if global_name in source_globals:
                assert global_name in facade_globals


def test_result_processing_constants_preserve_identity():
    """Expose the exact constant objects used by the moved helpers."""

    analyzer = importlib.import_module("src.analyzer")
    source = importlib.import_module("src.analyzer_parts.result_processing")

    for name in EXPECTED_RESULT_CONSTANTS:
        assert vars(analyzer)[name] is vars(source)[name]


def test_result_processing_annotations_preserve_reflection():
    """Keep moved module annotations visible from the legacy facade."""

    analyzer = importlib.import_module("src.analyzer")
    source = importlib.import_module("src.analyzer_parts.result_processing")

    assert tuple(analyzer.__annotations__) == EXPECTED_RESULT_ANNOTATIONS
    assert analyzer.__annotations__ == source.__annotations__
    assert get_type_hints(analyzer) == get_type_hints(source)


def test_result_helpers_resolve_legacy_facade_patches(monkeypatch):
    """Keep patch targets under :mod:`src.analyzer` behaviorally effective."""

    analyzer = importlib.import_module("src.analyzer")
    sentinel = object()
    monkeypatch.setattr(analyzer, "is_chip_placeholder_value", lambda _value: sentinel)

    assert analyzer._is_value_placeholder("raw") is sentinel


def test_result_processing_constants_restore_on_facade_reload():
    """Recreate moved constants and helper bindings when reloading the facade."""

    probe = textwrap.dedent(
        f"""
        import importlib
        from typing import get_type_hints

        constant_names = {EXPECTED_RESULT_CONSTANTS!r}
        annotation_names = {EXPECTED_RESULT_ANNOTATIONS!r}
        analyzer = importlib.import_module("src.analyzer")
        source = importlib.import_module("src.analyzer_parts.result_processing")
        expected_values = {{}}
        for name in constant_names:
            value = vars(source)[name]
            expected_values[name] = value.copy() if isinstance(value, set) else value

        for name in constant_names:
            setattr(analyzer, name, object())
        for name in annotation_names:
            analyzer.__annotations__[name] = object()

        analyzer = importlib.reload(analyzer)
        source = importlib.import_module("src.analyzer_parts.result_processing")
        for name, expected_value in expected_values.items():
            assert vars(analyzer)[name] is vars(source)[name]
            assert vars(analyzer)[name] == expected_value
        assert tuple(analyzer.__annotations__) == annotation_names
        assert analyzer.__annotations__ == source.__annotations__
        assert get_type_hints(analyzer) == get_type_hints(source)

        for name in constant_names:
            value = vars(analyzer)[name]
            if isinstance(value, set):
                value.add("__analyzer_reload_mutation__")

        analyzer = importlib.reload(analyzer)
        source = importlib.import_module("src.analyzer_parts.result_processing")
        for name, expected_value in expected_values.items():
            assert vars(analyzer)[name] is vars(source)[name]
            assert vars(analyzer)[name] == expected_value

        helper_marker = "__analyzer_facade_helper__"
        analyzer._RISK_WARNING_PLACEHOLDER_TEXTS = {{helper_marker}}
        assert analyzer._is_meaningful_text(helper_marker) is False
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
