# -*- coding: utf-8 -*-
"""Schemas for paper-trading process decision quality (Issue #1134)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class PaperDecisionQualityReason(BaseModel):
    dimension: Optional[str] = None
    code: str
    message: str


class PaperDecisionQualityDimension(BaseModel):
    status: Literal["ok", "unavailable"] = "ok"
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    reasons: List[PaperDecisionQualityReason] = Field(default_factory=list)
    inputs: Dict[str, float] = Field(default_factory=dict)


class PaperDecisionQualityItem(BaseModel):
    trade_id: Optional[int] = None
    symbol: Optional[str] = None
    market: Optional[str] = None
    side: Optional[str] = None
    trade_date: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    linked_signal_id: Optional[int] = None
    process_score: float = Field(..., ge=0.0, le=100.0)
    dimensions: Dict[str, PaperDecisionQualityDimension]
    effective_weights: Dict[str, float] = Field(default_factory=dict)
    reasons: List[PaperDecisionQualityReason] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    score_kind: Literal["process"] = "process"
    formula_version: str


class PaperDecisionQualityAggregateDimension(BaseModel):
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    status: Literal["ok", "unavailable"] = "ok"
    sample_size: Optional[int] = None


class PaperDecisionQualityAggregate(BaseModel):
    sample_size: int
    process_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    status: Literal["ok", "empty"] = "ok"
    dimensions: Dict[str, PaperDecisionQualityAggregateDimension] = Field(
        default_factory=dict
    )
    min_process_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    max_process_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)


class PaperDecisionQualityDivisionOfLabor(BaseModel):
    this_issue: int = 1134
    owns: str
    does_not_own: str
    outcome_owner_issue: int = 987


class PaperDecisionQualityResponse(BaseModel):
    score_kind: Literal["process"] = "process"
    formula_version: str
    disclaimer: str
    account_id: int
    account_type: Literal["paper"] = "paper"
    as_of: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    sample_size: int
    aggregate: PaperDecisionQualityAggregate
    items: List[PaperDecisionQualityItem] = Field(default_factory=list)
    division_of_labor: PaperDecisionQualityDivisionOfLabor
