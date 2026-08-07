# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Conservative runtime weights from attributable Skill Opinion outcomes."""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.agent.skills.aggregator import SkillAggregator
from src.agent.skills.defaults import extract_skill_id, is_skill_agent_name
from src.schemas.skill_opinion_outcome import SUPPORTED_SKILL_OUTCOME_HORIZONS
from src.services.skill_opinion_outcome_service import (
    SKILL_OPINION_OUTCOME_ENGINE_VERSION,
)
from src.services.skill_opinion_performance_service import (
    MIN_SKILL_OUTCOME_SAMPLE_SIZE,
    SkillOpinionPerformanceService,
)
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

_BETA_PRIOR_HITS = 15
_BETA_PRIOR_MISSES = 15
_BETA_PRIOR_SIZE = _BETA_PRIOR_HITS + _BETA_PRIOR_MISSES
_UNABLE_PENALTY = 0.25
MAX_SKILL_OPINION_WEIGHT_FACTOR = 1.2
MIN_SKILL_OPINION_WEIGHT_FACTOR = 1.0 / MAX_SKILL_OPINION_WEIGHT_FACTOR


def is_skill_opinion_outcome_weights_enabled(config: Any = None) -> bool:
    """Return whether default-off Bayesian outcome weights are enabled."""
    if config is None:
        from src.config import Config

        config = Config.get_instance()
    return bool(getattr(config, "skill_opinion_outcome_weights_enabled", False))


class SkillOpinionWeightService:
    """Convert sufficient Outcome statistics into bounded Skill factors."""

    def __init__(
        self,
        *,
        performance_service: Optional[SkillOpinionPerformanceService] = None,
        engine_version: str = SKILL_OPINION_OUTCOME_ENGINE_VERSION,
    ) -> None:
        self.performance_service = (
            performance_service or SkillOpinionPerformanceService()
        )
        self.engine_version = str(engine_version or "").strip()

    def compute_weights(
        self,
        skill_ids: Sequence[str],
    ) -> Dict[str, float]:
        """Return one fail-neutral performance factor per requested Skill."""
        requested = self._normalize_skill_ids(skill_ids)
        neutral = {skill_id: 1.0 for skill_id in requested}
        if not requested or not self.engine_version:
            return neutral

        try:
            stats = self.performance_service.get_stats(
                engine_version=self.engine_version,
                skill_ids=requested,
            )
            if not isinstance(stats, dict):
                return neutral
            if stats.get("engine_version") != self.engine_version:
                return neutral
            buckets = stats.get("buckets")
            if not isinstance(buckets, list):
                return neutral
        except Exception as exc:  # broad-exception: fallback_recorded - Weight lookup must never interrupt analysis; fail neutral.
            log_safe_exception(
                logger,
                "Failed to read Skill Opinion performance statistics",
                exc,
                error_code="skill_opinion_weight_stats_failed",
                level=logging.DEBUG,
            )
            return neutral

        requested_set = set(requested)
        scored: Dict[str, List[Tuple[float, float]]] = {
            skill_id: [] for skill_id in requested
        }
        invalid_skills: Set[str] = set()
        seen_buckets: Set[Tuple[str, str]] = set()

        for bucket in buckets:
            skill_id = self._bucket_skill_id(bucket)
            if skill_id not in requested_set:
                continue
            if not self._bucket_identity_is_current(bucket):
                continue

            horizon = str(bucket.get("horizon") or "").strip()
            bucket_key = (skill_id, horizon)
            if bucket_key in seen_buckets:
                invalid_skills.add(skill_id)
                continue
            seen_buckets.add(bucket_key)

            if not self._declares_sufficient_sample(bucket):
                continue

            score = self._score_bucket(bucket)
            if score is None:
                invalid_skills.add(skill_id)
                continue
            scored[skill_id].append(score)

        for skill_id, bucket_scores in scored.items():
            if skill_id in invalid_skills or not bucket_scores:
                continue
            evidence_total = sum(
                evidence_strength
                for _, evidence_strength in bucket_scores
            )
            if not math.isfinite(evidence_total) or evidence_total <= 0:
                continue
            combined_score = sum(
                bucket_score * evidence_strength
                for bucket_score, evidence_strength in bucket_scores
            ) / evidence_total
            factor = math.exp(
                math.log(MAX_SKILL_OPINION_WEIGHT_FACTOR) * combined_score
            )
            if not math.isfinite(factor):
                continue
            neutral[skill_id] = min(
                MAX_SKILL_OPINION_WEIGHT_FACTOR,
                max(MIN_SKILL_OPINION_WEIGHT_FACTOR, factor),
            )

        return neutral

    def _bucket_identity_is_current(self, bucket: Any) -> bool:
        if not isinstance(bucket, dict):
            return False
        horizon = str(bucket.get("horizon") or "").strip()
        return (
            bucket.get("engine_version") == self.engine_version
            and horizon in SUPPORTED_SKILL_OUTCOME_HORIZONS
        )

    @staticmethod
    def _bucket_skill_id(bucket: Any) -> str:
        if not isinstance(bucket, dict):
            return ""
        return str(bucket.get("skill_id") or "").strip()

    @staticmethod
    def _declares_sufficient_sample(bucket: Dict[str, Any]) -> bool:
        return bucket.get("sample_sufficient") is True

    @staticmethod
    def _score_bucket(
        bucket: Dict[str, Any],
    ) -> Optional[Tuple[float, float]]:
        evaluated = SkillOpinionWeightService._count(bucket.get("evaluated"))
        hit = SkillOpinionWeightService._count(bucket.get("hit"))
        miss = SkillOpinionWeightService._count(bucket.get("miss"))
        observational = SkillOpinionWeightService._count(
            bucket.get("observational")
        )
        unable = SkillOpinionWeightService._count(bucket.get("unable"))
        if None in (evaluated, hit, miss, observational, unable):
            return None
        if evaluated < MIN_SKILL_OUTCOME_SAMPLE_SIZE:
            return None
        if hit + miss != evaluated:
            return None

        posterior_hit_rate = (hit + _BETA_PRIOR_HITS) / (
            evaluated + _BETA_PRIOR_SIZE
        )
        direction_score = 2.0 * posterior_hit_rate - 1.0
        terminal_count = evaluated + observational + unable
        if terminal_count <= 0:
            return None
        unable_rate = unable / terminal_count
        bucket_score = min(
            1.0,
            max(-1.0, direction_score - _UNABLE_PENALTY * unable_rate),
        )
        evidence_strength = evaluated / (evaluated + _BETA_PRIOR_SIZE)
        if not all(
            math.isfinite(value)
            for value in (bucket_score, evidence_strength)
        ):
            return None
        return bucket_score, evidence_strength

    @staticmethod
    def _count(value: Any) -> Optional[int]:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if value >= 0 else None

    @staticmethod
    def _normalize_skill_ids(values: Sequence[str]) -> List[str]:
        normalized: List[str] = []
        for value in values:
            skill_id = str(value or "").strip()
            if skill_id and skill_id not in normalized:
                normalized.append(skill_id)
        return normalized


class OutcomeWeightedSkillAggregator(SkillAggregator):
    """SkillAggregator that multiplies confidence by Bayesian outcome factors.

    Installed only when ``SKILL_OPINION_OUTCOME_WEIGHTS_ENABLED`` is on.
    Replaces the unattributable backtest fallback and memory auto-weights
    for the duration of that aggregation call; missing/insufficient stats
    remain fail-neutral (factor ``1.0``).
    """

    def __init__(
        self,
        *,
        weight_service: Optional[SkillOpinionWeightService] = None,
    ) -> None:
        self._weight_service = weight_service
        self._outcome_factors: Dict[str, float] = {}

    def calculate(self, opinions, min_samples: int = 30):  # type: ignore[override]
        skill_opinions = [
            op for op in opinions if is_skill_agent_name(op.agent_name)
        ]
        skill_ids = [
            extract_skill_id(op.agent_name) or op.agent_name
            for op in skill_opinions
        ]
        self._outcome_factors = self._performance_weights(skill_ids)
        return super().calculate(opinions, min_samples=min_samples)

    def _compute_weight(  # type: ignore[override]
        self,
        opinion,
        min_samples: int,
        perf_weight: Optional[float] = None,
    ) -> float:
        del min_samples, perf_weight
        skill_id = extract_skill_id(opinion.agent_name) or opinion.agent_name
        factor = self._outcome_factors.get(skill_id, 1.0)
        if (
            isinstance(factor, (int, float))
            and not isinstance(factor, bool)
            and math.isfinite(factor)
            and MIN_SKILL_OPINION_WEIGHT_FACTOR
            <= float(factor)
            <= MAX_SKILL_OPINION_WEIGHT_FACTOR
        ):
            return float(opinion.confidence) * float(factor)
        return float(opinion.confidence)

    def _performance_weights(self, skill_ids: List[str]) -> Dict[str, float]:
        neutral = {skill_id: 1.0 for skill_id in skill_ids}
        try:
            service = self._weight_service or SkillOpinionWeightService()
            computed = service.compute_weights(skill_ids)
            if not isinstance(computed, dict):
                return neutral
            for skill_id in neutral:
                factor = computed.get(skill_id)
                if (
                    isinstance(factor, (int, float))
                    and not isinstance(factor, bool)
                    and math.isfinite(factor)
                    and MIN_SKILL_OPINION_WEIGHT_FACTOR
                    <= float(factor)
                    <= MAX_SKILL_OPINION_WEIGHT_FACTOR
                ):
                    neutral[skill_id] = float(factor)
        except Exception as exc:  # broad-exception: fallback_recorded - Outcome weight computation must never interrupt aggregation.
            log_safe_exception(
                logger,
                "Failed to compute Skill Opinion outcome weights",
                exc,
                error_code="skill_opinion_outcome_weights_failed",
                level=logging.DEBUG,
            )
        return neutral


def build_outcome_weight_aggregator(
    *,
    weight_service: Optional[SkillOpinionWeightService] = None,
) -> OutcomeWeightedSkillAggregator:
    """Factory used by the pipeline weight-application seam."""
    return OutcomeWeightedSkillAggregator(weight_service=weight_service)
