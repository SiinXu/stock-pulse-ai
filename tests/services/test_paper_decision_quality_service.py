# -*- coding: utf-8 -*-
"""Process-quality scores for paper trades (Issue #1134).

Acceptance: two fixtures with similar PnL but different discipline get different
process scores. Scores never use return fields.
"""

from __future__ import annotations

from src.services.paper_decision_quality_service import (
    FORMULA_VERSION,
    SCORE_KIND,
    score_paper_decision_context,
)

# Shared PnL so fixtures prove process ≠ return evaluation.
_SAME_PNL = {
    "realized_pnl_pct": 5.0,
    "return_pct": 5.0,
    "outcome": "hit",
    "win_rate": 1.0,
}


def _disciplined_buy() -> dict:
    return {
        "side": "buy",
        "symbol": "600519",
        "trade_date": "2024-06-03",
        "position_weight_pct": 12.0,
        "concentration_alert_pct": 35.0,
        **_SAME_PNL,
        "linked_signal": {
            "id": 101,
            "action": "buy",
            "confidence": 0.82,
            "invalidation": "Close below 95 for two sessions",
            "stop_loss": 95.0,
            "reason": "Trend and volume confirm a controlled entry.",
            "risk_summary": "Gap risk if earnings surprise.",
            "plan_quality": "complete",
            "source_type": "analysis",
            "data_quality_level": "high",
            "evidence": [{"id": "e1"}],
        },
    }


def _undisciplined_buy() -> dict:
    return {
        "side": "buy",
        "symbol": "600519",
        "trade_date": "2024-06-03",
        "position_weight_pct": 55.0,
        "concentration_alert_pct": 35.0,
        **_SAME_PNL,
        # No linked signal: no analysis support, unverifiable risk gate, oversized.
    }


def test_similar_pnl_different_discipline_get_different_scores() -> None:
    good = score_paper_decision_context(_disciplined_buy())
    bad = score_paper_decision_context(_undisciplined_buy())

    assert good["score_kind"] == SCORE_KIND == "process"
    assert bad["score_kind"] == "process"
    assert good["formula_version"] == FORMULA_VERSION
    assert good["process_score"] > bad["process_score"]
    assert good["process_score"] >= 80.0
    assert bad["process_score"] <= 40.0

    # PnL fields must be recorded as ignored, not consumed.
    assert "realized_pnl_pct" in good["evidence"]["ignored_return_fields"]
    assert "return_pct" in good["evidence"]["ignored_return_fields"]
    assert "realized_pnl_pct" in bad["evidence"]["ignored_return_fields"]


def test_reasons_are_human_readable_and_traceable() -> None:
    good = score_paper_decision_context(_disciplined_buy())
    bad = score_paper_decision_context(_undisciplined_buy())

    assert good["reasons"]
    assert all(item["message"] for item in good["reasons"])
    assert all(item["code"] for item in good["reasons"])
    assert any(item["code"] == "signal_linked" for item in good["reasons"])
    assert any(item["code"] == "invalidation_or_stop_present" for item in good["reasons"])

    assert any(item["code"] == "no_analysis_support" for item in bad["reasons"])
    assert any(item["code"] == "risk_gate_unverifiable" for item in bad["reasons"])
    assert "process" in good["disclaimer"].lower()
    assert "not a return" in good["disclaimer"].lower() or "not a return" in good["disclaimer"]


def test_trade_against_watch_signal_penalizes_risk_gate() -> None:
    context = _disciplined_buy()
    context["linked_signal"] = {
        **context["linked_signal"],
        "action": "watch",
        "confidence": 0.4,
    }
    scored = score_paper_decision_context(context)
    risk = scored["dimensions"]["risk_gate_compliance"]
    assert risk["score"] < 80.0
    assert any(
        reason["code"] == "trade_against_risk_gate" for reason in risk["reasons"]
    )


def test_poor_data_quality_large_size_penalizes_position_discipline() -> None:
    context = _disciplined_buy()
    context["position_weight_pct"] = 40.0
    context["linked_signal"] = {
        **context["linked_signal"],
        "data_quality_level": "poor",
    }
    scored = score_paper_decision_context(context)
    position = scored["dimensions"]["position_discipline"]
    assert position["score"] < 70.0
    assert any(
        reason["code"] == "size_not_reduced_for_gaps" for reason in position["reasons"]
    )


def test_score_ignores_outcome_fields_even_when_only_difference() -> None:
    """Identical process inputs with opposite fabricated PnL yield the same score."""
    base = _disciplined_buy()
    win = {**base, "realized_pnl_pct": 20.0, "outcome": "hit"}
    lose = {**base, "realized_pnl_pct": -20.0, "outcome": "miss"}
    assert (
        score_paper_decision_context(win)["process_score"]
        == score_paper_decision_context(lose)["process_score"]
    )
