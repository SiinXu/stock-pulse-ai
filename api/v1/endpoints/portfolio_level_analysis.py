# -*- coding: utf-8 -*-
"""Portfolio-level multi-symbol analysis endpoint (issue #128).

Auth contract matches neighboring analysis/portfolio routes: global admin-session
middleware when enabled; no extra public exemption.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.portfolio_level_analysis import (
    PortfolioLevelAnalysisRequest,
    PortfolioLevelAnalysisResponse,
)
from src.services.portfolio_level_analysis_service import (
    MAX_SYMBOLS,
    PortfolioLevelAnalysisService,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/portfolio",
    response_model=PortfolioLevelAnalysisResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Portfolio-level analysis failed"},
    },
    summary="Run portfolio-level analysis for a multi-symbol basket",
    description=(
        "Analyze a list of symbols as one portfolio rather than stacking per-symbol "
        "conclusions. Returns correlation highlights, concentration/diversification, "
        "shared risk exposures, stance distribution from existing analyses, structural "
        f"health, and an optional stress overlay. At most {MAX_SYMBOLS} symbols. "
        "Missing single-symbol price data degrades the result (status=partial) and never "
        "fails the whole request. Reuses the portfolio health and stress-test data planes "
        "via a synthetic equal/custom-weight snapshot — no separate holdings model."
    ),
    operation_id="analyzePortfolioLevel",
)
def analyze_portfolio_level(
    body: PortfolioLevelAnalysisRequest,
) -> PortfolioLevelAnalysisResponse:
    service = PortfolioLevelAnalysisService()
    try:
        payload = service.analyze(
            body.stock_codes,
            weights=body.weights,
            as_of=body.as_of,
            lookback_trading_days=body.lookback_trading_days,
            confidence=body.confidence,
            horizon_days=body.horizon_days,
            include_stress=body.include_stress,
            scenario_id=body.scenario_id,
            sector_map=body.sector_map,
            high_correlation_threshold=body.high_correlation_threshold,
            currency=body.currency,
        )
        return PortfolioLevelAnalysisResponse(**payload)
    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary
        log_safe_exception(
            logger,
            "Portfolio-level analysis failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Portfolio-level analysis failed",
            },
        ) from exc
