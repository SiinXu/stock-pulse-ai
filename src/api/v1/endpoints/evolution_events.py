# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated read-only EvolutionEvent list API (Issue #1113)."""

from __future__ import annotations

from datetime import datetime
from typing import FrozenSet, Optional

from fastapi import APIRouter, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.security import APIKeyCookie

from src.api.v1.errors import api_error
from src.api.v1.schemas.common import ErrorResponse
from src.api.v1.schemas.evolution_events import EvolutionEventListResponse
from src.auth import COOKIE_NAME
from src.repositories.base import RepositoryError
from src.services.evolution_event_query import EvolutionEventQueryService


admin_session_cookie = APIKeyCookie(
    name=COOKIE_NAME,
    scheme_name="AdminSessionCookie",
    auto_error=False,
)
router = APIRouter(dependencies=[Security(admin_session_cookie)])

AUTH_RESPONSE = {
    401: {
        "model": ErrorResponse,
        "description": "Missing or invalid administrator session when ADMIN_AUTH_ENABLED=true",
    },
}

_LIST_QUERY_KEYS: FrozenSet[str] = frozenset(
    {"occurred_from", "occurred_to", "event_type", "limit"}
)


def _reject_unknown_query_params(request: Request) -> None:
    extras = [key for key in request.query_params.keys() if key not in _LIST_QUERY_KEYS]
    if not extras:
        return
    extra_key = extras[0]
    raise RequestValidationError(
        [
            {
                "type": "extra_forbidden",
                "loc": ("query", extra_key),
                "msg": "Extra inputs are not permitted",
                "input": request.query_params.get(extra_key),
            }
        ]
    )


@router.get(
    "/evolution-events",
    response_model=EvolutionEventListResponse,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "Invalid time range, type, or limit"},
        422: {"model": ErrorResponse, "description": "Query parameter validation failed"},
        503: {"model": ErrorResponse, "description": "Evolution event storage is unavailable"},
    },
    summary="List EvolutionEvent rows by time range and exact type",
    description=(
        "Read-only list of append-only EvolutionEvent rows. "
        "occurred_from and occurred_to are required timezone-aware UTC instants "
        "and are inclusive. event_type is an optional exact match; omit it to "
        "skip the type filter. Blank event_type is rejected. limit defaults to "
        "100 and is capped at 200. This route does not append or mutate events."
    ),
    operation_id="listAgentEvolutionEvents",
)
def list_agent_evolution_events(
    request: Request,
    occurred_from: datetime = Query(...),
    occurred_to: datetime = Query(...),
    event_type: Optional[str] = Query(default=None),
    limit: Optional[int] = Query(default=None),
) -> EvolutionEventListResponse:
    _reject_unknown_query_params(request)
    service = EvolutionEventQueryService()
    try:
        payload = service.list_events(
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            event_type=event_type,
            limit=limit,
        )
        return EvolutionEventListResponse(
            items=payload["items"],
            limit=payload["limit"],
            returned=payload["returned"],
        )
    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc)) from exc
    except RepositoryError as exc:
        raise api_error(
            503,
            "evolution_event_unavailable",
            "Evolution event storage is unavailable",
        ) from exc
