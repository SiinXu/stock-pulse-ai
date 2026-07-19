# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for the vendor-neutral runtime state machine (AR-PY-01)."""

import threading

import pytest

from src.agent.runtime.contract import (
    TERMINAL_STATES,
    AgentExecution,
    AgentRuntime,
    ExecutionContext,
    ExecutionHandle,
    ExecutionMode,
    ExecutionState,
    deep_thaw,
)
from src.agent.runtime.native_adapter import NativeRuntimeAdapter


def make_context(mode=ExecutionMode.RUN, **overrides):
    params = {"mode": mode, "prompt": "analyze 600519"}
    if mode is ExecutionMode.CHAT:
        params["session_id"] = "session-1"
    params.update(overrides)
    return ExecutionContext(**params)


# ---------------------------------------------------------------------------
# ExecutionContext freezing
# ---------------------------------------------------------------------------

def test_context_is_frozen():
    ctx = make_context()
    with pytest.raises(AttributeError):
        ctx.prompt = "changed"


def test_context_request_context_is_read_only_snapshot():
    source = {"stock_code": "600519"}
    ctx = make_context(request_context=source)
    source["stock_code"] = "000001"
    assert ctx.request_context["stock_code"] == "600519"
    with pytest.raises(TypeError):
        ctx.request_context["stock_code"] = "000001"


def test_context_chat_requires_session_id():
    with pytest.raises(ValueError):
        ExecutionContext(mode=ExecutionMode.CHAT, prompt="hi")


def test_context_coerces_mode_from_string():
    ctx = ExecutionContext(mode="run", prompt="task")
    assert ctx.mode is ExecutionMode.RUN


def test_context_execution_ids_are_unique():
    assert make_context().execution_id != make_context().execution_id


# ---------------------------------------------------------------------------
# State machine transitions
# ---------------------------------------------------------------------------

def test_lifecycle_created_running_succeeded():
    execution = AgentExecution(make_context())
    assert execution.state is ExecutionState.CREATED
    assert execution.start() is True
    assert execution.state is ExecutionState.RUNNING
    assert execution.finish(ExecutionState.SUCCEEDED, result={"ok": True}) is True
    assert execution.state is ExecutionState.SUCCEEDED
    assert execution.is_terminal
    assert execution.result == {"ok": True}


def test_finish_requires_terminal_state():
    execution = AgentExecution(make_context())
    with pytest.raises(ValueError):
        execution.finish(ExecutionState.RUNNING)


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES, key=lambda s: s.value))
def test_terminal_states_are_immutable(terminal):
    execution = AgentExecution(make_context())
    execution.start()
    assert execution.finish(terminal, result="first", error="first-error") is True

    for late in TERMINAL_STATES:
        assert execution.finish(late, result="late", error="late-error") is False

    assert execution.state is terminal
    assert execution.result == "first"
    assert execution.error == "first-error"
    assert execution.dropped_transitions == len(TERMINAL_STATES)


def test_double_start_is_dropped_and_audited():
    execution = AgentExecution(make_context())
    assert execution.start() is True
    assert execution.start() is False
    assert execution.state is ExecutionState.RUNNING
    assert execution.dropped_transitions == 1


def test_start_after_terminal_is_dropped():
    execution = AgentExecution(make_context())
    execution.start()
    execution.finish(ExecutionState.FAILED, error="boom")
    assert execution.start() is False
    assert execution.state is ExecutionState.FAILED


def test_concurrent_terminal_precedence_first_wins():
    execution = AgentExecution(make_context())
    execution.start()
    barrier = threading.Barrier(2)
    outcomes = {}

    def contender(name, state):
        barrier.wait()
        outcomes[name] = execution.finish(state, result=name)

    threads = [
        threading.Thread(target=contender, args=("a", ExecutionState.SUCCEEDED)),
        threading.Thread(target=contender, args=("b", ExecutionState.CANCELLED)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes.values()) == [False, True]
    winner = next(name for name, won in outcomes.items() if won)
    assert execution.result == winner
    assert execution.dropped_transitions == 1
    assert execution.state in (ExecutionState.SUCCEEDED, ExecutionState.CANCELLED)


# ---------------------------------------------------------------------------
# Cancellation intent
# ---------------------------------------------------------------------------

def test_request_cancel_records_intent_without_terminal_transition():
    execution = AgentExecution(make_context())
    execution.start()
    assert execution.cancel_requested is False
    assert execution.request_cancel() is True
    assert execution.cancel_requested is True
    assert execution.state is ExecutionState.RUNNING


def test_request_cancel_after_terminal_is_rejected():
    execution = AgentExecution(make_context())
    execution.start()
    execution.finish(ExecutionState.SUCCEEDED)
    assert execution.request_cancel() is False
    assert execution.cancel_requested is False


# ---------------------------------------------------------------------------
# Handle delegation and runtime protocol
# ---------------------------------------------------------------------------

def test_handle_delegates_to_execution():
    execution = AgentExecution(make_context())
    handle = ExecutionHandle(execution)
    assert handle.execution_id == execution.context.execution_id
    assert handle.state is ExecutionState.CREATED
    assert handle.request_cancel() is True
    assert execution.cancel_requested is True
    execution.start()
    execution.finish(ExecutionState.SUCCEEDED, result="done")
    assert handle.is_terminal
    assert handle.result == "done"
    assert handle.error is None


def test_native_adapter_satisfies_runtime_protocol():
    adapter = NativeRuntimeAdapter(config=object())
    assert isinstance(adapter, AgentRuntime)
    assert adapter.name == "native"
    assert hasattr(adapter, "start")


# ---------------------------------------------------------------------------
# Deep-frozen execution context (AR-RF-02)
# ---------------------------------------------------------------------------

def test_context_deep_freezes_nested_containers():
    source = {"filters": {"sectors": ["tech"]}, "codes": ["600519"], "tags": {"a"}}
    ctx = make_context(request_context=source)
    # Caller mutation of nested objects after construction must not leak in.
    source["filters"]["sectors"].append("bank")
    source["codes"].append("000001")
    source["tags"].add("b")
    assert ctx.request_context["filters"]["sectors"] == ("tech",)
    assert ctx.request_context["codes"] == ("600519",)
    assert ctx.request_context["tags"] == frozenset({"a"})
    with pytest.raises(TypeError):
        ctx.request_context["filters"]["sectors"] = ["x"]


def test_deep_thaw_restores_mutable_containers():
    ctx = make_context(
        request_context={"filters": {"sectors": ["tech"]}, "codes": ["600519"], "tags": {"a"}}
    )
    thawed = deep_thaw(ctx.request_context)
    assert thawed == {"filters": {"sectors": ["tech"]}, "codes": ["600519"], "tags": {"a"}}
    assert isinstance(thawed, dict)
    assert isinstance(thawed["filters"], dict)
    assert isinstance(thawed["codes"], list)
    assert isinstance(thawed["tags"], set)
    thawed["codes"].append("000001")  # mutable, must not raise


# ---------------------------------------------------------------------------
# Live execution handle (RF-02)
# ---------------------------------------------------------------------------

class _Result:
    def __init__(self, *, success=True, cancelled=False, timed_out=False, error=None):
        self.success = success
        self.cancelled = cancelled
        self.timed_out = timed_out
        self.error = error


class _BlockingExecutor:
    """Native-style executor whose run() blocks until released."""

    def __init__(self, release, *, started=None, result=None, raise_exc=None):
        self._release = release
        self._started = started
        self._result = result if result is not None else _Result()
        self._raise = raise_exc
        self.calls = []

    def run(self, prompt, context=None):
        self.calls.append(("run", prompt, context))
        if self._started is not None:
            self._started.set()
        assert self._release.wait(5)
        if self._raise is not None:
            raise self._raise
        return self._result


class _ChatExecutor:
    """Native-style executor whose chat() emits progress then blocks."""

    def __init__(self, release, events, *, started=None, result=None):
        self._release = release
        self._events = events
        self._started = started
        self._result = result if result is not None else _Result()

    def chat(self, prompt, session_id=None, progress_callback=None, context=None):
        if self._started is not None:
            self._started.set()
        for event in self._events:
            progress_callback(event)
        assert self._release.wait(5)
        return self._result


def test_start_returns_running_handle_then_completes():
    release = threading.Event()
    started = threading.Event()
    result = _Result(success=True)
    adapter = NativeRuntimeAdapter(executor=_BlockingExecutor(release, started=started, result=result))
    handle = adapter.start(make_context())
    assert started.wait(5)
    assert handle.state is ExecutionState.RUNNING
    assert handle.is_terminal is False
    release.set()
    assert handle.wait(5) is True
    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.result is result
    handle.close()


def test_cancel_while_running_is_recorded():
    release = threading.Event()
    started = threading.Event()
    adapter = NativeRuntimeAdapter(
        executor=_BlockingExecutor(release, started=started, result=_Result(success=False, cancelled=True))
    )
    handle = adapter.start(make_context())
    assert started.wait(5)
    assert handle.request_cancel() is True
    assert handle.cancel_requested is True
    assert handle.state is ExecutionState.RUNNING
    release.set()
    assert handle.wait(5) is True
    assert handle.state is ExecutionState.CANCELLED
    handle.close()


def test_wait_timeout_while_running_returns_false():
    release = threading.Event()
    started = threading.Event()
    adapter = NativeRuntimeAdapter(executor=_BlockingExecutor(release, started=started))
    handle = adapter.start(make_context())
    assert started.wait(5)
    assert handle.wait(timeout=0.05) is False
    assert handle.state is ExecutionState.RUNNING
    release.set()
    assert handle.wait(5) is True
    handle.close()


def test_close_is_idempotent():
    release = threading.Event()
    release.set()
    adapter = NativeRuntimeAdapter(executor=_BlockingExecutor(release))
    handle = adapter.start(make_context())
    assert handle.wait(5) is True
    handle.close()
    handle.close()


def test_execute_reraises_native_exception():
    release = threading.Event()
    release.set()
    boom = RuntimeError("native boom")
    adapter = NativeRuntimeAdapter(executor=_BlockingExecutor(release, raise_exc=boom))
    with pytest.raises(RuntimeError, match="native boom"):
        adapter.execute(make_context())


def test_events_are_observable_via_handle():
    release = threading.Event()
    started = threading.Event()
    events = [{"type": "step", "n": 1}, {"type": "step", "n": 2}]
    adapter = NativeRuntimeAdapter(
        executor=_ChatExecutor(release, events, started=started)
    )
    handle = adapter.start(make_context(mode=ExecutionMode.CHAT))
    assert started.wait(5)
    release.set()
    assert handle.wait(5) is True
    assert list(handle.events) == events
    # After terminal the stream is closed, so subscribe replays and returns.
    assert list(handle.subscribe(timeout=0.1)) == events
    handle.close()


def test_cancel_before_start_records_intent():
    execution = AgentExecution(make_context())
    assert execution.request_cancel() is True
    assert execution.cancel_requested is True
    assert execution.start() is True
    assert execution.state is ExecutionState.RUNNING
