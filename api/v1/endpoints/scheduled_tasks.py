"""Scheduled-task API endpoints for schema version 1."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import get_runtime_scheduler_service, get_scheduled_task_service
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.scheduled_tasks import (
    ScheduledTaskCreateRequest,
    ScheduledTaskItem,
    ScheduledTaskListResponse,
    ScheduledTaskRunListResponse,
    ScheduledTaskStatusResponse,
)
from src.services.runtime_scheduler import RuntimeSchedulerService
from src.services.scheduled_task_service import (
    ScheduledTaskError,
    ScheduledTaskNotFoundError,
    ScheduledTaskService,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()


def _service_error(exc: ScheduledTaskError):
    status_code = 404 if isinstance(exc, ScheduledTaskNotFoundError) else 400
    return api_error(status_code, exc.error_code, str(exc))


@router.post(
    "",
    response_model=ScheduledTaskItem,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Create scheduled task",
)
def create_scheduled_task(
    request: ScheduledTaskCreateRequest,
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
    runtime_scheduler: RuntimeSchedulerService = Depends(get_runtime_scheduler_service),
) -> ScheduledTaskItem:
    try:
        item = service.create_task(request.model_dump())
        runtime_scheduler.reconcile_scheduled_tasks()
        return ScheduledTaskItem(**item)
    except ScheduledTaskError as exc:
        raise _service_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary logs diagnostics and returns a stable envelope.
        log_safe_exception(
            logger,
            "Create scheduled task failed",
            exc,
            error_code="scheduled_task_api_internal_error",
        )
        raise api_error(500, "internal_error", "Scheduled task operation failed")


@router.get(
    "",
    response_model=ScheduledTaskListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List scheduled tasks",
)
def list_scheduled_tasks(
    enabled: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
) -> ScheduledTaskListResponse:
    try:
        return ScheduledTaskListResponse(
            **service.list_tasks(enabled=enabled, limit=limit)
        )
    except ScheduledTaskError as exc:
        raise _service_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary logs diagnostics and returns a stable envelope.
        log_safe_exception(
            logger,
            "List scheduled tasks failed",
            exc,
            error_code="scheduled_task_api_internal_error",
        )
        raise api_error(500, "internal_error", "Scheduled task operation failed")


@router.get(
    "/{task_id}/status",
    response_model=ScheduledTaskStatusResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get scheduled task status",
)
def get_scheduled_task_status(
    task_id: str,
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
) -> ScheduledTaskStatusResponse:
    try:
        return ScheduledTaskStatusResponse(**service.get_status(task_id))
    except ScheduledTaskError as exc:
        raise _service_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary logs diagnostics and returns a stable envelope.
        log_safe_exception(
            logger,
            "Get scheduled task status failed",
            exc,
            error_code="scheduled_task_api_internal_error",
        )
        raise api_error(500, "internal_error", "Scheduled task operation failed")


@router.post(
    "/{task_id}/enable",
    response_model=ScheduledTaskItem,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Enable scheduled task",
)
def enable_scheduled_task(
    task_id: str,
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
    runtime_scheduler: RuntimeSchedulerService = Depends(get_runtime_scheduler_service),
) -> ScheduledTaskItem:
    try:
        item = service.set_enabled(task_id, True)
        runtime_scheduler.reconcile_scheduled_tasks()
        return ScheduledTaskItem(**item)
    except ScheduledTaskError as exc:
        raise _service_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary logs diagnostics and returns a stable envelope.
        log_safe_exception(
            logger,
            "Enable scheduled task failed",
            exc,
            error_code="scheduled_task_api_internal_error",
        )
        raise api_error(500, "internal_error", "Scheduled task operation failed")


@router.post(
    "/{task_id}/disable",
    response_model=ScheduledTaskItem,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Disable scheduled task",
)
def disable_scheduled_task(
    task_id: str,
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
    runtime_scheduler: RuntimeSchedulerService = Depends(get_runtime_scheduler_service),
) -> ScheduledTaskItem:
    try:
        item = service.set_enabled(task_id, False)
        runtime_scheduler.reconcile_scheduled_tasks()
        return ScheduledTaskItem(**item)
    except ScheduledTaskError as exc:
        raise _service_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary logs diagnostics and returns a stable envelope.
        log_safe_exception(
            logger,
            "Disable scheduled task failed",
            exc,
            error_code="scheduled_task_api_internal_error",
        )
        raise api_error(500, "internal_error", "Scheduled task operation failed")


@router.get(
    "/{task_id}/runs",
    response_model=ScheduledTaskRunListResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List scheduled task run records",
)
def list_scheduled_task_runs(
    task_id: str,
    limit: int = Query(100, ge=1, le=500),
    service: ScheduledTaskService = Depends(get_scheduled_task_service),
) -> ScheduledTaskRunListResponse:
    try:
        return ScheduledTaskRunListResponse(**service.list_runs(task_id, limit=limit))
    except ScheduledTaskError as exc:
        raise _service_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary logs diagnostics and returns a stable envelope.
        log_safe_exception(
            logger,
            "List scheduled task runs failed",
            exc,
            error_code="scheduled_task_api_internal_error",
        )
        raise api_error(500, "internal_error", "Scheduled task operation failed")
