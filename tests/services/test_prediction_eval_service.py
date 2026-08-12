# -*- coding: utf-8 -*-
"""Offline prediction-verification suite and regression gate (#1092)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from src.services.prediction_eval_service import (
    REGRESSION_THRESHOLD,
    compare_prediction_to_baseline,
    evaluate_prediction_case,
    load_prediction_eval_cases,
    run_prediction_eval_suite,
    score_only_prediction_view,
    write_prediction_baseline,
)


def test_threshold_is_zero_and_justified() -> None:
    assert REGRESSION_THRESHOLD == 0.0
    report = run_prediction_eval_suite()
    assert report["regression_threshold"] == 0.0
    assert "must not be relaxed" in str(report["threshold_rationale"]).lower()


def test_suite_covers_required_profiles() -> None:
    cases = load_prediction_eval_cases()
    assert len(cases) >= 6
    profiles = {str(case.get("profile") or "") for case in cases}
    for required in {
        "success",
        "provider_failure",
        "missing_data",
        "overclaim_temptation",
        "seeded_failure",
        "tool_failure",
    }:
        assert required in profiles


def test_suite_passes_on_committed_fixtures() -> None:
    report = run_prediction_eval_suite()
    agg = report["aggregate"]
    assert agg["checks_total"] > 0
    assert agg["checks_passed"] == agg["checks_total"]
    assert abs(float(agg["score"]) - 1.0) < 1e-12


def test_suite_is_deterministic() -> None:
    first = run_prediction_eval_suite()
    second = run_prediction_eval_suite()
    assert first["suite_hash"] == second["suite_hash"]


def test_injected_degradation_fails_regression_gate(tmp_path: Path) -> None:
    report = run_prediction_eval_suite()
    baseline_path = tmp_path / "prediction_baseline.json"
    write_prediction_baseline(report, baseline_path)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    degraded = score_only_prediction_view(report)
    degraded["cases"][0]["score"] = 0.0
    degraded["cases"][0]["passed"] = 0
    degraded["aggregate"]["score"] = 0.5
    degraded["aggregate"]["checks_passed"] = max(
        0, int(degraded["aggregate"]["checks_total"]) // 2
    )

    comparison = compare_prediction_to_baseline(
        degraded, baseline, regression_threshold=REGRESSION_THRESHOLD
    )
    assert comparison["regressed"] is True
    assert comparison["dropped"] is True or comparison["drop_count"] >= 1


def test_provider_failure_fixture_rejects_fabricated_hit() -> None:
    cases = {case["id"]: case for case in load_prediction_eval_cases()}
    case = copy.deepcopy(cases["pred-provider-failure-unavailable"])
    case["resolution"]["outcome"] = "hit"
    scored = evaluate_prediction_case(case)
    assert scored["score"] < 1.0
    failed_ids = {item["id"] for item in scored["failed_checks"]}
    assert "provider_failure_is_data_unavailable" in failed_ids
    assert "never_fabricated_hit_without_actuals" in failed_ids


def test_eval_not_bypassable_by_soul_skip_flag() -> None:
    import src.services.prediction_eval_service as mod

    assert not hasattr(mod, "DISABLE_SOUL_COMPOSITION")
    assert REGRESSION_THRESHOLD == 0.0
    report = run_prediction_eval_suite()
    assert report["aggregate"]["checks_total"] >= 6
