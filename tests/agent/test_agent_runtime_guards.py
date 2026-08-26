import json
import logging
import sys
import threading
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
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
from src.agent.runner import _execute_tools, run_agent_loop
from src.agent.runtime.guards import (
    RuntimeGuardPolicy,
    StageFailurePolicy,
    log_runtime_guard_event,
)
from src.agent.runtime import ExecutionContext, ExecutionLifecycle, ExecutionMode
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.runtime_facts import DegradationBoundary
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)
from tests.security_audit_test_utils import SecurityAuditRecorderStub


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
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["analysis_context:read"],
            ),
        )
    )
    return registry


class _ControllableClock:
    """Monotonic test clock for pipeline `time.time()` lookups.

    Isolated-stage `Future.result(timeout=...)` still uses the real wall clock.
    """

    def __init__(self, start: float = 1_000_000.0) -> None:
        self._now = start
        self._lock = threading.Lock()

    def time(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._now += seconds


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
            raise FuturesTimeoutError
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


def test_parallel_timeout_uses_the_shared_session_deadline():
    def _deadline_crossing_echo(message):
        if message == "slow":
            time.sleep(0.2)
        return {"echo": message}

    deadline = time.monotonic() + 0.1
    session = BoundToolSession(
        _echo_registry(_deadline_crossing_echo),
        execution_id="shared-parallel-deadline",
        allowed_tools=["echo"],
        granted_permissions=["analysis_context:read"],
        deadline_monotonic=deadline,
        security_audit=SecurityAuditRecorderStub(),
    )
    tool_calls_log = []

    results = _execute_tools(
        [
            ToolCall(id="fast", name="echo", arguments={"message": "fast"}),
            ToolCall(id="slow", name="echo", arguments={"message": "slow"}),
        ],
        session,
        step=1,
        progress_callback=None,
        tool_calls_log=tool_calls_log,
        tool_wait_timeout_seconds=1.0,
    )

    slow_log = next(
        entry
        for entry in tool_calls_log
        if entry["arguments"]["message"] == "slow"
    )
    slow_result = next(result for result in results if result["tc"].id == "slow")
    assert slow_log["timeout"] is True
    assert slow_log["success"] is False
    assert json.loads(slow_result["result_str"])["timeout"] is True


def test_timeout_during_attempt_audit_prevents_late_handler_dispatch():
    attempt_entered = threading.Event()
    release_attempt = threading.Event()
    completion_recorded = threading.Event()
    caller_returned = threading.Event()
    handler_calls = []

    class _BlockingAttemptAudit(SecurityAuditRecorderStub):
        def record_attempt(self, **fields):
            attempt_entered.set()
            assert release_attempt.wait(timeout=2)
            super().record_attempt(**fields)

        def record_completion(self, **fields):
            super().record_completion(**fields)
            completion_recorded.set()

    registry = _echo_registry(
        lambda message: handler_calls.append(message) or {"echo": message}
    )
    session = BoundToolSession(
        registry,
        execution_id="attempt-audit-timeout",
        allowed_tools=["echo"],
        granted_permissions=["analysis_context:read"],
        security_audit=_BlockingAttemptAudit(),
    )
    tool_calls_log = []
    result_holder = {}

    def _run_tools():
        result_holder["results"] = _execute_tools(
            [
                ToolCall(
                    id="audit-blocked",
                    name="echo",
                    arguments={"message": "must-not-run"},
                )
            ],
            session,
            step=1,
            progress_callback=None,
            tool_calls_log=tool_calls_log,
            tool_wait_timeout_seconds=0.01,
        )
        caller_returned.set()

    caller = threading.Thread(target=_run_tools)
    caller.start()
    assert attempt_entered.wait(timeout=1)
    assert caller_returned.wait(timeout=1)

    assert handler_calls == []
    assert session.dispatched_calls == 0
    assert tool_calls_log[0]["timeout"] is True

    release_attempt.set()
    assert completion_recorded.wait(timeout=1)
    caller.join(timeout=1)

    assert handler_calls == []
    assert session.dispatched_calls == 0
    assert session.dropped_results == 1
    assert json.loads(result_holder["results"][0]["result_str"])["timeout"] is True


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


def test_cached_completion_claim_wins_before_future_publication(monkeypatch):
    handler_calls = []

    def _permanent_failure(message):
        handler_calls.append(message)
        return {"error": "permanent", "retriable": False}

    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
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
    monkeypatch.setattr("src.agent.runner.ThreadPoolExecutor", _InlineExecutor)

    result = run_agent_loop(
        messages=[],
        tool_registry=_echo_registry(_permanent_failure),
        llm_adapter=adapter,
        max_steps=4,
        runtime_guard_policy=_policy(tool_timeout_seconds=1.0),
    )

    assert result.success is True
    assert handler_calls == ["same"]
    assert result.tool_calls_log[0]["cached"] is False
    assert result.tool_calls_log[1]["cached"] is True
    assert "timeout" not in result.tool_calls_log[1]


def test_rejected_completion_claim_wins_before_future_publication(monkeypatch):
    handler_calls = []
    registry = _echo_registry(
        lambda message: handler_calls.append(message) or {"echo": message}
    )
    session = BoundToolSession(
        registry,
        execution_id="rejected-completion",
        allowed_tools=["echo"],
        granted_permissions=["analysis_context:read"],
        max_tool_calls=0,
        security_audit=SecurityAuditRecorderStub(),
    )
    tool_calls_log = []
    monkeypatch.setattr("src.agent.runner.ThreadPoolExecutor", _InlineExecutor)

    results = _execute_tools(
        [ToolCall(id="rejected", name="echo", arguments={"message": "blocked"})],
        session,
        step=1,
        progress_callback=None,
        tool_calls_log=tool_calls_log,
        tool_wait_timeout_seconds=1.0,
    )

    assert handler_calls == []
    assert len(results) == 1
    assert tool_calls_log[0]["success"] is False
    assert "timeout" not in tool_calls_log[0]
    assert "budget_exhausted" in results[0]["result_str"]


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
        raise FuturesTimeoutError

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
        side_effect=[
            0.0,
            0.1,
            0.1,
            0.1,
            0.1,
            0.1,
            0.1,
            0.1,
            2.0,
        ],
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

    scripted = iter(
        [
            0.0,
            0.1,
            0.1,
            0.1,
            0.1,
            0.1,
            0.1,
            0.1,
            2.0,
            0.0,
            0.1,
            0.1,
            0.1,
            0.1,
            0.1,
            0.1,
            0.1,
            2.0,
        ]
    )

    def _monotonic():
        try:
            return next(scripted)
        except StopIteration:
            return 100.0

    with caplog.at_level(logging.WARNING), patch(
        "src.agent.runner.time.monotonic",
        side_effect=_monotonic,
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
    first_handler_started = threading.Event()
    release_first_handler = threading.Event()
    late_completion_recorded = threading.Event()

    class _LateCompletionAudit(SecurityAuditRecorderStub):
        def record_completion(self, **fields):
            super().record_completion(**fields)
            if fields.get("reason_code") == "late_result_dropped":
                late_completion_recorded.set()

    def _handler(message):
        handler_calls.append(message)
        if len(handler_calls) == 1:
            first_handler_started.set()
            assert release_first_handler.wait(timeout=2)
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
            assert first_handler_started.wait(timeout=1)
            release_first_handler.set()
            # Wait for the detached session worker to cross its completion
            # fence, attempt any cache write, and persist the late-drop audit.
            assert late_completion_recorded.wait(timeout=1)
        return response

    adapter.call_with_tools.side_effect = _next_response

    with patch(
        "src.agent.runner._get_security_audit_service",
        return_value=_LateCompletionAudit(),
    ):
        result = run_agent_loop(
            messages=[],
            tool_registry=_echo_registry(_handler),
            llm_adapter=adapter,
            max_steps=4,
            runtime_guard_policy=_policy(tool_timeout_seconds=0.1),
        )

    assert result.success is True
    assert late_completion_recorded.is_set()
    assert handler_calls == ["same", "same"]
    assert result.tool_calls_log[0]["timeout"] is True
    assert result.tool_calls_log[1]["success"] is True
    assert result.tool_calls_log[1]["cached"] is False


def test_unknown_tool_name_is_canonicalized_across_runner_traces(caplog):
    canary = "prompt_secret_tool_canary_987654321"
    progress_events = []
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(id="unknown", name=canary, arguments={}),
            ],
            provider="test",
        ),
        LLMResponse(content="done", provider="test"),
    ]

    with caplog.at_level(logging.INFO), patch(
        "src.agent.runner._get_security_audit_service",
        return_value=SecurityAuditRecorderStub(),
    ):
        result = run_agent_loop(
            messages=[],
            tool_registry=_echo_registry(),
            llm_adapter=adapter,
            max_steps=3,
            progress_callback=progress_events.append,
        )

    second_model_input = adapter.call_with_tools.call_args_list[1].args[0]
    visible_trace = str({
        "logs": [record.getMessage() for record in caplog.records],
        "progress": progress_events,
        "tool_calls_log": result.tool_calls_log,
        "messages": result.messages,
        "second_model_input": second_model_input,
    })
    assert result.success is True
    assert canary not in visible_trace
    assert "unrecognized" in visible_trace


def test_native_descriptors_and_execution_share_one_frozen_binding():
    original_calls = []
    replacement_calls = []

    class _ReplacingRegistry(ToolRegistry):
        def __init__(self):
            super().__init__()
            self._replaced = False

        def list_names(self):
            names = super().list_names()
            if not self._replaced:
                self._replaced = True
                self.register(
                    ToolDefinition(
                        name="echo",
                        description="Replacement integer echo.",
                        parameters=[
                            ToolParameter(
                                name="value",
                                type="integer",
                                description="Value",
                            ),
                        ],
                        handler=lambda value: replacement_calls.append(value)
                        or {"value": value},
                        policy=ToolPolicy.declared(
                            read_only=True,
                            permissions=["analysis_context:read"],
                        ),
                    )
                )
            return names

        def to_openai_tools(self):
            raise AssertionError("live registry descriptors must not be used")

    registry = _ReplacingRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Original string echo.",
            parameters=[
                ToolParameter(
                    name="message",
                    type="string",
                    description="Message",
                ),
            ],
            handler=lambda message: original_calls.append(message),
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["analysis_context:read"],
            ),
        )
    )
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(id="replacement", name="echo", arguments={"value": 7}),
            ],
            provider="test",
        ),
        LLMResponse(content="done", provider="test"),
    ]

    with patch(
        "src.agent.runner._get_security_audit_service",
        return_value=SecurityAuditRecorderStub(),
    ):
        result = run_agent_loop(
            messages=[],
            tool_registry=registry,
            llm_adapter=adapter,
            max_steps=3,
        )

    declarations = adapter.call_with_tools.call_args_list[0].args[1]
    assert declarations[0]["function"]["parameters"]["properties"] == {
        "value": {
            "type": "integer",
            "description": "Value",
        },
    }
    assert result.success is True
    assert original_calls == []
    assert replacement_calls == [7]


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
    run_timeout_s = 0.01
    clock = _ControllableClock()
    isolated_stage = orchestrator._execute_isolated_stage

    def _slow_stage(agent, _ctx, **_kwargs):
        # Exceed the isolated-stage Future timeout (remaining run budget) so
        # the in-flight critical stage is recorded as stage_timeout.
        time.sleep(run_timeout_s + 0.04)
        stage_finished.set()
        return StageResult(
            stage_name=agent.agent_name,
            status=StageStatus.COMPLETED,
        )

    def _isolated_stage_then_consume_run_budget(*args, **kwargs):
        try:
            return isolated_stage(*args, **kwargs)
        finally:
            # Pipeline elapsed time is independent of setup cost. Consume the
            # run budget only after the stage attempt so before_stage cannot
            # expire on a slow runner before technical is entered.
            clock.advance(run_timeout_s)

    with caplog.at_level(logging.WARNING), patch(
        "src.agent.orchestrator.time.time",
        clock.time,
    ), patch.object(
        orchestrator,
        "_get_timeout_seconds",
        return_value=run_timeout_s,
    ), patch.object(
        orchestrator,
        "_build_agent_chain",
        return_value=[SimpleNamespace(agent_name="technical")],
    ), patch.object(
        orchestrator,
        "_execute_isolated_stage",
        side_effect=_isolated_stage_then_consume_run_budget,
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


def test_stream_lifecycle_cancel_probe_survives_stage_context_isolation():
    orchestrator = AgentOrchestrator(
        tool_registry=_echo_registry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
        runtime_guard_policy=_policy(),
    )
    lifecycle = ExecutionLifecycle(
        ExecutionContext(
            mode=ExecutionMode.CHAT,
            prompt="test",
            session_id="stream-isolation-test",
            request_context={"nested": {"value": 1}},
        )
    )
    ctx = AgentContext(query="test")
    ctx.meta["response_mode"] = "chat"
    cancelled_probe = lifecycle.cancelled_check
    ctx.meta["_approval_cancelled_check"] = cancelled_probe
    agent = SimpleNamespace(agent_name="technical")

    with patch.object(
        orchestrator,
        "_run_stage_agent",
        return_value=StageResult(
            stage_name="technical",
            status=StageStatus.COMPLETED,
        ),
    ):
        result, staged_ctx = orchestrator._execute_isolated_stage(
            agent,
            ctx,
            stage_name="technical",
            progress_callback=None,
            timeout_seconds=None,
            cancelled_check=cancelled_probe,
        )

    assert result.status is StageStatus.COMPLETED
    assert staged_ctx is not ctx
    assert staged_ctx.meta["_approval_cancelled_check"] is cancelled_probe


def test_pipeline_isolates_stream_lifecycle_cancel_probe_without_mappingproxy_error():
    orchestrator = AgentOrchestrator(
        tool_registry=_echo_registry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
        runtime_guard_policy=_policy(),
    )
    lifecycle = ExecutionLifecycle(
        ExecutionContext(
            mode=ExecutionMode.CHAT,
            prompt="test",
            session_id="stream-pipeline-test",
            request_context={"nested": {"value": 1}},
        )
    )
    ctx = AgentContext(query="test")
    ctx.meta["response_mode"] = "chat"
    cancelled_probe = lifecycle.cancelled_check
    agents = [
        SimpleNamespace(agent_name="technical"),
        SimpleNamespace(agent_name="decision"),
    ]

    def _run_stage(agent, _ctx, **_kwargs):
        return StageResult(
            stage_name=agent.agent_name,
            status=StageStatus.COMPLETED,
            meta={"raw_text": "done" if agent.agent_name == "decision" else ""},
        )

    with patch.object(
        orchestrator,
        "_build_agent_chain",
        return_value=agents,
    ), patch.object(orchestrator, "_run_stage_agent", side_effect=_run_stage):
        result = orchestrator._execute_pipeline(
            ctx,
            parse_dashboard=False,
            cancelled_check=cancelled_probe,
        )

    assert result.success is True
    assert result.content == "done"
    assert ctx.meta["_approval_cancelled_check"] is cancelled_probe


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
