# -*- coding: utf-8 -*-
"""Table-driven tests for deterministic ClaimScorer (#1111 / #1107)."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pytest

from src.schemas.prediction_claim_scoring import (
    CLAIM_SCORER_VERSION,
    ClaimActuals,
    ClaimScoreConfig,
    OUTCOME_DATA_UNAVAILABLE,
    OUTCOME_HIT,
    OUTCOME_MISS,
    OUTCOME_PARTIAL,
)
from src.schemas.prediction_record import PredictionClaim
from src.services.claim_scorer import ClaimScorer


def _claim(
    claim_id: str,
    claim_type: str,
    payload: Mapping[str, Any],
    confidence: float = 0.5,
) -> Dict[str, Any]:
    return {
        "claim_id": claim_id,
        "type": claim_type,
        "confidence": confidence,
        "payload": dict(payload),
    }


def _score(
    claims: List[Mapping[str, Any]],
    actuals: Mapping[str, Any],
    config: Optional[Mapping[str, Any]] = None,
):
    return ClaimScorer().score(claims, actuals, config)


def _single(
    claim: Mapping[str, Any],
    actuals: Mapping[str, Any],
    config: Optional[Mapping[str, Any]] = None,
):
    report = _score([claim], actuals, config)
    assert len(report.claim_results) == 1
    return report.claim_results[0], report


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_id,direction,actuals,config,expected_outcome,expected_direction",
    [
        (
            "up_hit",
            "up",
            {"start_price": 100.0, "end_price": 105.0},
            None,
            OUTCOME_HIT,
            "up",
        ),
        (
            "down_hit",
            "down",
            {"start_price": 100.0, "end_price": 90.0},
            None,
            OUTCOME_HIT,
            "down",
        ),
        (
            "sideways_hit_zero_change",
            "sideways",
            {"start_price": 100.0, "end_price": 100.0},
            None,
            OUTCOME_HIT,
            "sideways",
        ),
        (
            "sideways_hit_exactly_epsilon",
            "sideways",
            {"start_price": 1000.0, "end_price": 1001.0},  # +0.1%
            {"flat_epsilon": 0.001},
            OUTCOME_HIT,
            "sideways",
        ),
        (
            "up_just_outside_epsilon",
            "up",
            {"start_price": 1000.0, "end_price": 1001.1},  # +0.11%
            {"sideways_epsilon": 0.001},
            OUTCOME_HIT,
            "up",
        ),
        (
            "predicted_up_actual_sideways_partial",
            "up",
            {"start_price": 100.0, "end_price": 100.05},
            {"flat_epsilon": 0.001},
            OUTCOME_PARTIAL,
            "sideways",
        ),
        (
            "predicted_sideways_actual_up_partial",
            "sideways",
            {"start_price": 100.0, "end_price": 102.0},
            None,
            OUTCOME_PARTIAL,
            "up",
        ),
        (
            "opposite_miss",
            "up",
            {"start_price": 100.0, "end_price": 90.0},
            None,
            OUTCOME_MISS,
            "down",
        ),
        (
            "configurable_epsilon_widens_sideways",
            "sideways",
            {"start_price": 100.0, "end_price": 102.0},
            {"flat_epsilon": 0.03},
            OUTCOME_HIT,
            "sideways",
        ),
        (
            "extreme_up",
            "up",
            {"start_price": 1.0, "end_price": 1000.0},
            None,
            OUTCOME_HIT,
            "up",
        ),
        (
            "extreme_down",
            "down",
            {"start_price": 1000.0, "end_price": 1.0},
            None,
            OUTCOME_HIT,
            "down",
        ),
    ],
)
def test_direction_table(
    case_id: str,
    direction: str,
    actuals: Dict[str, Any],
    config: Optional[Dict[str, Any]],
    expected_outcome: str,
    expected_direction: str,
) -> None:
    result, _ = _single(
        _claim(case_id, "direction", {"direction": direction}),
        actuals,
        config,
    )
    assert result.outcome == expected_outcome, case_id
    assert result.actual_direction == expected_direction, case_id
    assert result.score is not None, case_id


def test_direction_missing_prices_is_data_unavailable_not_hit() -> None:
    result, report = _single(
        _claim("x", "direction", {"direction": "up"}),
        {"start_price": 100.0},
    )
    assert result.outcome == OUTCOME_DATA_UNAVAILABLE
    assert result.score is None
    assert result.reason == "missing_prices"
    assert report.aggregate.data_unavailable_count == 1
    assert report.aggregate.hit_count == 0
    assert report.aggregate.mean_score is None


def test_direction_explicit_unavailable_reason() -> None:
    result, _ = _single(
        _claim("x", "direction", {"direction": "up"}),
        {
            "start_price": 100.0,
            "end_price": 110.0,
            "unavailable_reason": "provider_timeout",
        },
    )
    assert result.outcome == OUTCOME_DATA_UNAVAILABLE
    assert result.reason == "provider_timeout"
    assert result.score is None


def test_invalid_claim_mapping_is_miss_not_hit() -> None:
    result, _ = _single(
        {
            "claim_id": "bad",
            "type": "direction",
            "confidence": 0.5,
            "payload": {"direction": "sideways_maybe"},
        },
        {"start_price": 100.0, "end_price": 110.0},
    )
    assert result.outcome == OUTCOME_MISS
    assert result.reason == "invalid_claim"
    assert result.score == 0.0
    assert result.details.get("error") == "claim_validation_failed"
    # Validation diagnostics must surface for resolver logs (review #1188).
    validation_error = result.details.get("validation_error")
    assert isinstance(validation_error, str) and validation_error
    assert "direction" in validation_error.lower() or "payload" in validation_error.lower()


# ---------------------------------------------------------------------------
# Return bucket
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_id,return_end,low,high,incl_low,incl_high,margin,expected",
    [
        ("inside_hit", 105.0, 0.0, 10.0, True, False, 1.0, OUTCOME_HIT),
        ("low_boundary_inclusive", 100.0, 0.0, 5.0, True, False, 1.0, OUTCOME_HIT),
        ("high_boundary_exclusive", 105.0, 0.0, 5.0, True, False, 1.0, OUTCOME_PARTIAL),
        ("high_boundary_inclusive_hit", 105.0, 0.0, 5.0, True, True, 1.0, OUTCOME_HIT),
        ("just_inside_high", 104.9, 0.0, 5.0, True, False, 1.0, OUTCOME_HIT),
        ("near_bucket_partial", 106.0, 0.0, 5.0, True, False, 1.5, OUTCOME_PARTIAL),
        ("far_miss", 120.0, 0.0, 5.0, True, False, 1.0, OUTCOME_MISS),
        ("zero_bucket_low_ok", 100.0, 0.0, 5.0, True, False, 0.0, OUTCOME_HIT),
        (
            "zero_move_outside_negative_bucket_miss",
            100.0,
            -5.0,
            0.0,
            True,
            False,
            0.0,
            OUTCOME_MISS,
        ),
        (
            "zero_move_partial_with_margin",
            100.0,
            -5.0,
            0.0,
            True,
            False,
            0.5,
            OUTCOME_PARTIAL,
        ),
    ],
)
def test_return_bucket_table(
    case_id: str,
    return_end: float,
    low: float,
    high: float,
    incl_low: bool,
    incl_high: bool,
    margin: float,
    expected: str,
) -> None:
    claim = _claim(
        case_id,
        "return_bucket",
        {
            "low_pct": low,
            "high_pct": high,
            "inclusive_low": incl_low,
            "inclusive_high": incl_high,
        },
    )
    result, _ = _single(
        claim,
        {"start_price": 100.0, "end_price": return_end},
        {"bucket_partial_margin_pct": margin},
    )
    assert result.outcome == expected, case_id


def test_return_bucket_zero_bound_is_finite_and_scoreable() -> None:
    """Regression: 0.0 must not be treated as non-finite via truthiness."""
    result, _ = _single(
        _claim(
            "zero-bound",
            "return_bucket",
            {"low_pct": 0.0, "high_pct": 10.0},
        ),
        {"start_price": 100.0, "end_price": 105.0},
    )
    assert result.outcome == OUTCOME_HIT
    assert result.realized_return_pct == 5.0


# ---------------------------------------------------------------------------
# Level break
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_id,payload,actuals,config,expected",
    [
        (
            "break_above_hit_on_high",
            {"side": "above", "level": 110.0, "reference": "absolute_price"},
            {
                "start_price": 100.0,
                "end_price": 105.0,
                "high_price": 112.0,
                "low_price": 98.0,
            },
            None,
            OUTCOME_HIT,
        ),
        (
            "break_above_exactly_level",
            {"side": "above", "level": 110.0},
            {
                "start_price": 100.0,
                "end_price": 110.0,
                "high_price": 110.0,
                "low_price": 99.0,
            },
            None,
            OUTCOME_HIT,
        ),
        (
            "break_above_near_touch_partial",
            {"side": "above", "level": 100.0},
            {
                "start_price": 90.0,
                "end_price": 99.9,
                "high_price": 99.9,
                "low_price": 88.0,
            },
            {"level_touch_epsilon": 0.002},
            OUTCOME_PARTIAL,
        ),
        (
            "break_above_miss",
            {"side": "above", "level": 120.0},
            {
                "start_price": 100.0,
                "end_price": 105.0,
                "high_price": 110.0,
                "low_price": 99.0,
            },
            {"level_touch_epsilon": 0.001},
            OUTCOME_MISS,
        ),
        (
            "break_below_hit",
            {"side": "below", "level": 95.0},
            {
                "start_price": 100.0,
                "end_price": 96.0,
                "high_price": 101.0,
                "low_price": 94.0,
            },
            None,
            OUTCOME_HIT,
        ),
        (
            "break_below_end_only_fallback",
            {"side": "below", "level": 95.0},
            {"start_price": 100.0, "end_price": 94.0},
            None,
            OUTCOME_HIT,
        ),
        (
            "pct_from_as_of_close_above",
            {
                "side": "above",
                "level": 10.0,
                "reference": "pct_from_as_of_close",
            },
            {
                "start_price": 100.0,
                "end_price": 108.0,
                "high_price": 112.0,
                "low_price": 99.0,
            },
            None,
            OUTCOME_HIT,
        ),
    ],
)
def test_level_break_table(
    case_id: str,
    payload: Dict[str, Any],
    actuals: Dict[str, Any],
    config: Optional[Dict[str, Any]],
    expected: str,
) -> None:
    result, _ = _single(_claim(case_id, "level_break", payload), actuals, config)
    assert result.outcome == expected, case_id


# ---------------------------------------------------------------------------
# Vol regime + custom (price_range via custom in_range)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_id,predicted,actual,expected",
    [
        ("exact_hit", "high", "high", OUTCOME_HIT),
        ("adjacent_partial", "high", "elevated", OUTCOME_PARTIAL),
        ("far_miss", "low", "high", OUTCOME_MISS),
    ],
)
def test_vol_regime_table(
    case_id: str,
    predicted: str,
    actual: str,
    expected: str,
) -> None:
    result, _ = _single(
        _claim(case_id, "vol_regime", {"regime": predicted}),
        {"vol_regime": actual, "start_price": 100.0, "end_price": 100.0},
    )
    assert result.outcome == expected, case_id


def test_vol_regime_missing_is_unavailable() -> None:
    result, _ = _single(
        _claim("v", "vol_regime", {"regime": "normal"}),
        {"start_price": 100.0, "end_price": 101.0},
    )
    assert result.outcome == OUTCOME_DATA_UNAVAILABLE
    assert result.reason == "missing_vol_regime"


def test_vol_regime_garbage_label_is_unavailable_not_miss() -> None:
    """Fetcher typos must not poison hit-rate as miss (review #1188)."""
    result, report = _single(
        _claim("v", "vol_regime", {"regime": "high"}, confidence=0.9),
        {
            "start_price": 100.0,
            "end_price": 101.0,
            "vol_regime": "hihg",  # non-canonical
        },
    )
    assert result.outcome == OUTCOME_DATA_UNAVAILABLE
    assert result.reason == "invalid_vol_regime"
    assert result.score is None
    assert report.aggregate.miss_count == 0
    assert report.aggregate.data_unavailable_count == 1
    assert report.aggregate.calibrated_claims == 0


@pytest.mark.parametrize(
    "case_id,operator,expected,expected_high,actual,outcome",
    [
        ("eq_hit", "eq", 105.0, None, 105.0, OUTCOME_HIT),
        ("eq_miss", "eq", 105.0, None, 100.0, OUTCOME_MISS),
        ("gte_hit", "gte", 100.0, None, 100.0, OUTCOME_HIT),
        ("lt_miss", "lt", 100.0, None, 100.0, OUTCOME_MISS),
        # price_range analogue: end_price in [100, 110)
        ("in_range_hit", "in_range", 100.0, 110.0, 105.0, OUTCOME_HIT),
        ("in_range_high_exclusive", "in_range", 100.0, 110.0, 110.0, OUTCOME_MISS),
        ("in_range_low_inclusive", "in_range", 100.0, 110.0, 100.0, OUTCOME_HIT),
        ("token_eq", "eq", "bullish", None, "bullish", OUTCOME_HIT),
        ("token_ne", "ne", "bullish", None, "bearish", OUTCOME_HIT),
    ],
)
def test_custom_operator_table(
    case_id: str,
    operator: str,
    expected: Any,
    expected_high: Optional[float],
    actual: Any,
    outcome: str,
) -> None:
    payload: Dict[str, Any] = {
        "metric": "end_price",
        "operator": operator,
        "expected": expected,
    }
    if expected_high is not None:
        payload["expected_high"] = expected_high
    result, _ = _single(
        _claim(case_id, "custom", payload),
        {"metrics": {"end_price": actual}},
    )
    assert result.outcome == outcome, case_id


def test_custom_missing_metric_unavailable() -> None:
    result, _ = _single(
        _claim(
            "c",
            "custom",
            {"metric": "end_price", "operator": "eq", "expected": 1.0},
        ),
        {"metrics": {}},
    )
    assert result.outcome == OUTCOME_DATA_UNAVAILABLE
    assert result.reason == "missing_metric"


# ---------------------------------------------------------------------------
# Aggregate + confidence calibration
# ---------------------------------------------------------------------------


def test_aggregate_and_calibration_metrics() -> None:
    report = _score(
        [
            _claim("h1", "direction", {"direction": "up"}, confidence=0.9),
            _claim("m1", "direction", {"direction": "down"}, confidence=0.8),
            _claim("h2", "direction", {"direction": "up"}, confidence=0.5),
            _claim("h3", "direction", {"direction": "up"}, confidence=0.7),
        ],
        {"start_price": 100.0, "end_price": 105.0},
    )
    assert report.aggregate.hit_count == 3
    assert report.aggregate.miss_count == 1
    assert report.aggregate.partial_count == 0
    assert report.aggregate.scored_claims == 4
    assert report.aggregate.calibrated_claims == 4
    assert report.aggregate.mean_confidence is not None
    assert report.aggregate.brier_score is not None
    assert report.aggregate.expected_calibration_error is not None
    assert report.aggregate.mean_confidence_on_hit is not None
    assert report.aggregate.mean_confidence_on_miss is not None
    assert report.aggregate.hit_rate == 0.75
    assert report.scorer_version == CLAIM_SCORER_VERSION


def test_unavailable_excluded_from_mean_score_and_calibration() -> None:
    report = _score(
        [
            _claim("ok", "direction", {"direction": "up"}, confidence=0.6),
            _claim("bad", "direction", {"direction": "up"}, confidence=0.99),
        ],
        {"unavailable_reason": "halted"},
    )
    assert report.aggregate.data_unavailable_count == 2
    assert report.aggregate.scored_claims == 0
    assert report.aggregate.mean_score is None
    assert report.aggregate.calibrated_claims == 0
    assert report.aggregate.brier_score is None
    assert all(item.score is None for item in report.claim_results)


# ---------------------------------------------------------------------------
# Determinism (hard acceptance)
# ---------------------------------------------------------------------------


def test_same_input_repeated_runs_are_byte_identical() -> None:
    claims = [
        _claim("d", "direction", {"direction": "up"}, confidence=0.7),
        _claim(
            "b",
            "return_bucket",
            {"low_pct": 0.0, "high_pct": 10.0},
            confidence=0.55,
        ),
        _claim(
            "l",
            "level_break",
            {"side": "above", "level": 110.0},
            confidence=0.4,
        ),
        _claim(
            "r",
            "custom",
            {
                "metric": "end_price",
                "operator": "in_range",
                "expected": 100.0,
                "expected_high": 108.0,
            },
            confidence=0.65,
        ),
        _claim("v", "vol_regime", {"regime": "normal"}, confidence=0.5),
    ]
    actuals = {
        "start_price": 100.0,
        "end_price": 105.0,
        "high_price": 111.0,
        "low_price": 99.0,
        "vol_regime": "normal",
        "metrics": {"end_price": 105.0},
    }
    config = {
        "flat_epsilon": 0.001,
        "bucket_partial_margin_pct": 1.0,
        "level_touch_epsilon": 0.002,
        "calibration_bin_count": 10,
    }
    scorer = ClaimScorer()
    first = scorer.score(
        copy.deepcopy(claims),
        copy.deepcopy(actuals),
        copy.deepcopy(config),
    )
    for _ in range(25):
        again = scorer.score(
            copy.deepcopy(claims),
            copy.deepcopy(actuals),
            copy.deepcopy(config),
        )
        assert again.to_dict() == first.to_dict()


def test_score_accepts_a1_prediction_claim_models() -> None:
    claim = PredictionClaim.model_validate(
        _claim("dc", "direction", {"direction": "sideways"}, confidence=0.5)
    )
    report = ClaimScorer().score(
        [claim],
        ClaimActuals(start_price=100.0, end_price=100.0),
        ClaimScoreConfig(flat_epsilon=0.001),
    )
    assert report.claim_results[0].outcome == OUTCOME_HIT
    assert report.aggregate.mean_score == 1.0


def test_no_io_surface_is_pure_versioned() -> None:
    scorer = ClaimScorer()
    assert scorer.VERSION == CLAIM_SCORER_VERSION
    report = scorer.score([], {"start_price": 1.0, "end_price": 1.0})
    assert report.claim_results == []
    assert report.aggregate.total_claims == 0
    assert report.config["scorer_version"] == CLAIM_SCORER_VERSION
