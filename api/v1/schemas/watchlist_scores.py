# -*- coding: utf-8 -*-
"""Strict public schemas for watchlist score aggregation."""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StringConstraints,
    field_validator,
)

WatchlistScoreSort = Literal["manual", "score_desc", "score_asc"]
WatchlistScoreStatus = Literal["scored", "unanalyzed"]
WatchlistScoreFreshness = Literal["none", "unknown", "today", "recent", "stale_week", "stale"]
WatchlistScoreFactorKey = Literal["analysis_sentiment", "decision_signal"]
WatchlistScoreFactorStatus = Literal["applied", "ignored"]
WatchlistScoreDegradationReason = Literal[
    "invalid_sentiment",
    "inactive_signal",
    "expired_signal",
    "incoherent_signal_source",
    "unknown_signal_action",
    "invalid_signal_confidence",
]
StockCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=1,
        max_length=16,
        pattern=r"^[A-Za-z0-9^][A-Za-z0-9.^_-]{0,15}$",
    ),
]
FactorScalar = Union[str, int, FiniteFloat, bool, None]


class StrictScoreModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WatchlistScoreRequest(StrictScoreModel):
    stock_codes: List[StockCode] = Field(default_factory=list, max_length=200)
    sort: WatchlistScoreSort = "manual"

    @field_validator("stock_codes")
    @classmethod
    def reject_duplicate_codes(cls, value: List[str]) -> List[str]:
        normalized = [code.upper() for code in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("stock_codes must not contain duplicates")
        return value


class WatchlistScoreFactorSource(StrictScoreModel):
    id: Optional[int] = Field(default=None, ge=1)
    source_report_id: Optional[int] = Field(default=None, ge=1)
    profile: Optional[str] = Field(default=None, max_length=24)
    as_of: Optional[AwareDatetime] = None
    expires_at: Optional[AwareDatetime] = None
    formula_version: Literal["watchlist_score_v1"]


class WatchlistScoreFactor(StrictScoreModel):
    key: WatchlistScoreFactorKey
    status: WatchlistScoreFactorStatus
    value: Optional[Union[str, int, FiniteFloat]] = None
    params: Dict[str, FactorScalar] = Field(default_factory=dict, max_length=8)
    reason: Optional[WatchlistScoreDegradationReason] = None
    source: WatchlistScoreFactorSource


class WatchlistScoreItem(StrictScoreModel):
    stock_code: StockCode
    status: WatchlistScoreStatus
    score: Optional[int] = Field(default=None, ge=0, le=100)
    as_of: Optional[AwareDatetime] = None
    age_days: Optional[int] = Field(default=None, ge=0, le=365000)
    analysis_id: Optional[int] = Field(default=None, ge=1)
    operation_advice: Optional[str] = Field(default=None, max_length=64)
    factors: List[WatchlistScoreFactor] = Field(default_factory=list, max_length=2)
    freshness: WatchlistScoreFreshness = "none"
    degraded_reasons: List[WatchlistScoreDegradationReason] = Field(
        default_factory=list,
        max_length=2,
    )


class WatchlistScoreQueryCount(StrictScoreModel):
    analysis: int = Field(ge=0, le=1)
    signals: int = Field(ge=0, le=1)


class WatchlistScoreSourceRows(StrictScoreModel):
    analysis: int = Field(ge=0, le=200)
    signals: int = Field(ge=0, le=200)


class WatchlistScoreResponse(StrictScoreModel):
    formula_version: Literal["watchlist_score_v1"]
    scoring_mode: Literal["aggregate_existing"]
    sort: WatchlistScoreSort
    items: List[WatchlistScoreItem] = Field(max_length=200)
    query_count: WatchlistScoreQueryCount
    source_rows: WatchlistScoreSourceRows
    disclaimer_key: Literal["watchlist_score.disclaimer"]
