# -*- coding: utf-8 -*-
"""Watchlist AI score endpoint (Issue #147 / T25).

Aggregates existing analysis history and active decision signals. Does not
trigger LLM analysis. Auth follows neighboring authenticated routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.watchlist_scores import (
    WatchlistScoreRequest,
    WatchlistScoreResponse,
)
from src.services.watchlist_score_service import WatchlistScoreService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/scores",
    response_model=WatchlistScoreResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Score aggregation failed"},
    },
    summary="Score watchlist symbols from existing analysis",
    description=(
        "Batch-aggregate AI-oriented watchlist scores from the latest analysis "
        "history and same-report, unexpired decision signals. Symbols without analysis history "
        "return status=unanalyzed with score=null (never a fabricated 0). "
        "Requests are limited to 200 unique market identities. Default "
        "sort=manual preserves the caller's order. No new LLM calls."
    ),
    operation_id="scoreWatchlistSymbols",
)
def score_watchlist_symbols(body: WatchlistScoreRequest) -> WatchlistScoreResponse:
    service = WatchlistScoreService()
    try:
        payload = service.score_symbols(
            body.stock_codes,
            sort=body.sort,
        )
        return WatchlistScoreResponse(**payload)
    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map aggregation failures
        log_safe_exception(
            logger,
            "Watchlist score aggregation failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Watchlist score aggregation failed",
            },
        ) from exc
