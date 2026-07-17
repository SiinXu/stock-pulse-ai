# -*- coding: utf-8 -*-
"""Vendor-neutral agent runtime layer (AR-PY-01/AR-PY-02).

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
from src.agent.runtime.native_adapter import NativeRuntimeAdapter
from src.agent.runtime.tool_session import BoundToolSession

__all__ = [
    "TERMINAL_STATES",
    "AgentExecution",
    "AgentRuntime",
    "BoundToolSession",
    "ExecutionContext",
    "ExecutionHandle",
    "ExecutionMode",
    "ExecutionState",
    "NativeRuntimeAdapter",
    "new_execution_id",
]
