"""Model Pack import API contracts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from src.task_execution import TaskStatusEnum


class ModelPackImportAccepted(BaseModel):
    status: str = "accepted"
    task_id: str
    message: str
    message_code: str = "local_model.import.queued"


class ModelPackImportResult(BaseModel):
    model_id: str
    display_name: str
    minimum_memory_gb: int
    license_id: str
    warnings: List[str] = Field(default_factory=list)
    registration: Optional[Dict[str, Any]] = None


class ModelPackImportStatus(BaseModel):
    task_id: str
    status: TaskStatusEnum
    progress: int = Field(ge=0, le=100)
    error: Optional[str] = None
    message: Optional[str] = None
    result: Optional[ModelPackImportResult] = None


__all__ = [
    "ModelPackImportAccepted",
    "ModelPackImportResult",
    "ModelPackImportStatus",
]
