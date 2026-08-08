# -*- coding: utf-8 -*-
"""Event calendar API (issue #153 / T21).

Auth contract matches neighboring read-only routes: global admin-session
middleware when enabled; no extra public exemption.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.event_calendar import EventCalendarResponse
from src.services.event_calendar_service import EventCalendarService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=EventCalendarResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {"model": ErrorResponse, "description": "Event calendar failed"},
    },
    summary="Get event calendar for watchlist and holdings",
    description=(
        "Upcoming corporate events scoped to configured watchlist symbols and "
        "portfolio holdings. Disabled by default (EVENT_CALENDAR_ENABLED=false) "
        "with zero provider fetch. Impact preview reuses event_alerts.build_impact_context."
    ),
    operation_id="getEventCalendar",
)
def get_event_calendar(
    date_from: Optional[date] = Query(None, description="Range start (default: today)"),
    date_to: Optional[date] = Query(
        None, description="Range end (default: today + 90 days)"
    ),
    symbols: Optional[str] = Query(
        None,
        description="Optional comma-separated filter intersected with watchlist/holdings",
    ),
    event_types: Optional[str] = Query(
        None,
        description="Comma-separated: earnings,ex_dividend,unlock,index_rebalance,macro",
    ),
    include_impact: bool = Query(
        True,
        description="Attach impact preview via build_impact_context (no LLM invent)",
    ),
    report_language: str = Query(
        "zh",
        description="Language for impact text: zh or en",
    ),
) -> EventCalendarResponse:
    symbol_list = None
    if symbols is not None and str(symbols).strip():
        symbol_list = [part.strip() for part in str(symbols).split(",") if part.strip()]

    service = EventCalendarService()
    try:
        data = service.get_calendar(
            symbols=symbol_list,
            date_from=date_from,
            date_to=date_to,
            event_types=event_types,
            include_impact=include_impact,
            report_language=report_language,
        )
        return EventCalendarResponse(**data)
    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map calendar failures
        log_safe_exception(
            logger,
            "Get event calendar failed",
            exc,
            error_code="internal_error",
        )
        raise api_error(500, "internal_error", "Get event calendar failed") from exc
