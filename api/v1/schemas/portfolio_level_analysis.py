# -*- coding: utf-8 -*-
"""Schemas for multi-symbol portfolio-level analysis (issue #128)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StringConstraints,
    field_validator,
    model_validator,
)

from src.services.portfolio_level_analysis_service import (
    DEFAULT_STRESS_SCENARIO_ID,
    HIGH_CORRELATION_THRESHOLD,
    MAX_SYMBOLS,
)
from src.services.portfolio_risk_metrics_service import (
    DEFAULT_CONFIDENCE,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_LOOKBACK_TRADING_DAYS,
    MAX_HORIZON_DAYS,
    MAX_LOOKBACK_TRADING_DAYS,
    MIN_RETURN_OBSERVATIONS,
)

StockCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=1,
        max_length=16,
        pattern=r"^[A-Za-z0-9^][A-Za-z0-9.^_-]{0,15}$",
    ),
]


class StrictPortfolioLevelModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortfolioLevelAnalysisRequest(StrictPortfolioLevelModel):
    stock_codes: List[StockCode] = Field(
        ...,
        min_length=1,
        max_length=MAX_SYMBOLS,
        description=(
            f"Symbols to analyze as one basket (1..{MAX_SYMBOLS}). "
            "Duplicates are rejected."
        ),
    )
    weights: Optional[Dict[StockCode, FiniteFloat]] = Field(
        default=None,
        description=(
            "Optional non-negative weights keyed by stock code. Missing symbols "
            "use equal weight among usable names; weights for degraded symbols "
            "are ignored when rebasing."
        ),
    )
    as_of: Optional[date] = Field(
        default=None,
        description="As-of date for price history and synthetic snapshot; default today",
    )
    lookback_trading_days: int = Field(
        default=DEFAULT_LOOKBACK_TRADING_DAYS,
        ge=MIN_RETURN_OBSERVATIONS,
        le=MAX_LOOKBACK_TRADING_DAYS,
    )
    confidence: float = Field(
        default=DEFAULT_CONFIDENCE,
        gt=0.5,
        lt=1.0,
    )
    horizon_days: int = Field(
        default=DEFAULT_HORIZON_DAYS,
        ge=1,
        le=MAX_HORIZON_DAYS,
    )
    include_stress: bool = Field(
        default=True,
        description="When true, overlay a deterministic stress scenario on the basket",
    )
    scenario_id: str = Field(
        default=DEFAULT_STRESS_SCENARIO_ID,
        min_length=1,
        max_length=64,
    )
    sector_map: Optional[Dict[StockCode, Annotated[str, StringConstraints(min_length=1, max_length=80)]]] = (
        Field(
            default=None,
            description="Optional caller-provided sector labels for shared-risk clustering",
        )
    )
    high_correlation_threshold: float = Field(
        default=HIGH_CORRELATION_THRESHOLD,
        ge=0.0,
        le=1.0,
    )
    currency: Annotated[
        str,
        StringConstraints(strip_whitespace=True, to_upper=True, min_length=3, max_length=8),
    ] = "CNY"

    @field_validator("stock_codes")
    @classmethod
    def reject_duplicate_codes(cls, value: List[str]) -> List[str]:
        normalized = [code.upper() for code in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("stock_codes must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_weight_keys(self) -> "PortfolioLevelAnalysisRequest":
        if self.weights is None:
            return self
        allowed = set(self.stock_codes)
        unknown = [key for key in self.weights if key not in allowed]
        if unknown:
            raise ValueError(
                f"weights contains symbols not in stock_codes: {', '.join(sorted(unknown))}"
            )
        if not any(float(v) > 0 for v in self.weights.values()):
            raise ValueError("weights must include at least one positive value")
        return self


class PortfolioLevelWeightItem(StrictPortfolioLevelModel):
    symbol: StockCode
    weight_pct: FiniteFloat


class PortfolioLevelDegradedSymbol(StrictPortfolioLevelModel):
    stock_code: StockCode
    reason: str = Field(max_length=64)
    detail: Optional[str] = Field(default=None, max_length=256)


class PortfolioLevelCorrelationHighlight(StrictPortfolioLevelModel):
    left: StockCode
    right: StockCode
    correlation: FiniteFloat
    abs_correlation: FiniteFloat
    direction: Literal["positive", "negative"]


class PortfolioLevelSharedRisk(StrictPortfolioLevelModel):
    kind: str = Field(max_length=64)
    symbols: List[StockCode] = Field(default_factory=list, max_length=MAX_SYMBOLS)
    size: Optional[int] = Field(default=None, ge=0)
    summary: str = Field(max_length=512)
    sector: Optional[str] = Field(default=None, max_length=80)
    top_weight_pct: Optional[FiniteFloat] = None
    rank: Optional[int] = Field(default=None, ge=1)


class PortfolioLevelStanceItem(StrictPortfolioLevelModel):
    stock_code: Optional[StockCode] = None
    status: Optional[str] = None
    score: Optional[int] = Field(default=None, ge=0, le=100)
    operation_advice: Optional[str] = Field(default=None, max_length=64)
    freshness: Optional[str] = Field(default=None, max_length=32)


class PortfolioLevelStanceDistribution(StrictPortfolioLevelModel):
    status: str
    status_message: Optional[str] = None
    scored_count: int = 0
    unanalyzed_count: int = 0
    average_score: Optional[FiniteFloat] = None
    by_operation_advice: Dict[str, int] = Field(default_factory=dict)
    items: List[PortfolioLevelStanceItem] = Field(default_factory=list, max_length=MAX_SYMBOLS)
    formula_version: Optional[str] = None


class PortfolioLevelAnalysisResponse(StrictPortfolioLevelModel):
    formula_version: Literal["portfolio_level_analysis_v1"]
    analysis_mode: Literal["portfolio_level_basket"]
    snapshot_kind: Literal["synthetic_basket_v1"]
    as_of: str
    currency: str
    status: str
    status_message: Optional[str] = None
    disclaimer: str
    requested_symbols: List[StockCode] = Field(max_length=MAX_SYMBOLS)
    symbols_used: List[StockCode] = Field(default_factory=list, max_length=MAX_SYMBOLS)
    symbols_requested_count: int = Field(ge=0, le=MAX_SYMBOLS)
    symbols_used_count: int = Field(ge=0, le=MAX_SYMBOLS)
    max_symbols: int = Field(ge=1)
    weighting_mode: str
    weights: List[PortfolioLevelWeightItem] = Field(default_factory=list, max_length=MAX_SYMBOLS)
    degraded_symbols: List[PortfolioLevelDegradedSymbol] = Field(
        default_factory=list, max_length=MAX_SYMBOLS
    )
    annotations: List[str] = Field(default_factory=list, max_length=32)
    correlation: Dict[str, Any] = Field(default_factory=dict)
    correlation_highlights: List[PortfolioLevelCorrelationHighlight] = Field(
        default_factory=list, max_length=32
    )
    concentration: Dict[str, Any] = Field(default_factory=dict)
    var: Dict[str, Any] = Field(default_factory=dict)
    shared_risk_exposures: List[PortfolioLevelSharedRisk] = Field(
        default_factory=list, max_length=32
    )
    stance_distribution: PortfolioLevelStanceDistribution
    health: Dict[str, Any] = Field(default_factory=dict)
    stress: Optional[Dict[str, Any]] = None
    risk_metrics_status: Optional[str] = None
    risk_history: Dict[str, Any] = Field(default_factory=dict)
    assumptions: Dict[str, Any] = Field(default_factory=dict)
    calculated_at: str
