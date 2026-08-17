# -*- coding: utf-8 -*-
"""Skill opinion outcome API schemas (read-only surface + explicit run)."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SkillOutcomeHorizon = Literal["1d", "3d", "5d", "10d"]


class SkillOpinionOutcomeRunRequest(BaseModel):
    """Explicit offline evaluation trigger (no new scheduler in V0)."""

    model_config = ConfigDict(extra="forbid")

    sample_id: Optional[int] = Field(None, gt=0)
    analysis_history_id: Optional[int] = Field(None, gt=0)
    skill_id: Optional[str] = Field(None, min_length=1, max_length=128)
    stock_code: Optional[str] = Field(None, min_length=1, max_length=16)
    horizons: Optional[List[SkillOutcomeHorizon]] = None
    limit: int = Field(100, ge=1, le=500)


class SkillOpinionOutcomeRunErrorItem(BaseModel):
    sample_id: Optional[int] = None
    horizon: Optional[str] = None
    error_type: str


class SkillOpinionOutcomeItem(BaseModel):
    id: int
    skill_opinion_sample_id: int
    analysis_history_id: int
    stock_code: str
    skill_id: str
    signal: str
    horizon: str
    engine_version: str
    eval_status: str
    outcome: Optional[str] = None
    direction_correct: Optional[bool] = None
    unable_reason: Optional[str] = None
    analysis_date: Optional[str] = None
    start_trade_date: Optional[str] = None
    end_trade_date: Optional[str] = None
    start_price: Optional[float] = None
    end_close: Optional[float] = None
    stock_return_pct: Optional[float] = None
    directional_return_pct: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SkillOpinionOutcomeRunResponse(BaseModel):
    items: List[SkillOpinionOutcomeItem] = Field(default_factory=list)
    processed_keys: int
    created: int
    updated: int
    skipped: int
    failed: int
    errors: List[SkillOpinionOutcomeRunErrorItem] = Field(default_factory=list)
    histories_scanned: int
    samples_created: int
    limit_unit: str
    engine_version: str


class SkillOpinionOutcomeListResponse(BaseModel):
    items: List[SkillOpinionOutcomeItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    engine_version: str


class SkillOpinionSampleItem(BaseModel):
    id: int
    analysis_history_id: int
    stock_code: str
    skill_id: str
    skill_version: Optional[str] = None
    signal: str
    confidence: float
    horizon: Optional[str] = None
    data_quality_level: Optional[str] = None
    opinion_created_at: Optional[str] = None
    sample_schema_version: str
    created_at: Optional[str] = None


class SkillOpinionSampleListResponse(BaseModel):
    items: List[SkillOpinionSampleItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class SkillOpinionPerformanceBucketItem(BaseModel):
    skill_id: str
    horizon: str
    engine_version: str
    total: int
    pending: int
    evaluated: int
    observational: int
    unable: int
    hit: int
    miss: int
    sample_sufficient: bool
    sample_status: str
    hit_rate_pct: Optional[float] = None
    miss_rate_pct: Optional[float] = None
    avg_directional_return_pct: Optional[float] = None
    unable_rate_pct: Optional[float] = None


class SkillOpinionPerformanceStatsResponse(BaseModel):
    engine_version: str
    minimum_evaluated_sample_size: int
    buckets: List[SkillOpinionPerformanceBucketItem] = Field(
        default_factory=list
    )
