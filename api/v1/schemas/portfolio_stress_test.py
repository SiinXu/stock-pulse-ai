# -*- coding: utf-8 -*-
"""Strict API contracts for deterministic portfolio stress testing."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


FinitePercent = Annotated[float, Field(ge=-100.0, le=100.0, allow_inf_nan=False)]
FiniteRateBp = Annotated[float, Field(ge=-1000.0, le=1000.0, allow_inf_nan=False)]


class MarketStressShock(_StrictModel):
    factor: Literal["market"]
    value_pct: FinitePercent


class SectorStressShock(_StrictModel):
    factor: Literal["sector"]
    value_pct: FinitePercent


class FxStressShock(_StrictModel):
    factor: Literal["fx"]
    value_pct: FinitePercent


class RateStressShock(_StrictModel):
    factor: Literal["rate"]
    value_bp: FiniteRateBp


StressShock = Annotated[
    Union[MarketStressShock, SectorStressShock, FxStressShock, RateStressShock],
    Field(discriminator="factor"),
]


class StressScenarioSummary(_StrictModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    category: Literal["market", "sector", "fx", "rate", "custom"] = "custom"
    shocks: List[StressShock] = Field(min_length=1, max_length=16)
    requires_target_sector: bool = False
    availability: Literal["ready", "requires_parameters"] = "ready"
    source: Literal["built_in", "yaml", "custom_api"]
    version: int = Field(ge=1)
    scenario_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class StressScenarioListResponse(_StrictModel):
    scenarios: List[StressScenarioSummary] = Field(default_factory=list, max_length=64)
    simulation_method: Literal["deterministic_factor_shock"] = (
        "deterministic_factor_shock"
    )
    historical_replay_available: Literal[False] = False


class StressScenarioBlock(StressScenarioSummary):
    target_sector: Optional[str] = Field(default=None, max_length=80)


class StressAssumptions(_StrictModel):
    simulation_method: Literal["deterministic_factor_shock"]
    formula_version: Literal["portfolio_stress_linear_v2"]
    historical_replay: Literal[False] = False
    linear_factor_additivity: Literal[True] = True
    instantaneous_shock: Literal[True] = True
    cash_excluded: Literal[True] = True
    weight_basis: Literal["response_base_market_value"]
    provider_calls_on_hot_path: Literal[False] = False
    beta_policy: str = Field(max_length=120)
    sector_policy: str = Field(max_length=160)
    fx_policy: str = Field(max_length=200)
    rate_policy: str = Field(max_length=300)
    rate_sensitivity_pct_per_100bp: float = Field(
        gt=0, le=20, allow_inf_nan=False
    )
    reuses_risk_metrics_concentration: Literal[True] = True
    data_source: Literal["portfolio_read_only_replay"]
    simplified_assumptions: List[str] = Field(default_factory=list, max_length=32)
    scenario_category: Optional[str] = Field(default=None, max_length=32)


class StressPositionImpact(_StrictModel):
    position_key: str = Field(min_length=1, max_length=200)
    account_id: int
    symbol: str = Field(min_length=1, max_length=64)
    instrument_currency: str = Field(min_length=3, max_length=8)
    account_base_currency: str = Field(min_length=3, max_length=8)
    response_base_currency: str = Field(min_length=3, max_length=8)
    source_market_value: float = Field(ge=0, allow_inf_nan=False)
    market_value: float = Field(ge=0, allow_inf_nan=False)
    valuation_fx_rate_to_account_base: Optional[float] = Field(
        default=None, gt=0, allow_inf_nan=False
    )
    valuation_fx_rate_source: Optional[str] = Field(default=None, max_length=80)
    valuation_fx_rate_method: Optional[
        Literal[
            "zero",
            "identity",
            "direct_rate",
            "inverse_rate",
            "fallback_1_to_1",
            "unknown",
        ]
    ] = None
    valuation_fx_as_of: Optional[date] = None
    valuation_fx_stale: bool = False
    fx_rate_to_response_base: float = Field(gt=0, allow_inf_nan=False)
    fx_rate_source: str = Field(max_length=80)
    fx_rate_method: Literal["zero", "identity", "direct_rate", "inverse_rate", "fallback_1_to_1"]
    fx_as_of: Optional[date] = None
    fx_stale: bool
    weight_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    shock_pct: float = Field(ge=-100, allow_inf_nan=False)
    pnl: float = Field(allow_inf_nan=False)
    stressed_market_value: float = Field(ge=0, allow_inf_nan=False)
    beta_used: Optional[float] = Field(default=None, ge=-5, le=5, allow_inf_nan=False)
    beta_source: Optional[str] = Field(default=None, max_length=80)
    beta_as_of: Optional[date] = None
    sector: Optional[str] = Field(default=None, max_length=80)
    classification_source: Optional[str] = Field(default=None, max_length=80)
    classification_as_of: Optional[date] = None
    price_source: Optional[str] = Field(default=None, max_length=80)
    price_provider: Optional[str] = Field(default=None, max_length=80)
    price_date: Optional[date] = None
    price_stale: bool = False
    price_available: bool = True
    data_quality: Literal["ok", "partial"] = "ok"
    limitations: List[str] = Field(default_factory=list, max_length=32)


class StressExcludedPosition(_StrictModel):
    account_id: int
    symbol: str = Field(min_length=1, max_length=64)
    instrument_currency: str = Field(min_length=3, max_length=8)
    account_base_currency: str = Field(min_length=3, max_length=8)
    response_base_currency: str = Field(min_length=3, max_length=8)
    reason: Literal["price_unavailable", "non_positive_market_value"]
    value_status: Literal["known", "unknown"]
    known_market_value: Optional[float] = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    price_source: Optional[str] = Field(default=None, max_length=80)
    price_date: Optional[date] = None
    limitations: List[str] = Field(default_factory=list, max_length=32)


class StressWeightRow(_StrictModel):
    symbol: str = Field(min_length=1, max_length=200)
    weight_pct: float = Field(ge=0, le=100, allow_inf_nan=False)


class StressConcentrationBlock(_StrictModel):
    status: Literal["ok", "empty_portfolio"]
    hhi: Optional[float] = Field(default=None, allow_inf_nan=False)
    effective_n: Optional[float] = Field(default=None, allow_inf_nan=False)
    diversification_score: Optional[float] = Field(default=None, allow_inf_nan=False)
    top_weight_pct: Optional[float] = Field(default=None, allow_inf_nan=False)
    position_count: int = Field(default=0, ge=0)
    weights: List[StressWeightRow] = Field(default_factory=list, max_length=512)


class PortfolioStressTestResponse(_StrictModel):
    as_of: date
    calculated_at: datetime
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_version: Literal["portfolio_snapshot_v1"]
    account_id: Optional[int] = None
    cost_method: Literal["fifo", "avg"]
    currency: str = Field(min_length=3, max_length=8)
    status: Literal["ok", "empty_portfolio", "partial", "unavailable"]
    status_message: Optional[str] = Field(default=None, max_length=1000)
    portfolio_value: float = Field(default=0, ge=0, allow_inf_nan=False)
    authoritative_portfolio_value: float = Field(default=0, ge=0, allow_inf_nan=False)
    reconciliation_delta: float = Field(default=0, allow_inf_nan=False)
    positions_used: int = Field(default=0, ge=0)
    excluded_position_count: int = Field(default=0, ge=0)
    excluded_known_market_value: float = Field(default=0, ge=0, allow_inf_nan=False)
    excluded_unknown_value_count: int = Field(default=0, ge=0)
    excluded_positions: List[StressExcludedPosition] = Field(
        default_factory=list, max_length=512
    )
    simulation_method: Literal["deterministic_factor_shock"]
    historical_replay_available: Literal[False] = False
    scenario: StressScenarioBlock
    assumptions: StressAssumptions
    snapshot_fx_stale: bool = False
    snapshot_data_quality: Literal["ok", "partial"] = "ok"
    snapshot_limitations: List[str] = Field(default_factory=list, max_length=128)
    missing_data: List[str] = Field(default_factory=list, max_length=128)
    portfolio_pnl: Optional[float] = Field(default=None, allow_inf_nan=False)
    portfolio_pnl_pct: Optional[float] = Field(default=None, allow_inf_nan=False)
    stressed_portfolio_value: Optional[float] = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    position_impacts: List[StressPositionImpact] = Field(default_factory=list, max_length=512)
    top_losers: List[StressPositionImpact] = Field(default_factory=list, max_length=5)
    top_winners: List[StressPositionImpact] = Field(default_factory=list, max_length=5)
    concentration: StressConcentrationBlock


class PortfolioStressTestRequest(_StrictModel):
    """Exactly one preset id or custom shock list is required."""

    account_id: Optional[int] = Field(default=None, gt=0)
    as_of: Optional[date] = None
    cost_method: Literal["fifo", "avg"] = "fifo"
    scenario_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    target_sector: Optional[str] = Field(default=None, min_length=1, max_length=80)
    betas: Optional[Dict[str, float]] = Field(default=None, max_length=256)
    sector_map: Optional[Dict[str, str]] = Field(default=None, max_length=256)
    custom_shocks: Optional[List[StressShock]] = Field(
        default=None, min_length=1, max_length=16
    )
    rate_sensitivity_pct_per_100bp: Optional[float] = Field(
        default=None, gt=0, le=20, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def validate_scenario_selection(self) -> "PortfolioStressTestRequest":
        if (self.scenario_id is None) == (self.custom_shocks is None):
            raise ValueError("exactly one of scenario_id or custom_shocks is required")
        if self.betas:
            for symbol, beta in self.betas.items():
                if not symbol.strip() or len(symbol) > 64:
                    raise ValueError("beta symbols must contain 1-64 characters")
                if not math.isfinite(beta) or not -5.0 <= beta <= 5.0:
                    raise ValueError("beta values must be finite and within [-5, 5]")
        if self.sector_map:
            for symbol, sector in self.sector_map.items():
                if not symbol.strip() or len(symbol) > 64:
                    raise ValueError("sector-map symbols must contain 1-64 characters")
                if not sector.strip() or len(sector) > 80:
                    raise ValueError("sector labels must contain 1-80 characters")
        return self
