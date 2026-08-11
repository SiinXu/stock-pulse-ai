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
