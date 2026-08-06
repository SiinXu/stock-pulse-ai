# -*- coding: utf-8 -*-
"""Read-only portfolio risk metrics endpoint (issue #239 V0).

Auth contract matches neighboring portfolio routes: global admin-session
middleware when enabled; no extra public exemption.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.portfolio_risk_metrics import PortfolioRiskMetricsResponse
from src.services.portfolio_risk_metrics_service import (
    DEFAULT_CONFIDENCE,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_LOOKBACK_TRADING_DAYS,
    MAX_HORIZON_DAYS,
    MAX_LOOKBACK_TRADING_DAYS,
    MIN_RETURN_OBSERVATIONS,
    PortfolioRiskMetricsService,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _bad_request(exc: Exception) -> HTTPException:
    return api_error(400, "validation_error", str(exc))


def _internal_error(message: str, exc: Exception) -> HTTPException:
    log_safe_exception(
        logger,
        message,
        exc,
        error_code="internal_error",
    )
    return api_error(500, "internal_error", message)


@router.get(
    "/risk-metrics",
    response_model=PortfolioRiskMetricsResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {"model": ErrorResponse, "description": "Risk metrics computation failed"},
    },
    summary="Get portfolio risk metrics",
    description=(
        "Historical VaR, pairwise return correlation, and concentration/"
        "diversification metrics from stored daily closes and current holdings. "
        "Never calls market data providers. Insufficient history is reported "
        "explicitly (never silent zeros)."
    ),
    operation_id="getPortfolioRiskMetrics",
)
def get_portfolio_risk_metrics(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="As-of date; default today"),
    cost_method: str = Query("fifo", description="Cost method: fifo or avg"),
    confidence: float = Query(
        DEFAULT_CONFIDENCE,
        gt=0.5,
        lt=1.0,
        description="VaR confidence level exclusive of 0.5 and 1.0 (default 0.95)",
    ),
    horizon_days: int = Query(
        DEFAULT_HORIZON_DAYS,
        ge=1,
        le=MAX_HORIZON_DAYS,
        description="VaR horizon in trading days (1-day base; multi-day uses sqrt-time scaling)",
    ),
    lookback_trading_days: int = Query(
        DEFAULT_LOOKBACK_TRADING_DAYS,
        ge=MIN_RETURN_OBSERVATIONS,
        le=MAX_LOOKBACK_TRADING_DAYS,
        description="Number of trading-day closes requested for the history window",
    ),
) -> PortfolioRiskMetricsResponse:
    service = PortfolioRiskMetricsService()
    try:
        data = service.get_risk_metrics(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            confidence=confidence,
            horizon_days=horizon_days,
            lookback_trading_days=lookback_trading_days,
        )
        return PortfolioRiskMetricsResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map risk metrics failures to a sanitized API error
        raise _internal_error("Get portfolio risk metrics failed", exc)
