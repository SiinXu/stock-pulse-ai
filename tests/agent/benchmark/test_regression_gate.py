# -*- coding: utf-8 -*-
"""Regression-gate anti-tests for agent offline eval (#1092).

These tests intentionally are NOT marked ``benchmark`` so the offline CI gate
executes them. They prove score drops fail the gate without relaxing thresholds,
and that ``--strict-baseline`` cannot pass if Soul composition or ToolSurface
authorization is skipped on the shared replay path.
"""

from __future__ import annotations

import copy

import pytest

from tests.agent.benchmark.loader import load_baseline
from tests.agent.benchmark.metrics import compare_to_baseline
from src.agent.soul import compose_agent_soul_prompt
from src.agent.tools.surface import tool_surface_dispatch_authorized
from src.services.agent_eval_service import AgentEvalService, load_eval_cases
from src.services.prediction_eval_service import REGRESSION_THRESHOLD
from tests.agent_runtime_replay import ReplayLLMAdapter, build_replay_tool_registry


def _identity_soul(system_prompt: str) -> str:
    return system_prompt


def _strip_replay_soul_composition(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.agents.base_agent as base_agent
    import src.agent.executor as executor
    import src.agent.executor_parts.chat as executor_chat
    import src.agent.executor_parts.run as executor_run
    import src.agent.orchestrator as orchestrator
    import src.agent.orchestrator_parts.chat as orchestrator_chat
    import src.agent.soul as soul

    # Replay uses facade-rebound methods; patch the live lookup names as well
    # as the source-module aliases so composition is actually skipped.
    for module, name in (
        (soul, "compose_agent_soul_prompt"),
        (executor, "_compose_agent_soul_prompt"),
        (executor_run, "_compose_agent_soul_prompt"),
        (executor_chat, "_compose_agent_soul_prompt"),
        (orchestrator, "_compose_agent_soul_prompt"),
        (orchestrator_chat, "_compose_agent_soul_prompt"),
        (base_agent, "compose_agent_soul_prompt"),
    ):
        monkeypatch.setattr(module, name, _identity_soul)


def _direct_handler_bypass(tool_call, session):
    from src.agent import factory as factory_module

    name = getattr(tool_call, "name", None)
    arguments = getattr(tool_call, "arguments", None)
    registry = factory_module.get_tool_registry()
    tool_def = registry.get(name) if registry is not None else None
    handler = getattr(tool_def, "handler", None)
    if not callable(handler):
        raise AssertionError(f"cannot bypass ToolSurface for {name!r}")
    kwargs = dict(arguments) if isinstance(arguments, dict) else {}
    return handler(**kwargs)


def test_agent_benchmark_score_drop_is_detected() -> None:
    baseline = load_baseline()
    degraded = copy.deepcopy(baseline)
    degraded["aggregate"]["score"] = max(0.0, float(baseline["aggregate"]["score"]) - 0.25)
    if degraded.get("scenarios"):
        degraded["scenarios"][0]["score"] = 0.0
    comparison = compare_to_baseline(degraded, baseline)
    assert comparison["dropped"] is True or comparison["drop_count"] >= 1


def test_output_quality_regression_detected_on_candidate_corruption() -> None:
    cases = load_eval_cases()
    service = AgentEvalService()
    baseline = service.evaluate_suite(cases)
    broken = copy.deepcopy(cases)
    # Flip a pass fixture claim so rule score drops.
    mutated = False
    for case in broken:
        if case.get("id") == "fact-grounded-pass":
            # Mutate output numeric claim value if present.
            output = case.get("agent_output")
            if isinstance(output, dict):
                for claim in output.get("claims") or []:
                    if isinstance(claim, dict) and "value" in claim:
                        claim["value"] = float(claim["value"]) + 9999.0
                        mutated = True
                        break
            break
    assert mutated is True
    candidate = service.evaluate_suite(broken)
    comparison = service.compare_reports(
        baseline,
        candidate,
        baseline_agent_version="baseline",
        candidate_agent_version="candidate",
        baseline_config_version="cfg-b",
        candidate_config_version="cfg-c",
        regression_threshold=0.0,
    )
    assert baseline.suite_hash != candidate.suite_hash
    assert comparison["regressed"] is True or comparison["rule_delta"] < 0
    assert REGRESSION_THRESHOLD == 0.0


def test_replay_llm_adapter_rejects_missing_canonical_soul() -> None:
    adapter = ReplayLLMAdapter(
        [{"content": "ok", "allowed_stage": "single_run"}],
    )
    base_prompt = "负责生成专业的【决策仪表盘】分析报告"
    with pytest.raises(AssertionError, match="canonical Agent Soul"):
        adapter.call_with_tools(
            [{"role": "system", "content": base_prompt}],
            tools=[],
        )

    composed = compose_agent_soul_prompt(base_prompt)
    adapter_ok = ReplayLLMAdapter([{"content": "ok"}])
    response = adapter_ok.call_with_tools(
        [{"role": "system", "content": composed}],
        tools=[],
    )
    assert response.content == "ok"
    assert adapter_ok.observed_soul_composed == [True]
    assert adapter_ok.calls[0]["soul_composed"] is True


def test_replay_tool_handler_rejects_unauthorized_dispatch() -> None:
    registry = build_replay_tool_registry()
    tool = registry.get("echo")
    assert tool is not None
    assert tool_surface_dispatch_authorized() is False
    with pytest.raises(AssertionError, match="ToolSurface authorization"):
        tool.handler(message="hi")


def test_strict_baseline_fails_when_soul_composition_is_stripped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.services.prediction_eval_service as prediction_eval

    assert not hasattr(prediction_eval, "DISABLE_SOUL_COMPOSITION")
    _strip_replay_soul_composition(monkeypatch)
    from scripts.run_agent_benchmark import main as benchmark_main

    with pytest.raises((AssertionError, ValueError), match="Soul"):
        benchmark_main(["--strict-baseline", "--quiet"])


def test_strict_baseline_fails_when_tool_surface_is_bypassed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.agent.runner.execute_runner_tool_call_via_session",
        _direct_handler_bypass,
    )
    monkeypatch.setattr(
        "src.agent.runner_parts.tools.execute_runner_tool_call_via_session",
        _direct_handler_bypass,
    )
    from scripts.run_agent_benchmark import main as benchmark_main

    with pytest.raises(AssertionError, match="ToolSurface authorization"):
        benchmark_main(["--strict-baseline", "--quiet"])
