# -*- coding: utf-8 -*-
"""Pure Market Light metric helpers.

Issue #1085 step 1 extracts scoring only. Prompt assembly, LLM calls, and
degradation policy remain in ``src.market.analyzer``.
"""

from __future__ import annotations

from typing import Any, Dict


def market_light_status_from_score(score: int) -> str:
    """Map a canonical aggregate score to the traffic-light status."""
    if score >= 60:
        return "green"
    if score >= 40:
        return "yellow"
    return "red"


def _temperature_label(score: int, review_language: str) -> str:
    if review_language == "en":
        if score >= 70:
            return "risk-on"
        if score >= 55:
            return "constructive"
        if score >= 40:
            return "mixed"
        return "defensive"
    if score >= 70:
        return "强势"
    if score >= 55:
        return "偏暖"
    if score >= 40:
        return "震荡"
    return "偏弱"


def build_market_light_scores(
    overview: Any,
    *,
    has_market_stats: bool,
    review_language: str,
) -> Dict[str, Any]:
    """Build the canonical Market Light scores used by reports and alerts."""
    participants = overview.up_count + overview.down_count
    breadth_available = bool(has_market_stats and participants > 0)
    breadth_score = 50
    if breadth_available:
        breadth_score = int(overview.up_count / participants * 100)

    index_changes = [idx.change_pct for idx in overview.indices if idx.change_pct is not None]
    index_available = bool(overview.indices and index_changes)
    index_score = 50
    if index_available:
        avg_change = sum(index_changes) / len(index_changes)
        index_score = int(max(0, min(100, 50 + avg_change * 12)))

    limit_total = overview.limit_up_count + overview.limit_down_count
    limit_available = bool(has_market_stats and limit_total > 0)
    limit_score = 50
    if limit_available:
        limit_score = int(overview.limit_up_count / limit_total * 100)

    dimensions = {
        "breadth": {"score": breadth_score, "available": breadth_available},
        "index": {"score": index_score, "available": index_available},
        "limit": {"score": limit_score, "available": limit_available},
    }

    if not index_available:
        data_quality = "unavailable"
    elif all(dimension["available"] for dimension in dimensions.values()):
        data_quality = "ok"
    else:
        data_quality = "partial"

    score = int(round(breadth_score * 0.45 + index_score * 0.35 + limit_score * 0.20))
    return {
        "score": score,
        "temperature_label": _temperature_label(score, review_language),
        "dimensions": dimensions,
        "data_quality": data_quality,
    }


def build_market_temperature(
    overview: Any,
    *,
    has_market_stats: bool,
    review_language: str,
) -> tuple[int, str]:
    """Return ``(score, temperature_label)`` from the canonical scorer."""
    scores = build_market_light_scores(
        overview,
        has_market_stats=has_market_stats,
        review_language=review_language,
    )
    return int(scores["score"]), str(scores["temperature_label"])


__all__ = (
    "build_market_light_scores",
    "build_market_temperature",
    "market_light_status_from_score",
)
