# -*- coding: utf-8 -*-
"""Deterministic offline runner for the financial agent evaluation benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

# Ensure repo root is importable when executed as a script.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from tests.agent.benchmark.loader import (  # noqa: E402
    BASELINE_PATH,
    SCHEMA_VERSION,
    iter_scenarios,
    load_baseline,
    load_source_case,
)
from tests.agent.benchmark.metrics import (  # noqa: E402
    aggregate_scenario_scores,
    compare_to_baseline,
    render_markdown_report,
    score_observation,
)
from tests.agent_runtime_replay import observe_case  # noqa: E402
from src.services.agent_trajectory_eval_service import (  # noqa: E402
    evaluate_agent_trajectory,
)
from src.services.agent_eval_service import (  # noqa: E402
    AgentEvalService,
    load_eval_cases,
)


def run_output_quality_comparison(
    candidate_cases: Optional[Sequence[Mapping[str, Any]]] = None,
    *,
    baseline_agent_version: str = "frozen-agent-baseline",
    candidate_agent_version: str = "frozen-agent-candidate",
    baseline_config_version: str = "frozen-config-baseline",
    candidate_config_version: str = "frozen-config-candidate",
) -> Dict[str, Any]:
    """Run output-quality candidate-vs-baseline evaluation in the owned runner."""
    baseline_cases = load_eval_cases()
    candidates = list(candidate_cases) if candidate_cases is not None else baseline_cases
    service = AgentEvalService()
    baseline = service.evaluate_suite(baseline_cases)
    candidate = service.evaluate_suite(candidates)
    comparison = service.compare_reports(
        baseline,
        candidate,
        baseline_agent_version=baseline_agent_version,
        candidate_agent_version=candidate_agent_version,
        baseline_config_version=baseline_config_version,
        candidate_config_version=candidate_config_version,
    )
    return {
        "baseline": baseline.to_dict(),
        "candidate": candidate.to_dict(),
        "comparison": comparison,
    }


def run_scenario(scenario: Mapping[str, Any]) -> Dict[str, Any]:
    """Replay one scenario's source fixture and score the observed run."""
    scenario_id = str(scenario["id"])
    source_rel = str(scenario["source_case"])
    source_case = load_source_case(source_rel)
    observed = observe_case(source_case)
    evaluation = scenario.get("evaluation") or {}
    scored = score_observation(observed, evaluation, scenario_id=scenario_id)
    tool_rubric = evaluation.get("tool_usage_discipline") or {}
    source_input = source_case.get("input") or {}
    source_context = (
        source_input.get("context")
        if isinstance(source_input, Mapping)
        and isinstance(source_input.get("context"), Mapping)
        else {}
    )
    source_run_id = str(source_case.get("id") or source_rel)
    trajectory = evaluate_agent_trajectory(
        [
            {
                "run_id": source_run_id,
                "execution_id": f"offline-replay:{source_run_id}",
                "task_id": scenario_id,
                "agent_id": "offline-single-agent",
                "stock_code": source_context.get("stock_code"),
                "market": scenario.get("market"),
                "completed": observed.get("success")
                if isinstance(observed.get("success"), bool)
                else None,
                "tool_calls": observed.get("tool_calls") or [],
            }
        ],
        rubric={
            "required_tools": list(tool_rubric.get("required_tools") or []),
            "forbidden_tools": list(tool_rubric.get("forbidden_tools") or []),
        },
    )
    scored["trajectory_evaluation"] = trajectory.to_dict()
    scored["source_case"] = source_rel
    scored["market"] = scenario.get("market")
    scored["profile"] = scenario.get("profile")
    return scored


def run_benchmark(
    scenario_ids: Optional[Sequence[str]] = None,
    *,
    output_quality_candidate_root: Optional[Path] = None,
    baseline_agent_version: str = "frozen-agent-baseline",
    candidate_agent_version: str = "frozen-agent-candidate",
    baseline_config_version: str = "frozen-config-baseline",
    candidate_config_version: str = "frozen-config-candidate",
) -> Dict[str, Any]:
    """Run all (or selected) scenarios and return a stable JSON-serializable report."""
    selected = set(scenario_ids) if scenario_ids else None
    scenario_scores: List[Dict[str, Any]] = []
    for scenario in iter_scenarios():
        sid = str(scenario["id"])
        if selected is not None and sid not in selected:
            continue
        scenario_scores.append(run_scenario(scenario))

    if not scenario_scores:
        raise ValueError("no scenarios selected for agent evaluation benchmark")

    report = aggregate_scenario_scores(scenario_scores)
    report["schema_version"] = SCHEMA_VERSION
    report["scenario_details"] = sorted(
        scenario_scores,
        key=lambda item: str(item.get("scenario_id") or ""),
    )
    candidate_cases = (
        load_eval_cases(output_quality_candidate_root)
        if output_quality_candidate_root is not None
        else None
    )
    report["output_quality_evaluation"] = run_output_quality_comparison(
        candidate_cases,
        baseline_agent_version=baseline_agent_version,
        candidate_agent_version=candidate_agent_version,
        baseline_config_version=baseline_config_version,
        candidate_config_version=candidate_config_version,
    )
    return report


def canonical_json(payload: Any) -> str:
    """Serialize with sorted keys for deterministic byte-stable output."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def score_only_view(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Strip verbose check lists so baseline files stay small and stable."""
    scenarios = []
    for item in report.get("scenarios") or []:
        if not isinstance(item, Mapping):
            continue
        scenarios.append(
            {
                "scenario_id": item.get("scenario_id"),
                "passed": item.get("passed"),
                "total": item.get("total"),
                "score": item.get("score"),
                "failed_checks": item.get("failed_checks") or [],
                "families": item.get("families") or {},
            }
        )
    return {
        "schema_version": report.get("schema_version") or SCHEMA_VERSION,
        "aggregate": report.get("aggregate") or {},
        "scenarios": scenarios,
    }


def write_baseline(report: Mapping[str, Any], path: Optional[Path] = None) -> Path:
    target = path or BASELINE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = score_only_view(report)
    target.write_text(canonical_json(payload), encoding="utf-8")
    return target


def build_full_outputs(
    report: Mapping[str, Any],
    *,
    with_baseline: bool = True,
) -> Dict[str, Any]:
    comparison = None
    if with_baseline and BASELINE_PATH.is_file():
        comparison = compare_to_baseline(score_only_view(report), load_baseline())
    markdown = render_markdown_report(score_only_view(report), comparison)
    return {
        "report": report,
        "score_view": score_only_view(report),
        "comparison": comparison,
        "markdown": markdown,
    }
