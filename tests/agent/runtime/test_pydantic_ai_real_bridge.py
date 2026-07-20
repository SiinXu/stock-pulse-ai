# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Real-bridge conformance for the PydanticAI runtime (RF-05).

Unlike ``test_pydantic_ai_adapter.py``'s tool tests — where a fake PydanticAI
``Model`` emits ``ToolCallPart`` directly — these drive the *actual* bridge
(``build_stockpulse_backed_model``) over a fake StockPulse ``LLMToolAdapter``.
This is the RF-05 requirement that the loop must not be proven by shortcutting
the tool-call mapping: the fake adapter receives the real tool schema, prompt
and timeout, returns a StockPulse ``tool_call``, and the adapter's ``request()``
maps it to ``ToolCallPart`` so PydanticAI drives the ``BoundToolSession``
toolset; the tool return then rounds back into the next wire call.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.runtime.contract import ExecutionContext, ExecutionMode, ExecutionState
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)

from tests.agent.runtime._pydantic_ai_dependency import require_pydantic_ai

require_pydantic_ai()

from src.agent.runtime.pydantic_ai_adapter import PydanticAIRuntimeAdapter


def _echo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echoes the message back",
            parameters=[ToolParameter(name="message", type="string", description="Message")],
            handler=lambda message: {"echo": message},
            policy=ToolPolicy.declared(read_only=True, side_effects=[], permissions=["test:read"]),
        )
    )
    return registry


class _ScriptedLLMAdapter:
    """A fake StockPulse ``LLMToolAdapter`` that records every wire call.

    Turn 1 requests the ``echo`` tool; turn 2 (after seeing the tool result)
    returns the final dashboard JSON. Each call is recorded so the test can
    assert the real schema / prompt / timeout crossed the bridge.
    """

    def __init__(self, *, final: str = '{"signal": "buy", "confidence": 0.9}'):
        self.primary_model = "scripted-bridge-model"
        self._final = final
        self.calls: list = []

    def call_with_tools(self, messages, tools, provider=None, timeout=None):
        self.calls.append({"messages": messages, "tools": tools, "timeout": timeout})
        if len(self.calls) == 1:
            return LLMResponse(
                tool_calls=[ToolCall(id="call-1", name="echo", arguments={"message": "hi"})],
                usage={"prompt_tokens": 5, "completion_tokens": 2},
                model=self.primary_model,
            )
        return LLMResponse(
            content=self._final,
            usage={"prompt_tokens": 7, "completion_tokens": 3},
            model=self.primary_model,
        )


def _bound_session() -> BoundToolSession:
    return BoundToolSession(
        _echo_registry(),
        execution_id="ex-real-bridge",
        allowed_tools=["echo"],
        granted_permissions=["test:read"],
    )


def _run(adapter: PydanticAIRuntimeAdapter, *, timeout_seconds=None):
    return adapter.execute(
        ExecutionContext(mode=ExecutionMode.RUN, prompt="Analyze 600519", timeout_seconds=timeout_seconds)
    )


def test_real_bridge_forwards_real_tool_schema_and_timeout():
    fake = _ScriptedLLMAdapter()
    adapter = PydanticAIRuntimeAdapter(llm_adapter=fake, tool_session=_bound_session())

    handle = _run(adapter, timeout_seconds=30)

    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.result.dashboard == {"signal": "buy", "confidence": 0.9}

    first = fake.calls[0]
    # RF-05 #1: the real tool definition — never a fixed empty array — reaches
    # the wire call in the shared openai-tools shape.
    assert first["tools"], "bridge must forward registered tools, not []"
    fn = first["tools"][0]["function"]
    assert fn["name"] == "echo"
    assert fn["parameters"]["type"] == "object"
    assert "message" in fn["parameters"]["properties"]
    # The prompt actually crosses the bridge as a user message.
    assert any(m["role"] == "user" and "600519" in str(m["content"]) for m in first["messages"])
    # RF-05 #6: the execution's remaining timeout is threaded into the call.
    assert first["timeout"] is not None and 0 < first["timeout"] <= 30


def test_real_bridge_tool_return_rounds_back_into_next_request():
    fake = _ScriptedLLMAdapter()
    session = _bound_session()
    adapter = PydanticAIRuntimeAdapter(llm_adapter=fake, tool_session=session)

    handle = _run(adapter)

    assert handle.state is ExecutionState.SUCCEEDED
    # The tool ran exactly once, through the fail-closed BoundToolSession gate.
    assert session.dispatched_calls == 1
    # RF-05 #2/#3: the model produced a real tool call (not a fake shortcut),
    # and the tool result rounds back into the second wire call.
    assert len(fake.calls) == 2
    second_msgs = fake.calls[1]["messages"]
    assert any(m["role"] == "assistant" and m.get("tool_calls") for m in second_msgs)
    tool_msgs = [m for m in second_msgs if m["role"] == "tool"]
    assert tool_msgs, "tool return must round back to the next model request"
    assert tool_msgs[0]["name"] == "echo"
    assert tool_msgs[0]["tool_call_id"] == "call-1"
    assert "hi" in tool_msgs[0]["content"]


class _TraceCarryingAdapter:
    """Turn 1 emits a tool call carrying full provider trace; turn 2 finalizes.

    The trace (reasoning / opaque provider blocks / thought signature /
    provider-specific fields) must round back into turn 2's wire messages
    exactly like the native loop preserves it (RF-05 #4).
    """

    def __init__(self):
        self.primary_model = "trace-model"
        self.calls: list = []

    def call_with_tools(self, messages, tools, provider=None, timeout=None):
        self.calls.append({"messages": messages, "tools": tools, "timeout": timeout})
        if len(self.calls) == 1:
            return LLMResponse(
                content="thinking about it",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="echo",
                        arguments={"message": "hi"},
                        thought_signature="SIG-abc",
                        provider_specific_fields={"gemini": "psf-xyz"},
                    )
                ],
                reasoning_content="COT-REASONING",
                provider_blocks=[{"type": "thinking", "raw": "opaque-block"}],
                usage={"prompt_tokens": 5, "completion_tokens": 2},
                model=self.primary_model,
            )
        return LLMResponse(
            content='{"signal": "buy"}',
            usage={"prompt_tokens": 7, "completion_tokens": 3},
            model=self.primary_model,
        )


def test_real_bridge_roundtrips_provider_trace_losslessly():
    fake = _TraceCarryingAdapter()
    adapter = PydanticAIRuntimeAdapter(llm_adapter=fake, tool_session=_bound_session())

    handle = _run(adapter)

    assert handle.state is ExecutionState.SUCCEEDED
    assert len(fake.calls) == 2
    # Turn 2 must see the assistant turn's provider trace verbatim (#4).
    assistant = next(
        m for m in fake.calls[1]["messages"] if m["role"] == "assistant" and m.get("tool_calls")
    )
    assert assistant["reasoning_content"] == "COT-REASONING"
    assert assistant["provider_blocks"] == [{"type": "thinking", "raw": "opaque-block"}]
    tc = assistant["tool_calls"][0]
    assert tc["thought_signature"] == "SIG-abc"
    assert tc["provider_specific_fields"] == {"gemini": "psf-xyz"}


def test_real_bridge_text_only_success_without_tools():
    fake = _ScriptedLLMAdapter()
    # Force a single-turn text answer: no tool call, dashboard straight away.
    fake.call_with_tools = _single_turn(fake, '{"signal": "hold"}')  # type: ignore[assignment]
    adapter = PydanticAIRuntimeAdapter(llm_adapter=fake, tool_session=None)

    handle = _run(adapter)

    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.result.dashboard == {"signal": "hold"}


def test_real_bridge_malformed_output_fails_closed():
    fake = _ScriptedLLMAdapter()
    fake.call_with_tools = _single_turn(fake, "not json at all")  # type: ignore[assignment]
    adapter = PydanticAIRuntimeAdapter(llm_adapter=fake, tool_session=None)

    handle = _run(adapter)

    assert handle.state is ExecutionState.FAILED
    assert handle.result.success is False
    assert handle.result.dashboard is None


def _single_turn(fake: _ScriptedLLMAdapter, content: str):
    def _call(messages, tools, provider=None, timeout=None):
        fake.calls.append({"messages": messages, "tools": tools, "timeout": timeout})
        return LLMResponse(
            content=content,
            usage={"prompt_tokens": 3, "completion_tokens": 1},
            model=fake.primary_model,
        )

    return _call


# ---------------------------------------------------------------------------
# Prompt reuse, cancellation, deadline and provider error (RF-05 #5/#6/#7/#9)
# ---------------------------------------------------------------------------


class _PromptExecutor:
    """Minimal stand-in for ``AgentExecutor.build_run_messages`` (RF-05 #5)."""

    def build_run_messages(self, task, context=None):
        return ("SYSTEM-PROMPT-REUSED", f"USER::{task}", [])


def test_real_bridge_reuses_executor_prompt_authority():
    fake = _ScriptedLLMAdapter()
    fake.call_with_tools = _single_turn(fake, '{"signal": "buy"}')  # type: ignore[assignment]
    adapter = PydanticAIRuntimeAdapter(llm_adapter=fake, executor=_PromptExecutor())

    handle = _run(adapter)

    assert handle.state is ExecutionState.SUCCEEDED
    messages = fake.calls[0]["messages"]
    # The resolved system prompt crosses the bridge as a system message and the
    # executor-built user message replaces the raw prompt: one prompt authority
    # rather than a second set of business rules inside the adapter.
    assert {"role": "system", "content": "SYSTEM-PROMPT-REUSED"} in messages
    assert any(
        m["role"] == "user" and m["content"] == "USER::Analyze 600519" for m in messages
    )


def test_real_bridge_cancellation_wins_and_records_usage_once():
    from src.agent.runtime.pydantic_ai_adapter import build_stockpulse_backed_model

    cancel_flag = {"cancelled": False}

    class _CancelAfterToolAdapter:
        primary_model = "cancel-model"

        def __init__(self):
            self.calls: list = []

        def call_with_tools(self, messages, tools, provider=None, timeout=None):
            self.calls.append({"messages": messages})
            # Turn 1 asks for the tool, then flips cancellation on so the next
            # bridge checkpoint stops before spending a second billed request.
            cancel_flag["cancelled"] = True
            return LLMResponse(
                tool_calls=[ToolCall(id="call-1", name="echo", arguments={"message": "hi"})],
                usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                model=self.primary_model,
            )

    class _Recorder:
        def __init__(self):
            self.calls: list = []

        def record(self, usage, model, *, call_type="agent"):
            self.calls.append((usage, model))
            return True

    fake = _CancelAfterToolAdapter()
    recorder = _Recorder()
    model = build_stockpulse_backed_model(
        fake,
        cancelled_check=lambda: cancel_flag["cancelled"],
        usage_recorder=recorder,
    )
    adapter = PydanticAIRuntimeAdapter(model=model, tool_session=_bound_session())

    handle = _run(adapter)

    # Cancellation wins over any degraded success and never fakes one.
    assert handle.state is ExecutionState.CANCELLED
    assert handle.result.success is False
    # Exactly one wire call happened; its valid usage is still recorded once.
    assert len(fake.calls) == 1
    assert len(recorder.calls) == 1


def test_real_bridge_deadline_elapsed_times_out_before_wire_call():
    from src.agent.runtime.pydantic_ai_adapter import build_stockpulse_backed_model

    class _NeverCalledAdapter:
        primary_model = "deadline-model"

        def __init__(self):
            self.calls: list = []

        def call_with_tools(self, messages, tools, provider=None, timeout=None):
            self.calls.append({"messages": messages})
            return LLMResponse(content="{}", usage={}, model=self.primary_model)

    fake = _NeverCalledAdapter()
    # An already-elapsed deadline: the bridge must stop before spending a call.
    model = build_stockpulse_backed_model(fake, remaining_timeout=lambda: 0.0)
    adapter = PydanticAIRuntimeAdapter(model=model, tool_session=None)

    handle = _run(adapter)

    assert handle.state is ExecutionState.TIMED_OUT
    assert handle.result.success is False
    assert fake.calls == []  # no billed request after the deadline elapsed


def test_real_bridge_provider_error_fails_closed():
    from src.agent.runtime.pydantic_ai_adapter import build_stockpulse_backed_model

    class _ErroringAdapter:
        primary_model = "error-model"

        def call_with_tools(self, messages, tools, provider=None, timeout=None):
            # StockPulse surfaces a sanitized public failure via provider="error";
            # it must fail closed, never parse as a final dashboard answer.
            return LLMResponse(content="Agent generation failed.", provider="error")

    model = build_stockpulse_backed_model(_ErroringAdapter())
    adapter = PydanticAIRuntimeAdapter(model=model, tool_session=None)

    handle = _run(adapter)

    assert handle.state is ExecutionState.FAILED
    assert handle.result.success is False
    assert handle.result.dashboard is None
