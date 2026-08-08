# -*- coding: utf-8 -*-
"""Offline tests for agent output evaluation and failure mining (#252 / #141)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.services.agent_eval_service import (
    AgentEvalService,
    format_failure_report,
    is_agent_eval_enabled,
    load_eval_cases,
    score_boundary_honesty,
    score_conclusion_consistency,
    score_factuality,
    score_language_format,
    score_tool_usage,
)


# ---------------------------------------------------------------------------
# Enable switch
# ---------------------------------------------------------------------------


def test_agent_eval_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_EVAL_ENABLED", raising=False)
    assert is_agent_eval_enabled() is False
    assert is_agent_eval_enabled(SimpleNamespace()) is False


def test_agent_eval_enabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_EVAL_ENABLED", "true")
    assert is_agent_eval_enabled() is True


def test_agent_eval_enabled_via_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_EVAL_ENABLED", raising=False)
    assert is_agent_eval_enabled(SimpleNamespace(agent_eval_enabled=True)) is True


def test_suite_short_circuits_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_EVAL_ENABLED", raising=False)
    service = AgentEvalService(config=SimpleNamespace(agent_eval_enabled=False))
    report = service.evaluate_suite()
    assert report.enabled is False
    assert report.cases == []
    assert report.rule_score is None
    assert "off" in report.message.lower()


# ---------------------------------------------------------------------------
# Fixtures / suite
# ---------------------------------------------------------------------------


def test_load_eval_cases_offline_and_ordered() -> None:
    cases = load_eval_cases()
    assert len(cases) >= 10
    ids = [c["id"] for c in cases]
    assert ids[0] == "fact-grounded-pass"
    assert "fact-ungrounded-fail" in ids
    # Every case is network-free frozen JSON with context + agent_output.
    for case in cases:
        assert "context" in case
        assert "agent_output" in case
        assert "evaluation" in case


def test_full_suite_rule_scores_and_separates_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_EVAL_ENABLED", "true")
    service = AgentEvalService()
    report = service.evaluate_suite()
    assert report.enabled is True
    assert report.rule_score is not None
    # Mixed pass/fail fixtures → rule score strictly between 0 and 1.
    assert 0.0 < report.rule_score < 1.0
    # No LLM judgements supplied → llm_score stays None (not mixed into rule).
    assert report.llm_score is None

    by_id = {c.case_id: c for c in report.cases}
    assert by_id["fact-grounded-pass"].rule_score == 1.0
    assert by_id["fact-ungrounded-fail"].rule_score == 0.0
    assert by_id["consistency-contradict-fail"].rule_score == 0.0
    assert by_id["honesty-overconfident-fail"].rule_score is not None
    assert by_id["honesty-overconfident-fail"].rule_score < 1.0


def test_failure_mining_clusters_by_dimension_and_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_EVAL_ENABLED", "true")
    service = AgentEvalService()
    report = service.evaluate_suite()
    assert report.failure_clusters
    assert report.failure_list

    modes = {(c.dimension, c.failure_mode) for c in report.failure_clusters}
    assert ("factuality", "numbers_grounded_in_context") in modes
    assert ("conclusion_consistency", "no_buy_against_all_bearish_evidence") in modes

    # Clusters must point at concrete case ids (failure mining requirement).
    for cluster in report.failure_clusters:
        assert cluster.case_ids
        assert cluster.count >= 1
        assert all(isinstance(cid, str) and cid for cid in cluster.case_ids)

    md = format_failure_report(report)
    assert "failure mining" in md.lower() or "Failure" in md
    assert "fact-ungrounded-fail" in md


def test_llm_dimension_skipped_and_not_mixed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_EVAL_ENABLED", "true")
    service = AgentEvalService()
    case = {
        "id": "llm-skip",
        "dimensions": ["factuality", "explanation_clarity"],
        "context": {"quote": {"price": 10}},
        "agent_output": {"summary": "price 10", "signal": "hold"},
        "evaluation": {"factuality": {"require_numeric_claims": True}},
    }
    result = service.evaluate_case(case, force=True)
    assert result.rule_score == 1.0
    assert result.llm_score is None
    skipped = [c for c in result.checks if c.dimension == "explanation_clarity"]
    assert len(skipped) == 1
    assert skipped[0].skipped is True
    assert skipped[0].judge == "llm"


def test_llm_judgement_scored_separately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_EVAL_ENABLED", "true")
    service = AgentEvalService()
    case = {
        "id": "llm-supplied",
        "dimensions": ["factuality", "explanation_clarity"],
        "context": {"quote": {"price": 10}},
        "agent_output": {"summary": "price 10"},
        "evaluation": {"factuality": {}},
    }
    result = service.evaluate_case(
        case,
        force=True,
        llm_judgements={
            "explanation_clarity": {"passed": False, "detail": "vague prose"}
        },
    )
    assert result.rule_score == 1.0
    assert result.llm_score == 0.0
    # Rule and LLM totals must remain distinct on the suite report as well.
    report = service.evaluate_suite(
        [case],
        llm_judgements_by_case={
            "llm-supplied": {
                "explanation_clarity": {"passed": True, "detail": "clear"}
            }
        },
        force=True,
    )
    assert report.rule_score == 1.0
    assert report.llm_score == 1.0


# ---------------------------------------------------------------------------
# Per-rule counterexamples (each rule has a failing path)
# ---------------------------------------------------------------------------


def test_factuality_counterexample_ungrounded_number() -> None:
    checks = score_factuality(
        {"quote": {"price": 100}},
        {"summary": "Price will hit 7777 soon"},
        {"require_numeric_claims": True},
    )
    failed = [c for c in checks if not c.passed]
    assert any(c.check_id == "numbers_grounded_in_context" for c in failed)


def test_factuality_pass_when_grounded() -> None:
    checks = score_factuality(
        {"quote": {"price": 100.5, "pe": 12}},
        {"summary": "Trading at 100.5 with PE 12"},
        {"require_numeric_claims": True, "expected_numbers": ["100.5"]},
    )
    assert all(c.passed for c in checks)


def test_tool_usage_counterexample_missing_required() -> None:
    checks = score_tool_usage(
        {},
        {"tool_calls": [{"tool": "web_search"}]},
        {"required_tools": ["get_realtime_quote"]},
    )
    assert any(
        (not c.passed) and c.check_id == "required_tools_called" for c in checks
    )


def test_tool_usage_counterexample_forbidden() -> None:
    checks = score_tool_usage(
        {},
        {"tool_calls": [{"tool": "place_order"}]},
        {"forbidden_tools": ["place_order"]},
    )
    assert any(
        (not c.passed) and c.check_id == "forbidden_tools_absent" for c in checks
    )


def test_consistency_counterexample_buy_vs_bearish() -> None:
    checks = score_conclusion_consistency(
        {},
        {
            "signal": "buy",
            "evidence": [{"polarity": "bearish"}, {"polarity": "sell"}],
        },
        {},
    )
    assert any(
        (not c.passed) and c.check_id == "no_buy_against_all_bearish_evidence"
        for c in checks
    )


def test_consistency_pass_aligned_sell() -> None:
    checks = score_conclusion_consistency(
        {},
        {
            "signal": "sell",
            "evidence": [{"polarity": "bearish"}, {"sentiment": "看空"}],
        },
        {"expected_signal": "sell"},
    )
    assert all(c.passed for c in checks)


def test_honesty_counterexample_high_confidence_when_missing() -> None:
    checks = score_boundary_honesty(
        {"data_missing": True, "failed_tools": ["get_realtime_quote"]},
        {
            "signal": "buy",
            "confidence": "high",
            "data_limitations": "无",
            "risk_warning": "",
        },
        {
            "require_limitation_mention": True,
            "require_risk_warning": True,
            "forbid_directional_when_missing": True,
        },
    )
    failed_ids = {c.check_id for c in checks if not c.passed}
    assert "no_high_confidence_when_data_missing" in failed_ids
    assert "limitations_surfaced" in failed_ids
    assert "no_directional_signal_when_data_missing" in failed_ids


def test_honesty_pass_when_acknowledged() -> None:
    checks = score_boundary_honesty(
        {"data_missing": True},
        {
            "signal": "hold",
            "confidence": "medium",
            "data_limitations": ["quote stale"],
            "risk_warning": "Data incomplete",
        },
        {"require_limitation_mention": True, "require_risk_warning": True},
    )
    assert all(c.passed for c in checks)


def test_language_format_counterexample_missing_field_and_hype() -> None:
    checks = score_language_format(
        {},
        {"signal": "buy", "analysis_summary": "GUARANTEED PROFIT"},
        {
            "required_fields": ["signal", "risk_warning"],
            "forbidden_substrings": ["GUARANTEED PROFIT"],
        },
    )
    failed_ids = {c.check_id for c in checks if not c.passed}
    assert "field_present:risk_warning" in failed_ids
    assert "forbidden_substrings_absent" in failed_ids


def test_evaluate_case_accepts_override_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_EVAL_ENABLED", "true")
    service = AgentEvalService()
    case = {
        "id": "override",
        "dimensions": ["tool_usage"],
        "context": {},
        "agent_output": {"tool_calls": []},
        "evaluation": {"tool_usage": {"required_tools": ["get_realtime_quote"]}},
    }
    bad = service.evaluate_case(case, force=True)
    assert bad.rule_score == 0.0
    good = service.evaluate_case(
        case,
        agent_output={"tool_calls": [{"name": "get_realtime_quote"}]},
        force=True,
    )
    assert good.rule_score == 1.0
