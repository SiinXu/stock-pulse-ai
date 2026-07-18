# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Versioned internal runtime events (AR-PY-03).

``RuntimeEvent`` is the internal, versioned progress event carrying the
execution identity (``execution_id``/``stage``/``attempt``/``sequence``)
that the public SSE contract intentionally omits. The public SSE dicts
(``docs/agent-stream-events.md``) are produced exclusively through
:func:`to_public_sse_event` — the single downgrade point — so the wire
contract stays byte-identical while internal consumers gain typed
metadata.

The native stack keeps emitting legacy progress dicts at its existing
call sites; :meth:`RuntimeEventEmitter.ingest_legacy` uplifts them at the
execution boundary. Future runtime adapters emit typed events directly
via :meth:`RuntimeEventEmitter.emit`. Both entries share one sequence,
one stage tracker and one late-write fence: events arriving after the
execution reached a terminal state are dropped and audited, never
delivered.

``done`` / ``error`` SSE events are synthesized by the SSE endpoint from
the terminal execution result and are not part of the callback stream.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, Optional

from src.agent.stream_events import stream_event

logger = logging.getLogger(__name__)

RUNTIME_EVENT_SCHEMA_VERSION = 1

# Progress event types that map onto the public SSE contract. ``done`` and
# ``error`` are endpoint-synthesized terminal envelopes, not progress events.
PUBLIC_PROGRESS_EVENT_TYPES = frozenset(
    {
        "stage_start",
        "stage_done",
        "thinking",
        "tool_start",
        "tool_done",
        "generating",
        "pipeline_timeout",
        "pipeline_budget_skipped",
    }
)


@dataclass(frozen=True)
class RuntimeEvent:
    """Immutable internal event with frozen execution identity."""

    event_type: str
    execution_id: str
    sequence: int
    timestamp: float
    stage: Optional[str] = None
    attempt: Optional[int] = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = RUNTIME_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


def to_public_sse_event(event: RuntimeEvent) -> Dict[str, Any]:
    """Downgrade an internal event to the public SSE dict shape.

    This is the only supported path from internal events to the SSE wire
    contract. Reusing :func:`stream_event` keeps field semantics (including
    None-dropping) byte-identical with historical emissions.
    """
    return stream_event(event.event_type, **dict(event.payload))


class RuntimeEventEmitter:
    """Thread-safe, execution-scoped event source with a late-write fence."""

    def __init__(
        self,
        *,
        execution_id: str,
        terminal_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("RuntimeEventEmitter requires a non-empty execution_id")
        self._execution_id = execution_id
        self._terminal_check = terminal_check
        self._lock = threading.Lock()
        self._sequence = 0
        self._current_stage: Optional[str] = None
        self._dropped_events = 0

    @property
    def execution_id(self) -> str:
        return self._execution_id

    @property
    def dropped_events(self) -> int:
        with self._lock:
            return self._dropped_events

    def ingest_legacy(self, event: Mapping[str, Any]) -> Optional[RuntimeEvent]:
        """Uplift a legacy progress dict emitted by the native stack.

        Returns ``None`` when the event arrived after the terminal state
        and was fenced off (dropped and audited).
        """
        event_type = str(event.get("type") or "")
        payload = {key: value for key, value in event.items() if key != "type"}
        return self._emit(event_type, payload, stage_hint=payload.get("stage"))

    def emit(
        self,
        event_type: str,
        *,
        stage: Optional[str] = None,
        attempt: Optional[int] = None,
        **fields: Any,
    ) -> Optional[RuntimeEvent]:
        """Emit a typed internal event (entry point for runtime adapters)."""
        payload = {key: value for key, value in fields.items() if value is not None}
        return self._emit(event_type, payload, stage_hint=stage, attempt=attempt)

    def _emit(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        stage_hint: Optional[str] = None,
        attempt: Optional[int] = None,
    ) -> Optional[RuntimeEvent]:
        with self._lock:
            if self._terminal_check is not None and self._terminal_check():
                self._dropped_events += 1
                logger.warning(
                    "[RuntimeEvents] dropped late event after terminal state: "
                    "execution_id=%s type=%s",
                    self._execution_id,
                    event_type,
                )
                return None
            if event_type == "stage_start":
                self._current_stage = stage_hint
            stage = stage_hint if stage_hint is not None else self._current_stage
            if event_type == "stage_done":
                self._current_stage = None
            sequence = self._sequence
            self._sequence += 1
            return RuntimeEvent(
                event_type=event_type,
                execution_id=self._execution_id,
                sequence=sequence,
                timestamp=time.time(),
                stage=stage,
                attempt=attempt,
                payload=payload,
            )
