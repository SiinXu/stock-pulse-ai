# -*- coding: utf-8 -*-
"""Valuation estimate endpoint for DCF / relative models (issue #238)."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.valuation import ValuationEstimateRequest, ValuationEstimateResponse
from src.services.valuation_service import (
    MAX_DISCOUNT_RATE,
    MAX_GROWTH_RATE,
    MAX_PROJECTION_YEARS,
    MAX_TERMINAL_GROWTH_RATE,
    MIN_DISCOUNT_RATE,
    MIN_GROWTH_RATE,
    MIN_PROJECTION_YEARS,
    MIN_TERMINAL_GROWTH_RATE,
    ValuationService,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()


def _bad_request(message: str) -> HTTPException:
    return api_error(400, "validation_error", message)


def _internal_error(message: str, exc: Exception) -> HTTPException:
    log_safe_exception(logger, message, exc, error_code="valuation_estimate_failed")
    return api_error(500, "internal_error", message)


def _parse_peer_codes(peer_codes: Optional[List[str]]) -> Optional[List[str]]:
    if not peer_codes:
        return None
    cleaned = [str(item).strip() for item in peer_codes if str(item or "").strip()]
    return cleaned or None


@router.get(
    "/estimate",
    response_model=ValuationEstimateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {"model": ErrorResponse, "description": "Valuation estimate failed"},
    },
    summary="Estimate stock valuation (DCF + relative)",
    description=(
        "Transparent DCF and relative valuation (P/E, P/B, EV/EBITDA when "
        "explicit inputs exist). Returns assumptions and a growth×discount "
        "sensitivity table. Research support only; not investment advice."
    ),
    operation_id="estimateStockValuation",
)
def estimate_stock_valuation(
    stock_code: str = Query(..., min_length=1, description="Stock code"),
    growth_rate: Optional[float] = Query(None, description="Optional growth rate (decimal)"),
    discount_rate: Optional[float] = Query(None, description="Optional discount rate (decimal)"),
    terminal_growth_rate: Optional[float] = Query(None, description="Optional terminal growth rate (decimal)"),
    projection_years: Optional[int] = Query(None, ge=MIN_PROJECTION_YEARS, le=MAX_PROJECTION_YEARS),
    peer_codes: Optional[List[str]] = Query(None, description="Optional peer codes (repeat query param)"),
) -> ValuationEstimateResponse:
    code = str(stock_code or "").strip()
    if not code:
        raise _bad_request("stock_code is required")
    if growth_rate is not None and not (MIN_GROWTH_RATE <= growth_rate <= MAX_GROWTH_RATE):
        raise _bad_request(f"growth_rate must be between {MIN_GROWTH_RATE} and {MAX_GROWTH_RATE}")
    if discount_rate is not None and not (MIN_DISCOUNT_RATE <= discount_rate <= MAX_DISCOUNT_RATE):
        raise _bad_request(f"discount_rate must be between {MIN_DISCOUNT_RATE} and {MAX_DISCOUNT_RATE}")
    if terminal_growth_rate is not None and not (
        MIN_TERMINAL_GROWTH_RATE <= terminal_growth_rate <= MAX_TERMINAL_GROWTH_RATE
    ):
        raise _bad_request("terminal_growth_rate out of supported range")
    if (
        discount_rate is not None
        and terminal_growth_rate is not None
        and terminal_growth_rate >= discount_rate
    ):
        raise _bad_request("terminal_growth_rate must be strictly below discount_rate")
    try:
        service = ValuationService()
        payload = service.estimate(
            code,
            growth_rate=growth_rate,
            discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate,
            projection_years=projection_years,
            peer_codes=_parse_peer_codes(peer_codes),
        )
    except ValueError as exc:
        raise _bad_request(str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map valuation failures to a sanitized API error
        log_safe_exception(
            logger,
            "Valuation estimate failed",
            exc,
            error_code="valuation_estimate_failed",
        )
        raise api_error(500, "internal_error", "Valuation estimate failed") from exc
    return ValuationEstimateResponse.model_validate(payload)


@router.post(
    "/estimate",
    response_model=ValuationEstimateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request body"},
        500: {"model": ErrorResponse, "description": "Valuation estimate failed"},
    },
    summary="Estimate stock valuation with body overrides",
    description="Same as GET /estimate with JSON body for interactive Web sensitivity UI.",
    operation_id="estimateStockValuationPost",
)
def estimate_stock_valuation_post(body: ValuationEstimateRequest) -> ValuationEstimateResponse:
    return estimate_stock_valuation(
        stock_code=body.stock_code,
        growth_rate=body.growth_rate,
        discount_rate=body.discount_rate,
        terminal_growth_rate=body.terminal_growth_rate,
        projection_years=body.projection_years,
        peer_codes=body.peer_codes,
    )
