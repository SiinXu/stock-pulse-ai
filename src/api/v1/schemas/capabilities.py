# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Typed schemas for the read-only capability inventory API."""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

CapabilityDomain = Literal["data", "tool", "extension", "skill", "pipeline"]
SourceState = Literal["ok", "error", "generation_drift", "not_initialized"]
BoundedToken = Annotated[str, Field(min_length=1, max_length=128)]


class CapabilitySourceStatus(BaseModel):
    """Freshness and consistency state for one authoritative owner."""

    model_config = ConfigDict(extra="forbid")

    source: CapabilityDomain
    state: SourceState
    generation: str = Field(min_length=1, max_length=256)
    as_of: str = Field(min_length=1, max_length=64)
    error_code: Optional[str] = Field(default=None, max_length=128)


class CapabilityItemBase(BaseModel):
    """Fields common to all owner-observed capability records."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Stable domain-prefixed id",
    )
    owner: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    source_generation: str = Field(min_length=1, max_length=256)
    as_of: str = Field(min_length=1, max_length=64)
    registered: bool
    configured: Optional[bool] = None
    dependency_ready: Optional[bool] = None
    grantable: Optional[bool] = None
    executable: Optional[bool] = None
    healthy: Optional[bool] = None
    degraded: Optional[bool] = None
    dependencies: List[BoundedToken] = Field(default_factory=list, max_length=256)
    scopes: List[BoundedToken] = Field(default_factory=list, max_length=256)
    markets: List[BoundedToken] = Field(default_factory=list, max_length=256)
    providers: List[BoundedToken] = Field(
        default_factory=list,
        max_length=256,
        description=(
            "Every owner identity supplying this capability. Populated for "
            "data-domain records; the scalar provider field never joins ids."
        ),
    )
    provider_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="True supplier count, which may exceed the listed providers.",
    )
    reason_code: Optional[str] = Field(default=None, max_length=128)
    display_name: str = Field(default="", max_length=200)


class DataCapabilityItem(CapabilityItemBase):
    """Active data-provider or supplied-method observation."""

    domain: Literal["data"]
    type: Literal["data_provider", "data_method"]


class ToolCapabilityItem(CapabilityItemBase):
    """Registered or owner-declared Agent tool observation."""

    domain: Literal["tool"]
    type: Literal["agent_tool"]


class ExtensionCapabilityItem(CapabilityItemBase):
    """Plugin lifecycle or active contribution observation."""

    domain: Literal["extension"]
    type: Literal["plugin_lifecycle", "extension_registration"]


class SkillCapabilityItem(CapabilityItemBase):
    """Live analysis-skill observation from plugin or declarative owners."""

    domain: Literal["skill"]
    type: Literal["analysis_skill"]


class PipelineCapabilityItem(CapabilityItemBase):
    """Live pipeline-stage observation from the shared execution contract."""

    domain: Literal["pipeline"]
    type: Literal["pipeline_stage"]


CapabilityItem = Annotated[
    Union[
        DataCapabilityItem,
        ToolCapabilityItem,
        ExtensionCapabilityItem,
        SkillCapabilityItem,
        PipelineCapabilityItem,
    ],
    Field(discriminator="domain"),
]


class CapabilityListResponse(BaseModel):
    """Versioned GET /api/v1/capabilities inventory snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["capability-inventory/v1"]
    partial: bool
    sources: List[CapabilitySourceStatus] = Field(default_factory=list, max_length=5)
    items: List[CapabilityItem] = Field(default_factory=list, max_length=4096)
    total: int = Field(..., ge=0)
    executable_count: int = Field(..., ge=0)
    non_executable_count: int = Field(..., ge=0)
    unknown_executable_count: int = Field(..., ge=0)


# ---------------------------------------------------------------------------
# Write-side registry, resolution, and task-aware routing
# ---------------------------------------------------------------------------

WriteCapabilityDomain = Literal[
    "data", "tool", "skill", "pipeline", "llm", "persona",
]
WriteCapabilityType = Literal[
    "data_provider",
    "data_method",
    "agent_tool",
    "analysis_skill",
    "pipeline_stage",
    "llm_model",
    "persona_role",
]
WriteCapabilityStatus = Literal["active", "retired"]
TaskClass = Literal[
    "report",
    "agent",
    "vision",
    "market_review",
    "cheap_scan",
    "deep_reasoning",
    "coding",
]
RoutingPolicy = Literal["quality", "cost", "local_first"]
BoundedWriteToken = Annotated[str, Field(min_length=1, max_length=256)]
BoundedTag = Annotated[str, Field(min_length=1, max_length=64)]


class WriteCapabilityEntryRequest(BaseModel):
    """Payload for register and update of write-side capability declarations."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(min_length=1, max_length=256)
    domain: WriteCapabilityDomain
    capability_type: WriteCapabilityType
    version: str = Field(default="1", min_length=1, max_length=64)
    provider: str = Field(default="", max_length=128)
    display_name: str = Field(default="", max_length=200)
    dependencies: List[BoundedWriteToken] = Field(default_factory=list, max_length=64)
    tags: List[BoundedTag] = Field(default_factory=list, max_length=32)
    scopes: List[BoundedToken] = Field(default_factory=list, max_length=32)
    markets: List[BoundedToken] = Field(default_factory=list, max_length=32)
    model_route: str = Field(default="", max_length=256)
    cost_tier: str = Field(default="", max_length=32)
    latency_class: str = Field(default="", max_length=32)


class WriteCapabilityUpdateRequest(BaseModel):
    """Partial update payload; identity fields are rejected by the service."""

    model_config = ConfigDict(extra="forbid")

    version: Optional[str] = Field(default=None, min_length=1, max_length=64)
    provider: Optional[str] = Field(default=None, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=200)
    dependencies: Optional[List[BoundedWriteToken]] = Field(default=None, max_length=64)
    tags: Optional[List[BoundedTag]] = Field(default=None, max_length=32)
    scopes: Optional[List[BoundedToken]] = Field(default=None, max_length=32)
    markets: Optional[List[BoundedToken]] = Field(default=None, max_length=32)
    model_route: Optional[str] = Field(default=None, max_length=256)
    cost_tier: Optional[str] = Field(default=None, max_length=32)
    latency_class: Optional[str] = Field(default=None, max_length=32)


class WriteCapabilityEntryResponse(BaseModel):
    """One declared capability from the write-side registry."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    domain: WriteCapabilityDomain
    capability_type: WriteCapabilityType
    version: str
    status: WriteCapabilityStatus
    provider: str
    display_name: str = ""
    dependencies: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    scopes: List[str] = Field(default_factory=list)
    markets: List[str] = Field(default_factory=list)
    model_route: str = ""
    cost_tier: str = ""
    latency_class: str = ""
    registered_at: str = ""
    updated_at: str = ""
    retired_at: Optional[str] = None
    generation: int = Field(ge=1)


class WriteCapabilityListResponse(BaseModel):
    """Versioned write-side registry listing."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["capability-write-registry/v1"]
    generation: int = Field(ge=0)
    as_of: str
    items: List[WriteCapabilityEntryResponse] = Field(default_factory=list, max_length=1024)
    total: int = Field(ge=0)


class DependencyIssueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dependency: str
    capability_id: str
    reason_code: str
    detail: str = ""


class ResolutionResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    ready: bool
    reason_code: str
    satisfied: List[str] = Field(default_factory=list)
    issues: List[DependencyIssueResponse] = Field(default_factory=list)
    checked_against_generation: int = Field(ge=0)


class ResolveCapabilitiesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_ids: Optional[List[str]] = Field(default=None, max_length=256)
    include_inventory: bool = True


class ResolveCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["capability-resolution/v1"] = "capability-resolution/v1"
    write_generation: int = Field(ge=0)
    results: List[ResolutionResultResponse] = Field(default_factory=list, max_length=1024)
    ready_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)


class RouteCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    model_route: str
    score: int
    tags: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


class TaskRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_class: TaskClass
    policy: Optional[RoutingPolicy] = None


class TaskRouteDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["task-route-decision/v1"]
    task_class: TaskClass
    policy: RoutingPolicy
    selected_model: str = ""
    selected_capability_id: str = ""
    reason_code: str
    explain: List[str] = Field(default_factory=list, max_length=32)
    candidates: List[RouteCandidateResponse] = Field(default_factory=list, max_length=8)
    pin_source: str = ""
    fallback_used: bool = False
    routing_enabled: bool = False
    as_of: str = ""

