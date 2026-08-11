# -*- coding: utf-8 -*-
"""Structured Market Light snapshot schema."""

from __future__ import annotations

import math
from typing import Any, Literal, Mapping

from pydantic import BaseModel, Field


MarketRegion = Literal["cn", "hk", "us", "jp", "kr"]
MarketLightStatus = Literal["green", "yellow", "red"]
MarketLightDataQuality = Literal["ok", "partial", "unavailable"]
MARKET_LIGHT_REGIONS = frozenset(("cn", "hk", "us", "jp", "kr"))
_MARKET_LIGHT_SCORE_REGION_ORDER = ("cn", "hk", "us", "jp", "kr")


def resolve_market_light_sentiment_score(
    snapshots: Mapping[str, Mapping[str, Any]] | None,
    *,
    fallback: int = 50,
) -> int:
    """Aggregate valid canonical snapshot scores for history display."""
    scores: list[float] = []
    if isinstance(snapshots, Mapping):
        for region in _MARKET_LIGHT_SCORE_REGION_ORDER:
            snapshot = snapshots.get(region)
            if not isinstance(snapshot, Mapping):
                continue
            raw_score = snapshot.get("score")
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                continue
            score = float(raw_score)
            if math.isfinite(score):
                scores.append(min(100.0, max(0.0, score)))

    if not scores:
        return fallback
    return math.floor(sum(scores) / len(scores) + 0.5)


class MarketLightDimension(BaseModel):
    """A single Market Light scoring dimension."""

    score: int = Field(ge=0, le=100)
    available: bool


class MarketLightDimensions(BaseModel):
    """Canonical Market Light dimension scores."""

    breadth: MarketLightDimension
    index: MarketLightDimension
    limit: MarketLightDimension


class MarketLightSnapshot(BaseModel):
    """Structured Market Light snapshot persisted and consumed by alerts."""

    region: MarketRegion
    trade_date: str
    status: MarketLightStatus
    score: int = Field(ge=0, le=100)
    label: str
    temperature_label: str
    reasons: list[str]
    guidance: str
    dimensions: MarketLightDimensions
    data_quality: MarketLightDataQuality
