# -*- coding: utf-8 -*-
"""Tests for Issue #123 information quality grading and forced conclusions."""

from __future__ import annotations

from types import SimpleNamespace

from src.services.info_quality_grading import (
    apply_info_quality_constraints,
    build_forced_conclusion,
    grade_info_quality,
    read_info_quality_feature_flag,
    map_action_to_forced_stance,
    resolve_info_quality,
)


def test_grade_a_from_clean_validation_backed_quality() -> None:
    payload = grade_info_quality(
        {
            "overall_score": 92,
            "level": "good",
            "limitations": [],
            "metadata": {
                "validation_evidence": [
                    {
                        "schema_version": "data_quality_evidence.v1",
                        "data_type": "daily_bars",
                        "severity": "pass",
                        "issues": [],
                    }
                ]
            },
        },
        blocks={
            "quote": {"status": "available"},
            "daily_bars": {"status": "available"},
            "technical": {"status": "available"},
        },
    )
    assert payload["schema_version"] == "info-quality-v1"
    assert payload["grade"] == "A"
    assert payload["dimensions"]["source_reliability"] == "A"
    assert payload["dimensions"]["timeliness"] == "A"
    assert payload["dimensions"]["consistency"] == "A"
    assert payload["evidence_backed"] is True


def test_grade_c_from_stale_and_reject_validation_evidence() -> None:
    payload = grade_info_quality(
        {
            "overall_score": 48,
            "level": "poor",
            "limitations": ["quote: stale", "technical: fetch_failed"],
            "metadata": {
                "validation_evidence": [
                    {
                        "schema_version": "data_quality_evidence.v1",
                        "data_type": "realtime_quote",
                        "severity": "reject",
                        "rejected": True,
                        "issues": [
                            {
                                "code": "dv_quote_price_non_finite",
                                "severity": "reject",
                                "message": "non-finite price",
                            }
                        ],
                    },
                    {
                        "schema_version": "data_quality_evidence.v1",
                        "data_type": "realtime_quote",
                        "severity": "warn",
                        "issues": [
                            {
                                "code": "dv_cross_source_divergence",
                                "severity": "warn",
                                "message": "providers diverged",
                            }
                        ],
                    },
                ]
            },
        },
        blocks={
            "quote": {"status": "stale"},
            "daily_bars": {"status": "available"},
            "technical": {"status": "fetch_failed"},
        },
    )
    assert payload["grade"] == "C"
    assert payload["dimensions"]["source_reliability"] == "C"
    assert payload["dimensions"]["timeliness"] == "C"
    assert payload["dimensions"]["consistency"] in {"B", "C"}


def test_forced_conclusion_maps_actions() -> None:
    assert map_action_to_forced_stance("buy") == "Pass"
    assert map_action_to_forced_stance("sell") == "Fail"
    assert map_action_to_forced_stance("watch") == "Watch"


def test_grade_c_blocks_pass_forced_conclusion() -> None:
    forced = build_forced_conclusion(
        action="buy",
        info_quality={
            "grade": "C",
            "evidence_backed": False,
            "dimensions": {
                "source_reliability": "C",
                "timeliness": "C",
                "consistency": "B",
            },
        },
        language="en",
    )
    assert forced["schema_version"] == "forced-conclusion-v1"
    assert forced["stance"] == "Watch"
    assert forced["raw_stance"] == "Pass"
    assert forced["uncertainty"] is True
    assert "grade_c_pass_downgraded" in forced["constraint_reasons"]
    assert "no_evidence_pass_blocked" in forced["constraint_reasons"]


def test_apply_constraints_downgrades_buy_on_grade_c() -> None:
    result = SimpleNamespace(
        success=True,
        action="buy",
        action_label="Buy",
        operation_advice="买入",
        decision_type="buy",
        confidence_level="高",
        sentiment_score=80,
        analysis_summary="Aggressive buy without clean evidence",
        risk_warning="",
        guardrail_reason="market_phase_non_trading",
        report_language="zh",
        dashboard={},
        analysis_context_pack_overview={
            "data_quality": {
                "overall_score": 40,
                "level": "poor",
                "limitations": ["quote: missing", "technical: fetch_failed"],
                "validation_evidence": [
                    {
                        "schema_version": "data_quality_evidence.v1",
                        "severity": "reject",
                        "rejected": True,
                        "issues": [{"code": "dv_quote_price_missing", "severity": "reject"}],
                    }
                ],
            },
            "blocks": {
                "quote": {"status": "missing"},
                "daily_bars": {"status": "available"},
                "technical": {"status": "fetch_failed"},
            },
        },
    )

    adjustments = apply_info_quality_constraints(
        result,
        analysis_context_pack_overview=result.analysis_context_pack_overview,
        grading_enabled=True,
        forced_conclusion_enabled=True,
        enforce_action_downgrade=True,
        report_language="zh",
    )

    assert "info_quality_grade_c" in adjustments
    assert result.action == "watch"
    assert result.decision_type == "hold"
    assert result.dashboard["info_quality"]["grade"] == "C"
    assert result.dashboard["forced_conclusion"]["stance"] == "Watch"
    assert result.dashboard["forced_conclusion"]["raw_stance"] == "Pass"
    assert result.dashboard["forced_conclusion"]["uncertainty"] is True
    assert "no_evidence_pass_blocked" in result.dashboard["forced_conclusion"]["constraint_reasons"]
    assert "grade_c_pass_downgraded" in result.dashboard["forced_conclusion"]["constraint_reasons"]
    assert "market_phase_non_trading" in result.guardrail_reason
    assert result.confidence_level == "低"
    assert "信息质量" in str(result.risk_warning)

    apply_info_quality_constraints(
        result,
        analysis_context_pack_overview=result.analysis_context_pack_overview,
        grading_enabled=True,
        forced_conclusion_enabled=True,
        enforce_action_downgrade=False,
        report_language="zh",
    )
    assert result.dashboard["forced_conclusion"]["raw_stance"] == "Pass"
    assert "grade_c_pass_downgraded" in result.dashboard["forced_conclusion"]["constraint_reasons"]


def test_disabled_flags_skip_surfaces() -> None:
    result = SimpleNamespace(
        success=True,
        action="buy",
        action_label="Buy",
        operation_advice="Buy",
        decision_type="buy",
        confidence_level="High",
        sentiment_score=80,
        analysis_summary="buy",
        risk_warning="",
        report_language="en",
        dashboard={},
        analysis_context_pack_overview={
            "data_quality": {"overall_score": 40, "level": "poor", "limitations": ["quote: missing"]},
            "blocks": {"quote": {"status": "missing"}},
        },
    )
    adjustments = apply_info_quality_constraints(
        result,
        analysis_context_pack_overview=result.analysis_context_pack_overview,
        grading_enabled=False,
        forced_conclusion_enabled=False,
        enforce_action_downgrade=True,
        report_language="en",
    )
    assert adjustments == []
    assert "info_quality" not in result.dashboard
    assert "forced_conclusion" not in result.dashboard
    assert result.action == "buy"


def test_overview_list_blocks_preserves_grade_a_and_pass() -> None:
    """Regression: public overview emits list-shaped blocks, not a mapping."""

    overview = {
        "data_quality": {
            "overall_score": 92,
            "level": "good",
            "limitations": [],
            "validation_evidence": [
                {
                    "schema_version": "data_quality_evidence.v1",
                    "data_type": "daily_bars",
                    "severity": "pass",
                    "issues": [],
                }
            ],
            "info_quality": {
                "schema_version": "info-quality-v1",
                "grade": "A",
                "dimensions": {
                    "source_reliability": "A",
                    "timeliness": "A",
                    "consistency": "A",
                },
                "evidence_backed": True,
            },
            "info_quality_grade": "A",
        },
        "blocks": [
            {"key": "quote", "status": "available"},
            {"key": "daily_bars", "status": "available"},
            {"key": "technical", "status": "available"},
        ],
    }
    result = SimpleNamespace(
        success=True,
        action="buy",
        action_label="Buy",
        operation_advice="买入",
        decision_type="buy",
        confidence_level="高",
        sentiment_score=80,
        analysis_summary="Buy with clean evidence",
        risk_warning="",
        report_language="zh",
        dashboard={},
        analysis_context_pack_overview=overview,
    )
    adjustments = apply_info_quality_constraints(
        result,
        analysis_context_pack_overview=overview,
        grading_enabled=True,
        forced_conclusion_enabled=True,
        enforce_action_downgrade=True,
        report_language="zh",
    )
    assert result.dashboard["info_quality"]["grade"] == "A"
    assert result.action == "buy"
    assert result.dashboard["forced_conclusion"]["stance"] == "Pass"
    assert "forced_conclusion_pass_blocked" not in adjustments


def test_precomputed_grade_used_when_blocks_absent() -> None:
    overview = {
        "data_quality": {
            "overall_score": 90,
            "level": "good",
            "limitations": [],
            "info_quality_grade": "A",
            "info_quality": {
                "schema_version": "info-quality-v1",
                "grade": "A",
                "dimensions": {
                    "source_reliability": "A",
                    "timeliness": "A",
                    "consistency": "A",
                },
                "evidence_backed": True,
            },
        },
        # no blocks key
    }
    result = SimpleNamespace(
        success=True,
        action="buy",
        action_label="Buy",
        operation_advice="Buy",
        decision_type="buy",
        confidence_level="High",
        sentiment_score=80,
        analysis_summary="buy",
        risk_warning="",
        report_language="en",
        dashboard={},
        analysis_context_pack_overview=overview,
    )
    apply_info_quality_constraints(
        result,
        analysis_context_pack_overview=overview,
        grading_enabled=True,
        forced_conclusion_enabled=True,
        enforce_action_downgrade=True,
        report_language="en",
    )
    assert result.dashboard["info_quality"]["grade"] == "A"
    assert result.action == "buy"
    assert result.dashboard["forced_conclusion"]["stance"] == "Pass"


def test_empty_or_partial_core_evidence_fails_closed() -> None:
    empty = grade_info_quality({})
    partial = grade_info_quality(
        {"overall_score": 99, "level": "good"},
        blocks={"quote": {"status": "available"}},
    )

    assert empty["grade"] == "C"
    assert empty["evidence_backed"] is False
    assert partial["grade"] == "C"
    assert partial["evidence_backed"] is False


def test_malformed_evidence_and_statuses_are_not_coerced_to_clean() -> None:
    payload = grade_info_quality(
        {
            "overall_score": float("nan"),
            "level": "good",
            "validation_evidence": [
                {
                    "schema_version": "data_quality_evidence.v1",
                    "severity": "pass",
                    "rejected": "false",
                    "issues": [],
                }
            ],
        },
        blocks={
            "quote": {"status": "available"},
            "daily_bars": {"status": "available"},
            "technical": {"status": "mystery"},
        },
    )

    assert payload["grade"] == "C"
    assert payload["evidence_backed"] is False
    assert "invalid_validation_records:1" in payload["reasons"]
    assert "technical:invalid" in payload["reasons"]
    assert payload["overall_score"] is None


def test_untrusted_precomputed_grade_requires_complete_typed_schema() -> None:
    payload = resolve_info_quality(
        {
            "overall_score": 99,
            "level": "good",
            "info_quality_grade": "A",
            "info_quality": {
                "schema_version": "attacker-v1",
                "grade": "A",
                "evidence_backed": True,
            },
        }
    )

    assert payload["grade"] == "C"
    assert payload["evidence_backed"] is False


def test_forced_conclusion_without_grading_does_not_fabricate_quality() -> None:
    result = SimpleNamespace(
        success=True,
        action="buy",
        operation_advice="Buy",
        decision_type="buy",
        confidence_level="High",
        sentiment_score=80,
        risk_warning="",
        report_language="en",
        dashboard={
            "info_quality": {"grade": "A"},
            "forced_conclusion": {"stance": "Fail"},
        },
    )

    apply_info_quality_constraints(
        result,
        grading_enabled=False,
        forced_conclusion_enabled=True,
    )

    assert "info_quality" not in result.dashboard
    assert result.dashboard["forced_conclusion"]["stance"] == "Pass"
    assert result.dashboard["forced_conclusion"]["info_quality_grade"] is None
    assert result.dashboard["forced_conclusion"]["evidence_backed"] is None
    assert result.action == "buy"


def test_disabled_features_remove_untrusted_surfaces_without_other_mutation() -> None:
    result = SimpleNamespace(
        success=True,
        action="buy",
        dashboard={
            "info_quality": {"grade": "A"},
            "forced_conclusion": {"stance": "Pass"},
            "core_conclusion": {"one_sentence": "keep"},
        },
    )

    assert apply_info_quality_constraints(
        result,
        grading_enabled=False,
        forced_conclusion_enabled=False,
    ) == []
    assert result.dashboard == {"core_conclusion": {"one_sentence": "keep"}}
    assert result.action == "buy"


def test_failed_result_and_non_boolean_flags_do_not_publish_conclusions() -> None:
    failed = SimpleNamespace(
        success=False,
        dashboard={},
        action="buy",
    )
    assert apply_info_quality_constraints(failed) == []
    assert failed.dashboard == {}

    valid = SimpleNamespace(success=True, dashboard={}, action="buy")
    for kwargs in (
        {"grading_enabled": "false"},
        {"forced_conclusion_enabled": 1},
        {"enforce_action_downgrade": "true"},
    ):
        try:
            apply_info_quality_constraints(valid, **kwargs)
        except TypeError:
            pass
        else:
            raise AssertionError(f"coercive flags must be rejected: {kwargs}")


def test_non_finite_score_and_long_metadata_are_bounded_on_downgrade() -> None:
    result = SimpleNamespace(
        success=True,
        action="buy",
        operation_advice="Buy",
        decision_type="buy",
        confidence_level="High" * 500,
        sentiment_score=float("inf"),
        risk_warning="risk" * 500,
        guardrail_reason="existing",
        report_language="en",
        dashboard={},
    )
    overview = {
        "data_quality": {"overall_score": 20, "level": "poor"},
        "blocks": [
            {"key": "quote", "status": "missing"},
            {"key": "daily_bars", "status": "available"},
            {"key": "technical", "status": "available"},
        ],
    }

    apply_info_quality_constraints(
        result,
        analysis_context_pack_overview=overview,
    )

    forced = result.dashboard["forced_conclusion"]
    assert result.sentiment_score == 50
    assert len(forced["confidence_level"]) <= 320
    assert all(len(item) <= 320 for item in forced["main_risks"])
    assert forced["summary"].startswith("Forced conclusion: Watch")


def test_real_pipeline_entry_applies_fail_closed_grade_c_constraint() -> None:
    from src.core.stages.analysis_results import _AnalysisResultStageMixin

    owner = SimpleNamespace(
        config=SimpleNamespace(
            info_quality_grading_enabled=True,
            forced_conclusion_enabled=True,
            report_language="en",
        )
    )
    result = SimpleNamespace(
        success=True,
        action="buy",
        operation_advice="Buy",
        decision_type="buy",
        confidence_level="High",
        sentiment_score=82,
        risk_warning="",
        report_language="en",
        dashboard={},
    )

    adjustments = _AnalysisResultStageMixin._apply_info_quality_constraints(
        owner,
        result,
        analysis_context_pack_overview={},
    )

    assert "forced_conclusion_pass_blocked" in adjustments
    assert result.action == "watch"
    assert result.dashboard["info_quality"]["grade"] == "C"


def test_feature_flag_reader_defaults_only_when_attribute_is_absent() -> None:
    class DynamicConfig:
        def __getattr__(self, _name: str) -> object:
            return object()

    assert (
        read_info_quality_feature_flag(
            DynamicConfig(),
            "info_quality_grading_enabled",
        )
        is True
    )
    assert (
        read_info_quality_feature_flag(
            SimpleNamespace(forced_conclusion_enabled=False),
            "forced_conclusion_enabled",
        )
        is False
    )


def test_feature_flag_reader_rejects_explicit_non_boolean_value() -> None:
    try:
        read_info_quality_feature_flag(
            SimpleNamespace(info_quality_grading_enabled="false"),
            "info_quality_grading_enabled",
        )
    except TypeError:
        pass
    else:
        raise AssertionError("explicit non-boolean config must be rejected")
