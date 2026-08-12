# -*- coding: utf-8 -*-
"""Paper-trading process decision quality endpoint (Issue #1134)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Path, Query

from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.paper_decision_quality import PaperDecisionQualityResponse
from src.services.paper_decision_quality_service import (
    PaperAccountNotFoundError,
    PaperDecisionQualityService,
)
from src.services.paper_portfolio_service import PaperAccountRequiredError
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/accounts/{account_id}/paper-decision-quality",
    response_model=PaperDecisionQualityResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Score paper-trading decisions on process quality (not PnL)",
    description=(
        "Returns explainable process scores for simulated trades on a paper account: "
        "analysis support, risk-gate compliance, and position discipline. "
        "This is not a return or win-rate evaluation. Outcome metrics remain owned by "
        "DecisionSignal post-hoc calibration (issue #987)."
    ),
    operation_id="getPaperDecisionQuality",
)
def get_paper_decision_quality(
    account_id: int = Path(..., ge=1, description="Paper account ID"),
    date_from: Optional[date] = Query(None, description="Optional trade date from"),
    date_to: Optional[date] = Query(None, description="Optional trade date to"),
    limit: int = Query(50, ge=1, le=200, description="Max trades to score"),
) -> PaperDecisionQualityResponse:
    service = PaperDecisionQualityService()
    try:
        data = service.score_paper_account(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
        return PaperDecisionQualityResponse(**data)
    except PaperAccountNotFoundError as exc:
        raise api_error(404, "account_not_found", str(exc)) from exc
    except PaperAccountRequiredError as exc:
        raise api_error(400, "paper_account_required", str(exc)) from exc
    except ValueError as exc:
        raise api_error(400, "bad_request", str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary
        log_safe_exception(
            logger,
            "Get paper decision quality failed",
            exc,
            error_code="paper_decision_quality_failed",
        )
        raise api_error(
            500,
            "paper_decision_quality_failed",
            "Get paper decision quality failed",
        ) from exc
