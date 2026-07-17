# -*- coding: utf-8 -*-
"""Vendor-neutral agent runtime layer (AR-PY-01/AR-PY-02/AR-PY-03).

This package is owned by StockPulse and must never import external agent
framework types. See ``docs/architecture/ADR-001-agent-runtime.md``.
"""

from src.agent.runtime.contract import (
    TERMINAL_STATES,
    AgentExecution,
    AgentRuntime,
    ExecutionContext,
    ExecutionHandle,
    ExecutionMode,
    ExecutionState,
    new_execution_id,
)
from src.agent.runtime.events import (
    RUNTIME_EVENT_SCHEMA_VERSION,
    RuntimeEvent,
    RuntimeEventEmitter,
    to_public_sse_event,
)
from src.agent.runtime.lifecycle import (
    ExecutionLifecycle,
    UsageRecorder,
    classify_terminal_state,
    get_default_usage_recorder,
)
from src.agent.runtime.native_adapter import NativeRuntimeAdapter
from src.agent.runtime.tool_session import BoundToolSession

__all__ = [
    "RUNTIME_EVENT_SCHEMA_VERSION",
    "TERMINAL_STATES",
    "AgentExecution",
    "AgentRuntime",
    "BoundToolSession",
    "ExecutionContext",
    "ExecutionHandle",
    "ExecutionLifecycle",
    "ExecutionMode",
    "ExecutionState",
    "NativeRuntimeAdapter",
    "RuntimeEvent",
    "RuntimeEventEmitter",
    "UsageRecorder",
    "classify_terminal_state",
    "get_default_usage_recorder",
    "new_execution_id",
    "to_public_sse_event",
]
