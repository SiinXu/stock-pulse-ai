# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Typed immutable contracts for owner-driven capability inventory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Literal, Optional, Tuple

CAPABILITY_SCHEMA_VERSION = "capability-inventory/v1"
CapabilityDomain = Literal["data", "tool", "extension"]
CapabilityType = Literal[
    "data_provider", "data_method", "agent_tool",
    "plugin_lifecycle", "extension_registration",
]
SourceState = Literal["ok", "error", "generation_drift"]


@dataclass(frozen=True, slots=True)
class SourceStatus:
    source: Literal["data", "tool", "extension"]
    state: SourceState
    generation: str
    as_of: str
    error_code: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source not in {"data", "tool", "extension"}:
            raise ValueError("source is invalid")
        if self.state not in {"ok", "error", "generation_drift"}:
            raise ValueError("source state is invalid")
        if not self.generation or len(self.generation) > 256:
            raise ValueError("source generation must be bounded")
        if not self.as_of or len(self.as_of) > 64:
            raise ValueError("source timestamp must be bounded")
        if self.error_code is not None and (
            not self.error_code or len(self.error_code) > 128
        ):
            raise ValueError("source error code must be bounded")
        if self.state == "ok" and self.error_code is not None:
            raise ValueError("successful source must not carry an error code")
        if self.state != "ok" and self.error_code is None:
            raise ValueError("failed source requires an error code")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    capability_id: str
    domain: CapabilityDomain
    capability_type: CapabilityType
    owner: str
    provider: str
    version: str
    source_generation: str
    as_of: str
    registered: bool
    configured: Optional[bool] = None
    dependency_ready: Optional[bool] = None
    grantable: Optional[bool] = None
    executable: Optional[bool] = None
    healthy: Optional[bool] = None
    degraded: Optional[bool] = None
    dependencies: Tuple[str, ...] = ()
    scopes: Tuple[str, ...] = ()
    markets: Tuple[str, ...] = ()
    reason_code: Optional[str] = None
    display_name: str = ""

    def __post_init__(self) -> None:
        allowed_types = {
            "data": {"data_provider", "data_method"},
            "tool": {"agent_tool"},
            "extension": {"plugin_lifecycle", "extension_registration"},
        }
        if (
            self.domain not in allowed_types
            or self.capability_type not in allowed_types[self.domain]
        ):
            raise ValueError("capability type does not match its domain")
        for name, value, maximum in (
            ("capability_id", self.capability_id, 256),
            ("owner", self.owner, 128),
            ("provider", self.provider, 128),
            ("version", self.version, 64),
            ("source_generation", self.source_generation, 256),
            ("as_of", self.as_of, 64),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"{name} must be a bounded non-empty string")
        if len(self.display_name) > 200:
            raise ValueError("display_name must be bounded")
        if self.reason_code is not None and (
            not self.reason_code or len(self.reason_code) > 128
        ):
            raise ValueError("reason_code must be bounded")
        if self.executable is False and not self.reason_code:
            raise ValueError("known non-executable records require reason_code")
        for values in (self.dependencies, self.scopes, self.markets):
            if len(values) > 64 or any(
                not isinstance(item, str) or not item or len(item) > 128
                for item in values
            ):
                raise ValueError("metadata lists must be bounded strings")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    schema_version: str = CAPABILITY_SCHEMA_VERSION
    sources: Tuple[SourceStatus, ...] = ()
    items: Tuple[CapabilityRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != CAPABILITY_SCHEMA_VERSION:
            raise ValueError("unsupported capability snapshot schema version")
        if (
            len(self.sources) > 3
            or len({source.source for source in self.sources}) != len(self.sources)
        ):
            raise ValueError("capability sources must be unique and bounded")
        if len(self.items) > 4096:
            raise ValueError("capability snapshot is too large")

    @property
    def partial(self) -> bool:
        return any(source.state != "ok" for source in self.sources)
