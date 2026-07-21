import json
import logging
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.orchestrator import AgentOrchestrator, _StageProgressFence
from src.agent.protocols import (
    AgentContext,
    StageFailureReason,
    StageResult,
    StageStatus,
)
from src.agent.runner import run_agent_loop
from src.agent.runtime.guards import (
    RuntimeGuardPolicy,
    StageFailurePolicy,
    log_runtime_guard_event,
)
from src.agent.runtime_facts import DegradationBoundary
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolRegistry


def _policy(**overrides):
    values = {
        "tool_timeout_seconds": 120.0,
        "max_identical_tool_calls": 3,
        "max_stage_entries": 1,
        "stage_failure_policy": StageFailurePolicy.ISOLATE,
    }
    values.update(overrides)
    return RuntimeGuardPolicy(**values)


def _echo_registry(handler=None):
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a message",
            parameters=[
                ToolParameter(
                    name="message",
                    type="string",
                    description="Message to echo",
                )
            ],
            handler=handler or (lambda message: {"echo": message}),
        )
    )
    return registry


def _guard_events(records):
    events = []
    prefix = "agent_runtime_guard "
    for record in records:
        message = record.getMessage()
        if message.startswith(prefix):
            events.append(json.loads(message[len(prefix):]))
    return events


class _CompletedFuture:
    """Expose a completed result only after one simulated wait timeout."""

    def __init__(self, result):
        self._result = result
        self._wait_attempted = False

    def result(self, timeout=None):
        if timeout is not None and not self._wait_attempted:
            self._wait_attempted = True
            raise TimeoutError
        return self._result

    def cancel(self):
        return False


class _InlineExecutor:
    """Complete submitted work before publishing its future result."""

    def __init__(self, max_workers):
        self.max_workers = max_workers

    def submit(self, callback, *args):
        return _CompletedFuture(callback(*args))

    def shutdown(self, wait=True, cancel_futures=False):
        return None


class _ImmediateFuture:
    """Publish an inline execution result without a caller-side wait timeout."""

    def __init__(self, result):
        self._result = result

    def result(self, timeout=None):
        return self._result

    def cancel(self):
        return False


class _ImmediateExecutor:
    """Run submitted work inline and publish it immediately."""

    def __init__(self, max_workers):
        self.max_workers = max_workers

    def submit(self, callback, *args):
        return _ImmediateFuture(callback(*args))

    def shutdown(self, wait=True, cancel_futures=False):
        return None


def test_runtime_guard_policy_reads_environment(monkeypatch):
    monkeypatch.setenv("AGENT_TOOL_TIMEOUT_S", "45.5")
    monkeypatch.setenv("AGENT_MAX_IDENTICAL_TOOL_CALLS", "4")
    monkeypatch.setenv("AGENT_MAX_STAGE_ENTRIES", "2")
    monkeypatch.setenv("AGENT_STAGE_FAILURE_POLICY", "fail_fast")

    policy = RuntimeGuardPolicy.from_sources()

    assert policy == RuntimeGuardPolicy(
        tool_timeout_seconds=45.5,
        max_identical_tool_calls=4,
        max_stage_entries=2,
        stage_failure_policy=StageFailurePolicy.FAIL_FAST,
    )


def test_structured_guard_strings_are_redacted_and_bounded(caplog):
    unsafe_name = (
        "Bearer super-secret-token "
        "https://user:password@private.example/path "
        + ("x" * 300)
    )

    with caplog.at_level(logging.WARNING):
        log_runtime_guard_event(
            logging.getLogger("test.runtime.guard"),
            "tool_timeout",
            tool=unsafe_name,
        )

    event = _guard_events(caplog.records)[0]
    assert "super-secret-token" not in event["tool"]
    assert "password" not in event["tool"]
    assert "private.example" not in event["tool"]
    assert len(event["tool"]) <= 120


def test_repeated_identical_tool_call_stops_before_extra_dispatch(caplog):
    dispatched = []
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="retry",
            tool_calls=[
                ToolCall(
                    id=f"call-{index}",
                    name="echo",
                    arguments={"message": "same"},
                )
            ],
            provider="test",
        )
        for index in range(3)
    ]

    with caplog.at_level(logging.WARNING):
        result = run_agent_loop(
            messages=[],
            tool_registry=_echo_registry(
                lambda message: dispatched.append(message) or {"echo": message}
            ),
            llm_adapter=adapter,
            max_steps=6,
            runtime_guard_policy=_policy(max_identical_tool_calls=2),
        )

    assert result.success is False
    assert result.failure_reason == StageFailureReason.LOOP_DETECTED
    assert result.total_steps == 3
    assert dispatched == ["same", "same"]
    events = _guard_events(caplog.records)
    assert any(
        event["event"] == "tool_loop_detected"
        and event["observed"] == 3
        and event["limit"] == 2
        for event in events
    )
    assert all("same" not in json.dumps(event) for event in events)


def test_runtime_policy_tool_timeout_is_enforced_and_logged(caplog):
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="use tool",
            tool_calls=[
                ToolCall(id="slow", name="echo", arguments={"message": "slow"})
            ],
            provider="test",
        ),
        LLMResponse(content="done", provider="test"),
    ]

    def _slow_echo(message):
        time.sleep(0.05)
        return {"echo": message}

    with caplog.at_level(logging.WARNING):
        result = run_agent_loop(
            messages=[],
            tool_registry=_echo_registry(_slow_echo),
            llm_adapter=adapter,
            max_steps=3,
            tool_call_timeout_seconds=1.0,
            runtime_guard_policy=_policy(tool_timeout_seconds=0.01),
        )

    assert result.success is True
    assert result.tool_calls_log[0]["timeout"] is True
    events = _guard_events(caplog.records)
    assert any(
        event["event"] == "tool_timeout"
        and event["tool"] == "echo"
        and event["limit_seconds"] == 0.01
        for event in events
    )


def test_tool_completion_claim_wins_before_future_publication(monkeypatch):
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="use tool",
            tool_calls=[
                ToolCall(id="echo", name="echo", arguments={"message": "ready"})
            ],
            provider="test",
        ),
        LLMResponse(content="done", provider="test"),
    ]
    monkeypatch.setattr("src.agent.runner.ThreadPoolExecutor", _InlineExecutor)

    result = run_agent_loop(
        messages=[],
        tool_registry=_echo_registry(),
        llm_adapter=adapter,
        max_steps=3,
        runtime_guard_policy=_policy(tool_timeout_seconds=1.0),
    )

    assert result.success is True
    assert result.tool_calls_log[0]["success"] is True
    assert "timeout" not in result.tool_calls_log[0]


def test_parallel_completion_claims_win_before_batch_publication(monkeypatch):
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="use tools",
            tool_calls=[
                ToolCall(
                    id=f"echo-{index}",
                    name="echo",
                    arguments={"message": f"ready-{index}"},
                )
                for index in range(2)
            ],
            provider="test",
        ),
        LLMResponse(content="done", provider="test"),
    ]

    def _raise_batch_timeout(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr("src.agent.runner.ThreadPoolExecutor", _InlineExecutor)
    monkeypatch.setattr("src.agent.runner.as_completed", _raise_batch_timeout)

    result = run_agent_loop(
        messages=[],
        tool_registry=_echo_registry(),
        llm_adapter=adapter,
        max_steps=3,
        runtime_guard_policy=_policy(tool_timeout_seconds=1.0),
    )

    assert result.success is True
    assert len(result.tool_calls_log) == 2
    assert all(entry["success"] is True for entry in result.tool_calls_log)
    assert all("timeout" not in entry for entry in result.tool_calls_log)


def test_fence_deadline_timeout_is_logged_when_future_publishes(caplog, monkeypatch):
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="use tool",
            tool_calls=[
                ToolCall(id="late", name="echo", arguments={"message": "late"})
            ],
            provider="test",
        ),
        LLMResponse(content="done", provider="test"),
    ]
    monkeypatch.setattr("src.agent.runner.ThreadPoolExecutor", _ImmediateExecutor)

    with caplog.at_level(logging.WARNING), patch(
        "src.agent.runner.time.monotonic",
        side_effect=[0.0, 2.0],
    ):
        result = run_agent_loop(
            messages=[],
            tool_registry=_echo_registry(),
            llm_adapter=adapter,
            max_steps=3,
            runtime_guard_policy=_policy(tool_timeout_seconds=1.0),
        )

    assert result.success is True
    assert result.tool_calls_log[0]["timeout"] is True
    assert result.tool_calls_log[0]["success"] is False
    assert any(
        event["event"] == "tool_timeout"
        and event["tool"] == "echo"
        for event in _guard_events(caplog.records)
    )


def test_parallel_fence_deadline_timeouts_are_logged(caplog, monkeypatch):
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="use tools",
            tool_calls=[
                ToolCall(
                    id=f"late-{index}",
                    name="echo",
                    arguments={"message": f"late-{index}"},
                )
                for index in range(2)
            ],
            provider="test",
        ),
        LLMResponse(content="done", provider="test"),
    ]
    monkeypatch.setattr("src.agent.runner.ThreadPoolExecutor", _ImmediateExecutor)
    monkeypatch.setattr(
        "src.agent.runner.as_completed",
        lambda futures, timeout=None: list(futures),
    )

    with caplog.at_level(logging.WARNING), patch(
        "src.agent.runner.time.monotonic",
        side_effect=[0.0, 2.0, 0.0, 2.0],
    ):
        result = run_agent_loop(
            messages=[],
            tool_registry=_echo_registry(),
            llm_adapter=adapter,
            max_steps=3,
            runtime_guard_policy=_policy(tool_timeout_seconds=1.0),
        )

    assert result.success is True
    assert len(result.tool_calls_log) == 2
    assert all(entry["timeout"] is True for entry in result.tool_calls_log)
    events = _guard_events(caplog.records)
    assert sum(event["event"] == "tool_timeout" for event in events) == 2


def test_timed_out_late_result_cannot_populate_session_cache():
    handler_calls = []

    def _handler(message):
        handler_calls.append(message)
        if len(handler_calls) == 1:
            time.sleep(0.04)
            return {"error": "late failure", "retriable": False}
        return {"echo": message}

    responses = iter(
        [
            LLMResponse(
                content="first",
                tool_calls=[
                    ToolCall(id="first", name="echo", arguments={"message": "same"})
                ],
                provider="test",
            ),
            LLMResponse(
                content="second",
                tool_calls=[
                    ToolCall(id="second", name="echo", arguments={"message": "same"})
                ],
                provider="test",
            ),
            LLMResponse(content="done", provider="test"),
        ]
    )
    adapter = MagicMock()

    def _next_response(*_args, **_kwargs):
        response = next(responses)
        if response.content == "second":
            time.sleep(0.06)
        return response

    adapter.call_with_tools.side_effect = _next_response

    result = run_agent_loop(
        messages=[],
        tool_registry=_echo_registry(_handler),
        llm_adapter=adapter,
        max_steps=4,
        runtime_guard_policy=_policy(tool_timeout_seconds=0.01),
    )

    assert result.success is True
    assert handler_calls == ["same", "same"]
    assert result.tool_calls_log[0]["timeout"] is True
    assert result.tool_calls_log[1]["success"] is True
    assert result.tool_calls_log[1]["cached"] is False


def test_full_run_timeout_emits_structured_guard_event(caplog):
    with caplog.at_level(logging.WARNING), patch(
        "src.agent.runner._remaining_timeout_seconds",
        return_value=0.0,
    ):
        result = run_agent_loop(
            messages=[],
            tool_registry=_echo_registry(),
            llm_adapter=MagicMock(),
            max_steps=2,
            max_wall_clock_seconds=1.0,
            runtime_guard_policy=_policy(),
        )

    assert result.timed_out is True
    assert any(
        event["event"] == "run_timeout"
        and event["scope"] == "agent_loop"
        for event in _guard_events(caplog.records)
    )


def test_stage_progress_close_orders_callbacks_before_terminal_events():
    fence = _StageProgressFence()
    callback_entered = threading.Event()
    release_callback = threading.Event()
    close_finished = threading.Event()
    delivered = []

    def _callback(event):
        callback_entered.set()
        release_callback.wait(timeout=1)
        delivered.append(event)

    emitter = threading.Thread(
        target=fence.emit,
        args=(_callback, {"event": "before_timeout"}),
    )
    emitter.start()
    assert callback_entered.wait(timeout=1)

    closer = threading.Thread(
        target=lambda: (fence.close(), close_finished.set()),
    )
    closer.start()
    assert close_finished.wait(timeout=0.01) is False

    release_callback.set()
    emitter.join(timeout=1)
    closer.join(timeout=1)
    assert close_finished.is_set()

    fence.emit(_callback, {"event": "after_timeout"})
    assert delivered == [{"event": "before_timeout"}]


def test_full_run_deadline_wins_over_critical_stage_timeout(caplog):
    orchestrator = AgentOrchestrator(
        tool_registry=_echo_registry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(agent_orchestrator_timeout_s=1),
        runtime_guard_policy=_policy(),
    )
    stage_finished = threading.Event()

    def _slow_stage(agent, _ctx, **_kwargs):
        time.sleep(0.05)
        stage_finished.set()
        return StageResult(
            stage_name=agent.agent_name,
            status=StageStatus.COMPLETED,
        )

    with caplog.at_level(logging.WARNING), patch.object(
        orchestrator,
        "_get_timeout_seconds",
        return_value=0.01,
    ), patch.object(
        orchestrator,
        "_build_agent_chain",
        return_value=[SimpleNamespace(agent_name="technical")],
    ), patch.object(orchestrator, "_run_stage_agent", side_effect=_slow_stage):
        result = orchestrator._execute_pipeline(
            AgentContext(query="test"),
            parse_dashboard=False,
        )

    assert result.timed_out is True
    assert "Pipeline timed out" in result.error
    events = _guard_events(caplog.records)
    assert any(
        event["event"] == "stage_timeout"
        and event["stage"] == "technical"
        for event in events
    )
    assert any(
        event["event"] == "run_timeout"
        and event["scope"] == "orchestrator"
        and event["stage"] == "technical"
        for event in events
    )
    assert not any(event["event"] == "stage_failure_fail_fast" for event in events)
    assert result.runtime_facts.degraded_events[0].stage == "technical"
    assert (
        result.runtime_facts.degraded_events[0].reason
        == StageFailureReason.TIMEOUT
    )
    assert stage_finished.wait(timeout=1)


def test_uncaught_noncritical_stage_exception_isolated_and_pipeline_continues(caplog):
    orchestrator = AgentOrchestrator(
        tool_registry=_echo_registry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
        runtime_guard_policy=_policy(),
    )
    ctx = AgentContext(query="test")
    ctx.meta["response_mode"] = "chat"
    agents = [
        SimpleNamespace(agent_name="technical"),
        SimpleNamespace(agent_name="intel"),
        SimpleNamespace(agent_name="decision"),
    ]
    calls = []

    def _run_stage(agent, _ctx, **_kwargs):
        calls.append(agent.agent_name)
        if agent.agent_name == "intel":
            raise RuntimeError("provider payload must stay private")
        return StageResult(
            stage_name=agent.agent_name,
            status=StageStatus.COMPLETED,
            meta={"raw_text": "done" if agent.agent_name == "decision" else ""},
        )

    with caplog.at_level(logging.WARNING), patch.object(
        orchestrator,
        "_build_agent_chain",
        return_value=agents,
    ), patch.object(orchestrator, "_run_stage_agent", side_effect=_run_stage):
        result = orchestrator._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success is True
    assert result.content == "done"
    assert calls == ["technical", "intel", "decision"]
    assert result.stats.failed_stages == 1
    assert result.runtime_facts.degraded_events[0].stage == "intel"
    assert result.runtime_facts.degraded_events[0].reason == StageFailureReason.STAGE_FAILURE
    events = _guard_events(caplog.records)
    assert any(
        event["event"] == "stage_failure_isolated"
        and event["stage"] == "intel"
        for event in events
    )
    assert all("provider payload" not in json.dumps(event) for event in events)


def test_stage_timeout_isolates_late_context_and_continues(caplog):
    orchestrator = AgentOrchestrator(
        tool_registry=_echo_registry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(
            agent_orchestrator_timeout_s=0,
            agent_intel_agent_timeout_s=0.01,
        ),
        runtime_guard_policy=_policy(),
    )
    ctx = AgentContext(query="test")
    ctx.meta["response_mode"] = "chat"
    agents = [
        SimpleNamespace(agent_name="intel"),
        SimpleNamespace(agent_name="decision"),
    ]
    calls = []

    def _run_stage(agent, run_ctx, **_kwargs):
        calls.append(agent.agent_name)
        if agent.agent_name == "intel":
            run_ctx.set_data("partial_intel", "must not commit")
            time.sleep(0.05)
            run_ctx.set_data("late_intel", "must not commit")
            return StageResult(
                stage_name="intel",
                status=StageStatus.COMPLETED,
            )
        return StageResult(
            stage_name="decision",
            status=StageStatus.COMPLETED,
            meta={"raw_text": "done"},
        )

    with caplog.at_level(logging.WARNING), patch.object(
        orchestrator,
        "_build_agent_chain",
        return_value=agents,
    ), patch.object(orchestrator, "_run_stage_agent", side_effect=_run_stage):
        result = orchestrator._execute_pipeline(ctx, parse_dashboard=False)

    time.sleep(0.06)
    assert result.success is True
    assert result.content == "done"
    assert calls == ["intel", "decision"]
    assert "partial_intel" not in ctx.data
    assert "late_intel" not in ctx.data
    assert result.stats.stage_results[0].failure_reason == StageFailureReason.TIMEOUT
    assert any(
        event["event"] == "stage_timeout"
        and event["stage"] == "intel"
        and event["limit_seconds"] == 0.01
        for event in _guard_events(caplog.records)
    )


def test_fail_fast_policy_stops_after_noncritical_stage_exception():
    orchestrator = AgentOrchestrator(
        tool_registry=_echo_registry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
        runtime_guard_policy=_policy(
            stage_failure_policy=StageFailurePolicy.FAIL_FAST,
        ),
    )
    agents = [
        SimpleNamespace(agent_name="technical"),
        SimpleNamespace(agent_name="intel"),
        SimpleNamespace(agent_name="decision"),
    ]
    calls = []

    def _run_stage(agent, _ctx, **_kwargs):
        calls.append(agent.agent_name)
        if agent.agent_name == "intel":
            raise RuntimeError("failure")
        return StageResult(
            stage_name=agent.agent_name,
            status=StageStatus.COMPLETED,
        )

    with patch.object(
        orchestrator,
        "_build_agent_chain",
        return_value=agents,
    ), patch.object(orchestrator, "_run_stage_agent", side_effect=_run_stage):
        result = orchestrator._execute_pipeline(
            AgentContext(query="test"),
            parse_dashboard=False,
        )

    assert result.success is False
    assert result.error == "Stage 'intel' failed"
    assert calls == ["technical", "intel"]


def test_decision_preparation_exception_becomes_a_failed_stage():
    orchestrator = AgentOrchestrator(
        tool_registry=_echo_registry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
        runtime_guard_policy=_policy(),
    )
    agents = [SimpleNamespace(agent_name="decision")]

    with patch.object(
        orchestrator,
        "_build_agent_chain",
        return_value=agents,
    ), patch.object(
        orchestrator,
        "_run_strategy_engine",
        side_effect=RuntimeError("invalid strategy state"),
    ), patch.object(orchestrator, "_run_stage_agent") as run_stage:
        result = orchestrator._execute_pipeline(
            AgentContext(query="test"),
            parse_dashboard=False,
        )

    assert result.success is False
    assert result.error == "Stage 'decision' failed"
    assert result.stats.stage_results[0].failure_reason == StageFailureReason.STAGE_FAILURE
    run_stage.assert_not_called()


def test_decision_preparation_timeout_cannot_commit_late_state(caplog):
    orchestrator = AgentOrchestrator(
        tool_registry=_echo_registry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(
            agent_orchestrator_timeout_s=0,
            agent_decision_agent_timeout_s=0.01,
        ),
        runtime_guard_policy=_policy(),
    )
    ctx = AgentContext(query="test")

    def _slow_preparation(staged_ctx):
        time.sleep(0.05)
        staged_ctx.set_data("late_decision", "must not commit")

    with caplog.at_level(logging.WARNING), patch.object(
        orchestrator,
        "_build_agent_chain",
        return_value=[SimpleNamespace(agent_name="decision")],
    ), patch.object(
        orchestrator,
        "_run_strategy_engine",
        side_effect=_slow_preparation,
    ), patch.object(orchestrator, "_run_stage_agent") as run_stage:
        result = orchestrator._execute_pipeline(ctx, parse_dashboard=False)

    time.sleep(0.06)
    assert result.success is False
    assert result.error == "Stage 'decision' failed"
    assert "late_decision" not in ctx.data
    assert result.stats.stage_results[0].failure_reason == StageFailureReason.TIMEOUT
    assert any(
        event["event"] == "stage_timeout"
        and event["stage"] == "decision"
        and event["limit_seconds"] == 0.01
        for event in _guard_events(caplog.records)
    )
    run_stage.assert_not_called()


def test_stage_reentry_guard_stops_duplicate_before_execution(caplog):
    orchestrator = AgentOrchestrator(
        tool_registry=_echo_registry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
        runtime_guard_policy=_policy(max_stage_entries=1),
    )
    agents = [
        SimpleNamespace(agent_name="intel"),
        SimpleNamespace(agent_name="intel"),
        SimpleNamespace(agent_name="decision"),
    ]
    calls = []

    def _run_stage(agent, _ctx, **_kwargs):
        calls.append(agent.agent_name)
        return StageResult(
            stage_name=agent.agent_name,
            status=StageStatus.COMPLETED,
        )

    with caplog.at_level(logging.WARNING), patch.object(
        orchestrator,
        "_build_agent_chain",
        return_value=agents,
    ), patch.object(orchestrator, "_run_stage_agent", side_effect=_run_stage):
        result = orchestrator._execute_pipeline(
            AgentContext(query="test"),
            parse_dashboard=False,
        )

    assert result.success is False
    assert result.error == "Stage 'intel' exceeded the re-entry limit"
    assert calls == ["intel"]
    assert result.stats.stage_results[-1].failure_reason == StageFailureReason.LOOP_DETECTED
    assert result.runtime_facts.degraded_events[0].boundary == DegradationBoundary.BEFORE_STAGE
    assert any(
        event["event"] == "stage_loop_detected"
        and event["stage"] == "intel"
        and event["observed"] == 2
        for event in _guard_events(caplog.records)
    )
