# -*- coding: utf-8 -*-
"""Authenticated skill-opinion outcome endpoints (V0 read + explicit run)."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.security import APIKeyCookie

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.skill_outcomes import (
    SkillOpinionOutcomeListResponse,
    SkillOpinionOutcomeRunRequest,
    SkillOpinionOutcomeRunResponse,
    SkillOpinionPerformanceStatsResponse,
    SkillOpinionSampleListResponse,
)
from src.auth import COOKIE_NAME
from src.services.skill_opinion_outcome_service import (
    SKILL_OPINION_OUTCOME_ENGINE_VERSION,
    SkillOpinionOutcomeService,
)
from src.services.skill_opinion_performance_service import (
    SkillOpinionPerformanceService,
)
from src.services.skill_opinion_sample_service import SkillOpinionSampleService
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


def _bad_request(exc: Exception, *, error: str = "validation_error") -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": error, "message": str(exc)},
    )




@router.post(
    "/run",
    response_model=SkillOpinionOutcomeRunResponse,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "请求字段非法"},
        422: {"model": ErrorResponse, "description": "请求体校验失败"},
        500: {"model": ErrorResponse, "description": "评估失败"},
    },
    summary="触发技能观点后验评估",
    description=(
        "显式触发 skill-opinion sample materialization 与 offline outcome 评估。"
        "V0 不新增调度器；limit 计数 outcome keys，不计数 samples。"
        "不拉取或回填行情。"
    ),
    operation_id="runSkillOpinionOutcomes",
)
def run_outcomes(
    request: SkillOpinionOutcomeRunRequest,
) -> SkillOpinionOutcomeRunResponse:
    service = SkillOpinionOutcomeService()
    try:
        return SkillOpinionOutcomeRunResponse(
            **service.run_outcomes(
                sample_id=request.sample_id,
                analysis_history_id=request.analysis_history_id,
                skill_id=request.skill_id,
                stock_code=request.stock_code,
                horizons=request.horizons,
                limit=request.limit,
            )
        )
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map run failures to a sanitized API error
        log_safe_exception(
            logger,
            "Run skill opinion outcomes failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Run skill opinion outcomes failed",
            },
        )


@router.get(
    "",
    response_model=SkillOpinionOutcomeListResponse,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "查询参数非法"},
        422: {"model": ErrorResponse, "description": "查询参数校验失败"},
        500: {"model": ErrorResponse, "description": "查询失败"},
    },
    summary="查询技能观点后验结果",
    description="分页查询 skill-opinion outcome；默认当前 engine_version。",
    operation_id="listSkillOpinionOutcomes",
)
def list_outcomes(
    skill_id: Optional[str] = Query(None, min_length=1, max_length=128),
    stock_code: Optional[str] = Query(None, min_length=1, max_length=16),
    horizon: Optional[str] = Query(None),
    eval_status: Optional[str] = Query(None),
    sample_id: Optional[int] = Query(None, gt=0),
    analysis_history_id: Optional[int] = Query(None, gt=0),
    engine_version: Optional[str] = Query(None, min_length=1, max_length=32),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SkillOpinionOutcomeListResponse:
    service = SkillOpinionOutcomeService()
    try:
        return SkillOpinionOutcomeListResponse(
            **service.list_outcomes(
                skill_id=skill_id,
                stock_code=stock_code,
                horizon=horizon,
                eval_status=eval_status,
                sample_id=sample_id,
                analysis_history_id=analysis_history_id,
                engine_version=engine_version,
                limit=limit,
                offset=offset,
            )
        )
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map list failures to a sanitized API error
        log_safe_exception(
            logger,
            "List skill opinion outcomes failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "List skill opinion outcomes failed",
            },
        )


@router.get(
    "/stats",
    response_model=SkillOpinionPerformanceStatsResponse,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "查询参数非法"},
        422: {"model": ErrorResponse, "description": "查询参数校验失败"},
        500: {"model": ErrorResponse, "description": "统计失败"},
    },
    summary="查询技能观点后验统计",
    description=(
        "按 skill_id + horizon + engine_version 独立分桶；"
        "不足 30 个 evaluated 样本时只返回计数，不返回比率。"
    ),
    operation_id="getSkillOpinionOutcomeStats",
)
def get_stats(
    skill_id: Optional[str] = Query(None, min_length=1, max_length=128),
    skill_ids: Optional[List[str]] = Query(None),
    horizons: Optional[List[str]] = Query(None),
    engine_version: Optional[str] = Query(None, min_length=1, max_length=32),
) -> SkillOpinionPerformanceStatsResponse:
    service = SkillOpinionPerformanceService()
    try:
        payload = service.get_stats(
            skill_id=skill_id,
            skill_ids=skill_ids,
            horizons=horizons,
            engine_version=(
                engine_version
                if engine_version is not None
                else SKILL_OPINION_OUTCOME_ENGINE_VERSION
            ),
        )
        return SkillOpinionPerformanceStatsResponse(**payload)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map stats failures to a sanitized API error
        log_safe_exception(
            logger,
            "Get skill opinion outcome stats failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Get skill opinion outcome stats failed",
            },
        )


@router.get(
    "/samples",
    response_model=SkillOpinionSampleListResponse,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "查询参数非法"},
        422: {"model": ErrorResponse, "description": "查询参数校验失败"},
        500: {"model": ErrorResponse, "description": "查询失败"},
    },
    summary="查询最近技能观点样本",
    description="只读返回低敏感 skill opinion samples；不含 reasoning 或模型原文。",
    operation_id="listSkillOpinionSamples",
)
def list_samples(
    skill_id: Optional[str] = Query(None, min_length=1, max_length=128),
    stock_code: Optional[str] = Query(None, min_length=1, max_length=16),
    analysis_history_id: Optional[int] = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SkillOpinionSampleListResponse:
    service = SkillOpinionSampleService()
    try:
        return SkillOpinionSampleListResponse(
            **service.list_recent_samples(
                skill_id=skill_id,
                stock_code=stock_code,
                analysis_history_id=analysis_history_id,
                limit=limit,
                offset=offset,
            )
        )
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - map sample list failures to a sanitized API error
        log_safe_exception(
            logger,
            "List skill opinion samples failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "List skill opinion samples failed",
            },
        )
