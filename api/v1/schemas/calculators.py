# -*- coding: utf-8 -*-
"""Strict contracts for independent financial calculators (issue #240)."""

from __future__ import annotations

from typing import Annotated, List, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


MAX_MONEY = 1e15
MAX_RATE = 10.0
MAX_YEARS = 100.0


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CompoundGrowthRequest(_StrictModel):
    principal: float = Field(ge=0, le=MAX_MONEY, allow_inf_nan=False)
    annual_rate: float = Field(ge=-MAX_RATE, le=MAX_RATE, allow_inf_nan=False)
    years: float = Field(gt=0, le=MAX_YEARS, allow_inf_nan=False)
    contribution_per_period: float = Field(
        0.0,
        ge=-MAX_MONEY,
        le=MAX_MONEY,
        allow_inf_nan=False,
        description="End-of-period contribution; negative values are withdrawals",
    )
    periods_per_year: int = Field(12, ge=1, le=365)


class BalancePoint(_StrictModel):
    period: int = Field(ge=0)
    balance: float = Field(allow_inf_nan=False)
    total_contributed: float = Field(allow_inf_nan=False)
    gain: float = Field(allow_inf_nan=False)


class CompoundGrowthResponse(_StrictModel):
    status: Literal["ok"]
    principal: float = Field(allow_inf_nan=False)
    annual_rate: float = Field(allow_inf_nan=False)
    years: float = Field(allow_inf_nan=False)
    contribution_per_period: float = Field(allow_inf_nan=False)
    periods_per_year: int
    period_count: int
    period_rate: float = Field(allow_inf_nan=False)
    final_value: float = Field(allow_inf_nan=False)
    total_contributed: float = Field(allow_inf_nan=False)
    total_gain: float = Field(allow_inf_nan=False)
    series_total_points: int = Field(ge=2)
    series_returned_points: int = Field(ge=2, le=241)
    series_sampled: bool
    series_stride: int = Field(ge=1)
    series: List[BalancePoint]


class TargetContributionRequest(_StrictModel):
    target: float = Field(ge=0, le=MAX_MONEY, allow_inf_nan=False)
    principal: float = Field(ge=0, le=MAX_MONEY, allow_inf_nan=False)
    annual_rate: float = Field(ge=-MAX_RATE, le=MAX_RATE, allow_inf_nan=False)
    years: float = Field(gt=0, le=MAX_YEARS, allow_inf_nan=False)
    periods_per_year: int = Field(12, ge=1, le=365)


class _TargetContributionBase(_StrictModel):
    target: float = Field(allow_inf_nan=False)
    principal: float = Field(allow_inf_nan=False)
    annual_rate: float = Field(allow_inf_nan=False)
    years: float = Field(allow_inf_nan=False)
    periods_per_year: int
    period_count: int
    period_rate: float = Field(allow_inf_nan=False)
    currency_precision_digits: Literal[2]
    contribution_rounding: Literal["ceiling"]


class TargetContributionOkResponse(_TargetContributionBase):
    status: Literal["ok"]
    reason_code: Literal["contribution_required"]
    contribution_per_period: float = Field(allow_inf_nan=False)


class TargetContributionAlreadyMetResponse(_TargetContributionBase):
    status: Literal["already_met"]
    reason_code: Literal["principal_growth_meets_target"]
    contribution_per_period: float = Field(allow_inf_nan=False)


class TargetContributionUnreachableResponse(_TargetContributionBase):
    status: Literal["unreachable"]
    reason_code: Literal["target_unreachable"]
    contribution_per_period: None = None


TargetContributionResponse = Annotated[
    Union[
        TargetContributionOkResponse,
        TargetContributionAlreadyMetResponse,
        TargetContributionUnreachableResponse,
    ],
    Field(discriminator="status"),
]


class TargetDurationRequest(_StrictModel):
    target: float = Field(ge=0, le=MAX_MONEY, allow_inf_nan=False)
    principal: float = Field(ge=0, le=MAX_MONEY, allow_inf_nan=False)
    annual_rate: float = Field(ge=-MAX_RATE, le=MAX_RATE, allow_inf_nan=False)
    contribution_per_period: float = Field(
        ge=-MAX_MONEY,
        le=MAX_MONEY,
        allow_inf_nan=False,
        description="End-of-period contribution; negative values are withdrawals",
    )
    periods_per_year: int = Field(12, ge=1, le=365)


class _TargetDurationBase(_StrictModel):
    target: float = Field(allow_inf_nan=False)
    principal: float = Field(allow_inf_nan=False)
    annual_rate: float = Field(allow_inf_nan=False)
    contribution_per_period: float = Field(allow_inf_nan=False)
    periods_per_year: int
    period_rate: float = Field(allow_inf_nan=False)


class TargetDurationOkResponse(_TargetDurationBase):
    status: Literal["ok"]
    reason_code: Literal["duration_solved"]
    period_count: int = Field(ge=1)
    years: float = Field(gt=0, le=MAX_YEARS, allow_inf_nan=False)


class TargetDurationAlreadyMetResponse(_TargetDurationBase):
    status: Literal["already_met"]
    reason_code: Literal["principal_already_meets_target"]
    period_count: Literal[0]
    years: float = Field(ge=0, le=0, allow_inf_nan=False)


class TargetDurationUnreachableResponse(_TargetDurationBase):
    status: Literal["unreachable"]
    reason_code: Literal[
        "non_positive_trajectory",
        "max_years_exceeded",
        "target_unreachable",
    ]
    period_count: None = None
    years: None = None


TargetDurationResponse = Annotated[
    Union[
        TargetDurationOkResponse,
        TargetDurationAlreadyMetResponse,
        TargetDurationUnreachableResponse,
    ],
    Field(discriminator="status"),
]
