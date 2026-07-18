# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Execution lifecycle binding (AR-PY-03).

``ExecutionLifecycle`` ties one execution together: the ``AgentExecution``
state machine (AR-PY-01), the versioned event stream with its late-write
fence (``events.py``) and the cancellation intent consumed by the native
loop's cooperative checkpoints.

``classify_terminal_state`` is the single stable classification from a
native result to a terminal ``ExecutionState``; every runtime path (SSE
endpoint, ``NativeRuntimeAdapter``, future adapters) must map results
through it so identical failures never diverge across runtimes.

``UsageRecorder`` is the single convergence point for LLM usage
telemetry persistence, replacing the previous direct
``persist_llm_usage`` calls scattered across the runner and the chat
context compressor.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from src.agent.runtime.contract import (
    AgentExecution,
    ExecutionContext,
    ExecutionHandle,
    ExecutionState,
)
from src.agent.runtime.events import RuntimeEvent, RuntimeEventEmitter
from src.llm.usage import should_persist_usage_telemetry
from src.storage import persist_llm_usage


class UsageRecorder:
    """Single convergence point for LLM usage telemetry persistence."""

    def record(
        self,
        usage: Any,
        model: str,
        *,
        call_type: str = "agent",
    ) -> bool:
        """Persist one usage sample; returns whether it was persisted."""
        if not should_persist_usage_telemetry(usage):
            return False
        persist_llm_usage(usage, model, call_type=call_type)
        return True


_DEFAULT_USAGE_RECORDER = UsageRecorder()


def get_default_usage_recorder() -> UsageRecorder:
    return _DEFAULT_USAGE_RECORDER


def classify_terminal_state(
    *,
    success: bool,
    cancelled: bool = False,
    timed_out: bool = False,
) -> ExecutionState:
    """Stable result classification shared by every runtime path.

    Cancellation wins over any other outcome: a cancelled execution must
    terminate as ``CANCELLED`` even when partial content exists, so the
    degraded-synthesis paths can never masquerade as pseudo-success.
    """
    if cancelled:
        return ExecutionState.CANCELLED
    if success:
        return ExecutionState.SUCCEEDED
    if timed_out:
        return ExecutionState.TIMED_OUT
    return ExecutionState.FAILED


class ExecutionLifecycle:
    """Binds one execution's state machine, event stream and cancellation."""

    def __init__(
        self,
        context: ExecutionContext,
        *,
        usage_recorder: Optional[UsageRecorder] = None,
    ) -> None:
        self._execution = AgentExecution(context)
        self._handle = ExecutionHandle(self._execution)
        self._emitter = RuntimeEventEmitter(
            execution_id=context.execution_id,
            terminal_check=lambda: self._execution.is_terminal,
        )
        self._usage_recorder = (
            usage_recorder if usage_recorder is not None else get_default_usage_recorder()
        )

    @property
    def execution_id(self) -> str:
        return self._execution.context.execution_id

    @property
    def handle(self) -> ExecutionHandle:
        return self._handle

    @property
    def emitter(self) -> RuntimeEventEmitter:
        return self._emitter

    @property
    def usage_recorder(self) -> UsageRecorder:
        return self._usage_recorder

    @property
    def state(self) -> ExecutionState:
        return self._execution.state

    @property
    def is_terminal(self) -> bool:
        return self._execution.is_terminal

    def start(self) -> bool:
        return self._execution.start()

    def request_cancel(self) -> bool:
        return self._execution.request_cancel()

    def cancelled_check(self) -> bool:
        """Cooperative cancellation probe; pass as ``cancelled_check=``."""
        return self._execution.cancel_requested

    def ingest_progress_event(
        self, event: Mapping[str, Any]
    ) -> Optional[RuntimeEvent]:
        """Uplift a legacy progress dict; ``None`` means fenced late event."""
        return self._emitter.ingest_legacy(event)

    def finish_from_result(self, result: Any) -> ExecutionState:
        """Classify a native result and finish the execution (first wins)."""
        state = classify_terminal_state(
            success=bool(getattr(result, "success", False)),
            cancelled=bool(getattr(result, "cancelled", False)),
            timed_out=bool(getattr(result, "timed_out", False)),
        )
        self._execution.finish(state, result=result, error=getattr(result, "error", None))
        return state

    def fail(self, error: str) -> bool:
        return self._execution.finish(ExecutionState.FAILED, error=error)
