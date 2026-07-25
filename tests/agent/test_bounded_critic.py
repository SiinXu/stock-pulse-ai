"""Bounded Critic contracts for the Native Multi pipeline."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()

from src.agent import critic
from src.agent.agents.decision_agent import DecisionAgent
from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import (
    AgentContext,
    AgentOpinion,
    StageFailureReason,
    StageResult,
    StageStatus,
)
from src.agent.runtime.guards import RuntimeGuardPolicy, StageFailurePolicy
from src.agent.soul import AGENT_SOUL_MARKER, AGENT_SOUL_SYSTEM_BLOCK
from src.agent.tools.registry import ToolRegistry
from src.config import Config
from src.core.config_registry import get_field_definition


def _stage_result(
    name: str,
    *,
    status: StageStatus = StageStatus.COMPLETED,
    raw_text: str = "ok",
    model: str = "test/model",
    tool_calls: list | None = None,
) -> StageResult:
    result = StageResult(
        stage_name=name,
        status=status,
        failure_reason=(
            StageFailureReason.STAGE_FAILURE
            if status == StageStatus.FAILED
            else None
        ),
    )
    result.meta.update({
        "raw_text": raw_text,
        "models_used": [model],
        "tool_calls_log": list(tool_calls or []),
    })
    return result


class _FixtureCritic:
    agent_name = "critic"
    max_steps = 1
    tool_names: list[str] = []

    def __init__(self, raw_output: str) -> None:
        self.raw_output = raw_output
        self.calls = 0

    def run(self, ctx: AgentContext, **_kwargs) -> StageResult:
        self.calls += 1
        ctx.meta["critic_trace"] = critic.parse_critic_output(self.raw_output)
        return _stage_result(
            "critic",
            raw_text=self.raw_output,
            model="test/critic",
        )


class _FixtureStage:
    max_steps = 1

    def __init__(self, agent_name: str, run_callback) -> None:
        self.agent_name = agent_name
        self._run_callback = run_callback
        self.calls = 0

    def run(self, ctx: AgentContext, **_kwargs) -> StageResult:
        self.calls += 1
        return self._run_callback(ctx, self.calls)


def _orchestrator(*, enabled: bool, skill_manager=None) -> AgentOrchestrator:
    config = SimpleNamespace(
        agent_critic_enabled=enabled,
        agent_orchestrator_timeout_s=0,
        agent_risk_override=True,
    )
    return AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=MagicMock(),
        config=config,
        skill_manager=skill_manager,
    )


@pytest.mark.parametrize(
    ("payload", "expected_verdict", "expected_validation"),
    [
        (
            {
                "verdict": "pass",
                "retry_targets": [],
                "reasons": ["Evidence is sufficient."],
                "missing_evidence": [],
            },
            "pass",
            "valid",
        ),
        (
            {
                "verdict": "retry",
                "retry_targets": ["intelligence"],
                "reasons": ["Material news evidence is missing."],
                "missing_evidence": ["Current issuer announcement coverage."],
            },
            "retry",
            "valid",
        ),
        (
            {
                "verdict": "fail_soft",
                "retry_targets": [],
                "reasons": ["The limitation cannot be closed by the whitelist."],
                "missing_evidence": ["Audited segment detail."],
            },
            "fail_soft",
            "valid",
        ),
        (
            {
                "verdict": "unknown",
                "retry_targets": [],
                "reasons": [],
                "missing_evidence": [],
            },
            "fail_soft",
            "invalid",
        ),
        ([], "fail_soft", "invalid"),
        (
            {
                "verdict": "retry",
                "retry_targets": ["risk"],
                "reasons": ["Try an unapproved stage."],
                "missing_evidence": [],
            },
            "fail_soft",
            "invalid",
        ),
    ],
)
def test_critic_output_contract_fails_closed(
    payload,
    expected_verdict,
    expected_validation,
) -> None:
    trace = critic.parse_critic_output(json.dumps(payload))

    assert trace["verdict"] == expected_verdict
    assert trace["validation_status"] == expected_validation
    assert trace["retry_budget_consumed"] == 0
    assert trace["retry_budget_remaining"] == 1


def test_critic_output_rejects_valid_object_wrapped_in_top_level_array() -> None:
    payload = {
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": ["Retry intelligence."],
        "missing_evidence": ["Current issuer evidence."],
    }

    trace = critic.parse_critic_output(json.dumps([payload]))

    assert trace["verdict"] == "fail_soft"
    assert trace["validation_status"] == "invalid"
    assert trace["requested_verdict"] is None
    assert trace["retry_targets_requested"] == []


def test_critic_output_accepts_one_fenced_top_level_object() -> None:
    payload = {
        "verdict": "pass",
        "retry_targets": [],
        "reasons": ["Evidence is sufficient."],
        "missing_evidence": [],
    }

    trace = critic.parse_critic_output(
        f"```json\n{json.dumps(payload)}\n```"
    )

    assert trace["verdict"] == "pass"
    assert trace["validation_status"] == "valid"


def test_critic_output_accepts_max_length_catalog_skill_id() -> None:
    skill_id = "s" * 128
    payload = {
        "verdict": "retry",
        "retry_targets": [f"skill:{skill_id}"],
        "reasons": ["Recheck the entered catalog skill."],
        "missing_evidence": ["Updated skill evidence."],
    }

    trace = critic.parse_critic_output(json.dumps(payload))

    assert trace["verdict"] == "retry"
    assert trace["validation_status"] == "valid"
    assert trace["retry_targets_requested"] == [f"skill:{skill_id}"]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "verdict": "retry",
            "retry_targets": ["intelligence"],
            "reasons": [],
            "missing_evidence": [],
        },
        {
            "verdict": "fail_soft",
            "retry_targets": [],
            "reasons": [],
            "missing_evidence": [],
        },
    ],
    ids=["retry-without-reason", "fail-soft-without-limitation"],
)
def test_non_pass_critic_output_requires_an_explicit_explanation(payload) -> None:
    trace = critic.parse_critic_output(json.dumps(payload))

    assert trace["verdict"] == "fail_soft"
    assert trace["validation_status"] == "invalid"
    assert trace["requested_verdict"] is None
    assert trace["retry_targets_requested"] == []
    assert trace["reasons"] == [
        "Critic output did not satisfy the bounded verdict contract."
    ]


@pytest.mark.parametrize(
    "invalid_targets",
    [
        ["skill:" + "MODEL_CONTROLLED_MARKER" * 300],
        [f"skill:MODEL_CONTROLLED_MARKER-{index}" for index in range(100)],
    ],
    ids=["oversized-target", "too-many-targets"],
)
def test_invalid_critic_output_drops_untrusted_requested_fields(
    invalid_targets,
) -> None:
    payload = {
        "verdict": "MODEL_CONTROLLED_MARKER" * 300,
        "retry_targets": invalid_targets,
        "reasons": ["Invalid request must not survive validation."],
        "missing_evidence": [],
    }

    trace = critic.parse_critic_output(json.dumps(payload))
    serialized_trace = json.dumps(trace)

    assert trace["verdict"] == "fail_soft"
    assert trace["validation_status"] == "invalid"
    assert trace["requested_verdict"] is None
    assert trace["retry_targets_requested"] == []
    assert "MODEL_CONTROLLED_MARKER" not in serialized_trace
    assert len(serialized_trace) < 1_000


def test_unavailable_runtime_reason_displaces_a_model_reason() -> None:
    ctx = AgentContext(query="Analyze", stock_code="600519")
    ctx.meta["critic_trace"] = critic.parse_critic_output(json.dumps({
        "verdict": "retry",
        "retry_targets": ["skill:missing"],
        "reasons": [f"Model reason {index}" for index in range(5)],
        "missing_evidence": [],
    }))
    runtime_reason = "The requested catalog stage is unavailable."

    trace = critic.mark_retry_unavailable(
        ctx,
        "skill:missing",
        reason=runtime_reason,
    )

    assert len(trace["reasons"]) == 5
    assert trace["reasons"][-1] == runtime_reason
    assert "Model reason 4" not in trace["reasons"]


def test_failed_retry_runtime_reason_displaces_a_model_reason() -> None:
    ctx = AgentContext(query="Analyze", stock_code="600519")
    ctx.meta["critic_trace"] = critic.parse_critic_output(json.dumps({
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": [f"Model reason {index}" for index in range(5)],
        "missing_evidence": [],
    }))
    assert critic.start_retry(ctx, "intelligence") is not None

    trace = critic.finish_retry(ctx, completed=False)

    assert len(trace["reasons"]) == 5
    assert trace["reasons"][-1] == (
        "Whitelisted retry did not complete; Decision must preserve the limitation."
    )
    assert "Model reason 4" not in trace["reasons"]


def test_critic_prompt_has_one_soul_and_no_tool_surface() -> None:
    agent = critic.BoundedCriticAgent(
        tool_registry=ToolRegistry(),
        llm_adapter=MagicMock(),
    )
    ctx = AgentContext(query="Analyze", stock_code="600519")

    messages = agent._build_messages(ctx)

    assert agent._filtered_registry().list_names() == []
    system_prompt = messages[0]["content"]
    assert system_prompt.endswith(f"\n\n{AGENT_SOUL_SYSTEM_BLOCK}")
    assert system_prompt.count(AGENT_SOUL_MARKER) == 1
    assert "retry must request exactly one target and include at least one reason" in (
        system_prompt
    )
    assert "include at least one\nreason or missing_evidence item" in system_prompt


@pytest.mark.parametrize(
    ("enabled", "response_mode"),
    [(False, None), (True, "chat")],
)
def test_pipeline_skips_critic_when_disabled_or_chat(
    monkeypatch,
    enabled,
    response_mode,
) -> None:
    orch = _orchestrator(enabled=enabled)
    decision = _FixtureStage(
        "decision",
        lambda ctx, _call: (
            ctx.set_data("final_dashboard_raw", "final")
            or _stage_result("decision", raw_text="final")
        ),
    )
    ctx = AgentContext(query="Analyze", stock_code="600519")
    if response_mode is not None:
        ctx.meta["response_mode"] = response_mode

    def _unexpected_critic(**_kwargs):
        raise AssertionError("Critic must not be constructed")

    monkeypatch.setattr(critic, "BoundedCriticAgent", _unexpected_critic)
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [decision])

    result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success is True
    assert decision.calls == 1
    assert [item.stage_name for item in result.stats.stage_results] == ["decision"]


def test_pipeline_keeps_critic_at_one_step_when_global_limit_is_raised(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    orch.max_steps = 25
    fixture_critic = _FixtureCritic(json.dumps({
        "verdict": "pass",
        "retry_targets": [],
        "reasons": ["Evidence is sufficient."],
        "missing_evidence": [],
    }))

    def _decision(ctx: AgentContext, _call: int) -> StageResult:
        ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [decision])

    result = orch._execute_pipeline(
        AgentContext(query="Analyze", stock_code="600519"),
        parse_dashboard=False,
    )

    assert result.success is True
    assert fixture_critic.max_steps == critic.CRITIC_MAX_STEPS
    assert fixture_critic.calls == 1


def test_critic_budget_skip_preserves_decision_stage_minimum(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    orch.config.agent_orchestrator_timeout_s = 100
    ctx = AgentContext(query="Analyze", stock_code="600519")
    events = []
    clock = {"now": 0.0}

    def _technical(_ctx: AgentContext, _call: int) -> StageResult:
        clock["now"] = 80.0
        return _stage_result("technical", raw_text="technical")

    technical = _FixtureStage("technical", _technical)

    def _decision(run_ctx: AgentContext, _call: int) -> StageResult:
        assert run_ctx.meta["critic_trace"]["validation_status"] == "budget_skipped"
        run_ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)

    def _unexpected_critic(**_kwargs):
        raise AssertionError("Critic must not be constructed without its budget")

    monkeypatch.setattr(critic, "BoundedCriticAgent", _unexpected_critic)
    monkeypatch.setattr(
        orch,
        "_build_agent_chain",
        lambda _ctx: [technical, decision],
    )

    with patch("src.agent.orchestrator.time.time", side_effect=lambda: clock["now"]):
        result = orch._execute_pipeline(
            ctx,
            parse_dashboard=False,
            progress_callback=events.append,
        )

    critic_result = next(
        item for item in result.stats.stage_results if item.stage_name == "critic"
    )
    assert result.success is True
    assert decision.calls == 1
    assert critic_result.status == StageStatus.FAILED
    assert critic_result.failure_reason == StageFailureReason.BUDGET_SKIP
    assert critic_result.meta["critic"]["validation_status"] == "budget_skipped"
    assert ctx.meta["critic_trace"]["retry_budget_consumed"] == 0
    assert ctx.meta["critic_trace"]["retry_budget_remaining"] == 1
    assert ctx.meta["degraded_stages"][-1]["non_critical"] is True
    assert ctx.meta["degraded_events"][-1] == {
        "stage": "critic",
        "reason": "budget_skip",
        "boundary": "before_stage",
    }
    assert [event["type"] for event in events].count("critic_verdict") == 1


def test_retry_budget_skip_preserves_decision_without_consuming_budget(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    orch.config.agent_orchestrator_timeout_s = 100
    ctx = AgentContext(query="Analyze", stock_code="600519")
    clock = {"now": 0.0}

    def _intel(run_ctx: AgentContext, call: int) -> StageResult:
        run_ctx.add_opinion(AgentOpinion(
            agent_name="intel",
            signal="hold",
            confidence=0.6,
            reasoning=f"intelligence-{call}",
        ))
        return _stage_result("intel", raw_text=f"intel-{call}")

    intel = _FixtureStage("intel", _intel)
    retry_payload = {
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": ["Retry intelligence once."],
        "missing_evidence": ["Current issuer evidence."],
    }

    def _critic_run(run_ctx: AgentContext, _call: int) -> StageResult:
        run_ctx.meta["critic_trace"] = critic.parse_critic_output(
            json.dumps(retry_payload)
        )
        clock["now"] = 80.0
        return _stage_result("critic", raw_text=json.dumps(retry_payload))

    fixture_critic = _FixtureStage("critic", _critic_run)

    def _decision(run_ctx: AgentContext, _call: int) -> StageResult:
        trace = run_ctx.meta["critic_trace"]
        assert trace["verdict"] == "fail_soft"
        assert trace["retry_status"] == "unavailable"
        run_ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [intel, decision])

    with patch("src.agent.orchestrator.time.time", side_effect=lambda: clock["now"]):
        result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success is True
    assert intel.calls == 1
    assert decision.calls == 1
    assert ctx.meta["critic_trace"]["retry_budget_consumed"] == 0
    assert ctx.meta["critic_trace"]["retry_budget_remaining"] == 1
    assert ctx.meta["critic_trace"]["reasons"][-1] == (
        "Critic retry was skipped to preserve the minimum Decision stage budget."
    )


def test_critic_and_retry_timeouts_exclude_decision_reserve(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    orch.config.agent_orchestrator_timeout_s = 100

    def _intel(run_ctx: AgentContext, call: int) -> StageResult:
        run_ctx.add_opinion(AgentOpinion(
            agent_name="intel",
            signal="hold",
            confidence=0.6,
            reasoning=f"intelligence-{call}",
        ))
        return _stage_result("intel", raw_text=f"intel-{call}")

    intel = _FixtureStage("intel", _intel)
    fixture_critic = _FixtureCritic(json.dumps({
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": ["Retry intelligence once."],
        "missing_evidence": ["Current issuer evidence."],
    }))

    def _decision(ctx: AgentContext, _call: int) -> StageResult:
        ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [intel, decision])

    observed_timeouts = []
    execute_isolated_stage = orch._execute_isolated_stage

    def _capture_timeout(
        agent,
        run_ctx,
        *,
        stage_name,
        progress_callback,
        timeout_seconds,
        cancelled_check,
    ):
        observed_timeouts.append((stage_name, timeout_seconds))
        return execute_isolated_stage(
            agent,
            run_ctx,
            stage_name=stage_name,
            progress_callback=progress_callback,
            timeout_seconds=timeout_seconds,
            cancelled_check=cancelled_check,
        )

    monkeypatch.setattr(orch, "_execute_isolated_stage", _capture_timeout)

    with patch("src.agent.orchestrator.time.time", return_value=0.0):
        result = orch._execute_pipeline(
            AgentContext(query="Analyze", stock_code="600519"),
            parse_dashboard=False,
        )

    assert result.success is True
    assert observed_timeouts == [
        ("intel", 100.0),
        ("critic", 84.0),
        ("intel", 84.0),
        ("decision", 100.0),
    ]


@pytest.mark.parametrize(
    ("critic_payload", "expected_verdict", "expected_validation"),
    [
        (
            {
                "verdict": "pass",
                "retry_targets": [],
                "reasons": ["Enough evidence."],
                "missing_evidence": [],
            },
            "pass",
            "valid",
        ),
        (
            {
                "verdict": "fail_soft",
                "retry_targets": [],
                "reasons": ["Keep a limitation."],
                "missing_evidence": ["Missing issuer detail."],
            },
            "fail_soft",
            "valid",
        ),
        (
            {
                "verdict": "retry",
                "retry_targets": ["skill:not_in_catalog"],
                "reasons": ["Request an unavailable target."],
                "missing_evidence": [],
            },
            "fail_soft",
            "valid",
        ),
        ({"not": "the contract"}, "fail_soft", "invalid"),
    ],
)
def test_pipeline_pass_fail_soft_invalid_and_unavailable_do_not_retry(
    monkeypatch,
    critic_payload,
    expected_verdict,
    expected_validation,
) -> None:
    orch = _orchestrator(enabled=True)
    fixture_critic = _FixtureCritic(json.dumps(critic_payload))
    seen_trace = {}

    def _decision(ctx: AgentContext, _call: int) -> StageResult:
        seen_trace.update(ctx.meta["critic_trace"])
        ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [decision])

    result = orch._execute_pipeline(
        AgentContext(query="Analyze", stock_code="600519"),
        parse_dashboard=False,
    )

    assert result.success is True
    assert fixture_critic.calls == 1
    assert decision.calls == 1
    assert seen_trace["verdict"] == expected_verdict
    assert seen_trace["validation_status"] == expected_validation
    assert seen_trace["retry_budget_consumed"] == 0
    assert [item.stage_name for item in result.stats.stage_results] == [
        "critic",
        "decision",
    ]


def test_missing_intelligence_retries_once_replaces_context_and_keeps_authority(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    ctx = AgentContext(query="Analyze", stock_code="600519")
    events = []

    technical = _FixtureStage(
        "technical",
        lambda run_ctx, _call: (
            run_ctx.add_opinion(AgentOpinion(
                agent_name="technical",
                signal="hold",
                confidence=0.6,
                reasoning="Technical fixture.",
            ))
            or _stage_result("technical", raw_text="technical")
        ),
    )

    def _intel(run_ctx: AgentContext, call: int) -> StageResult:
        if call == 2:
            assert not any(op.agent_name == "intel" for op in run_ctx.opinions)
            assert "intel_opinion" not in run_ctx.data
            assert not any(
                flag.get("category") == "intel" for flag in run_ctx.risk_flags
            )
        label = "fresh" if call == 2 else "stale"
        run_ctx.add_opinion(AgentOpinion(
            agent_name="intel",
            signal="hold",
            confidence=0.7,
            reasoning=f"{label} intelligence",
        ))
        run_ctx.set_data("intel_opinion", {"round": call})
        run_ctx.add_risk_flag("intel", f"{label} risk")
        return _stage_result(
            "intel",
            raw_text=f"intel-{call}",
            tool_calls=[{"call": f"intel-{call}"}],
        )

    intel = _FixtureStage("intel", _intel)
    fixture_critic = _FixtureCritic(json.dumps({
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": ["Current intelligence is incomplete."],
        "missing_evidence": ["Latest issuer announcement."],
    }))

    def _decision(run_ctx: AgentContext, _call: int) -> StageResult:
        intel_opinions = [
            op for op in run_ctx.opinions if op.agent_name == "intel"
        ]
        assert [op.reasoning for op in intel_opinions] == ["fresh intelligence"]
        assert run_ctx.get_data("intel_opinion") == {"round": 2}
        assert [
            flag["description"]
            for flag in run_ctx.risk_flags
            if flag.get("category") == "intel"
        ] == ["fresh risk"]
        assert run_ctx.meta["critic_trace"]["retry_status"] == "completed"
        run_ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)
    strategy_process = MagicMock(wraps=orch.strategy_engine.process)
    orch.strategy_engine.process = strategy_process
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(
        orch,
        "_build_agent_chain",
        lambda _ctx: [technical, intel, decision],
    )

    result = orch._execute_pipeline(
        ctx,
        parse_dashboard=False,
        progress_callback=events.append,
    )

    assert result.success is True
    assert intel.calls == 2
    assert fixture_critic.calls == 1
    assert decision.calls == 1
    assert strategy_process.call_count == 1
    assert [item.stage_name for item in result.stats.stage_results] == [
        "technical",
        "intel",
        "critic",
        "intel",
        "decision",
    ]
    assert result.stats.stage_results[1].meta["raw_text"] == "intel-1"
    assert result.stats.stage_results[3].meta["raw_text"] == "intel-2"
    assert result.tool_calls_log == [
        {"call": "intel-1"},
        {"call": "intel-2"},
    ]
    assert ctx.meta["critic_trace"]["retry_budget_consumed"] == 1
    assert ctx.meta["critic_trace"]["retry_budget_remaining"] == 0
    assert [event["type"] for event in events].count("critic_verdict") == 1
    assert [event["type"] for event in events].count("critic_retry_start") == 1
    assert [event["type"] for event in events].count("critic_retry_done") == 1
    retry_done = next(
        event for event in events if event["type"] == "critic_retry_done"
    )
    assert retry_done["retry_targets_executed"] == ["intelligence"]
    assert retry_done["retry_budget_consumed"] == 1


def test_retry_completion_updates_critic_stats_before_cancellation(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    ctx = AgentContext(query="Analyze", stock_code="600519")
    events = []
    cancelled = {"value": False}

    def _intel(run_ctx: AgentContext, call: int) -> StageResult:
        run_ctx.add_opinion(AgentOpinion(
            agent_name="intel",
            signal="hold",
            confidence=0.6,
            reasoning=f"intelligence-{call}",
        ))
        return _stage_result("intel", raw_text=f"intel-{call}")

    intel = _FixtureStage("intel", _intel)
    fixture_critic = _FixtureCritic(json.dumps({
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": ["Retry intelligence once."],
        "missing_evidence": ["Current issuer evidence."],
    }))

    def _unexpected_decision(_ctx: AgentContext, _call: int) -> StageResult:
        raise AssertionError("Decision must not run after cancellation")

    decision = _FixtureStage("decision", _unexpected_decision)

    def _progress(event) -> None:
        events.append(event)
        if event["type"] == "critic_retry_done":
            cancelled["value"] = True

    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(
        orch,
        "_build_agent_chain",
        lambda _ctx: [intel, decision],
    )

    result = orch._execute_pipeline(
        ctx,
        parse_dashboard=False,
        progress_callback=_progress,
        cancelled_check=lambda: cancelled["value"],
    )

    critic_result = next(
        item for item in result.stats.stage_results if item.stage_name == "critic"
    )
    retry_done = next(event for event in events if event["type"] == "critic_retry_done")
    assert result.cancelled is True
    assert decision.calls == 0
    assert ctx.meta["critic_trace"]["retry_status"] == "completed"
    assert critic_result.meta["critic"]["retry_status"] == "completed"
    assert retry_done["retry_status"] == "completed"


def test_initial_critic_trace_is_finalized_before_cancellation(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    ctx = AgentContext(query="Analyze", stock_code="600519")
    events = []
    cancelled = {"value": False}
    fixture_critic = _FixtureCritic(json.dumps({
        "verdict": "pass",
        "retry_targets": [],
        "reasons": ["Evidence is sufficient."],
        "missing_evidence": [],
    }))

    def _unexpected_decision(_ctx: AgentContext, _call: int) -> StageResult:
        raise AssertionError("Decision must not run after cancellation")

    decision = _FixtureStage("decision", _unexpected_decision)

    def _progress(event) -> None:
        events.append(event)
        if event["type"] == "stage_done" and event["stage"] == "critic":
            cancelled["value"] = True

    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [decision])

    result = orch._execute_pipeline(
        ctx,
        parse_dashboard=False,
        progress_callback=_progress,
        cancelled_check=lambda: cancelled["value"],
    )

    critic_result = next(
        item for item in result.stats.stage_results if item.stage_name == "critic"
    )
    verdict_events = [
        event for event in events if event["type"] == "critic_verdict"
    ]
    assert result.cancelled is True
    assert decision.calls == 0
    assert ctx.meta["critic_trace"]["verdict"] == "pass"
    assert critic_result.meta["critic"]["verdict"] == "pass"
    assert len(verdict_events) == 1
    assert verdict_events[0]["verdict"] == "pass"


def test_retry_completion_updates_critic_stats_before_global_timeout(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    orch.config.agent_orchestrator_timeout_s = 100
    ctx = AgentContext(query="Analyze", stock_code="600519")
    events = []
    clock = {"now": 0.0}

    def _intel(run_ctx: AgentContext, call: int) -> StageResult:
        run_ctx.add_opinion(AgentOpinion(
            agent_name="intel",
            signal="hold",
            confidence=0.6,
            reasoning=f"intelligence-{call}",
        ))
        if call == 2:
            clock["now"] = 101.0
        return _stage_result("intel", raw_text=f"intel-{call}")

    intel = _FixtureStage("intel", _intel)
    fixture_critic = _FixtureCritic(json.dumps({
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": ["Retry intelligence once."],
        "missing_evidence": ["Current issuer evidence."],
    }))

    def _unexpected_decision(_ctx: AgentContext, _call: int) -> StageResult:
        raise AssertionError("Decision must not run after the global timeout")

    decision = _FixtureStage("decision", _unexpected_decision)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(
        orch,
        "_build_agent_chain",
        lambda _ctx: [intel, decision],
    )

    with patch("src.agent.orchestrator.time.time", side_effect=lambda: clock["now"]):
        result = orch._execute_pipeline(
            ctx,
            parse_dashboard=False,
            progress_callback=events.append,
        )

    critic_result = next(
        item for item in result.stats.stage_results if item.stage_name == "critic"
    )
    retry_done = next(event for event in events if event["type"] == "critic_retry_done")
    assert result.timed_out is True
    assert decision.calls == 0
    assert ctx.meta["critic_trace"]["retry_status"] == "completed"
    assert critic_result.meta["critic"]["retry_status"] == "completed"
    assert retry_done["retry_status"] == "completed"


def test_failed_initial_critic_trace_is_finalized_before_global_timeout(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    orch.config.agent_orchestrator_timeout_s = 100
    ctx = AgentContext(query="Analyze", stock_code="600519")
    events = []
    clock = {"now": 0.0}

    def _fail_critic(_ctx: AgentContext, _call: int) -> StageResult:
        clock["now"] = 101.0
        return _stage_result("critic", status=StageStatus.FAILED)

    fixture_critic = _FixtureStage("critic", _fail_critic)

    def _unexpected_decision(_ctx: AgentContext, _call: int) -> StageResult:
        raise AssertionError("Decision must not run after the global timeout")

    decision = _FixtureStage("decision", _unexpected_decision)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [decision])

    with patch("src.agent.orchestrator.time.time", side_effect=lambda: clock["now"]):
        result = orch._execute_pipeline(
            ctx,
            parse_dashboard=False,
            progress_callback=events.append,
        )

    critic_result = next(
        item for item in result.stats.stage_results if item.stage_name == "critic"
    )
    verdict_events = [
        event for event in events if event["type"] == "critic_verdict"
    ]
    assert result.timed_out is True
    assert decision.calls == 0
    assert ctx.meta["critic_trace"]["verdict"] == "fail_soft"
    assert ctx.meta["critic_trace"]["validation_status"] == "stage_failed"
    assert critic_result.meta["critic"]["verdict"] == "fail_soft"
    assert len(verdict_events) == 1
    assert verdict_events[0]["validation_status"] == "stage_failed"


def test_failed_initial_critic_is_fail_soft_under_fail_fast_policy(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    orch.runtime_guard_policy = RuntimeGuardPolicy(
        stage_failure_policy=StageFailurePolicy.FAIL_FAST,
    )
    ctx = AgentContext(query="Analyze", stock_code="600519")
    fixture_critic = _FixtureStage(
        "critic",
        lambda _ctx, _call: _stage_result(
            "critic",
            status=StageStatus.FAILED,
        ),
    )

    def _decision(run_ctx: AgentContext, _call: int) -> StageResult:
        assert run_ctx.meta["critic_trace"]["verdict"] == "fail_soft"
        assert run_ctx.meta["critic_trace"]["validation_status"] == "stage_failed"
        run_ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [decision])

    result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success is True
    assert decision.calls == 1
    assert ctx.meta["degraded_stages"][-1] == {
        "stage_name": "critic",
        "status": "failed",
        "non_critical": True,
    }


def test_failed_retry_preserves_prior_context_and_becomes_fail_soft(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    orch.runtime_guard_policy = RuntimeGuardPolicy(
        stage_failure_policy=StageFailurePolicy.FAIL_FAST,
    )
    ctx = AgentContext(query="Analyze", stock_code="600519")

    def _intel(run_ctx: AgentContext, call: int) -> StageResult:
        run_ctx.add_opinion(AgentOpinion(
            agent_name="intel",
            signal="hold",
            confidence=0.5,
            reasoning=f"intel-{call}",
        ))
        run_ctx.set_data("intel_opinion", {"round": call})
        return _stage_result(
            "intel",
            status=(
                StageStatus.FAILED if call == 2 else StageStatus.COMPLETED
            ),
            raw_text=f"intel-{call}",
            tool_calls=[{"call": f"intel-{call}"}],
        )

    intel = _FixtureStage("intel", _intel)
    fixture_critic = _FixtureCritic(json.dumps({
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": ["Retry intelligence once."],
        "missing_evidence": ["Fresh evidence."],
    }))

    def _decision(run_ctx: AgentContext, _call: int) -> StageResult:
        assert [
            op.reasoning for op in run_ctx.opinions if op.agent_name == "intel"
        ] == ["intel-1"]
        assert run_ctx.get_data("intel_opinion") == {"round": 1}
        assert run_ctx.meta["critic_trace"]["verdict"] == "fail_soft"
        assert run_ctx.meta["critic_trace"]["retry_status"] == "failed"
        run_ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(
        orch,
        "_build_agent_chain",
        lambda _ctx: [intel, decision],
    )

    result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success is True
    assert intel.calls == 2
    assert decision.calls == 1
    assert ctx.get_data("intel_opinion") == {"round": 1}
    assert ctx.meta["critic_trace"]["retry_budget_consumed"] == 1
    assert result.stats.stage_results[0].status == StageStatus.COMPLETED
    assert result.stats.stage_results[2].status == StageStatus.FAILED
    assert result.tool_calls_log == [
        {"call": "intel-1"},
        {"call": "intel-2"},
    ]


def test_retry_timeout_preserves_prior_context_and_failure_reason(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    ctx = AgentContext(query="Analyze", stock_code="600519")

    def _intel(run_ctx: AgentContext, _call: int) -> StageResult:
        run_ctx.add_opinion(AgentOpinion(
            agent_name="intel",
            signal="hold",
            confidence=0.5,
            reasoning="original intelligence",
        ))
        run_ctx.set_data("intel_opinion", {"round": 1})
        return _stage_result("intel", raw_text="intel-1")

    intel = _FixtureStage("intel", _intel)
    fixture_critic = _FixtureCritic(json.dumps({
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": ["Retry intelligence once."],
        "missing_evidence": ["Fresh evidence."],
    }))

    def _decision(run_ctx: AgentContext, _call: int) -> StageResult:
        assert [
            op.reasoning for op in run_ctx.opinions if op.agent_name == "intel"
        ] == ["original intelligence"]
        assert run_ctx.get_data("intel_opinion") == {"round": 1}
        run_ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(
        orch,
        "_build_agent_chain",
        lambda _ctx: [intel, decision],
    )
    execute_isolated_stage = orch._execute_isolated_stage
    intel_entries = 0

    def _execute_with_retry_timeout(agent, run_ctx, *, stage_name, **kwargs):
        nonlocal intel_entries
        if stage_name == "intel":
            intel_entries += 1
            if intel_entries == 2:
                raise TimeoutError("retry timed out")
        return execute_isolated_stage(
            agent,
            run_ctx,
            stage_name=stage_name,
            **kwargs,
        )

    monkeypatch.setattr(orch, "_execute_isolated_stage", _execute_with_retry_timeout)

    result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success is True
    assert intel.calls == 1
    assert decision.calls == 1
    retry_result = result.stats.stage_results[2]
    assert retry_result.stage_name == "intel"
    assert retry_result.status == StageStatus.FAILED
    assert retry_result.failure_reason == StageFailureReason.TIMEOUT
    assert ctx.meta["critic_trace"]["verdict"] == "fail_soft"
    assert ctx.meta["critic_trace"]["retry_status"] == "failed"
    assert {
        "stage": "intel",
        "reason": "timeout",
        "boundary": "during_stage",
    } in ctx.meta["degraded_events"]


def test_skill_retry_resolution_requires_catalog_and_prior_entry() -> None:
    skill_agent = SimpleNamespace(agent_name="skill_bull_trend")
    manager = SimpleNamespace(
        get=lambda skill_id: object() if skill_id == "bull_trend" else None
    )
    entered = [_stage_result("skill_bull_trend")]

    assert critic.resolve_retry_source_agent(
        "skill:bull_trend",
        agents=[skill_agent],
        prior_results=entered,
        skill_manager=manager,
    ) is skill_agent
    assert critic.resolve_retry_source_agent(
        "skill:unknown",
        agents=[skill_agent],
        prior_results=entered,
        skill_manager=manager,
    ) is None
    assert critic.resolve_retry_source_agent(
        "skill:bull_trend",
        agents=[skill_agent],
        prior_results=[],
        skill_manager=manager,
    ) is None


def test_skill_retry_with_invalid_signal_preserves_original_evidence(
    monkeypatch,
) -> None:
    manager = SimpleNamespace(
        get=lambda skill_id: object() if skill_id == "bull_trend" else None
    )
    orch = _orchestrator(enabled=True, skill_manager=manager)
    ctx = AgentContext(query="Analyze", stock_code="600519")

    def _skill(run_ctx: AgentContext, call: int) -> StageResult:
        if call == 2:
            assert not any(
                opinion.agent_name == "skill_bull_trend"
                for opinion in run_ctx.opinions
            )
        run_ctx.add_opinion(AgentOpinion(
            agent_name="skill_bull_trend",
            signal="buy" if call == 1 else "not-a-canonical-signal",
            confidence=0.7,
            reasoning=f"skill evidence {call}",
        ))
        return _stage_result("skill_bull_trend", raw_text=f"skill-{call}")

    skill = _FixtureStage("skill_bull_trend", _skill)
    fixture_critic = _FixtureCritic(json.dumps({
        "verdict": "retry",
        "retry_targets": ["skill:bull_trend"],
        "reasons": ["Retry the selected Skill once."],
        "missing_evidence": ["A canonical Skill signal."],
    }))

    def _decision(run_ctx: AgentContext, _call: int) -> StageResult:
        skill_opinions = [
            opinion
            for opinion in run_ctx.opinions
            if opinion.agent_name == "skill_bull_trend"
        ]
        assert [opinion.reasoning for opinion in skill_opinions] == [
            "skill evidence 1"
        ]
        assert run_ctx.meta["critic_trace"]["verdict"] == "fail_soft"
        assert run_ctx.meta["critic_trace"]["retry_status"] == "failed"
        run_ctx.set_data("final_dashboard_raw", "final")
        return _stage_result("decision", raw_text="final")

    decision = _FixtureStage("decision", _decision)
    strategy_process = MagicMock(wraps=orch.strategy_engine.process)
    orch.strategy_engine.process = strategy_process
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: fixture_critic,
    )
    monkeypatch.setattr(
        orch,
        "_build_agent_chain",
        lambda _ctx: [skill, decision],
    )

    result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success is True
    assert skill.calls == 2
    assert decision.calls == 1
    assert strategy_process.call_count == 1
    assert result.stats.stage_results[2].stage_name == "skill_bull_trend"
    assert result.stats.stage_results[2].status == StageStatus.FAILED
    assert result.stats.stage_results[2].failure_reason == (
        StageFailureReason.STAGE_FAILURE
    )


def test_decision_prompt_treats_critic_trace_as_limitations_only() -> None:
    agent = DecisionAgent(tool_registry=ToolRegistry(), llm_adapter=MagicMock())
    ctx = AgentContext(query="Analyze", stock_code="600519")
    ctx.meta["critic_trace"] = critic.parse_critic_output(json.dumps({
        "verdict": "fail_soft",
        "retry_targets": [],
        "reasons": ["Evidence remains incomplete."],
        "missing_evidence": ["Current announcement."],
    }))

    prompt = agent.build_user_message(ctx)

    assert "Bounded Critic Trace (limitations only)" in prompt
    assert "Evidence remains incomplete." in prompt
    assert "Do not treat this trace as a strategy opinion" in prompt


def test_critic_config_defaults_off_loads_env_and_is_registered() -> None:
    with patch.dict(os.environ, {"STOCK_LIST": "600519"}, clear=True):
        default_config = Config._load_from_env()
    with patch.dict(
        os.environ,
        {"STOCK_LIST": "600519", "AGENT_CRITIC_ENABLED": "true"},
        clear=True,
    ):
        enabled_config = Config._load_from_env()

    field = get_field_definition("AGENT_CRITIC_ENABLED")
    assert default_config.agent_critic_enabled is False
    assert enabled_config.agent_critic_enabled is True
    assert field["default_value"] == "false"
    assert field["data_type"] == "boolean"
    assert field["help_key"] == "settings.agent.AGENT_CRITIC_ENABLED"
