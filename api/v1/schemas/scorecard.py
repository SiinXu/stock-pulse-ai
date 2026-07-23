# -*- coding: utf-8 -*-
"""Public signal scorecard response schemas (Issue #379)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ScorecardBucket(BaseModel):
    signal_type: str
    horizon: str
    status: str = Field(description="'ok' or 'insufficient_data'")
    sample_size: int
    completed: int
    hit_rate_pct: Optional[float] = None
    avg_return_pct: Optional[float] = None


class ScorecardOverall(BaseModel):
    status: str
    sample_size: int
    completed: int
    hit_rate_pct: Optional[float] = None
    avg_return_pct: Optional[float] = None


class ScorecardReturnBand(BaseModel):
    band: str
    count: int
    share_pct: Optional[float] = None


class ScorecardMiss(BaseModel):
    signal_type: str
    horizon: str
    return_pct: Optional[float] = None
    anchor_date: Optional[str] = None


class SignalScorecardResponse(BaseModel):
    min_samples: int
    overall: ScorecardOverall
    by_signal_type_horizon: List[ScorecardBucket]
    return_distribution: List[ScorecardReturnBand]
    recent_misses: List[ScorecardMiss]
