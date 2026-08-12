# -*- coding: utf-8 -*-
"""Contract tests for hard per-mode budgets (Refs #1121, #125)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock

import pytest

from src.agent.llm_adapter import ToolCall
from src.agent.protocols import StageFailureReason
from src.agent.runner import run_agent_loop
from src.agent.runtime.mode_budget import (
    ModeBudgetLimits,
    budget_breach_from_max_steps,
    create_mode_budget_account,
    estimate_usage_cost_usd,
    resolve_mode_budget_limits,
)
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)


class _FakeResponse:
    def __init__(
        self,
        *,
        content: str = "",
        tool_calls=None,
        usage=None,
        provider: str = "fake",
        model: str = "fake-model",
        reasoning_content=None,
        provider_blocks=None,
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = usage or {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        self.provider = provider
        self.model = model
        self.reasoning_content = reasoning_content
        self.provider_blocks = provider_blocks


def _adapter(responses: List[_FakeResponse]):
    adapter = MagicMock()
    adapter.model = "fake-model"
    adapter.call_with_tools.side_effect = list(responses)
    return adapter


def _echo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a message.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
            ],
            handler=lambda message="": {"message": message},
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                side_effects=[],
                permissions=["analysis_context:read"],
            ),
        )
    )
    return registry


def test_resolve_mode_defaults_differ_by_mode():
    quick = resolve_mode_budget_limits(mode="quick")
    full = resolve_mode_budget_limits(mode="full")
    chat = resolve_mode_budget_limits(mode="standard", chat=True)
    assert quick.max_llm_turns < full.max_llm_turns
    assert quick.max_tool_calls < full.max_tool_calls
    assert chat.mode == "chat"
    assert quick.enabled is True


def test_global_tightener_reduces_mode_defaults():
    cfg = SimpleNamespace(
        agent_mode_budget_enabled=True,
        agent_mode_budget_max_tool_calls=3,
        agent_mode_budget_max_llm_turns=0,
        agent_mode_budget_max_cost_usd=0.0,
        agent_mode_budget_max_tokens=0,
    )
    limits = resolve_mode_budget_limits(cfg, mode="full")
    assert limits.max_tool_calls == 3
    assert limits.max_llm_turns == 12


def test_max_steps_exceeded_is_budget_turns_not_silent_success():
    """Counterexample: exceeding LLM turns terminates with budget_turns."""
    tool_call = ToolCall(id="c1", name="echo", arguments={"message": "x"})
    adapter = _adapter([
        _FakeResponse(tool_calls=[tool_call], content="need tool"),
    ])
    account = create_mode_budget_account(
        limits=ModeBudgetLimits(
            mode="quick",
            enabled=True,
            max_llm_turns=1,
            max_tool_calls=10,
            max_cost_usd=0,
            max_tokens=0,
        )
    )
    result = run_agent_loop(
        messages=[{"role": "user", "content": "hi"}],
        tool_registry=_echo_registry(),
        llm_adapter=adapter,
        max_steps=1,
        mode_budget_account=account,
    )
    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_TURNS
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["breach"]["reason"] == "budget_turns"
    err = (result.error or "").lower()
    assert "turn" in err or "max steps" in err or "budget" in err


def test_tool_budget_breach_terminates_with_budget_tools():
    t1 = ToolCall(id="c1", name="echo", arguments={"message": "a"})
    t2 = ToolCall(id="c2", name="echo", arguments={"message": "b"})
    adapter = _adapter([
        _FakeResponse(tool_calls=[t1], content="t1"),
        _FakeResponse(tool_calls=[t2], content="t2"),
    ])
    account = create_mode_budget_account(
        limits=ModeBudgetLimits(
            mode="quick",
            enabled=True,
            max_llm_turns=10,
            max_tool_calls=1,
            max_cost_usd=0,
            max_tokens=0,
        )
    )
    result = run_agent_loop(
        messages=[{"role": "user", "content": "hi"}],
        tool_registry=_echo_registry(),
        llm_adapter=adapter,
        max_steps=5,
        mode_budget_account=account,
    )
    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_TOOLS
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["breach"]["reason"] == "budget_tools"
    assert result.budget_snapshot["used"]["tool_calls"] >= 1


def test_cost_budget_breach_terminates_with_budget_cost(monkeypatch):
    monkeypatch.setattr(
        "src.agent.runner.estimate_usage_cost_usd",
        lambda usage, model="": 1.0,
    )
    adapter = _adapter([
        _FakeResponse(
            content="done",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        ),
    ])
    account = create_mode_budget_account(
        limits=ModeBudgetLimits(
            mode="quick",
            enabled=True,
            max_llm_turns=10,
            max_tool_calls=50,
            max_cost_usd=0.01,
            max_tokens=0,
        )
    )
    result = run_agent_loop(
        messages=[{"role": "user", "content": "hi"}],
        tool_registry=_echo_registry(),
        llm_adapter=adapter,
        max_steps=5,
        mode_budget_account=account,
    )
    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_COST
    assert result.budget_snapshot["breach"]["reason"] == "budget_cost"


def test_cancel_outranks_budget_when_cancelled_before_step():
    adapter = _adapter([_FakeResponse(content="should not run")])
    account = create_mode_budget_account(
        limits=ModeBudgetLimits(
            mode="quick",
            enabled=True,
            max_llm_turns=1,
            max_tool_calls=1,
            max_cost_usd=0.01,
            max_tokens=1,
        )
    )
    result = run_agent_loop(
        messages=[{"role": "user", "content": "hi"}],
        tool_registry=_echo_registry(),
        llm_adapter=adapter,
        max_steps=3,
        mode_budget_account=account,
        cancelled_check=lambda: True,
    )
    assert result.cancelled is True
    assert result.success is False
    assert adapter.call_with_tools.call_count == 0


def test_budget_breach_from_max_steps_message_is_explicit():
    breach = budget_breach_from_max_steps(max_steps=3)
    assert breach.reason == "budget_turns"
    assert breach.failure_reason == StageFailureReason.BUDGET_TURNS
    assert "max steps" in breach.message.lower() or "turn" in breach.message.lower()


def test_estimate_usage_cost_prefers_explicit_cost_field():
    assert estimate_usage_cost_usd({"response_cost": 0.42}) == pytest.approx(0.42)


def test_disabled_mode_budget_does_not_cap():
    cfg = SimpleNamespace(agent_mode_budget_enabled=False)
    limits = resolve_mode_budget_limits(cfg, mode="quick")
    assert limits.enabled is False
    assert limits.effective_max_steps(99) == 99
