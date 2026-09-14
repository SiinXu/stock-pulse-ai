# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only EvolutionEvent list for the authenticated HTTP query (Issue #1113).

Wraps ``AgentEvolutionEventRepository.list_events`` only. This module does not
append, update, delete, or import the adapter producer helper.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.repositories.agent_evolution_event_repo import AgentEvolutionEventRepository
from src.schemas.evolution_event import EvolutionEvent, validate_query_limit
from src.storage import DatabaseManager


class EvolutionEventQueryService:
    """Project stored EvolutionEvent rows for the HTTP list."""

    def __init__(
        self,
        *,
        store: Optional[AgentEvolutionEventRepository] = None,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.store = store or AgentEvolutionEventRepository(db_manager)

    def list_events(
        self,
        *,
        occurred_from: datetime,
        occurred_to: datetime,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        bound = validate_query_limit(limit)
        items: List[EvolutionEvent] = self.store.list_events(
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            event_type=event_type,
            limit=limit,
        )
        return {
            "items": items,
            "limit": bound,
            "returned": len(items),
        }
