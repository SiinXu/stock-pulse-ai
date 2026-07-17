# -*- coding: utf-8 -*-
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
