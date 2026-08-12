# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline contracts for the pipeline analysis quality gate (#887)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from src.analyzer import AnalysisResult
from src.schemas.report_strata import ReportStrata, VerifiedFact
from src.services.agent_eval_service import score_factuality
from src.services.analysis_quality_gate import (
    QUALITY_GATE_SCHEMA_VERSION,
    QualityGateFailurePolicy,
    QualityGateVerdict,
    apply_analysis_quality_gate,
    evaluate_analysis_quality,
    parse_quality_gate_failure_policy,
    project_claims_from_result,
    project_facts_from_evidence,
    resolve_quality_gate_config,
)
from src.services.history_service import HistoryService


def _result(
    *,
    verified_facts: Optional[List[Any]] = None,
    claims: Optional[List[Dict[str, Any]]] = None,
    price: Optional[float] = 1680.5,
    language: str = "en",
) -> AnalysisResult:
    strata = ReportStrata(
        verified_facts=[
            item if isinstance(item, VerifiedFact) else VerifiedFact(statement=str(item))
            for item in (verified_facts or [])
        ],
        model_inference=[],
        missing_or_conflicts=[],
        risks_counter_evidence=[],
        disclaimer="AI-generated content for reference only. Not investment advice.",
    )
    dashboard: Dict[str, Any] = {"report_strata": strata.to_public_dict()}
    if claims is not None:
        dashboard["claims"] = claims
    return AnalysisResult(
        code="600519",
        name="Kweichow Moutai",
        sentiment_score=55,
        trend_prediction="sideways",
        operation_advice="Hold",
        decision_type="hold",
        confidence_level="medium",
        report_language=language,
        dashboard=dashboard,
        analysis_summary="summary",
        current_price=price,
        change_pct=-1.2,
        success=True,
    )


def test_parse_failure_policy_rejects_unknown() -> None:
    assert parse_quality_gate_failure_policy("annotate") == "annotate"
    assert parse_quality_gate_failure_policy("INTERCEPT") == "intercept"
    with pytest.raises(ValueError):
        parse_quality_gate_failure_policy("warn")


def test_resolve_config_defaults() -> None:
    enabled, policy = resolve_quality_gate_config(None)
    assert enabled is True
    assert policy is QualityGateFailurePolicy.ANNOTATE


def test_resolve_config_rejects_non_boolean_enabled_value() -> None:
    with pytest.raises(ValueError, match="must be a boolean"):
        resolve_quality_gate_config(
            SimpleNamespace(
                analysis_quality_gate_enabled="false",
                analysis_quality_gate_on_failure="annotate",
            )
        )


def test_resolve_config_ignores_dynamic_mock_attributes() -> None:
    enabled, policy = resolve_quality_gate_config(MagicMock())
    assert enabled is True
    assert policy is QualityGateFailurePolicy.ANNOTATE


def test_project_facts_from_evidence_includes_pipeline_price() -> None:
    facts = project_facts_from_evidence(
        current_price=1680.5,
        change_pct=-1.2,
        as_of="2026-08-08",
        source_id="frozen-quote",
    )
    values = {f["value"] for f in facts}
    assert 1680.5 in values
    assert -1.2 in values


def test_project_facts_bounds_input_and_rejects_non_finite_values() -> None:
    raw_facts = [
        {"fact_id": "nan", "value": float("nan")},
        {"fact_id": "inf", "value": float("inf")},
        {"fact_id": "huge", "value": 10**10_000},
    ] + [
        {
            "fact_id": f"fact-{index}",
            "field_path": "quote.price",
            "value": float(index),
            "unit": "price",
            "as_of": "2026-08-08",
            "source_id": "fixture",
        }
        for index in range(300)
    ]
    facts = project_facts_from_evidence(evidence_context={"facts": raw_facts})
    assert len(facts) <= 256
    assert all(fact["fact_id"] not in {"nan", "inf", "huge"} for fact in facts)


def test_project_facts_consumes_real_technical_context() -> None:
    facts = project_facts_from_evidence(
        technical_context=SimpleNamespace(
            ma5=10.5,
            support_levels=[9.8],
            resistance_levels=[11.2],
        )
    )
    paths = {fact["field_path"] for fact in facts}
    assert "technical.ma5" in paths
    assert "technical.support_levels.0" in paths
    assert "technical.resistance_levels.0" in paths


def test_grounded_structured_claims_pass() -> None:
    facts = [
        {
            "fact_id": "quote-price",
            "field_path": "quote.price",
            "value": 1680.5,
            "unit": "CNY",
            "as_of": "2026-08-08",
            "source_id": "frozen-quote",
        }
    ]
    claims = [
        {
            "claim_id": "reported-price",
            "source_fact_id": "quote-price",
            "field_path": "quote.price",
            "value": 1680.5,
            "unit": "CNY",
            "as_of": "2026-08-08",
            "source_id": "frozen-quote",
        }
    ]
    checks = score_factuality({"facts": facts}, {"claims": claims}, {})
    assert all(c.passed for c in checks if not c.skipped)

    result = _result(claims=claims, verified_facts=[])
    gate = apply_analysis_quality_gate(
        result,
        evidence_context={"facts": facts},
        config=SimpleNamespace(
            analysis_quality_gate_enabled=True,
            analysis_quality_gate_on_failure="annotate",
        ),
    )
    assert gate.verdict is QualityGateVerdict.PASS
    assert gate.passed is True
    assert result.quality_gate_result is not None
    assert result.quality_gate_result["schema_version"] == QUALITY_GATE_SCHEMA_VERSION
    assert "eval_hook" in result.quality_gate_result
    assert "factuality" in result.quality_gate_result["eval_hook"]["dimensions"]


def test_rule_scoring_is_deterministic() -> None:
    facts = project_facts_from_evidence(current_price=10.0, as_of="2026-08-08")
    result = _result(verified_facts=["Current price is 10.0."], price=10.0)
    claims, _ungrounded, _statements = project_claims_from_result(
        result,
        facts=facts,
    )
    first = evaluate_analysis_quality(facts=facts, claims=claims, result=result)
    second = evaluate_analysis_quality(facts=facts, claims=claims, result=result)
    assert first == second


def test_quality_gate_trace_round_trips_through_history_rebuild() -> None:
    result = _result(verified_facts=[], claims=[])
    gate = apply_analysis_quality_gate(result)
    raw_result = result.to_dict()
    assert raw_result["quality_gate_result"] == gate.to_trace_dict()

    record = SimpleNamespace(
        code=result.code,
        name=result.name,
        sentiment_score=result.sentiment_score,
        trend_prediction=result.trend_prediction,
        operation_advice=result.operation_advice,
        news_content="",
        analysis_summary=result.analysis_summary,
    )
    restored = HistoryService.__new__(HistoryService)._rebuild_analysis_result(
        raw_result,
        record,
    )
    assert restored is not None
    assert restored.quality_gate_result == gate.to_trace_dict()


def test_ungrounded_verified_fact_annotated_by_default() -> None:
    facts = [
        {
            "fact_id": "quote-price",
            "field_path": "quote.price",
            "value": 1680.5,
            "unit": "price",
            "as_of": "2026-08-08",
            "source_id": "frozen-quote",
        }
    ]
    result = _result(
        verified_facts=["Target price is 9999.0 with secret model upside."],
        claims=None,
        price=1680.5,
    )
    gate = apply_analysis_quality_gate(
        result,
        evidence_context={"facts": facts},
        config=SimpleNamespace(
            analysis_quality_gate_enabled=True,
            analysis_quality_gate_on_failure="annotate",
        ),
    )
    assert gate.verdict is QualityGateVerdict.ANNOTATE
    assert gate.passed is False
    assert result.success is True
    strata = result.dashboard["report_strata"]
    inference_text = " ".join(strata.get("model_inference") or [])
    assert "9999" in inference_text
    assert result.quality_gate_result["verdict"] == "annotate"
    assert result.quality_gate_result["eval_hook"]["rule_score"] is not None
    assert "factuality" in result.quality_gate_result["detail"]
    assert "ungrounded_claim" in result.quality_gate_result["failure_reason_codes"]


def test_ungrounded_intercept_fails_result() -> None:
    facts = [
        {
            "fact_id": "quote-price",
            "field_path": "quote.price",
            "value": 1680.5,
            "unit": "CNY",
            "as_of": "2026-08-08",
            "source_id": "frozen-quote",
        }
    ]
    claims = [
        {
            "claim_id": "fabricated-target",
            "source_fact_id": "quote-price",
            "field_path": "quote.price",
            "value": 9999.0,
            "unit": "CNY",
            "as_of": "2026-08-08",
            "source_id": "frozen-quote",
        }
    ]
    result = _result(claims=claims, verified_facts=[])
    gate = apply_analysis_quality_gate(
        result,
        evidence_context={"facts": facts},
        config=SimpleNamespace(
            analysis_quality_gate_enabled=True,
            analysis_quality_gate_on_failure="intercept",
        ),
    )
    assert gate.verdict is QualityGateVerdict.INTERCEPT
    assert result.success is False
    assert result.error_code == "quality_gate_intercept"
    assert result.quality_gate_result["verdict"] == "intercept"


def test_gate_exception_fail_closed_to_annotate(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _result(verified_facts=["Price 1680.5"], price=1680.5)

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("projected facts exploded")

    monkeypatch.setattr(
        "src.services.analysis_quality_gate.project_facts_from_evidence",
        _boom,
    )
    gate = apply_analysis_quality_gate(
        result,
        config=SimpleNamespace(
            analysis_quality_gate_enabled=True,
            analysis_quality_gate_on_failure="intercept",
        ),
    )
    assert gate.verdict is QualityGateVerdict.GATE_ERROR
    assert gate.fail_closed is True
    assert gate.failure_policy is QualityGateFailurePolicy.ANNOTATE
    assert result.quality_gate_result is not None
    assert result.quality_gate_result["fail_closed"] is True
    assert result.success is True
    assert result.error_code != "quality_gate_intercept"
    strata = result.dashboard["report_strata"]
    assert strata["verified_facts"] == []
    assert "1680.5" in " ".join(strata["model_inference"])
    assert gate.action_taken == "gate_error_demote_all_verified_facts"


def test_failed_analysis_is_not_reclassified_as_gate_success() -> None:
    result = _result(verified_facts=["Price 9999.0"], price=None)
    result.success = False
    result.error_code = "provider_unavailable"
    gate = apply_analysis_quality_gate(result)
    assert gate.verdict is QualityGateVerdict.SKIPPED
    assert gate.passed is False
    assert gate.action_taken == "skipped_failed_analysis"
    assert result.success is False
    assert result.error_code == "provider_unavailable"


def test_empty_dimension_override_cannot_bypass_factuality() -> None:
    result = _result(verified_facts=["Target price 9999.0"], price=10.0)
    gate = apply_analysis_quality_gate(result, dimensions=())
    assert gate.verdict is QualityGateVerdict.GATE_ERROR
    assert gate.fail_closed is True
    assert result.dashboard["report_strata"]["verified_facts"] == []


def test_disabled_gate_skipped_with_trace() -> None:
    result = _result(verified_facts=["Price 9999.0"], price=None)
    gate = apply_analysis_quality_gate(
        result,
        config=SimpleNamespace(
            analysis_quality_gate_enabled=False,
            analysis_quality_gate_on_failure="annotate",
        ),
    )
    assert gate.verdict is QualityGateVerdict.SKIPPED
    assert result.quality_gate_result["verdict"] == "skipped"


def test_project_claims_binds_matching_verified_fact() -> None:
    facts = project_facts_from_evidence(
        current_price=1680.5,
        as_of="2026-08-08",
        source_id="pipeline",
    )
    result = _result(
        verified_facts=["Current price is 1680.5 in the session."],
        price=1680.5,
    )
    claims, ungrounded, statements = project_claims_from_result(result, facts=facts)
    assert claims
    assert not ungrounded
    assert all(c["source_fact_id"] != "__missing__" for c in claims)
    assert statements


def test_runtime_dashboard_numeric_claim_uses_technical_evidence() -> None:
    result = _result(verified_facts=[], claims=None, price=10.0)
    result.dashboard["data_perspective"] = {
        "price_position": {"current_price": 10.0, "ma5": 9.5}
    }
    gate = apply_analysis_quality_gate(
        result,
        technical_context=SimpleNamespace(current_price=10.0, ma5=9.5),
    )
    assert gate.verdict is QualityGateVerdict.PASS
    assert gate.claim_count == 2
    assert result.dashboard["data_perspective"]["price_position"]["ma5"] == 9.5


def test_runtime_dashboard_invented_number_is_quarantined() -> None:
    result = _result(verified_facts=[], claims=None, price=10.0)
    result.dashboard["data_perspective"] = {
        "price_position": {"current_price": 9999.0, "ma5": 9.5}
    }
    gate = apply_analysis_quality_gate(
        result,
        technical_context=SimpleNamespace(current_price=10.0, ma5=9.5),
    )
    assert gate.verdict is QualityGateVerdict.ANNOTATE
    price_position = result.dashboard["data_perspective"]["price_position"]
    assert price_position["current_price"] is None
    assert price_position["ma5"] == 9.5
    assert "dashboard:data_perspective.price_position.current_price" in (
        gate.ungrounded_claim_ids
    )


def test_ambiguous_equal_values_do_not_bind_by_insertion_order() -> None:
    facts = [
        {
            "fact_id": "price",
            "field_path": "quote.price",
            "value": 10.0,
            "unit": "price",
            "as_of": "2026-08-08",
            "source_id": "fixture",
        },
        {
            "fact_id": "pe",
            "field_path": "fundamentals.pe",
            "value": 10.0,
            "unit": "ratio",
            "as_of": "2026-08-08",
            "source_id": "fixture",
        },
    ]
    result = _result(verified_facts=["The metric is 10.0."], price=None)
    claims, ungrounded, _statements = project_claims_from_result(result, facts=facts)
    assert claims[0]["source_fact_id"] == "__missing__"
    assert ungrounded == ["strata-fact-0-0"]


def test_percentage_claim_does_not_bind_to_equal_price() -> None:
    facts = [
        {
            "fact_id": "price",
            "field_path": "quote.price",
            "value": 10.0,
            "unit": "price",
            "as_of": "2026-08-08",
            "source_id": "fixture",
        }
    ]
    result = _result(verified_facts=["The change is 10%."], price=None)
    claims, ungrounded, _statements = project_claims_from_result(result, facts=facts)
    assert claims[0]["source_fact_id"] == "__missing__"
    assert ungrounded == ["strata-fact-0-0"]


def test_field_marker_does_not_bind_to_wrong_equal_value() -> None:
    facts = [
        {
            "fact_id": "price",
            "field_path": "quote.price",
            "value": 10.0,
            "unit": "price",
            "as_of": "2026-08-08",
            "source_id": "fixture",
        }
    ]
    result = _result(verified_facts=["PE is 10."], price=None)
    claims, ungrounded, _statements = project_claims_from_result(result, facts=facts)
    assert claims[0]["source_fact_id"] == "__missing__"
    assert ungrounded == ["strata-fact-0-0"]


def test_annotate_quarantines_failed_structured_claim() -> None:
    facts = [
        {
            "fact_id": "price",
            "field_path": "quote.price",
            "value": 10.0,
            "unit": "price",
            "as_of": "2026-08-08",
            "source_id": "fixture",
        }
    ]
    result = _result(
        claims=[
            {
                "claim_id": "invented-target",
                "source_fact_id": "price",
                "field_path": "quote.price",
                "value": 9999.0,
                "unit": "price",
                "as_of": "2026-08-08",
                "source_id": "fixture",
                "statement": "Target price is 9999.0.",
            }
        ],
        price=10.0,
    )
    gate = apply_analysis_quality_gate(
        result,
        evidence_context={"facts": facts},
    )
    assert gate.verdict is QualityGateVerdict.ANNOTATE
    assert result.dashboard["claims"] == []
    inference = " ".join(result.dashboard["report_strata"]["model_inference"])
    assert "9999.0" in inference
    assert "quarantine_structured_claims" in gate.action_taken


def test_invalid_structured_claim_set_is_fully_quarantined() -> None:
    facts = [
        {
            "fact_id": "price",
            "field_path": "quote.price",
            "value": 10.0,
            "unit": "price",
            "as_of": "2026-08-08",
            "source_id": "fixture",
        }
    ]
    duplicate_claim = {
        "claim_id": "duplicate",
        "source_fact_id": "price",
        "field_path": "quote.price",
        "value": 10.0,
        "unit": "price",
        "as_of": "2026-08-08",
        "source_id": "fixture",
    }
    result = _result(claims=[duplicate_claim, duplicate_claim], price=10.0)
    gate = apply_analysis_quality_gate(result, evidence_context={"facts": facts})
    assert gate.verdict is QualityGateVerdict.ANNOTATE
    assert "factuality_invalid" in gate.failure_reason_codes
    assert result.dashboard["claims"] == []
    assert "quarantine_all_structured_claims" in gate.action_taken


def test_gate_error_quarantines_all_structured_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _result(
        claims=[
            {
                "claim_id": "unchecked",
                "value": 9999.0,
                "statement": "Target price 9999.0",
            }
        ],
        price=None,
    )

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("scorer failed")

    monkeypatch.setattr(
        "src.services.analysis_quality_gate.evaluate_analysis_quality",
        _boom,
    )
    gate = apply_analysis_quality_gate(result)
    assert gate.verdict is QualityGateVerdict.GATE_ERROR
    assert result.dashboard["claims"] == []
    assert "quarantine_all_structured_claims" in gate.action_taken


def test_soft_limitations_do_not_fail_gate_without_invented_facts() -> None:
    """Review counterexample: routine limitations + buy/high must not annotate.

    Soft data_quality.limitations must not mark data_missing for the failure
    path. boundary_honesty may still appear as advisory checks in the hook.
    """
    overview = {
        "data_quality": {
            "level": "good",
            "limitations": ["news window partial"],
        },
        "blocks": [{"key": "quote", "status": "available"}],
    }
    result = AnalysisResult(
        code="AAPL",
        name="Apple",
        sentiment_score=70,
        trend_prediction="up",
        operation_advice="Buy",
        decision_type="buy",
        confidence_level="high",
        report_language="en",
        dashboard={},
        analysis_summary="buy",
        success=True,
        current_price=10.0,
        change_pct=1.0,
    )
    gate = apply_analysis_quality_gate(
        result,
        analysis_context_pack_overview=overview,
        config=SimpleNamespace(
            analysis_quality_gate_enabled=True,
            analysis_quality_gate_on_failure="annotate",
        ),
    )
    assert gate.verdict is QualityGateVerdict.PASS
    assert gate.passed is True
    assert result.success is True
    assert gate.failure_reason_codes == ()
    assert "boundary_honesty" in gate.dimensions
    assert result.quality_gate_result["eval_hook"]["failure_dimensions"] == [
        "factuality"
    ]
    assert "boundary_honesty" in result.quality_gate_result["eval_hook"][
        "advisory_dimensions"
    ]


def test_boundary_honesty_advisory_does_not_intercept() -> None:
    """Even under intercept policy, honesty-only signals must not hard-fail."""
    overview = {
        "data_quality": {"level": "good", "limitations": ["stale news"]},
        "blocks": [{"key": "quote", "status": "available"}],
    }
    result = AnalysisResult(
        code="AAPL",
        name="Apple",
        sentiment_score=70,
        trend_prediction="up",
        operation_advice="Buy",
        decision_type="buy",
        confidence_level="high",
        report_language="en",
        dashboard={},
        analysis_summary="buy",
        success=True,
        current_price=10.0,
    )
    gate = apply_analysis_quality_gate(
        result,
        analysis_context_pack_overview=overview,
        config=SimpleNamespace(
            analysis_quality_gate_enabled=True,
            analysis_quality_gate_on_failure="intercept",
        ),
    )
    assert gate.verdict is QualityGateVerdict.PASS
    assert result.success is True
    assert result.error_code != "quality_gate_intercept"
