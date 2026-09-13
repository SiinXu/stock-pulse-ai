# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-soft EvolutionEvent append for online adapters (Issue #1106).

Lives in ``src.services`` so ``src.agent`` does not import ``src.repositories``
(ADR-010). This is the default writer for ``calibrate_confidence``; callers may
inject ``append_event``. Append failure is logged and does not raise to the
adapter. This module does not list events, auto-promote, or mutate Soul.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.repositories.agent_evolution_event_repo import AgentEvolutionEventRepository
from src.repositories.base import RepositoryError
from src.schemas.evolution_event import EvolutionEventCreate
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


def append_evolution_event(event: EvolutionEventCreate) -> Any:
    """Append one EvolutionEvent through the repository. Fail-closed."""
    return AgentEvolutionEventRepository().append(event)


def append_evolution_event_fail_soft(
    event: EvolutionEventCreate,
    *,
    append_event: Optional[Callable[[EvolutionEventCreate], Any]] = None,
    samples: int = 0,
    event_type: str = "",
    log: Optional[logging.Logger] = None,
) -> None:
    """Invoke the writer and log repository/validation failures without raising."""
    writer = append_event if append_event is not None else append_evolution_event
    try:
        writer(event)
    except (RepositoryError, ValidationError, SQLAlchemyError) as exc:
        log_safe_exception(
            log or logger,
            "Online adapter calibration event append failed",
            exc,
            error_code="adapter_calibrate_event_append_failed",
            level=logging.WARNING,
            context={"event_type": str(event_type), "samples": int(samples)},
        )
