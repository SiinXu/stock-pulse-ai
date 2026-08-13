# -*- coding: utf-8 -*-
"""Regression-gate anti-tests for agent offline eval (#1092).

These tests intentionally are NOT marked ``benchmark`` so the offline CI gate
executes them. They prove score drops fail the gate without relaxing thresholds.
"""

from __future__ import annotations

import copy

from tests.agent.benchmark.loader import load_baseline
from tests.agent.benchmark.metrics import compare_to_baseline
from src.services.agent_eval_service import AgentEvalService, load_eval_cases
from src.services.prediction_eval_service import REGRESSION_THRESHOLD


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
