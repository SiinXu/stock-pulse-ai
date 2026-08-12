# -*- coding: utf-8 -*-
from __future__ import annotations
import io, json, zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.schemas.evidence_chain import AuditPackageManifest
from src.services.audit_package_export_service import (
    AuditPackageExportDisabled, AuditPackageExportService, is_audit_export_enabled,
)
from src.services.evidence_chain_service import EvidenceChainDisabled
FIXTURE_STRATA = Path(__file__).parents[1] / "fixtures" / "report_strata" / "full_strata.json"

class _FakeRecord:
    def __init__(self):
        self.id = 42; self.query_id = "q-audit-1"; self.code = "600519"
        self.name = "Kweichow Moutai"; self.market = "CN"; self.model_used = "test-model"
        self.created_at = "2026-08-01T12:00:00"
        strata = json.loads(FIXTURE_STRATA.read_text(encoding="utf-8"))
        self.raw_result = json.dumps({
            "dashboard": {
                "report_strata": strata,
                "core_conclusion": {"decision_type": "hold", "operation_advice": "hold",
                                    "confidence_level": "medium", "analysis_summary": "summary"},
                "strategy_synthesis": {"final_signal": "hold"},
                "decision_signal": {"action": "hold", "score": 0.5,
                                    "api_key": "sk-test-SHOULD_NOT_LEAK_1234567890abcdef"},
            },
            "operation_advice": "hold",
        })
        self.context_snapshot = json.dumps({
            "diagnostics": {
                "trace_id": "abcd1234abcd1234abcd1234abcd1234",
                "provider_runs": [{"provider": "eastmoney", "data_type": "ohlcv", "operation": "daily", "status": "ok"}],
                "agent_events": [{"event_type": "tool_call", "name": "technical_agent",
                                  "tool_name": "get_indicators", "status": "ok",
                                  "timestamp": "2026-08-01T10:00:00Z"}],
                "llm_runs": [], "pipeline_stage_runs": [{"stage": "analyze", "status": "ok"}],
            }
        })

class _FakeHistory:
    def __init__(self): self._record = _FakeRecord()
    def _resolve_record(self, record_id):
        return self._record if record_id in {"42", "q-audit-1"} else None
    def _parse_diagnostic_json_field(self, value, field_name):
        if value is None: return None
        if isinstance(value, (dict, list)): return value
        if isinstance(value, str) and value.strip(): return json.loads(value)
        return None
    def get_markdown_report(self, record_id):
        return ("# Test Report\n\nHold recommendation.\n"
                "Secret path: /Users/siin/secret/keys.env\n"
                "Token: sk-ant-api03-FAKE_SECRET_FOR_TEST_ONLY_ABCDEFG\n")

def test_is_audit_export_enabled_defaults_false():
    assert is_audit_export_enabled(None) is False
    assert is_audit_export_enabled(SimpleNamespace(audit_export_enabled=True)) is True

def test_export_disabled_raises():
    service = AuditPackageExportService(
        history_service=_FakeHistory(),
        config=SimpleNamespace(audit_export_enabled=False, evidence_chain_enabled=True),
    )
    with pytest.raises(AuditPackageExportDisabled):
        service.export_for_record("42")

def test_evidence_chain_disabled_blocks_package():
    service = AuditPackageExportService(
        history_service=_FakeHistory(),
        config=SimpleNamespace(audit_export_enabled=True, evidence_chain_enabled=False,
                               audit_include_raw_artifacts=False, report_language="en"),
    )
    with pytest.raises(EvidenceChainDisabled):
        service.export_for_record("42")

def test_zip_contains_manifest_chain_and_explicit_missing_markers():
    service = AuditPackageExportService(
        history_service=_FakeHistory(),
        config=SimpleNamespace(audit_export_enabled=True, evidence_chain_enabled=True,
                               audit_include_raw_artifacts=False, report_language="en",
                               reasoning_trace_export_max_chars=500_000),
    )
    result = service.export_for_record("42")
    assert result.zip_bytes[:2] == b"PK"
    AuditPackageManifest.model_validate(result.manifest)
    with zipfile.ZipFile(io.BytesIO(result.zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names and "evidence_chain.json" in names
        assert "gaps.json" in names and "report.md" in names
        assert "reasoning_trace.json" in names
        assert "raw_intermediates/SKIPPED.txt" in names
        manifest = json.loads(zf.read("manifest.json"))
        statuses = {a["name"]: a["status"] for a in manifest["artifacts"]}
        assert statuses["evidence_chain.json"] == "present"
        assert statuses["raw_intermediates/"] == "skipped"
        report = zf.read("report.md").decode("utf-8")
        assert "/Users/siin/secret/keys.env" not in report
        assert "sk-ant-api03-FAKE_SECRET_FOR_TEST_ONLY_ABCDEFG" not in report
        whole = zf.read("decision_signal.json").decode("utf-8")
        assert "sk-test-SHOULD_NOT_LEAK" not in whole

def test_json_envelope_shape():
    result = AuditPackageExportService(
        history_service=_FakeHistory(),
        config=SimpleNamespace(audit_export_enabled=True, evidence_chain_enabled=True,
                               audit_include_raw_artifacts=False, report_language="en",
                               reasoning_trace_export_max_chars=500_000),
    ).export_for_record("42")
    envelope = result.to_json_envelope()
    assert envelope["schema_version"] == "audit-package-v1"
    assert envelope["evidence_chain"]["schema_version"] == "evidence-chain-v1"
