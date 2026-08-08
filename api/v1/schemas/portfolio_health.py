# -*- coding: utf-8 -*-
"""Schemas for daily portfolio health score (issue #151)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PortfolioHealthBand(BaseModel):
    name: str
    min_inclusive: float
    max_exclusive: float


class PortfolioHealthInsight(BaseModel):
    code: str
    severity: str = Field(description="'info' or 'warning'")
    message: str
    symbol: Optional[str] = None
    metric: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None
    source: str = Field(
        default="rule",
        description="'rule' or 'rule+llm_polish' — LLM never changes score fields",
    )


class PortfolioHealthDataQuality(BaseModel):
    status: str
    fx_stale: bool = False
    snapshot_data_quality: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)
    missing_price_symbols: List[str] = Field(default_factory=list)
    risk_metrics_status: Optional[str] = None
    partial_reasons: List[str] = Field(default_factory=list)


class PortfolioHealthInputs(BaseModel):
    top_weight_pct: Optional[float] = None
    var_pct: Optional[float] = None
    diversification_score: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    cash_pct: Optional[float] = None
    total_equity: float = 0.0
    total_cash: float = 0.0
    total_market_value: float = 0.0


class PortfolioHealthResponse(BaseModel):
    as_of: str
    account_id: Optional[int] = None
    cost_method: str
    currency: str
    status: str = Field(
        description="'ok', 'partial', 'empty_portfolio', or 'unavailable'"
    )
    status_message: Optional[str] = None
    score: Optional[float] = Field(
        default=None,
        description="Deterministic 0-100 health score; null when unscorable",
    )
    band: Optional[str] = Field(
        default=None,
        description="'healthy' | 'fair' | 'caution' | 'poor'",
    )
    disclaimer: str
    score_source: str = Field(
        default="rules",
        description="Always 'rules' — LLM cannot modify the score",
    )
    llm_can_modify_score: bool = Field(
        default=False,
        description="Hard contract flag; always false",
    )
    formula_version: str = "portfolio_health_v1"
    weights: Dict[str, float] = Field(default_factory=dict)
    effective_weights: Dict[str, float] = Field(default_factory=dict)
    bands: List[PortfolioHealthBand] = Field(default_factory=list)
    dimensions: Dict[str, Any] = Field(default_factory=dict)
    unavailable_dimensions: List[str] = Field(default_factory=list)
    insights: List[PortfolioHealthInsight] = Field(default_factory=list)
    data_quality: PortfolioHealthDataQuality
    inputs: PortfolioHealthInputs
    persisted: bool = False
