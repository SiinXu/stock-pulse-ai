# -*- coding: utf-8 -*-
"""Independent financial calculator endpoints (issue #240 / T09).

Auth contract matches neighboring tool routes: global admin-session middleware
when enabled; no portfolio or market-data coupling.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.v1.errors import api_error
from api.v1.schemas.calculators import (
    CompoundGrowthRequest,
    CompoundGrowthResponse,
    TargetContributionRequest,
    TargetContributionResponse,
    TargetDurationRequest,
    TargetDurationResponse,
)
from api.v1.schemas.common import ErrorResponse
from src.services.financial_calculator_service import (
    CalculatorInputError,
    compute_compound_growth,
    solve_target_contribution,
    solve_target_duration,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()

_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid calculator inputs"},
    500: {"model": ErrorResponse, "description": "Calculator computation failed"},
}


def _bad_request(exc: CalculatorInputError) -> HTTPException:
    return api_error(400, exc.code, exc.message)


def _run_compound(body: CompoundGrowthRequest) -> CompoundGrowthResponse:
    data = compute_compound_growth(
        principal=body.principal,
        annual_rate=body.annual_rate,
        years=body.years,
        contribution_per_period=body.contribution_per_period,
        periods_per_year=body.periods_per_year,
    )
    return CompoundGrowthResponse.model_validate(data)


def _run_target_contribution(body: TargetContributionRequest) -> TargetContributionResponse:
    data = solve_target_contribution(
        target=body.target,
        principal=body.principal,
        annual_rate=body.annual_rate,
        years=body.years,
        periods_per_year=body.periods_per_year,
    )
    return TargetContributionResponse.model_validate(data)


def _run_target_duration(body: TargetDurationRequest) -> TargetDurationResponse:
    data = solve_target_duration(
        target=body.target,
        principal=body.principal,
        annual_rate=body.annual_rate,
        contribution_per_period=body.contribution_per_period,
        periods_per_year=body.periods_per_year,
    )
    return TargetDurationResponse.model_validate(data)


@router.post(
    "/compound-growth",
    response_model=CompoundGrowthResponse,
    responses=_ERROR_RESPONSES,
    summary="Compound growth calculator",
    description=(
        "Deterministic compound-growth projection with optional end-of-period "
        "contributions. Pure arithmetic; never calls market data providers."
    ),
    operation_id="postCompoundGrowth",
)
def post_compound_growth(body: CompoundGrowthRequest) -> CompoundGrowthResponse:
    try:
        return _run_compound(body)
    except CalculatorInputError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map unexpected calculator failures to a sanitized API error
        log_safe_exception(
            logger,
            "Compound growth calculation failed",
            exc,
            error_code="internal_error",
        )
        raise api_error(500, "internal_error", "Compound growth calculation failed") from exc


@router.post(
    "/target-contribution",
    response_model=TargetContributionResponse,
    responses=_ERROR_RESPONSES,
    summary="Solve contribution required to reach a target",
    description=(
        "Solves the end-of-period contribution needed to reach a target amount "
        "within a fixed horizon. Unreachable scenarios return status=unreachable "
        "instead of Infinity."
    ),
    operation_id="postTargetContribution",
)
def post_target_contribution(body: TargetContributionRequest) -> TargetContributionResponse:
    try:
        return _run_target_contribution(body)
    except CalculatorInputError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map unexpected calculator failures to a sanitized API error
        log_safe_exception(
            logger,
            "Target contribution calculation failed",
            exc,
            error_code="internal_error",
        )
        raise api_error(
            500,
            "internal_error",
            "Target contribution calculation failed",
        ) from exc


@router.post(
    "/target-duration",
    response_model=TargetDurationResponse,
    responses=_ERROR_RESPONSES,
    summary="Solve periods required to reach a target",
    description=(
        "Solves how many periods are needed to reach a target given principal, "
        "rate, and contribution. Unreachable scenarios return status=unreachable "
        "instead of Infinity."
    ),
    operation_id="postTargetDuration",
)
def post_target_duration(body: TargetDurationRequest) -> TargetDurationResponse:
    try:
        return _run_target_duration(body)
    except CalculatorInputError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map unexpected calculator failures to a sanitized API error
        log_safe_exception(
            logger,
            "Target duration calculation failed",
            exc,
            error_code="internal_error",
        )
        raise api_error(500, "internal_error", "Target duration calculation failed") from exc
