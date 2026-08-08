# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only contracts for outbound HTTP policy transparency."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field

OUTBOUND_ACTIVITY_MAX_PAGE_SIZE = 100

OutboundDecision = Literal["allowed", "blocked"]


class _StrictOutboundModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class LocalOnlyModeStatus(_StrictOutboundModel):
    enabled: bool = Field(...)
    env_key: str = Field(default="LOCAL_ONLY_MODE")
    policy: str = Field(default="non_loopback_denied")
    allowed_destination_classes: List[str] = Field(default_factory=lambda: ["loopback"])
    blocked_error_reason: str = Field(default="local_only_mode_blocked")


class OutboundActivityItem(_StrictOutboundModel):
    occurred_at: str = Field(...)
    decision: OutboundDecision = Field(...)
    destination_class: str = Field(...)
    scheme: str = Field(...)
    host_type: str = Field(...)
    reason: str = Field(...)
    correlation_id: str = Field(...)
    local_only_mode: bool = Field(...)
    allowlisted: bool = Field(...)


class OutboundActivityPage(_StrictOutboundModel):
    local_only_mode: bool = Field(...)
    items: List[OutboundActivityItem] = Field(default_factory=list)
    limit: int = Field(..., ge=1, le=OUTBOUND_ACTIVITY_MAX_PAGE_SIZE)
    returned: int = Field(..., ge=0)
    max_retained: int = Field(...)
