# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for valuation report/prompt projection (issue #238 remaining scope)."""

from __future__ import annotations

from src.analyzer import AnalysisResult
from src.services.report_renderer import render
from src.services.valuation_projection import (
    extract_valuation_payload,
    format_valuation_prompt_block,
    project_valuation_for_report,
)
from src.services.valuation_service import VALUATION_DISCLAIMER, VALUATION_SCHEMA_VERSION


def _sample_estimate() -> dict:
    return {
        "schema_version": VALUATION_SCHEMA_VERSION,
        "status": "ok",
        "stock_code": "AAPL",
        "dcf": {
            "status": "ok",
            "equity_value": 1446.21,
            "enterprise_value": 1446.21,
            "intrinsic_value_per_share": 14.46,
            "assumptions": {
                "base_fcf": 100.0,
                "cash_flow_source": "operating_cash_flow",
                "growth_rate": 0.05,
                "discount_rate": 0.10,
                "terminal_growth_rate": 0.02,
                "projection_years": 5,
                "growth_source": "caller_override",
            },
            "sensitivity": {
                "rows": [{"growth_rate": 0.05, "discount_rate": 0.10, "equity_value": 1446.21}],
                "equity_value_low": 1200.0,
                "equity_value_mid": 1446.21,
                "equity_value_high": 1700.0,
            },
            "market": {"current_price": 18.0, "upside_vs_price_pct": -19.67},
        },
        "relative": {
            "status": "ok",
            "target": {"pe_ratio": 18.0, "pb_ratio": 3.0, "ev_ebitda": 12.0},
            "implied_prices": {"pe_based": 15.0, "pb_based": 16.0, "ev_ebitda_equity_value": 900.0},
            "premium_discount": {"pe_vs_peers_pct": 10.0},
            "ev_ebitda": {"status": "ok", "target_multiple": 12.0, "peer_median": 10.0},
        },
        "disclaimer": VALUATION_DISCLAIMER,
    }


def test_project_valuation_missing_is_none() -> None:
    assert project_valuation_for_report(None) is None
    assert project_valuation_for_report({}) is None
    assert format_valuation_prompt_block(None) == ""
    assert format_valuation_prompt_block({}) == ""


def test_project_valuation_for_report_includes_assumptions_and_sensitivity() -> None:
    projection = project_valuation_for_report(_sample_estimate(), language="en")
    assert projection is not None
    assert projection["present"] is True
    assert projection["dcf"]["equity_value"] == 1446.21
    assert projection["dcf"]["assumptions"]["growth_rate"] == 0.05
    assert projection["dcf"]["sensitivity"]["equity_value_low"] == 1200.0
    assert projection["relative"]["ev_ebitda"] == 12.0
    prompt = format_valuation_prompt_block(_sample_estimate())
    assert "growth=0.05" in prompt


def test_extract_valuation_from_dashboard() -> None:
    payload = _sample_estimate()
    result = AnalysisResult(
        code="AAPL", name="Apple", trend_prediction="up", sentiment_score=60,
        operation_advice="Hold", analysis_summary="ok", decision_type="hold",
        dashboard={"valuation": payload}, report_language="en",
    )
    assert extract_valuation_payload(result) is payload


def test_render_markdown_omits_valuation_when_missing() -> None:
    result = AnalysisResult(
        code="600519", name="贵州茅台", trend_prediction="看多", sentiment_score=72,
        operation_advice="持有", analysis_summary="稳健", decision_type="hold",
        dashboard={"core_conclusion": {"one_sentence": "持有观望"}}, report_language="zh",
    )
    out = render("markdown", [result], summary_only=False)
    assert out is not None
    assert "估值估计" not in out
    assert "决策仪表盘" in out


def test_render_markdown_includes_valuation_when_present() -> None:
    payload = _sample_estimate()
    result = AnalysisResult(
        code="AAPL", name="Apple", trend_prediction="up", sentiment_score=60,
        operation_advice="Hold", analysis_summary="ok", decision_type="hold",
        dashboard={"core_conclusion": {"one_sentence": "hold"}, "valuation": payload},
        report_language="en",
    )
    out = render("markdown", [result], summary_only=False)
    assert out is not None
    assert "Valuation Estimate" in out
    assert "Key Assumptions" in out
    assert "0.05" in out
    assert "Sensitivity Range" in out


def test_render_markdown_valuation_via_extra_context() -> None:
    payload = _sample_estimate()
    result = AnalysisResult(
        code="AAPL", name="Apple", trend_prediction="up", sentiment_score=60,
        operation_advice="Hold", analysis_summary="ok", decision_type="hold",
        dashboard={"core_conclusion": {"one_sentence": "hold"}}, report_language="en",
    )
    out = render("markdown", [result], summary_only=False, extra_context={"valuation_by_code": {"AAPL": payload}})
    assert out is not None
    assert "Valuation Estimate" in out
