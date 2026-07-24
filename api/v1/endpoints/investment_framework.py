# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""CRUD API for the local personal investment framework."""

from __future__ import annotations

import logging
from typing import Callable, TypeVar

from fastapi import APIRouter, Query

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.investment_framework import (
    InvestmentFrameworkCreateRequest,
    InvestmentFrameworkDeactivateRequest,
    InvestmentFrameworkDeleteResponse,
    InvestmentFrameworkHistoryResponse,
    InvestmentFrameworkResponse,
    InvestmentFrameworkUpdateRequest,
)
from src.services.investment_framework_service import (
    InvestmentFrameworkAlreadyExistsError,
    InvestmentFrameworkNotFoundError,
    InvestmentFrameworkRevisionConflictError,
    InvestmentFrameworkService,
)
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)
router = APIRouter()
T = TypeVar("T")
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}


def _translate_service_error(exc: Exception):
    if isinstance(exc, InvestmentFrameworkNotFoundError):
        raise api_error(404, exc.error_code, str(exc)) from exc
    if isinstance(exc, InvestmentFrameworkAlreadyExistsError):
        raise api_error(409, exc.error_code, str(exc)) from exc
    if isinstance(exc, InvestmentFrameworkRevisionConflictError):
        raise api_error(
            409,
            exc.error_code,
            str(exc),
            params={"current_revision": exc.current_revision},
        ) from exc


def _execute(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (
        InvestmentFrameworkNotFoundError,
        InvestmentFrameworkAlreadyExistsError,
        InvestmentFrameworkRevisionConflictError,
    ) as exc:
        _translate_service_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - Unknown failures are logged safely and returned through a stable error envelope.
        log_safe_exception(
            logger,
            "Investment framework API operation failed",
            exc,
            error_code="investment_framework_internal_error",
        )
        raise api_error(
            500,
            "internal_error",
            "Investment framework operation failed",
        ) from exc


@router.post(
    "",
    response_model=InvestmentFrameworkResponse,
    status_code=201,
    responses={409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Create the local personal investment framework",
)
def create_framework(
    request: InvestmentFrameworkCreateRequest,
) -> InvestmentFrameworkResponse:
    return _execute(
        lambda: InvestmentFrameworkResponse.model_validate(
            InvestmentFrameworkService().create(
                content=request.content,
                change_summary=request.change_summary,
            )
        )
    )


@router.get(
    "",
    response_model=InvestmentFrameworkResponse,
    responses=_ERROR_RESPONSES,
    summary="Read the latest personal investment framework version",
)
def get_framework() -> InvestmentFrameworkResponse:
    return _execute(
        lambda: InvestmentFrameworkResponse.model_validate(
            InvestmentFrameworkService().get()
        )
    )


@router.put(
    "",
    response_model=InvestmentFrameworkResponse,
    responses=_ERROR_RESPONSES,
    summary="Create a new personal investment framework version",
)
def update_framework(
    request: InvestmentFrameworkUpdateRequest,
) -> InvestmentFrameworkResponse:
    return _execute(
        lambda: InvestmentFrameworkResponse.model_validate(
            InvestmentFrameworkService().update(
                expected_revision=request.expected_revision,
                content=request.content,
                change_summary=request.change_summary,
            )
        )
    )


@router.get(
    "/history",
    response_model=InvestmentFrameworkHistoryResponse,
    responses=_ERROR_RESPONSES,
    summary="List immutable personal investment framework versions",
)
def list_framework_history() -> InvestmentFrameworkHistoryResponse:
    return _execute(
        lambda: InvestmentFrameworkHistoryResponse.model_validate(
            InvestmentFrameworkService().list_history()
        )
    )


@router.post(
    "/deactivate",
    response_model=InvestmentFrameworkResponse,
    responses=_ERROR_RESPONSES,
    summary="Deactivate framework context while retaining version history",
)
def deactivate_framework(
    request: InvestmentFrameworkDeactivateRequest,
) -> InvestmentFrameworkResponse:
    return _execute(
        lambda: InvestmentFrameworkResponse.model_validate(
            InvestmentFrameworkService().deactivate(
                expected_revision=request.expected_revision,
            )
        )
    )


@router.delete(
    "",
    response_model=InvestmentFrameworkDeleteResponse,
    responses=_ERROR_RESPONSES,
    summary="Delete the framework aggregate and all version history",
)
def delete_framework(
    expected_revision: int = Query(..., ge=1),
) -> InvestmentFrameworkDeleteResponse:
    return _execute(
        lambda: InvestmentFrameworkDeleteResponse.model_validate(
            InvestmentFrameworkService().delete(
                expected_revision=expected_revision,
            )
        )
    )
