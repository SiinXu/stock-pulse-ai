# -*- coding: utf-8 -*-
"""Schemas for independent financial calculators (issue #240)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class CompoundGrowthRequest(BaseModel):
    principal: float = Field(..., description="Starting principal amount")
    annual_rate: float = Field(
        ...,
        description="Nominal annual rate as a decimal (0.07 = 7%). May be zero or negative.",
    )
    years: float = Field(..., gt=0, description="Investment horizon in years")
    contribution_per_period: float = Field(
        0.0,
        description="End-of-period contribution (may be negative for withdrawals)",
    )
    periods_per_year: int = Field(
        12,
        ge=1,
        le=365,
        description="Compounding / contribution frequency per year",
    )


class BalancePoint(BaseModel):
    period: int
    balance: float
    total_contributed: float
    gain: float


class CompoundGrowthResponse(BaseModel):
    status: str = Field(description="'ok'")
    principal: float
    annual_rate: float
    years: float
    contribution_per_period: float
    periods_per_year: int
    period_count: int
    period_rate: float
    final_value: float
    total_contributed: float
    total_gain: float
    series: List[BalancePoint]


class TargetContributionRequest(BaseModel):
    target: float = Field(..., description="Target terminal amount")
    principal: float = Field(..., description="Starting principal amount")
    annual_rate: float = Field(..., description="Nominal annual rate as a decimal")
    years: float = Field(..., gt=0, description="Investment horizon in years")
    periods_per_year: int = Field(12, ge=1, le=365)


class TargetContributionResponse(BaseModel):
    status: str = Field(description="'ok', 'already_met', or 'unreachable'")
    target: float
    principal: float
    annual_rate: float
    years: float
    periods_per_year: int
    period_count: int
    period_rate: float
    contribution_per_period: Optional[float] = None
    message: Optional[str] = None


class TargetDurationRequest(BaseModel):
    target: float = Field(..., description="Target terminal amount")
    principal: float = Field(..., description="Starting principal amount")
    annual_rate: float = Field(..., description="Nominal annual rate as a decimal")
    contribution_per_period: float = Field(
        ...,
        description="End-of-period contribution (may be negative)",
    )
    periods_per_year: int = Field(12, ge=1, le=365)


class TargetDurationResponse(BaseModel):
    status: str = Field(description="'ok', 'already_met', or 'unreachable'")
    target: float
    principal: float
    annual_rate: float
    contribution_per_period: float
    periods_per_year: int
    period_rate: float
    period_count: Optional[int] = None
    years: Optional[float] = None
    message: Optional[str] = None
