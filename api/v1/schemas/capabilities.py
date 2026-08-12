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
# Write-side capability registry (additive; does not alter inventory schemas)
# ---------------------------------------------------------------------------

WriteCapabilityDomain = Literal[
    "data", "tool", "skill", "pipeline", "llm", "persona"
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
TaskClassLiteral = Literal[
    "report",
    "agent",
    "vision",
    "market_review",
    "cheap_scan",
    "deep_reasoning",
    "coding",
]
RoutingPolicyLiteral = Literal["quality", "cost", "local_first"]


class WriteCapabilityEntryResponse(BaseModel):
    """One operator-declared capability entry."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(min_length=1, max_length=256)
    domain: WriteCapabilityDomain
    capability_type: WriteCapabilityType
    version: str = Field(min_length=1, max_length=64)
    status: WriteCapabilityStatus
    provider: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=200)
    dependencies: List[BoundedToken] = Field(default_factory=list, max_length=64)
    tags: List[str] = Field(default_factory=list, max_length=32)
    scopes: List[BoundedToken] = Field(default_factory=list, max_length=32)
    markets: List[BoundedToken] = Field(default_factory=list, max_length=32)
    model_route: str = Field(default="", max_length=256)
    cost_tier: str = Field(default="", max_length=32)
    latency_class: str = Field(default="", max_length=32)
    registered_at: str = Field(default="", max_length=64)
    updated_at: str = Field(default="", max_length=64)
    retired_at: Optional[str] = Field(default=None, max_length=64)
    generation: int = Field(..., ge=1)


class WriteCapabilityRegisterRequest(BaseModel):
    """Create a new write-side capability declaration."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(min_length=1, max_length=256)
    domain: WriteCapabilityDomain
    capability_type: WriteCapabilityType
    version: str = Field(default="1", min_length=1, max_length=64)
    provider: str = Field(default="", max_length=128)
    display_name: str = Field(default="", max_length=200)
    dependencies: List[str] = Field(default_factory=list, max_length=64)
    tags: List[str] = Field(default_factory=list, max_length=32)
    scopes: List[str] = Field(default_factory=list, max_length=32)
    markets: List[str] = Field(default_factory=list, max_length=32)
    model_route: str = Field(default="", max_length=256)
    cost_tier: str = Field(default="", max_length=32)
    latency_class: str = Field(default="", max_length=32)


class WriteCapabilityUpdateRequest(BaseModel):
    """Partial update for a non-retired capability declaration."""

    model_config = ConfigDict(extra="forbid")

    version: Optional[str] = Field(default=None, min_length=1, max_length=64)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=200)
    dependencies: Optional[List[str]] = Field(default=None, max_length=64)
    tags: Optional[List[str]] = Field(default=None, max_length=32)
    scopes: Optional[List[str]] = Field(default=None, max_length=32)
    markets: Optional[List[str]] = Field(default=None, max_length=32)
    model_route: Optional[str] = Field(default=None, max_length=256)
    cost_tier: Optional[str] = Field(default=None, max_length=32)
    latency_class: Optional[str] = Field(default=None, max_length=32)


class WriteCapabilityListResponse(BaseModel):
    """Versioned write-side registry list."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["capability-write-registry/v1"]
    generation: int = Field(..., ge=0)
    as_of: str = Field(min_length=1, max_length=64)
    entries: List[WriteCapabilityEntryResponse] = Field(
        default_factory=list, max_length=1024
    )
    total: int = Field(..., ge=0)


class DependencyIssueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dependency: str = Field(min_length=1, max_length=256)
    capability_id: str = Field(min_length=1, max_length=256)
    reason_code: str = Field(min_length=1, max_length=128)
    detail: str = Field(default="", max_length=256)


class ResolutionResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(min_length=1, max_length=256)
    ready: bool
    reason_code: str = Field(min_length=1, max_length=128)
    satisfied: List[str] = Field(default_factory=list, max_length=64)
    issues: List[DependencyIssueResponse] = Field(default_factory=list, max_length=64)
    checked_against_generation: int = Field(..., ge=0)


class CapabilityResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_ids: Optional[List[str]] = Field(default=None, max_length=256)
    include_inventory: bool = True
    active_only: bool = True


class CapabilityResolveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: List[ResolutionResultResponse] = Field(default_factory=list, max_length=1024)
    total: int = Field(..., ge=0)
    write_generation: int = Field(..., ge=0)


class RouteCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(min_length=1, max_length=256)
    model_route: str = Field(min_length=1, max_length=256)
    score: int
    tags: List[str] = Field(default_factory=list, max_length=32)
    reasons: List[str] = Field(default_factory=list, max_length=32)


class TaskRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_class: TaskClassLiteral
    policy: Optional[RoutingPolicyLiteral] = None


class TaskRouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["task-route-decision/v1"]
    task_class: TaskClassLiteral
    policy: RoutingPolicyLiteral
    selected_model: str = Field(default="", max_length=256)
    selected_capability_id: str = Field(default="", max_length=256)
    reason_code: str = Field(min_length=1, max_length=128)
    explain: List[str] = Field(default_factory=list, max_length=32)
    candidates: List[RouteCandidateResponse] = Field(default_factory=list, max_length=8)
    pin_source: str = Field(default="", max_length=128)
    fallback_used: bool = False
    routing_enabled: bool = False
    as_of: str = Field(default="", max_length=64)
