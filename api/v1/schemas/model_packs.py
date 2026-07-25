"""Model Pack import API contracts."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from api.v1.schemas.local_models import LOCAL_MODEL_ID_PATTERN
from src.model_pack import MAX_DESKTOP_MODEL_PACK_ATTESTATION_BYTES
from src.model_pack.manifest import LICENSE_ID_PATTERN
from src.task_execution import TaskStatusEnum


class ModelPackImportAccepted(BaseModel):
    """Accepted background Model Pack task."""

    status: str = "accepted"
    task_id: str
    message: str
    message_code: str = "local_model.import.queued"


class ModelPackImportResult(BaseModel):
    """Completed Model Pack import result."""

    model_id: str
    display_name: str
    minimum_memory_gb: int
    license_id: str
    warnings: List[str] = Field(default_factory=list)
    activated: bool
    selected_primary: bool = False


class ModelPackDesktopActivationRequest(BaseModel):
    """Manifest fields returned by the isolated Desktop validator."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(..., min_length=1, max_length=96, pattern=LOCAL_MODEL_ID_PATTERN)
    display_name: str = Field(..., min_length=1, max_length=160)
    minimum_memory_gb: int = Field(..., ge=1, le=2048)
    license_id: str = Field(
        ..., min_length=1, max_length=128, pattern=LICENSE_ID_PATTERN.pattern
    )
    expected_config_version: str = Field(..., min_length=1, max_length=128)
    expected_runtime_identity: str = Field(
        ..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    desktop_attestation: str = Field(
        ..., min_length=1, max_length=MAX_DESKTOP_MODEL_PACK_ATTESTATION_BYTES
    )

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        """Normalize visible Desktop metadata before attestation binding."""
        normalized = value.strip()
        if not normalized or any(ord(character) < 32 for character in normalized):
            raise ValueError("display_name must be visible text")
        return normalized


class ModelPackImportStatus(BaseModel):
    """Canonical task status and optional completed import result."""

    task_id: str
    status: TaskStatusEnum
    progress: int = Field(ge=0, le=100)
    error: Optional[str] = None
    message: Optional[str] = None
    result: Optional[ModelPackImportResult] = None


__all__ = [
    "ModelPackImportAccepted",
    "ModelPackDesktopActivationRequest",
    "ModelPackImportResult",
    "ModelPackImportStatus",
]
