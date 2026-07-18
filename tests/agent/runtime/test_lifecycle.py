# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Runtime lifecycle / events / cooperative-cancellation tests (AR-PY-03).

Covers three converging seams:

- ``RuntimeEvent`` / ``RuntimeEventEmitter``: legacy-dict uplift is
  byte-identical after downgrade, sequences are monotonic, the stage
  tracker follows ``stage_start`` / ``stage_done`` and the late-write
  fence drops events after the terminal state (audited, thread-safe).
- ``classify_terminal_state`` / ``ExecutionLifecycle`` / ``UsageRecorder``:
  cancellation wins over every other outcome and usage persistence is
  guarded through a single sink.
- Cooperative cancellation threaded through the shared runner, the
  orchestrator pipeline, the executor and the native adapter: a cancelled
  run terminates as cancelled and never masquerades as a degraded
  pseudo-success or a persisted failure sentinel.
"""

import os
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.orchestrator import AgentOrchestrator, OrchestratorResult
from src.agent.protocols import AgentContext, StageResult, StageStatus
from src.agent.runner import run_agent_loop
from src.agent.runtime.contract import (
    ExecutionContext,
    ExecutionMode,
    ExecutionState,
)
from src.agent.runtime.events import (
    RuntimeEvent,
    RuntimeEventEmitter,
    to_public_sse_event,
)
from src.agent.runtime.lifecycle import (
    ExecutionLifecycle,
    UsageRecorder,
    classify_result_terminal_state,
    classify_terminal_state,
)
from src.agent.runtime.native_adapter import NativeRuntimeAdapter
from src.agent.stream_events import stream_event
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _registry(handler=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echoes the message",
            parameters=[ToolParameter(name="message", type="string", description="Message")],
            handler=handler or (lambda message: {"echo": message}),
        )
    )
    return registry


def _final_response() -> LLMResponse:
    return LLMResponse(
        content="Done.",
        tool_calls=[],
        usage={"total_tokens": 5},
        provider="openai",
        model="openai/gpt-test",
    )


def _tool_call_response() -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[ToolCall(id="c1", name="echo", arguments={"message": "hi"})],
        usage={"total_tokens": 3},
        provider="openai",
        model="openai/gpt-test",
    )


_LEGACY_EVENTS = [
    stream_event("stage_start", stage="technical", message="Starting technical analysis..."),
    stream_event("stage_done", stage="technical", status="completed", duration=0.25),
    stream_event("thinking", step=1, message="正在制定分析路径..."),
    stream_event("tool_start", step=1, tool="get_realtime_quote", display_name="获取实时行情"),
    stream_event(
        "tool_done",
        step=1,
        tool="get_realtime_quote",
        success=True,
        duration=0.1,
        display_name="获取实时行情",
    ),
    stream_event("generating", message="生成最终答案..."),
    stream_event("pipeline_timeout", stage="decision", elapsed=1.1, timeout=1),
    stream_event(
        "pipeline_budget_skipped",
        stage="decision",
        elapsed=6.0,
        timeout=20,
        remaining=5.0,
        minimum=15,
        reason="insufficient_budget",
        message="Skipped decision analysis due to insufficient remaining budget",
    ),
]


# ---------------------------------------------------------------------------
# Events: uplift / downgrade byte-identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("legacy", _LEGACY_EVENTS, ids=lambda e: e["type"])
def test_legacy_uplift_downgrade_is_byte_identical(legacy):
    emitter = RuntimeEventEmitter(execution_id="ex-1")
    runtime_event = emitter.ingest_legacy(legacy)
    assert runtime_event is not None
    assert to_public_sse_event(runtime_event) == legacy


def test_emitter_requires_non_empty_execution_id():
    with pytest.raises(ValueError):
        RuntimeEventEmitter(execution_id="")


def test_sequence_is_monotonic_and_stage_is_tracked():
    emitter = RuntimeEventEmitter(execution_id="ex-2")
    started = emitter.ingest_legacy({"type": "stage_start", "stage": "technical"})
    thinking = emitter.ingest_legacy({"type": "thinking", "step": 1})
    done = emitter.ingest_legacy({"type": "stage_done", "stage": "technical"})
    after = emitter.ingest_legacy({"type": "generating"})

    assert [e.sequence for e in (started, thinking, done, after)] == [0, 1, 2, 3]
    # thinking inherits the open stage; after stage_done the tracker resets.
    assert started.stage == "technical"
    assert thinking.stage == "technical"
    assert done.stage == "technical"
    assert after.stage is None


def test_typed_emit_drops_none_fields():
    emitter = RuntimeEventEmitter(execution_id="ex-3")
    event = emitter.emit("tool_done", stage="technical", tool="echo", message=None)
    assert event is not None
    assert "message" not in event.payload
    assert event.payload["tool"] == "echo"
    assert event.stage == "technical"


def test_runtime_event_payload_is_read_only():
    event = RuntimeEvent(
        event_type="thinking",
        execution_id="ex-4",
        sequence=0,
        timestamp=0.0,
        payload={"step": 1},
    )
    with pytest.raises(TypeError):
        event.payload["step"] = 2


# ---------------------------------------------------------------------------
# Events: late-write fence
# ---------------------------------------------------------------------------


def test_late_write_fence_drops_and_audits_after_terminal():
    flag = {"terminal": False}
    emitter = RuntimeEventEmitter(
        execution_id="ex-5", terminal_check=lambda: flag["terminal"]
    )
    delivered = emitter.ingest_legacy({"type": "thinking", "step": 1})
    assert delivered is not None
    assert emitter.dropped_events == 0

    flag["terminal"] = True
    dropped = emitter.ingest_legacy({"type": "thinking", "step": 2})
    assert dropped is None
    assert emitter.dropped_events == 1


def test_fence_is_thread_safe_under_concurrent_emit():
    flag = {"terminal": False}
    emitter = RuntimeEventEmitter(
        execution_id="ex-6", terminal_check=lambda: flag["terminal"]
    )
    n = 40
    barrier = threading.Barrier(n + 1)
    results = []
    lock = threading.Lock()

    def worker(i):
        barrier.wait()
        event = emitter.ingest_legacy({"type": "thinking", "step": i})
        with lock:
            results.append(event)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    barrier.wait()
    flag["terminal"] = True  # race the flip against the emits
    for t in threads:
        t.join()

    delivered = [r for r in results if r is not None]
    dropped = [r for r in results if r is None]
    # No event is lost or double-counted.
    assert len(delivered) + len(dropped) == n
    assert len(dropped) == emitter.dropped_events
    # Delivered sequences are unique and contiguous from zero.
    assert sorted(e.sequence for e in delivered) == list(range(len(delivered)))


# ---------------------------------------------------------------------------
# classify_terminal_state precedence
# ---------------------------------------------------------------------------


def test_classify_cancellation_wins_over_success_and_timeout():
    assert (
        classify_terminal_state(success=True, cancelled=True, timed_out=True)
        is ExecutionState.CANCELLED
    )
    assert classify_terminal_state(success=True) is ExecutionState.SUCCEEDED
    assert (
        classify_terminal_state(success=False, timed_out=True)
        is ExecutionState.TIMED_OUT
    )
    assert classify_terminal_state(success=False) is ExecutionState.FAILED


def test_classify_result_reads_attributes_through_single_authority():
    """The result-object classifier the entry-point write fences share must
    apply the same cancellation-wins precedence as classify_terminal_state."""

    class _Result:
        def __init__(self, success=False, cancelled=False, timed_out=False):
            self.success = success
            self.cancelled = cancelled
            self.timed_out = timed_out

    # Cancellation wins even when partial success/timeout coexist: a cancelled
    # chat turn must never persist a success assistant message.
    assert (
        classify_result_terminal_state(_Result(success=True, cancelled=True, timed_out=True))
        is ExecutionState.CANCELLED
    )
    assert classify_result_terminal_state(_Result(success=True)) is ExecutionState.SUCCEEDED
    assert classify_result_terminal_state(_Result(timed_out=True)) is ExecutionState.TIMED_OUT
    assert classify_result_terminal_state(_Result()) is ExecutionState.FAILED
    # Missing attributes default to falsey -> FAILED (no crash on partial objects).
    assert classify_result_terminal_state(object()) is ExecutionState.FAILED


# ---------------------------------------------------------------------------
# ExecutionLifecycle
# ---------------------------------------------------------------------------


def _chat_context() -> ExecutionContext:
    return ExecutionContext(
        mode=ExecutionMode.CHAT, prompt="hi", session_id="s-1"
    )


def test_lifecycle_cancelled_check_reflects_request():
    lifecycle = ExecutionLifecycle(_chat_context())
    lifecycle.start()
    assert lifecycle.cancelled_check() is False
    assert lifecycle.request_cancel() is True
    assert lifecycle.cancelled_check() is True


def test_lifecycle_finish_from_result_classifies_and_is_first_wins():
    lifecycle = ExecutionLifecycle(_chat_context())
    lifecycle.start()
    result = SimpleNamespace(success=False, cancelled=True, timed_out=False, error="x")
    assert lifecycle.finish_from_result(result) is ExecutionState.CANCELLED
    assert lifecycle.state is ExecutionState.CANCELLED
    assert lifecycle.is_terminal is True
    # A later fail() cannot overwrite the first terminal transition.
    assert lifecycle.fail("late") is False
    assert lifecycle.state is ExecutionState.CANCELLED


def test_lifecycle_emitter_is_fenced_after_terminal():
    lifecycle = ExecutionLifecycle(_chat_context())
    lifecycle.start()
    live = lifecycle.ingest_progress_event({"type": "thinking", "step": 1})
    assert live is not None
    lifecycle.finish_from_result(SimpleNamespace(success=True))
    fenced = lifecycle.ingest_progress_event({"type": "thinking", "step": 2})
    assert fenced is None
    assert lifecycle.emitter.dropped_events == 1


# ---------------------------------------------------------------------------
# UsageRecorder
# ---------------------------------------------------------------------------


def test_usage_recorder_guards_and_propagates_call_type():
    with patch("src.agent.runtime.lifecycle.persist_llm_usage") as persist:
        recorder = UsageRecorder()
        assert recorder.record({}, "openai/gpt-test") is False
        persist.assert_not_called()

        assert (
            recorder.record({"total_tokens": 5}, "openai/gpt-test", call_type="agent")
            is True
        )
        persist.assert_called_once_with(
            {"total_tokens": 5}, "openai/gpt-test", call_type="agent"
        )


# ---------------------------------------------------------------------------
# Runner cooperative cancellation + usage convergence
# ---------------------------------------------------------------------------


def test_runner_cancel_before_first_step_makes_no_llm_call():
    adapter = MagicMock()
    result = run_agent_loop(
        messages=[{"role": "user", "content": "Analyze"}],
        tool_registry=_registry(),
        llm_adapter=adapter,
        max_steps=3,
        cancelled_check=lambda: True,
    )
    adapter.call_with_tools.assert_not_called()
    assert result.cancelled is True
    assert result.success is False


def test_runner_cancel_after_llm_blocks_tool_dispatch():
    calls = {"tool": 0}

    def _handler(message):
        calls["tool"] += 1
        return {"echo": message}

    flag = {"cancel": False}

    adapter = MagicMock()

    def _call(*_args, **_kwargs):
        flag["cancel"] = True  # cancel arrives after the model call returns
        return _tool_call_response()

    adapter.call_with_tools.side_effect = _call
    messages = [{"role": "user", "content": "Analyze"}]

    result = run_agent_loop(
        messages=messages,
        tool_registry=_registry(_handler),
        llm_adapter=adapter,
        max_steps=3,
        cancelled_check=lambda: flag["cancel"],
    )

    assert result.cancelled is True
    assert calls["tool"] == 0  # tool never dispatched
    # The assistant tool_calls message must not be appended on cancel.
    assert all("tool_calls" not in m for m in messages)


def test_runner_cancel_after_tools_stops_next_step():
    flag = {"cancel": False}

    def _handler(message):
        flag["cancel"] = True  # flip only once the first step's tool ran
        return {"echo": message}

    adapter = MagicMock()
    adapter.call_with_tools.return_value = _tool_call_response()

    result = run_agent_loop(
        messages=[{"role": "user", "content": "Analyze"}],
        tool_registry=_registry(_handler),
        llm_adapter=adapter,
        max_steps=3,
        cancelled_check=lambda: flag["cancel"],
    )

    assert result.cancelled is True
    # Only the first step's LLM call happened; step 2 was cancelled at the top.
    assert adapter.call_with_tools.call_count == 1


def test_runner_uses_injected_usage_recorder():
    class _RecordingRecorder:
        def __init__(self):
            self.calls = []

        def record(self, usage, model, *, call_type="agent"):
            self.calls.append((usage, model, call_type))
            return True

    recorder = _RecordingRecorder()
    adapter = MagicMock()
    adapter.call_with_tools.return_value = _final_response()

    run_agent_loop(
        messages=[{"role": "user", "content": "Analyze"}],
        tool_registry=_registry(),
        llm_adapter=adapter,
        max_steps=1,
        usage_recorder=recorder,
    )

    assert recorder.calls == [({"total_tokens": 5}, "openai/gpt-test", "agent")]


def test_runner_timeout_sets_timed_out_flag():
    adapter = MagicMock()
    with patch(
        "src.agent.runner._remaining_timeout_seconds", return_value=0.0
    ):
        result = run_agent_loop(
            messages=[{"role": "user", "content": "Analyze"}],
            tool_registry=_registry(),
            llm_adapter=adapter,
            max_steps=3,
            max_wall_clock_seconds=30.0,
        )
    adapter.call_with_tools.assert_not_called()
    assert result.timed_out is True
    assert result.cancelled is False
    assert result.success is False


# ---------------------------------------------------------------------------
# Orchestrator cooperative cancellation
# ---------------------------------------------------------------------------


def _orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(
        tool_registry=_registry(),
        llm_adapter=MagicMock(),
        mode="standard",
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
    )


def test_orchestrator_cancel_pre_stage_skips_degraded_synthesis():
    orch = _orchestrator()
    ctx = AgentContext(query="Analyze 600519", stock_code="600519")
    ctx.meta["response_mode"] = "chat"
    agents = [SimpleNamespace(agent_name="technical"), SimpleNamespace(agent_name="decision")]
    events = []
    run_stage = MagicMock()

    with patch.object(orch, "_build_agent_chain", return_value=agents), patch.object(
        orch, "_run_stage_agent", run_stage
    ):
        result = orch._execute_pipeline(
            ctx,
            parse_dashboard=False,
            progress_callback=events.append,
            cancelled_check=lambda: True,
        )

    run_stage.assert_not_called()
    assert events == []
    assert result.cancelled is True
    assert result.success is False
    assert result.dashboard is None


def test_orchestrator_cancel_post_stage_beats_degradation():
    orch = _orchestrator()
    ctx = AgentContext(query="Analyze 600519", stock_code="600519")
    ctx.meta["response_mode"] = "chat"
    agents = [SimpleNamespace(agent_name="technical"), SimpleNamespace(agent_name="decision")]
    ran = []

    def _run_stage(agent, run_ctx, **_kwargs):
        ran.append(agent.agent_name)
        return StageResult(
            stage_name=agent.agent_name,
            status=StageStatus.COMPLETED,
            duration_s=0.25,
            meta={"models_used": [f"mock/{agent.agent_name}"]},
        )

    cancel_states = iter([False, True])

    with patch.object(orch, "_build_agent_chain", return_value=agents), patch.object(
        orch, "_run_stage_agent", side_effect=_run_stage
    ):
        result = orch._execute_pipeline(
            ctx,
            parse_dashboard=False,
            cancelled_check=lambda: next(cancel_states, True),
        )

    assert ran == ["technical"]  # second stage never started
    assert result.cancelled is True
    assert result.success is False


def test_orchestrator_chat_cancel_skips_failure_sentinel():
    orch = _orchestrator()
    conv = MagicMock()

    cancelled = OrchestratorResult(
        success=False, content="", error="Pipeline cancelled", cancelled=True
    )

    with patch(
        "src.agent.orchestrator.resolve_stock_scope",
        return_value=SimpleNamespace(effective_context={}, stock_scope=None),
    ), patch(
        "src.agent.orchestrator.build_visible_chat_history", return_value=[]
    ), patch(
        "src.agent.conversation.conversation_manager", conv
    ), patch.object(
        orch, "_execute_pipeline", return_value=cancelled
    ):
        result = orch.chat("hi", session_id="s-1")

    roles = [call.args[1] for call in conv.add_message.call_args_list]
    assert roles == ["user"]  # only the user turn persisted, no failure sentinel
    assert result.cancelled is True
    assert result.success is False


# ---------------------------------------------------------------------------
# Executor cooperative cancellation
# ---------------------------------------------------------------------------


def test_executor_chat_cancel_skips_sentinel_and_provider_trace():
    from src.agent.executor import AgentExecutor, AgentResult

    executor = AgentExecutor(tool_registry=_registry(), llm_adapter=MagicMock())
    conv = MagicMock()
    cancelled = AgentResult(success=False, content="", error="cancelled", cancelled=True)

    with patch(
        "src.agent.executor.resolve_stock_scope",
        return_value=SimpleNamespace(effective_context={}, stock_scope=None),
    ), patch(
        "src.agent.executor.build_agent_chat_context_bundle",
        return_value=SimpleNamespace(context_messages=[]),
    ), patch(
        "src.agent.conversation.conversation_manager", conv
    ), patch.object(
        executor, "_run_loop", return_value=cancelled
    ), patch.object(
        executor, "_persist_provider_trace"
    ) as persist_trace:
        result = executor.chat("hi", session_id="s-1")

    roles = [call.args[1] for call in conv.add_message.call_args_list]
    assert roles == ["user"]  # no failure sentinel appended
    persist_trace.assert_not_called()
    assert result.cancelled is True


# ---------------------------------------------------------------------------
# Native adapter maps a cancelled result to CANCELLED
# ---------------------------------------------------------------------------


def test_native_adapter_maps_cancelled_result_to_cancelled_state():
    executor = SimpleNamespace(
        chat=lambda message, session_id, progress_callback=None, context=None: SimpleNamespace(
            success=False, cancelled=True, timed_out=False, error="cancelled"
        )
    )
    adapter = NativeRuntimeAdapter(executor=executor)
    handle = adapter.execute(
        ExecutionContext(mode=ExecutionMode.CHAT, prompt="hi", session_id="s-1")
    )
    assert handle.state is ExecutionState.CANCELLED
