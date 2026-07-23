# -*- coding: utf-8 -*-
"""Public signal scorecard endpoint (Issue #379).

An opt-in, no-auth transparency surface. Disabled by default so self-hosted
deployments stay private; when enabled it returns aggregated, non-sensitive
statistics only.
"""

import logging

from fastapi import APIRouter, HTTPException

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.scorecard import SignalScorecardResponse
from src.config import get_config
from src.services.signal_scorecard_service import SignalScorecardService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

# No Security dependency: this router is public. Exposure is still gated at
# request time by SIGNAL_SCORECARD_PUBLIC_ENABLED, and the path is added to the
# auth middleware's exempt list so it stays reachable without a session.
router = APIRouter()


@router.get(
    "",
    response_model=SignalScorecardResponse,
    responses={
        404: {"model": ErrorResponse, "description": "公开计分卡未开启"},
        500: {"model": ErrorResponse, "description": "聚合失败"},
    },
    summary="公开信号计分卡",
    description=(
        "聚合的公开信号战绩：按信号类型与周期的命中率、收益分布、近期偏离案例。"
        "默认关闭；需将 SIGNAL_SCORECARD_PUBLIC_ENABLED 设为 true 才对外可见；"
        "仅输出聚合、非敏感数据（不含个股身份）。样本不足的桶返回 insufficient_data。"
    ),
    operation_id="getPublicSignalScorecard",
)
def get_public_scorecard() -> SignalScorecardResponse:
    config = get_config()
    if not getattr(config, "signal_scorecard_public_enabled", False):
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Public scorecard is not enabled"},
        )
    try:
        payload = SignalScorecardService().build_scorecard(
            min_samples=int(getattr(config, "signal_scorecard_min_samples", 10)),
        )
        return SignalScorecardResponse(**payload)
    except Exception as exc:  # broad-exception: fallback_recorded - map scorecard aggregation failures to a sanitized API error
        log_safe_exception(
            logger, "Build public signal scorecard failed", exc, error_code="internal_error"
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Build public signal scorecard failed"},
        )
