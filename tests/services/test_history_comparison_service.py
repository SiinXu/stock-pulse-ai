from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict

from src.services.history_comparison_service import (
    BASELINE_OK,
    DIRECTION_CHANGED,
    DIRECTION_DOWN,
    DIRECTION_UP,
    MAX_LIST_CHANGE_ITEMS,
    MAX_LIST_ITEM_LENGTH,
    _diff_snapshots,
    _extract_comparable_snapshot,
    _project_number,
    _record_to_signal,
    get_signal_changes_batch,
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


def test_signal_changes_batch_uses_one_alias_aware_bounded_query(
    monkeypatch,
) -> None:
    calls = []

    class FakeDatabase:
        def get_analysis_history_batch(self, **kwargs: Any):
            calls.append(kwargs)
            return [
                _record(
                    id=3,
                    code="00700.HK",
                    query_id="latest",
                    created_at=datetime(2026, 8, 9, 7, 0),
                ),
                _record(
                    id=2,
                    code="HK00700",
                    query_id="previous",
                    created_at=datetime(2026, 8, 8, 7, 0),
                ),
                _record(
                    id=1,
                    code="600519.SH",
                    query_id="a-share",
                    created_at=datetime(2026, 8, 9, 6, 0),
                ),
            ]

    manager = SimpleNamespace(get_instance=lambda: FakeDatabase())
    monkeypatch.setattr(
        "src.services.history_comparison_service._database_manager",
        lambda: manager,
    )

    result = get_signal_changes_batch(
        ["HK00700", "600519"],
        limit=2,
        created_at_from=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    assert len(calls) == 1
    assert calls[0]["limit_per_code"] == 2
    assert "00700.HK" in calls[0]["codes"]
    assert [row["record_id"] for row in result["HK00700"]] == [3, 2]
    assert [row["record_id"] for row in result["600519"]] == [1]


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


def test_project_number_rejects_non_finite_and_invalid_values() -> None:
    assert _project_number(None) == (None, "missing_value")
    assert _project_number(float("nan")) == (None, "non_finite_number")
    assert _project_number(float("inf")) == (None, "non_finite_number")
    assert _project_number(float("-inf")) == (None, "non_finite_number")
    assert _project_number("not-a-number") == (None, "invalid_number")
    assert _project_number(10**1000) == (None, "non_finite_number")
    assert _project_number(12.5) == (12.5, None)
    assert _project_number("12.5") == (12.5, None)


def test_diff_detects_all_dimension_changes() -> None:
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

    base_snapshot = _extract_comparable_snapshot(base)
    target_snapshot = _extract_comparable_snapshot(target)
    assert base_snapshot is not None and target_snapshot is not None
    delta = _diff_snapshots(base_snapshot, target_snapshot)

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


def test_five_to_zero_dimension_score_is_a_decrease() -> None:
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
                        "fundamental_status": {"score": "0"},
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
    fundamental = next(
        item
        for item in payload["score_changes"]
        if item["field"] == "dimension.fundamental_score"
    )
    assert fundamental["base_value"] is None
    assert fundamental["target_value"] == 0.0
    assert fundamental["unavailability"] == {
        "base": "missing_value",
        "target": None,
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
