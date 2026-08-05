# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only decision-profile outcome calibration (DecisionSignal stats surface).

Ports the sample-sufficiency-gated profile calibration contract from upstream
decision-profile outcome calibration onto StockPulse DecisionSignal outcomes.
Uses only already-persisted outcome prices; never triggers market reads.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import logging
import math
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from src.schemas.decision_profile import VALID_DECISION_PROFILES
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

MIN_PROFILE_CALIBRATION_SAMPLE_SIZE = 30
PROFILE_SOURCES = frozenset({
    "auto_default",
    "backfill_defaulted",
    "legacy_unknown",
    "user_selected",
})
PROFILE_CALIBRATION_BREAKDOWN_DIMENSIONS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("decision_profile", ("decision_profile",)),
    ("decision_profile_action", ("decision_profile", "action")),
    ("decision_profile_horizon", ("decision_profile", "horizon")),
    ("decision_profile_market_phase", ("decision_profile", "market_phase")),
    (
        "decision_profile_data_quality_level",
        ("decision_profile", "data_quality_level"),
    ),
    ("profile_source", ("profile_source",)),
)

LONG_SIDE_ACTIONS = frozenset({"buy", "add", "hold", "watch", "alert"})
DEFENSIVE_ACTIONS = frozenset({"sell", "reduce", "avoid"})


class OutcomeLike(Protocol):
    """Minimal outcome fields required for profile calibration aggregates."""

    eval_status: Optional[str]
    outcome: Optional[str]
    stock_return_pct: Optional[float]
    unable_reason: Optional[str]
    action: Optional[str]
    horizon: Optional[str]
    market_phase: Optional[str]
    data_quality_level: Optional[str]
    start_price: Optional[float]
    min_low: Optional[float]
    max_high: Optional[float]


class OutcomeStatsSampleLike(Protocol):
    """Outcome row plus live signal fields used only for profile attribution."""

    outcome: OutcomeLike
    decision_profile: Optional[str]
    metadata_json: Optional[str]


def is_decision_profile_calibration_enabled(config: Any = None) -> bool:
    """Return whether the profile-calibration response surface is enabled."""
    if config is None:
        try:
            from src.config import Config

            config = Config.get_instance()
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(
                logger,
                "Failed to load config for decision profile calibration gate",
                exc,
                error_code="decision_profile_calibration_config_unavailable",
                level=logging.WARNING,
            )
            return False
    return bool(getattr(config, "decision_profile_calibration_enabled", False))


def build_profile_calibration(
    stats_rows: Sequence[OutcomeStatsSampleLike],
) -> Dict[str, Any]:
    """Build independent profile-calibration breakdowns for stats rows."""
    samples: List[Dict[str, Any]] = []
    for stats_row in stats_rows:
        outcome = stats_row.outcome
        samples.append({
            "outcome": outcome,
            "decision_profile": normalize_profile_dimension(stats_row.decision_profile),
            "action": str(outcome.action or "unknown"),
            "horizon": str(outcome.horizon or "unknown"),
            "market_phase": str(outcome.market_phase or "unknown"),
            "data_quality_level": str(outcome.data_quality_level or "unknown"),
            "profile_source": normalize_profile_source(stats_row.metadata_json),
        })
    breakdowns = {
        name: profile_calibration_breakdown(samples, dimensions)
        for name, dimensions in PROFILE_CALIBRATION_BREAKDOWN_DIMENSIONS
    }
    return {
        "minimum_completed_sample_size": MIN_PROFILE_CALIBRATION_SAMPLE_SIZE,
        "breakdowns": breakdowns,
    }


def empty_profile_calibration() -> Dict[str, Any]:
    """Cold-start empty calibration payload with the fixed six breakdown keys."""
    return {
        "minimum_completed_sample_size": MIN_PROFILE_CALIBRATION_SAMPLE_SIZE,
        "breakdowns": {
            name: []
            for name, _dimensions in PROFILE_CALIBRATION_BREAKDOWN_DIMENSIONS
        },
    }


def profile_calibration_breakdown(
    samples: Sequence[Mapping[str, Any]],
    dimensions: Sequence[str],
) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, ...], List[Any]] = defaultdict(list)
    for sample in samples:
        key = tuple(str(sample.get(dimension) or "unknown") for dimension in dimensions)
        grouped[key].append(sample["outcome"])

    buckets = [
        {
            "dimensions": dict(zip(dimensions, values)),
            **profile_calibration_aggregate(rows),
        }
        for values, rows in grouped.items()
    ]
    return sorted(
        buckets,
        key=lambda item: (
            -int(item["total"]),
            tuple(str(item["dimensions"][dimension]) for dimension in dimensions),
        ),
    )


def profile_calibration_aggregate(rows: Sequence[Any]) -> Dict[str, Any]:
    aggregate = _aggregate_outcome_rows(rows)
    sample_sufficient = int(aggregate["completed"]) >= MIN_PROFILE_CALIBRATION_SAMPLE_SIZE
    direction_denominator = int(aggregate["hit"]) + int(aggregate["miss"])
    adverse_excursions = [
        value
        for row in rows
        if (value := row_max_adverse_excursion_pct(row)) is not None
    ]
    return {
        "total": aggregate["total"],
        "completed": aggregate["completed"],
        "unable": aggregate["unable"],
        "hit": aggregate["hit"],
        "miss": aggregate["miss"],
        "neutral": aggregate["neutral"],
        "sample_sufficient": sample_sufficient,
        "hit_rate_pct": aggregate["hit_rate_pct"] if sample_sufficient else None,
        "avg_stock_return_pct": (
            aggregate["avg_stock_return_pct"] if sample_sufficient else None
        ),
        "miss_rate_pct": (
            round(int(aggregate["miss"]) / direction_denominator * 100, 2)
            if sample_sufficient and direction_denominator
            else None
        ),
        "unable_rate_pct": (
            round(int(aggregate["unable"]) / int(aggregate["total"]) * 100, 2)
            if sample_sufficient and int(aggregate["total"])
            else None
        ),
        "max_adverse_excursion_pct": (
            round(max(adverse_excursions), 4)
            if sample_sufficient and adverse_excursions
            else None
        ),
    }


def row_max_adverse_excursion_pct(row: Any) -> Optional[float]:
    """Compute max adverse excursion from persisted prices only."""
    if not _is_positive_finite(getattr(row, "start_price", None)):
        return None
    start_price = float(row.start_price)
    action = str(getattr(row, "action", None) or "")
    if action in LONG_SIDE_ACTIONS:
        if not _is_positive_finite(getattr(row, "min_low", None)):
            return None
        return max(0.0, (start_price - float(row.min_low)) / start_price * 100)
    if action in DEFENSIVE_ACTIONS:
        if not _is_positive_finite(getattr(row, "max_high", None)):
            return None
        return max(0.0, (float(row.max_high) - start_price) / start_price * 100)
    return None


def normalize_profile_dimension(value: Any) -> str:
    profile = str(value or "").strip().lower()
    return profile if profile in VALID_DECISION_PROFILES else "unknown"


def normalize_profile_source(metadata_json: Optional[str]) -> str:
    metadata = _json_loads(metadata_json)
    if not isinstance(metadata, dict):
        return "unknown"
    profile_source = str(metadata.get("profile_source") or "").strip().lower()
    return profile_source if profile_source in PROFILE_SOURCES else "unknown"


def _aggregate_outcome_rows(rows: Sequence[Any]) -> Dict[str, Any]:
    total = len(rows)
    completed = [row for row in rows if getattr(row, "eval_status", None) == "completed"]
    unable = [row for row in rows if getattr(row, "eval_status", None) == "unable"]
    hit = sum(1 for row in completed if getattr(row, "outcome", None) == "hit")
    miss = sum(1 for row in completed if getattr(row, "outcome", None) == "miss")
    neutral = sum(1 for row in completed if getattr(row, "outcome", None) == "neutral")
    denominator = hit + miss
    returns = [
        float(row.stock_return_pct)
        for row in completed
        if getattr(row, "stock_return_pct", None) is not None
    ]
    unable_reasons = Counter(
        getattr(row, "unable_reason", None) or "unknown" for row in unable
    )
    return {
        "total": total,
        "completed": len(completed),
        "unable": len(unable),
        "hit": hit,
        "miss": miss,
        "neutral": neutral,
        "hit_rate_pct": round(hit / denominator * 100, 2) if denominator else None,
        "avg_stock_return_pct": (
            round(sum(returns) / len(returns), 4) if returns else None
        ),
        "unable_reasons": dict(sorted(unable_reasons.items())),
    }


def _is_positive_finite(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _json_loads(value: Optional[str]) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        log_safe_exception(
            logger,
            "Decision signal sidecar source JSON is invalid",
            exc,
            error_code="decision_signal_sidecar_json_invalid",
            level=logging.WARNING,
        )
        return None
