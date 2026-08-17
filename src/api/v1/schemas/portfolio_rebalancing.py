# -*- coding: utf-8 -*-
"""Schemas for portfolio rebalancing and position-band recommendations."""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
WeightPct = Annotated[float, Field(ge=0.0, le=100.0, allow_inf_nan=False)]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]

RiskTolerance = Literal["conservative", "moderate", "aggressive"]
RebalanceStatus = Literal["ok", "empty_portfolio", "insufficient_data", "refused"]
SuggestionAction = Literal["trim", "add", "hold"]
PositionAction = Literal["add", "reduce", "hold", "exit"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PortfolioRebalanceWeightItem(_StrictModel):
    symbol: str = Field(min_length=1, max_length=32)
    weight_pct: WeightPct


class PortfolioRebalanceTargetModel(_StrictModel):
    name: str
    description: str
    max_single_weight_pct: WeightPct
    band_max_single_weight_pct: WeightPct
    soft_max_single_name_weight: UnitFloat
    min_effective_n: FiniteFloat
    max_hhi: UnitFloat
    target_var_pct_ceiling: FiniteFloat
    notes: List[str] = Field(default_factory=list, max_length=32)


class PortfolioRebalanceCurrent(_StrictModel):
    portfolio_value: FiniteFloat = 0.0
    weights: List[PortfolioRebalanceWeightItem] = Field(default_factory=list)
    risk_status: Optional[str] = None
    var_pct: Optional[FiniteFloat] = None
    hhi: Optional[UnitFloat] = None
    effective_n: Optional[FiniteFloat] = None
    diversification_score: Optional[UnitFloat] = None


class PortfolioRebalanceBreach(_StrictModel):
    kind: str = Field(min_length=1, max_length=64)
    symbol: Optional[str] = Field(default=None, max_length=32)
    current_pct: FiniteFloat
    limit_pct: FiniteFloat
    drift_pct: FiniteFloat


class PortfolioRebalanceDrift(_StrictModel):
    max_abs_weight_drift_pct: FiniteFloat = 0.0
    breaches: List[PortfolioRebalanceBreach] = Field(default_factory=list)


class PortfolioRebalanceSuggestion(_StrictModel):
    action: SuggestionAction
    symbol: str = Field(min_length=1, max_length=32)
    from_weight_pct: WeightPct
    to_weight_pct: WeightPct
    delta_weight_pct: FiniteFloat
    approx_notional: FiniteFloat
    rationale: str = Field(min_length=1, max_length=2000)
    assumptions: List[str] = Field(default_factory=list, max_length=32)
    is_suggestion_only: bool = True
    auto_execute: bool = False


class PortfolioPositionBand(_StrictModel):
    symbol: str = Field(min_length=1, max_length=32)
    action: PositionAction
    current_weight_pct: WeightPct
    target_weight_pct_low: WeightPct
    target_weight_pct_mid: WeightPct
    target_weight_pct_high: WeightPct
    effective_cap_pct: WeightPct
    signal: str = Field(min_length=1, max_length=32)
    mode: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=2000)
    assumptions: List[str] = Field(default_factory=list, max_length=32)
    is_suggestion_only: bool = True
    auto_execute: bool = False


class PortfolioRebalanceAssumptions(_StrictModel):
    method: str
    uses_risk_metrics: bool
    risk_metrics_source: str
    provider_calls_on_hot_path: bool
    tax_and_transaction_costs: str
    recommendation_honesty: str
    weight_basis: str
    cross_currency: str
    portfolio_aware_sizing_enabled: bool
    drift_threshold_pct: FiniteFloat


class PortfolioRebalanceRiskSummary(_StrictModel):
    status: str
    var_status: Optional[str] = None
    correlation_status: Optional[str] = None
    concentration_status: Optional[str] = None


class PortfolioRebalancingResponse(_StrictModel):
    as_of: str
    account_id: Optional[int] = None
    cost_method: str
    currency: str
    status: RebalanceStatus
    status_message: Optional[str] = None
    disclaimer: str
    risk_tolerance: RiskTolerance
    is_suggestion_only: bool = True
    auto_execute: bool = False
    target_model: PortfolioRebalanceTargetModel
    current: PortfolioRebalanceCurrent
    drift: PortfolioRebalanceDrift
    suggestions: List[PortfolioRebalanceSuggestion] = Field(default_factory=list)
    position_bands: List[PortfolioPositionBand] = Field(default_factory=list)
    assumptions: PortfolioRebalanceAssumptions
    risk_metrics_summary: PortfolioRebalanceRiskSummary
