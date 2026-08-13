# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Scoring-facing contracts for deterministic prediction claim evaluation (#1111).

Consumes claim shapes from :mod:`src.schemas.prediction_record` (A1 / #1101).
This module owns **outcomes, actuals, config, and aggregates only** — not
persistence, extraction, or market I/O (A2–A4 / A6–A8).

Product rules (Epic #1107):
- Research / quality-ops framing only — not a guaranteed-returns product.
- Insufficient actuals → ``data_unavailable``; never fabricate a hit.
- Invalid claim payloads → ``data_unavailable``; do not poison model metrics.
- Pure records: no I/O, clock, or randomness.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union


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
MAX_CALIBRATION_BIN_COUNT = 1000

# Canonical vol-regime labels (must match A1 VolRegimeValue).
VOL_REGIME_ORDER: Tuple[str, ...] = ("low", "normal", "high", "elevated")
CANONICAL_VOL_REGIMES = frozenset(VOL_REGIME_ORDER)
# Treat elevated as adjacent to high only.
_VOL_REGIME_ADJACENT = {
    frozenset({"low", "normal"}),
    frozenset({"normal", "high"}),
    frozenset({"high", "elevated"}),
}
# Cap validation diagnostic text kept on claim results (resolver logs / tests).
MAX_VALIDATION_DETAIL_CHARS = 500


@dataclass(frozen=True)
class ClaimScoreConfig:
    """Deterministic scoring thresholds (not environment- or time-derived)."""

    sideways_epsilon: float = DEFAULT_SIDEWAYS_EPSILON
    # Alias kept for issue wording ("flat epsilon"); same units as sideways_epsilon.
    flat_epsilon: Optional[float] = None
    bucket_partial_margin_pct: float = DEFAULT_BUCKET_PARTIAL_MARGIN_PCT
    level_touch_epsilon: float = DEFAULT_LEVEL_TOUCH_EPSILON
    calibration_bin_count: int = DEFAULT_CALIBRATION_BIN_COUNT
    # Engine provenance is code-owned and must not be caller-overridable.
    scorer_version: str = field(default=CLAIM_SCORER_VERSION, init=False)

    def __post_init__(self) -> None:
        for name in (
            "sideways_epsilon",
            "bucket_partial_margin_pct",
            "level_touch_epsilon",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.flat_epsilon is not None and (
            isinstance(self.flat_epsilon, bool)
            or not isinstance(self.flat_epsilon, (int, float))
            or not math.isfinite(float(self.flat_epsilon))
            or float(self.flat_epsilon) < 0.0
        ):
            raise ValueError("flat_epsilon must be a finite non-negative number")
        if (
            isinstance(self.calibration_bin_count, bool)
            or not isinstance(self.calibration_bin_count, int)
            or not 1 <= self.calibration_bin_count <= MAX_CALIBRATION_BIN_COUNT
        ):
            raise ValueError(
                "calibration_bin_count must be an integer between 1 and "
                f"{MAX_CALIBRATION_BIN_COUNT}"
            )

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
        if not isinstance(value, Mapping):
            raise TypeError("claim score config must be a mapping")
        known = {
            item.name
            for item in cls.__dataclass_fields__.values()  # type: ignore[attr-defined]
            if item.init
        }
        unknown = sorted(str(key) for key in value if key not in known)
        if unknown:
            raise ValueError(f"unknown claim score config keys: {', '.join(unknown)}")
        payload = {key: value[key] for key in value}
        return cls(**payload)


@dataclass(frozen=True)
class ClaimActuals:
    """Market realization used to score claims for one prediction horizon.

    Path extremes (``high_price`` / ``low_price``) are required to prove a
    level-break miss. An ``end_price`` can still prove a hit or near-touch.

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
        if not isinstance(value, Mapping):
            raise TypeError("claim actuals must be a mapping or ClaimActuals")
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload: Dict[str, Any] = {key: value[key] for key in value if key in known}

        # Accept A4 ActualsSnapshot mappings without importing the provider-facing
        # schema. Any non-ok status is authoritative even if stale price fields
        # are accidentally present in the payload.
        status = str(value.get("status") or "").strip().lower()
        explicitly_unavailable = value.get("data_unavailable") is True
        explicitly_not_ok = value.get("ok") is False
        if (status and status != "ok") or explicitly_unavailable or explicitly_not_ok:
            payload["unavailable_reason"] = str(
                value.get("reason") or status or "data_unavailable"
            )
        metrics = payload.get("metrics")
        if metrics is None:
            payload["metrics"] = {}
        elif isinstance(metrics, Mapping):
            payload["metrics"] = dict(metrics)
        else:
            # A malformed actuals metric container is missing data, not a
            # scorer crash or evidence that a claim missed.
            payload["metrics"] = {}
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


def is_canonical_vol_regime(value: str) -> bool:
    """Return True when ``value`` is an A1-canonical vol-regime label."""
    return value in CANONICAL_VOL_REGIMES


def vol_regimes_adjacent(a: str, b: str) -> bool:
    """Return True when two *distinct* canonical labels are adjacent for partial.

    Callers must already reject non-canonical labels. Equal labels are not
    adjacent (exact match is handled as hit before this helper is used).
    """
    if a == b:
        return False
    if not (is_canonical_vol_regime(a) and is_canonical_vol_regime(b)):
        return False
    return frozenset({a, b}) in _VOL_REGIME_ADJACENT
