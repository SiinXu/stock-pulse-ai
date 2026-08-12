# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.schemas.evidence_chain import EvidenceChainPackage
from src.services.evidence_chain_service import (
    EvidenceChainDisabled, EvidenceChainService, build_evidence_chain_package,
    is_evidence_chain_enabled, render_evidence_chain_markdown,
)
FIXTURE_STRATA = Path(__file__).parents[1] / "fixtures" / "report_strata" / "full_strata.json"

def _base_raw_result():
    strata = json.loads(FIXTURE_STRATA.read_text(encoding="utf-8"))
    return {
        "dashboard": {
            "report_strata": strata,
            "core_conclusion": {
                "decision_type": "hold", "operation_advice": "hold",
                "confidence_level": "medium",
                "analysis_summary": "Constructive near-term case with valuation risk.",
            },
            "strategy_synthesis": {"final_signal": "hold"},
        },
        "operation_advice": "hold", "model_used": "test-model",
    }

def _diagnostics():
    return {
        "trace_id": "abcd1234abcd1234abcd1234abcd1234",
        "provider_runs": [{"provider": "eastmoney", "data_type": "ohlcv", "operation": "daily", "status": "ok"}],
        "llm_runs": [{"provider": "openai", "model": "gpt-test", "call_type": "analysis", "status": "ok"}],
        "pipeline_stage_runs": [{"stage": "analyze", "status": "ok"}],
        "agent_events": [
            {"event_type": "tool_call", "name": "technical_agent", "tool_name": "get_indicators",
             "status": "ok", "timestamp": "2026-08-01T10:00:00Z"},
            {"event_type": "agent_complete", "name": "technical_agent", "status": "ok",
             "summary": "momentum constructive", "timestamp": "2026-08-01T10:00:01Z"},
        ],
    }

def test_is_evidence_chain_enabled_defaults_true():
    assert is_evidence_chain_enabled(None) is True
    assert is_evidence_chain_enabled(SimpleNamespace(evidence_chain_enabled=False)) is False

def test_build_links_verified_facts_to_evidence():
    result = build_evidence_chain_package(
        run_id="run-1", record_id="42", diagnostics=_diagnostics(), raw_result=_base_raw_result(),
    )
    package = result.package
    EvidenceChainPackage.model_validate(package)
    facts = [c for c in package["conclusions"] if c["stratum"] == "verified_fact"]
    assert facts
    assert all(c["evidence_status"] == "partial" for c in facts)
    assert all(c["missing_note"] for c in facts)
    strata_items = [e for e in package["evidence_items"] if e["source_type"] == "report_strata"]
    assert strata_items and all(e["status"] == "partial" for e in strata_items)
    source_types = {e["source_type"] for e in package["evidence_items"]}
    assert "data_source" in source_types and "tool_call" in source_types
    assert package["reasoning_steps"]

def test_missing_evidence_is_explicit_never_omitted():
    raw = _base_raw_result()
    for fact in raw["dashboard"]["report_strata"]["verified_facts"]:
        fact.pop("source_id", None); fact.pop("as_of", None)
    package = build_evidence_chain_package(run_id="run-m", record_id="7", diagnostics={}, raw_result=raw).package
    EvidenceChainPackage.model_validate(package)
    facts = [c for c in package["conclusions"] if c["stratum"] == "verified_fact"]
    for fact in facts:
        assert fact["evidence_status"] in {"missing", "partial"}
        assert fact.get("missing_note")
        assert fact["as_of_status"] == "missing"
    assert package["evidence_items"]
    assert any(e["status"] == "missing" for e in package["evidence_items"])
    assert package["gaps"]
    cov = {s["source"]: s for s in package["coverage"]["sources"]}
    assert cov["diagnostics.provider_runs"]["absent"] is True
    assert package["coverage"]["not_recorded"]

def test_redaction_counterexamples_api_key_bearer_and_local_path():
    secret_key = "sk-ant-api03-THIS_IS_A_FAKE_KEY_FOR_TEST_ONLY_1234567890"
    bearer = "Bearer FAKESECRET_m4n5o6p7q8r9s0t1u2v3"
    local_path = "/Users/siin/secret/portfolio.csv"
    raw = _base_raw_result()
    raw["dashboard"]["core_conclusion"]["analysis_summary"] = f"Use key {secret_key} and token {bearer} from {local_path}"
    diag = _diagnostics()
    diag["agent_events"].append({
        "event_type": "tool_call", "name": "intel_agent", "tool_name": "fetch_news", "status": "ok",
        "summary": f"downloaded {local_path} with {secret_key}", "timestamp": "2026-08-01T10:00:02Z",
    })
    dumped = json.dumps(build_evidence_chain_package(
        run_id="run-s", record_id="99", diagnostics=diag, raw_result=raw,
    ).package, ensure_ascii=False)
    assert secret_key not in dumped
    assert bearer not in dumped
    assert local_path not in dumped
    assert "/Users/siin/" not in dumped

def test_render_markdown_mentions_missing_explicitly():
    md = render_evidence_chain_markdown(build_evidence_chain_package(
        run_id="run-md", record_id="1", diagnostics={}, raw_result=_base_raw_result(),
    ).package, language="en")
    assert "Evidence & Audit" in md
    assert "missing" in md.lower()

def test_failed_source_runs_do_not_support_decisions():
    diagnostics = _diagnostics()
    for key in ("provider_runs", "llm_runs", "pipeline_stage_runs"):
        for item in diagnostics[key]:
            item["status"] = "failed"
    for item in diagnostics["agent_events"]:
        item["status"] = "failed"
    package = build_evidence_chain_package(
        run_id="run-failed", record_id="8", diagnostics=diagnostics,
        raw_result=_base_raw_result(),
    ).package
    decision = next(item for item in package["conclusions"] if item["stratum"] == "decision")
    assert decision["evidence_status"] == "missing"
    assert decision["evidence_refs"] == []
    assert any(item["status"] == "missing" for item in package["evidence_items"])

def test_service_disabled_raises():
    service = EvidenceChainService(
        history_service=SimpleNamespace(_resolve_record=lambda _id: object()),
        config=SimpleNamespace(evidence_chain_enabled=False),
    )
    with pytest.raises(EvidenceChainDisabled):
        service.build_for_record("1")
