# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin lifecycle control API schemas (list + toggle/reload)."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


PluginLifecycleAction = Literal["enable", "disable", "reload"]
PluginLifecycleState = Literal["registered", "enabled", "disabled", "failed"]
PluginSource = Literal["builtin", "external"]


class PluginInfo(BaseModel):
    """One registered plugin and its lifecycle state."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable plugin id from the manifest")
    name: str
    version: str
    source: PluginSource
    state: PluginLifecycleState
    desired_enabled: bool = Field(
        ...,
        description="Persisted operator intent (False means disabled across restarts)",
    )
    reloadable: bool = Field(
        ...,
        description="True when in-process hot-reload is attempted for this plugin",
    )
    package_root: Optional[str] = Field(
        None,
        description="Absolute package directory for external plugins when known",
    )
    extension_points: List[str] = Field(default_factory=list)
    description: str = ""
    author: str = ""


class PluginListResponse(BaseModel):
    """GET /api/v1/plugins response."""

    model_config = ConfigDict(extra="forbid")

    items: List[PluginInfo] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class PluginLifecycleRequest(BaseModel):
    """POST /api/v1/plugins/{plugin_id}/lifecycle body."""

    model_config = ConfigDict(extra="forbid")

    action: PluginLifecycleAction = Field(
        ...,
        description="enable/disable toggles runtime state and persistence; reload re-imports code",
    )


class PluginLifecycleResponse(BaseModel):
    """Result of one lifecycle action."""

    model_config = ConfigDict(extra="forbid")

    plugin_id: str
    action: PluginLifecycleAction
    success: bool
    state: PluginLifecycleState
    reloaded: bool = False
    restart_required: bool = False
    error_code: Optional[str] = None
    message: Optional[str] = None
    plugin: Optional[PluginInfo] = None
