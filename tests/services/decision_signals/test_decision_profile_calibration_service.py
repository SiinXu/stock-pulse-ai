# -*- coding: utf-8 -*-
"""Deterministic tests for decision-profile outcome calibration."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import pytest

from src.services.decision_profile_calibration_service import (
    MIN_PROFILE_CALIBRATION_SAMPLE_SIZE,
    build_profile_calibration,
    empty_profile_calibration,
    is_decision_profile_calibration_enabled,
    normalize_profile_source,
    row_max_adverse_excursion_pct,
)


@dataclass
class _Outcome:
    eval_status: str = "completed"
    outcome: Optional[str] = "hit"
    stock_return_pct: Optional[float] = 2.0
    unable_reason: Optional[str] = None
    action: str = "buy"
    horizon: str = "3d"
    market_phase: str = "postmarket"
    data_quality_level: str = "good"
    start_price: Optional[float] = 100.0
    min_low: Optional[float] = 94.0
    max_high: Optional[float] = 108.0


@dataclass(frozen=True)
class _StatsRow:
    outcome: _Outcome
    decision_profile: Optional[str]
    metadata_json: Optional[str]


def _row(
    *,
    decision_profile: Optional[str] = "balanced",
    profile_source: Optional[str] = "auto_default",
    action: str = "buy",
    horizon: str = "3d",
    market_phase: str = "postmarket",
    data_quality_level: str = "good",
    outcome_value: str = "hit",
    eval_status: str = "completed",
    stock_return_pct: float = 2.0,
) -> _StatsRow:
    metadata = (
        f'{{"profile_source": "{profile_source}"}}'
        if profile_source is not None
        else None
    )
    return _StatsRow(
        outcome=_Outcome(
            eval_status=eval_status,
            outcome=outcome_value if eval_status == "completed" else None,
            stock_return_pct=stock_return_pct if eval_status == "completed" else None,
            action=action,
            horizon=horizon,
            market_phase=market_phase,
            data_quality_level=data_quality_level,
        ),
        decision_profile=decision_profile,
        metadata_json=metadata,
    )


def test_empty_data_cold_start() -> None:
    payload = empty_profile_calibration()
    assert payload["minimum_completed_sample_size"] == MIN_PROFILE_CALIBRATION_SAMPLE_SIZE
    assert set(payload["breakdowns"]) == {
        "decision_profile",
        "decision_profile_action",
        "decision_profile_horizon",
        "decision_profile_market_phase",
        "decision_profile_data_quality_level",
        "profile_source",
    }
    assert all(buckets == [] for buckets in payload["breakdowns"].values())
    assert build_profile_calibration([]) == empty_profile_calibration()


def test_profile_calibration_groups_six_dimensions_and_gates_each_bucket() -> None:
    rows = []
    outcomes = ("hit", "miss", "neutral")
    for index in range(30):
        rows.append(
            _row(
                decision_profile="balanced",
                action="buy",
                horizon="3d",
                profile_source="auto_default",
                outcome_value=outcomes[index % 3],
                stock_return_pct={"hit": 2.0, "miss": -2.0, "neutral": 0.0}[outcomes[index % 3]],
            )
        )
    for index in range(29):
        rows.append(
            _row(
                decision_profile="balanced",
                action="sell",
                horizon="10d",
                profile_source="user_selected",
                outcome_value="hit" if index % 2 == 0 else "miss",
            )
        )
    rows.append(
        _row(
            decision_profile=None,
            action="hold",
            horizon="5d",
            market_phase="intraday",
            data_quality_level="medium",
            profile_source="legacy_unknown",
        )
    )

    calibration = build_profile_calibration(rows)
    breakdowns = calibration["breakdowns"]
    assert calibration["minimum_completed_sample_size"] == 30

    profile_buckets = {
        bucket["dimensions"]["decision_profile"]: bucket
        for bucket in breakdowns["decision_profile"]
    }
    assert profile_buckets["balanced"]["completed"] == 59
    assert profile_buckets["balanced"]["sample_sufficient"] is True
    assert profile_buckets["unknown"]["sample_sufficient"] is False
    assert profile_buckets["unknown"]["hit_rate_pct"] is None

    action_buckets = {
        (bucket["dimensions"]["decision_profile"], bucket["dimensions"]["action"]): bucket
        for bucket in breakdowns["decision_profile_action"]
    }
    buy = action_buckets[("balanced", "buy")]
    sell = action_buckets[("balanced", "sell")]
    assert buy["completed"] == 30
    assert buy["hit"] == 10
    assert buy["miss"] == 10
    assert buy["neutral"] == 10
    assert buy["sample_sufficient"] is True
    assert buy["hit_rate_pct"] == 50.0
    assert buy["miss_rate_pct"] == 50.0
    assert buy["unable_rate_pct"] == 0.0
    assert buy["avg_stock_return_pct"] == 0.0
    assert buy["max_adverse_excursion_pct"] == 6.0
    assert sell["completed"] == 29
    assert sell["sample_sufficient"] is False
    for metric in (
        "hit_rate_pct",
        "avg_stock_return_pct",
        "miss_rate_pct",
        "unable_rate_pct",
        "max_adverse_excursion_pct",
    ):
        assert sell[metric] is None


@pytest.mark.parametrize(
    ("metadata_json", "expected"),
    [
        ('{"profile_source": "auto_default"}', "auto_default"),
        ('{"profile_source": "invalid"}', "unknown"),
        (None, "unknown"),
    ],
)
def test_profile_source_normalization(metadata_json, expected) -> None:
    assert normalize_profile_source(metadata_json) == expected


@pytest.mark.parametrize("action", ["buy", "add", "hold", "watch", "alert"])
def test_long_side_max_adverse_excursion_formula(action) -> None:
    row = _Outcome(action=action, start_price=100.0, min_low=91.5, max_high=110.0)
    assert row_max_adverse_excursion_pct(row) == 8.5


@pytest.mark.parametrize("action", ["sell", "reduce", "avoid"])
def test_defensive_max_adverse_excursion_formula(action) -> None:
    row = _Outcome(action=action, start_price=100.0, min_low=91.5, max_high=112.0)
    assert row_max_adverse_excursion_pct(row) == 12.0


def test_gate_helper_default_off() -> None:
    assert is_decision_profile_calibration_enabled(
        SimpleNamespace(decision_profile_calibration_enabled=False)
    ) is False
    assert is_decision_profile_calibration_enabled(
        SimpleNamespace(decision_profile_calibration_enabled=True)
    ) is True
    assert is_decision_profile_calibration_enabled(SimpleNamespace()) is False
