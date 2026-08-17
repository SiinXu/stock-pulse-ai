# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Typed contracts for research asset package export (Issues #988 / #1140)."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _reject_non_finite(value: Any, *, path: str = "meta") -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_non_finite(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_non_finite(item, path=f"{path}[{index}]")


class ResearchPackProgressStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    status: Literal["pending", "running", "completed", "skipped", "failed"]
    detail: Optional[str] = Field(default=None, max_length=500)


class ResearchPackJsonEnvelope(BaseModel):
    """JSON companion when callers need metadata without assembling ZIP bytes."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["research-pack-v1"]
    meta: Dict[str, Any]
    truncated: bool
    progress: List[ResearchPackProgressStage] = Field(default_factory=list)
    byte_length: int = Field(ge=0)
    root_dirname: str = Field(min_length=1, max_length=120)
    zip_included: bool = False

    @field_validator("meta")
    @classmethod
    def validate_finite_meta(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        _reject_non_finite(value)
        return value
