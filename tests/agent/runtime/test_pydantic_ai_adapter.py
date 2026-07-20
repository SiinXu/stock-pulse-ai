# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the experimental PydanticAI runtime adapter (AR-PY-04, 方案 B).

Two contracts are asserted:

- **Optional-dependency contract**: when ``pydantic-ai-slim`` is absent, the
  availability probe reports False and using the runtime raises one explicit
  ``PydanticAIRuntimeUnavailableError`` — never a silent fallback. Native is
  unaffected (this module never touches the default path).
- **POC functional contract**: driven by a deterministic fake PydanticAI
  ``Model`` (no network), a Single Agent run terminates via the shared
  ``classify_terminal_state`` and maps PydanticAI output into a StockPulse
  ``AgentResult``.
"""

import asyncio
import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.runtime.contract import ExecutionContext, ExecutionMode, ExecutionState
from src.agent.runtime.pydantic_ai_adapter import (
    PydanticAIRuntimeAdapter,
    PydanticAIRuntimeUnavailableError,
    _to_stockpulse_messages,
    is_pydantic_ai_available,
)
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)

from tests.agent.runtime._pydantic_ai_dependency import require_pydantic_ai

pydantic_ai = require_pydantic_ai()


def _fake_model(output_text: str):
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models import Model
    from pydantic_ai.usage import RequestUsage

    class _FakeModel(Model):
        def __init__(self):
            self.calls = []

        @property
        def model_name(self) -> str:
            return "fake-model"

        @property
        def system(self) -> str:
            return "stockpulse"

        async def request(self, messages, model_settings, model_request_parameters):
            self.calls.append(list(messages))
            return ModelResponse(
                parts=[TextPart(content=output_text)],
                usage=RequestUsage(input_tokens=4, output_tokens=6),
                model_name=self.model_name,
            )

    return _FakeModel()


def _tool_then_final_model(tool_name: str, tool_args: dict, final_text: str):
    """Fake Model: emit one tool call, then a final text answer."""
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models import Model
    from pydantic_ai.usage import RequestUsage

    class _ToolCallingModel(Model):
        def __init__(self):
            self.step = 0

        @property
        def model_name(self) -> str:
            return "tool-fake"

        @property
        def system(self) -> str:
            return "stockpulse"

        async def request(self, messages, model_settings, model_request_parameters):
            self.step += 1
            if self.step == 1:
                return ModelResponse(
                    parts=[ToolCallPart(tool_name=tool_name, args=tool_args, tool_call_id="c1")],
                    usage=RequestUsage(input_tokens=2, output_tokens=1),
                    model_name=self.model_name,
                )
            return ModelResponse(
                parts=[TextPart(content=final_text)],
                usage=RequestUsage(input_tokens=2, output_tokens=1),
                model_name=self.model_name,
            )

    return _ToolCallingModel()


def _blocking_model(started: threading.Event, release: threading.Event, output_text: str):
    """Fake Model that stays inside one request until the test releases it."""
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models import Model
    from pydantic_ai.usage import RequestUsage

    class _BlockingModel(Model):
        @property
        def model_name(self) -> str:
            return "blocking-fake"

        @property
        def system(self) -> str:
            return "stockpulse"

        async def request(self, messages, model_settings, model_request_parameters):
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.001)
            return ModelResponse(
                parts=[TextPart(content=output_text)],
                usage=RequestUsage(input_tokens=1, output_tokens=1),
                model_name=self.model_name,
            )

    return _BlockingModel()


def _tool_then_blocking_final_model(
    tool_name: str,
    tool_args: dict,
    final_text: str,
    waiting: threading.Event,
    release: threading.Event,
):
    """Emit one tool call, then block the final model turn."""
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models import Model
    from pydantic_ai.usage import RequestUsage

    class _ToolThenBlockingModel(Model):
        def __init__(self):
            self.step = 0

        @property
        def model_name(self) -> str:
            return "tool-blocking-fake"

        @property
        def system(self) -> str:
            return "stockpulse"

        async def request(self, messages, model_settings, model_request_parameters):
            self.step += 1
            if self.step == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name=tool_name,
                            args=tool_args,
                            tool_call_id="c1",
                        )
                    ],
                    usage=RequestUsage(input_tokens=1, output_tokens=1),
                    model_name=self.model_name,
                )
            waiting.set()
            while not release.is_set():
                await asyncio.sleep(0.001)
            return ModelResponse(
                parts=[TextPart(content=final_text)],
                usage=RequestUsage(input_tokens=1, output_tokens=1),
                model_name=self.model_name,
            )

    return _ToolThenBlockingModel()


def _echo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echoes the message",
            parameters=[ToolParameter(name="message", type="string", description="Message")],
            handler=lambda message: {"echo": message},
            policy=ToolPolicy.declared(read_only=True, side_effects=[], permissions=["test:read"]),
        )
    )
    return registry


def _run_context(prompt: str) -> ExecutionContext:
    return ExecutionContext(mode=ExecutionMode.RUN, prompt=prompt)


# ---------------------------------------------------------------------------
# Optional-dependency contract
# ---------------------------------------------------------------------------


def test_availability_probe_true_when_installed():
    assert is_pydantic_ai_available() is True


def test_availability_probe_false_when_absent():
    with patch("importlib.util.find_spec", return_value=None):
        assert is_pydantic_ai_available() is False


def test_execute_raises_explicit_error_when_dependency_absent():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model('{"signal": "buy"}'))
    # Simulate the dependency being uninstalled: a None entry in sys.modules
    # makes ``import pydantic_ai`` raise ImportError.
    with patch.dict(sys.modules, {"pydantic_ai": None}):
        with pytest.raises(PydanticAIRuntimeUnavailableError):
            adapter.execute(_run_context("Analyze 600519"))


def test_constructor_requires_model_or_adapter():
    with pytest.raises(ValueError):
        PydanticAIRuntimeAdapter()


# ---------------------------------------------------------------------------
# POC functional contract
# ---------------------------------------------------------------------------


def test_run_maps_dashboard_output_to_succeeded():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model('{"signal": "buy", "confidence": 0.8}'))
    handle = adapter.execute(_run_context("Analyze 600519"))

    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.is_terminal is True
    result = handle.result
    assert result.success is True
    assert result.dashboard == {"signal": "buy", "confidence": 0.8}
    assert result.total_tokens == 10
    assert result.model == "fake-model"


def test_run_without_dashboard_json_fails_closed():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model("no json here"))
    handle = adapter.execute(_run_context("Analyze 600519"))

    assert handle.state is ExecutionState.FAILED
    assert handle.result.success is False
    assert handle.result.dashboard is None
    assert "dashboard" in (handle.result.error or "").lower()


def test_execute_reraises_worker_exception():
    from pydantic_ai.models import Model

    exception = RuntimeError("pydantic runtime boom")

    class _RaisingModel(Model):
        @property
        def model_name(self) -> str:
            return "raising-fake"

        @property
        def system(self) -> str:
            return "stockpulse"

        async def request(self, messages, model_settings, model_request_parameters):
            raise exception

    adapter = PydanticAIRuntimeAdapter(model=_RaisingModel())

    with pytest.raises(RuntimeError, match="pydantic runtime boom") as excinfo:
        adapter.execute(_run_context("Analyze 600519"))

    assert excinfo.value is exception


def test_start_returns_live_running_handle_then_completes():
    started = threading.Event()
    release = threading.Event()
    adapter = PydanticAIRuntimeAdapter(
        model=_blocking_model(started, release, '{"signal": "buy"}')
    )

    handle = adapter.start(_run_context("Analyze 600519"))
    try:
        assert started.wait(5)
        assert handle.state is ExecutionState.RUNNING
        assert handle.is_terminal is False
        assert handle.wait(timeout=0.01) is False
    finally:
        release.set()
        handle.wait(5)
        handle.close()

    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.result.dashboard == {"signal": "buy"}


def test_live_handle_cancellation_wins_after_active_request_returns():
    started = threading.Event()
    release = threading.Event()
    adapter = PydanticAIRuntimeAdapter(
        model=_blocking_model(started, release, '{"signal": "buy"}')
    )

    handle = adapter.start(_run_context("Analyze 600519"))
    try:
        assert started.wait(5)
        assert handle.request_cancel() is True
        assert handle.cancel_requested is True
        assert handle.state is ExecutionState.RUNNING
    finally:
        release.set()
        handle.wait(5)
        handle.close()

    assert handle.state is ExecutionState.CANCELLED
    assert handle.result.success is False
    assert handle.result.cancelled is True


def test_live_cancel_fences_wire_response_before_tool_dispatch():
    started = threading.Event()
    release = threading.Event()

    class _BlockingToolCallAdapter:
        primary_model = "blocking-wire-model"

        def call_with_tools(self, messages, tools, provider=None, timeout=None):
            started.set()
            assert release.wait(5)
            return LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call-after-cancel",
                        name="echo",
                        arguments={"message": "must-not-run"},
                    )
                ],
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                model=self.primary_model,
            )

    session = BoundToolSession(
        _echo_registry(),
        execution_id="ex-cancel-fence",
        allowed_tools=["echo"],
        granted_permissions=["test:read"],
    )
    adapter = PydanticAIRuntimeAdapter(
        llm_adapter=_BlockingToolCallAdapter(),
        tool_session=session,
    )

    handle = adapter.start(_run_context("Analyze 600519"))
    try:
        assert started.wait(5)
        assert handle.request_cancel() is True
    finally:
        release.set()
        handle.wait(5)
        handle.close()

    assert handle.state is ExecutionState.CANCELLED
    assert session.dispatched_calls == 0


def test_live_handle_subscribes_to_tool_events_before_terminal():
    waiting = threading.Event()
    release = threading.Event()
    callback = MagicMock()
    session = BoundToolSession(
        _echo_registry(),
        execution_id="ex-live-events",
        allowed_tools=["echo"],
        granted_permissions=["test:read"],
    )
    adapter = PydanticAIRuntimeAdapter(
        model=_tool_then_blocking_final_model(
            "echo",
            {"message": "hi"},
            '{"signal": "hold"}',
            waiting,
            release,
        ),
        tool_session=session,
    )

    handle = adapter.start(
        _run_context("Analyze 600519"), progress_callback=callback
    )
    try:
        assert waiting.wait(5)
        assert handle.state is ExecutionState.RUNNING
        live_events = list(handle.subscribe(timeout=0.01))
        assert [event.event_type for event in live_events] == [
            "tool_start",
            "tool_done",
        ]
    finally:
        release.set()
        handle.wait(5)
        handle.close()

    assert handle.state is ExecutionState.SUCCEEDED
    assert [event.event_type for event in handle.events] == [
        "tool_start",
        "tool_done",
    ]
    assert callback.call_count == 2


def test_chat_mode_is_unsupported():
    # RF-05: CHAT is frozen behind a stable unsupported_capability error until
    # the RF-06 conformance decision — never a silent degrade into a second
    # Conversation / SSE / trace surface.
    adapter = PydanticAIRuntimeAdapter(model=_fake_model("Here is my analysis."))
    with pytest.raises(NotImplementedError) as excinfo:
        adapter.execute(
            ExecutionContext(mode=ExecutionMode.CHAT, prompt="hi", session_id="s-1")
        )
    assert "unsupported_capability" in str(excinfo.value)


def test_research_mode_is_unsupported():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model('{"signal": "buy"}'))
    with pytest.raises(NotImplementedError) as excinfo:
        adapter.execute(ExecutionContext(mode=ExecutionMode.RESEARCH, prompt="deep research"))
    assert "unsupported_capability" in str(excinfo.value)


def test_name_is_experimental_and_non_default():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model("{}"))
    assert adapter.name == "pydantic_ai_experimental"


# ---------------------------------------------------------------------------
# Message conversion (deterministic, no model)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# BoundToolSession -> PydanticAI toolset bridge
# ---------------------------------------------------------------------------


def test_tool_call_routes_through_bound_session():
    session = BoundToolSession(
        _echo_registry(),
        execution_id="ex-tool-1",
        allowed_tools=["echo"],
        granted_permissions=["test:read"],
    )
    adapter = PydanticAIRuntimeAdapter(
        model=_tool_then_final_model("echo", {"message": "hi"}, '{"signal": "buy"}'),
        tool_session=session,
    )
    handle = adapter.execute(_run_context("Analyze 600519"))

    assert handle.state is ExecutionState.SUCCEEDED
    assert session.dispatched_calls == 1  # dispatched through the fail-closed gate
    assert handle.result.dashboard == {"signal": "buy"}


def test_gate_rejection_is_fail_closed_at_dispatch():
    # 'echo' is exposed (allowlisted) but the session lacks its required
    # permission -> execute() must reject at the gate without dispatching,
    # returning the shared error contract; the model then finalizes.
    session = BoundToolSession(
        _echo_registry(),
        execution_id="ex-tool-2",
        allowed_tools=["echo"],
        granted_permissions=[],  # missing 'test:read'
    )
    adapter = PydanticAIRuntimeAdapter(
        model=_tool_then_final_model("echo", {"message": "hi"}, '{"signal": "hold"}'),
        tool_session=session,
    )
    handle = adapter.execute(_run_context("Analyze 600519"))

    assert handle.state is ExecutionState.SUCCEEDED
    assert session.dispatched_calls == 0  # rejection never counts as a dispatch
    assert handle.result.dashboard == {"signal": "hold"}


def test_usage_is_recorded_through_single_recorder():
    # RF-05 #8 / AR-RF-10: usage is recorded once per wire call through the
    # single recorder, reusing StockPulse's own usage dict — the same
    # prompt/completion token field names the storage summary reads — so
    # provider telemetry survives and the Usage page keeps counting.
    class _RecordingRecorder:
        def __init__(self):
            self.calls = []

        def record(self, usage, model, *, call_type="agent"):
            self.calls.append((usage, model, call_type))
            return True

    class _OneShotAdapter:
        primary_model = "usage-model"

        def call_with_tools(self, messages, tools, provider=None, timeout=None):
            return LLMResponse(
                content='{"signal": "buy"}',
                usage={"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
                model=self.primary_model,
            )

    recorder = _RecordingRecorder()
    adapter = PydanticAIRuntimeAdapter(
        llm_adapter=_OneShotAdapter(), usage_recorder=recorder
    )
    adapter.execute(_run_context("Analyze 600519"))

    assert len(recorder.calls) == 1
    usage, model, call_type = recorder.calls[0]
    assert call_type == "agent"
    assert model == "usage-model"
    assert usage == {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10}


def test_tool_calls_emit_events_through_shared_emitter():
    from src.agent.runtime.events import RuntimeEventEmitter

    emitter = RuntimeEventEmitter(execution_id="ex-evt-1")
    events = []
    original = emitter.emit

    def _spy(event_type, **fields):
        result = original(event_type, **fields)
        events.append((event_type, fields))
        return result

    emitter.emit = _spy  # type: ignore[assignment]

    session = BoundToolSession(
        _echo_registry(),
        execution_id="ex-evt-1",
        allowed_tools=["echo"],
        granted_permissions=["test:read"],
    )
    adapter = PydanticAIRuntimeAdapter(
        model=_tool_then_final_model("echo", {"message": "hi"}, '{"signal": "buy"}'),
        tool_session=session,
        event_emitter=emitter,
    )
    adapter.execute(_run_context("Analyze 600519"))

    kinds = [e[0] for e in events]
    assert "tool_start" in kinds
    assert "tool_done" in kinds
    start = next(f for t, f in events if t == "tool_start")
    done = next(f for t, f in events if t == "tool_done")
    assert start["tool"] == "echo"
    assert done["tool"] == "echo"
    assert done["success"] is True


def test_toolset_exposes_only_allowed_tools():
    from src.agent.runtime.pydantic_ai_toolset import build_bound_session_toolset

    registry = _echo_registry()
    registry.register(
        ToolDefinition(
            name="secret",
            description="hidden",
            parameters=[],
            handler=lambda: {"x": 1},
        )
    )
    session = BoundToolSession(registry, execution_id="ex-tool-3", allowed_tools=["echo"])
    toolset = build_bound_session_toolset(session)
    tool_names = {t.name for t in toolset.tools.values()}
    assert tool_names == {"echo"}


def test_message_conversion_maps_text_parts_only():
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        SystemPromptPart,
        TextPart,
        UserPromptPart,
    )

    history = [
        ModelRequest(parts=[SystemPromptPart(content="sys"), UserPromptPart(content="hello")]),
        ModelResponse(parts=[TextPart(content="hi back")], model_name="fake"),
    ]
    assert _to_stockpulse_messages(history) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi back"},
    ]
