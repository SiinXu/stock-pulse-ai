# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Response models for reasoning-trace export (Issue #135)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReasoningTraceExportResponse(BaseModel):
    """JSON export envelope for ``reasoning-trace-v1``."""

    schema_version: str = Field(..., description="Export contract version")
    run: Dict[str, Any] = Field(default_factory=dict)
    agents: List[Dict[str, Any]] = Field(default_factory=list)
    synthesis: Dict[str, Any] = Field(default_factory=dict)
    data_sources: Dict[str, Any] = Field(default_factory=dict)
    coverage: Dict[str, Any] = Field(default_factory=dict)
    truncated: bool = False
    truncation: Optional[Dict[str, Any]] = None
    markdown: Optional[str] = Field(
        default=None,
        description="Optional human-readable markdown companion (redacted)",
    )
