# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Agent run observability L0: structured events with trace/span ids.

Lightweight phase / tool / model / decision events are default-on and
persisted through the existing run-diagnostics / run-flow storage path.
Deep payload capture is opt-in via ``AGENT_OBSERVABILITY_DEEP_PAYLOAD``.
"""

from __future__ import annotations

from src.agent.observability.events import (
    AGENT_EVENT_SCHEMA_VERSION,
    AgentEventType,
    AgentRunEvent,
    build_span_id,
    emit_agent_event,
    emit_decision,
    emit_model_end,
    emit_model_start,
    emit_phase_end,
    emit_phase_start,
    emit_tool_end,
    emit_tool_start,
    is_agent_observability_enabled,
    is_deep_payload_enabled,
    reset_span_state_for_tests,
    sanitize_agent_event_payload,
)

__all__ = [
    "AGENT_EVENT_SCHEMA_VERSION",
    "AgentEventType",
    "AgentRunEvent",
    "build_span_id",
    "emit_agent_event",
    "emit_decision",
    "emit_model_end",
    "emit_model_start",
    "emit_phase_end",
    "emit_phase_start",
    "emit_tool_end",
    "emit_tool_start",
    "is_agent_observability_enabled",
    "is_deep_payload_enabled",
    "reset_span_state_for_tests",
    "sanitize_agent_event_payload",
]
