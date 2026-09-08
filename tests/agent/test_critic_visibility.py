"""Critic pass/revision visibility on reports, events, and evidence chain."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent import critic
from src.agent.observability import AgentEventType, reset_span_state_for_tests
from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import (
    AgentContext,
    AgentOpinion,
    StageResult,
    StageStatus,
)
from src.agent.tools.registry import ToolRegistry
from src.analyzer import AnalysisResult
from src.report_language import append_critic_lines, get_report_labels
from src.services.evidence_chain_service import build_evidence_chain_package
from src.services.report_mode import get_mode_limits
from src.services.report_renderer import render
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)
from src.config import Config
from src.services.run_flow import build_history_run_flow_snapshot


def _stage_result(name: str, *, status: StageStatus = StageStatus.COMPLETED) -> StageResult:
    result = StageResult(stage_name=name, status=status)
    result.meta.update({"raw_text": "ok", "models_used": ["test/model"], "tool_calls_log": []})
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
        return _stage_result("critic")


class _FixtureStage:
    max_steps = 1

    def __init__(self, agent_name: str, run_callback) -> None:
        self.agent_name = agent_name
        self._run_callback = run_callback
        self.calls = 0

    def run(self, ctx: AgentContext, **_kwargs) -> StageResult:
        self.calls += 1
        return self._run_callback(ctx, self.calls)


def _orchestrator(*, enabled: bool, max_iters: int = 1) -> AgentOrchestrator:
    config = SimpleNamespace(
        agent_critic_enabled=enabled,
        agent_critic_max_iters=max_iters,
        agent_orchestrator_timeout_s=0,
        agent_risk_override=True,
    )
    return AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=MagicMock(),
        config=config,
    )


def _pass_payload() -> str:
    return json.dumps({
        "verdict": "pass",
        "retry_targets": [],
        "reasons": ["Evidence is sufficient."],
        "missing_evidence": [],
    })


def _retry_payload() -> str:
    return json.dumps({
        "verdict": "retry",
        "retry_targets": ["intelligence"],
        "reasons": ["Current intelligence is incomplete."],
        "missing_evidence": ["Latest issuer announcement."],
    })


def _fail_soft_payload() -> str:
    return json.dumps({
        "verdict": "fail_soft",
        "retry_targets": [],
        "reasons": ["Issuer filings remain incomplete."],
        "missing_evidence": ["Audited segment detail."],
    })


def _decision_with_dashboard(ctx: AgentContext, _call: int) -> StageResult:
    ctx.set_data(
        "final_dashboard",
        {
            "decision_type": "hold",
            "analysis_summary": "hold for now",
            "dashboard": {"phase_decision": {"data_limitations": []}},
        },
    )
    return _stage_result("decision")


def _phase_events(snapshot: dict) -> list[dict]:
    return [
        event
        for event in snapshot.get("agent_events") or []
        if event.get("event_type") in {
            AgentEventType.PHASE_START.value,
            AgentEventType.PHASE_END.value,
        }
    ]


@pytest.fixture(autouse=True)
def _reset_spans():
    reset_span_state_for_tests()
    yield
    reset_span_state_for_tests()


def test_pass_without_revision_is_visible_on_dashboard(monkeypatch) -> None:
    orch = _orchestrator(enabled=True)
    fixture_critic = _FixtureCritic(_pass_payload())
    decision = _FixtureStage("decision", _decision_with_dashboard)
    monkeypatch.setattr(critic, "BoundedCriticAgent", lambda **_kwargs: fixture_critic)
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [decision])
    ctx = AgentContext(query="Analyze", stock_code="600519")

    result = orch._execute_pipeline(ctx, parse_dashboard=True)

    assert result.success is True
    appendix = (ctx.get_data("final_dashboard") or {}).get("dashboard", {}).get("critic")
    assert appendix is not None
    assert appendix["enabled"] is True
    assert appendix["ran"] is True
    assert appendix["verdict"] == "pass"
    assert appendix["convergence_status"] == "pass"
    assert appendix["revision_occurred"] is False
    assert appendix["iteration_consumed"] == 0
    assert "Critic passed without requesting a revision." in appendix["summary"]
    assert len(appendix["summary"]) <= 300


def test_one_retry_revision_is_visible_on_dashboard(monkeypatch) -> None:
    orch = _orchestrator(enabled=True)
    ctx = AgentContext(query="Analyze", stock_code="600519")

    def _intel(run_ctx: AgentContext, call: int) -> StageResult:
        run_ctx.add_opinion(AgentOpinion(
            agent_name="intel",
            signal="hold",
            confidence=0.7,
            reasoning=f"intelligence-{call}",
        ))
        return _stage_result("intel")

    intel = _FixtureStage("intel", _intel)
    fixture_critic = _FixtureCritic(_retry_payload())
    decision = _FixtureStage("decision", _decision_with_dashboard)
    monkeypatch.setattr(critic, "BoundedCriticAgent", lambda **_kwargs: fixture_critic)
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [intel, decision])

    result = orch._execute_pipeline(ctx, parse_dashboard=True)

    assert result.success is True
    appendix = (ctx.get_data("final_dashboard") or {}).get("dashboard", {}).get("critic")
    assert appendix["enabled"] is True
    assert appendix["revision_occurred"] is True
    assert appendix["iteration_consumed"] == 1
    assert appendix["verdict"] in {"pass", "retry", "fail_soft"}
    assert appendix["convergence_status"] in {
        "converged", "not_converged", "unavailable",
    }


@pytest.mark.parametrize(
    ("builder", "expected_convergence", "expected_verdict"),
    [
        (
            lambda ctx: critic.record_critic_budget_skip(ctx),
            "budget_skipped",
            "fail_soft",
        ),
        (
            lambda ctx: critic.record_critic_stage_failure(ctx),
            "stage_failed",
            "fail_soft",
        ),
        (
            lambda ctx: critic.mark_convergence_unavailable(ctx, "Recheck unavailable."),
            "unavailable",
            "fail_soft",
        ),
    ],
)
def test_fail_soft_unavailable_budget_and_stage_failed_summaries(
    builder,
    expected_convergence,
    expected_verdict,
) -> None:
    ctx = AgentContext(query="Analyze", stock_code="600519")
    if expected_convergence == "unavailable":
        ctx.meta["critic_trace"] = critic.parse_critic_output(_retry_payload())
    trace = builder(ctx)
    appendix = critic.build_dashboard_critic_appendix(
        trace,
        enabled=True,
        ran=expected_convergence != "budget_skipped",
    )
    assert appendix["verdict"] == expected_verdict
    assert appendix["convergence_status"] == expected_convergence
    expected_phrase = {
        "budget_skipped": "skipped to preserve the Decision",
        "stage_failed": "did not complete",
        "unavailable": "unavailable",
    }[expected_convergence]
    assert expected_phrase in appendix["summary"]
    assert len(appendix["summary"]) <= 300


def test_disabled_critic_does_not_add_dashboard_appendix(monkeypatch) -> None:
    orch = _orchestrator(enabled=False)
    decision = _FixtureStage("decision", _decision_with_dashboard)
    monkeypatch.setattr(
        critic,
        "BoundedCriticAgent",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("Critic must not run")),
    )
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [decision])
    ctx = AgentContext(query="Analyze", stock_code="600519")

    result = orch._execute_pipeline(ctx, parse_dashboard=True)

    assert result.success is True
    dashboard = (ctx.get_data("final_dashboard") or {}).get("dashboard") or {}
    assert "critic" not in dashboard
    not_required = critic.build_dashboard_critic_appendix(
        None, enabled=False, ran=False,
    )
    assert not_required["enabled"] is False
    assert not_required["ran"] is False
    assert not_required["convergence_status"] == "not_required"
    assert "not required" in not_required["summary"].lower()


def test_summary_is_sanitized_and_capped_at_300_chars() -> None:
    secret = "sk-ant-api03-THIS_IS_A_FAKE_KEY_FOR_TEST_ONLY_1234567890"
    huge = ("Issuer filing gap " + secret + " ") * 20
    trace = {
        "verdict": "fail_soft",
        "convergence_status": "not_converged",
        "retry_status": "failed",
        "reasons": [huge],
        "iteration_consumed": 0,
        "iteration_max": 1,
        "revision_rounds": [],
    }
    summary = critic.build_critic_summary(trace)
    appendix = critic.build_dashboard_critic_appendix(trace, enabled=True, ran=True)
    assert len(summary) <= 300
    assert len(appendix["summary"]) <= 300
    assert secret not in summary
    assert secret not in appendix["summary"]
    assert "not_converged" in appendix["convergence_status"]
    english = {
        status: critic.build_critic_summary({"convergence_status": status})
        for status in (
            "pass", "converged", "not_converged", "unavailable",
            "budget_skipped", "stage_failed",
        )
    }
    assert "passed without requesting a revision" in english["pass"].lower()
    assert "converged after a controlled retry" in english["converged"].lower()
    assert "remain after the bounded revision" in english["not_converged"].lower()
    assert "unavailable" in english["unavailable"].lower()
    assert "skipped to preserve" in english["budget_skipped"].lower()
    assert "did not complete" in english["stage_failed"].lower()


def test_phase_start_end_persist_for_critic_and_retry_through_diagnostics_and_flow(
    monkeypatch,
) -> None:
    orch = _orchestrator(enabled=True)
    ctx = AgentContext(query="Analyze", stock_code="600519")

    def _intel(run_ctx: AgentContext, call: int) -> StageResult:
        run_ctx.add_opinion(AgentOpinion(
            agent_name="intel",
            signal="hold",
            confidence=0.6,
            reasoning=f"intelligence-{call}",
        ))
        return _stage_result("intel")

    intel = _FixtureStage("intel", _intel)
    fixture_critic = _FixtureCritic(_retry_payload())
    decision = _FixtureStage("decision", _decision_with_dashboard)
    monkeypatch.setattr(critic, "BoundedCriticAgent", lambda **_kwargs: fixture_critic)
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [intel, decision])
    monkeypatch.setattr(
        "src.agent.observability.events.is_agent_observability_enabled",
        lambda: True,
    )

    token = activate_run_diagnostic_context(trace_id="trace-critic-vis")
    try:
        result = orch._execute_pipeline(ctx, parse_dashboard=True)
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert result.success is True
    assert snapshot is not None
    phases = _phase_events(snapshot)
    names = [event.get("name") for event in phases]
    types = [event.get("event_type") for event in phases]
    assert "critic" in names
    assert "critic_retry" in names
    assert AgentEventType.PHASE_START.value in types
    assert AgentEventType.PHASE_END.value in types
    critic_start = next(
        event for event in phases
        if event["name"] == "critic" and event["event_type"] == AgentEventType.PHASE_START.value
    )
    retry_end = next(
        event for event in phases
        if event["name"] == "critic_retry" and event["event_type"] == AgentEventType.PHASE_END.value
    )
    for event in (critic_start, retry_end):
        attrs = event.get("attrs") or {}
        assert set(attrs).issubset({"reason", "verdict", "convergence", "retry_status", "revision"})

    class _Record:
        query_id = "q-critic"
        code = "600519"
        name = "Kweichow Moutai"
        report_type = "detailed"
        created_at = "2026-08-06T10:00:00"
        id = 131

    flow = build_history_run_flow_snapshot(
        _Record(),
        context_snapshot={"diagnostics": snapshot},
        raw_result={"model_used": "test", "success": True},
    )
    phase_nodes = [node for node in flow.nodes if node.id.startswith("agent_phase_")]
    labels = " ".join(
        f"{getattr(node, 'label', '')} {getattr(node, 'id', '')}"
        for node in phase_nodes
    )
    event_text = " ".join(
        f"{getattr(event, 'type', '')} {getattr(event, 'message', '')}"
        for event in flow.events
    )
    combined = f"{labels} {event_text}".lower()
    assert "critic" in combined
    assert "critic_retry" in combined


def test_native_multi_run_delegates_to_pipeline_with_critic_events(monkeypatch) -> None:
    orch = _orchestrator(enabled=True)
    fixture_critic = _FixtureCritic(_pass_payload())
    decision = _FixtureStage("decision", _decision_with_dashboard)
    monkeypatch.setattr(critic, "BoundedCriticAgent", lambda **_kwargs: fixture_critic)
    monkeypatch.setattr(orch, "_build_agent_chain", lambda _ctx: [decision])
    monkeypatch.setattr(
        "src.agent.observability.events.is_agent_observability_enabled",
        lambda: True,
    )
    token = activate_run_diagnostic_context(trace_id="trace-critic-run")
    try:
        result = orch.run("Analyze 600519", {"stock_code": "600519"})
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert result.success is True
    assert snapshot is not None
    names = [event.get("name") for event in _phase_events(snapshot)]
    assert "critic" in names
    dashboard = (result.dashboard or {}).get("dashboard") or result.dashboard or {}
    nested = dashboard.get("critic") if isinstance(dashboard, dict) else None
    if nested is None and isinstance(result.dashboard, dict):
        nested = (result.dashboard.get("dashboard") or {}).get("critic")
    assert nested is not None
    assert nested["verdict"] == "pass"


def test_evidence_chain_projects_critic_item_step_and_coverage() -> None:
    appendix = critic.build_dashboard_critic_appendix(
        critic.parse_critic_output(_pass_payload()),
        enabled=True,
        ran=True,
    )
    package = build_evidence_chain_package(
        run_id="run-critic",
        record_id="131",
        diagnostics={"agent_events": []},
        raw_result={"dashboard": {"critic": appendix, "core_conclusion": {"decision_type": "hold"}}},
    ).package
    items = [
        item for item in package["evidence_items"]
        if item["source_type"] == "pipeline_stage" and item["source_id"] == "critic"
    ]
    steps = [
        step for step in package["reasoning_steps"]
        if step.get("stage") == "critic" or step.get("role") == "critic"
    ]
    coverage = {source["source"]: source for source in package["coverage"]["sources"]}
    assert len(items) == 1
    assert steps
    assert coverage["dashboard.critic"]["present"] is True
    assert coverage["dashboard.critic"]["absent"] is False


def test_standard_research_include_critic_and_brief_excludes() -> None:
    assert get_mode_limits("brief")["include_critic"] is False
    assert get_mode_limits("standard")["include_critic"] is True
    assert get_mode_limits("research")["include_critic"] is True

    appendix = critic.build_dashboard_critic_appendix(
        critic.parse_critic_output(_pass_payload()),
        enabled=True,
        ran=True,
    )
    result = AnalysisResult(
        code="600519",
        name="贵州茅台",
        trend_prediction="看多",
        sentiment_score=70,
        operation_advice="持有",
        decision_type="hold",
        analysis_summary="hold",
        dashboard={"core_conclusion": {"one_sentence": "hold"}, "critic": appendix},
        report_language="en",
    )
    with patch("src.services.report_renderer.get_config") as mock_config:
        config = MagicMock()
        config.report_templates_dir = "templates"
        config.report_language = "en"
        config.report_mode = "standard"
        config.report_show_llm_model = False
        mock_config.return_value = config
        markdown = render("markdown", [result], extra_context={"report_language": "en", "report_mode": "standard"})
        research = render("markdown", [result], extra_context={"report_language": "en", "report_mode": "research"})
        brief_md = render("markdown", [result], extra_context={"report_language": "en", "report_mode": "brief"})
        wechat = render("wechat", [result], extra_context={"report_language": "en", "report_mode": "standard"})
        brief_platform = render("brief", [result], extra_context={"report_language": "en"})
    assert markdown is not None and "Critic Review" in markdown
    assert research is not None and "Critic Review" in research
    assert wechat is not None and "Critic Review" in wechat
    assert brief_md is not None and "Critic Review" not in brief_md
    assert brief_platform is not None and "Critic Review" not in brief_platform

    zh_lines: list[str] = []
    append_critic_lines(zh_lines, {"critic": appendix}, get_report_labels("zh"))
    en_lines: list[str] = []
    append_critic_lines(en_lines, {"critic": appendix}, get_report_labels("en"))
    skipped: list[str] = []
    append_critic_lines(skipped, {"critic": {"enabled": False}}, get_report_labels("en"))
    assert "批评审阅" in "\n".join(zh_lines)
    assert "Critic Review" in "\n".join(en_lines)
    assert skipped == []


def test_notification_python_path_renders_critic_appendix() -> None:
    from src.notification import _append_critic_block

    appendix = critic.build_dashboard_critic_appendix(
        critic.parse_critic_output(_fail_soft_payload()),
        enabled=True,
        ran=True,
    )
    lines: list[str] = []
    _append_critic_block(lines, appendix, get_report_labels("en"))
    joined = "\n".join(lines)
    assert "Critic Review" in joined
    assert "fail_soft" in joined


def test_defaults_and_decision_authority_unchanged() -> None:
    config = Config()
    assert config.agent_critic_enabled is False
    ctx = AgentContext(query="Analyze", stock_code="600519")
    assert critic.is_critic_enabled(config, ctx) is False
    ctx.meta["response_mode"] = "chat"
    enabled = SimpleNamespace(agent_critic_enabled=True)
    assert critic.is_critic_enabled(enabled, ctx) is False
