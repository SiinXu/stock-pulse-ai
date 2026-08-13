# -*- coding: utf-8 -*-
"""Schemas for valuation estimate API (issue #238 remaining scope).

Peer relative-value canvas request/response contracts live here for issue #1139.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

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


class PeerValuationCanvasRequest(BaseModel):
    """Request body for the constrained peer relative-value canvas (issue #1139)."""

    stock_code: str = Field(..., min_length=1, description="Target stock code")
    peer_source: Literal["custom", "industry"] = Field(
        "custom",
        description="Explainable peer-set source: custom codes or industry-constrained set",
    )
    peer_codes: Optional[List[str]] = Field(
        None,
        description="Peer stock codes (required for comparison; never invented server-side)",
    )
    industry_label: Optional[str] = Field(
        None,
        description="Optional industry label override when peer_source=industry",
    )
    base_currency: Optional[str] = Field(
        None,
        description="Base currency for cross-market estimate normalization (default: target listing currency)",
    )


class PeerValuationCanvasResponse(BaseModel):
    schema_version: str
    status: str
    stock_code: Optional[str] = None
    base_currency: Optional[str] = None
    fx_stale: Optional[bool] = None
    peer_set: Optional[Dict[str, Any]] = None
    metrics: List[str] = Field(default_factory=list)
    multiple_metrics: Optional[List[str]] = None
    currency_metrics: Optional[List[str]] = None
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    medians: Optional[Dict[str, Any]] = None
    relative_summary: Optional[Dict[str, Any]] = None
    heatmap_cells: Optional[List[Dict[str, Any]]] = None
    valuation_status: Optional[str] = None
    disclaimer: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None

    model_config = {"extra": "allow"}
