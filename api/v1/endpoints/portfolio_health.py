# -*- coding: utf-8 -*-
"""Read-only retrieval and explicit refresh for portfolio health."""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from api.v1.errors import api_error, error_json_response
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.portfolio_health import PortfolioHealthResponse
from src.repositories.base import RepositoryError
from src.services.portfolio_health_service import PortfolioHealthService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _map_repository_error(exc: RepositoryError):
    if exc.error_code == "portfolio_health_migration_required":
        return error_json_response(
            503,
            "portfolio_health_migration_required",
            "Portfolio health storage is unavailable until database migrations are applied.",
        )
    return error_json_response(
        500, "internal_error", "Portfolio health storage failed"
    )


@router.get(
    "/health",
    response_model=PortfolioHealthResponse,
    responses={
        404: {"model": ErrorResponse, "description": "No stored daily health snapshot"},
        503: {"model": ErrorResponse, "description": "Portfolio health migration required"},
        500: {"model": ErrorResponse, "description": "Health snapshot retrieval failed"},
    },
    summary="Get a stored daily portfolio health snapshot",
    description=(
        "Read-only lookup. This endpoint never replays the portfolio and never writes "
        "portfolio caches or health rows. Use POST /health/refresh for explicit computation."
    ),
    operation_id="getPortfolioHealth",
)
def get_portfolio_health(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="Snapshot date; default today"),
    cost_method: Literal["fifo", "avg"] = Query("fifo"),
) -> PortfolioHealthResponse | JSONResponse:
    try:
        service = PortfolioHealthService()
        data = service.get_stored_health(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
        )
        if data is None:
            raise api_error(404, "portfolio_health_not_found", "No stored health snapshot")
        return PortfolioHealthResponse(**data)
    except RepositoryError as exc:
        return _map_repository_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary
        if getattr(exc, "status_code", None) == 404:
            raise
        log_safe_exception(
            logger,
            "Get stored portfolio health failed",
            exc,
            error_code="portfolio_health_get_failed",
        )
        raise api_error(
            500, "portfolio_health_get_failed", "Get stored portfolio health failed"
        ) from exc


@router.post(
    "/health/refresh",
    response_model=PortfolioHealthResponse,
    responses={
        503: {"model": ErrorResponse, "description": "Inputs or migration unavailable"},
        500: {"model": ErrorResponse, "description": "Health score computation failed"},
    },
    summary="Explicitly refresh a daily portfolio health snapshot",
    description=(
        "Replays one side-effect-free portfolio snapshot, passes that immutable input to "
        "risk metrics, and optionally performs one atomic health upsert. With persist=false "
        "the complete operation performs zero writes."
    ),
    operation_id="refreshPortfolioHealth",
)
def refresh_portfolio_health(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="As-of date; default today"),
    cost_method: Literal["fifo", "avg"] = Query("fifo"),
    persist: bool = Query(True, description="Persist one atomic daily health upsert"),
) -> PortfolioHealthResponse | JSONResponse:
    try:
        service = PortfolioHealthService()
        data = service.get_health(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            persist=persist,
        )
        return PortfolioHealthResponse(**data)
    except RepositoryError as exc:
        return _map_repository_error(exc)
    except ValueError as exc:
        log_safe_exception(
            logger,
            "Portfolio health input/configuration rejected",
            exc,
            error_code="portfolio_health_input_invalid",
        )
        return error_json_response(
            503,
            "portfolio_health_input_invalid",
            "Portfolio health inputs or configuration are invalid.",
        )
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary
        log_safe_exception(
            logger,
            "Refresh portfolio health failed",
            exc,
            error_code="portfolio_health_refresh_failed",
        )
        raise api_error(
            500, "portfolio_health_refresh_failed", "Refresh portfolio health failed"
        ) from exc
