from __future__ import annotations

import json
import math
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from src.services.history_comparison_service import (
    BASELINE_MISSING_BASE,
    BASELINE_MISSING_HISTORY,
    BASELINE_MISSING_TARGET,
    BASELINE_OK,
    DIRECTION_CHANGED,
    DIRECTION_DOWN,
    DIRECTION_UNAVAILABLE,
    DIRECTION_UP,
    MAX_LIST_CHANGE_ITEMS,
    MAX_LIST_ITEM_LENGTH,
    _diff_snapshots,
    _extract_comparable_snapshot,
    _finite_number,
    _record_to_signal,
    compare_analyses,
    get_latest_delta,
)


def _record(**overrides: Any) -> SimpleNamespace:
    values = {
        "id": 1,
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
        no_baseline = get_latest_delta("600519", "stock")

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
        _record(id=11, query_id="only", raw_result=_raw_payload()),
    ]

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        delta = get_latest_delta("600519", "stock")

    assert delta.has_baseline is False
    assert delta.baseline_status == BASELINE_MISSING_HISTORY
    assert delta.target_record_id == 11
    assert delta.target_query_id == "only"
    assert delta.base_record_id is None


def test_compare_analyses_missing_base_or_target() -> None:
    db = MagicMock()

    def _lookup(record_id: int) -> Optional[Any]:
        if record_id == 10:
            return _record(id=10, query_id="base", raw_result=_raw_payload())
        return None

    db.get_analysis_history_by_id.side_effect = _lookup

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        missing_target = compare_analyses("600519", 10, 20)
        missing_base = compare_analyses("600519", 20, 10)

    assert missing_target.has_baseline is False
    assert missing_target.baseline_status == BASELINE_MISSING_TARGET
    assert missing_base.has_baseline is False
    assert missing_base.baseline_status == BASELINE_MISSING_BASE


def test_compare_analyses_detects_dimension_changes() -> None:
    base = _record(
        id=101,
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
        id=102,
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

    def _lookup(record_id: int) -> Optional[Any]:
        if record_id == 101:
            return base
        if record_id == 102:
            return target
        return None

    db.get_analysis_history_by_id.side_effect = _lookup

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        delta = compare_analyses("600519", 101, 102)

    assert delta.has_baseline is True
    assert delta.baseline_status == BASELINE_OK
    assert delta.has_material_changes is True
    assert delta.base_record_id == 101
    assert delta.target_record_id == 102
    assert delta.base_query_id == "run-base"
    assert delta.target_query_id == "run-target"

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
        id=201,
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
        id=202,
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

    def _lookup(record_id: int) -> Optional[Any]:
        if record_id == 201:
            return base
        if record_id == 202:
            return target
        return None

    db.get_analysis_history_by_id.side_effect = _lookup

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        delta = compare_analyses("600519", 201, 202)

    assert delta.has_baseline is True
    by_field = {c.field: c for c in delta.conclusion_changes + delta.score_changes}
    assert by_field["stop_loss"].comparable is False
    assert by_field["stop_loss"].delta is None
    assert by_field["stop_loss"].direction == DIRECTION_UNAVAILABLE
    assert by_field["stop_loss"].target_value is None
    assert by_field["stop_loss"].unavailability is not None
    assert by_field["stop_loss"].unavailability.target == "non_finite_number"
    assert by_field["sentiment_score"].comparable is False
    assert by_field["sentiment_score"].delta is None
    # Non-finite target trend_score must not produce a numeric delta.
    assert by_field["dimension.trend_score"].comparable is False
    assert by_field["dimension.trend_score"].delta is None
    assert by_field["dimension.trend_score"].direction == DIRECTION_UNAVAILABLE
    assert math.isfinite(by_field["stop_loss"].base_value)
    json.dumps(delta.to_dict(), allow_nan=False)


def test_get_latest_delta_uses_two_most_recent_runs() -> None:
    older = _record(
        id=301,
        query_id="older",
        created_at=datetime(2026, 7, 10, 9, 0),
        sentiment_score=40,
        raw_result=_raw_payload(sentiment_score=40, operation_advice="Hold", action="hold"),
    )
    newer = _record(
        id=302,
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
    # Storage returns newest first; the service compares this exact pair directly.
    db.get_analysis_history.return_value = [newer, older]

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        delta = get_latest_delta("600519", "stock")

    assert delta.has_baseline is True
    assert delta.base_record_id == 301
    assert delta.target_record_id == 302
    assert delta.base_query_id == "older"
    assert delta.target_query_id == "newer"
    db.get_analysis_history_by_id.assert_not_called()
    score = next(c for c in delta.score_changes if c.field == "sentiment_score")
    assert score.delta == 25.0
    assert score.direction == DIRECTION_UP


def test_analysis_delta_to_dict_shape() -> None:
    base = _record(id=401, query_id="a", raw_result=_raw_payload(sentiment_score=10))
    target = _record(
        id=402,
        query_id="b",
        sentiment_score=20,
        raw_result=_raw_payload(sentiment_score=20),
    )
    db = MagicMock()
    db.get_analysis_history_by_id.side_effect = lambda record_id: (
        base if record_id == 401 else target if record_id == 402 else None
    )

    with patch(
        "src.services.history_comparison_service._database_manager",
        return_value=MagicMock(get_instance=MagicMock(return_value=db)),
    ):
        payload = compare_analyses("600519", 401, 402).to_dict()

    assert set(payload.keys()) >= {
        "has_baseline",
        "conclusion_changes",
        "score_changes",
        "evidence_changes",
        "risk_changes",
        "base_record_id",
        "target_record_id",
        "base_query_id",
        "target_query_id",
    }
    assert payload["has_baseline"] is True
    assert payload["base_record_id"] == 401
    assert payload["target_record_id"] == 402
    assert payload["base_query_id"] == "a"
    assert payload["target_query_id"] == "b"
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_nested_dimension_score_preserves_zero_and_negative_values() -> None:
    for value in (0, 0.0, "0", -3):
        snapshot = _extract_comparable_snapshot(
            _record(
                id=501,
                raw_result=_raw_payload(
                    dashboard={
                        "data_perspective": {"volume_status": {"score": value}},
                    }
                ),
            )
        )
        assert snapshot is not None
        assert snapshot["dimension_scores"]["volume_score"] == value

    missing = _extract_comparable_snapshot(
        _record(
            id=502,
            raw_result=_raw_payload(dashboard={"data_perspective": {"volume_status": {}}}),
        )
    )
    assert missing is not None
    assert "volume_score" not in missing["dimension_scores"]


def test_real_five_to_zero_dimension_score_is_a_decrease() -> None:
    base = _extract_comparable_snapshot(
        _record(
            id=511,
            query_id="base",
            raw_result=_raw_payload(
                dashboard={
                    "data_perspective": {"volume_status": {"score": 5}},
                }
            ),
        )
    )
    target = _extract_comparable_snapshot(
        _record(
            id=512,
            query_id="target",
            raw_result=_raw_payload(
                dashboard={
                    "data_perspective": {"volume_status": {"score": 0}},
                }
            ),
        )
    )
    assert base is not None and target is not None

    change = next(
        item
        for item in _diff_snapshots(base, target).score_changes
        if item.field == "dimension.volume_score"
    )
    assert change.base_value == 5.0
    assert change.target_value == 0.0
    assert change.delta == -5.0
    assert change.direction == DIRECTION_DOWN


def test_non_finite_dimension_zero_and_missing_reasons_are_strict_json_safe() -> None:
    base = _extract_comparable_snapshot(
        _record(
            id=521,
            query_id="base",
            stop_loss=100.0,
            sentiment_score=10,
            raw_result=_raw_payload(
                key_points=["base evidence"],
                risk_warning=["base risk"],
                dashboard={
                    "data_perspective": {
                        "volume_status": {"score": 0},
                        "momentum_status": {"score": float("nan")},
                    }
                },
            ),
        )
    )
    target = _extract_comparable_snapshot(
        _record(
            id=522,
            query_id="target",
            stop_loss=float("inf"),
            sentiment_score=20,
            raw_result=_raw_payload(
                key_points=["target evidence"],
                risk_warning=["target risk"],
                dashboard={
                    "data_perspective": {
                        "volume_status": {"score": -1},
                        "momentum_status": {"score": float("-inf")},
                    }
                },
            ),
        )
    )
    assert base is not None and target is not None

    payload = _diff_snapshots(base, target).to_dict()
    assert payload["conclusion_changes"]
    assert payload["score_changes"]
    assert payload["evidence_changes"]
    assert payload["risk_changes"]
    stop_loss = next(
        item for item in payload["conclusion_changes"] if item["field"] == "stop_loss"
    )
    assert stop_loss["target_value"] is None
    assert stop_loss["unavailability"]["target"] == "non_finite_number"
    momentum = next(
        item
        for item in payload["score_changes"]
        if item["field"] == "dimension.momentum_score"
    )
    assert momentum["base_value"] is None
    assert momentum["target_value"] is None
    assert momentum["unavailability"] == {
        "base": "non_finite_number",
        "target": "non_finite_number",
    }
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_list_change_output_is_bounded_and_reports_omitted_details() -> None:
    long_suffix = "x" * (MAX_LIST_ITEM_LENGTH + 50)
    base = _extract_comparable_snapshot(
        _record(id=531, query_id="base", raw_result=_raw_payload(key_points=[]))
    )
    target = _extract_comparable_snapshot(
        _record(
            id=532,
            query_id="target",
            raw_result=_raw_payload(
                key_points=[f"item-{index:03d}-{long_suffix}" for index in range(105)]
            ),
        )
    )
    assert base is not None and target is not None

    change = next(
        item
        for item in _diff_snapshots(base, target).evidence_changes
        if item.field == "key_points"
    )
    assert len(change.added) == MAX_LIST_CHANGE_ITEMS
    assert change.added_total == 105
    assert change.output_truncated is True
    assert all(len(item) <= MAX_LIST_ITEM_LENGTH for item in change.added)
