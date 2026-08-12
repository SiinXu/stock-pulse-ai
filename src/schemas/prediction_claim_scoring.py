# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Scoring-facing contracts for deterministic prediction claim evaluation (#1111).

Consumes claim shapes from :mod:`src.schemas.prediction_record` (A1 / #1101).
This module owns **outcomes, actuals, config, and aggregates only** — not
persistence, extraction, or market I/O (A2–A4 / A6–A8).

Product rules (Epic #1107):
- Research / quality-ops framing only — not a guaranteed-returns product.
- Insufficient actuals → ``data_unavailable``; never fabricate a hit.
- Invalid claim payloads → ``miss`` with reason ``invalid_claim`` (still not a hit).
- Pure records: no I/O, clock, or randomness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


CLAIM_SCORER_VERSION = "claim-scorer-v1"

OUTCOME_HIT = "hit"
OUTCOME_PARTIAL = "partial"
OUTCOME_MISS = "miss"
OUTCOME_DATA_UNAVAILABLE = "data_unavailable"

TERMINAL_SCORED_OUTCOMES: Tuple[str, ...] = (
    OUTCOME_HIT,
    OUTCOME_PARTIAL,
    OUTCOME_MISS,
)

OUTCOME_NUMERIC_SCORE: Dict[str, float] = {
    OUTCOME_HIT: 1.0,
    OUTCOME_PARTIAL: 0.5,
    OUTCOME_MISS: 0.0,
}

# Default: |return fraction| <= 0.1% is treated as sideways.
DEFAULT_SIDEWAYS_EPSILON = 0.001
# Percentage-point gap outside a return bucket that still scores partial.
DEFAULT_BUCKET_PARTIAL_MARGIN_PCT = 1.0
# Relative band (fraction of absolute level) for level-break near-touch partial.
DEFAULT_LEVEL_TOUCH_EPSILON = 0.002
# Equal-width bins for expected calibration error over confidences in [0, 1].
DEFAULT_CALIBRATION_BIN_COUNT = 10

# Adjacent vol-regime partial matrix (research-only labels).
VOL_REGIME_ORDER: Tuple[str, ...] = ("low", "normal", "high", "elevated")
# Treat elevated as adjacent to high only.
_VOL_REGIME_ADJACENT = {
    frozenset({"low", "normal"}),
    frozenset({"normal", "high"}),
    frozenset({"high", "elevated"}),
}


@dataclass(frozen=True)
class ClaimScoreConfig:
    """Deterministic scoring thresholds (not environment- or time-derived)."""

    sideways_epsilon: float = DEFAULT_SIDEWAYS_EPSILON
    # Alias kept for issue wording ("flat epsilon"); same units as sideways_epsilon.
    flat_epsilon: Optional[float] = None
    bucket_partial_margin_pct: float = DEFAULT_BUCKET_PARTIAL_MARGIN_PCT
    level_touch_epsilon: float = DEFAULT_LEVEL_TOUCH_EPSILON
    calibration_bin_count: int = DEFAULT_CALIBRATION_BIN_COUNT
    scorer_version: str = CLAIM_SCORER_VERSION

    def resolved_sideways_epsilon(self) -> float:
        if self.flat_epsilon is not None:
            return float(self.flat_epsilon)
        return float(self.sideways_epsilon)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["sideways_epsilon_resolved"] = self.resolved_sideways_epsilon()
        return data

    @classmethod
    def from_mapping(
        cls,
        value: Optional[Union[Mapping[str, Any], "ClaimScoreConfig"]] = None,
    ) -> "ClaimScoreConfig":
        if value is None:
            return cls()
        if isinstance(value, ClaimScoreConfig):
            return value
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {key: value[key] for key in value if key in known}
        return cls(**payload)


@dataclass(frozen=True)
class ClaimActuals:
    """Market realization used to score claims for one prediction horizon.

    Prefer path extremes (``high_price`` / ``low_price``) for level-break claims.
    When extremes are omitted, level-break falls back to ``end_price`` only.

    ``metrics`` supplies values for ``custom`` claims (metric name → number or
    machine token). ``vol_regime`` is the resolved label for ``vol_regime`` claims.
    """

    start_price: Optional[float] = None
    end_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    vol_regime: Optional[str] = None
    metrics: Dict[str, Union[float, str]] = field(default_factory=dict)
    unavailable_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(
        cls,
        value: Union[Mapping[str, Any], "ClaimActuals"],
    ) -> "ClaimActuals":
        if isinstance(value, ClaimActuals):
            return value
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload: Dict[str, Any] = {key: value[key] for key in value if key in known}
        metrics = payload.get("metrics")
        if metrics is None:
            payload["metrics"] = {}
        elif isinstance(metrics, Mapping):
            payload["metrics"] = dict(metrics)
        return cls(**payload)


@dataclass(frozen=True)
class ClaimScoreResult:
    """Per-claim deterministic outcome."""

    claim_id: str
    claim_type: str
    outcome: str
    score: Optional[float]
    reason: str
    confidence: Optional[float] = None
    realized_return_pct: Optional[float] = None
    actual_direction: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaimScoreAggregate:
    """Roll-up over a claim set (scored claims only for rates and calibration)."""

    total_claims: int
    scored_claims: int
    hit_count: int
    partial_count: int
    miss_count: int
    data_unavailable_count: int
    mean_score: Optional[float]
    hit_rate: Optional[float]
    calibrated_claims: int
    mean_confidence: Optional[float]
    brier_score: Optional[float]
    expected_calibration_error: Optional[float]
    mean_confidence_on_hit: Optional[float]
    mean_confidence_on_miss: Optional[float]
    scorer_version: str = CLAIM_SCORER_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaimScoreReport:
    """Full pure-function result of ClaimScorer.score."""

    claim_results: List[ClaimScoreResult]
    aggregate: ClaimScoreAggregate
    scorer_version: str = CLAIM_SCORER_VERSION
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_results": [item.to_dict() for item in self.claim_results],
            "aggregate": self.aggregate.to_dict(),
            "scorer_version": self.scorer_version,
            "config": dict(self.config),
        }


def outcome_numeric_score(outcome: str) -> Optional[float]:
    """Map a terminal outcome to its numeric score; unscored outcomes return None."""
    return OUTCOME_NUMERIC_SCORE.get(outcome)


def vol_regimes_adjacent(a: str, b: str) -> bool:
    """Return True when two vol-regime labels are adjacent for partial credit."""
    if a == b:
        return True
    return frozenset({a, b}) in _VOL_REGIME_ADJACENT
