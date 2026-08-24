# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated read-only prediction resolver diagnostics API (Issue #1114)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Security
from fastapi.security import APIKeyCookie

from src.api.v1.errors import api_error
from src.api.v1.schemas.common import ErrorResponse
from src.api.v1.schemas.prediction_resolver_diagnostics import (
    PredictionResolverDiagnosticsResponse,
)
from src.application_services import get_application_services
from src.auth import COOKIE_NAME
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.services.prediction_resolver_diagnostics import (
    PredictionResolverDiagnosticsStoreError,
    collect_prediction_resolver_diagnostics,
)


admin_session_cookie = APIKeyCookie(
    name=COOKIE_NAME,
    scheme_name="AdminSessionCookie",
    auto_error=False,
)
router = APIRouter(dependencies=[Security(admin_session_cookie)])

AUTH_RESPONSE = {
    401: {
        "model": ErrorResponse,
        "description": "未登录或管理员会话无效（ADMIN_AUTH_ENABLED=true 时）",
    },
}


@router.get(
    "/prediction-resolver/diagnostics",
    response_model=PredictionResolverDiagnosticsResponse,
    responses={
        **AUTH_RESPONSE,
        503: {
            "model": ErrorResponse,
            "description": "预测存储不可读，无法探测 claimable due 或 UTC 日结果计数",
        },
    },
    summary="读取预测解析器到期诊断",
    description=(
        "只读返回当前可认领的到期预测（pending 与已过期 resolving 租约），"
        "以及 observed_at 所在 UTC 自然日的持久化结果计数。"
        "不会 tick、认领、重新排队或启动 worker。"
        "this_process_worker_registered 仅表示本 API 进程是否登记了 "
        "prediction_resolver 后台任务，不是全局 worker 健康。"
    ),
    operation_id="getPredictionResolverDiagnostics",
)
def get_prediction_resolver_diagnostics(
    request: Request,
) -> PredictionResolverDiagnosticsResponse:
    scheduler = getattr(request.app.state, "runtime_scheduler_service", None)
    store = AgentPredictionRepository()
    try:
        payload = collect_prediction_resolver_diagnostics(
            config=get_application_services().config,
            store=store,
            scheduler=scheduler,
        )
    except PredictionResolverDiagnosticsStoreError as exc:
        raise api_error(
            503,
            "internal_error",
            "Prediction resolver diagnostics store is unavailable",
        ) from exc
    return PredictionResolverDiagnosticsResponse(**payload)
