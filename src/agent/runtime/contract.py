# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Vendor-neutral agent runtime contract (AR-PY-01).

Defines the execution state machine, the frozen per-execution input
snapshot and the ``AgentRuntime`` protocol that every runtime adapter
(native first, external frameworks later) must implement.

Contract rules (ADR-001):

- No external agent framework types may appear in this module.
- Terminal states are immutable; on concurrent terminal transitions the
  first one wins and later attempts are dropped and audited.
- ``request_cancel()`` records intent only. As of AR-PY-03 the native
  loop consumes that intent at cooperative checkpoints (top of each step,
  after every LLM call, at pipeline stage boundaries) and terminates as
  ``CANCELLED`` via ``classify_terminal_state``; cancellation always wins
  over degraded synthesis and timeout so a cancelled run never reports a
  pseudo-success.
- ``ExecutionContext`` only carries fields that are actually consumed at
  the current stage. Tool allowlists, budgets and resolved model routes
  are added in later phases when they become enforced, to avoid
  declared-but-unenforced contract surface.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    """Business entrypoint the execution maps to."""

    RUN = "run"
    CHAT = "chat"
    RESEARCH = "research"


class ExecutionState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


TERMINAL_STATES = frozenset(
    {
        ExecutionState.SUCCEEDED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
        ExecutionState.TIMED_OUT,
    }
)


def new_execution_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class ExecutionContext:
    """Frozen input snapshot for a single execution.

    ``request_context`` is defensively copied into a read-only mapping so
    an execution can never observe caller-side mutation after creation.
    """

    mode: ExecutionMode
    prompt: str
    execution_id: str = field(default_factory=new_execution_id)
    session_id: Optional[str] = None
    architecture: Optional[str] = None
    request_context: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ExecutionMode):
            object.__setattr__(self, "mode", ExecutionMode(self.mode))
        if self.mode is ExecutionMode.CHAT and not self.session_id:
            raise ValueError("chat execution requires a session_id")
        object.__setattr__(
            self, "request_context", MappingProxyType(dict(self.request_context))
        )


class AgentExecution:
    """Thread-safe execution state machine with terminal precedence."""

    def __init__(self, context: ExecutionContext):
        self._context = context
        self._lock = threading.Lock()
        self._state = ExecutionState.CREATED
        self._result: Any = None
        self._error: Optional[str] = None
        self._cancel_requested = False
        self._dropped_transitions = 0

    @property
    def context(self) -> ExecutionContext:
        return self._context

    @property
    def state(self) -> ExecutionState:
        with self._lock:
            return self._state

    @property
    def is_terminal(self) -> bool:
        with self._lock:
            return self._state in TERMINAL_STATES

    @property
    def result(self) -> Any:
        with self._lock:
            return self._result

    @property
    def error(self) -> Optional[str]:
        with self._lock:
            return self._error

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_requested

    @property
    def dropped_transitions(self) -> int:
        with self._lock:
            return self._dropped_transitions

    def start(self) -> bool:
        """Transition ``created`` -> ``running``. Any other origin is dropped."""
        with self._lock:
            if self._state is ExecutionState.CREATED:
                self._state = ExecutionState.RUNNING
                return True
            return self._drop_locked("start", ExecutionState.RUNNING)

    def finish(
        self,
        state: ExecutionState,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """Transition to a terminal state.

        Returns ``True`` when this call owns the terminal transition.
        Late attempts after a terminal state are dropped and audited
        (first terminal wins), returning ``False``.
        """
        if state not in TERMINAL_STATES:
            raise ValueError(f"finish() requires a terminal state, got: {state}")
        with self._lock:
            if self._state in TERMINAL_STATES:
                return self._drop_locked("finish", state)
            self._state = state
            self._result = result
            self._error = error
            return True

    def request_cancel(self) -> bool:
        """Record cancellation intent. No-op once terminal."""
        with self._lock:
            if self._state in TERMINAL_STATES:
                return False
            self._cancel_requested = True
            return True

    def _drop_locked(self, operation: str, attempted: ExecutionState) -> bool:
        self._dropped_transitions += 1
        logger.warning(
            "[Runtime] dropped late %s transition: execution_id=%s current=%s attempted=%s",
            operation,
            self._context.execution_id,
            self._state.value,
            attempted.value,
        )
        return False


class ExecutionHandle:
    """Caller-facing view of an execution: status queries plus cancel intent."""

    def __init__(self, execution: AgentExecution):
        self._execution = execution

    @property
    def execution_id(self) -> str:
        return self._execution.context.execution_id

    @property
    def context(self) -> ExecutionContext:
        return self._execution.context

    @property
    def state(self) -> ExecutionState:
        return self._execution.state

    @property
    def is_terminal(self) -> bool:
        return self._execution.is_terminal

    @property
    def result(self) -> Any:
        return self._execution.result

    @property
    def error(self) -> Optional[str]:
        return self._execution.error

    @property
    def cancel_requested(self) -> bool:
        return self._execution.cancel_requested

    def request_cancel(self) -> bool:
        return self._execution.request_cancel()


ProgressCallback = Callable[[Dict[str, Any]], None]


@runtime_checkable
class AgentRuntime(Protocol):
    """Protocol every runtime adapter must implement.

    AR-PY-01 semantics: ``execute`` runs synchronously and returns a
    handle already in a terminal state. ``progress_callback`` bridges the
    existing native progress events until typed runtime events replace it
    (AR-PY-03).
    """

    @property
    def name(self) -> str:
        ...

    def execute(
        self,
        context: ExecutionContext,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ExecutionHandle:
        ...
