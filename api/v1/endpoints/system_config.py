"""System configuration endpoints."""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.deps import get_runtime_scheduler_service, get_system_config_service
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.system_config import (
    DiscoverLLMChannelModelsRequest,
    DiscoverLLMChannelModelsResponse,
    ExportSystemConfigResponse,
    GenerationBackendStatusPreviewRequest,
    GenerationBackendStatusResponse,
    ImportSystemConfigRequest,
    LocalModelCatalogResponse,
    LLMProviderCatalogResponse,
    RollbackSystemConfigRequest,
    SystemConfigConflictResponse,
    SystemConfigResponse,
    SystemConfigSchemaResponse,
    SetupStatusResponse,
    TestGenerationBackendRequest,
    TestGenerationBackendResponse,
    SystemConfigValidationErrorResponse,
    TestLLMChannelRequest,
    TestLLMChannelResponse,
    TestNotificationChannelRequest,
    TestNotificationChannelResponse,
    UpdateSystemConfigRequest,
    UpdateSystemConfigResponse,
    ValidateSystemConfigRequest,
    ValidateSystemConfigResponse,
)
from src.auth import COOKIE_NAME, is_auth_enabled, refresh_auth_state, verify_session
from src.llm.local_model_catalog import LocalModelCatalogError, get_local_model_catalog
from src.services.system_config_service import (
    ConfigConflictError,
    ConfigImportError,
    ConfigRollbackError,
    ConfigValidationError,
    SystemConfigService,
)
from src.services.runtime_scheduler import RuntimeSchedulerService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _config_audit_actor() -> str:
    """Return the attributable operator class available in the single-admin model."""
    if os.getenv("DSA_DESKTOP_MODE") == "true":
        return "desktop_operator"
    if is_auth_enabled():
        return "authenticated_admin"
    return "local_operator"


def _log_config_exception(
    event: str,
    exc: BaseException,
    *,
    error_code: str = "internal_error",
    level: int = logging.ERROR,
    context: Mapping[str, Any] | None = None,
) -> None:
    """Route configuration endpoint failures through the shared sanitizer."""
    log_safe_exception(
        logger,
        event,
        exc,
        error_code=error_code,
        level=level,
        context=context,
    )


@router.get(
    "/scheduler/status",
    summary="Get runtime scheduler status",
    description="Return status for the in-process Web/API/Desktop scheduler.",
)
def get_scheduler_status(
    scheduler: RuntimeSchedulerService = Depends(get_runtime_scheduler_service),
) -> dict:
    """Return runtime scheduler status."""
    return scheduler.status()


@router.post(
    "/scheduler/run-now",
    summary="Run scheduled analysis now",
    description="Trigger one scheduled analysis run in the current process.",
)
def run_scheduler_now(
    scheduler: RuntimeSchedulerService = Depends(get_runtime_scheduler_service),
) -> dict:
    """Trigger one runtime scheduled analysis run."""
    result = scheduler.run_now()
    if not result.get("accepted", False):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "scheduler_busy",
                "message": "A scheduled analysis is already running",
                "reason": result.get("reason", "analysis_already_running"),
            },
        )
    return result


class EnvBackupAccessDenied(Exception):
    """Raised when raw `.env` backup access is not allowed for this request."""

    def __init__(self, *, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _allow_env_backup_access(request: Request) -> None:
    """Gate raw .env backup/restore to explicit secure modes.

    - Desktop runtime keeps existing local behavior via DSA_DESKTOP_MODE.
    - Non-desktop runtime must have admin auth enabled and a valid session.
    """
    if os.getenv("DSA_DESKTOP_MODE") == "true":
        return

    refresh_auth_state()
    if not is_auth_enabled():
        raise EnvBackupAccessDenied(
            status_code=403,
            message="System config backup is disabled; enable admin authentication first",
        )

    cookie_val = request.cookies.get(COOKIE_NAME)
    if cookie_val and verify_session(cookie_val):
        return

    raise EnvBackupAccessDenied(
        status_code=401,
        message="System config backup requires a valid admin session",
    )


def _raise_env_backup_access_error(exc: EnvBackupAccessDenied) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "error": "env_backup_access_denied",
            "message": exc.message,
        },
    )


@router.get(
    "/config",
    response_model=SystemConfigResponse,
    responses={
        200: {"description": "Configuration loaded"},
        401: {"description": "Unauthorized", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Get system configuration",
    description=(
        "Read current configuration and return display values. Server-masked "
        "sensitive fields may return the mask token; clients should use "
        "raw_value_exists and is_masked to interpret values. "
        "configured_notification_channels is computed from the current live "
        "Config snapshot with the runtime notification detector."
    ),
)
def get_system_config(
    include_schema: bool = Query(True, description="Whether to include schema metadata"),
    service: SystemConfigService = Depends(get_system_config_service),
) -> SystemConfigResponse:
    """Load and return current system configuration."""
    try:
        payload = service.get_config(include_schema=include_schema)
        return SystemConfigResponse.model_validate(payload)
    except Exception as exc:
        _log_config_exception("System configuration load failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to load system configuration",
            },
        )


@router.get(
    "/config/setup/status",
    response_model=SetupStatusResponse,
    responses={
        200: {"description": "Setup status loaded"},
        401: {"description": "Unauthorized", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Get first-run setup status",
    description="Read a side-effect-free setup readiness summary from saved and runtime configuration.",
)
def get_setup_status(
    service: SystemConfigService = Depends(get_system_config_service),
) -> SetupStatusResponse:
    """Return first-run setup status without writing config or reloading runtime state."""
    try:
        payload = service.get_setup_status()
        return SetupStatusResponse.model_validate(payload)
    except Exception as exc:
        _log_config_exception("Setup status load failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to load setup status",
            },
        )


@router.get(
    "/config/generation-backends/status",
    response_model=GenerationBackendStatusResponse,
    responses={
        200: {"description": "Generation backend status loaded"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Get generation backend status",
    description=(
        "Read a side-effect-free generation backend cheap-check status from "
        "saved and runtime configuration. This endpoint does not run a model request."
    ),
)
def get_generation_backend_status(
    service: SystemConfigService = Depends(get_system_config_service),
) -> GenerationBackendStatusResponse:
    """Return saved/runtime generation backend status without writing config."""
    try:
        payload = service.get_generation_backend_status()
        return GenerationBackendStatusResponse.model_validate(payload)
    except Exception as exc:
        _log_config_exception("Generation backend status load failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to load generation backend status",
            },
        )


@router.get(
    "/config/llm/mode-status",
    responses={
        200: {"description": "LLM config mode status loaded"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Get LLM config mode status",
    description=(
        "Report the requested vs effective model configuration source "
        "(auto/channels/yaml/legacy), detected and overridden sources."
    ),
)
def get_llm_config_mode_status(
    service: SystemConfigService = Depends(get_system_config_service),
) -> dict:
    """Return the model config source mode status without writing config."""
    try:
        return service.get_llm_config_mode_status()
    except Exception as exc:
        _log_config_exception("LLM config mode status load failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to load LLM config mode status",
            },
        )


@router.get(
    "/config/llm/available-models",
    responses={
        200: {"description": "Available model routes loaded"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Get the model routes declared by currently-enabled connections",
    description=(
        "Return the canonical model routes (and their display name / connection / "
        "provider grouping) the Web model selectors offer. The route set matches "
        "backend validation, so the UI never has to derive routes itself."
    ),
)
def get_llm_available_models(
    service: SystemConfigService = Depends(get_system_config_service),
) -> dict:
    """Return available model routes for the current saved config."""
    try:
        return service.get_available_models()
    except Exception as exc:
        _log_config_exception("Available model list load failed", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Failed to load available models"},
        )


@router.get(
    "/config/llm/providers",
    response_model=LLMProviderCatalogResponse,
    responses={
        200: {"description": "LLM provider catalog loaded"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Get the authoritative LLM model-service provider catalog",
    description=(
        "Return provider metadata (label, protocol, default endpoint, credential "
        "and base-URL requirements, discovery support, capabilities). This is the "
        "single source of truth the Web model-access page consumes."
    ),
)
def get_llm_provider_catalog() -> dict:
    """Return the authoritative provider catalog without reading user config."""
    try:
        from src.llm.provider_catalog import (
            get_connection_field_schema,
            get_empty_api_key_hosts,
            get_provider_catalog,
        )

        return {
            "providers": get_provider_catalog(),
            "connection_fields": get_connection_field_schema(),
            "empty_api_key_hosts": get_empty_api_key_hosts(),
        }
    except Exception as exc:
        _log_config_exception("LLM provider catalog load failed", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Failed to load LLM provider catalog"},
        )


@router.get(
    "/config/llm/local-models",
    response_model=LocalModelCatalogResponse,
    responses={
        200: {"description": "Local model catalog loaded"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Get the authoritative local model catalog",
    description=(
        "Return the fixed General and Finance local-model selections, verified "
        "artifact facts, hardware guidance, license conclusions, and install status."
    ),
)
def get_llm_local_model_catalog() -> dict:
    """Return the validated local model catalog without reading user config."""
    try:
        return get_local_model_catalog()
    except LocalModelCatalogError as exc:
        _log_config_exception("Local model catalog load failed", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Failed to load local model catalog"},
        )


@router.get(
    "/config/llm/legacy-migration/preview",
    responses={
        200: {"description": "Legacy migration preview loaded"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Preview Legacy -> Channels migration",
    description="Return a redacted preview of the channels that would be created from legacy provider keys.",
)
def preview_legacy_channels_migration(
    service: SystemConfigService = Depends(get_system_config_service),
) -> dict:
    """Return a redacted Legacy -> Channels migration preview."""
    try:
        return service.preview_legacy_channels_migration()
    except Exception as exc:
        _log_config_exception("Legacy channel migration preview failed", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Failed to preview legacy channel migration"},
        )


@router.post(
    "/config/llm/legacy-migration/apply",
    responses={
        200: {"description": "Legacy migration applied"},
        400: {"description": "Validation error", "model": SystemConfigValidationErrorResponse},
        409: {"description": "Config version conflict", "model": SystemConfigConflictResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Apply Legacy -> Channels migration",
    description="Copy detected legacy provider config into channels and set LLM_CONFIG_MODE=channels.",
)
def apply_legacy_channels_migration(
    payload: UpdateSystemConfigRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> dict:
    """Apply the Legacy -> Channels migration atomically."""
    try:
        return service.apply_legacy_channels_migration(
            config_version=payload.config_version,
            validate_connectivity=payload.validate_connectivity,
            connectivity_timeout_seconds=payload.connectivity_timeout_seconds,
            actor=_config_audit_actor(),
        )
    except ConfigValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": "validation_error", "issues": exc.issues})
    except ConfigConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "config_conflict", "current_config_version": exc.current_version},
        )
    except Exception as exc:  # broad-exception: fallback_recorded - map migration failures to a sanitized API error
        log_safe_exception(
            logger,
            "Legacy channel migration apply failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Failed to apply legacy channel migration"},
        )


@router.post(
    "/config/generation-backends/status/preview",
    response_model=GenerationBackendStatusResponse,
    responses={
        200: {"description": "Generation backend status preview loaded"},
        400: {"description": "Validation failed", "model": SystemConfigValidationErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Preview generation backend status",
    description="Run a side-effect-free cheap check against unsaved settings draft values.",
)
def preview_generation_backend_status(
    request: GenerationBackendStatusPreviewRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> GenerationBackendStatusResponse:
    """Return generation backend status for unsaved draft values."""
    try:
        payload = service.preview_generation_backend_status(
            items=[item.model_dump() for item in request.items],
            mask_token=request.mask_token,
        )
        return GenerationBackendStatusResponse.model_validate(payload)
    except ConfigValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_failed",
                "message": "System configuration validation failed",
                "issues": exc.issues,
            },
        )
    except Exception as exc:
        _log_config_exception("Generation backend status preview failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to preview generation backend status",
            },
        )


@router.post(
    "/config/generation-backends/smoke-test",
    response_model=TestGenerationBackendResponse,
    responses={
        200: {"description": "Generation backend smoke test completed"},
        400: {"description": "Validation failed", "model": SystemConfigValidationErrorResponse},
        422: {"description": "Invalid smoke test request", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Smoke test generation backend",
    description="Run an explicit fixed-prompt generation backend smoke test without persisting config.",
)
def test_generation_backend(
    request: TestGenerationBackendRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> TestGenerationBackendResponse:
    """Run a fixed generation backend smoke test."""
    try:
        payload = service.test_generation_backend(
            backend_id=request.backend_id,
            mode=request.mode,
            items=[item.model_dump() for item in request.items],
            mask_token=request.mask_token,
            timeout_seconds=request.timeout_seconds,
        )
        return TestGenerationBackendResponse.model_validate(payload)
    except ConfigValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_failed",
                "message": "System configuration validation failed",
                "issues": exc.issues,
            },
        )
    except Exception as exc:
        _log_config_exception("Generation backend smoke test failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to smoke test generation backend",
            },
        )


@router.put(
    "/config",
    response_model=UpdateSystemConfigResponse,
    responses={
        200: {"description": "Configuration updated"},
        400: {"description": "Validation failed", "model": SystemConfigValidationErrorResponse},
        409: {"description": "Version conflict", "model": SystemConfigConflictResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Update system configuration",
    description="Update key-value pairs in .env. Mask token preserves existing secret values.",
)
def update_system_config(
    request: UpdateSystemConfigRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> UpdateSystemConfigResponse:
    """Validate and persist system configuration updates."""
    try:
        payload = service.update(
            config_version=request.config_version,
            items=[item.model_dump() for item in request.items],
            mask_token=request.mask_token,
            reload_now=request.reload_now,
            validate_connectivity=request.validate_connectivity,
            connectivity_timeout_seconds=request.connectivity_timeout_seconds,
            actor=_config_audit_actor(),
        )
        return UpdateSystemConfigResponse.model_validate(payload)
    except ConfigValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_failed",
                "message": "System configuration validation failed",
                "issues": exc.issues,
            },
        )
    except ConfigConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "config_version_conflict",
                "message": "Configuration has changed, please reload and retry",
                "current_config_version": exc.current_version,
            },
        )
    except Exception as exc:  # broad-exception: fallback_recorded - map update failures to a sanitized API error
        log_safe_exception(
            logger,
            "System configuration update failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to update system configuration",
            },
        )


@router.post(
    "/config/rollback",
    response_model=UpdateSystemConfigResponse,
    responses={
        200: {"description": "Last-known-good configuration restored"},
        400: {"description": "Rollback validation failed", "model": SystemConfigValidationErrorResponse},
        409: {"description": "Rollback unavailable or version conflict", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Roll back system configuration",
    description=(
        "Atomically restore and activate the previous last-known-good runtime "
        "configuration without changing administrator authentication state."
    ),
)
def rollback_system_config(
    request: RollbackSystemConfigRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> UpdateSystemConfigResponse:
    """Restore the previous runtime configuration in one authenticated action."""
    try:
        payload = service.restore_last_good_config(
            config_version=request.config_version,
            actor=_config_audit_actor(),
        )
        return UpdateSystemConfigResponse.model_validate(payload)
    except ConfigValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_failed",
                "message": "System configuration rollback validation failed",
                "issues": exc.issues,
            },
        )
    except ConfigConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "config_version_conflict",
                "message": "Configuration has changed, please reload and retry",
                "current_config_version": exc.current_version,
            },
        )
    except ConfigRollbackError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "rollback_unavailable",
                "message": exc.message,
            },
        )
    except Exception as exc:  # broad-exception: fallback_recorded - map rollback failures to a sanitized API error
        log_safe_exception(
            logger,
            "System configuration rollback failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to roll back system configuration",
            },
        )


@router.get(
    "/config/export",
    response_model=ExportSystemConfigResponse,
    responses={
        200: {"description": "Env exported"},
        401: {"description": "Unauthorized", "model": ErrorResponse},
        403: {"description": "Env backup disabled", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Export env backup",
    description="Return the raw saved .env content for configuration backup.",
)
def export_system_config(
    request: Request,
    service: SystemConfigService = Depends(get_system_config_service),
) -> ExportSystemConfigResponse:
    """Export the active `.env` file for config backup."""
    try:
        _allow_env_backup_access(request)
    except EnvBackupAccessDenied as exc:
        _log_config_exception(
            "System configuration export blocked",
            exc,
            error_code="env_backup_access_denied",
            level=logging.WARNING,
            context={"status_code": exc.status_code},
        )
        _raise_env_backup_access_error(exc)

    try:
        payload = service.export_env()
        return ExportSystemConfigResponse.model_validate(payload)
    except Exception as exc:
        _log_config_exception("System configuration export failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to export system configuration",
            },
        )


@router.post(
    "/config/import",
    response_model=UpdateSystemConfigResponse,
    responses={
        200: {"description": "Env imported"},
        400: {
            "description": "Import failed",
            "content": {
                "application/json": {
                    "schema": {
                        "anyOf": [
                            {"$ref": "#/components/schemas/ErrorResponse"},
                            {"$ref": "#/components/schemas/SystemConfigValidationErrorResponse"},
                        ]
                    }
                }
            },
        },
        401: {"description": "Unauthorized", "model": ErrorResponse},
        403: {"description": "Env backup disabled", "model": ErrorResponse},
        409: {"description": "Version conflict", "model": SystemConfigConflictResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Import env backup",
    description="Merge raw .env text into the saved configuration with config version conflict protection.",
)
def import_system_config(
    request: ImportSystemConfigRequest,
    request_obj: Request,
    service: SystemConfigService = Depends(get_system_config_service),
) -> UpdateSystemConfigResponse:
    """Import a `.env` backup into the active config."""
    try:
        _allow_env_backup_access(request_obj)
    except EnvBackupAccessDenied as exc:
        _log_config_exception(
            "System configuration import blocked",
            exc,
            error_code="env_backup_access_denied",
            level=logging.WARNING,
            context={"status_code": exc.status_code},
        )
        _raise_env_backup_access_error(exc)

    try:
        payload = service.import_env(
            config_version=request.config_version,
            content=request.content,
            reload_now=request.reload_now,
            validate_connectivity=request.validate_connectivity,
            connectivity_timeout_seconds=request.connectivity_timeout_seconds,
            actor=_config_audit_actor(),
        )
        return UpdateSystemConfigResponse.model_validate(payload)
    except ConfigImportError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_import_file",
                "message": exc.message,
            },
        )
    except ConfigValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_failed",
                "message": "System configuration validation failed",
                "issues": exc.issues,
            },
        )
    except ConfigConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "config_version_conflict",
                "message": "Configuration has changed, please reload and retry",
                "current_config_version": exc.current_version,
            },
        )
    except Exception as exc:  # broad-exception: fallback_recorded - map import failures to a sanitized API error
        log_safe_exception(
            logger,
            "System configuration import failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to import system configuration",
            },
        )


@router.post(
    "/config/validate",
    response_model=ValidateSystemConfigResponse,
    responses={
        200: {"description": "Validation completed"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Validate system configuration",
    description="Validate submitted configuration values without writing to .env.",
)
def validate_system_config(
    request: ValidateSystemConfigRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> ValidateSystemConfigResponse:
    """Run pre-save validation only."""
    try:
        payload = service.validate(items=[item.model_dump() for item in request.items])
        return ValidateSystemConfigResponse.model_validate(payload)
    except Exception as exc:
        _log_config_exception("System configuration validation failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to validate system configuration",
            },
        )


@router.post(
    "/config/llm/test-channel",
    response_model=TestLLMChannelResponse,
    responses={
        200: {"description": "Channel test completed"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Test one LLM channel",
    description="Run a minimal LLM request against one unsaved or saved channel definition.",
)
def test_llm_channel(
    request: TestLLMChannelRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> TestLLMChannelResponse:
    """Validate and test one channel definition without writing `.env`."""
    try:
        payload = service.test_llm_channel(
            name=request.name,
            provider_id=request.provider_id,
            protocol=request.protocol,
            base_url=request.base_url,
            api_key=request.api_key,
            models=request.models,
            enabled=request.enabled,
            timeout_seconds=request.timeout_seconds,
            capability_checks=request.capability_checks,
            use_saved_secret=request.use_saved_secret,
        )
        return TestLLMChannelResponse.model_validate(payload)
    except Exception as exc:
        _log_config_exception("LLM channel test failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to test LLM channel",
            },
        )


@router.post(
    "/config/notification/test-channel",
    response_model=TestNotificationChannelResponse,
    responses={
        200: {"description": "Notification channel test completed"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Test one notification channel",
    description="Send a short test notification using unsaved or saved notification configuration.",
)
def test_notification_channel(
    request: TestNotificationChannelRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> TestNotificationChannelResponse:
    """Validate and test one notification channel without writing `.env`."""
    try:
        payload = service.test_notification_channel(
            channel=request.channel,
            items=[item.model_dump() for item in request.items],
            mask_token=request.mask_token,
            title=request.title,
            content=request.content,
            timeout_seconds=request.timeout_seconds,
        )
        return TestNotificationChannelResponse.model_validate(payload)
    except Exception as exc:
        _log_config_exception("Notification channel test failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to test notification channel",
            },
        )


@router.post(
    "/config/llm/discover-models",
    response_model=DiscoverLLMChannelModelsResponse,
    responses={
        200: {"description": "Model discovery completed"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Discover models for one LLM channel",
    description="Call one unsaved or saved channel's `/models` endpoint and return discovered model IDs.",
)
def discover_llm_channel_models(
    request: DiscoverLLMChannelModelsRequest,
    service: SystemConfigService = Depends(get_system_config_service),
) -> DiscoverLLMChannelModelsResponse:
    """Discover models for one channel definition without writing `.env`."""
    try:
        payload = service.discover_llm_channel_models(
            name=request.name,
            provider_id=request.provider_id,
            protocol=request.protocol,
            base_url=request.base_url,
            api_key=request.api_key,
            models=request.models,
            timeout_seconds=request.timeout_seconds,
            use_saved_secret=request.use_saved_secret,
        )
        return DiscoverLLMChannelModelsResponse.model_validate(payload)
    except Exception as exc:
        _log_config_exception("LLM channel model discovery failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to discover LLM channel models",
            },
        )


@router.get(
    "/config/schema",
    response_model=SystemConfigSchemaResponse,
    responses={
        200: {"description": "Schema loaded"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Get system configuration schema",
    description="Return categorized field metadata used for dynamic settings form rendering.",
)
def get_system_config_schema(
    service: SystemConfigService = Depends(get_system_config_service),
) -> SystemConfigSchemaResponse:
    """Return schema metadata for system configuration fields."""
    try:
        payload = service.get_schema()
        return SystemConfigSchemaResponse.model_validate(payload)
    except Exception as exc:
        _log_config_exception("System configuration schema load failed", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Failed to load system configuration schema",
            },
        )
