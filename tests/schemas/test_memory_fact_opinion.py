# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic contract tests for the #1124 DAG-1 fact/opinion field lock."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.v1.schemas.decision_signals import DecisionSignalFeedbackRequest
from src.schemas.agent_episode import EpisodeOutcomeLabels
from src.schemas.memory_fact_opinion import (
    FACT_FIELD_NAMES,
    OPINION_FIELD_NAMES,
    FactOpinionMixError,
    lock_fact_payload,
    lock_opinion_payload,
    lock_prediction_outcome_actuals,
)


def test_fact_and_opinion_field_sets_are_disjoint() -> None:
    overlap = FACT_FIELD_NAMES & OPINION_FIELD_NAMES
    assert overlap == frozenset()
    assert "outcome_json" in FACT_FIELD_NAMES
    assert "prediction_outcome" in FACT_FIELD_NAMES
    assert "feedback_value" in OPINION_FIELD_NAMES
    assert "user_feedback" in OPINION_FIELD_NAMES
    assert "source" in OPINION_FIELD_NAMES


def test_lock_fact_payload_rejects_opinion_keys() -> None:
    payload = {"label": "hit", "score": 1.0, "feedback_value": "useful", "note": "rewrite"}
    with pytest.raises(FactOpinionMixError, match="feedback_value"):
        lock_fact_payload(payload)
    with pytest.raises(FactOpinionMixError, match="note"):
        lock_prediction_outcome_actuals(payload)


def test_lock_opinion_payload_rejects_actuals_keys() -> None:
    payload = {
        "feedback_value": "useful",
        "source": "api",
        "outcome": "miss",
        "start_price": 100.0,
    }
    with pytest.raises(FactOpinionMixError, match="outcome"):
        lock_opinion_payload(payload)


def test_lock_allows_separated_payloads() -> None:
    actuals = {
        "label": "hit",
        "score": {"aggregate": {"hit_count": 1}},
        "actuals": {"end_price": 105.0},
        "engine_version": "prediction-resolver-v1",
    }
    opinion = {
        "feedback_value": "not_useful",
        "reason_code": "disputed",
        "note": "user disagrees with the score",
        "source": "web",
    }
    assert lock_prediction_outcome_actuals(actuals) is actuals
    assert lock_opinion_payload(opinion) is opinion


def test_feedback_request_rejects_smuggled_actuals_fields() -> None:
    with pytest.raises((ValidationError, FactOpinionMixError)):
        DecisionSignalFeedbackRequest.model_validate(
            {
                "feedback_value": "useful",
                "source": "api",
                "outcome": "miss",
                "label": "hit",
                "start_price": 1,
            }
        )


def test_feedback_request_accepts_documented_opinion_fields() -> None:
    request = DecisionSignalFeedbackRequest.model_validate(
        {
            "feedback_value": "useful",
            "reason_code": "matched_plan",
            "note": "agrees with the call",
            "source": "web",
        }
    )
    assert request.feedback_value == "useful"
    assert request.source == "web"


def test_episode_extra_cannot_carry_actuals_fields() -> None:
    with pytest.raises(ValidationError, match="PredictionOutcome actuals"):
        EpisodeOutcomeLabels.model_validate(
            {
                "user_feedback": "disagree_score",
                "extra": {"outcome": "miss", "start_price": "1"},
            }
        )
    labels = EpisodeOutcomeLabels.model_validate(
        {
            "user_feedback": "disagree_score",
            "prediction_outcome": "hit",
            "prediction_id": "pred-1",
            "extra": {"review_queue": "meta"},
        }
    )
    assert labels.user_feedback == "disagree_score"
    assert labels.prediction_outcome == "hit"
