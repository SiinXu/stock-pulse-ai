# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations
import io, json, zipfile
from types import SimpleNamespace
from typing import Any, Dict, Optional
import pytest
from src.services.research_pack_export_service import (
    DEFAULT_MAX_ZIP_BYTES, ResearchPackExportDisabled, ResearchPackExportService,
    ResearchPackLimitError, ResearchPackNotFound, get_research_pack_max_zip_bytes,
    is_research_pack_export_enabled,
)
from src.services.reasoning_trace_export_service import redact_export_payload as shared_redact

class _FakeHistory:
    def __init__(self, record, *, markdown="# Report\n\n### 🃏 Decision Card\n- Action: Buy\n", news=None):
        self._record, self._markdown, self._news = record, markdown, news or []
    def _resolve_record(self, record_id): return self._record
    def get_markdown_report(self, record_id): return self._markdown
    def resolve_and_get_news(self, record_id, limit=20): return self._news[:limit]
    def _parse_diagnostic_json_field(self, value, field_name):
        if value is None: return None
        if isinstance(value, (dict, list)): return value
        if isinstance(value, str): return json.loads(value) if value.strip() else None
        return value

def _record(**overrides):
    base = {
        "id": 42, "query_id": "q-research-pack-1", "code": "600519", "name": "Kweichow Moutai",
        "operation_advice": "Buy", "analysis_summary": "Thesis holds while volume confirms.",
        "trend_prediction": "up", "sentiment_score": 72, "stop_loss": "1600", "take_profit": "1900",
        "created_at": None,
        "raw_result": {
            "model_used": "test-model", "operation_advice": "Buy",
            "analysis_summary": "Thesis holds while volume confirms.",
            "dashboard": {
                "core_conclusion": {"operation_advice": "Buy", "analysis_summary": "Thesis holds while volume confirms.",
                                    "confidence_level": "high", "key_risks": ["macro"]},
                "signal_attribution": {"weights": [{"name": "technical", "weight": 0.4}]},
            },
            "prediction_claims": [{"text": "Price stays above 1700 in 5d", "horizon": "5d"}],
        },
        "context_snapshot": {
            "diagnostics": {
                "trace_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "provider_runs": [{"provider": "eastmoney", "status": "ok"}],
                "agent_events": [{"event_type": "tool_call", "tool_name": "get_daily", "agent_role": "technical", "summary": "ok"}],
            }
        },
    }
    base.update(overrides)
    return SimpleNamespace(**base)

def _enabled_config(**extra):
    data = {"research_pack_export_enabled": True, "research_pack_max_zip_bytes": DEFAULT_MAX_ZIP_BYTES,
            "report_language": "en", "reasoning_trace_export_max_chars": 500_000}
    data.update(extra)
    return SimpleNamespace(**data)

def _unzip(zip_bytes):
    out = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            out[name] = zf.read(name)
    return out

def test_flag_defaults_off():
    assert is_research_pack_export_enabled(SimpleNamespace()) is False

def test_max_zip_bytes_clamped():
    assert get_research_pack_max_zip_bytes(SimpleNamespace(research_pack_max_zip_bytes=100)) == 1 * 1024 * 1024

def test_max_zip_bytes_rejects_non_finite_config():
    config = SimpleNamespace(research_pack_max_zip_bytes=float("inf"))
    assert get_research_pack_max_zip_bytes(config) == DEFAULT_MAX_ZIP_BYTES

def test_export_disabled_raises():
    service = ResearchPackExportService(history_service=_FakeHistory(_record()), config=SimpleNamespace(research_pack_export_enabled=False))
    with pytest.raises(ResearchPackExportDisabled):
        service.export_for_record("42")

def test_export_not_found():
    service = ResearchPackExportService(history_service=_FakeHistory(None), config=_enabled_config())
    with pytest.raises(ResearchPackNotFound):
        service.export_for_record("missing")

def test_export_zip_structure_and_progress():
    stages = []
    service = ResearchPackExportService(
        history_service=_FakeHistory(_record(), news=[{"title": "Moutai volume rises", "snippet": "Turnover up"}]),
        config=_enabled_config(),
    )
    result = service.export_for_record("42", progress_callback=lambda n, s, d: stages.append((n, s)), language="en")
    assert result.schema_version == "research-pack-v1"
    assert result.resolved_record_id == "42"
    assert any(n == "assemble_zip" and s == "completed" for n, s in stages)
    files = _unzip(result.zip_bytes)
    names = sorted(files)
    for suffix in ("/report.md", "/brief-card.md", "/signals.json", "/evidence-refs.json",
                   "/evidence-summary.md", "/reasoning-trace.json", "/claims-outcomes.json",
                   "/meta.json", "/README.md"):
        assert any(n.endswith(suffix) for n in names), suffix
    meta = json.loads(next(v for k, v in files.items() if k.endswith("/meta.json")))
    assert meta["share_mode"] is True
    assert meta["evidence_chain_status"] == "deferred"
    assert any(p.get("name") == "report" for p in meta["progress"])
    signals = json.loads(next(v for k, v in files.items() if k.endswith("/signals.json")))
    assert signals["status"] == "present"
    evidence = json.loads(next(v for k, v in files.items() if k.endswith("/evidence-refs.json")))
    assert evidence["count"] >= 1
    claims = json.loads(next(v for k, v in files.items() if k.endswith("/claims-outcomes.json")))
    assert claims["claims_status"] == "present"

@pytest.mark.parametrize("report_mode", ["brief", "standard", "research"])
def test_export_preserves_all_report_modes_and_decision_card(report_mode):
    marker = f"mode-marker:{report_mode}"
    markdown = f"# Report\n\n{marker}\n\n### 🃏 Decision Card\n- Action: Hold\n"
    record = _record(report_type=report_mode)
    result = ResearchPackExportService(
        history_service=_FakeHistory(record, markdown=markdown),
        config=_enabled_config(),
    ).export_for_record("42")

    files = _unzip(result.zip_bytes)
    report = next(v for k, v in files.items() if k.endswith("/report.md")).decode()
    brief_card = next(
        v for k, v in files.items() if k.endswith("/brief-card.md")
    ).decode()
    meta = json.loads(next(v for k, v in files.items() if k.endswith("/meta.json")))

    assert marker in report
    assert "Decision Card" in brief_card
    assert meta["report_mode"] == report_mode

def test_non_finite_metrics_are_explicitly_not_calculable():
    record = _record(
        sentiment_score=float("nan"),
        raw_result={
            "model_used": "test-model",
            "operation_advice": "Hold",
            "analysis_summary": "Insufficient finite metrics.",
            "decision_signal": {
                "score": float("nan"),
                "strength": float("inf"),
            },
            "dashboard": {"core_conclusion": {"operation_advice": "Hold"}},
        },
    )
    result = ResearchPackExportService(
        history_service=_FakeHistory(record),
        config=_enabled_config(),
    ).export_for_record("42")
    files = _unzip(result.zip_bytes)

    def reject_constant(value):
        raise AssertionError(f"non-finite JSON constant exported: {value}")

    for name, payload in files.items():
        if name.endswith(".json"):
            json.loads(payload, parse_constant=reject_constant)
    brief_card = next(
        v for k, v in files.items() if k.endswith("/brief-card.md")
    ).decode()
    signals = json.loads(
        next(v for k, v in files.items() if k.endswith("/signals.json"))
    )
    assert "Not calculable" in brief_card
    assert "Not evaluated" in brief_card
    assert signals["status"] == "not_calculable"
    assert signals["signal"]["not_calculable_fields"] == ["score", "strength"]

def test_risk_gate_verdict_is_rendered_when_evaluated():
    record = _record()
    record.raw_result["risk_gate_result"] = {"verdict": "downgrade"}
    result = ResearchPackExportService(
        history_service=_FakeHistory(record),
        config=_enabled_config(),
    ).export_for_record("42")
    files = _unzip(result.zip_bytes)
    brief_card = next(
        v for k, v in files.items() if k.endswith("/brief-card.md")
    ).decode()
    assert "Risk conclusion**: downgrade" in brief_card
    assert "Not evaluated" not in brief_card

REDACT_COUNTEREXAMPLES = {
    "openai_key": "sk-abcdefghijklmnopqrstuvwxyz1234567890ABCD",
    "anthropic_key": "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "github_pat": "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "bearer": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlWFla",
    "local_path": "/Users/alice/secrets/config.env",
    "credentialed_url": "https://user:p4ssw0rd@example.com/v1/data",
}

@pytest.mark.parametrize("label,secret", list(REDACT_COUNTEREXAMPLES.items()), ids=list(REDACT_COUNTEREXAMPLES))
def test_redaction_counterexamples_absent_from_zip(label, secret):
    assert shared_redact({"probe": secret})["probe"] != secret
    poisoned = f"# Report\n\nAPI key: {secret}\n\n### 🃏 Decision Card\n- Action: Hold\n"
    record = _record(
        analysis_summary=f"summary with {secret}",
        raw_result={"model_used": "test-model", "operation_advice": "Hold", "analysis_summary": f"leak {secret}",
                    "dashboard": {"core_conclusion": {"operation_advice": "Hold", "analysis_summary": f"leak {secret}", "key_risks": [f"risk {secret}"]}}},
        context_snapshot={"diagnostics": {"trace_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                                          "provider_runs": [{"provider": "test", "summary": f"used {secret}"}],
                                          "agent_events": [{"event_type": "tool_call", "tool_name": "fetch", "summary": f"arg={secret}"}]}},
    )
    result = ResearchPackExportService(history_service=_FakeHistory(record, markdown=poisoned), config=_enabled_config()).export_for_record("42")
    joined = b"\n".join(_unzip(result.zip_bytes).values()).decode("utf-8", errors="replace")
    assert secret not in joined
    assert secret.encode("utf-8") not in result.zip_bytes

def test_zip_size_bound_recorded():
    high_entropy = "# Report\n" + "".join(chr(32 + (i % 90)) for i in range(200_000))
    service = ResearchPackExportService(history_service=_FakeHistory(_record(), markdown=high_entropy),
                                        config=_enabled_config(research_pack_max_zip_bytes=1 * 1024 * 1024))
    result = service.export_for_record("42")
    assert len(result.zip_bytes) <= 1 * 1024 * 1024
    assert result.meta["limits"]["max_zip_bytes"] == 1 * 1024 * 1024

def test_progress_callback_sequence():
    seen = []
    ResearchPackExportService(history_service=_FakeHistory(_record()), config=_enabled_config()).export_for_record(
        "42", progress_callback=lambda n, s, d: seen.append(n) if s in ("completed", "skipped", "failed") else None)
    assert "resolve_record" in seen and "assemble_zip" in seen


def test_json_mode_skips_zip_assembly():
    service = ResearchPackExportService(
        history_service=_FakeHistory(_record()),
        config=_enabled_config(),
    )
    result = service.export_for_record("42", include_zip=False)
    assert result.zip_included is False
    assert result.zip_bytes == b""
    assert result.content_byte_length > 0
    envelope = result.to_json_envelope()
    assert envelope["zip_included"] is False
    assert envelope["byte_length"] == result.content_byte_length
    assert result.meta.get("zip_included") is False
    assert "zip_byte_length" not in result.meta or result.meta.get("zip_byte_length") is None


def test_zip_meta_byte_length_matches_archive():
    service = ResearchPackExportService(
        history_service=_FakeHistory(_record()),
        config=_enabled_config(),
    )
    result = service.export_for_record("42", include_zip=True)
    assert result.zip_included is True
    assert len(result.zip_bytes) > 0
    files = _unzip(result.zip_bytes)
    meta = json.loads(next(v for k, v in files.items() if k.endswith("/meta.json")))
    assert meta["zip_byte_length"] == len(result.zip_bytes)
    assert meta.get("zip_included") is True
