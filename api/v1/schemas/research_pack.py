# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Typed contracts for research asset package export (Issues #988 / #1140)."""
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

class ResearchPackProgressStage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    status: Literal["pending", "running", "completed", "skipped", "failed"]
    detail: Optional[str] = Field(default=None, max_length=500)

class ResearchPackJsonEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["research-pack-v1"]
    meta: Dict[str, Any]
    truncated: bool
    progress: List[ResearchPackProgressStage] = Field(default_factory=list)
    byte_length: int = Field(ge=0)
    root_dirname: str = Field(min_length=1, max_length=120)
