"""Versioned local Model Pack import endpoints."""

from __future__ import annotations

import errno
import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from api.deps import get_model_pack_import_service
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.model_packs import (
    ModelPackImportAccepted,
    ModelPackImportStatus,
)
from src.services.model_pack_import_service import ModelPackImportService
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)
router = APIRouter()
_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024
_SUPPORTED_ARCHIVE_SUFFIXES = frozenset({".modelpack", ".zip"})


def _remove_staging(staging_root: Path) -> None:
    shutil.rmtree(staging_root, ignore_errors=True)


def _stage_upload(upload: UploadFile) -> tuple[Path, Path]:
    original_suffix = Path(upload.filename or "").suffix.lower()
    if original_suffix not in _SUPPORTED_ARCHIVE_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "unsupported_archive",
                "message": "Select a .modelpack or .zip Model Pack file.",
            },
        )
    staging_root = Path(tempfile.mkdtemp(prefix="stockpulse-model-pack-upload-"))
    staged_path = staging_root / f"upload{original_suffix}"
    total_bytes = 0
    try:
        try:
            with staged_path.open("wb") as output:
                while True:
                    chunk = upload.file.read(_UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    output.write(chunk)
        finally:
            upload.file.close()
    except OSError as exc:
        _remove_staging(staging_root)
        if exc.errno == errno.ENOSPC:
            raise HTTPException(
                status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                detail={
                    "error": "insufficient_disk_space",
                    "message": "Not enough server disk space to stage this Model Pack.",
                },
            ) from exc
        raise
    except Exception:  # broad-exception: cleanup - Remove private staging before the API boundary sanitizes upload failures.
        _remove_staging(staging_root)
        raise
    if total_bytes == 0:
        _remove_staging(staging_root)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "empty_model_pack",
                "message": "The selected Model Pack is empty. Select it again.",
            },
        )
    return staged_path, staging_root


@router.post(
    "/import",
    response_model=ModelPackImportAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Model Pack import accepted"},
        400: {"description": "Invalid upload", "model": ErrorResponse},
        507: {"description": "Insufficient staging disk", "model": ErrorResponse},
    },
    summary="Import a local Model Pack",
    description=(
        "Stage a Model Pack for background validation and import. "
        "The Ollama target is read only from server configuration."
    ),
)
def import_model_pack(
    file: UploadFile = File(..., description="A .modelpack or ZIP archive"),
    service: ModelPackImportService = Depends(get_model_pack_import_service),
) -> ModelPackImportAccepted:
    staging_root = None
    try:
        staged_path, staging_root = _stage_upload(file)
        task = service.start_import(staged_path, cleanup_root=staging_root)
    except HTTPException:
        raise
    except Exception as exc:
        if staging_root is not None:
            _remove_staging(staging_root)
        log_safe_exception(
            logger,
            "Model Pack import submission failed",
            exc,
            error_code="model_pack_import_submission_failed",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "model_pack_import_submission_failed",
                "message": "Could not start the Model Pack import. Try again.",
            },
        ) from exc
    return ModelPackImportAccepted(
        task_id=task.task_id,
        message="Model Pack import queued.",
    )


@router.get(
    "/imports/{task_id}",
    response_model=ModelPackImportStatus,
    responses={
        200: {"description": "Model Pack import status"},
        404: {"description": "Import task not found", "model": ErrorResponse},
    },
    summary="Get Model Pack import status",
)
def get_model_pack_import(
    task_id: str,
    service: ModelPackImportService = Depends(get_model_pack_import_service),
) -> ModelPackImportStatus:
    payload = service.get_import(task_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "model_pack_import_not_found",
                "message": "The Model Pack import task was not found.",
            },
        )
    return ModelPackImportStatus.model_validate(payload)
