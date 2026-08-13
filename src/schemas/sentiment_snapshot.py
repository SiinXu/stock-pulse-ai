# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""First-class sentiment snapshot contract (Issue #179).

Sentiment is supporting evidence for analysis context, not a trading conclusion.
The pipeline scores already-fetched news/event items; it does not introduce
ungoverned external sources.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SENTIMENT_SNAPSHOT_SCHEMA_VERSION: Literal["sentiment-snapshot-v1"] = (
    "sentiment-snapshot-v1"
)

SentimentResultStatus = Literal["available", "degraded", "unavailable"]
SentimentLabel = Literal["bullish", "bearish", "neutral", "mixed", "unclear"]
SentimentFreshness = Literal["fresh", "aging", "stale", "unknown"]
SentimentSourceType = Literal["news", "event", "local_intel", "social"]
SentimentSourceStatus = Literal["available", "partial", "unavailable"]
SentimentAsOfStatus = Literal["present", "missing"]
SentimentRole = Literal["evidence"]

SentimentReasonCode = Literal[
    "ok",
    "partial_coverage",
    "news_source_unavailable",
    "no_data",
    "stale_evidence",
    "unknown_freshness",
    "low_signal",
    "scoring_failed",
]

SENTIMENT_DISCLAIMER = (
    "News- and event-derived sentiment is unverified supporting evidence, "
    "not investment advice or trading authority."
)


class _StrictSentimentModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        str_strip_whitespace=True,
    )


class SentimentEvidenceItem(_StrictSentimentModel):
    """One auditable evidence snippet that contributed to the score."""

    evidence_id: str = Field(min_length=1, max_length=96)
    source_type: SentimentSourceType
    source_id: str = Field(min_length=1, max_length=80)
    dimension: Optional[str] = Field(default=None, max_length=64)
    snippet: str = Field(min_length=1, max_length=400)
    as_of: Optional[str] = Field(default=None, max_length=64)
    as_of_status: SentimentAsOfStatus = "missing"
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    polarity: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    link: Optional[str] = Field(default=None, max_length=400)
    provider: Optional[str] = Field(default=None, max_length=80)


class SentimentSourceSummary(_StrictSentimentModel):
    """Coverage row for one governed input source family."""

    source_id: str = Field(min_length=1, max_length=80)
    source_type: SentimentSourceType
    status: SentimentSourceStatus
    item_count: int = Field(default=0, ge=0, le=500)
    provider: Optional[str] = Field(default=None, max_length=80)
    as_of: Optional[str] = Field(default=None, max_length=64)
    as_of_status: SentimentAsOfStatus = "missing"


class SentimentSnapshot(_StrictSentimentModel):
    """Stable, downstream-consumable sentiment evidence package."""

    schema_version: Literal["sentiment-snapshot-v1"] = SENTIMENT_SNAPSHOT_SCHEMA_VERSION
    role: SentimentRole = "evidence"
    stock_code: str = Field(min_length=1, max_length=32)
    stock_name: Optional[str] = Field(default=None, max_length=120)
    market: Optional[str] = Field(default=None, max_length=32)
    as_of: str = Field(min_length=1, max_length=64)
    window_days: int = Field(default=7, ge=1, le=90)
    status: SentimentResultStatus
    degraded: bool
    reason_code: SentimentReasonCode
    score: Optional[int] = Field(default=None, ge=0, le=100)
    label: SentimentLabel = "unclear"
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_basis: str = Field(default="", max_length=240)
    freshness: SentimentFreshness = "unknown"
    freshness_as_of: Optional[str] = Field(default=None, max_length=64)
    sources: List[SentimentSourceSummary] = Field(default_factory=list, max_length=16)
    evidence: List[SentimentEvidenceItem] = Field(default_factory=list, max_length=24)
    gaps: List[str] = Field(default_factory=list, max_length=12)
    item_count: int = Field(default=0, ge=0, le=500)
    method: Literal["news_lexicon_v1"] = "news_lexicon_v1"
    disclaimer: str = Field(default=SENTIMENT_DISCLAIMER, max_length=320)

    def to_public_dict(self) -> dict:
        """JSON-safe dict for context pack, snapshot, and downstream consumers."""
        return self.model_dump(mode="json")
