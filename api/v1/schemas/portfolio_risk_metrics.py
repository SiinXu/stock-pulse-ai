# -*- coding: utf-8 -*-
"""Schemas for portfolio risk metrics (issue #239 V0)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PortfolioRiskWeightItem(BaseModel):
    symbol: str
    weight_pct: float


class PortfolioRiskAssumptions(BaseModel):
    var_method: str
    confidence: float
    horizon_days: int
    lookback_trading_days: int
    min_return_observations: int
    min_correlation_observations: int
    return_definition: str
    portfolio_aggregation: str
    cash_excluded: bool
    weight_basis: str
    horizon_scaling: str
    distribution_assumption: str
    correlation_method: str
    concentration_metrics: str
    data_source: str
    provider_calls_on_hot_path: bool


class PortfolioHistoricalVaRBlock(BaseModel):
    status: str = Field(description="'ok', 'insufficient_history', or 'unavailable'")
    status_message: Optional[str] = None
    confidence: Optional[float] = None
    horizon_days: Optional[int] = None
    var_pct: Optional[float] = Field(
        default=None,
        description="Historical VaR as positive loss percentage points (e.g. 3.5 means 3.5%)",
    )
    var_value: Optional[float] = Field(
        default=None,
        description="Historical VaR in portfolio currency units",
    )
    observation_count: int = 0
    percentile_used: Optional[float] = None
    one_day_var_pct: Optional[float] = None


class PortfolioCorrelationBlock(BaseModel):
    status: str = Field(description="'ok', 'insufficient_history', or 'unavailable'")
    status_message: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)
    matrix: List[List[Optional[float]]] = Field(
        default_factory=list,
        description="Pairwise Pearson correlation matrix aligned with symbols",
    )
    observation_count: int = 0


class PortfolioConcentrationBlock(BaseModel):
    status: str = Field(description="'ok' or 'empty_portfolio'")
    hhi: Optional[float] = Field(default=None, description="Herfindahl-Hirschman index of weights")
    effective_n: Optional[float] = Field(default=None, description="1 / HHI")
    diversification_score: Optional[float] = Field(
        default=None,
        description="Normalized diversification score in [0, 1]; equal-weight → 1.0",
    )
    top_weight_pct: Optional[float] = None
    position_count: int = 0
    weights: List[PortfolioRiskWeightItem] = Field(default_factory=list)


class PortfolioRiskHistoryMeta(BaseModel):
    aligned_trading_days: int = 0
    lookback_trading_days_requested: int = 0
    price_series_symbols: List[str] = Field(default_factory=list)
    aligned_start: Optional[str] = None
    aligned_end: Optional[str] = None


class PortfolioRiskMetricsResponse(BaseModel):
    as_of: str
    account_id: Optional[int] = None
    cost_method: str
    currency: str
    status: str = Field(
        description="'ok', 'empty_portfolio', 'insufficient_history', or 'partial'"
    )
    status_message: Optional[str] = None
    portfolio_value: float = 0.0
    positions_used: int = 0
    assumptions: PortfolioRiskAssumptions
    var: PortfolioHistoricalVaRBlock
    correlation: PortfolioCorrelationBlock
    concentration: PortfolioConcentrationBlock
    history: Optional[PortfolioRiskHistoryMeta] = None
