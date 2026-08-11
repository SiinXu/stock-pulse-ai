# -*- coding: utf-8 -*-
"""Today's Focus read API (Issue #157 / T26)."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import ValidationError

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.todays_focus import TodaysFocusResponse
from src.services.todays_focus_service import (
    DEFAULT_MAX_FOCUS_ITEMS,
    MAX_FOCUS_ITEMS_HARD_CAP,
    TodaysFocusService,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/today",
    response_model=TodaysFocusResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {"model": ErrorResponse, "description": "Focus aggregation failed"},
    },
    summary="Get today's focus recommendations",
    description=(
        "Fresh local-calendar-day evidence from the watchlist and persisted holdings "
        "cache. Hard-capped, read-only, and explicit about source degradation; never "
        "fetches market data, runs analysis, or replays portfolio state."
    ),
    operation_id="getTodaysFocus",
)
def get_todays_focus(
    max_items: int = Query(
        DEFAULT_MAX_FOCUS_ITEMS,
        ge=0,
        le=MAX_FOCUS_ITEMS_HARD_CAP,
        description="Hard cap for returned focus items (default 5, max 10)",
    ),
    account_id: Optional[int] = Query(
        None,
        ge=1,
        description="Optional portfolio account id for the cached holdings universe",
    ),
    language: Optional[str] = Query(
        None,
        pattern="^(en|zh)$",
        description="Reason display language (en/zh); defaults to report_language",
    ),
) -> TodaysFocusResponse:
    service = TodaysFocusService()
    try:
        data = service.build_focus(
            max_items=max_items,
            account_id=account_id,
            language=language,
        )
        return TodaysFocusResponse(**data)
    except ValidationError as exc:
        log_safe_exception(
            logger,
            "Today's focus response validation failed",
            exc,
            error_code="internal_response_validation_error",
        )
        raise api_error(500, "internal_error", "Get today's focus failed") from exc
    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API error
        log_safe_exception(logger, "Get today's focus failed", exc, error_code="internal_error")
        raise api_error(500, "internal_error", "Get today's focus failed") from exc
