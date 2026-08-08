# -*- coding: utf-8 -*-
"""Today's Focus read API (Issue #157 / T26)."""
from __future__ import annotations
import logging
from typing import Optional
from fastapi import APIRouter, Query
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.todays_focus import TodaysFocusResponse
from src.services.todays_focus_service import DEFAULT_MAX_FOCUS_ITEMS, MAX_FOCUS_ITEMS_HARD_CAP, TodaysFocusService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get(
    "/today",
    response_model=TodaysFocusResponse,
    responses={400: {"model": ErrorResponse, "description": "Invalid query parameters"}, 500: {"model": ErrorResponse, "description": "Focus aggregation failed"}},
    summary="Get today's focus recommendations",
    description="Deterministic short list of symbols from watchlist + holdings. Hard-capped; empty when nothing qualifies. Never triggers market data fetches or analysis runs.",
    operation_id="getTodaysFocus",
)
def get_todays_focus(
    max_items: int = Query(DEFAULT_MAX_FOCUS_ITEMS, ge=0, le=MAX_FOCUS_ITEMS_HARD_CAP, description="Hard cap for returned focus items (default 5, max 10)"),
    account_id: Optional[int] = Query(None, description="Optional portfolio account id for holdings weight context"),
    language: Optional[str] = Query(None, description="Reason display language (en/zh); defaults to report_language"),
) -> TodaysFocusResponse:
    service = TodaysFocusService()
    try:
        data = service.build_focus(max_items=max_items, account_id=account_id, language=language)
        return TodaysFocusResponse(**data)
    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map failures to sanitized API error
        log_safe_exception(logger, "Get today's focus failed", exc, error_code="internal_error")
        raise api_error(500, "internal_error", "Get today's focus failed") from exc
