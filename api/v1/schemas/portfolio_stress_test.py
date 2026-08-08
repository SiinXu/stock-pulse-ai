# -*- coding: utf-8 -*-
"""Schemas for portfolio stress testing (issue #158 / T07)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StressShock(BaseModel):
    factor: str = Field(description="market | sector | fx | rate")
    value_pct: Optional[float] = Field(
        default=None,
        description="Shock magnitude in percent points (market/sector/fx)",
    )
    value_bp: Optional[float] = Field(
        default=None,
        description="Shock magnitude in basis points (rate factor)",
    )


class StressScenarioSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "custom"
    shocks: List[StressShock] = Field(default_factory=list)
    requires_target_sector: bool = False


class StressScenarioListResponse(BaseModel):
    scenarios: List[StressScenarioSummary] = Field(default_factory=list)
    simulation_method: str = "deterministic_factor_shock"
    historical_replay_available: bool = False


class StressScenarioBlock(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "custom"
    shocks: List[StressShock] = Field(default_factory=list)
    target_sector: Optional[str] = None


class StressAssumptions(BaseModel):
    simulation_method: str
    historical_replay: bool = False
    linear_factor_additivity: bool = True
    instantaneous_shock: bool = True
    cash_excluded: bool = True
    weight_basis: str
    provider_calls_on_hot_path: bool = False
    beta_policy: str
    sector_policy: str
    fx_policy: str
    rate_policy: str
    rate_sensitivity_pct_per_100bp: float
    reuses_risk_metrics_concentration: bool = True
    data_source: str
    simplified_assumptions: List[str] = Field(default_factory=list)
    scenario_category: Optional[str] = None


class StressPositionImpact(BaseModel):
    symbol: str
    market_value: float
    weight_pct: float
    shock_pct: float
    pnl: float
    stressed_market_value: float
    beta_used: Optional[float] = None
    beta_source: Optional[str] = None
    sector: Optional[str] = None
    valuation_currency: Optional[str] = None


class StressConcentrationBlock(BaseModel):
    status: str
    hhi: Optional[float] = None
    effective_n: Optional[float] = None
    diversification_score: Optional[float] = None
    top_weight_pct: Optional[float] = None
    position_count: int = 0
    weights: List[Dict[str, Any]] = Field(default_factory=list)


class PortfolioStressTestResponse(BaseModel):
    as_of: str
    account_id: Optional[int] = None
    cost_method: str
    currency: str
    status: str = Field(
        description="'ok', 'empty_portfolio', or 'partial'",
    )
    status_message: Optional[str] = None
    portfolio_value: float = 0.0
    positions_used: int = 0
    simulation_method: str = "deterministic_factor_shock"
    historical_replay_available: bool = False
    scenario: StressScenarioBlock
    assumptions: StressAssumptions
    missing_data: List[str] = Field(default_factory=list)
    portfolio_pnl: Optional[float] = None
    portfolio_pnl_pct: Optional[float] = None
    stressed_portfolio_value: Optional[float] = None
    position_impacts: List[StressPositionImpact] = Field(default_factory=list)
    top_losers: List[StressPositionImpact] = Field(default_factory=list)
    top_winners: List[StressPositionImpact] = Field(default_factory=list)
    concentration: StressConcentrationBlock


class PortfolioStressTestRequest(BaseModel):
    """Optional body for POST custom / overridden stress runs."""

    account_id: Optional[int] = None
    as_of: Optional[str] = Field(
        default=None,
        description="ISO date YYYY-MM-DD; default today",
    )
    cost_method: str = "fifo"
    scenario_id: Optional[str] = Field(
        default=None,
        description="Built-in or YAML scenario id; omit when custom_shocks is set",
    )
    target_sector: Optional[str] = Field(
        default=None,
        description="Required for sector scenarios",
    )
    betas: Optional[Dict[str, float]] = Field(
        default=None,
        description="Optional per-symbol market beta; missing names use beta=1 with label",
    )
    sector_map: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional per-symbol sector labels for sector shocks",
    )
    custom_shocks: Optional[List[StressShock]] = Field(
        default=None,
        description="When set, builds a custom scenario instead of a preset id",
    )
    rate_sensitivity_pct_per_100bp: Optional[float] = Field(
        default=None,
        description="Override default equity sensitivity to rate moves",
        gt=0,
    )
