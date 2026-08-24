# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated optional run and prediction feedback APIs (Issue #1105)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Security
from fastapi.security import APIKeyCookie

from src.api.v1.schemas.agent_feedback import (
    AgentPredictionFeedbackItem,
    AgentPredictionFeedbackRequest,
    AgentRunFeedbackItem,
    AgentRunFeedbackRequest,
)
from src.api.v1.schemas.common import ErrorResponse
from src.auth import COOKIE_NAME
from src.services.agent_feedback_service import (
    AgentFeedbackNotFoundError,
    AgentFeedbackService,
    AgentFeedbackUnresolvedError,
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

FeedbackIdPath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=128,
        pattern=r"^\S+$",
    ),
]


def _bad_request(exc: Exception, *, error: str = "validation_error") -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": error, "message": str(exc)},
    )


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": "not_found", "message": str(exc)},
    )


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error": "conflict", "message": str(exc)},
    )


@router.get(
    "/runs/{run_id}/feedback",
    response_model=AgentRunFeedbackItem,
    responses={
        **AUTH_RESPONSE,
        404: {"model": ErrorResponse, "description": "分析 run 不存在"},
        422: {"model": ErrorResponse, "description": "路径参数校验失败"},
        500: {"model": ErrorResponse, "description": "查询失败"},
    },
    summary="查询分析 run 用户反馈",
    description=(
        "按 canonical run_id 读取最新 sidecar 意见。没有反馈时返回 "
        "feedback_value=null；未知 run 身份返回 404。不改写预测 actuals 或 episode。"
    ),
    operation_id="getAgentRunFeedback",
)
def get_run_feedback(run_id: FeedbackIdPath) -> AgentRunFeedbackItem:
    service = AgentFeedbackService()
    try:
        return AgentRunFeedbackItem(**service.get_run_feedback(run_id))
    except AgentFeedbackNotFoundError as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map run feedback reads to a sanitized API error
        log_safe_exception(
            logger, "Get agent run feedback failed", exc, error_code="internal_error"
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Get agent run feedback failed"},
        )


@router.put(
    "/runs/{run_id}/feedback",
    response_model=AgentRunFeedbackItem,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "请求字段非法"},
        404: {"model": ErrorResponse, "description": "分析 run 不存在"},
        422: {"model": ErrorResponse, "description": "请求体或路径参数校验失败"},
        500: {"model": ErrorResponse, "description": "更新失败"},
    },
    summary="写入分析 run 用户反馈",
    description=(
        "按 canonical run_id upsert 最新 useful|partial|wrong|harmful 反馈。"
        "意见只写入 sidecar；不会改写 agent_predictions.outcome_json 或 "
        "UPDATE append-only agent_episodes。"
    ),
    operation_id="putAgentRunFeedback",
)
def put_run_feedback(
    request: AgentRunFeedbackRequest,
    run_id: FeedbackIdPath,
) -> AgentRunFeedbackItem:
    service = AgentFeedbackService()
    try:
        return AgentRunFeedbackItem(
            **service.put_run_feedback(
                run_id,
                feedback_value=request.feedback_value,
                note=request.note,
                source=request.source,
            )
        )
    except AgentFeedbackNotFoundError as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map run feedback writes to a sanitized API error
        log_safe_exception(
            logger, "Put agent run feedback failed", exc, error_code="internal_error"
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Put agent run feedback failed"},
        )


@router.get(
    "/predictions/{prediction_id}/feedback",
    response_model=AgentPredictionFeedbackItem,
    responses={
        **AUTH_RESPONSE,
        404: {"model": ErrorResponse, "description": "预测不存在"},
        422: {"model": ErrorResponse, "description": "路径参数校验失败"},
        500: {"model": ErrorResponse, "description": "查询失败"},
    },
    summary="查询预测用户反馈",
    description=(
        "按 prediction_id 读取最新 sidecar 意见。没有反馈时返回 "
        "feedback_value=null；未知 prediction 返回 404。"
    ),
    operation_id="getAgentPredictionFeedback",
)
def get_prediction_feedback(
    prediction_id: FeedbackIdPath,
) -> AgentPredictionFeedbackItem:
    service = AgentFeedbackService()
    try:
        return AgentPredictionFeedbackItem(
            **service.get_prediction_feedback(prediction_id)
        )
    except AgentFeedbackNotFoundError as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map prediction feedback reads to a sanitized API error
        log_safe_exception(
            logger, "Get agent prediction feedback failed", exc, error_code="internal_error"
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Get agent prediction feedback failed"},
        )


@router.put(
    "/predictions/{prediction_id}/feedback",
    response_model=AgentPredictionFeedbackItem,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "请求字段非法"},
        404: {"model": ErrorResponse, "description": "预测不存在"},
        409: {"model": ErrorResponse, "description": "预测尚未 resolved"},
        422: {"model": ErrorResponse, "description": "请求体或路径参数校验失败"},
        500: {"model": ErrorResponse, "description": "更新失败"},
    },
    summary="写入预测用户反馈",
    description=(
        "按已落地 prediction_id upsert 最新 agree_hit|agree_miss|disagree_score|"
        "context_note 反馈。仅 resolved 预测可写入，未 resolved 返回 409。"
        "混入行情 actuals、Soul 边界标记、超限备注或客户端 provenance 的载荷会被拒绝且不落库。"
    ),
    operation_id="putAgentPredictionFeedback",
)
def put_prediction_feedback(
    request: AgentPredictionFeedbackRequest,
    prediction_id: FeedbackIdPath,
) -> AgentPredictionFeedbackItem:
    service = AgentFeedbackService()
    try:
        return AgentPredictionFeedbackItem(
            **service.put_prediction_feedback(
                prediction_id,
                feedback_value=request.feedback_value,
                note=request.note,
                source=request.source,
            )
        )
    except AgentFeedbackNotFoundError as exc:
        raise _not_found(exc)
    except AgentFeedbackUnresolvedError as exc:
        raise _conflict(exc)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map prediction feedback writes to a sanitized API error
        log_safe_exception(
            logger, "Put agent prediction feedback failed", exc, error_code="internal_error"
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Put agent prediction feedback failed"},
        )
