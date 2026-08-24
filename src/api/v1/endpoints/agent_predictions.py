# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated read-only prediction get-by-id and list APIs (Issue #1102)."""

from __future__ import annotations

import logging
from typing import Annotated, FrozenSet

from fastapi import APIRouter, Path, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.security import APIKeyCookie

from src.api.v1.errors import api_error
from src.api.v1.schemas.agent_predictions import (
    AgentPredictionItem,
    AgentPredictionListQuery,
    AgentPredictionListResponse,
)
from src.api.v1.schemas.common import ErrorResponse
from src.auth import COOKIE_NAME
from src.services.agent_prediction_query import (
    AgentPredictionFilterError,
    AgentPredictionNotFoundError,
    AgentPredictionQueryService,
)
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

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

PredictionIdPath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=128,
        pattern=r"^\S+$",
    ),
]

_LIST_QUERY_KEYS: FrozenSet[str] = frozenset({"run_id", "symbol", "market", "limit"})


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
    "/predictions/{prediction_id}",
    response_model=AgentPredictionItem,
    responses={
        **AUTH_RESPONSE,
        404: {"model": ErrorResponse, "description": "预测不存在"},
        422: {"model": ErrorResponse, "description": "路径参数校验失败"},
        500: {"model": ErrorResponse, "description": "查询失败"},
    },
    summary="按 id 查询预测",
    description=(
        "按 prediction_id 返回允许列表中的身份、状态与有界 outcome_label。"
        "未知 id 返回 404。不会返回 outcome/claims/leases/model_meta/价格，"
        "也不会 tick、认领或写回预测。"
    ),
    operation_id="getAgentPrediction",
)
def get_agent_prediction(prediction_id: PredictionIdPath) -> AgentPredictionItem:
    service = AgentPredictionQueryService()
    try:
        return AgentPredictionItem(**service.get_prediction(prediction_id))
    except AgentPredictionNotFoundError as exc:
        raise api_error(404, "not_found", str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map prediction get to sanitized API error
        log_safe_exception(
            logger, "Get agent prediction failed", exc, error_code="internal_error"
        )
        raise api_error(
            500, "internal_error", "Get agent prediction failed"
        ) from exc


@router.get(
    "/predictions",
    response_model=AgentPredictionListResponse,
    responses={
        **AUTH_RESPONSE,
        422: {"model": ErrorResponse, "description": "查询参数校验失败"},
        500: {"model": ErrorResponse, "description": "查询失败"},
    },
    summary="按 run 或标的查询预测列表",
    description=(
        "必须且只能使用一种身份过滤：run_id，或同时提供 symbol 与 market。"
        "limit 默认 50、上限 50。零行返回 200 空列表。只读，不暴露 list_due。"
    ),
    operation_id="listAgentPredictions",
)
def list_agent_predictions(
    request: Request,
    query: Annotated[AgentPredictionListQuery, Query()],
) -> AgentPredictionListResponse:
    _reject_unknown_query_params(request)
    service = AgentPredictionQueryService()
    try:
        payload = service.list_predictions(
            run_id=query.run_id,
            symbol=query.symbol,
            market=query.market,
            limit=query.limit,
        )
        return AgentPredictionListResponse(**payload)
    except AgentPredictionFilterError as exc:
        raise api_error(422, "validation_error", str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map prediction list to sanitized API error
        log_safe_exception(
            logger, "List agent predictions failed", exc, error_code="internal_error"
        )
        raise api_error(
            500, "internal_error", "List agent predictions failed"
        ) from exc
