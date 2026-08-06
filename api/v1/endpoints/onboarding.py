# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API for agent-guided onboarding plan generation and apply."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends

from api.deps import get_system_config_service
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.onboarding import (
    OnboardingApplyRequest,
    OnboardingApplyResponse,
    OnboardingPlanRequest,
    OnboardingPlanResponse,
    OnboardingResetResponse,
    OnboardingStateResponse,
)
from src.services.onboarding_plan_service import (
    OnboardingPlanError,
    OnboardingPlanService,
    OnboardingProfileValidationError,
    OnboardingSecretRejectedError,
)
from src.services.system_config_service import (
    ConfigConflictError,
    ConfigValidationError,
    SystemConfigService,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()

_ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}


def _plan_service(system_config: SystemConfigService) -> OnboardingPlanService:
    return OnboardingPlanService(system_config_service=system_config)


def _plan_response(payload: Dict[str, Any]) -> OnboardingPlanResponse:
    return OnboardingPlanResponse.model_validate(payload)


@router.post(
    "/plan",
    response_model=OnboardingPlanResponse,
    responses=_ERROR_RESPONSES,
    summary="Generate an agent-guided onboarding plan",
    description=(
        "Rule-based plan generation is the default. "
        "When prefer_llm is true but no model is available, the response stays "
        "engine=rules with an honest llm_note (no fake AI)."
    ),
)
def generate_onboarding_plan(
    request: OnboardingPlanRequest,
    system_config: SystemConfigService = Depends(get_system_config_service),
) -> OnboardingPlanResponse:
    service = _plan_service(system_config)
    try:
        payload = service.build_plan(
            request.profile.model_dump(),
            model_available=request.model_available,
            prefer_llm=request.prefer_llm,
        )
        return _plan_response(payload)
    except OnboardingProfileValidationError as exc:
        raise api_error(
            400,
            exc.error_code,
            str(exc),
            params={"issues": exc.issues},
        ) from exc
    except OnboardingPlanError as exc:
        raise api_error(400, exc.error_code, str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded
        log_safe_exception(
            logger,
            "Onboarding plan generation failed",
            exc,
            error_code="onboarding_plan_internal_error",
        )
        raise api_error(500, "internal_error", "Failed to generate onboarding plan") from exc


@router.post(
    "/apply",
    response_model=OnboardingApplyResponse,
    responses=_ERROR_RESPONSES,
    summary="Apply non-secret onboarding config recommendations",
    description=(
        "Writes only non-secret config keys through SystemConfigService. "
        "Secrets are never invented; remaining secret steps stay in the plan todos."
    ),
)
def apply_onboarding_plan(
    request: OnboardingApplyRequest,
    system_config: SystemConfigService = Depends(get_system_config_service),
) -> OnboardingApplyResponse:
    service = _plan_service(system_config)
    try:
        payload = service.apply_plan(
            request.profile.model_dump(),
            config_version=request.config_version,
            model_available=request.model_available,
            prefer_llm=request.prefer_llm,
            confirm=request.confirm,
        )
        return OnboardingApplyResponse.model_validate({
            **payload,
            "plan": payload["plan"],
        })
    except OnboardingProfileValidationError as exc:
        raise api_error(
            400,
            exc.error_code,
            str(exc),
            params={"issues": exc.issues},
        ) from exc
    except OnboardingSecretRejectedError as exc:
        raise api_error(400, exc.error_code, str(exc)) from exc
    except ConfigValidationError as exc:
        raise api_error(
            400,
            "validation_failed",
            "System configuration validation failed",
            params={"issues": exc.issues},
        ) from exc
    except ConfigConflictError as exc:
        raise api_error(
            409,
            "config_version_conflict",
            "Configuration has changed, please reload and retry",
            params={"current_config_version": exc.current_version},
        ) from exc
    except OnboardingPlanError as exc:
        raise api_error(400, exc.error_code, str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded
        log_safe_exception(
            logger,
            "Onboarding plan apply failed",
            exc,
            error_code="onboarding_apply_internal_error",
        )
        raise api_error(500, "internal_error", "Failed to apply onboarding plan") from exc


@router.get(
    "/state",
    response_model=OnboardingStateResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get persisted onboarding profile and last plan",
)
def get_onboarding_state(
    system_config: SystemConfigService = Depends(get_system_config_service),
) -> OnboardingStateResponse:
    service = _plan_service(system_config)
    try:
        state = service.get_state()
        if not state:
            return OnboardingStateResponse(exists=False)
        plan = state.get("plan")
        return OnboardingStateResponse(
            exists=True,
            status=state.get("status"),
            profile=state.get("profile"),
            plan=_plan_response(plan) if isinstance(plan, dict) else None,
            applied_at=state.get("applied_at"),
            applied_keys=list(state.get("applied_keys") or []),
            config_version=state.get("config_version"),
        )
    except Exception as exc:  # broad-exception: fallback_recorded
        log_safe_exception(
            logger,
            "Onboarding state load failed",
            exc,
            error_code="onboarding_state_internal_error",
        )
        raise api_error(500, "internal_error", "Failed to load onboarding state") from exc


@router.delete(
    "/state",
    response_model=OnboardingResetResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Reset persisted onboarding profile (keeps already written config)",
)
def reset_onboarding_state(
    system_config: SystemConfigService = Depends(get_system_config_service),
) -> OnboardingResetResponse:
    service = _plan_service(system_config)
    try:
        payload = service.reset_state()
        return OnboardingResetResponse.model_validate(payload)
    except OnboardingPlanError as exc:
        raise api_error(500, exc.error_code, str(exc)) from exc
    except Exception as exc:  # broad-exception: fallback_recorded
        log_safe_exception(
            logger,
            "Onboarding state reset failed",
            exc,
            error_code="onboarding_reset_internal_error",
        )
        raise api_error(500, "internal_error", "Failed to reset onboarding state") from exc
