# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fact-versus-opinion field lock for memory and prediction writes (#1124 DAG-1).

System market actuals (PredictionOutcome / decision-signal outcomes) and user
opinion (feedback sidecars, episode labels) must not share write keys. Mixed
payloads are rejected, not stripped and stored as facts.

This module is the DAG-1 contract only. It does not stamp provenance (DAG-3),
reject Soul-boundary markers (DAG-2), or add product feedback APIs (#1105).
"""

from __future__ import annotations

from typing import Any, FrozenSet, Iterable, Mapping, Tuple

# Market actuals and resolver-owned PredictionOutcome keys. These must not
# appear on user-feedback / opinion writes.
FACT_FIELD_NAMES: FrozenSet[str] = frozenset(
    {
        "actual_direction",
        "actuals",
        "anchor_date",
        "claims_json",
        "data_quality_level",
        "direction_correct",
        "direction_expected",
        "end_close",
        "end_price",
        "engine_version",
        "eval_status",
        "eval_window_days",
        "high_price",
        "hit",
        "holding_state",
        "is_hit",
        "label",
        "low_price",
        "max_high",
        "min_low",
        "miss",
        "outcome",
        "outcome_json",
        "plan_quality",
        "prediction_id",
        "prediction_outcome",
        "realized_return_pct",
        "resolved_at",
        "score",
        "scored_at",
        "source_agent",
        "source_type",
        "start_price",
        "stock_return_pct",
        "unable_reason",
        "vol_regime",
        "was_correct",
    }
)

# User-opinion / feedback keys. These must not appear on PredictionOutcome
# actuals or decision-signal outcome writes. Transport ``source`` (web/api) is
# an opinion-sidecar field, not provenance.
OPINION_FIELD_NAMES: FrozenSet[str] = frozenset(
    {
        "agree_hit",
        "agree_miss",
        "context_note",
        "disagree_score",
        "feedback_value",
        "manual_grade",
        "not_useful",
        "note",
        "notes",
        "reason_code",
        "source",
        "useful",
        "user_feedback",
    }
)


class FactOpinionMixError(ValueError):
    """Raised when a write mixes market actuals with user-opinion fields."""


def mixed_fact_opinion_keys(
    payload: Mapping[str, Any],
    *,
    forbidden: Iterable[str],
) -> Tuple[str, ...]:
    """Return sorted top-level keys that collide with ``forbidden``."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    blocked = frozenset(str(name) for name in forbidden)
    return tuple(sorted(str(key) for key in payload if str(key) in blocked))


def lock_fact_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Reject opinion fields on PredictionOutcome / market-actuals writes."""
    mixed = mixed_fact_opinion_keys(payload, forbidden=OPINION_FIELD_NAMES)
    if mixed:
        raise FactOpinionMixError(
            "opinion fields cannot mutate PredictionOutcome actuals: "
            + ", ".join(mixed)
        )
    return payload


def lock_prediction_outcome_actuals(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Alias used by prediction resolve writes for PredictionOutcome actuals."""
    return lock_fact_payload(payload)


def lock_opinion_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Reject market-actuals fields on user-feedback / opinion writes."""
    mixed = mixed_fact_opinion_keys(payload, forbidden=FACT_FIELD_NAMES)
    if mixed:
        raise FactOpinionMixError(
            "fact fields cannot be written through opinion/feedback payloads: "
            + ", ".join(mixed)
        )
    return payload


__all__ = [
    "FACT_FIELD_NAMES",
    "FactOpinionMixError",
    "OPINION_FIELD_NAMES",
    "lock_fact_payload",
    "lock_opinion_payload",
    "lock_prediction_outcome_actuals",
    "mixed_fact_opinion_keys",
]
