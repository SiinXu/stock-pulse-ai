# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Wrapper-parity tests for the native runtime adapter (AR-PY-01).

The adapter must pass native results through unchanged (identity, not
copies) and must never convert an exception into a degraded result.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent.runtime.contract import (
    ExecutionContext,
    ExecutionMode,
    ExecutionState,
)
from src.agent.runtime.native_adapter import NativeRuntimeAdapter


class FakeExecutor:
    """Records calls and returns pre-seeded results, mirroring the
    AgentExecutor / AgentOrchestrator run()/chat() interface."""

    def __init__(self, run_result=None, chat_result=None, run_error=None, chat_events=None):
        self.run_result = run_result
        self.chat_result = chat_result
        self.run_error = run_error
        self.chat_events = chat_events or []
        self.run_calls = []
        self.chat_calls = []

    def run(self, task, context=None):
        self.run_calls.append({"task": task, "context": context})
        if self.run_error is not None:
            raise self.run_error
        return self.run_result

    def chat(self, message, session_id, progress_callback=None, context=None):
        self.chat_calls.append(
            {
                "message": message,
                "session_id": session_id,
                "progress_callback": progress_callback,
                "context": context,
            }
        )
        for event in self.chat_events:
            if progress_callback is not None:
                progress_callback(event)
        return self.chat_result


def make_result(**overrides):
    fields = {"success": True, "content": "report", "error": None}
    fields.update(overrides)
    return SimpleNamespace(**fields)


# ---------------------------------------------------------------------------
# run mode
# ---------------------------------------------------------------------------

def test_run_success_passes_result_through_unchanged():
    result = make_result()
    executor = FakeExecutor(run_result=result)
    adapter = NativeRuntimeAdapter(executor=executor)

    handle = adapter.execute(
        ExecutionContext(
            mode=ExecutionMode.RUN,
            prompt="analyze 600519",
            request_context={"stock_code": "600519"},
        )
    )

    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.result is result
    assert handle.error is None
    assert executor.run_calls == [
        {"task": "analyze 600519", "context": {"stock_code": "600519"}}
    ]


def test_run_with_empty_request_context_passes_none():
    executor = FakeExecutor(run_result=make_result())
    adapter = NativeRuntimeAdapter(executor=executor)

    adapter.execute(ExecutionContext(mode=ExecutionMode.RUN, prompt="task"))

    assert executor.run_calls[0]["context"] is None


def test_run_failure_maps_to_failed_with_error():
    result = make_result(success=False, error="all models failed")
    executor = FakeExecutor(run_result=result)
    adapter = NativeRuntimeAdapter(executor=executor)

    handle = adapter.execute(ExecutionContext(mode=ExecutionMode.RUN, prompt="task"))

    assert handle.state is ExecutionState.FAILED
    assert handle.result is result
    assert handle.error == "all models failed"


def test_run_exception_marks_failed_and_reraises():
    from src.agent.runtime import native_adapter as native_module

    captured = []
    original_execution_cls = native_module.AgentExecution

    def capturing_execution(context):
        execution = original_execution_cls(context)
        captured.append(execution)
        return execution

    executor = FakeExecutor(run_error=RuntimeError("adapter exploded"))
    adapter = NativeRuntimeAdapter(executor=executor)

    with patch.object(native_module, "AgentExecution", new=capturing_execution):
        with pytest.raises(RuntimeError, match="adapter exploded"):
            adapter.execute(ExecutionContext(mode=ExecutionMode.RUN, prompt="task"))

    assert len(captured) == 1
    assert captured[0].state is ExecutionState.FAILED
    assert "adapter exploded" in (captured[0].error or "")


def test_degraded_success_true_result_stays_succeeded():
    """ADR-001 D2: degraded success=true results are a frozen compatibility
    contract; the adapter must map them to SUCCEEDED, error field intact."""
    result = make_result(success=True, error="pipeline budget exhausted")
    executor = FakeExecutor(run_result=result)
    adapter = NativeRuntimeAdapter(executor=executor)

    handle = adapter.execute(ExecutionContext(mode=ExecutionMode.RUN, prompt="task"))

    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.error == "pipeline budget exhausted"


# ---------------------------------------------------------------------------
# chat mode
# ---------------------------------------------------------------------------

def test_chat_dispatch_wraps_callback_and_forwards_events():
    """RF-02: the adapter wraps the caller callback so progress reaches both
    the caller and the live handle's event stream; message/session/context
    pass through unchanged."""
    result = make_result(content="answer")
    event = {"type": "step", "n": 1}
    executor = FakeExecutor(chat_result=result, chat_events=[event])
    adapter = NativeRuntimeAdapter(executor=executor)
    callback = MagicMock()

    handle = adapter.execute(
        ExecutionContext(
            mode=ExecutionMode.CHAT,
            prompt="what changed today?",
            session_id="session-9",
            request_context={"stock_code": "hk00700"},
        ),
        progress_callback=callback,
    )

    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.result is result
    assert len(executor.chat_calls) == 1
    call = executor.chat_calls[0]
    assert call["message"] == "what changed today?"
    assert call["session_id"] == "session-9"
    assert call["context"] == {"stock_code": "hk00700"}
    # The executor receives a wrapper, not the raw caller callback.
    assert call["progress_callback"] is not callback
    # The caller callback still fires, and the event is captured on the handle.
    callback.assert_called_once_with(event)
    assert list(handle.events) == [event]


# ---------------------------------------------------------------------------
# research mode
# ---------------------------------------------------------------------------

def _research_config(budget=12345):
    return SimpleNamespace(agent_deep_research_budget=budget)


def test_research_dispatch_builds_agent_and_maps_success():
    result = make_result(report="deep dive")
    research_agent = MagicMock()
    research_agent.research.return_value = result
    research_cls = MagicMock(return_value=research_agent)
    registry = object()
    llm_adapter = object()

    with patch("src.agent.research.ResearchAgent", research_cls), patch(
        "src.agent.factory.get_tool_registry", return_value=registry
    ), patch("src.agent.llm_adapter.LLMToolAdapter", return_value=llm_adapter):
        adapter = NativeRuntimeAdapter(config=_research_config())
        handle = adapter.execute(
            ExecutionContext(
                mode=ExecutionMode.RESEARCH,
                prompt="why did the sector rally?",
                timeout_seconds=90,
            )
        )

    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.result is result
    research_cls.assert_called_once_with(
        tool_registry=registry,
        llm_adapter=llm_adapter,
        token_budget=12345,
    )
    # The caller passed no callback, but the adapter still supplies a wrapper
    # so research progress is captured on the live handle's event stream.
    research_agent.research.assert_called_once()
    research_call = research_agent.research.call_args
    assert research_call.args == ("why did the sector rally?",)
    assert research_call.kwargs["context"] is None
    assert research_call.kwargs["timeout_seconds"] == 90
    assert callable(research_call.kwargs["progress_callback"])


def test_research_timed_out_maps_to_timed_out_state():
    result = SimpleNamespace(success=False, timed_out=True, error="budget elapsed")
    research_agent = MagicMock()
    research_agent.research.return_value = result

    with patch("src.agent.research.ResearchAgent", return_value=research_agent), patch(
        "src.agent.factory.get_tool_registry", return_value=object()
    ), patch("src.agent.llm_adapter.LLMToolAdapter", return_value=object()):
        adapter = NativeRuntimeAdapter(config=_research_config())
        handle = adapter.execute(
            ExecutionContext(mode=ExecutionMode.RESEARCH, prompt="question")
        )

    assert handle.state is ExecutionState.TIMED_OUT
    assert handle.error == "budget elapsed"


# ---------------------------------------------------------------------------
# assembly seam
# ---------------------------------------------------------------------------

def test_prebuilt_executor_short_circuits_factory():
    executor = FakeExecutor(run_result=make_result())
    adapter = NativeRuntimeAdapter(executor=executor)

    with patch("src.agent.factory.build_agent_executor") as build_mock:
        adapter.execute(ExecutionContext(mode=ExecutionMode.RUN, prompt="task"))

    build_mock.assert_not_called()


def test_lazy_executor_is_built_once_and_reused():
    executor = FakeExecutor(run_result=make_result())
    config = object()

    with patch(
        "src.agent.factory.build_agent_executor", return_value=executor
    ) as build_mock:
        adapter = NativeRuntimeAdapter(config=config, skills=["trend"])
        adapter.execute(ExecutionContext(mode=ExecutionMode.RUN, prompt="one"))
        adapter.execute(ExecutionContext(mode=ExecutionMode.RUN, prompt="two"))

    build_mock.assert_called_once_with(config, skills=["trend"])
    assert len(executor.run_calls) == 2


def test_build_agent_runtime_returns_native_adapter():
    from src.agent.factory import build_agent_runtime

    runtime = build_agent_runtime(config=object())
    assert isinstance(runtime, NativeRuntimeAdapter)
    assert runtime.name == "native"
