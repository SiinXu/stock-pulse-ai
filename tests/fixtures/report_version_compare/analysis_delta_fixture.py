# -*- coding: utf-8 -*-
"""Fixture AnalysisDelta payloads for T18 independent tests (T17 contract A)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


def make_analysis_delta(
    *,
    base_record_id: int,
    target_record_id: int,
    has_baseline: bool = True,
    baseline_status: str = "ok",
    baseline_reason: Optional[str] = None,
    conclusion_changes: Optional[List[Mapping[str, Any]]] = None,
    score_changes: Optional[List[Mapping[str, Any]]] = None,
    evidence_changes: Optional[List[Mapping[str, Any]]] = None,
    risk_changes: Optional[List[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a dict matching FILE_OWNERSHIP contract A for ``compare_analyses``."""
    return {
        "has_baseline": has_baseline,
        "baseline_status": baseline_status,
        "baseline_reason": baseline_reason,
        "stock_code": "600519",
        "base_record_id": base_record_id,
        "target_record_id": target_record_id,
        "base_query_id": "shared-query",
        "target_query_id": "shared-query",
        "report_type": "detailed",
        "has_material_changes": bool(
            conclusion_changes or score_changes or evidence_changes or risk_changes
        ),
        "conclusion_changes": list(conclusion_changes or []),
        "score_changes": list(score_changes or []),
        "evidence_changes": list(evidence_changes or []),
        "risk_changes": list(risk_changes or []),
    }


def fixture_compare_analyses_factory(delta: Dict[str, Any]):
    """Return a compare_analyses callable that always returns ``delta``."""

    def _compare(stock_code: str, base_record_id: int, target_record_id: int) -> Dict[str, Any]:
        del stock_code  # fixture ignores stock_code
        payload = dict(delta)
        payload["base_record_id"] = base_record_id
        payload["target_record_id"] = target_record_id
        return payload

    return _compare


CONCLUSION_REVERSAL_DELTA = make_analysis_delta(
    base_record_id=1,
    target_record_id=2,
    has_baseline=True,
    conclusion_changes=[
        {
            "field": "action",
            "base_value": "buy",
            "target_value": "sell",
            "delta": None,
            "direction": "changed",
            "comparable": True,
            "unavailability": None,
        }
    ],
    score_changes=[
        {
            "field": "sentiment_score",
            "base_value": 80,
            "target_value": 25,
            "delta": -55,
            "direction": "down",
            "comparable": True,
            "unavailability": None,
        }
    ],
)

NO_BASELINE_DELTA = make_analysis_delta(
    base_record_id=1,
    target_record_id=2,
    has_baseline=False,
    baseline_status="missing_history",
    baseline_reason="no prior comparable history",
)

MINOR_SCORE_DELTA = make_analysis_delta(
    base_record_id=1,
    target_record_id=2,
    has_baseline=True,
    score_changes=[
        {
            "field": "sentiment_score",
            "base_value": 70,
            "target_value": 72,
            "delta": 2,
            "direction": "up",
            "comparable": True,
            "unavailability": None,
        }
    ],
)
