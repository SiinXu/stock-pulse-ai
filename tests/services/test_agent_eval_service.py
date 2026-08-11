# -*- coding: utf-8 -*-
"""Focused offline tests for output-quality evaluation (#252 / #141)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.agent_eval_service import (
    EVAL_SCHEMA_VERSION,
    MAX_CASES,
    AgentEvalService,
    format_failure_report,
    is_agent_eval_enabled,
    load_eval_cases,
    score_boundary_honesty,
    score_conclusion_consistency,
    score_factuality,
    score_language_format,
    score_llm_dimension,
    score_tool_usage,
)


def _fact(*, fact_id: str = "price", field: str = "quote.price", value: float = 100.0,
          unit: str = "CNY") -> dict[str, object]:
    return {"fact_id": fact_id, "field_path": field, "value": value, "unit": unit,
            "as_of": "2026-08-08", "source_id": "fixture-source"}


def _claim(*, claim_id: str = "price-claim", source_fact_id: str = "price",
           field: str = "quote.price", value: float = 100.0,
           unit: str = "CNY") -> dict[str, object]:
    return {"claim_id": claim_id, "source_fact_id": source_fact_id,
            "field_path": field, "value": value, "unit": unit,
            "as_of": "2026-08-08", "source_id": "fixture-source"}


def _tool(name: str, **overrides: object) -> dict[str, object]:
    call: dict[str, object] = {"tool": name, "attempted": True, "completed": True,
                               "succeeded": True, "valid_result": True,
                               "authorized": True}
    call.update(overrides)
    return call


def _case(case_id: str = "case", output: dict[str, object] | None = None) -> dict[str, object]:
    return {"id": case_id, "dimensions": ["factuality"],
            "context": {"facts": [_fact()]},
            "agent_output": output if output is not None else {"claims": [_claim()]},
            "evaluation": {"factuality": {"required_claim_ids": ["price-claim"]}},
            "agent_version": "agent-v1", "config_version": "config-v1"}


def test_compatibility_opt_in_is_exact_typed_config_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_EVAL_ENABLED", "true")
    assert not is_agent_eval_enabled()
    assert not is_agent_eval_enabled(SimpleNamespace(agent_eval_enabled="true"))
    assert is_agent_eval_enabled(SimpleNamespace(agent_eval_enabled=True))


def test_explicit_suite_invocation_does_not_depend_on_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_EVAL_ENABLED", raising=False)
    report = AgentEvalService().evaluate_suite([_case()])
    assert report.enabled and report.rule_score == 1.0
    assert report.schema_version == EVAL_SCHEMA_VERSION
    assert len(report.suite_hash) == 64


def test_load_eval_cases_is_ordered_hashed_and_strict() -> None:
    cases = load_eval_cases()
    assert cases[0]["id"] == "fact-grounded-pass"
    assert all(len(case["_artifact_hash"]) == 64 for case in cases)


def test_loader_rejects_duplicate_manifest_ids(tmp_path: Path) -> None:
    (tmp_path / "cases").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps({
        "version": "agent_eval/1.0", "case_ids": ["x", "x"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_eval_cases(tmp_path)


def test_loader_rejects_unlisted_fixture(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    cases.mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps({
        "version": "agent_eval/1.0", "case_ids": ["x"]}), encoding="utf-8")
    for case_id in ("x", "extra"):
        (cases / f"{case_id}.json").write_text(json.dumps(_case(case_id)), encoding="utf-8")
    with pytest.raises(ValueError, match="not listed"):
        load_eval_cases(tmp_path)


def test_empty_or_malformed_output_is_invalid_not_vacuous_pass() -> None:
    result = AgentEvalService().evaluate_case(_case(output={}))
    assert result.rule_score == 0.0
    assert result.metadata["invalid"] is True
    assert result.checks[0].status == "invalid"


def test_missing_dimension_rubric_is_invalid() -> None:
    case = _case()
    case["evaluation"] = {}
    result = AgentEvalService().evaluate_case(case)
    assert result.rule_score == 0.0
    assert result.metadata["invalid"] is True


def test_factuality_exact_binding_passes() -> None:
    assert all(check.passed for check in score_factuality(
        {"facts": [_fact()]}, {"claims": [_claim()]},
        {"required_claim_ids": ["price-claim"]}))


def test_factuality_rejects_cross_field_value_borrowing() -> None:
    facts = [_fact(fact_id="price", field="quote.price", value=100),
             _fact(fact_id="revenue", field="fundamentals.revenue", value=100, unit="CNYm")]
    claim = _claim(source_fact_id="revenue", field="quote.price", value=100, unit="CNYm")
    checks = score_factuality({"facts": facts}, {"claims": [claim]}, {})
    assert any(not check.passed and check.check_id == "claim_bound_to_source_fact" for check in checks)


def test_factuality_rejects_percent_absolute_borrowing() -> None:
    fact = _fact(field="quote.change_pct", value=5, unit="percent")
    claim = _claim(field="quote.change", value=5, unit="CNY")
    checks = score_factuality({"facts": [fact]}, {"claims": [claim]}, {})
    assert any(not check.passed for check in checks)


def test_factuality_rejects_non_finite_value() -> None:
    checks = score_factuality({"facts": [_fact(value=float("nan"))]},
                              {"claims": [_claim()]}, {})
    assert any(check.status == "invalid" for check in checks)


def test_required_tool_needs_success_valid_result_and_authorization() -> None:
    for field in ("completed", "succeeded", "valid_result", "authorized"):
        checks = score_tool_usage({}, {"tool_calls": [_tool("quote", **{field: False})]},
                                  {"required_tools": ["quote"]})
        assert any(not check.passed for check in checks)
    string_bool = score_tool_usage({}, {"tool_calls": [_tool("quote", succeeded="true")]},
                                   {"required_tools": ["quote"]})
    assert any(not check.passed for check in string_bool)


def test_forbidden_tool_fails_when_attempted() -> None:
    checks = score_tool_usage({}, {"tool_calls": [_tool("place_order", succeeded=False)]},
                              {"forbidden_tools": ["place_order"]})
    assert any(not check.passed and check.check_id == "forbidden_tools_absent" for check in checks)


def test_llm_judgement_requires_strict_boolean_finite_score_and_provenance() -> None:
    invalid = score_llm_dimension("explanation_clarity", {
        "explanation_clarity": {"passed": "false", "score": float("nan")}})
    assert invalid[0].status == "invalid" and not invalid[0].passed
    valid = score_llm_dimension("explanation_clarity", {"explanation_clarity": {
        "passed": True, "score": 0.8, "detail": "clear", "judge_id": "judge-1",
        "model": "frozen-judge", "rubric_version": "v1", "as_of": "2026-08-08"}})
    assert valid[0].passed and valid[0].judge == "llm"


def test_llm_dimension_skipped_is_not_mixed_into_rule_score() -> None:
    case = _case()
    case["dimensions"] = ["factuality", "explanation_clarity"]
    case["evaluation"]["explanation_clarity"] = {}
    result = AgentEvalService().evaluate_case(case)
    assert result.rule_score == 1.0 and result.llm_score is None
    assert next(c for c in result.checks if c.judge == "llm").status == "skipped"


def test_other_rule_counterexamples_remain_detected() -> None:
    consistency = score_conclusion_consistency({}, {
        "signal": "buy", "evidence": [{"polarity": "bearish"}]}, {})
    honesty = score_boundary_honesty({"data_missing": True}, {
        "signal": "buy", "confidence": "high", "data_limitations": "none"},
        {"forbid_directional_when_missing": True})
    language = score_language_format({}, {"signal": "buy"},
                                     {"required_fields": ["risk_warning"]})
    assert any(not item.passed for item in consistency)
    assert any(not item.passed for item in honesty)
    assert any(not item.passed for item in language)


def test_suite_failure_mining_and_strict_json_serialization() -> None:
    bad = _case("bad")
    bad["agent_output"] = {"claims": [_claim(value=101)]}
    report = AgentEvalService().evaluate_suite([_case("good"), bad])
    assert 0 < report.rule_score < 1
    assert report.failure_clusters and report.failure_list
    payload = json.dumps(report.to_dict(), allow_nan=False, sort_keys=True)
    assert "bad" in payload and "failure" in format_failure_report(report).lower()


def test_suite_bounds_case_count() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        AgentEvalService().evaluate_suite([_case(str(index)) for index in range(MAX_CASES + 1)])


def test_case_rejects_unbounded_nesting() -> None:
    case = _case()
    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(20):
        child: dict[str, object] = {}
        cursor["child"] = child
        cursor = child
    case["context"] = nested
    result = AgentEvalService().evaluate_case(case)
    assert result.rule_score == 0.0
    assert result.checks[0].status == "invalid"


def test_candidate_baseline_comparison_detects_regression_and_tracks_provenance() -> None:
    service = AgentEvalService()
    baseline = service.evaluate_suite([_case("same")])
    regressed_case = _case("same")
    regressed_case["agent_output"] = {"claims": [_claim(value=999)]}
    candidate = service.evaluate_suite([regressed_case])
    comparison = service.compare_reports(
        baseline, candidate, baseline_agent_version="agent-v1",
        candidate_agent_version="agent-v2", baseline_config_version="config-v1",
        candidate_config_version="config-v2")
    assert comparison["regressed"] is True
    assert comparison["rule_delta"] < 0
    assert comparison["baseline_suite_hash"] != comparison["candidate_suite_hash"]
    assert comparison["baseline_case_count"] == comparison["candidate_case_count"] == 1
