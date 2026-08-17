# -*- coding: utf-8 -*-
"""Schemas for portfolio risk metrics (issue #239 V0)."""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field


FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
UnitWeightPct = Annotated[float, Field(ge=0.0, le=100.0, allow_inf_nan=False)]
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
CorrFloat = Annotated[float, Field(ge=-1.0, le=1.0, allow_inf_nan=False)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PortfolioRiskWeightItem(_StrictModel):
    symbol: str
    weight_pct: UnitWeightPct


class PortfolioRiskAssumptions(_StrictModel):
    var_method: str
    confidence: FiniteFloat
    horizon_days: int
    lookback_trading_days: int
    min_return_observations: int
    min_correlation_observations: int
    return_definition: str
    portfolio_aggregation: str
    cash_excluded: bool
    weight_basis: str
    fx_policy: str
    horizon_scaling: str
    distribution_assumption: str
    correlation_method: str
    concentration_metrics: str
    data_source: str
    provider_calls_on_hot_path: bool


class PortfolioHistoricalVaRBlock(_StrictModel):
    status: str = Field(description="'ok', 'insufficient_history', or 'unavailable'")
    status_message: Optional[str] = None
    confidence: Optional[FiniteFloat] = None
    horizon_days: Optional[int] = None
    var_pct: Optional[NonNegFloat] = Field(
        default=None,
        description="Historical VaR as positive loss percentage points (e.g. 3.5 means 3.5%)",
    )
    var_value: Optional[NonNegFloat] = Field(
        default=None,
        description="Historical VaR in portfolio response-base currency units",
    )
    observation_count: int = 0
    percentile_used: Optional[UnitInterval] = None
    one_day_var_pct: Optional[NonNegFloat] = None


class PortfolioCorrelationBlock(_StrictModel):
    status: str = Field(description="'ok', 'insufficient_history', or 'unavailable'")
    status_message: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)
    matrix: List[List[Optional[CorrFloat]]] = Field(
        default_factory=list,
        description="Pairwise Pearson correlation matrix aligned with symbols",
    )
    observation_count: int = 0


class PortfolioConcentrationBlock(_StrictModel):
    status: str = Field(description="'ok' or 'empty_portfolio'")
    hhi: Optional[UnitInterval] = Field(
        default=None, description="Herfindahl-Hirschman index of weights"
    )
    effective_n: Optional[NonNegFloat] = Field(default=None, description="1 / HHI")
    diversification_score: Optional[UnitInterval] = Field(
        default=None,
        description="Normalized diversification score in [0, 1]; equal-weight → 1.0",
    )
    top_weight_pct: Optional[UnitWeightPct] = None
    position_count: int = 0
    weights: List[PortfolioRiskWeightItem] = Field(default_factory=list)


class PortfolioRiskHistoryMeta(_StrictModel):
    aligned_trading_days: int = 0
    lookback_trading_days_requested: int = 0
    price_series_symbols: List[str] = Field(default_factory=list)
    aligned_start: Optional[str] = None
    aligned_end: Optional[str] = None


class PortfolioRiskMetricsResponse(_StrictModel):
    as_of: str
    account_id: Optional[int] = None
    cost_method: str
    currency: str
    status: str = Field(
        description="'ok', 'empty_portfolio', 'insufficient_history', 'partial'"
    )
    status_message: Optional[str] = None
    portfolio_value: NonNegFloat = 0.0
    positions_used: int = 0
    fx_stale: bool = False
    assumptions: PortfolioRiskAssumptions
    var: PortfolioHistoricalVaRBlock
    correlation: PortfolioCorrelationBlock
    concentration: PortfolioConcentrationBlock
    history: Optional[PortfolioRiskHistoryMeta] = None
