# -*- coding: utf-8 -*-
"""Schemas for valuation estimate API (issue #238 remaining scope)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ValuationEstimateRequest(BaseModel):
    stock_code: str = Field(..., min_length=1, description="Stock code such as 600519, hk00700, or AAPL")
    growth_rate: Optional[float] = Field(None, description="Optional high-growth rate as a decimal")
    discount_rate: Optional[float] = Field(None, description="Optional discount rate / WACC as a decimal")
    terminal_growth_rate: Optional[float] = Field(None, description="Optional perpetual growth rate as a decimal")
    projection_years: Optional[int] = Field(None, ge=1, le=15, description="Optional projection horizon in years")
    peer_codes: Optional[List[str]] = Field(None, description="Optional peer codes for relative valuation medians")


class ValuationEstimateResponse(BaseModel):
    schema_version: str
    status: str
    stock_code: str
    dcf: Dict[str, Any] = Field(default_factory=dict)
    relative: Dict[str, Any] = Field(default_factory=dict)
    fundamentals_snapshot: Optional[Dict[str, Any]] = None
    disclaimer: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None

    model_config = {"extra": "allow"}
