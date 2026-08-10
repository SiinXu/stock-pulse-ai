# -*- coding: utf-8 -*-
"""Offline financial agent evaluation benchmark tests (#252 V0).

Marked ``benchmark`` so the blocking offline gate excludes them
(``pytest -m "not network and not benchmark"``). Run via:

  python scripts/run_agent_benchmark.py
  python -m pytest -m benchmark tests/agent/benchmark -q
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys

import pytest

from src.services.agent_eval_service import load_eval_cases
from scripts.run_agent_benchmark import main as benchmark_main

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from tests.agent.benchmark.loader import (  # noqa: E402
    BASELINE_PATH,
    BENCHMARK_FIXTURE_ROOT,
    MANIFEST_PATH,
    METRIC_FAMILIES,
    SCHEMA_VERSION,
    iter_scenarios,
    list_scenario_ids,
    load_baseline,
    load_manifest,
    load_source_case,
)
from tests.agent.benchmark.metrics import (  # noqa: E402
    compare_to_baseline,
    score_observation,
)
from tests.agent.benchmark.runner import (  # noqa: E402
    canonical_json,
    run_benchmark,
    run_output_quality_comparison,
    score_only_view,
)

pytestmark = [
    pytest.mark.benchmark,
]


def test_manifest_declares_small_fixed_panel() -> None:
    manifest = load_manifest()
    assert manifest.get("schema_version") == SCHEMA_VERSION
    case_ids = list_scenario_ids()
    assert 3 <= len(case_ids) <= 6
    assert case_ids == [entry["id"] for entry in manifest["cases"]]
    for entry in manifest["cases"]:
        path = BENCHMARK_FIXTURE_ROOT / entry["file"]
        assert path.is_file(), f"missing scenario file: {path}"
        scenario = json.loads(path.read_text(encoding="utf-8"))
        source = load_source_case(scenario["source_case"])
        assert source.get("id")
    assert MANIFEST_PATH.is_file()
    assert BASELINE_PATH.is_file()


@pytest.mark.parametrize("scenario_id", list_scenario_ids())
def test_scenario_has_all_metric_families(scenario_id: str) -> None:
    scenario = next(s for s in iter_scenarios() if s["id"] == scenario_id)
    evaluation = scenario["evaluation"]
    for family in METRIC_FAMILIES:
        assert family in evaluation
        assert isinstance(evaluation[family], dict)


def test_end_to_end_benchmark_passes_and_matches_baseline() -> None:
    report = run_benchmark()
    view = score_only_view(report)
    assert view["schema_version"] == SCHEMA_VERSION
    agg = view["aggregate"]
    assert agg["scenarios"] == len(list_scenario_ids())
    assert agg["checks_total"] > 0
    assert agg["checks_passed"] == agg["checks_total"]
    assert abs(float(agg["score"]) - 1.0) < 1e-9

    baseline = load_baseline()
    comparison = compare_to_baseline(view, baseline)
    assert comparison["drop_count"] == 0
    assert not comparison["dropped"]
    assert abs(float(comparison["delta"])) < 1e-9


def test_benchmark_is_deterministic() -> None:
    first = run_benchmark()
    second = run_benchmark()
    assert canonical_json(first) == canonical_json(second)


def test_benchmark_emits_joinable_strict_trajectory_evaluations() -> None:
    report = run_benchmark()
    details = report["scenario_details"]
    assert details
    evaluation_ids = set()
    for detail in details:
        trajectory = detail["trajectory_evaluation"]
        provenance = trajectory["provenance"]
        assert provenance["input_schema_version"] == "agent-trajectory-input-v1"
        assert provenance["engine_version"] == "agent-trajectory-eval-v2"
        assert provenance["run_count"] == 1
        assert trajectory["runs"][0]["task_id"] == detail["scenario_id"]
        assert trajectory["metrics"]["tool_selection_precision"] is not None
        assert "tool_selection_accuracy" not in trajectory["metrics"]
        assert "step_efficiency" not in trajectory["metrics"]
        evaluation_ids.add(provenance["evaluation_id"])
    assert len(evaluation_ids) == len(details)
    json.dumps(report, allow_nan=False, sort_keys=True)


def test_output_quality_uses_canonical_runner_and_detects_candidate_regression() -> None:
    report = run_benchmark()
    output_eval = report["output_quality_evaluation"]
    assert output_eval["comparison"]["regressed"] is False
    assert output_eval["baseline"]["suite_hash"] == output_eval["candidate"]["suite_hash"]

    candidate_cases = copy.deepcopy(load_eval_cases())
    candidate_cases[0]["agent_output"] = {}
    comparison = run_output_quality_comparison(candidate_cases)["comparison"]
    assert comparison["regressed"] is True


def test_strict_cli_exits_nonzero_for_output_quality_regression(tmp_path) -> None:
    source = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "agent_eval")
    candidate_root = tmp_path / "candidate"
    shutil.copytree(source, candidate_root)
    case_path = candidate_root / "cases" / "fact-grounded-pass.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["agent_output"] = {}
    case_path.write_text(json.dumps(case), encoding="utf-8")
    assert benchmark_main([
        "--strict-baseline", "--quiet",
        "--output-quality-candidate-root", str(candidate_root),
        "--candidate-agent-version", "agent-v2",
        "--candidate-config-version", "config-v2",
    ]) == 2


def test_score_observation_detects_overconfident_partial_path() -> None:
    scenario = next(s for s in iter_scenarios() if s["id"] == "bench-a-partial-honesty")
    observed = {
        "success": True,
        "signal": "buy",
        "tool_calls": [
            {
                "tool": "get_realtime_quote",
                "arguments": {"stock_code": "600519"},
                "success": True,
            }
        ],
        "dashboard": {
            "decision_type": "buy",
            "confidence_level": "高",
            "risk_warning": "",
            "analysis_summary": "Definitely buy with full conviction.",
            "stock_name": "贵州茅台",
            "dashboard": {
                "phase_decision": {
                    "data_limitations": "无",
                }
            },
        },
        "content": "全力买入",
    }
    scored = score_observation(
        observed,
        scenario["evaluation"],
        scenario_id=scenario["id"],
    )
    assert scored["score"] < 1.0
    failed_ids = {item["id"] for item in scored["failed_checks"]}
    assert "signal_matches" in failed_ids
    assert (
        "confidence_level_allowed" in failed_ids
        or "forbid_high_confidence" in failed_ids
    )
    assert "risk_warning_present" in failed_ids
    assert "nontrivial_data_limitations" in failed_ids


def test_tool_discipline_detects_wrong_stock_scope() -> None:
    scenario = next(s for s in iter_scenarios() if s["id"] == "bench-a-happy-path")
    evaluation = copy.deepcopy(scenario["evaluation"])
    observed = {
        "success": True,
        "signal": "hold",
        "tool_calls": [
            {
                "tool": "get_realtime_quote",
                "arguments": {"stock_code": "000001"},
                "success": True,
            },
            {
                "tool": "analyze_trend",
                "arguments": {"stock_code": "000001"},
                "success": True,
            },
            {
                "tool": "get_chip_distribution",
                "arguments": {"stock_code": "000001"},
                "success": True,
            },
        ],
        "dashboard": {
            "decision_type": "hold",
            "confidence_level": "中",
            "risk_warning": "估值风险",
            "analysis_summary": "持有",
            "stock_name": "贵州茅台",
        },
        "content": "ok",
    }
    scored = score_observation(observed, evaluation, scenario_id=scenario["id"])
    failed_ids = {item["id"] for item in scored["failed_checks"]}
    assert "stock_scope" in failed_ids
