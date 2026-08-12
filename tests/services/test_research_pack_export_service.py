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
