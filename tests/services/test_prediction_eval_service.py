# -*- coding: utf-8 -*-
"""Offline prediction-verification suite and regression gate (#1092)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import types

import pytest

from src.services.prediction_eval_service import (
    REGRESSION_THRESHOLD,
    compare_prediction_to_baseline,
    evaluate_prediction_case,
    load_prediction_baseline,
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


def test_committed_baseline_matches_frozen_acceptance_table() -> None:
    current = score_only_prediction_view(run_prediction_eval_suite())
    comparison = compare_prediction_to_baseline(
        current,
        load_prediction_baseline(),
    )
    assert comparison["regressed"] is False
    assert comparison["contract_drift"] is False


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
    degraded["aggregate"]["checks_passed"] = sum(
        int(item["passed"]) for item in degraded["cases"]
    )
    degraded["aggregate"]["score"] = (
        degraded["aggregate"]["checks_passed"]
        / degraded["aggregate"]["checks_total"]
    )

    comparison = compare_prediction_to_baseline(
        degraded, baseline, regression_threshold=REGRESSION_THRESHOLD
    )
    assert comparison["regressed"] is True
    assert comparison["dropped"] is True or comparison["drop_count"] >= 1


def test_case_or_check_removal_cannot_shrink_acceptance_table() -> None:
    baseline = score_only_prediction_view(run_prediction_eval_suite())
    current = copy.deepcopy(baseline)
    removed = current["cases"].pop()
    current["aggregate"]["cases"] -= 1
    current["aggregate"]["checks_passed"] -= int(removed["passed"])
    current["aggregate"]["checks_total"] -= int(removed["total"])
    current["aggregate"]["score"] = (
        current["aggregate"]["checks_passed"]
        / current["aggregate"]["checks_total"]
    )

    comparison = compare_prediction_to_baseline(current, baseline)

    assert comparison["regressed"] is True
    assert comparison["contract_drift"] is True
    assert comparison["missing_case_ids"] == [removed["case_id"]]


def test_non_finite_scores_and_relaxed_threshold_fail_closed() -> None:
    baseline = score_only_prediction_view(run_prediction_eval_suite())
    malformed = copy.deepcopy(baseline)
    malformed["aggregate"]["score"] = float("nan")
    with pytest.raises(ValueError, match="finite|between"):
        compare_prediction_to_baseline(malformed, baseline)
    with pytest.raises(ValueError, match="fixed at 0.0"):
        compare_prediction_to_baseline(
            baseline,
            baseline,
            regression_threshold=0.1,
        )


def test_provider_failure_fixture_rejects_fabricated_hit() -> None:
    cases = {case["id"]: case for case in load_prediction_eval_cases()}
    case = copy.deepcopy(cases["pred-provider-failure-unavailable"])
    case["resolution"]["outcome"] = "hit"
    scored = evaluate_prediction_case(case)
    assert scored["score"] < 1.0
    failed_ids = {item["id"] for item in scored["failed_checks"]}
    assert "provider_failure_is_data_unavailable" in failed_ids
    assert "never_fabricated_hit_without_actuals" in failed_ids


def test_unstructured_prose_cannot_be_fabricated_as_miss() -> None:
    cases = {case["id"]: case for case in load_prediction_eval_cases()}
    case = copy.deepcopy(cases["pred-unstructured-prose-rejected"])
    case["resolution"]["outcome"] = "miss"

    scored = evaluate_prediction_case(case)

    failed_ids = {item["id"] for item in scored["failed_checks"]}
    assert "prose_outcome_unavailable" in failed_ids


def test_installed_claim_scorer_failure_is_not_silently_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = types.ModuleType("src.services.claim_scorer")

    class _BrokenScorer:
        def score(self, claims, actuals):
            raise RuntimeError("scorer unavailable")

    fake_module.ClaimScorer = _BrokenScorer
    monkeypatch.setitem(sys.modules, "src.services.claim_scorer", fake_module)
    cases = {case["id"]: case for case in load_prediction_eval_cases()}

    scored = evaluate_prediction_case(cases["pred-direction-hit"])

    failures = {item["id"] for item in scored["failed_checks"]}
    assert "claim_scorer_contract" in failures


def test_eval_not_bypassable_by_soul_skip_flag() -> None:
    import src.services.prediction_eval_service as mod

    assert not hasattr(mod, "DISABLE_SOUL_COMPOSITION")
    assert REGRESSION_THRESHOLD == 0.0
    report = run_prediction_eval_suite()
    assert report["aggregate"]["checks_total"] >= 6
