# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API contracts for recommended config presets and stockpulse-profile YAML."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConfigProfileChange(BaseModel):
    """One non-secret configuration key change."""

    key: str
    from_value: str = Field(..., description="Previous non-secret value")
    to: str = Field(..., description="Next non-secret value")


class ConfigProfileDetection(BaseModel):
    """Local-first detection signals used for preset ranking."""

    ollama_healthy: bool = False
    model_pack_present: bool = False
    cli_detected: List[str] = Field(default_factory=list)
    cloud_ready: bool = False


class ConfigPresetItem(BaseModel):
    """One official recommended configuration preset."""

    id: str
    display_name: str
    description: str
    tags: List[str] = Field(default_factory=list)
    preference_order: List[str] = Field(default_factory=list)
    config_values: Dict[str, str] = Field(default_factory=dict)
    strategies: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Any] = Field(default_factory=dict)
    requirements: Dict[str, Any] = Field(default_factory=dict)
    recommended: bool = False
    score: int = 0
    meets_requirements: bool = True


class ConfigPresetListResponse(BaseModel):
    """Official presets with recommendation ranking."""

    recommended_preset_id: Optional[str] = None
    detection: ConfigProfileDetection = Field(default_factory=ConfigProfileDetection)
    presets: List[ConfigPresetItem] = Field(default_factory=list)


class ConfigPresetApplyRequest(BaseModel):
    """Apply or preview an official preset against the current config version."""

    config_version: str = Field(..., min_length=1, max_length=128)
    reload_now: bool = True


class ConfigPresetApplyResponse(BaseModel):
    """Result of applying an official preset."""

    preset_id: str
    display_name: str
    applied: bool
    config_version: str
    new_config_version: str
    updated_keys: List[str] = Field(default_factory=list)
    changes: List[ConfigProfileChange] = Field(default_factory=list)
    features: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class ConfigPresetPreviewResponse(BaseModel):
    """Preview of applying an official preset."""

    preset_id: str
    display_name: str
    config_version: str
    features: Dict[str, Any] = Field(default_factory=dict)
    changes: List[ConfigProfileChange] = Field(default_factory=list)
    change_count: int = 0


class ConfigProfileExportResponse(BaseModel):
    """Exported stockpulse-profile YAML (secrets stripped)."""

    content: str
    config_version: str
    filename: str
    keys_exported: List[str] = Field(default_factory=list)
    keys_redacted: int = 0


class ConfigProfileImportRequest(BaseModel):
    """Import or preview a stockpulse-profile YAML document."""

    config_version: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1, max_length=262144)
    reload_now: bool = True


class ConfigProfileImportPreviewResponse(BaseModel):
    """Validated profile import preview with non-secret diff."""

    valid: bool
    config_version: str
    name: str = ""
    display_name: str = ""
    description: str = ""
    features: Dict[str, Any] = Field(default_factory=dict)
    changes: List[ConfigProfileChange] = Field(default_factory=list)
    change_count: int = 0
    issues: List[Dict[str, Any]] = Field(default_factory=list)


class ConfigProfileImportApplyResponse(BaseModel):
    """Result of applying an imported stockpulse-profile YAML."""

    applied: bool
    config_version: str
    new_config_version: str
    updated_keys: List[str] = Field(default_factory=list)
    changes: List[ConfigProfileChange] = Field(default_factory=list)
    name: str = ""
    features: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


__all__ = [
    "ConfigPresetApplyRequest",
    "ConfigPresetApplyResponse",
    "ConfigPresetItem",
    "ConfigPresetListResponse",
    "ConfigPresetPreviewResponse",
    "ConfigProfileChange",
    "ConfigProfileDetection",
    "ConfigProfileExportResponse",
    "ConfigProfileImportApplyResponse",
    "ConfigProfileImportPreviewResponse",
    "ConfigProfileImportRequest",
]
