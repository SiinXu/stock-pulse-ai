# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic tests for Bayesian skill-opinion outcome weights."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from src.agent.protocols import AgentOpinion
from src.agent.skills.aggregator import SkillAggregator
from src.services.skill_opinion_outcome_service import (
    SKILL_OPINION_OUTCOME_ENGINE_VERSION,
)
from src.services.skill_opinion_weight_service import (
    OutcomeWeightedSkillAggregator,
    SkillOpinionWeightService,
    is_skill_opinion_outcome_weights_enabled,
)


class _FakePerformanceService:
    def __init__(self, buckets=None, *, error=None):
        self.buckets = list(buckets or [])
        self.error = error
        self.last_filters = None

    def get_stats(self, **filters):
        self.last_filters = filters
        if self.error is not None:
            raise self.error
        return {
            "engine_version": SKILL_OPINION_OUTCOME_ENGINE_VERSION,
            "minimum_evaluated_sample_size": 30,
            "buckets": self.buckets,
        }


def _bucket(
    *,
    skill_id="alpha",
    horizon="1d",
    engine_version=SKILL_OPINION_OUTCOME_ENGINE_VERSION,
    evaluated=30,
    hit=18,
    miss=12,
    observational=0,
    unable=0,
    sample_sufficient=True,
):
    return {
        "skill_id": skill_id,
        "horizon": horizon,
        "engine_version": engine_version,
        "total": evaluated + observational + unable,
        "pending": 0,
        "evaluated": evaluated,
        "observational": observational,
        "unable": unable,
        "hit": hit,
        "miss": miss,
        "sample_sufficient": sample_sufficient,
        "sample_status": "sufficient" if sample_sufficient else "observational",
        "hit_rate_pct": None,
        "miss_rate_pct": None,
        "avg_directional_return_pct": None,
        "unable_rate_pct": None,
    }


def _service(*buckets, error=None):
    return SkillOpinionWeightService(
        performance_service=_FakePerformanceService(buckets, error=error)
    )


def test_flag_defaults_off():
    assert is_skill_opinion_outcome_weights_enabled(SimpleNamespace()) is False
    assert is_skill_opinion_outcome_weights_enabled(
        SimpleNamespace(skill_opinion_outcome_weights_enabled=True)
    ) is True


def test_cold_start_zero_samples_is_neutral_no_crash():
    assert _service().compute_weights(["alpha", "beta"]) == {"alpha": 1.0, "beta": 1.0}
    assert _service().compute_weights([]) == {}


def test_weights_stay_neutral_without_independently_sufficient_bucket():
    service = _service(
        _bucket(evaluated=29, hit=29, miss=0, sample_sufficient=False),
        _bucket(skill_id="other", evaluated=100, hit=100, miss=0),
        _bucket(engine_version="skill-opinion-outcome-v999", evaluated=100, hit=100, miss=0),
    )
    assert service.compute_weights(["alpha", "missing"]) == {"alpha": 1.0, "missing": 1.0}


def test_beta_prior_shrinks_minimum_sample_hit_rate_toward_neutral():
    assert _service(_bucket(evaluated=30, hit=30, miss=0)).compute_weights(["alpha"])["alpha"] == pytest.approx(1.2 ** 0.5)


def test_more_evidence_moves_posterior_closer_to_observed_hit_rate():
    weights = _service(
        _bucket(skill_id="small", evaluated=30, hit=18, miss=12),
        _bucket(skill_id="large", evaluated=300, hit=180, miss=120),
    ).compute_weights(["small", "large"])
    assert weights["small"] == pytest.approx(1.2 ** 0.1)
    assert weights["large"] == pytest.approx(1.2 ** (2 * (195 / 330) - 1))
    assert weights["large"] > weights["small"] > 1.0


def test_sufficient_horizons_use_evidence_weighted_model_average():
    weights = _service(
        _bucket(horizon="1d", evaluated=30, hit=24, miss=6),
        _bucket(horizon="3d", evaluated=90, hit=45, miss=45),
        _bucket(horizon="5d", evaluated=29, hit=29, miss=0, sample_sufficient=False),
    ).compute_weights(["alpha"])
    combined_score = (0.3 * 0.5 + 0.0 * 0.75) / (0.5 + 0.75)
    assert weights["alpha"] == pytest.approx(1.2 ** combined_score)


def test_terminal_unable_rate_conservatively_reduces_factor():
    weights = _service(_bucket(evaluated=30, hit=30, miss=0, unable=30)).compute_weights(["alpha"])
    assert weights["alpha"] == pytest.approx(1.2 ** 0.375)


def test_extreme_negative_evidence_stays_at_multiplicative_lower_bound():
    assert _service(_bucket(evaluated=300, hit=0, miss=300, unable=300)).compute_weights(["alpha"])["alpha"] == pytest.approx(1.0 / 1.2)


@pytest.mark.parametrize(
    "bucket",
    [
        _bucket(evaluated=30, hit=math.nan, miss=0),
        _bucket(evaluated=30, hit=31, miss=-1),
        _bucket(evaluated=30, hit=20, miss=10, unable=-1),
        _bucket(evaluated=30, hit=20, miss=9),
    ],
)
def test_malformed_bucket_fails_neutral(bucket):
    assert _service(bucket).compute_weights(["alpha"]) == {"alpha": 1.0}


def test_statistics_failure_fails_neutral():
    assert _service(error=RuntimeError("database unavailable")).compute_weights(["alpha"]) == {"alpha": 1.0}


def test_weight_query_is_restricted_to_requested_skills():
    performance_service = _FakePerformanceService([_bucket(skill_id="alpha")])
    SkillOpinionWeightService(performance_service=performance_service).compute_weights([" alpha ", "beta", "alpha"])
    assert performance_service.last_filters == {
        "engine_version": SKILL_OPINION_OUTCOME_ENGINE_VERSION,
        "skill_ids": ["alpha", "beta"],
    }


def _opinions():
    return [
        AgentOpinion(agent_name="skill_alpha", signal="buy", confidence=1.0),
        AgentOpinion(agent_name="skill_without_samples", signal="sell", confidence=1.0),
    ]


def test_outcome_aggregator_applies_bayesian_factors():
    result = OutcomeWeightedSkillAggregator(
        weight_service=_service(_bucket(skill_id="alpha", evaluated=30, hit=30, miss=0))
    ).calculate(_opinions())
    assert result is not None
    assert result.weights == pytest.approx([1.2 ** 0.5, 1.0])
    assert result.weighted_score > 3.0


def test_gate_off_parity_matches_stock_aggregator(monkeypatch):
    monkeypatch.setattr(SkillAggregator, "_use_backtest_autoweight", staticmethod(lambda: False))
    monkeypatch.setattr("src.agent.memory.AgentMemory.from_config", lambda: SimpleNamespace(enabled=False))
    opinions = _opinions()
    stock = SkillAggregator().calculate(opinions)
    empty = OutcomeWeightedSkillAggregator(weight_service=_service()).calculate(opinions)
    assert stock is not None and empty is not None
    assert stock.weights == empty.weights
    assert stock.weighted_score == empty.weighted_score
    assert stock.weighted_confidence == empty.weighted_confidence
    assert stock.final_signal == empty.final_signal
    assert stock.insufficient_evidence == empty.insufficient_evidence


def test_pipeline_gate_off_uses_stock_aggregator():
    from src.agent.orchestrator_parts.pipeline import _PipelineMethods

    class _Host(_PipelineMethods):
        def __init__(self):
            self.config = SimpleNamespace(skill_opinion_outcome_weights_enabled=False)

    assert type(_Host()._skill_aggregator_for_weights(_Host().config)) is SkillAggregator


def test_pipeline_gate_on_uses_outcome_aggregator():
    from src.agent.orchestrator_parts.pipeline import _PipelineMethods

    class _Host(_PipelineMethods):
        def __init__(self):
            self.config = SimpleNamespace(skill_opinion_outcome_weights_enabled=True)

    assert isinstance(_Host()._skill_aggregator_for_weights(_Host().config), OutcomeWeightedSkillAggregator)
