# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin lifecycle control API schemas (list + toggle/reload)."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


PluginLifecycleAction = Literal["enable", "disable", "reload"]
PluginLifecycleState = Literal["registered", "enabled", "disabled", "failed"]
PluginSource = Literal["builtin", "external"]
PluginSettingValue = Union[str, int, float, bool, None]


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
    notification_channels: List[str] = Field(
        default_factory=list,
        description=(
            "Canonical notification channel IDs from active notification_channel "
            "registrations; empty when the adapter is not loaded or not active"
        ),
    )
    description: str = ""
    author: str = ""
    last_error_code: Optional[str] = Field(
        None,
        description="Stable last lifecycle failure code when the plugin is degraded",
    )
    settings_count: int = Field(
        0,
        ge=0,
        description="Number of declarative settings fields in the plugin manifest",
    )


class PluginListResponse(BaseModel):
    """GET /api/v1/plugins response."""

    model_config = ConfigDict(extra="forbid")

    items: List[PluginInfo] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class PluginHealthEntryResponse(BaseModel):
    """One plugin health row for operator diagnostics consumers."""

    model_config = ConfigDict(extra="forbid")

    plugin_id: str
    name: str
    version: str
    source: PluginSource
    state: PluginLifecycleState
    desired_enabled: bool
    extension_points: List[str] = Field(default_factory=list)
    last_error_code: Optional[str] = None
    package_root: Optional[str] = None
    reloadable: bool = False


class PluginHealthResponse(BaseModel):
    """GET /api/v1/plugins/health — read-only plugin health snapshot."""

    model_config = ConfigDict(extra="forbid")

    generated_at: str = Field(
        ...,
        description="UTC ISO-8601 timestamp when the snapshot was built",
    )
    total: int = Field(..., ge=0)
    plugins: List[PluginHealthEntryResponse] = Field(default_factory=list)


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


class PluginSettingOptionResponse(BaseModel):
    """One finite option for a generated plugin setting control."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    label: str
    value: PluginSettingValue


class PluginSettingFieldResponse(BaseModel):
    """One strict manifest-declared plugin settings field."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    key: str
    title: str
    description: str = ""
    data_type: Literal["string", "integer", "number", "boolean"]
    ui_control: Literal["text", "password", "number", "select", "textarea", "switch"]
    is_sensitive: bool = False
    is_required: bool = False
    default_value: PluginSettingValue = None
    options: List[PluginSettingOptionResponse] = Field(default_factory=list)
    validation: Dict[str, object] = Field(default_factory=dict)
    display_order: int = Field(100, ge=0)


class PluginSettingsResponse(BaseModel):
    """Generated schema and masked effective values for one plugin."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    plugin_id: str
    schema_: List[PluginSettingFieldResponse] = Field(default_factory=list, alias="schema")
    values: Dict[str, PluginSettingValue] = Field(default_factory=dict)
    masked_keys: List[str] = Field(default_factory=list)
    mask_token: str = "******"


class PluginSettingsUpdateRequest(BaseModel):
    """Full replacement of explicit values; omitted keys reset to defaults."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    values: Dict[str, PluginSettingValue] = Field(default_factory=dict)
    mask_token: str = "******"


class PluginSettingsUpdateResponse(PluginSettingsResponse):
    """Persisted settings projection plus apply semantics."""

    changed_keys: List[str] = Field(default_factory=list)
    restart_required: bool = False
