import json
import logging
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import (
    AgentContext,
    StageFailureReason,
    StageResult,
    StageStatus,
)
from src.agent.runner import run_agent_loop
from src.agent.runtime.guards import RuntimeGuardPolicy, StageFailurePolicy
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
