from __future__ import annotations

import json
import math
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from src.services.history_comparison_service import (
    BASELINE_MISSING_BASE,
    BASELINE_MISSING_HISTORY,
    BASELINE_MISSING_TARGET,
    BASELINE_OK,
    DIRECTION_CHANGED,
    DIRECTION_UNAVAILABLE,
    DIRECTION_UP,
    _diff_snapshots,
    _extract_comparable_snapshot,
    _finite_number,
    _record_to_signal,
    compare_analyses,
    get_latest_delta,
)


def _record(**overrides: Any) -> SimpleNamespace:
    values = {
        "created_at": datetime(2026, 7, 11, 9, 0),
        "query_id": "q1",
        "code": "600519",
        "sentiment_score": 72,
        "operation_advice": "Hold",
        "trend_prediction": "Bullish",
        "report_type": "stock",
        "report_language": "en",
        "raw_result": "{}",
        "ideal_buy": None,
        "secondary_buy": None,
        "stop_loss": None,
        "take_profit": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _raw_payload(**overrides: Any) -> str:
    payload: Dict[str, Any] = {
        "operation_advice": "Hold",
        "action": "hold",
        "action_label": "Hold",
        "confidence_level": "medium",
        "sentiment_score": 60,
        "key_points": "Steady demand, Valuation elevated",
        "risk_warning": "Macro volatility",
        "data_sources": "tushare, news",
        "dashboard": {
            "intelligence": {
                "risk_alerts": ["Valuation elevated"],
                "positive_catalysts": ["Quarterly update clean"],
            },
            "data_perspective": {
                "trend_status": {
                    "trend_score": 55,
                }
            },
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": 1600.0,
                    "stop_loss": 1550.0,
                    "take_profit": 1700.0,
                }
            },
            "report_strata": {
                "verified_facts": [{"statement": "Close at 1680"}],
                "risks_counter_evidence": ["Elevated PE"],
            },
        },
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_history_signal_uses_score_aligned_display_action() -> None:
    signal = _record_to_signal(_record(), report_language="en")

    assert signal is not None
    assert signal["action"] == "buy"
    assert signal["action_label"] == "Buy"


def test_history_signal_preserves_applied_guardrail() -> None:
    signal = _record_to_signal(
        _record(
            raw_result=(
                '{"action":"hold","dashboard":{"decision_stability":'
                '{"applied":true,"reason":"Wait for confirmation"}}}'
            )
        ),
        report_language="en",
    )

    assert signal is not None
    assert signal["action"] == "hold"
    assert signal["action_label"] == "Hold"


def test_finite_number_rejects_non_finite() -> None:
    assert _finite_number(None) is None
    assert _finite_number(float("nan")) is None
    assert _finite_number(float("inf")) is None
    assert _finite_number(float("-inf")) is None
    assert _finite_number("not-a-number") is None
    assert _finite_number(12.5) == 12.5
    assert _finite_number("12.5") == 12.5


def test_no_baseline_distinct_from_no_change() -> None:
    """Missing history must not look like 'everything unchanged'."""
    db = MagicMock()
    db.get_analysis_history.return_value = []

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        no_baseline = get_latest_delta("600519")

    assert no_baseline.has_baseline is False
    assert no_baseline.baseline_status == BASELINE_MISSING_HISTORY
    assert no_baseline.has_material_changes is False
    assert no_baseline.conclusion_changes == []
    assert no_baseline.score_changes == []

    base_snap = _extract_comparable_snapshot(
        _record(query_id="base", raw_result=_raw_payload())
    )
    target_snap = _extract_comparable_snapshot(
        _record(query_id="target", raw_result=_raw_payload())
    )
    assert base_snap is not None and target_snap is not None
    no_change = _diff_snapshots(base_snap, target_snap)

    assert no_change.has_baseline is True
    assert no_change.baseline_status == BASELINE_OK
    assert no_change.has_material_changes is False
    assert no_change.conclusion_changes == []
    assert no_change.score_changes == []
    assert no_change.evidence_changes == []
    assert no_change.risk_changes == []

    # Explicit contract: the two states are not interchangeable.
    assert (no_baseline.has_baseline, no_baseline.baseline_status) != (
        no_change.has_baseline,
        no_change.baseline_status,
    )


def test_get_latest_delta_single_history_is_no_baseline() -> None:
    db = MagicMock()
    db.get_analysis_history.return_value = [
        _record(query_id="only", raw_result=_raw_payload()),
    ]

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        delta = get_latest_delta("600519")

    assert delta.has_baseline is False
    assert delta.baseline_status == BASELINE_MISSING_HISTORY
    assert delta.target_run_id == "only"
    assert delta.base_run_id is None


def test_compare_analyses_missing_base_or_target() -> None:
    db = MagicMock()

    def _lookup(*, code: str, query_id: Optional[str] = None, **_kwargs: Any) -> List[Any]:
        if query_id == "base":
            return [_record(query_id="base", code=code, raw_result=_raw_payload())]
        return []

    db.get_analysis_history.side_effect = _lookup

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        missing_target = compare_analyses("600519", "base", "missing")
        missing_base = compare_analyses("600519", "missing", "base")

    assert missing_target.has_baseline is False
    assert missing_target.baseline_status == BASELINE_MISSING_TARGET
    assert missing_base.has_baseline is False
    assert missing_base.baseline_status == BASELINE_MISSING_BASE


def test_compare_analyses_detects_dimension_changes() -> None:
    base = _record(
        query_id="run-base",
        sentiment_score=50,
        operation_advice="Hold",
        stop_loss=1500.0,
        take_profit=1700.0,
        ideal_buy=1550.0,
        raw_result=_raw_payload(
            operation_advice="Hold",
            action="hold",
            confidence_level="medium",
            sentiment_score=50,
            key_points="Steady demand",
            risk_warning="Macro volatility",
            data_sources="tushare",
            dashboard={
                "intelligence": {
                    "risk_alerts": ["Valuation elevated"],
                    "positive_catalysts": ["Quarterly update clean"],
                },
                "data_perspective": {"trend_status": {"trend_score": 50}},
                "battle_plan": {
                    "sniper_points": {
                        "ideal_buy": 1550.0,
                        "stop_loss": 1500.0,
                        "take_profit": 1700.0,
                    }
                },
                "report_strata": {
                    "verified_facts": [{"statement": "Close at 1600"}],
                    "risks_counter_evidence": ["Elevated PE"],
                },
            },
        ),
    )
    target = _record(
        query_id="run-target",
        sentiment_score=70,
        operation_advice="Buy",
        stop_loss=1520.0,
        take_profit=1750.0,
        ideal_buy=1580.0,
        raw_result=_raw_payload(
            operation_advice="Buy",
            action="buy",
            action_label="Buy",
            confidence_level="high",
            sentiment_score=70,
            key_points="Steady demand, New product pipeline",
            risk_warning="Macro volatility",
            data_sources="tushare, news",
            dashboard={
                "intelligence": {
                    "risk_alerts": ["Liquidity risk"],
                    "positive_catalysts": [
                        "Quarterly update clean",
                        "Export recovery",
                    ],
                },
                "data_perspective": {"trend_status": {"trend_score": 68}},
                "battle_plan": {
                    "sniper_points": {
                        "ideal_buy": 1580.0,
                        "stop_loss": 1520.0,
                        "take_profit": 1750.0,
                    }
                },
                "report_strata": {
                    "verified_facts": [
                        {"statement": "Close at 1600"},
                        {"statement": "Volume above MA20"},
                    ],
                    "risks_counter_evidence": ["Elevated PE", "Currency headwind"],
                },
            },
        ),
    )

    db = MagicMock()

    def _lookup(*, code: str, query_id: Optional[str] = None, **_kwargs: Any) -> List[Any]:
        if query_id == "run-base":
            return [base]
        if query_id == "run-target":
            return [target]
        return []

    db.get_analysis_history.side_effect = _lookup

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        delta = compare_analyses("600519", "run-base", "run-target")

    assert delta.has_baseline is True
    assert delta.baseline_status == BASELINE_OK
    assert delta.has_material_changes is True
    assert delta.base_run_id == "run-base"
    assert delta.target_run_id == "run-target"

    conclusion_by_field = {c.field: c for c in delta.conclusion_changes}
    assert conclusion_by_field["operation_advice"].direction == DIRECTION_CHANGED
    assert conclusion_by_field["action"].target_value == "buy"
    assert conclusion_by_field["confidence_level"].base_value == "medium"
    assert conclusion_by_field["confidence_level"].target_value == "high"
    assert conclusion_by_field["stop_loss"].delta == 20.0
    assert conclusion_by_field["stop_loss"].direction == DIRECTION_UP
    assert conclusion_by_field["take_profit"].delta == 50.0

    score_by_field = {c.field: c for c in delta.score_changes}
    assert score_by_field["sentiment_score"].delta == 20.0
    assert score_by_field["sentiment_score"].direction == DIRECTION_UP
    assert score_by_field["dimension.trend_score"].base_value == 50.0
    assert score_by_field["dimension.trend_score"].target_value == 68.0
    assert score_by_field["dimension.trend_score"].direction == DIRECTION_UP

    evidence_by_field = {c.field: c for c in delta.evidence_changes}
    assert "New product pipeline" in evidence_by_field["key_points"].added
    assert "news" in evidence_by_field["data_sources"].added
    assert "Export recovery" in evidence_by_field["positive_catalysts"].added
    assert "Volume above MA20" in evidence_by_field["verified_facts"].added

    risk_by_field = {c.field: c for c in delta.risk_changes}
    assert "Liquidity risk" in risk_by_field["risk_alerts"].added
    assert "Valuation elevated" in risk_by_field["risk_alerts"].removed
    assert "Currency headwind" in risk_by_field["risks_counter_evidence"].added


def test_non_finite_numeric_is_not_forged_into_delta() -> None:
    base = _record(
        query_id="b",
        stop_loss=100.0,
        sentiment_score=50,
        raw_result=_raw_payload(
            sentiment_score=50,
            dashboard={
                "intelligence": {"risk_alerts": [], "positive_catalysts": []},
                "data_perspective": {"trend_status": {"trend_score": 40}},
                "battle_plan": {"sniper_points": {"stop_loss": 100.0}},
                "report_strata": {"verified_facts": [], "risks_counter_evidence": []},
            },
        ),
    )
    target = _record(
        query_id="t",
        stop_loss=float("nan"),
        sentiment_score=float("inf"),
        raw_result=_raw_payload(
            sentiment_score=float("inf"),
            dashboard={
                "intelligence": {"risk_alerts": [], "positive_catalysts": []},
                "data_perspective": {
                    "trend_status": {"trend_score": float("-inf")}
                },
                "battle_plan": {"sniper_points": {"stop_loss": float("nan")}},
                "report_strata": {"verified_facts": [], "risks_counter_evidence": []},
            },
        ),
    )

    db = MagicMock()

    def _lookup(*, code: str, query_id: Optional[str] = None, **_kwargs: Any) -> List[Any]:
        if query_id == "b":
            return [base]
        if query_id == "t":
            return [target]
        return []

    db.get_analysis_history.side_effect = _lookup

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        delta = compare_analyses("600519", "b", "t")

    assert delta.has_baseline is True
    by_field = {c.field: c for c in delta.conclusion_changes + delta.score_changes}
    assert by_field["stop_loss"].comparable is False
    assert by_field["stop_loss"].delta is None
    assert by_field["stop_loss"].direction == DIRECTION_UNAVAILABLE
    assert by_field["sentiment_score"].comparable is False
    assert by_field["sentiment_score"].delta is None
    # Non-finite target trend_score must not produce a numeric delta.
    assert by_field["dimension.trend_score"].comparable is False
    assert by_field["dimension.trend_score"].delta is None
    assert by_field["dimension.trend_score"].direction == DIRECTION_UNAVAILABLE
    assert math.isfinite(by_field["stop_loss"].base_value)


def test_get_latest_delta_uses_two_most_recent_runs() -> None:
    older = _record(
        query_id="older",
        created_at=datetime(2026, 7, 10, 9, 0),
        sentiment_score=40,
        raw_result=_raw_payload(sentiment_score=40, operation_advice="Hold", action="hold"),
    )
    newer = _record(
        query_id="newer",
        created_at=datetime(2026, 7, 11, 9, 0),
        sentiment_score=65,
        raw_result=_raw_payload(
            sentiment_score=65,
            operation_advice="Buy",
            action="buy",
            action_label="Buy",
        ),
    )
    db = MagicMock()
    # Storage returns newest first.
    db.get_analysis_history.side_effect = [
        [newer, older],  # get_latest_delta list
        [older],  # compare base lookup
        [newer],  # compare target lookup
    ]

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        delta = get_latest_delta("600519")

    assert delta.has_baseline is True
    assert delta.base_run_id == "older"
    assert delta.target_run_id == "newer"
    score = next(c for c in delta.score_changes if c.field == "sentiment_score")
    assert score.delta == 25.0
    assert score.direction == DIRECTION_UP


def test_analysis_delta_to_dict_shape() -> None:
    base = _record(query_id="a", raw_result=_raw_payload(sentiment_score=10))
    target = _record(
        query_id="b",
        sentiment_score=20,
        raw_result=_raw_payload(sentiment_score=20),
    )
    db = MagicMock()
    db.get_analysis_history.side_effect = lambda **kwargs: (
        [base] if kwargs.get("query_id") == "a" else [target]
    )

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        payload = compare_analyses("600519", "a", "b").to_dict()

    assert set(payload.keys()) >= {
        "has_baseline",
        "conclusion_changes",
        "score_changes",
        "evidence_changes",
        "risk_changes",
        "base_run_id",
        "target_run_id",
    }
    assert payload["has_baseline"] is True
    assert payload["base_run_id"] == "a"
    assert payload["target_run_id"] == "b"
