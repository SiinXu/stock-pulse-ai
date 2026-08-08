# -*- coding: utf-8 -*-
"""Fixture AnalysisDelta payloads for T18 independent tests (T17 contract A)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def make_analysis_delta(
    *,
    base_run_id: str,
    target_run_id: str,
    has_baseline: bool = True,
    conclusion_changes: Optional[List[Any]] = None,
    score_changes: Optional[List[Any]] = None,
    evidence_changes: Optional[List[Any]] = None,
    risk_changes: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Build a dict matching FILE_OWNERSHIP contract A for ``compare_analyses``."""
    return {
        "has_baseline": has_baseline,
        "conclusion_changes": list(conclusion_changes or []),
        "score_changes": list(score_changes or []),
        "evidence_changes": list(evidence_changes or []),
        "risk_changes": list(risk_changes or []),
        "base_run_id": str(base_run_id),
        "target_run_id": str(target_run_id),
    }


def fixture_compare_analyses_factory(delta: Dict[str, Any]):
    """Return a compare_analyses callable that always returns ``delta``."""

    def _compare(stock_code: str, base_run_id: str, target_run_id: str) -> Dict[str, Any]:
        del stock_code  # fixture ignores stock_code
        payload = dict(delta)
        payload["base_run_id"] = str(base_run_id)
        payload["target_run_id"] = str(target_run_id)
        return payload

    return _compare


CONCLUSION_REVERSAL_DELTA = make_analysis_delta(
    base_run_id="1",
    target_run_id="2",
    has_baseline=True,
    conclusion_changes=[
        {
            "field": "action",
            "base": "buy",
            "target": "sell",
            "severity": "major",
        }
    ],
    score_changes=[{"field": "sentiment_score", "base": 80, "target": 25}],
)

NO_BASELINE_DELTA = make_analysis_delta(
    base_run_id="1",
    target_run_id="2",
    has_baseline=False,
)

MINOR_SCORE_DELTA = make_analysis_delta(
    base_run_id="1",
    target_run_id="2",
    has_baseline=True,
    score_changes=[{"field": "sentiment_score", "base": 70, "target": 72}],
)
