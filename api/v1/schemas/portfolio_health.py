# -*- coding: utf-8 -*-
"""Strict schemas for deterministic portfolio health snapshots."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
ScoreFloat = Annotated[float, Field(ge=0.0, le=100.0, allow_inf_nan=False)]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
HealthBandName = Literal["healthy", "fair", "caution", "poor"]
HealthStatus = Literal["ok", "partial", "empty_portfolio", "unavailable"]
DimensionStatus = Literal["ok", "unavailable"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PortfolioHealthBand(_StrictModel):
    name: HealthBandName
    min_inclusive: ScoreFloat
    max_exclusive: ScoreFloat


class PortfolioHealthInsight(_StrictModel):
    code: str = Field(min_length=1, max_length=96)
    severity: Literal["info", "warning"]
    message: str = Field(min_length=1, max_length=1000)
    symbol: Optional[str] = Field(default=None, max_length=32)
    metric: Optional[str] = Field(default=None, max_length=96)
    value: Optional[FiniteFloat] = None
    threshold: Optional[FiniteFloat] = None
    source: Literal["rule", "rule+llm_polish"] = "rule"


class PortfolioHealthDataQuality(_StrictModel):
    status: Literal["ok", "partial", "empty", "unavailable"]
    fx_stale: bool = False
    snapshot_data_quality: Optional[str] = Field(default=None, max_length=64)
    limitations: List[str] = Field(default_factory=list, max_length=256)
    missing_price_symbols: List[str] = Field(default_factory=list, max_length=256)
    risk_metrics_status: Optional[str] = Field(default=None, max_length=64)
    partial_reasons: List[str] = Field(default_factory=list, max_length=64)


class PortfolioHealthInputs(_StrictModel):
    top_weight_pct: Optional[ScoreFloat] = None
    var_pct: Optional[ScoreFloat] = None
    diversification_score: Optional[UnitFloat] = None
    unrealized_pnl_pct: Optional[FiniteFloat] = None
    cash_pct: Optional[FiniteFloat] = None
    total_equity: FiniteFloat = 0.0
    total_cash: FiniteFloat = 0.0
    total_market_value: FiniteFloat = 0.0


class PortfolioHealthDimension(_StrictModel):
    status: DimensionStatus
    score: Optional[ScoreFloat] = None
    input: Dict[str, FiniteFloat] = Field(default_factory=dict, max_length=8)
    formula: Optional[str] = Field(default=None, max_length=500)
    reason: Optional[str] = Field(default=None, max_length=96)
    status_message: Optional[str] = Field(default=None, max_length=500)


class PortfolioHealthDimensions(_StrictModel):
    concentration: PortfolioHealthDimension
    risk_exposure: PortfolioHealthDimension
    diversification: PortfolioHealthDimension
    pnl: PortfolioHealthDimension
    cash_ratio: PortfolioHealthDimension


class PortfolioHealthWeights(_StrictModel):
    concentration: UnitFloat
    risk_exposure: UnitFloat
    diversification: UnitFloat
    pnl: UnitFloat
    cash_ratio: UnitFloat


class PortfolioHealthEffectiveWeights(_StrictModel):
    concentration: Optional[UnitFloat] = None
    risk_exposure: Optional[UnitFloat] = None
    diversification: Optional[UnitFloat] = None
    pnl: Optional[UnitFloat] = None
    cash_ratio: Optional[UnitFloat] = None


class PortfolioHealthResolvedConfig(_StrictModel):
    weights: PortfolioHealthWeights
    concentration_alert_pct: ScoreFloat
    cash_low_alert_pct: ScoreFloat
    cash_high_alert_pct: ScoreFloat
    var_alert_pct: ScoreFloat
    diversification_alert: UnitFloat
    pnl_loss_alert_pct: Annotated[
        float, Field(ge=-100.0, le=0.0, allow_inf_nan=False)
    ]
    source: Literal["shared_config"]


class PortfolioHealthProvenance(_StrictModel):
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    risk_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    calculated_at: datetime
    risk_history: Dict[str, Any] = Field(default_factory=dict)
    price_provenance: Dict[str, Any] = Field(default_factory=dict)
    fx_provenance: Dict[str, Any] = Field(default_factory=dict)


class PortfolioHealthResponse(_StrictModel):
    as_of: date
    account_id: Optional[int] = None
    cost_method: Literal["fifo", "avg"]
    currency: str = Field(min_length=1, max_length=16)
    status: HealthStatus
    status_message: Optional[str] = Field(default=None, max_length=2000)
    score: Optional[ScoreFloat] = Field(
        default=None,
        description="Comparable deterministic score; null for incomplete coverage.",
    )
    partial_score: Optional[ScoreFloat] = Field(
        default=None,
        description=(
            "Fixed-denominator diagnostic estimate. Missing dimensions contribute zero; "
            "never compare this value with complete daily scores."
        ),
    )
    band: Optional[HealthBandName] = None
    coverage_ratio: UnitFloat
    comparable: bool
    disclaimer: str
    score_source: Literal["rules"] = "rules"
    llm_can_modify_score: Literal[False] = False
    formula_version: Literal["portfolio_health_v2"] = "portfolio_health_v2"
    weights: PortfolioHealthWeights
    effective_weights: PortfolioHealthEffectiveWeights
    bands: List[PortfolioHealthBand] = Field(default_factory=list, max_length=4)
    dimensions: PortfolioHealthDimensions
    unavailable_dimensions: List[
        Literal["concentration", "risk_exposure", "diversification", "pnl", "cash_ratio"]
    ] = Field(default_factory=list, max_length=5)
    insights: List[PortfolioHealthInsight] = Field(default_factory=list, max_length=64)
    data_quality: PortfolioHealthDataQuality
    inputs: PortfolioHealthInputs
    config: PortfolioHealthResolvedConfig
    provenance: PortfolioHealthProvenance
    persisted: bool = False
