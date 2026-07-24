"""Local model lifecycle API schemas."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.task_execution import TaskStatusEnum


LOCAL_MODEL_ID_PATTERN = (
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*"
    r"(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$"
)


class LocalModelRequest(BaseModel):
    """One catalog-backed model operation without caller-controlled endpoints."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(..., min_length=1, max_length=128, pattern=LOCAL_MODEL_ID_PATTERN)


class LocalModelAssignmentRequest(LocalModelRequest):
    """Register or explicitly assign one installed local model."""

    assignment: Literal["auto", "primary", "agent"] = "auto"


class LocalModelDesktopActivationRequest(LocalModelRequest):
    """Activate a Desktop pull only against its original configuration snapshot."""

    expected_config_version: str = Field(..., min_length=1, max_length=128)
    expected_runtime_identity: str = Field(
        ..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )


class LocalModelDesktopUnregistrationRequest(LocalModelRequest):
    """Unregister before Desktop deletion using one immutable runtime snapshot."""

    expected_config_version: str = Field(..., min_length=1, max_length=128)
    expected_runtime_identity: str = Field(
        ..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )


class LocalModelRegistrationRestoreRequest(LocalModelRequest):
    """Consume a short-lived rollback capability issued by unregister."""

    recovery_token: str = Field(..., min_length=1, max_length=128)


class LocalModelConfigurationResponse(BaseModel):
    """Caller-safe local model configuration state."""

    config_version: str
    registered_models: List[str] = Field(default_factory=list)
    primary_model: str = ""
    agent_model: str = ""


class LocalModelRuntimeResponse(BaseModel):
    """Runtime availability plus saved assignment state."""

    runtime: Literal["ollama"] = "ollama"
    status: Literal["running", "unavailable"]
    installed_models: List[str] = Field(default_factory=list)
    manual_pull_supported: bool = False
    configuration: LocalModelConfigurationResponse


class LocalModelPullAccepted(BaseModel):
    """Accepted local model pull task."""

    task_id: str
    trace_id: str
    status: TaskStatusEnum
    model_id: str


class LocalModelPullResult(BaseModel):
    """Completed download with its separate activation outcome."""

    model_id: str
    activated: bool
    selected_primary: bool = False


class LocalModelPullStatus(BaseModel):
    """Polling response for one local model pull task."""

    task_id: str
    status: TaskStatusEnum
    progress: int = Field(0, ge=0, le=100)
    model_id: str
    error: Optional[str] = None
    result: Optional[LocalModelPullResult] = None


class LocalModelMutationResponse(LocalModelConfigurationResponse):
    """Configuration or deletion mutation response."""

    success: bool = True
    model_id: str
    selected_primary: bool = False
    selected_agent: bool = False
    deleted: bool = False
    updated_keys: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    applied_count: int = 0
    skipped_masked_count: int = 0
    reload_triggered: bool = False


class LocalModelUnregistrationResponse(LocalModelMutationResponse):
    """Unregister result with the required one-time Desktop deletion reservation."""

    recovery_token: str
