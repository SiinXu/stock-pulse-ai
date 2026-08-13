# -*- coding: utf-8 -*-
"""Schemas for LLM usage tracking API."""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field

class CallTypeBreakdown(BaseModel):
    call_type: str = Field(..., description="'analysis' | 'agent' | 'market_review'")
    calls: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int
    estimated_cost_usd: Optional[float] = None

class ModelBreakdown(BaseModel):
    model: str
    calls: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int
    max_total_tokens: int = 0
    estimated_cost_usd: Optional[float] = None

class StageBreakdown(BaseModel):
    stage: str
    calls: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int
    estimated_cost_usd: Optional[float] = None
    success_calls: int = 0
    avg_latency_ms: int = 0

class AgentModeBreakdown(BaseModel):
    agent_mode: str
    calls: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int
    estimated_cost_usd: Optional[float] = None

class UsageCallRecord(BaseModel):
    id: int
    called_at: str = Field(..., description="ISO datetime string")
    call_type: str
    model: str
    stock_code: Optional[str] = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    run_id: Optional[str] = None
    stage: Optional[str] = None
    agent_mode: Optional[str] = None
    estimated_cost_usd: Optional[float] = None
    cost_status: Optional[str] = None
    route_outcome: Optional[str] = None
    route_attempt: Optional[int] = None
    primary_model: Optional[str] = None
    latency_ms: Optional[int] = None
    call_success: Optional[bool] = None

class UsageSummaryResponse(BaseModel):
    period: str = Field(..., description="'today' | 'month' | 'all'")
    from_date: str
    to_date: str
    total_calls: int
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int
    total_estimated_cost_usd: Optional[float] = None
    priced_calls: int = 0
    unpriced_calls: int = 0
    routing_primary_success: int = 0
    routing_fallback_success: int = 0
    routing_failed: int = 0
    routing_success_rate: Optional[float] = None
    routing_fallback_rate: Optional[float] = None
    by_call_type: List[CallTypeBreakdown]
    by_model: List[ModelBreakdown]
    by_stage: List[StageBreakdown] = Field(default_factory=list)
    by_agent_mode: List[AgentModeBreakdown] = Field(default_factory=list)

class UsageDashboardResponse(UsageSummaryResponse):
    recent_calls: List[UsageCallRecord]
