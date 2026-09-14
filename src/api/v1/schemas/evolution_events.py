# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP list response for authenticated EvolutionEvent queries (Issue #1113)."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.evolution_event import EVOLUTION_EVENT_MAX_LIMIT, EvolutionEvent


class EvolutionEventListResponse(BaseModel):
    """Bounded EvolutionEvent page. No total count or cursor in this slice."""

    model_config = ConfigDict(extra="forbid")

    items: List[EvolutionEvent]
    limit: int = Field(ge=1, le=EVOLUTION_EVENT_MAX_LIMIT)
    returned: int = Field(ge=0, le=EVOLUTION_EVENT_MAX_LIMIT)
