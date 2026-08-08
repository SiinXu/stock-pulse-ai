# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Immutable records for the read-only capability aggregation view."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping

CapabilityDomain = Literal["data", "tool", "extension"]

REASON_FEATURE_DISABLED = "feature_disabled"
REASON_MISSING_CONFIG = "missing_config"
REASON_MISSING_DEPENDENCY = "missing_dependency"
REASON_PLUGIN_DISABLED = "plugin_disabled"
REASON_PLUGIN_FAILED = "plugin_failed"
REASON_NOT_REGISTERED = "not_registered"

KNOWN_UNAVAILABLE_REASON_CODES = frozenset(
    {
        REASON_FEATURE_DISABLED,
        REASON_MISSING_CONFIG,
        REASON_MISSING_DEPENDENCY,
        REASON_PLUGIN_DISABLED,
        REASON_PLUGIN_FAILED,
        REASON_NOT_REGISTERED,
    }
)


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    """One aggregated capability observation from an existing registry."""

    capability_id: str
    domain: CapabilityDomain
    provider: str
    available: bool
    reason_code: str | None = None
    reason_message: str | None = None
    display_name: str = ""
    details: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if self.domain not in {"data", "tool", "extension"}:
            raise ValueError(f"unsupported capability domain: {self.domain!r}")
        if type(self.capability_id) is not str or not self.capability_id.strip():
            raise ValueError("capability_id must be a non-empty string")
        if type(self.provider) is not str or not self.provider.strip():
            raise ValueError("provider must be a non-empty string")
        if self.available:
            if self.reason_code is not None or self.reason_message is not None:
                raise ValueError("available records must not carry an unavailable reason")
        else:
            if type(self.reason_code) is not str or not self.reason_code.strip():
                raise ValueError("unavailable records require a reason_code")
        details = self.details
        if details is None:
            object.__setattr__(self, "details", MappingProxyType({}))
        elif not isinstance(details, Mapping):
            raise TypeError("details must be a mapping")
        elif type(details) is not MappingProxyType:
            object.__setattr__(self, "details", MappingProxyType(dict(details)))
