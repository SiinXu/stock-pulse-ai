# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Schemas for the read-only capability registry aggregation API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CapabilityDomain = Literal["data", "tool", "extension"]


class CapabilityItem(BaseModel):
    """One aggregated capability observation."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable capability id (domain-prefixed)")
    domain: CapabilityDomain
    provider: str
    available: bool
    reason_code: Optional[str] = None
    reason_message: Optional[str] = None
    display_name: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class CapabilityListResponse(BaseModel):
    """GET /api/v1/capabilities response."""

    model_config = ConfigDict(extra="forbid")

    items: List[CapabilityItem] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    available_count: int = Field(..., ge=0)
    unavailable_count: int = Field(..., ge=0)
