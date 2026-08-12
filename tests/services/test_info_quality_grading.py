# -*- coding: utf-8 -*-
"""Tests for Issue #123 information quality grading and forced conclusions."""

from __future__ import annotations

from types import SimpleNamespace

from src.services.info_quality_grading import (
    apply_info_quality_constraints,
    build_forced_conclusion,
    grade_info_quality,
    map_action_to_forced_stance,
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
    assert result.dashboard["forced_conclusion"]["uncertainty"] is True
    assert "信息质量" in str(result.risk_warning)


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
