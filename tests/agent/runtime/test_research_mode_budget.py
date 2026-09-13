# -*- coding: utf-8 -*-
"""Real-layer Deep Research mode-budget counterexamples (Refs #1121)."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock, patch

from src.agent.llm_adapter import ToolCall
from src.agent.research import ResearchAgent, research_token_budget_from_config
from src.agent.runtime.contract import (
    AgentExecution,
    ExecutionContext,
    ExecutionMode,
)
from src.agent.runtime.mode_budget import resolve_research_mode_budget_limits
from src.agent.runtime.native_adapter import NativeRuntimeAdapter
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
        self.reasoning_content = None
        self.provider_blocks = None


class _FakeResearchAdapter:
    def __init__(
        self,
        text_responses: List[_FakeResponse],
        tool_responses: List[_FakeResponse] | None = None,
    ):
        self.model = "fake-model"
        self._text = list(text_responses)
        self._tools = list(tool_responses or [])
        self.text_calls = 0
        self.tool_calls = 0

    def call_text(self, *args, **kwargs):
        self.text_calls += 1
        if not self._text:
            raise AssertionError("unexpected call_text after research should have stopped")
        return self._text.pop(0)

    def call_with_tools(self, *args, **kwargs):
        self.tool_calls += 1
        if not self._tools:
            raise AssertionError(
                "unexpected call_with_tools after research should have stopped"
            )
        return self._tools.pop(0)


def _cfg(**overrides) -> SimpleNamespace:
    values = dict(
        agent_mode_budget_enabled=True,
        agent_mode_budget_max_llm_turns=0,
        agent_mode_budget_max_tool_calls=0,
        agent_mode_budget_max_cost_usd=0.0,
        agent_mode_budget_max_tokens=0,
        agent_deep_research_budget=30000,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _research_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name in ("get_stock_info", "get_realtime_quote"):
        registry.register(
            ToolDefinition(
                name=name,
                description=name,
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


def _agent(adapter, cfg, token_budget=None) -> ResearchAgent:
    return ResearchAgent(
        tool_registry=_research_registry(),
        llm_adapter=adapter,
        token_budget=cfg.agent_deep_research_budget if token_budget is None else token_budget,
        config=cfg,
    )


def _decompose_response() -> _FakeResponse:
    return _FakeResponse(content='{"questions":["What is the moat?"]}')


def test_research_limits_use_specialist_defaults_and_research_token_ceiling():
    limits = resolve_research_mode_budget_limits(
        _cfg(agent_deep_research_budget=30000), token_budget=30000
    )
    assert limits.mode == "specialist"
    assert limits.max_llm_turns == 12
    assert limits.max_tool_calls == 64
    assert limits.max_cost_usd == 1.50
    assert limits.max_tokens == 30000


def test_research_token_ceiling_mins_with_global_max_tokens():
    limits = resolve_research_mode_budget_limits(
        _cfg(agent_mode_budget_max_tokens=5000, agent_deep_research_budget=30000),
        token_budget=30000,
    )
    assert limits.max_tokens == 5000


def test_disabled_switch_keeps_token_only_fail_closed_profile():
    limits = resolve_research_mode_budget_limits(
        _cfg(agent_mode_budget_enabled=False, agent_deep_research_budget=111),
        token_budget=111,
    )
    assert limits.enabled is True
    assert limits.max_llm_turns == 0
    assert limits.max_tool_calls == 0
    assert limits.max_cost_usd == 0.0
    assert limits.max_tokens == 111


def _tool_loop_response(n: int) -> _FakeResponse:
    return _FakeResponse(
        tool_calls=[
            ToolCall(
                id=f"c{n}",
                name="get_stock_info",
                arguments={"message": f"lookup-{n}"},
            )
        ],
        content="need tools",
    )


def _sub_question_final_response() -> _FakeResponse:
    return _FakeResponse(content="Sub-question findings.")


def _four_step_sub_question_fill(start: int) -> List[_FakeResponse]:
    return [
        _tool_loop_response(start),
        _tool_loop_response(start + 1),
        _tool_loop_response(start + 2),
        _sub_question_final_response(),
    ]


def test_remaining_max_steps_clamps_to_unused_turns_not_absolute_cap():
    from src.agent.runtime.mode_budget import create_research_mode_budget_account

    account = create_research_mode_budget_account(
        _cfg(agent_mode_budget_specialist_max_llm_turns=12),
        token_budget=30000,
    )
    assert account.remaining_max_steps(4) == 4
    account.llm_turns = 10
    assert account.remaining_max_steps(4) == 2
    account.llm_turns = 12
    assert account.remaining_max_steps(4) == 0

    token_only = create_research_mode_budget_account(
        _cfg(agent_mode_budget_enabled=False, agent_deep_research_budget=111),
        token_budget=111,
    )
    assert token_only.remaining_max_steps(4) == 4


def test_r1_decompose_turn_blocks_subquestions_and_synthesis():
    adapter = _FakeResearchAdapter(
        text_responses=[
            _decompose_response(),
            _FakeResponse(content="should not synthesise"),
        ],
        tool_responses=[_FakeResponse(content="should not research")],
    )
    result = _agent(
        adapter,
        _cfg(agent_mode_budget_specialist_max_llm_turns=1),
    ).research("Analyse 600519")

    assert result.success is False
    assert result.failure_reason == "budget_turns"
    assert result.timed_out is False
    assert result.cancelled is False
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["breach"]["reason"] == "budget_turns"
    assert result.budget_snapshot["used"]["llm_turns"] >= 1
    assert adapter.text_calls == 1
    assert adapter.tool_calls == 0


def test_r2_token_cap_below_one_completion_is_budget_tokens_not_timeout():
    adapter = _FakeResearchAdapter(
        text_responses=[
            _FakeResponse(
                content='{"questions":["Q1"]}',
                usage={"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
            ),
            _FakeResponse(content="should not synthesise"),
        ],
        tool_responses=[_FakeResponse(content="should not research")],
    )
    result = _agent(
        adapter,
        _cfg(agent_deep_research_budget=10),
        token_budget=10,
    ).research("Analyse 600519")

    assert result.success is False
    assert result.failure_reason == "budget_tokens"
    assert result.timed_out is False
    assert result.budget_snapshot["breach"]["reason"] == "budget_tokens"
    assert adapter.text_calls == 1
    assert adapter.tool_calls == 0


def test_r3_two_tools_against_one_tool_cap_is_budget_tools():
    t1 = ToolCall(id="c1", name="get_stock_info", arguments={"message": "a"})
    t2 = ToolCall(id="c2", name="get_realtime_quote", arguments={"message": "b"})
    adapter = _FakeResearchAdapter(
        text_responses=[
            _decompose_response(),
            _FakeResponse(content="should not synthesise"),
        ],
        tool_responses=[_FakeResponse(tool_calls=[t1, t2], content="need tools")],
    )
    result = _agent(
        adapter,
        _cfg(agent_mode_budget_specialist_max_tool_calls=1),
    ).research("Analyse 600519")

    assert result.success is False
    assert result.failure_reason == "budget_tools"
    assert result.timed_out is False
    assert result.budget_snapshot["breach"]["reason"] == "budget_tools"
    assert adapter.tool_calls == 1
    assert adapter.text_calls == 1


def test_r4_cancel_before_any_llm_does_not_call_adapter():
    adapter = _FakeResearchAdapter(
        text_responses=[_decompose_response()],
        tool_responses=[_FakeResponse(content="nope")],
    )
    result = _agent(adapter, _cfg()).research(
        "Analyse 600519",
        cancelled_check=lambda: True,
    )
    assert result.success is False
    assert result.cancelled is True
    assert result.failure_reason not in {
        "budget_turns",
        "budget_tools",
        "budget_cost",
        "budget_tokens",
    }
    assert adapter.text_calls == 0
    assert adapter.tool_calls == 0


def test_r5_cancel_after_decompose_wins_over_remaining_turns():
    adapter = _FakeResearchAdapter(
        text_responses=[
            _decompose_response(),
            _FakeResponse(content="should not synthesise"),
        ],
        tool_responses=[_FakeResponse(content="should not research")],
    )
    calls = {"n": 0}

    def cancelled_check():
        return calls["n"] >= 1

    original_call_text = adapter.call_text

    def tracking_call_text(*args, **kwargs):
        response = original_call_text(*args, **kwargs)
        calls["n"] += 1
        return response

    adapter.call_text = tracking_call_text
    result = _agent(
        adapter,
        _cfg(agent_mode_budget_specialist_max_llm_turns=12),
    ).research("Analyse 600519", cancelled_check=cancelled_check)

    assert result.success is False
    assert result.cancelled is True
    assert result.failure_reason not in {
        "budget_turns",
        "budget_tools",
        "budget_cost",
        "budget_tokens",
    }
    assert adapter.tool_calls == 0
    assert calls["n"] == 1


def test_r6_disabled_mode_budget_still_fail_closes_research_token_cap():
    adapter = _FakeResearchAdapter(
        text_responses=[
            _FakeResponse(
                content='{"questions":["Q1"]}',
                usage={"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
            ),
            _FakeResponse(content="should not synthesise"),
        ],
        tool_responses=[_FakeResponse(content="should not research")],
    )
    result = _agent(
        adapter,
        _cfg(agent_mode_budget_enabled=False, agent_deep_research_budget=10),
        token_budget=10,
    ).research("Analyse 600519")

    assert result.success is False
    assert result.failure_reason == "budget_tokens"
    assert result.budget_snapshot["limits"]["max_llm_turns"] == 0
    assert result.budget_snapshot["limits"]["max_tokens"] == 10
    assert adapter.text_calls == 1
    assert adapter.tool_calls == 0


def test_r7_native_handle_cancel_is_visible_to_research():
    adapter = _FakeResearchAdapter(text_responses=[_decompose_response()])
    config = _cfg()
    with patch(
        "src.agent.runtime_assembly.get_tool_registry",
        return_value=_research_registry(),
    ), patch(
        "src.agent.llm_adapter.LLMToolAdapter",
        return_value=adapter,
    ):
        native = NativeRuntimeAdapter(config=config)
        context = ExecutionContext(mode=ExecutionMode.RESEARCH, prompt="why rally?")
        execution = AgentExecution(context)
        execution.request_cancel()
        result = native._run_research(context, None, None, execution)

    assert result.cancelled is True
    assert result.success is False
    assert adapter.text_calls == 0
    assert adapter.tool_calls == 0


def test_r8_constructors_share_config_derived_token_ceiling():
    from src.api.v1.endpoints import agent as agent_endpoint
    from src.bot.commands.research import ResearchCommand
    from src.agent.runtime.native_adapter import NativeRuntimeAdapter as NativeCls

    cfg = _cfg(agent_deep_research_budget=12345)
    assert research_token_budget_from_config(cfg) == 12345
    assert "research_token_budget_from_config" in inspect.getsource(
        agent_endpoint.agent_research
    )
    assert "research_token_budget_from_config" in inspect.getsource(
        ResearchCommand.execute
    )
    assert "research_token_budget_from_config" in inspect.getsource(
        NativeCls._run_research
    )

    adapter = _FakeResearchAdapter(
        text_responses=[
            _FakeResponse(
                content='{"questions":["Q1"]}',
                usage={"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
            )
        ]
    )
    result = _agent(adapter, cfg, token_budget=12345).research("q")
    assert result.budget_snapshot["limits"]["max_tokens"] == 12345


def test_r9_three_turn_cap_does_not_bill_a_fourth_subquestion_step():
    adapter = _FakeResearchAdapter(
        text_responses=[
            _FakeResponse(content='{"questions":["Q1","Q2"]}'),
            _FakeResponse(content="should not synthesise"),
        ],
        tool_responses=[_tool_loop_response(i) for i in range(8)],
    )
    result = _agent(
        adapter,
        _cfg(agent_mode_budget_specialist_max_llm_turns=3),
    ).research("Analyse 600519")

    assert result.success is False
    assert result.failure_reason == "budget_turns"
    assert result.timed_out is False
    assert result.cancelled is False
    assert result.budget_snapshot["used"]["llm_turns"] <= 3
    assert result.budget_snapshot["limits"]["max_llm_turns"] == 3
    assert adapter.text_calls == 1
    assert adapter.tool_calls <= 2
    assert adapter.text_calls + adapter.tool_calls <= 3


def test_r10_default_specialist_twelve_turn_cap_does_not_bill_a_thirteenth_call():
    adapter = _FakeResearchAdapter(
        text_responses=[
            _FakeResponse(content='{"questions":["Q1","Q2","Q3","Q4"]}'),
            _FakeResponse(content="should not synthesise"),
        ],
        tool_responses=(
            _four_step_sub_question_fill(1)
            + _four_step_sub_question_fill(5)
            + [_tool_loop_response(i) for i in range(20, 28)]
        ),
    )
    result = _agent(adapter, _cfg()).research("Analyse 600519")

    assert result.success is False
    assert result.failure_reason == "budget_turns"
    assert result.timed_out is False
    assert result.cancelled is False
    used = int(result.budget_snapshot["used"]["llm_turns"])
    assert used <= 12
    assert result.budget_snapshot["limits"]["max_llm_turns"] == 12
    assert adapter.text_calls == 1
    assert adapter.text_calls + adapter.tool_calls <= 12
    assert "remaining_max_steps" in inspect.getsource(
        ResearchAgent._research_sub_question
    )


def test_api_maps_budget_failure_to_success_false_with_stable_error():
    from src.api.v1.endpoints.agent import ResearchRequest, agent_research
    from src.agent.research import ResearchResult

    config = SimpleNamespace(
        litellm_model="gemini/test-model",
        agent_deep_research_budget=30000,
        agent_deep_research_timeout=180,
        is_agent_available=lambda: True,
        agent_mode_budget_enabled=True,
    )
    research_result = ResearchResult(
        success=False,
        report="partial markdown that must not count as complete",
        sub_questions=["Q1"],
        findings_count=1,
        total_tokens=40,
        error="Mode 'specialist' LLM turn budget exceeded: 1/1",
        failure_reason="budget_turns",
        budget_snapshot={"limits": {"max_llm_turns": 1}, "used": {"llm_turns": 1}, "breach": {"reason": "budget_turns"}},
    )

    async def fake_research(*_args, **_kwargs):
        return research_result

    async def _run():
        with (
            patch("src.api.v1.endpoints.agent.get_config", return_value=config),
            patch("src.api.v1.endpoints.agent._run_research_in_background", new=fake_research),
            patch("src.agent.factory.get_tool_registry", return_value=MagicMock()),
            patch("src.agent.llm_adapter.LLMToolAdapter", return_value=MagicMock()),
        ):
            return await agent_research(ResearchRequest(question="600519 risk"))

    response = asyncio.run(_run())
    assert response.success is False
    assert response.error == "agent_research_failed"
    assert response.failure_reason == "budget_turns"
    assert response.cancelled is False
    assert response.content == "partial markdown that must not count as complete"
    assert response.budget_snapshot["breach"]["reason"] == "budget_turns"
