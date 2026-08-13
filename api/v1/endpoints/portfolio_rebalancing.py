# -*- coding: utf-8 -*-
"""Read-only portfolio rebalancing recommendations endpoint (issues #237, #126).

Auth contract matches neighboring portfolio routes: global admin-session
middleware when enabled; no extra public exemption.
Suggestions only — never executes trades.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Query

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.portfolio_rebalancing import PortfolioRebalancingResponse
from src.services.portfolio_risk_metrics_service import (
    DEFAULT_CONFIDENCE,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_LOOKBACK_TRADING_DAYS,
    MAX_HORIZON_DAYS,
    MAX_LOOKBACK_TRADING_DAYS,
    MIN_RETURN_OBSERVATIONS,
)
from src.services.portfolio_rebalancing_service import (
    DEFAULT_DRIFT_THRESHOLD_PCT,
    DEFAULT_RISK_TOLERANCE,
    PortfolioRebalancingService,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _bad_request(exc: Exception):
    return api_error(400, "validation_error", str(exc))


@router.get(
    "/rebalancing-recommendations",
    response_model=PortfolioRebalancingResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {
            "model": ErrorResponse,
            "description": "Rebalancing recommendation computation failed",
        },
    },
    summary="Get portfolio rebalancing and position-band recommendations",
    description=(
        "Deterministic risk-band rebalancing suggestions and risk-adjusted position "
        "weight bands from the current portfolio snapshot and portfolio risk metrics. "
        "Suggestions are for human review only and are never auto-executed. "
        "Insufficient history yields an explicit refusal (no invented trades). "
        "Never calls market data providers on the hot path."
    ),
    operation_id="getPortfolioRebalancingRecommendations",
)
def get_portfolio_rebalancing_recommendations(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="As-of date; default today"),
    cost_method: Literal["fifo", "avg"] = Query("fifo"),
    risk_tolerance: Literal["conservative", "moderate", "aggressive"] = Query(
        DEFAULT_RISK_TOLERANCE,
        description="Risk preference band used for caps and target position ranges",
    ),
    drift_threshold_pct: float = Query(
        DEFAULT_DRIFT_THRESHOLD_PCT,
        ge=0.0,
        le=100.0,
        description="Minimum absolute weight drift (percentage points) to emit a suggestion",
    ),
    confidence: float = Query(
        DEFAULT_CONFIDENCE,
        gt=0.5,
        lt=1.0,
        description="VaR confidence forwarded to risk metrics (exclusive of 0.5 and 1.0)",
    ),
    horizon_days: int = Query(
        DEFAULT_HORIZON_DAYS,
        ge=1,
        le=MAX_HORIZON_DAYS,
        description="VaR horizon forwarded to risk metrics",
    ),
    lookback_trading_days: int = Query(
        DEFAULT_LOOKBACK_TRADING_DAYS,
        ge=MIN_RETURN_OBSERVATIONS,
        le=MAX_LOOKBACK_TRADING_DAYS,
        description="Lookback trading days forwarded to risk metrics",
    ),
) -> PortfolioRebalancingResponse:
    service = PortfolioRebalancingService()
    try:
        data = service.get_recommendations(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            risk_tolerance=risk_tolerance,
            drift_threshold_pct=drift_threshold_pct,
            confidence=confidence,
            horizon_days=horizon_days,
            lookback_trading_days=lookback_trading_days,
        )
        return PortfolioRebalancingResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map failures to sanitized API error
        log_safe_exception(
            logger,
            "Get portfolio rebalancing recommendations failed",
            exc,
            error_code="internal_error",
        )
        raise api_error(
            500,
            "internal_error",
            "Get portfolio rebalancing recommendations failed",
        ) from exc
