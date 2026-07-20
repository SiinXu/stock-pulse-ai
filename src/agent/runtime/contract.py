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
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

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


def _deep_freeze(value: Any) -> Any:
    """Recursively convert a value into an immutable snapshot.

    Mappings become read-only proxies, sequences become tuples and sets
    become frozensets, so a caller can never mutate an execution's inputs
    after construction — not even through nested containers (AR-RF-02).
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def deep_thaw(value: Any) -> Any:
    """Inverse of :func:`_deep_freeze`: a mutable deep copy for adapters.

    The frozen snapshot protects the contract boundary; native code still
    expects ordinary ``dict``/``list``/``set`` instances, so adapters thaw
    the snapshot at the boundary rather than leaking immutable containers.
    """
    if isinstance(value, Mapping):
        return {key: deep_thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [deep_thaw(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return {deep_thaw(item) for item in value}
    return value


@dataclass(frozen=True)
class ExecutionContext:
    """Frozen input snapshot for a single execution.

    ``request_context`` is deep-frozen into a read-only snapshot so an
    execution can never observe caller-side mutation after creation, not
    even through nested dicts, lists or sets.
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
            self, "request_context", _deep_freeze(dict(self.request_context))
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

    def finish_resolved(
        self,
        resolver: Callable[
            [bool], Tuple[ExecutionState, Any, Optional[str]]
        ],
    ) -> bool:
        """Resolve and commit one terminal transition under the state lock.

        ``resolver`` receives the cancellation-intent snapshot while the same
        lock that protects :meth:`request_cancel` remains held. This closes the
        check-to-finish race for adapters that must apply cancellation or a
        deadline at their final write fence. The resolver must be side-effect
        free and must not call back into this execution.
        """
        with self._lock:
            if self._state in TERMINAL_STATES:
                return self._drop_locked("finish_resolved", None)
            state, result, error = resolver(self._cancel_requested)
            if state not in TERMINAL_STATES:
                raise ValueError(
                    f"finish_resolved() requires a terminal state, got: {state}"
                )
            self._state = state
            self._result = result
            self._error = error
            return True

    def claim_operation(
        self,
        claim: Callable[[], None],
        *,
        deadline_monotonic: Optional[float] = None,
    ) -> Optional[ExecutionState]:
        """Linearize one external operation against cancel and deadline state.

        ``claim`` must only record a constant-time reservation or result
        acceptance; it must not perform a potentially blocking external call.
        A ``None`` return means the claim won. Otherwise the returned state
        identifies the fence that won, and ``claim`` was not invoked.
        """
        with self._lock:
            if self._state is not ExecutionState.RUNNING:
                return self._state
            if self._cancel_requested:
                return ExecutionState.CANCELLED
            if (
                deadline_monotonic is not None
                and time.monotonic() >= deadline_monotonic
            ):
                return ExecutionState.TIMED_OUT
            claim()
            return None

    def request_cancel(self) -> bool:
        """Record cancellation intent. No-op once terminal."""
        with self._lock:
            if self._state in TERMINAL_STATES:
                return False
            self._cancel_requested = True
            return True

    def _drop_locked(
        self,
        operation: str,
        attempted: Optional[ExecutionState],
    ) -> bool:
        self._dropped_transitions += 1
        logger.warning(
            "[Runtime] dropped late %s transition: execution_id=%s current=%s attempted=%s",
            operation,
            self._context.execution_id,
            self._state.value,
            attempted.value if attempted is not None else "unresolved",
        )
        return False


class _EventStream:
    """Thread-safe, replayable event buffer for a running execution."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._events: list = []
        self._closed = False

    def publish(self, event: Any) -> None:
        with self._condition:
            if self._closed:
                return
            self._events.append(event)
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def snapshot(self) -> Tuple[Any, ...]:
        with self._condition:
            return tuple(self._events)

    def subscribe(self, timeout: Optional[float] = None) -> Iterator[Any]:
        index = 0
        while True:
            with self._condition:
                while index >= len(self._events) and not self._closed:
                    if not self._condition.wait(timeout):
                        if index >= len(self._events) and not self._closed:
                            return
                if index >= len(self._events) and self._closed:
                    return
                batch = self._events[index:]
                index = len(self._events)
            for event in batch:
                yield event


class ExecutionHandle:
    """Caller-facing control handle for a possibly-running execution.

    Returned by ``AgentRuntime.start`` while the worker may still be in
    ``RUNNING``. Callers can observe state, consume events, request
    cancellation, await the terminal state and release resources. The
    single-argument form ``ExecutionHandle(execution)`` remains a pure
    status view for callers that own the lifecycle themselves.
    """

    def __init__(
        self,
        execution: AgentExecution,
        *,
        event_stream: Optional["_EventStream"] = None,
        done_event: Optional[threading.Event] = None,
    ):
        self._execution = execution
        self._event_stream = event_stream
        self._done_event = done_event
        self._worker: Optional[threading.Thread] = None
        self._worker_exception: Optional[BaseException] = None
        self._close_lock = threading.Lock()
        self._closed = False

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

    @property
    def events(self) -> Tuple[Any, ...]:
        if self._event_stream is None:
            return ()
        return self._event_stream.snapshot()

    @property
    def worker_exception(self) -> Optional[BaseException]:
        return self._worker_exception

    def subscribe(self, timeout: Optional[float] = None) -> Iterator[Any]:
        if self._event_stream is None:
            return iter(())
        return self._event_stream.subscribe(timeout=timeout)

    def request_cancel(self) -> bool:
        return self._execution.request_cancel()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until terminal (or ``timeout``); returns whether terminal."""
        if self._done_event is not None:
            self._done_event.wait(timeout)
        return self._execution.is_terminal

    def close(self) -> None:
        """Idempotently join the worker and close the event stream."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        worker = self._worker
        if (
            worker is not None
            and worker.is_alive()
            and worker is not threading.current_thread()
        ):
            worker.join()
        if self._event_stream is not None:
            self._event_stream.close()

    def _attach_worker(self, worker: threading.Thread) -> None:
        self._worker = worker

    def _set_worker_exception(self, exc: BaseException) -> None:
        self._worker_exception = exc


ProgressCallback = Callable[[Dict[str, Any]], None]


@runtime_checkable
class AgentRuntime(Protocol):
    """Protocol every runtime adapter must implement.

    ``start`` launches the execution and returns a live
    ``ExecutionHandle`` that may still be ``RUNNING``; callers use it to
    observe state, consume events, cancel and await the terminal state.
    ``execute`` is a synchronous compatibility helper: it starts, waits
    for the terminal state and returns the handle, re-raising any error
    the native stack raised so existing callers keep their semantics.
    """

    @property
    def name(self) -> str:
        ...

    def start(
        self,
        context: ExecutionContext,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ExecutionHandle:
        ...

    def execute(
        self,
        context: ExecutionContext,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ExecutionHandle:
        ...
