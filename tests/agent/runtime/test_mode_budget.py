# -*- coding: utf-8 -*-
"""Contract tests for hard per-mode Agent budgets (Refs #1121, #125)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.agent.executor import AgentExecutor
from src.agent.llm_adapter import ToolCall
from src.agent.protocols import StageFailureReason
from src.agent.runner import run_agent_loop
from src.agent.runtime.mode_budget import (
    ModeBudgetLimits,
    budget_breach_from_max_steps,
    create_mode_budget_account,
    estimate_usage_cost_usd,
    get_or_create_context_budget_account,
    resolve_mode_budget_limits,
)
from src.config import Config
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


def _chat_executor(*, adapter, max_steps: int, config) -> AgentExecutor:
    return AgentExecutor(
        tool_registry=_echo_registry(),
        llm_adapter=adapter,
        max_steps=max_steps,
        config=config,
    )


def _run_chat_loop(executor: AgentExecutor):
    return executor._run_loop(
        messages=[{"role": "user", "content": "hi"}],
        tool_decls=[],
        parse_dashboard=False,
    )


def _unique_tool_turns(count: int) -> List[_FakeResponse]:
    return [
        _FakeResponse(
            tool_calls=[
                ToolCall(
                    id=f"c{index}",
                    name="echo",
                    arguments={"message": f"x{index}"},
                )
            ],
            content="need tool",
        )
        for index in range(count)
    ]


def test_chat_factory_disabled_does_not_clip_max_steps():
    """AGENT_MODE_BUDGET_ENABLED=false must reach Chat and not clip AGENT_MAX_STEPS."""
    cfg = SimpleNamespace(agent_mode_budget_enabled=False)
    adapter = _adapter(_unique_tool_turns(11) + [_FakeResponse(content="done")])
    executor = _chat_executor(adapter=adapter, max_steps=20, config=cfg)
    result = _run_chat_loop(executor)
    assert result.success is True
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["limits"]["enabled"] is False
    assert result.total_steps > 10
    assert adapter.call_with_tools.call_count > 10


def test_chat_factory_enabled_tiny_tool_cap_breaches_budget_tools():
    """An enabled Chat account with a tiny tool cap still breaches with budget_tools."""
    cfg = SimpleNamespace(
        agent_mode_budget_enabled=True,
        agent_mode_budget_max_tool_calls=1,
        agent_mode_budget_max_llm_turns=0,
        agent_mode_budget_max_cost_usd=0.0,
        agent_mode_budget_max_tokens=0,
    )
    t1 = ToolCall(id="c1", name="echo", arguments={"message": "a"})
    t2 = ToolCall(id="c2", name="echo", arguments={"message": "b"})
    adapter = _adapter([
        _FakeResponse(tool_calls=[t1], content="t1"),
        _FakeResponse(tool_calls=[t2], content="t2"),
    ])
    executor = _chat_executor(adapter=adapter, max_steps=5, config=cfg)
    result = _run_chat_loop(executor)
    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_TOOLS
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["limits"]["enabled"] is True
    assert result.budget_snapshot["breach"]["reason"] == "budget_tools"


def test_run_loop_persists_mode_budget_account_on_executor():
    """The live Chat/single-agent account stays on the executor after the loop."""
    cfg = SimpleNamespace(agent_mode_budget_enabled=True)
    adapter = _adapter([_FakeResponse(content="done")])
    executor = _chat_executor(adapter=adapter, max_steps=5, config=cfg)
    assert getattr(executor, "mode_budget_account", None) is None
    result = _run_chat_loop(executor)
    account = executor.mode_budget_account
    assert account is not None
    assert result.budget_snapshot is not None
    assert account.llm_turns == result.budget_snapshot["used"]["llm_turns"]
    assert account.llm_turns >= 1


def test_chat_factory_default_on_still_clips_chat_turn_budget():
    """Default-on Chat still applies the built-in 10-turn cap (compatibility)."""
    cfg = SimpleNamespace(agent_mode_budget_enabled=True)
    adapter = _adapter(_unique_tool_turns(11) + [_FakeResponse(content="done")])
    executor = _chat_executor(adapter=adapter, max_steps=20, config=cfg)
    result = _run_chat_loop(executor)
    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_TURNS
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["limits"]["enabled"] is True
    assert result.budget_snapshot["limits"]["max_llm_turns"] == 10


def test_classic_analyzer_does_not_import_mode_budget():
    """Classic single-pass analyzer must not import the Agent mode-budget module."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    pythonpath = os.pathsep.join(
        [str(repo_root), os.environ.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import src.analyzer; "
                "assert 'src.agent.runtime.mode_budget' not in sys.modules, "
                "sorted(k for k in sys.modules if 'mode_budget' in k)"
            ),
        ],
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": pythonpath},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


_PER_MODE_BUDGET_FIELDS = (
    "agent_mode_budget_quick_max_llm_turns",
    "agent_mode_budget_quick_max_tool_calls",
    "agent_mode_budget_quick_max_cost_usd",
    "agent_mode_budget_standard_max_llm_turns",
    "agent_mode_budget_standard_max_tool_calls",
    "agent_mode_budget_standard_max_cost_usd",
    "agent_mode_budget_full_max_llm_turns",
    "agent_mode_budget_full_max_tool_calls",
    "agent_mode_budget_full_max_cost_usd",
    "agent_mode_budget_specialist_max_llm_turns",
    "agent_mode_budget_specialist_max_tool_calls",
    "agent_mode_budget_specialist_max_cost_usd",
    "agent_mode_budget_chat_max_llm_turns",
    "agent_mode_budget_chat_max_tool_calls",
    "agent_mode_budget_chat_max_cost_usd",
)


def test_config_keeps_documented_per_mode_budget_override_fields():
    """Per-mode overrides stay Config attributes (not a silent deletion)."""
    missing = [
        name
        for name in _PER_MODE_BUDGET_FIELDS
        if name not in Config.__dataclass_fields__
    ]
    assert missing == []


def test_per_mode_override_takes_effect_for_multi():
    """A documented per-mode Config override still binds Multi's context account."""
    cfg = SimpleNamespace(
        agent_mode_budget_enabled=True,
        agent_mode_budget_max_llm_turns=0,
        agent_mode_budget_max_tool_calls=0,
        agent_mode_budget_max_cost_usd=0.0,
        agent_mode_budget_max_tokens=0,
        agent_mode_budget_quick_max_tool_calls=4,
        agent_mode_budget_quick_max_llm_turns=0,
        agent_mode_budget_quick_max_cost_usd=0.0,
        agent_mode_budget_full_max_tool_calls=0,
    )
    quick_ctx = SimpleNamespace(meta={"orchestrator_mode": "quick"})
    quick_account = get_or_create_context_budget_account(
        quick_ctx, cfg, mode="quick"
    )
    assert quick_account.limits.mode == "quick"
    assert quick_account.limits.max_tool_calls == 4
    assert quick_account.limits.max_llm_turns == 6
    assert quick_account.limits.max_cost_usd == pytest.approx(0.15)

    full_ctx = SimpleNamespace(meta={"orchestrator_mode": "full"})
    full_account = get_or_create_context_budget_account(full_ctx, cfg, mode="full")
    assert full_account.limits.mode == "full"
    assert full_account.limits.max_tool_calls == 48


def test_per_mode_override_zero_keeps_mode_default():
    """0 on a per-mode override still means 'keep mode default', not unlimited."""
    cfg = SimpleNamespace(
        agent_mode_budget_enabled=True,
        agent_mode_budget_quick_max_tool_calls=0,
        agent_mode_budget_quick_max_llm_turns=0,
        agent_mode_budget_quick_max_cost_usd=0.0,
    )
    limits = resolve_mode_budget_limits(cfg, mode="quick")
    assert limits.max_tool_calls == 16
    assert limits.max_llm_turns == 6
    assert limits.max_cost_usd == pytest.approx(0.15)


def test_global_tightener_mins_with_per_mode_override():
    """A positive global tightener still takes min() after a per-mode override."""
    cfg = SimpleNamespace(
        agent_mode_budget_enabled=True,
        agent_mode_budget_max_tool_calls=3,
        agent_mode_budget_max_llm_turns=0,
        agent_mode_budget_max_cost_usd=0.0,
        agent_mode_budget_max_tokens=0,
        agent_mode_budget_quick_max_tool_calls=8,
    )
    limits = resolve_mode_budget_limits(cfg, mode="quick")
    assert limits.max_tool_calls == 3


def test_chat_factory_honors_per_mode_chat_override():
    """Passing Config into Chat means agent_mode_budget_chat_max_* now applies."""
    cfg = SimpleNamespace(
        agent_mode_budget_enabled=True,
        agent_mode_budget_max_tool_calls=0,
        agent_mode_budget_max_llm_turns=0,
        agent_mode_budget_max_cost_usd=0.0,
        agent_mode_budget_max_tokens=0,
        agent_mode_budget_chat_max_tool_calls=1,
        agent_mode_budget_chat_max_llm_turns=0,
        agent_mode_budget_chat_max_cost_usd=0.0,
    )
    t1 = ToolCall(id="c1", name="echo", arguments={"message": "a"})
    t2 = ToolCall(id="c2", name="echo", arguments={"message": "b"})
    adapter = _adapter([
        _FakeResponse(tool_calls=[t1], content="t1"),
        _FakeResponse(tool_calls=[t2], content="t2"),
    ])
    executor = _chat_executor(adapter=adapter, max_steps=5, config=cfg)
    result = _run_chat_loop(executor)
    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_TOOLS
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["limits"]["max_tool_calls"] == 1
    assert result.budget_snapshot["breach"]["reason"] == "budget_tools"


def test_per_mode_override_env_maps_onto_config_attributes():
    """The loader still maps optional AGENT_MODE_BUDGET_<MODE>_MAX_* env vars."""
    with patch("src.config.setup_env"), patch.object(
        Config, "_parse_litellm_yaml", return_value=[]
    ), patch.object(Config, "_parse_stock_email_groups", return_value=[]), patch.dict(
        os.environ,
        {
            "STOCK_LIST": "600519",
            "AGENT_MODE_BUDGET_QUICK_MAX_TOOL_CALLS": "4",
            "AGENT_MODE_BUDGET_CHAT_MAX_LLM_TURNS": "7",
        },
        clear=True,
    ):
        loaded = Config._load_from_env()
    try:
        assert loaded.agent_mode_budget_quick_max_tool_calls == 4
        assert loaded.agent_mode_budget_chat_max_llm_turns == 7
        quick = resolve_mode_budget_limits(loaded, mode="quick")
        assert quick.max_tool_calls == 4
        chat = resolve_mode_budget_limits(loaded, mode="chat", chat=True)
        assert chat.max_llm_turns == 7
        assert chat.max_tool_calls == 24
    finally:
        Config.reset_instance()
