# -*- coding: utf-8 -*-
"""Daily portfolio health score endpoint (issue #151).

Auth contract matches neighboring portfolio routes: global admin-session
middleware when enabled; no extra public exemption.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.portfolio_health import PortfolioHealthResponse
from src.services.portfolio_health_service import PortfolioHealthService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _bad_request(exc: Exception):
    return api_error(400, "validation_error", str(exc))


@router.get(
    "/health",
    response_model=PortfolioHealthResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {"model": ErrorResponse, "description": "Health score computation failed"},
    },
    summary="Get daily portfolio health score",
    description=(
        "Deterministic 0-100 portfolio health score with dimension breakdown and "
        "actionable insights. Aggregates existing snapshot and risk-metrics inputs; "
        "never calls market data providers on the hot path. Scores are rule-based "
        "(LLM cannot modify them). Partial data quality is reported explicitly. "
        "This is a structural metric, not investment advice."
    ),
    operation_id="getPortfolioHealth",
)
def get_portfolio_health(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="As-of date; default today"),
    cost_method: str = Query("fifo", description="Cost method: fifo or avg"),
    persist: bool = Query(
        True,
        description="Upsert the daily snapshot (overwrite same day); set false for dry compute",
    ),
) -> PortfolioHealthResponse:
    service = PortfolioHealthService()
    try:
        data = service.get_health(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            persist=persist,
        )
        return PortfolioHealthResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map health failures
        log_safe_exception(
            logger,
            "Get portfolio health failed",
            exc,
            error_code="internal_error",
        )
        raise api_error(500, "internal_error", "Get portfolio health failed") from exc
