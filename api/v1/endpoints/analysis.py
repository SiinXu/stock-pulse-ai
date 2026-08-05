# -*- coding: utf-8 -*-
"""
===================================
股票分析接口
===================================

HTTP layer: auth/deps, DTO validation, status codes, SSE framing, and projection
into response models. Use-case orchestration lives in
``src.services.analysis_api_service.AnalysisApiService``.

Private helpers remain importable here as thin facades so existing API tests that
patch or call ``api.v1.endpoints.analysis.*`` keep working without wire changes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, Depends, Query, Body
from fastapi.responses import JSONResponse, StreamingResponse

from api.deps import (
    get_config_dep,
    require_security_audit_service,
)
from api.v1.schemas.analysis import (
    AnalyzeRequest,
    AnalysisResultResponse,
    TaskAccepted,
    BatchTaskAcceptedResponse,
    TaskStatus,
    TaskListResponse,
    DuplicateTaskErrorResponse,
    MarketReviewRequest,
    MarketReviewAccepted,
)
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.run_flow import RunFlowSnapshot
from src.data.stock_index_loader import resolve_index_stock_code
from src.config import Config
from src.core.market_review_lock import (
    MarketReviewExecutionLock as _MarketReviewExecutionLock,
    market_review_lock_path,
    release_market_review_lock as _release_market_review_lock,
    try_acquire_market_review_lock as _try_acquire_market_review_lock,
)
from src.core.market_review_runtime import (
    build_market_review_runtime as _runtime_build_market_review_runtime,
)
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis
from src.services.name_to_code_resolver import resolve_name_to_code
from src.services.task_queue import get_task_queue
from src.task_execution import TaskEventType, TaskStatusEnum, deep_thaw
from src.services.security_audit_service import SecurityAuditRecorder

logger = logging.getLogger(__name__)

router = APIRouter()


def _analysis_api_service_cls():
    """Lazy import to avoid api.v1 package init <-> service circular load."""
    from src.services.analysis_api_service import AnalysisApiService

    return AnalysisApiService


def _analysis_api_service():
    """Build a service bound to this module's collaborators (patch seams)."""
    return _analysis_api_service_cls()(
        get_task_queue=get_task_queue,
        resolve_name_to_code=resolve_name_to_code,
        resolve_index_stock_code=resolve_index_stock_code,
        resolve_index_stock_code_for_analysis=resolve_index_stock_code_for_analysis,
        load_sync_fundamental_sources=_load_sync_fundamental_sources,
        build_analysis_report=_build_analysis_report,
        run_market_review_background=_run_market_review_background,
        load_history_run_flow_by_query_id=_load_history_run_flow_by_query_id,
        get_config_instance=Config.get_instance,
        get_config_dep=get_config_dep,
        try_acquire_market_review_lock=_try_acquire_market_review_lock,
        release_market_review_lock=_release_market_review_lock,
        build_market_review_runtime=_build_market_review_runtime,
    )


def _require_analysis_audit_service(value: object) -> SecurityAuditRecorder:
    return _analysis_api_service_cls().require_analysis_audit_service(value)


def _record_analysis_submission_audit(
    service: SecurityAuditRecorder,
    *,
    phase: str,
    correlation_id: str,
    stock_code: str,
    outcome: str = "pending",
    reason_code: str = "attempt_started",
    metadata: dict[str, Any] | None = None,
) -> None:
    return _analysis_api_service_cls().record_analysis_submission_audit(
        service,
        phase=phase,
        correlation_id=correlation_id,
        stock_code=stock_code,
        outcome=outcome,
        reason_code=reason_code,
        metadata=metadata,
    )


def _get_task_trace_id(task: Any) -> Optional[str]:
    return _analysis_api_service_cls().get_task_trace_id(task)


def _get_task_message_code(task: Any, default: str = "task.status") -> str:
    return _analysis_api_service_cls().get_task_message_code(task, default)


def _get_task_message_params(task: Any, **fallback: Any) -> Dict[str, Any]:
    return _analysis_api_service_cls().get_task_message_params(task, **fallback)


def _market_review_lock_path(config: Config) -> Path:
    return market_review_lock_path(config)


def _build_market_review_runtime(config: Config) -> tuple[Any, Any, Any]:
    return _runtime_build_market_review_runtime(config)


def _with_request_report_language(config: Config, report_language: Optional[str]) -> Config:
    return _analysis_api_service_cls().with_request_report_language(config, report_language)


def _run_market_review_background(
    send_notification: bool,
    effective_region: str,
    lock_token: Optional[_MarketReviewExecutionLock] = None,
    config: Optional[Config] = None,
    query_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _analysis_api_service_cls()(
        get_task_queue=get_task_queue,
        get_config_dep=get_config_dep,
        try_acquire_market_review_lock=_try_acquire_market_review_lock,
        release_market_review_lock=_release_market_review_lock,
        build_market_review_runtime=_build_market_review_runtime,
    ).run_market_review_background(
        send_notification,
        effective_region,
        lock_token=lock_token,
        config=config,
        query_id=query_id,
    )


def _coalesce_text(*values: Any) -> Optional[str]:
    return _analysis_api_service_cls().coalesce_text(*values)


def _invalid_analysis_input_error():
    return _analysis_api_service_cls().invalid_analysis_input_error()


def _is_obviously_invalid_analysis_input(text: str) -> bool:
    return _analysis_api_service_cls().is_obviously_invalid_analysis_input(text)


def _resolve_and_normalize_input(raw_value: str) -> str:
    return _analysis_api_service().resolve_and_normalize_input(raw_value)


def _handle_async_analysis_batch(
    stock_codes: list,
    request: AnalyzeRequest,
    *,
    security_audit: SecurityAuditRecorder,
) -> JSONResponse:
    return _analysis_api_service().handle_async_analysis_batch(
        stock_codes,
        request,
        security_audit=security_audit,
    )


def _handle_sync_analysis(
    stock_code: str,
    request: AnalyzeRequest,
) -> AnalysisResultResponse:
    return _analysis_api_service().handle_sync_analysis(stock_code, request)


def _format_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    from src.services.analysis_api_service import format_sse_event

    return format_sse_event(event_type, data)


def _load_history_run_flow_by_query_id(
    query_id: str,
    *,
    code: Optional[str] = None,
    report_type: Optional[str] = None,
    fail_open: bool = False,
) -> Optional[RunFlowSnapshot]:
    return _analysis_api_service_cls()(
        get_task_queue=get_task_queue,
        resolve_index_stock_code=resolve_index_stock_code,
    ).load_history_run_flow_by_query_id(
        query_id,
        code=code,
        report_type=report_type,
        fail_open=fail_open,
    )


def _safe_task_flow_text(value: Any, *, max_length: int) -> Optional[str]:
    return _analysis_api_service_cls().safe_task_flow_text(value, max_length=max_length)


def _history_report_type_for_task_flow(value: Any) -> Optional[str]:
    return _analysis_api_service_cls().history_report_type_for_task_flow(value)


def _datetime_to_iso(value: Any) -> Optional[str]:
    return _analysis_api_service_cls().datetime_to_iso(value)


def _extract_report_created_at(payload: Dict[str, Any]) -> Optional[str]:
    return _analysis_api_service().extract_report_created_at(payload)


def _display_stock_code_from_index(stock_code: Any) -> str:
    return _analysis_api_service().display_stock_code_from_index(stock_code)


def _prepare_report_for_task_enrichment(
    report_data: Dict[str, Any],
    created_at: Optional[str],
) -> Dict[str, Any]:
    return _analysis_api_service_cls().prepare_report_for_task_enrichment(
        report_data, created_at
    )


def _build_task_analysis_result(task: Any) -> AnalysisResultResponse:
    return _analysis_api_service().build_task_analysis_result(task)


def _load_sync_fundamental_sources(
    query_id: str,
    stock_code: str,
):
    return _analysis_api_service_cls()(
        get_task_queue=get_task_queue,
        resolve_index_stock_code=resolve_index_stock_code,
    ).load_sync_fundamental_sources(query_id, stock_code)


def _build_analysis_report(
    report_data: Dict[str, Any],
    query_id: str,
    stock_code: str,
    stock_name: Optional[str] = None,
    context_snapshot: Optional[Any] = None,
    fallback_fundamental_payload: Optional[Dict[str, Any]] = None,
    fallback_raw_result_payload: Optional[Any] = None,
):
    return _analysis_api_service_cls()(
        get_task_queue=get_task_queue,
        resolve_index_stock_code=resolve_index_stock_code,
        get_config_instance=Config.get_instance,
    ).build_analysis_report(
        report_data,
        query_id,
        stock_code,
        stock_name,
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
        fallback_raw_result_payload=fallback_raw_result_payload,
    )


@router.post(
    "/analyze",
    response_model=AnalysisResultResponse,
    responses={
        200: {"description": "分析完成（同步模式）", "model": AnalysisResultResponse},
        202: {
            "description": "分析任务已接受（异步模式）",
            "model": Union[TaskAccepted, BatchTaskAcceptedResponse],
        },
        400: {"description": "请求参数错误", "model": ErrorResponse},
        409: {"description": "股票正在分析中，拒绝重复提交", "model": DuplicateTaskErrorResponse},
        500: {"description": "分析失败", "model": ErrorResponse},
        503: {"description": "Security audit unavailable", "model": ErrorResponse},
    },
    summary="触发股票分析",
    description="启动 AI 智能分析任务，支持同步和异步模式。异步模式下相同股票代码不允许重复提交。"
)
def trigger_analysis(
        request: AnalyzeRequest,
        config: Config = Depends(get_config_dep),
        security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
) -> Union[AnalysisResultResponse, JSONResponse]:
    """Trigger stock analysis (sync or async)."""
    return _analysis_api_service().trigger_analysis(
        request,
        config=config,
        security_audit=security_audit,
    )


@router.post(
    "/market-review",
    response_model=MarketReviewAccepted,
    status_code=202,
    responses={
        202: {"description": "大盘复盘任务已接受", "model": MarketReviewAccepted},
        409: {"description": "大盘复盘正在执行", "model": ErrorResponse},
        500: {"description": "提交失败", "model": ErrorResponse},
    },
    summary="触发大盘复盘",
    description="提交一个后台大盘复盘任务，复用 CLI 的大盘复盘运行时装配并保存报告。该人工触发入口不按交易日检查跳过；接口内部仅提供进程内/单机防重，如多实例（多 Worker/多容器）部署，需结合外部幂等机制避免重复触发。",
)
def trigger_market_review(
    request: Optional[MarketReviewRequest] = Body(None),
    config: Config = Depends(get_config_dep),
) -> MarketReviewAccepted:
    """Trigger market review from Web/API without blocking the request."""
    return _analysis_api_service().trigger_market_review(request, config=config)


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    responses={
        200: {"description": "任务列表"},
    },
    summary="获取分析任务列表",
    description="获取当前所有分析任务，可按状态筛选"
)
def get_task_list(
    status: Optional[str] = Query(
        None,
        description=(
            "筛选状态：pending, processing, completed, failed, cancel_requested, "
            "cancelled, interrupted（支持逗号分隔多个）"
        )
    ),
    limit: int = Query(20, description="返回数量限制", ge=1, le=100),
) -> TaskListResponse:
    """Get the analysis task list."""
    return _analysis_api_service().get_task_list(status=status, limit=limit)


@router.get(
    "/tasks/stream",
    responses={
        200: {"description": "SSE 事件流", "content": {"text/event-stream": {}}},
    },
    summary="任务状态 SSE 流",
    description="通过 Server-Sent Events 实时推送任务状态变化"
)
async def task_stream():
    """SSE task status stream (transport adapter over the process-local queue)."""
    async def event_generator():
        task_queue = get_task_queue()
        stream = task_queue.subscribe_all()
        try:
            yield _format_sse_event("connected", {"message": "Connected to task stream"})
            while True:
                try:
                    event = await stream.receive(timeout=30)
                    legacy_type = {
                        TaskEventType.CREATED: "task_created",
                        TaskEventType.SNAPSHOT: "task_created",
                        TaskEventType.STARTED: "task_started",
                        TaskEventType.PROGRESS: "task_progress",
                        TaskEventType.CANCEL_REQUESTED: "task_progress",
                        TaskEventType.COMPLETED: "task_completed",
                        TaskEventType.FAILED: "task_failed",
                        TaskEventType.CANCELLED: "task_failed",
                        TaskEventType.INTERRUPTED: "task_failed",
                    }[event.type]
                    yield _format_sse_event(legacy_type, deep_thaw(event.data))
                except asyncio.TimeoutError:
                    yield _format_sse_event("heartbeat", {
                        "timestamp": datetime.now().isoformat()
                    })
                except StopAsyncIteration:
                    break
        except asyncio.CancelledError:
            logger.debug("SSE client disconnected, cancelling event generator")
            raise
        finally:
            await stream.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get(
    "/tasks/{task_id}/flow",
    response_model=RunFlowSnapshot,
    responses={
        200: {"description": "任务运行流快照"},
        404: {"description": "任务不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取分析任务运行流",
    description="根据 task_id 查询任务数据流/信息流快照；活跃任务缺少诊断时返回骨架流。",
)
def get_task_run_flow(task_id: str) -> RunFlowSnapshot:
    """Query an analysis task run-flow snapshot."""
    return _analysis_api_service().get_task_run_flow(task_id)


@router.get(
    "/status/{task_id}",
    response_model=TaskStatus,
    responses={
        200: {"description": "任务状态"},
        404: {"description": "任务不存在", "model": ErrorResponse},
    },
    summary="查询分析任务状态",
    description="根据 task_id 查询单个任务的状态"
)
def get_analysis_status(task_id: str) -> TaskStatus:
    """Query analysis task status from the queue, then history."""
    return _analysis_api_service().get_analysis_status(task_id)
