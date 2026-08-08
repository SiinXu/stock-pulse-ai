# -*- coding: utf-8 -*-
"""Schemas for watchlist AI score aggregation (Issue #147 / T25)."""

from __future__ import annotations

from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


class WatchlistScoreRequest(BaseModel):
    stock_codes: List[str] = Field(
        default_factory=list,
        description="Ordered watchlist symbols to score (max 200). Empty list returns empty items.",
    )
    sort: str = Field(
        default="manual",
        description="Sort mode: manual (default, preserve input order), score_desc, score_asc",
    )


class WatchlistScoreFactor(BaseModel):
    key: str
    label: str
    value: Union[str, int, float]
    detail: Optional[str] = None


class WatchlistScoreItem(BaseModel):
    stock_code: str
    status: str = Field(description="'scored' or 'unanalyzed'")
    score: Optional[int] = Field(
        default=None,
        description="0-100 composite when scored; null when unanalyzed (never invented as 0)",
    )
    as_of: Optional[str] = None
    age_days: Optional[int] = None
    analysis_id: Optional[int] = None
    operation_advice: Optional[str] = None
    factors: List[WatchlistScoreFactor] = Field(default_factory=list)
    freshness: str = "none"


class WatchlistScoreQueryCount(BaseModel):
    analysis: int
    signals: int


class WatchlistScoreResponse(BaseModel):
    scoring_mode: str
    sort: str
    items: List[WatchlistScoreItem]
    query_count: WatchlistScoreQueryCount
    disclaimer: str
