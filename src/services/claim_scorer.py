# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic claim scorer for prediction verification (#1111 / #1107).

Pure function surface
---------------------
``ClaimScorer.score(claims, actuals, config) → ClaimScoreReport``

* No I/O, no wall-clock, no randomness — same inputs always yield same outputs.
* Missing / non-finite actuals → ``data_unavailable`` (never a fabricated hit).
* Invalid claim payloads → ``data_unavailable`` so model metrics are not poisoned.
* Accepts A1 :class:`~src.schemas.prediction_record.PredictionClaim` instances
  or plain mappings with the same shape (``type`` + ``payload``).
* Distinct from offline agent-output eval and skill-opinion signal evaluation.

Boundary conventions
--------------------
* Direction sideways band: ``|return_fraction| <= sideways_epsilon`` (inclusive).
  Config key ``flat_epsilon`` is an accepted alias (issue wording).
* Return buckets: honor payload ``inclusive_low`` / ``inclusive_high``; distance
  to the interval within ``bucket_partial_margin_pct`` → partial.
* Level break: absolute level or ``pct_from_as_of_close``; ``high >= level`` /
  ``low <= level``; near-touch within ``level_touch_epsilon * |level|`` → partial.
* Vol regime: exact canonical label hit; adjacent labels partial; non-canonical
  actual labels → ``data_unavailable`` (``invalid_vol_regime``), never miss.
* Custom: deterministic operator over ``actuals.metrics[metric]``.
* Invalid claims: ``data_unavailable`` with truncated validation diagnostics.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from pydantic import ValidationError

from src.schemas.prediction_claim_scoring import (
    CLAIM_SCORER_VERSION,
    MAX_VALIDATION_DETAIL_CHARS,
    ClaimActuals,
    ClaimScoreAggregate,
    ClaimScoreConfig,
    ClaimScoreReport,
    ClaimScoreResult,
    OUTCOME_DATA_UNAVAILABLE,
    OUTCOME_HIT,
    OUTCOME_MISS,
    OUTCOME_PARTIAL,
    is_canonical_vol_regime,
    outcome_numeric_score,
    vol_regimes_adjacent,
)
from src.schemas.prediction_record import (
    CustomClaimPayload,
    DirectionPayload,
    LevelBreakPayload,
    PredictionClaim,
    ReturnBucketPayload,
    VolRegimePayload,
)


ClaimLike = Union[PredictionClaim, Mapping[str, Any]]
ActualsLike = Union[ClaimActuals, Mapping[str, Any]]
ConfigLike = Union[ClaimScoreConfig, Mapping[str, Any], None]


class ClaimScorer:
    """Deterministic multi-claim scorer with optional confidence calibration."""

    VERSION = CLAIM_SCORER_VERSION

    def score(
        self,
        claims: Sequence[ClaimLike],
        actuals: ActualsLike,
        config: ConfigLike = None,
    ) -> ClaimScoreReport:
        """Score every claim against fixed actuals.

        Parameters
        ----------
        claims:
            A1 ``PredictionClaim`` instances or plain claim mappings.
        actuals:
            Realized market values (or an explicit unavailable reason).
        config:
            Optional thresholds; defaults are stable constants, not env-derived.
        """
        cfg = ClaimScoreConfig.from_mapping(config)
        act = ClaimActuals.from_mapping(actuals)
        results: List[ClaimScoreResult] = []
        for raw in claims:
            claim, coerce_details, raw_claim_id, raw_claim_type = self._coerce_claim(
                raw
            )
            if claim is None:
                results.append(
                    ClaimScoreResult(
                        claim_id=raw_claim_id,
                        claim_type=raw_claim_type,
                        outcome=OUTCOME_DATA_UNAVAILABLE,
                        score=None,
                        reason="invalid_claim",
                        confidence=None,
                        details=dict(
                            coerce_details
                            or {"error": "claim_validation_failed"}
                        ),
                    )
                )
                continue
            results.append(self._score_one(claim, act, cfg))
        aggregate = self._aggregate(results, cfg)
        return ClaimScoreReport(
            claim_results=results,
            aggregate=aggregate,
            scorer_version=cfg.scorer_version,
            config=cfg.to_dict(),
        )

    # ------------------------------------------------------------------
    # Claim coercion
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_claim(
        raw: ClaimLike,
    ) -> Tuple[
        Optional[PredictionClaim],
        Optional[Dict[str, Any]],
        str,
        str,
    ]:
        """Validate a claim mapping into A1 ``PredictionClaim``.

        Returns the validated claim, optional diagnostics, and bounded raw
        identity fields. Failures preserve only deterministic diagnostics so
        resolvers cannot leak adapter exception text or poison model metrics.
        """
        if isinstance(raw, PredictionClaim):
            return raw, None, str(raw.claim_id), str(raw.type)
        if not isinstance(raw, Mapping):
            return (
                None,
                {
                    "error": "claim_validation_failed",
                    "validation_error": "claim must be a mapping or PredictionClaim",
                },
                "unknown",
                "unknown",
            )
        raw_claim_id = "unknown"
        raw_claim_type = "unknown"
        try:
            payload = dict(raw)
            raw_claim_id = ClaimScorer._bounded_raw_label(payload.get("claim_id"))
            raw_claim_type = ClaimScorer._bounded_raw_label(
                payload.get("type") or payload.get("claim_type")
            )
            claim = PredictionClaim.model_validate(payload)
            return claim, None, str(claim.claim_id), str(claim.type)
        except ValidationError as exc:
            return (
                None,
                {
                    "error": "claim_validation_failed",
                    "validation_error": ClaimScorer._truncate_detail(str(exc)),
                },
                raw_claim_id,
                raw_claim_type,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - malformed mapping is returned as a deterministic unavailable diagnostic
            diagnostic: Dict[str, Any] = {}
            diagnostic["error"] = "claim_validation_failed"
            diagnostic["validation_error"] = "unexpected_claim_validation_error"
            diagnostic["exception_type"] = type(exc).__name__
            return None, diagnostic, raw_claim_id, raw_claim_type

    @staticmethod
    def _truncate_detail(text: str) -> str:
        cleaned = str(text or "").strip()
        if len(cleaned) <= MAX_VALIDATION_DETAIL_CHARS:
            return cleaned
        return cleaned[: MAX_VALIDATION_DETAIL_CHARS - 3] + "..."

    @staticmethod
    def _bounded_raw_label(value: Any) -> str:
        if not isinstance(value, str):
            return "unknown"
        cleaned = value.strip()
        if not cleaned or len(cleaned) > 128:
            return "unknown"
        return cleaned

    # ------------------------------------------------------------------
    # Per-claim dispatch
    # ------------------------------------------------------------------

    def _score_one(
        self,
        claim: PredictionClaim,
        actuals: ClaimActuals,
        config: ClaimScoreConfig,
    ) -> ClaimScoreResult:
        confidence = float(claim.confidence)

        if actuals.unavailable_reason:
            return self._unavailable(
                claim,
                reason=str(actuals.unavailable_reason),
                confidence=confidence,
            )

        payload = claim.payload
        if claim.type == "direction" and isinstance(payload, DirectionPayload):
            return self._score_direction(claim, payload, actuals, config, confidence)
        if claim.type == "return_bucket" and isinstance(payload, ReturnBucketPayload):
            return self._score_return_bucket(
                claim, payload, actuals, config, confidence
            )
        if claim.type == "level_break" and isinstance(payload, LevelBreakPayload):
            return self._score_level_break(claim, payload, actuals, config, confidence)
        if claim.type == "vol_regime" and isinstance(payload, VolRegimePayload):
            return self._score_vol_regime(claim, payload, actuals, confidence)
        if claim.type == "custom" and isinstance(payload, CustomClaimPayload):
            return self._score_custom(claim, payload, actuals, confidence)
        return self._unavailable(
            claim,
            reason="invalid_claim",
            confidence=confidence,
            details={"error": "payload_type_mismatch", "claim_type": claim.type},
        )

    def _score_direction(
        self,
        claim: PredictionClaim,
        payload: DirectionPayload,
        actuals: ClaimActuals,
        config: ClaimScoreConfig,
        confidence: float,
    ) -> ClaimScoreResult:
        predicted = payload.direction
        realized = self._realized_return(actuals)
        if realized is None:
            return self._unavailable(
                claim,
                reason="missing_prices",
                confidence=confidence,
            )
        return_fraction, return_pct = realized
        epsilon = config.resolved_sideways_epsilon()
        if not self._finite_non_negative(epsilon):
            return self._unavailable(
                claim,
                reason="invalid_config",
                confidence=confidence,
                details={"error": "sideways_epsilon_must_be_finite_non_negative"},
            )

        actual_direction = self._direction_from_return(
            return_fraction,
            sideways_epsilon=epsilon,
        )
        if predicted == actual_direction:
            outcome = OUTCOME_HIT
            reason = "direction_match"
        elif predicted == "sideways" or actual_direction == "sideways":
            outcome = OUTCOME_PARTIAL
            reason = "sideways_boundary_partial"
        else:
            outcome = OUTCOME_MISS
            reason = "direction_opposite"

        return self._result(
            claim,
            outcome,
            reason=reason,
            confidence=confidence,
            realized_return_pct=return_pct,
            actual_direction=actual_direction,
            details={
                "predicted_direction": predicted,
                "sideways_epsilon": epsilon,
                "return_fraction": return_fraction,
            },
        )

    def _score_return_bucket(
        self,
        claim: PredictionClaim,
        payload: ReturnBucketPayload,
        actuals: ClaimActuals,
        config: ClaimScoreConfig,
        confidence: float,
    ) -> ClaimScoreResult:
        if not self._finite_non_negative(config.bucket_partial_margin_pct):
            return self._unavailable(
                claim,
                reason="invalid_config",
                confidence=confidence,
                details={
                    "error": "bucket_partial_margin_pct_must_be_finite_non_negative"
                },
            )

        realized = self._realized_return(actuals)
        if realized is None:
            return self._unavailable(
                claim,
                reason="missing_prices",
                confidence=confidence,
            )
        _, return_pct = realized
        inside = self._in_interval(
            return_pct,
            low=float(payload.low_pct),
            high=float(payload.high_pct),
            inclusive_low=bool(payload.inclusive_low),
            inclusive_high=bool(payload.inclusive_high),
        )
        distance = self._distance_to_interval(
            return_pct,
            low=float(payload.low_pct),
            high=float(payload.high_pct),
            inclusive_low=bool(payload.inclusive_low),
            inclusive_high=bool(payload.inclusive_high),
        )
        margin = float(config.bucket_partial_margin_pct)
        if inside:
            outcome = OUTCOME_HIT
            reason = "return_in_bucket"
        elif distance <= margin and not (distance == 0.0 and margin == 0.0):
            # Distance 0 with zero margin is the open exclusive bound itself:
            # outside the hit interval and not a partial near-miss.
            outcome = OUTCOME_PARTIAL
            reason = "return_near_bucket"
        else:
            outcome = OUTCOME_MISS
            reason = "return_outside_bucket"

        return self._result(
            claim,
            outcome,
            reason=reason,
            confidence=confidence,
            realized_return_pct=return_pct,
            details={
                "low_pct": float(payload.low_pct),
                "high_pct": float(payload.high_pct),
                "inclusive_low": bool(payload.inclusive_low),
                "inclusive_high": bool(payload.inclusive_high),
                "bucket_id": payload.bucket_id,
                "distance_pct": distance,
                "bucket_partial_margin_pct": margin,
            },
        )

    def _score_level_break(
        self,
        claim: PredictionClaim,
        payload: LevelBreakPayload,
        actuals: ClaimActuals,
        config: ClaimScoreConfig,
        confidence: float,
    ) -> ClaimScoreResult:
        if not self._finite_non_negative(config.level_touch_epsilon):
            return self._unavailable(
                claim,
                reason="invalid_config",
                confidence=confidence,
                details={"error": "level_touch_epsilon_must_be_finite_non_negative"},
            )

        level = self._resolve_level(payload, actuals)
        if level is None:
            # Missing start for pct reference, or non-positive absolute level.
            if payload.reference == "pct_from_as_of_close" and (
                self._positive_finite(actuals.start_price) is None
            ):
                return self._unavailable(
                    claim,
                    reason="missing_start_price",
                    confidence=confidence,
                )
            return self._unavailable(
                claim,
                reason="invalid_claim",
                confidence=confidence,
                details={
                    "error": "unresolvable_level",
                    "reference": payload.reference,
                    "level": payload.level,
                },
            )

        high = self._positive_finite(actuals.high_price)
        low = self._positive_finite(actuals.low_price)
        end = self._positive_finite(actuals.end_price)
        if high is None and low is None and end is None:
            return self._unavailable(
                claim,
                reason="missing_prices",
                confidence=confidence,
            )
        touch_band = float(config.level_touch_epsilon) * abs(level)
        side = payload.side
        if side == "above":
            reference = high if high is not None else end
        else:
            reference = low if low is not None else end

        start = self._positive_finite(actuals.start_price)
        if high is not None and (
            (end is not None and high < end) or (start is not None and high < start)
        ):
            return self._unavailable(
                claim,
                reason="invalid_price_path",
                confidence=confidence,
                details={"error": "high_price_below_observed_close"},
            )
        if low is not None and (
            (end is not None and low > end) or (start is not None and low > start)
        ):
            return self._unavailable(
                claim,
                reason="invalid_price_path",
                confidence=confidence,
                details={"error": "low_price_above_observed_close"},
            )
        if high is not None and low is not None and low > high:
            return self._unavailable(
                claim,
                reason="invalid_price_path",
                confidence=confidence,
                details={"error": "low_price_above_high_price"},
            )

        broken = reference is not None and (
            reference >= level if side == "above" else reference <= level
        )

        if broken:
            outcome = OUTCOME_HIT
            reason = "level_broken"
        elif reference is not None and abs(reference - level) <= touch_band:
            outcome = OUTCOME_PARTIAL
            reason = "level_near_touch"
        elif (side == "above" and high is None) or (side == "below" and low is None):
            return self._unavailable(
                claim,
                reason="missing_path_extreme",
                confidence=confidence,
                details={
                    "required": "high_price" if side == "above" else "low_price",
                    "end_price": end,
                    "resolved_level": level,
                },
            )
        else:
            outcome = OUTCOME_MISS
            reason = "level_not_broken"

        realized = self._realized_return(actuals)
        return_pct = None if realized is None else realized[1]
        return self._result(
            claim,
            outcome,
            reason=reason,
            confidence=confidence,
            realized_return_pct=return_pct,
            details={
                "resolved_level": level,
                "break_side": side,
                "reference": payload.reference,
                "payload_level": float(payload.level),
                "high_price": high,
                "low_price": low,
                "end_price": end,
                "touch_band": touch_band,
                "level_touch_epsilon": float(config.level_touch_epsilon),
            },
        )

    def _score_vol_regime(
        self,
        claim: PredictionClaim,
        payload: VolRegimePayload,
        actuals: ClaimActuals,
        confidence: float,
    ) -> ClaimScoreResult:
        actual = str(actuals.vol_regime or "").strip().lower()
        if not actual:
            return self._unavailable(
                claim,
                reason="missing_vol_regime",
                confidence=confidence,
            )
        # Non-canonical labels are incomplete actuals, not a directional miss:
        # a bad ActualsFetcher must not poison hit-rate / calibration.
        if not is_canonical_vol_regime(actual):
            return self._unavailable(
                claim,
                reason="invalid_vol_regime",
                confidence=confidence,
                details={
                    "predicted_regime": payload.regime,
                    "actual_regime": actual,
                },
            )
        predicted = payload.regime
        if predicted == actual:
            outcome = OUTCOME_HIT
            reason = "vol_regime_match"
        elif vol_regimes_adjacent(predicted, actual):
            outcome = OUTCOME_PARTIAL
            reason = "vol_regime_adjacent"
        else:
            outcome = OUTCOME_MISS
            reason = "vol_regime_mismatch"
        return self._result(
            claim,
            outcome,
            reason=reason,
            confidence=confidence,
            details={
                "predicted_regime": predicted,
                "actual_regime": actual,
            },
        )

    def _score_custom(
        self,
        claim: PredictionClaim,
        payload: CustomClaimPayload,
        actuals: ClaimActuals,
        confidence: float,
    ) -> ClaimScoreResult:
        metric = payload.metric
        if metric not in actuals.metrics:
            return self._unavailable(
                claim,
                reason="missing_metric",
                confidence=confidence,
                details={"metric": metric},
            )
        actual_value = actuals.metrics[metric]
        operator = payload.operator
        expected = payload.expected
        expected_high = payload.expected_high

        try:
            matched, partial = self._eval_custom(
                operator=operator,
                actual=actual_value,
                expected=expected,
                expected_high=expected_high,
            )
        except ValueError as exc:
            return self._unavailable(
                claim,
                reason="invalid_metric",
                confidence=confidence,
                details={"error": str(exc), "metric": metric, "operator": operator},
            )

        if matched:
            outcome = OUTCOME_HIT
            reason = "custom_match"
        elif partial:
            outcome = OUTCOME_PARTIAL
            reason = "custom_partial"
        else:
            outcome = OUTCOME_MISS
            reason = "custom_mismatch"

        return self._result(
            claim,
            outcome,
            reason=reason,
            confidence=confidence,
            details={
                "metric": metric,
                "operator": operator,
                "expected": expected,
                "expected_high": expected_high,
                "actual": actual_value,
                "unit": payload.unit,
            },
        )

    @staticmethod
    def _eval_custom(
        *,
        operator: str,
        actual: Union[float, str],
        expected: Union[float, str],
        expected_high: Optional[float],
    ) -> Tuple[bool, bool]:
        """Return (hit, partial). Partial is reserved; custom is binary today."""
        if operator in {"eq", "ne"}:
            if isinstance(actual, bool):
                raise ValueError("eq/ne actual must be a finite number or string")
            if isinstance(actual, str) != isinstance(expected, str):
                raise ValueError("eq/ne operands must have matching scalar types")
            if isinstance(actual, str) and isinstance(expected, str):
                equal = actual == expected
            else:
                actual_n = ClaimScorer._finite_number(actual)
                expected_n = ClaimScorer._finite_number(expected)
                if actual_n is None or expected_n is None:
                    raise ValueError("eq/ne numeric operands must be finite")
                equal = actual_n == expected_n
            return (equal if operator == "eq" else not equal), False

        # Numeric comparison operators. String machine tokens must not be
        # coerced through float(); they are eq/ne labels, not numeric actuals.
        if isinstance(actual, str) or isinstance(expected, str):
            raise ValueError(f"operator {operator} requires finite numeric operands")
        actual_n = ClaimScorer._finite_number(actual)
        expected_n = ClaimScorer._finite_number(expected)
        if actual_n is None or expected_n is None:
            raise ValueError(f"operator {operator} requires finite numeric operands")

        if operator == "gt":
            return actual_n > expected_n, False
        if operator == "gte":
            return actual_n >= expected_n, False
        if operator == "lt":
            return actual_n < expected_n, False
        if operator == "lte":
            return actual_n <= expected_n, False
        if operator == "in_range":
            if expected_high is None or ClaimScorer._finite_number(expected_high) is None:
                raise ValueError("in_range requires finite expected_high")
            high = float(expected_high)
            # Half-open [expected, expected_high) to match default return_bucket.
            return expected_n <= actual_n < high, False
        raise ValueError(f"unsupported operator {operator!r}")

    # ------------------------------------------------------------------
    # Aggregate + calibration
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        results: Sequence[ClaimScoreResult],
        config: ClaimScoreConfig,
    ) -> ClaimScoreAggregate:
        hit = partial = miss = unavailable = 0
        scores: List[float] = []
        confidences: List[float] = []
        targets: List[float] = []
        conf_on_hit: List[float] = []
        conf_on_miss: List[float] = []

        for item in results:
            if item.outcome == OUTCOME_HIT:
                hit += 1
            elif item.outcome == OUTCOME_PARTIAL:
                partial += 1
            elif item.outcome == OUTCOME_MISS:
                miss += 1
            elif item.outcome == OUTCOME_DATA_UNAVAILABLE:
                unavailable += 1

            if item.score is not None:
                scores.append(float(item.score))

            if (
                item.confidence is not None
                and item.score is not None
                and item.outcome != OUTCOME_DATA_UNAVAILABLE
            ):
                confidences.append(float(item.confidence))
                targets.append(float(item.score))
                if item.outcome == OUTCOME_HIT:
                    conf_on_hit.append(float(item.confidence))
                elif item.outcome == OUTCOME_MISS:
                    conf_on_miss.append(float(item.confidence))

        scored = hit + partial + miss
        mean_score = self._mean(scores)
        hit_rate = (float(hit) / float(scored)) if scored else None
        brier = None
        ece = None
        if confidences:
            brier = sum(
                (c - y) * (c - y) for c, y in zip(confidences, targets)
            ) / float(len(confidences))
            ece = self._expected_calibration_error(
                confidences,
                targets,
                bin_count=max(1, int(config.calibration_bin_count)),
            )

        return ClaimScoreAggregate(
            total_claims=len(results),
            scored_claims=scored,
            hit_count=hit,
            partial_count=partial,
            miss_count=miss,
            data_unavailable_count=unavailable,
            mean_score=mean_score,
            hit_rate=hit_rate,
            calibrated_claims=len(confidences),
            mean_confidence=self._mean(confidences),
            brier_score=brier,
            expected_calibration_error=ece,
            mean_confidence_on_hit=self._mean(conf_on_hit),
            mean_confidence_on_miss=self._mean(conf_on_miss),
            scorer_version=config.scorer_version,
        )

    @staticmethod
    def _expected_calibration_error(
        confidences: Sequence[float],
        targets: Sequence[float],
        *,
        bin_count: int,
    ) -> Optional[float]:
        """ECE over equal-width bins on [0, 1]; last bin closed on the right."""
        if not confidences or bin_count < 1:
            return None
        n = len(confidences)
        total = 0.0
        for index in range(bin_count):
            lo = index / float(bin_count)
            hi = (index + 1) / float(bin_count)
            bin_conf: List[float] = []
            bin_tgt: List[float] = []
            for conf, tgt in zip(confidences, targets):
                if index == bin_count - 1:
                    in_bin = lo <= conf <= hi
                else:
                    in_bin = lo <= conf < hi
                if in_bin:
                    bin_conf.append(conf)
                    bin_tgt.append(tgt)
            if not bin_conf:
                continue
            avg_conf = sum(bin_conf) / float(len(bin_conf))
            avg_tgt = sum(bin_tgt) / float(len(bin_tgt))
            total += (len(bin_conf) / float(n)) * abs(avg_conf - avg_tgt)
        return total

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_level(
        self,
        payload: LevelBreakPayload,
        actuals: ClaimActuals,
    ) -> Optional[float]:
        raw_level = self._finite_number(payload.level)
        if raw_level is None:
            return None
        if payload.reference == "absolute_price":
            # Absolute break levels must be positive prices.
            return raw_level if raw_level > 0.0 else None
        # pct_from_as_of_close: level is a percent offset from start/as_of close.
        start = self._positive_finite(actuals.start_price)
        if start is None:
            return None
        return start * (1.0 + raw_level / 100.0)

    def _realized_return(
        self,
        actuals: ClaimActuals,
    ) -> Optional[Tuple[float, float]]:
        start = self._positive_finite(actuals.start_price)
        end = self._positive_finite(actuals.end_price)
        if start is None or end is None:
            return None
        return_fraction = (end - start) / start
        if not math.isfinite(return_fraction):
            return None
        return return_fraction, return_fraction * 100.0

    @staticmethod
    def _direction_from_return(
        return_fraction: float,
        *,
        sideways_epsilon: float,
    ) -> str:
        if abs(return_fraction) <= sideways_epsilon:
            return "sideways"
        if return_fraction > 0.0:
            return "up"
        return "down"

    @staticmethod
    def _in_interval(
        value: float,
        *,
        low: float,
        high: float,
        inclusive_low: bool,
        inclusive_high: bool,
    ) -> bool:
        if inclusive_low:
            if value < low:
                return False
        elif value <= low:
            return False
        if inclusive_high:
            if value > high:
                return False
        elif value >= high:
            return False
        return True

    @staticmethod
    def _distance_to_interval(
        value: float,
        *,
        low: float,
        high: float,
        inclusive_low: bool,
        inclusive_high: bool,
    ) -> float:
        if ClaimScorer._in_interval(
            value,
            low=low,
            high=high,
            inclusive_low=inclusive_low,
            inclusive_high=inclusive_high,
        ):
            return 0.0
        if value < low or (not inclusive_low and value == low):
            return abs(low - value)
        if value > high or (not inclusive_high and value == high):
            return abs(value - high)
        return 0.0

    def _unavailable(
        self,
        claim: PredictionClaim,
        *,
        reason: str,
        confidence: float,
        details: Optional[Mapping[str, Any]] = None,
    ) -> ClaimScoreResult:
        return self._result(
            claim,
            OUTCOME_DATA_UNAVAILABLE,
            reason=reason,
            confidence=confidence,
            score=None,
            score_explicit=True,
            details=details,
        )

    def _result(
        self,
        claim: PredictionClaim,
        outcome: str,
        *,
        reason: str,
        confidence: float,
        score: Optional[float] = None,
        score_explicit: bool = False,
        realized_return_pct: Optional[float] = None,
        actual_direction: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> ClaimScoreResult:
        resolved_score = score if score_explicit else outcome_numeric_score(outcome)
        return ClaimScoreResult(
            claim_id=str(claim.claim_id),
            claim_type=str(claim.type),
            outcome=outcome,
            score=resolved_score,
            reason=reason,
            confidence=confidence,
            realized_return_pct=realized_return_pct,
            actual_direction=actual_direction,
            details=dict(details or {}),
        )

    @staticmethod
    def _positive_finite(value: Any) -> Optional[float]:
        number = ClaimScorer._finite_number(value)
        if number is None or number <= 0.0:
            return None
        return number

    @staticmethod
    def _finite_number(value: Any) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (OverflowError, TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _finite_non_negative(value: Any) -> bool:
        number = ClaimScorer._finite_number(value)
        return number is not None and number >= 0.0

    @staticmethod
    def _mean(values: Sequence[float]) -> Optional[float]:
        if not values:
            return None
        return sum(values) / float(len(values))
