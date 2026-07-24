"""Catalog-backed local model runtime and activation endpoints."""

from __future__ import annotations

import logging
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_local_model_service
from api.v1.schemas.local_models import (
    LocalModelAssignmentRequest,
    LocalModelConfigurationResponse,
    LocalModelDesktopActivationRequest,
    LocalModelDesktopUnregistrationRequest,
    LocalModelMutationResponse,
    LocalModelPullAccepted,
    LocalModelPullStatus,
    LocalModelRegistrationRestoreRequest,
    LocalModelRequest,
    LocalModelRuntimeResponse,
    LocalModelUnregistrationResponse,
)
from src.services.local_model_service import (
    LocalModelError,
    LocalModelInUseError,
    LocalModelNotInstalledError,
    LocalModelNotAllowedError,
    LocalModelRuntimeRequestError,
    LocalModelRuntimeUnavailableError,
    LocalModelService,
    LocalModelValidationError,
)
from src.services.system_config_service import ConfigConflictError, ConfigValidationError
from src.services.task_queue import TaskStatus
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)
router = APIRouter()


def _raise_local_model_error(exc: Exception, *, model_id: str = "") -> NoReturn:
    """Map internal local-model failures to stable caller-safe API errors."""
    if isinstance(exc, LocalModelValidationError):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(
        exc,
        (LocalModelNotAllowedError, LocalModelNotInstalledError, LocalModelInUseError),
    ):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, (LocalModelRuntimeUnavailableError, LocalModelRuntimeRequestError)):
        # Keep this as a public dependency failure. The global API boundary
        # deliberately redacts all 5xx details, which would discard the safe
        # manual pull fallback the model center needs to render.
        status_code = status.HTTP_424_FAILED_DEPENDENCY
    elif isinstance(exc, ConfigValidationError):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, ConfigConflictError):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    error_code = getattr(exc, "error_code", None)
    if not error_code:
        error_code = "config_version_conflict" if isinstance(exc, ConfigConflictError) else "local_model_error"
    detail = {
        "error": error_code,
        "message": "The local model operation could not be completed",
    }
    if isinstance(exc, LocalModelRuntimeUnavailableError) and model_id:
        detail["manual_command"] = f"ollama pull {model_id}"
    raise HTTPException(status_code=status_code, detail=detail)


@router.get("/runtime", response_model=LocalModelRuntimeResponse)
def get_local_model_runtime(
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelRuntimeResponse:
    """Return runtime availability and current saved assignments."""
    try:
        payload = service.get_runtime_status()
        payload["configuration"] = service.get_configuration()
        return LocalModelRuntimeResponse.model_validate(payload)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API boundary
        log_safe_exception(logger, "Local model runtime status failed", exc, error_code="local_model_status_failed")
        _raise_local_model_error(exc)


@router.get("/configuration", response_model=LocalModelConfigurationResponse)
def get_local_model_configuration(
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelConfigurationResponse:
    """Return caller-safe registered and assigned local models."""
    try:
        return LocalModelConfigurationResponse.model_validate(service.get_configuration())
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API boundary
        log_safe_exception(logger, "Local model configuration load failed", exc, error_code="local_model_config_failed")
        _raise_local_model_error(exc)


@router.post(
    "/pulls",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=LocalModelPullAccepted,
)
def start_local_model_pull(
    request: LocalModelRequest,
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelPullAccepted:
    """Submit one catalog-allowlisted Ollama pull task."""
    try:
        task = service.start_pull(request.model_id)
        task_status = task.status.value if isinstance(task.status, TaskStatus) else str(task.status)
        return LocalModelPullAccepted(
            task_id=task.task_id,
            trace_id=task.trace_id or task.task_id,
            status=task_status,
            model_id=task.stock_code,
        )
    except (LocalModelError, ConfigValidationError, ConfigConflictError) as exc:
        _raise_local_model_error(exc, model_id=request.model_id)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API boundary
        log_safe_exception(logger, "Local model pull submission failed", exc, error_code="local_model_pull_submit_failed")
        _raise_local_model_error(exc, model_id=request.model_id)


@router.get("/pulls/{task_id}", response_model=LocalModelPullStatus)
def get_local_model_pull(
    task_id: str,
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelPullStatus:
    """Poll one local model pull task."""
    payload = service.get_pull(task_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "local_model_pull_not_found", "message": "Local model pull task not found"},
        )
    return LocalModelPullStatus.model_validate(payload)


@router.post("/assignments", response_model=LocalModelMutationResponse)
def assign_local_model(
    request: LocalModelAssignmentRequest,
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelMutationResponse:
    """Register or explicitly assign one local model through SystemConfigService."""
    try:
        payload = service.configure_model(request.model_id, assignment=request.assignment)
        payload["success"] = True
        return LocalModelMutationResponse.model_validate(payload)
    except (LocalModelError, ConfigValidationError, ConfigConflictError) as exc:
        _raise_local_model_error(exc, model_id=request.model_id)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API boundary
        log_safe_exception(logger, "Local model assignment failed", exc, error_code="local_model_assignment_failed")
        _raise_local_model_error(exc, model_id=request.model_id)


@router.post("/desktop-activations", response_model=LocalModelMutationResponse)
def activate_desktop_local_model(
    request: LocalModelDesktopActivationRequest,
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelMutationResponse:
    """Activate a Desktop pull only if its configuration and runtime stayed fixed."""
    try:
        payload = service.activate_desktop_model(
            request.model_id,
            expected_config_version=request.expected_config_version,
            expected_runtime_identity=request.expected_runtime_identity,
        )
        payload["success"] = True
        return LocalModelMutationResponse.model_validate(payload)
    except (LocalModelError, ConfigValidationError, ConfigConflictError) as exc:
        _raise_local_model_error(exc, model_id=request.model_id)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API boundary
        log_safe_exception(
            logger,
            "Desktop local model activation failed",
            exc,
            error_code="local_model_desktop_activation_failed",
        )
        _raise_local_model_error(exc, model_id=request.model_id)


@router.delete("/models", response_model=LocalModelMutationResponse)
def delete_local_model(
    request: LocalModelRequest,
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelMutationResponse:
    """Delete a non-active model through the server-side Ollama transport."""
    try:
        payload = service.delete_model(request.model_id)
        payload["success"] = True
        return LocalModelMutationResponse.model_validate(payload)
    except (LocalModelError, ConfigValidationError, ConfigConflictError) as exc:
        _raise_local_model_error(exc, model_id=request.model_id)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API boundary
        log_safe_exception(logger, "Local model deletion failed", exc, error_code="local_model_delete_failed")
        _raise_local_model_error(exc, model_id=request.model_id)


@router.delete("/registrations", response_model=LocalModelUnregistrationResponse)
def unregister_local_model(
    request: LocalModelDesktopUnregistrationRequest,
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelUnregistrationResponse:
    """Validate and remove configuration before desktop deletes local weights."""
    try:
        payload = service.unregister_model(
            request.model_id,
            expected_config_version=request.expected_config_version,
            expected_runtime_identity=request.expected_runtime_identity,
        )
        payload["success"] = True
        payload["deleted"] = False
        return LocalModelUnregistrationResponse.model_validate(payload)
    except (LocalModelError, ConfigValidationError, ConfigConflictError) as exc:
        _raise_local_model_error(exc, model_id=request.model_id)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API boundary
        log_safe_exception(logger, "Local model unregister failed", exc, error_code="local_model_unregister_failed")
        _raise_local_model_error(exc, model_id=request.model_id)


@router.post("/registration-recoveries/finalize", response_model=LocalModelMutationResponse)
def finalize_local_model_unregistration(
    request: LocalModelRegistrationRestoreRequest,
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelMutationResponse:
    """Revoke Desktop rollback after the corresponding weights were deleted."""
    try:
        payload = service.finalize_unregistration(
            request.model_id,
            recovery_token=request.recovery_token,
        )
        return LocalModelMutationResponse.model_validate(payload)
    except (LocalModelError, ConfigValidationError, ConfigConflictError) as exc:
        _raise_local_model_error(exc, model_id=request.model_id)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API boundary
        log_safe_exception(
            logger,
            "Local model unregistration finalization failed",
            exc,
            error_code="local_model_unregistration_finalize_failed",
        )
        _raise_local_model_error(exc, model_id=request.model_id)


@router.post("/registrations", response_model=LocalModelMutationResponse)
def restore_local_model_registration(
    request: LocalModelRegistrationRestoreRequest,
    service: LocalModelService = Depends(get_local_model_service),
) -> LocalModelMutationResponse:
    """Consume an exact Desktop rollback without probing the stopped runtime."""
    try:
        payload = service.restore_registration(
            request.model_id,
            recovery_token=request.recovery_token,
        )
        payload["success"] = True
        return LocalModelMutationResponse.model_validate(payload)
    except (LocalModelError, ConfigValidationError, ConfigConflictError) as exc:
        _raise_local_model_error(exc, model_id=request.model_id)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized API boundary
        log_safe_exception(
            logger,
            "Local model registration restore failed",
            exc,
            error_code="local_model_registration_restore_failed",
        )
        _raise_local_model_error(exc, model_id=request.model_id)
