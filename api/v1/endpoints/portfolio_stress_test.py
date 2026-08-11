# -*- coding: utf-8 -*-
"""Read-only portfolio stress-test endpoints (issue #158 / T07).

Auth contract matches neighboring portfolio routes: global admin-session
middleware when enabled; no extra public exemption.

Web UI is intentionally out of scope (Portfolio Web surface owned elsewhere).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.portfolio_stress_test import (
    PortfolioStressTestRequest,
    PortfolioStressTestResponse,
    StressScenarioListResponse,
    StressScenarioSummary,
)
from src.services.portfolio_stress_scenarios import (
    DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP,
    ScenarioCatalogUnavailableError,
)
from src.services.portfolio_stress_test_service import PortfolioStressTestService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _bad_request(exc: Exception) -> HTTPException:
    return api_error(400, "validation_error", str(exc))


def _catalog_unavailable(exc: Exception) -> HTTPException:
    return api_error(503, "portfolio_stress_catalog_unavailable", str(exc))


@router.get(
    "/stress-test/scenarios",
    response_model=StressScenarioListResponse,
    responses={
        503: {"model": ErrorResponse, "description": "Scenario catalog unavailable"},
    },
    summary="List portfolio stress scenarios",
    description=(
        "Built-in deterministic factor-shock scenarios plus any overrides loaded "
        "from PORTFOLIO_STRESS_SCENARIOS_PATH. Historical path replay is not "
        "available in this delivery."
    ),
    operation_id="listPortfolioStressScenarios",
)
def list_portfolio_stress_scenarios() -> StressScenarioListResponse:
    service = PortfolioStressTestService()
    try:
        scenarios = service.list_scenarios()
        return StressScenarioListResponse(
            scenarios=[StressScenarioSummary(**item) for item in scenarios],
            simulation_method="deterministic_factor_shock",
            historical_replay_available=False,
        )
    except ScenarioCatalogUnavailableError as exc:
        raise _catalog_unavailable(exc)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitize catalog failures
        log_safe_exception(
            logger,
            "List portfolio stress scenarios failed",
            exc,
            error_code="internal_error",
        )
        raise api_error(
            500,
            "internal_error",
            "List portfolio stress scenarios failed",
        ) from exc


@router.get(
    "/stress-test",
    response_model=PortfolioStressTestResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        503: {"model": ErrorResponse, "description": "Scenario catalog unavailable"},
        500: {"model": ErrorResponse, "description": "Stress test computation failed"},
    },
    summary="Run a built-in portfolio stress scenario",
    description=(
        "Applies a declarative deterministic factor shock to current holdings "
        "and returns estimated PnL impact with explicit assumptions. "
        "Missing beta defaults to 1.0 with status=partial. "
        "Does not call market data providers. Historical replay is not implemented."
    ),
    operation_id="getPortfolioStressTest",
)
def get_portfolio_stress_test(
    scenario_id: str = Query(..., min_length=1, max_length=64, description="Built-in or YAML scenario id"),
    account_id: Optional[int] = Query(None, gt=0, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="As-of date; default today"),
    cost_method: Literal["fifo", "avg"] = Query("fifo", description="Cost method: fifo or avg"),
    target_sector: Optional[str] = Query(
        None,
        min_length=1,
        max_length=80,
        description="Sector presets are POST-only because they also require sector_map",
    ),
    rate_sensitivity_pct_per_100bp: float = Query(
        DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP,
        gt=0,
        le=20,
        allow_inf_nan=False,
        description="Equity return percent points per +100bp rate move (simplified)",
    ),
) -> PortfolioStressTestResponse:
    service = PortfolioStressTestService()
    try:
        data = service.run_stress_test(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            scenario_id=scenario_id,
            target_sector=target_sector,
            rate_sensitivity_pct_per_100bp=rate_sensitivity_pct_per_100bp,
        )
        return PortfolioStressTestResponse(**data)
    except ScenarioCatalogUnavailableError as exc:
        raise _catalog_unavailable(exc)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map stress failures
        log_safe_exception(
            logger,
            "Get portfolio stress test failed",
            exc,
            error_code="internal_error",
        )
        raise api_error(500, "internal_error", "Get portfolio stress test failed") from exc


@router.post(
    "/stress-test",
    response_model=PortfolioStressTestResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request body"},
        503: {"model": ErrorResponse, "description": "Scenario catalog unavailable"},
        500: {"model": ErrorResponse, "description": "Stress test computation failed"},
    },
    summary="Run portfolio stress test with optional custom shocks",
    description=(
        "Same deterministic engine as GET, with optional custom_shocks, "
        "per-symbol betas, and sector_map. Prefer supplying betas/sector_map "
        "to avoid unit-beta and unclassified-sector simplifications."
    ),
    operation_id="postPortfolioStressTest",
)
def post_portfolio_stress_test(
    body: PortfolioStressTestRequest,
) -> PortfolioStressTestResponse:
    service = PortfolioStressTestService()
    try:
        custom_shocks = None
        if body.custom_shocks:
            custom_shocks = [shock.model_dump(exclude_none=True) for shock in body.custom_shocks]
        rate_sens = (
            body.rate_sensitivity_pct_per_100bp
            if body.rate_sensitivity_pct_per_100bp is not None
            else DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP
        )
        data = service.run_stress_test(
            account_id=body.account_id,
            as_of=body.as_of,
            cost_method=body.cost_method,
            scenario_id=body.scenario_id,
            target_sector=body.target_sector,
            betas=body.betas,
            sector_map=body.sector_map,
            custom_shocks=custom_shocks,
            rate_sensitivity_pct_per_100bp=rate_sens,
        )
        return PortfolioStressTestResponse(**data)
    except ScenarioCatalogUnavailableError as exc:
        raise _catalog_unavailable(exc)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map stress failures
        log_safe_exception(
            logger,
            "Post portfolio stress test failed",
            exc,
            error_code="internal_error",
        )
        raise api_error(500, "internal_error", "Post portfolio stress test failed") from exc
