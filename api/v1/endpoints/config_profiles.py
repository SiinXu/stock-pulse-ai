# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Recommended config presets and stockpulse-profile YAML endpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from api.deps import get_config_profile_service
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.config_profiles import (
    ConfigPresetApplyRequest,
    ConfigPresetApplyResponse,
    ConfigPresetListResponse,
    ConfigPresetPreviewResponse,
    ConfigProfileExportResponse,
    ConfigProfileImportApplyResponse,
    ConfigProfileImportPreviewResponse,
    ConfigProfileImportRequest,
)
from src.services.config_profile_service import (
    ConfigProfileError,
    ConfigProfileNotFoundError,
    ConfigProfileService,
    ConfigProfileValidationError,
)
from src.services.system_config_service import ConfigConflictError
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()


def _normalize_changes(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map service diffs onto response models (from → from_value)."""
    normalized: List[Dict[str, Any]] = []
    for item in changes or []:
        normalized.append(
            {
                "key": item.get("key", ""),
                "from_value": item.get("from", item.get("from_value", "")),
                "to": item.get("to", ""),
            }
        )
    return normalized


def _service_error(exc: ConfigProfileError):
    if isinstance(exc, ConfigProfileNotFoundError):
        return api_error(404, exc.error_code, str(exc))
    if isinstance(exc, ConfigProfileValidationError):
        return api_error(
            400,
            exc.error_code,
            str(exc),
            details={"issues": list(getattr(exc, "issues", []) or [])},
        )
    return api_error(400, exc.error_code, str(exc))


@router.get(
    "/presets",
    response_model=ConfigPresetListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List recommended configuration presets",
    description=(
        "Return official named presets with local-first recommendation ranking. "
        "Detection prefers healthy Ollama / Model Pack, then CLI backends, then cloud."
    ),
)
def list_config_presets(
    service: ConfigProfileService = Depends(get_config_profile_service),
) -> ConfigPresetListResponse:
    try:
        return ConfigPresetListResponse.model_validate(service.list_presets())
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary returns stable envelope
        log_safe_exception(
            logger,
            "List config presets failed",
            exc,
            error_code="config_profile_list_failed",
        )
        raise api_error(500, "internal_error", "Failed to list configuration presets")


@router.post(
    "/presets/{preset_id}/preview",
    response_model=ConfigPresetPreviewResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Preview applying a configuration preset",
)
def preview_config_preset(
    preset_id: str,
    request: ConfigPresetApplyRequest,
    service: ConfigProfileService = Depends(get_config_profile_service),
) -> ConfigPresetPreviewResponse:
    try:
        payload = service.preview_preset_apply(
            preset_id,
            config_version=request.config_version,
        )
        payload["changes"] = _normalize_changes(payload.get("changes") or [])
        return ConfigPresetPreviewResponse.model_validate(payload)
    except ConfigProfileError as exc:
        raise _service_error(exc)
    except ConfigConflictError as exc:
        raise api_error(
            409,
            "config_version_conflict",
            "Configuration has changed, please reload and retry",
            details={"current_config_version": exc.current_version},
        )
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary returns stable envelope
        log_safe_exception(
            logger,
            "Preview config preset failed",
            exc,
            error_code="config_profile_preview_failed",
        )
        raise api_error(500, "internal_error", "Failed to preview configuration preset")


@router.post(
    "/presets/{preset_id}/apply",
    response_model=ConfigPresetApplyResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Apply a configuration preset",
    description=(
        "Apply non-secret keys from an official preset through SystemConfigService. "
        "Never writes secrets. Callers should preview first and confirm."
    ),
)
def apply_config_preset(
    preset_id: str,
    request: ConfigPresetApplyRequest,
    service: ConfigProfileService = Depends(get_config_profile_service),
) -> ConfigPresetApplyResponse:
    try:
        payload = service.apply_preset(
            preset_id,
            config_version=request.config_version,
            reload_now=request.reload_now,
            actor="config_profile_api",
        )
        payload["changes"] = _normalize_changes(payload.get("changes") or [])
        return ConfigPresetApplyResponse.model_validate(payload)
    except ConfigProfileError as exc:
        raise _service_error(exc)
    except ConfigConflictError as exc:
        raise api_error(
            409,
            "config_version_conflict",
            "Configuration has changed, please reload and retry",
            details={"current_config_version": exc.current_version},
        )
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary returns stable envelope
        log_safe_exception(
            logger,
            "Apply config preset failed",
            exc,
            error_code="config_profile_apply_failed",
        )
        raise api_error(500, "internal_error", "Failed to apply configuration preset")


@router.get(
    "/export",
    response_model=ConfigProfileExportResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Export stockpulse-profile YAML",
    description=(
        "Export non-secret configuration as stockpulse-profile v1 YAML. "
        "Secret keys (API keys, tokens, passwords, extra headers) are never included."
    ),
)
def export_config_profile(
    service: ConfigProfileService = Depends(get_config_profile_service),
) -> ConfigProfileExportResponse:
    try:
        return ConfigProfileExportResponse.model_validate(service.export_profile())
    except ConfigProfileError as exc:
        raise _service_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary returns stable envelope
        log_safe_exception(
            logger,
            "Export config profile failed",
            exc,
            error_code="config_profile_export_failed",
        )
        raise api_error(500, "internal_error", "Failed to export configuration profile")


@router.post(
    "/import/preview",
    response_model=ConfigProfileImportPreviewResponse,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Preview stockpulse-profile YAML import",
    description=(
        "Validate profile YAML (schema + no secrets) and return a non-secret diff. "
        "Does not write configuration."
    ),
)
def preview_config_profile_import(
    request: ConfigProfileImportRequest,
    service: ConfigProfileService = Depends(get_config_profile_service),
) -> ConfigProfileImportPreviewResponse:
    try:
        payload = service.preview_import(
            content=request.content,
            config_version=request.config_version,
        )
        payload["changes"] = _normalize_changes(payload.get("changes") or [])
        return ConfigProfileImportPreviewResponse.model_validate(payload)
    except ConfigProfileError as exc:
        raise _service_error(exc)
    except ConfigConflictError as exc:
        raise api_error(
            409,
            "config_version_conflict",
            "Configuration has changed, please reload and retry",
            details={"current_config_version": exc.current_version},
        )
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary returns stable envelope
        log_safe_exception(
            logger,
            "Preview config profile import failed",
            exc,
            error_code="config_profile_import_preview_failed",
        )
        raise api_error(500, "internal_error", "Failed to preview configuration profile import")


@router.post(
    "/import/apply",
    response_model=ConfigProfileImportApplyResponse,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Apply stockpulse-profile YAML import",
    description=(
        "Validate and apply a stockpulse-profile YAML through SystemConfigService. "
        "Secret-bearing profiles are rejected. Prefer /import/preview before apply."
    ),
)
def apply_config_profile_import(
    request: ConfigProfileImportRequest,
    service: ConfigProfileService = Depends(get_config_profile_service),
) -> ConfigProfileImportApplyResponse:
    try:
        payload = service.apply_import(
            content=request.content,
            config_version=request.config_version,
            reload_now=request.reload_now,
            actor="config_profile_api",
        )
        payload["changes"] = _normalize_changes(payload.get("changes") or [])
        return ConfigProfileImportApplyResponse.model_validate(payload)
    except ConfigProfileError as exc:
        raise _service_error(exc)
    except ConfigConflictError as exc:
        raise api_error(
            409,
            "config_version_conflict",
            "Configuration has changed, please reload and retry",
            details={"current_config_version": exc.current_version},
        )
    except Exception as exc:  # broad-exception: fallback_recorded - API boundary returns stable envelope
        log_safe_exception(
            logger,
            "Apply config profile import failed",
            exc,
            error_code="config_profile_import_apply_failed",
        )
        raise api_error(500, "internal_error", "Failed to apply configuration profile import")
