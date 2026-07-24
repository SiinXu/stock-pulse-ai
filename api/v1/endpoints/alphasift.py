# -*- coding: utf-8 -*-
"""AlphaSift stock screening API routes."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Type, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from api.deps import get_config_dep
from api.v1.errors import api_error
from api.v1.schemas.alphasift import (
    AlphaSiftHotspotDetailResponse,
    AlphaSiftHotspotsResponse,
    AlphaSiftInstallResponse,
    AlphaSiftScreenAccepted,
    AlphaSiftScreenRequest,
    AlphaSiftScreenResponse,
    AlphaSiftScreenTaskStatus,
    AlphaSiftStatusResponse,
    AlphaSiftStrategiesResponse,
    AlphaSiftStrategyResponse,
)
from api.v1.schemas.common import ErrorResponse
from src.config import Config
from src.services.alphasift_service import AlphaSiftService
from src.services.task_queue import (
    TaskStatus as QueueTaskStatus,
    get_task_queue,
    public_task_error,
    public_task_message,
)

router = APIRouter()

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


def _validated_payload(
    model: Type[ResponseModelT],
    payload: Any,
) -> Dict[str, Any]:
    """Validate service output before exposing its serialized transport form."""

    return model.model_validate(payload).model_dump(exclude_unset=True)


def _service(config: Config) -> AlphaSiftService:
    return AlphaSiftService(config=config)


def _screening_task_not_found(task_id: str) -> HTTPException:
    return api_error(
        404,
        "alphasift_screen_task_not_found",
        f"选股任务 {task_id} 不存在或已过期",
    )


@router.get(
    "/status",
    response_model=AlphaSiftStatusResponse,
    response_model_exclude_unset=True,
)
def alphasift_status(config: Config = Depends(get_config_dep)) -> Dict[str, Any]:
    return _validated_payload(AlphaSiftStatusResponse, _service(config).status())


@router.get(
    "/strategies",
    response_model=AlphaSiftStrategiesResponse,
    response_model_exclude_unset=True,
)
def alphasift_strategies(
    request: Request,
    config: Config = Depends(get_config_dep),
) -> Dict[str, Any]:
    return _validated_payload(AlphaSiftStrategiesResponse, _service(config).strategies())


@router.get(
    "/hotspots",
    response_model=AlphaSiftHotspotsResponse,
    response_model_exclude_unset=True,
    responses={422: {"model": ErrorResponse}},
)
def alphasift_hotspots(
    provider: str = Query("", max_length=32),
    top: int = Query(12, ge=1, le=50),
    refresh: bool = Query(False),
    include_details: bool = Query(False),
    config: Config = Depends(get_config_dep),
) -> Dict[str, Any]:
    refresh_value = refresh if isinstance(refresh, bool) else bool(getattr(refresh, "default", False))
    include_details_value = (
        include_details
        if isinstance(include_details, bool)
        else bool(getattr(include_details, "default", False))
    )
    return _validated_payload(
        AlphaSiftHotspotsResponse,
        _service(config).hotspots(
            provider=provider,
            top=top,
            refresh=refresh_value,
            include_details=include_details_value,
        ),
    )


@router.get(
    "/hotspots/{topic:path}",
    response_model=AlphaSiftHotspotDetailResponse,
    response_model_exclude_unset=True,
    responses={422: {"model": ErrorResponse}},
)
def alphasift_hotspot_detail(
    topic: str,
    provider: str = Query("", max_length=32),
    refresh: bool = Query(False),
    config: Config = Depends(get_config_dep),
) -> Dict[str, Any]:
    refresh_value = refresh if isinstance(refresh, bool) else bool(getattr(refresh, "default", False))
    return _validated_payload(
        AlphaSiftHotspotDetailResponse,
        _service(config).hotspot_detail(
            topic=topic,
            provider=provider,
            refresh=refresh_value,
        ),
    )


@router.post(
    "/install",
    response_model=AlphaSiftInstallResponse,
    response_model_exclude_unset=True,
)
def alphasift_install(
    request: Request,
    config: Config = Depends(get_config_dep),
) -> Dict[str, Any]:
    return _validated_payload(
        AlphaSiftInstallResponse,
        _service(config).install(request=request),
    )


@router.post(
    "/screen/tasks",
    status_code=202,
    response_model=AlphaSiftScreenAccepted,
    response_model_exclude_unset=True,
    responses={422: {"model": ErrorResponse}},
)
def alphasift_start_screen_task(
    request: AlphaSiftScreenRequest,
    http_request: Request,
    config: Config = Depends(get_config_dep),
) -> AlphaSiftScreenAccepted:
    task_id = uuid.uuid4().hex
    task_queue = get_task_queue()

    def run_screen() -> Dict[str, Any]:
        task_queue.update_task_progress(
            task_id,
            20,
            "正在执行 AlphaSift 选股，外部数据源较慢时会持续后台运行",
        )
        result = _validated_payload(
            AlphaSiftScreenResponse,
            _service(config).screen(
                strategy=request.strategy,
                market=request.market,
                max_results=request.max_results,
            ),
        )
        task_queue.update_task_progress(
            task_id,
            90,
            f"选股已完成，正在整理 {result.get('candidate_count', 0)} 条候选",
        )
        return result

    task = task_queue.submit_background_task(
        run_screen,
        stock_code="alphasift_screen",
        stock_name=f"{request.strategy} / {request.market}",
        report_type="alphasift_screen",
        message="AlphaSift 选股任务已提交",
        task_id=task_id,
        trace_id=task_id,
        failure_error_code="alphasift_screen_failed",
    )
    return AlphaSiftScreenAccepted(
        task_id=task.task_id,
        trace_id=task.trace_id or task.task_id,
        status=task.status.value if isinstance(task.status, QueueTaskStatus) else str(task.status),
        message=task.message or "AlphaSift 选股任务已提交",
        message_code=getattr(task, "message_code", "task.screening.queued"),
        message_params=getattr(task, "message_params", {}),
        strategy=request.strategy,
        market=request.market,
        max_results=request.max_results,
    )


@router.get(
    "/screen/tasks/{task_id}",
    response_model=AlphaSiftScreenTaskStatus,
    response_model_exclude_unset=True,
    responses={404: {"model": ErrorResponse}},
)
def alphasift_screen_task_status(task_id: str) -> AlphaSiftScreenTaskStatus:
    task = get_task_queue().get_task(task_id)
    if task is None or task.report_type != "alphasift_screen":
        raise _screening_task_not_found(task_id)

    result = (
        AlphaSiftScreenResponse.model_validate(task.result)
        if task.status == QueueTaskStatus.COMPLETED and isinstance(task.result, dict)
        else None
    )
    return AlphaSiftScreenTaskStatus(
        task_id=task.task_id,
        trace_id=task.trace_id or task.task_id,
        status=task.status.value if isinstance(task.status, QueueTaskStatus) else str(task.status),
        progress=task.progress,
        message=public_task_message(task),
        message_code=getattr(task, "message_code", "task.status"),
        message_params=getattr(task, "message_params", {}),
        error=public_task_error(task, default_error_code="alphasift_screen_failed"),
        result=result,
    )


@router.post(
    "/screen",
    response_model=AlphaSiftScreenResponse,
    response_model_exclude_unset=True,
    responses={422: {"model": ErrorResponse}},
)
def alphasift_screen(
    request: AlphaSiftScreenRequest,
    http_request: Request,
    config: Config = Depends(get_config_dep),
) -> Dict[str, Any]:
    return _validated_payload(
        AlphaSiftScreenResponse,
        _service(config).screen(
            strategy=request.strategy,
            market=request.market,
            max_results=request.max_results,
        ),
    )
