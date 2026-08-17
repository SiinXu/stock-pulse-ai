# -*- coding: utf-8 -*-
"""Bounded AI candidate discovery API routes (#177 / #325)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from src.api.deps import get_config_dep
from src.api.v1.errors import api_error
from src.api.v1.schemas.candidate_discovery import (
    CandidateDiscoveryRequest,
    CandidateDiscoveryResponse,
    CandidateDiscoveryTaskAccepted,
    CandidateDiscoveryTaskStatus,
)
from src.api.v1.schemas.common import ErrorResponse
from src.config import Config
from src.services.candidate_discovery_service import (
    CandidateDiscoveryService,
    DiscoveryCancelled,
    DiscoveryValidationError,
)
from src.services.task_queue import (
    TaskStatus as QueueTaskStatus,
    get_task_queue,
    public_task_error,
    public_task_message,
)
from src.task_execution import TaskNotFoundError
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()

REPORT_TYPE = "candidate_discovery"


def _service(config: Config) -> CandidateDiscoveryService:
    return CandidateDiscoveryService(config_provider=lambda: config)


def _discovery_task_not_found(task_id: str):
    return api_error(
        404,
        "candidate_discovery_task_not_found",
        f"Discovery task {task_id} was not found or has expired",
    )


def _run_discovery(
    service: CandidateDiscoveryService,
    request: CandidateDiscoveryRequest,
    *,
    cancel_check=None,
) -> Dict[str, Any]:
    return service.discover(
        query=request.query,
        criteria=request.criteria.model_dump() if request.criteria is not None else None,
        universe=request.universe,
        page=request.page,
        page_size=request.page_size,
        max_results=request.max_results,
        max_provider_calls=request.max_provider_calls,
        codes=request.codes,
        markets=request.markets,
        account_id=request.account_id,
        use_llm=request.use_llm,
        language=request.language,
        cancel_check=cancel_check,
    )


@router.post(
    "/screen",
    response_model=CandidateDiscoveryResponse,
    response_model_exclude_unset=True,
    responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Run bounded AI candidate discovery",
    description=(
        "Natural-language or criteria-driven candidate discovery over an explicit "
        "paginated universe. Quotes go through data_provider with a hard provider-call "
        "budget. Research screening only — not trade instructions."
    ),
    operation_id="runCandidateDiscovery",
)
def run_candidate_discovery(
    request: CandidateDiscoveryRequest,
    config: Config = Depends(get_config_dep),
) -> Dict[str, Any]:
    try:
        return _run_discovery(_service(config), request)
    except DiscoveryValidationError as exc:
        raise api_error(400, "candidate_discovery_invalid_request", str(exc)) from exc
    except DiscoveryCancelled as exc:
        raise api_error(409, "candidate_discovery_cancelled", str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - stable API error
        log_safe_exception(
            logger,
            "Candidate discovery failed",
            exc,
            error_code="candidate_discovery_failed",
        )
        raise api_error(500, "candidate_discovery_failed", "Candidate discovery failed") from exc


def _is_discovery_cancel_requested(task_queue, task_id: str) -> bool:
    task = task_queue.get_task(task_id)
    if task is None:
        return False
    status = task.status.value if hasattr(task.status, "value") else str(task.status)
    return status in {
        QueueTaskStatus.CANCEL_REQUESTED.value,
        QueueTaskStatus.CANCELLED.value,
    }


def _cancelled_discovery_payload(request: CandidateDiscoveryRequest) -> Dict[str, Any]:
    """Return a non-null payload so the worker exits without a failed terminalization.

    When the queue has already recorded CANCEL_REQUESTED, completing with any
    payload is remapped to CANCELLED by TaskQueue._terminalize_locked.
    """
    return {
        "pack_version": "candidate_discovery/1.0",
        "run_id": uuid.uuid4().hex,
        "status": "cancelled",
        "query": request.query or "",
        "universe": request.universe,
        "market": "cn",
        "page": request.page,
        "page_size": request.page_size,
        "max_results": request.max_results,
        "candidate_count": 0,
        "candidates": [],
        "criteria": {},
        "empty_reason": "cancelled",
        "empty_message": "Discovery run cancelled before candidates were packaged.",
        "warnings": [],
        "research_disclaimer": (
            "Research screening only. Not investment advice or trade instructions."
        ),
        "universe_contract": {
            "source": request.universe,
            "resolved_count": 0,
            "evaluated_count": 0,
            "truncated": False,
        },
        "cost_contract": {
            "provider_calls": 0,
            "provider_hits": 0,
            "provider_errors": 0,
            "max_provider_calls": request.max_provider_calls,
            "llm_calls": 0,
            "llm_explained": 0,
            "max_llm_calls": 0,
            "elapsed_ms": 0,
            "analysis_runs_triggered": 0,
            "database_writes": 0,
            "bounded": True,
            "interruptible": True,
            "cancelled": True,
        },
    }


@router.post(
    "/screen/tasks",
    status_code=202,
    response_model=CandidateDiscoveryTaskAccepted,
    response_model_exclude_unset=True,
    responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Submit bounded AI candidate discovery task",
    operation_id="startCandidateDiscoveryTask",
)
def start_candidate_discovery_task(
    request: CandidateDiscoveryRequest,
    config: Config = Depends(get_config_dep),
) -> CandidateDiscoveryTaskAccepted:
    task_id = uuid.uuid4().hex
    task_queue = get_task_queue()
    service = _service(config)

    def cancel_check() -> bool:
        return _is_discovery_cancel_requested(task_queue, task_id)

    def run_discovery() -> Dict[str, Any]:
        if cancel_check():
            return _cancelled_discovery_payload(request)
        task_queue.update_task_progress(
            task_id,
            15,
            "Resolving bounded discovery universe",
        )
        try:
            result = _run_discovery(service, request, cancel_check=cancel_check)
        except DiscoveryCancelled:
            # Cooperative cancel: exit cleanly so CANCEL_REQUESTED → CANCELLED,
            # not a failed task with candidate_discovery_failed.
            return _cancelled_discovery_payload(request)
        if cancel_check():
            return _cancelled_discovery_payload(request)
        task_queue.update_task_progress(
            task_id,
            90,
            f"Discovery complete; packaging {result.get('candidate_count', 0)} candidates",
        )
        return result

    task = task_queue.submit_background_task(
        run_discovery,
        stock_code="candidate_discovery",
        stock_name=f"{request.universe} / page {request.page}",
        report_type=REPORT_TYPE,
        message="Candidate discovery task submitted",
        task_id=task_id,
        trace_id=task_id,
        failure_error_code="candidate_discovery_failed",
    )
    return CandidateDiscoveryTaskAccepted(
        task_id=task.task_id,
        trace_id=task.trace_id or task.task_id,
        status=task.status.value if isinstance(task.status, QueueTaskStatus) else str(task.status),
        message=task.message or "Candidate discovery task submitted",
        message_code=getattr(task, "message_code", "task.discovery.queued"),
        message_params=getattr(task, "message_params", {}) or {},
        universe=request.universe,
        page=request.page,
        page_size=request.page_size,
        max_results=request.max_results,
        max_provider_calls=request.max_provider_calls,
    )


@router.get(
    "/screen/tasks/{task_id}",
    response_model=CandidateDiscoveryTaskStatus,
    response_model_exclude_unset=True,
    responses={404: {"model": ErrorResponse}},
    summary="Get candidate discovery task status",
    operation_id="getCandidateDiscoveryTask",
)
def get_candidate_discovery_task(task_id: str) -> CandidateDiscoveryTaskStatus:
    task = get_task_queue().get_task(task_id)
    if task is None or task.report_type != REPORT_TYPE:
        raise _discovery_task_not_found(task_id)

    result: Optional[CandidateDiscoveryResponse] = None
    if task.status == QueueTaskStatus.COMPLETED and isinstance(task.result, dict):
        result = CandidateDiscoveryResponse.model_validate(task.result)

    return CandidateDiscoveryTaskStatus(
        task_id=task.task_id,
        trace_id=task.trace_id or task.task_id,
        status=task.status.value if isinstance(task.status, QueueTaskStatus) else str(task.status),
        progress=task.progress,
        message=public_task_message(task),
        message_code=getattr(task, "message_code", "task.status"),
        message_params=getattr(task, "message_params", {}) or {},
        error=public_task_error(task, default_error_code="candidate_discovery_failed"),
        result=result,
    )


@router.post(
    "/screen/tasks/{task_id}/cancel",
    response_model=CandidateDiscoveryTaskStatus,
    response_model_exclude_unset=True,
    responses={404: {"model": ErrorResponse}},
    summary="Cancel a running candidate discovery task",
    operation_id="cancelCandidateDiscoveryTask",
)
def cancel_candidate_discovery_task(task_id: str) -> CandidateDiscoveryTaskStatus:
    task_queue = get_task_queue()
    existing = task_queue.get_task(task_id)
    if existing is None or existing.report_type != REPORT_TYPE:
        raise _discovery_task_not_found(task_id)
    try:
        snapshot = task_queue.cancel(task_id)
    except TaskNotFoundError as exc:
        raise _discovery_task_not_found(task_id) from exc

    task = task_queue.get_task(task_id) or existing
    return CandidateDiscoveryTaskStatus(
        task_id=snapshot.task_id if hasattr(snapshot, "task_id") else task_id,
        trace_id=getattr(task, "trace_id", None) or task_id,
        status=(
            snapshot.status.value
            if hasattr(snapshot.status, "value")
            else str(getattr(snapshot, "status", getattr(task, "status", "cancelled")))
        ),
        progress=int(getattr(snapshot, "progress", getattr(task, "progress", 0)) or 0),
        message=getattr(snapshot, "message", None) or public_task_message(task) or "Cancel requested",
        message_code=getattr(snapshot, "message_code", None) or "task.cancel_requested",
        message_params=getattr(snapshot, "message_params", {}) or {},
        error=None,
        result=None,
    )
