# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for reasoning-trace export (Issue #135 / T03)."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from api.v1.schemas.reasoning_trace import ReasoningTraceExportResponse
from src.services.reasoning_trace_export_service import (
    MAX_MAX_EXPORT_CHARS,
    SCHEMA_VERSION,
    ReasoningTraceExportDisabled,
    ReasoningTraceExportService,
    ReasoningTraceNotFound,
    build_reasoning_trace_package,
    is_reasoning_trace_export_enabled,
    resolve_max_export_chars,
)


FAKE_API_KEY = "sk-test-secret-key-DO-NOT-LEAK-1234567890"
FAKE_TOKEN = "Bearer ghp_exampleTokenValueABCDEF1234567890"
FAKE_PATH = "/Users/alice/.config/stock-pulse/secrets.env"
FAKE_URL = "https://user:p4ssw0rd@api.example.com/v1/chat"


def _source_payload() -> Dict[str, Any]:
    return {
        "diagnostics": {
            "trace_id": "trace-abc",
            "query_id": "q-1",
            "stock_code": "600519",
            "agent_events": [
                {
                    "event_type": "agent.tool_start",
                    "name": "get_quote",
                    "status": "ok",
                    "sequence": 1,
                    "timestamp": "2026-08-09T00:00:00Z",
                    "attrs": {
                        "agent": "research",
                        "tool": "get_quote",
                        "api_key": FAKE_API_KEY,
                        "authorization": FAKE_TOKEN,
                    },
                },
                {
                    "event_type": "agent.decision",
                    "name": "research",
                    "sequence": 2,
                    "attrs": {
                        "agent": "research",
                        "signal": "buy",
                        "summary": f"used key {FAKE_API_KEY} from {FAKE_PATH}",
                    },
                },
                {
                    "event_type": "agent.decision",
                    "name": "risk",
                    "sequence": 3,
                    "attrs": {"agent": "risk", "signal": "hold"},
                },
            ],
            "provider_runs": [
                {
                    "provider": "yfinance",
                    "data_type": "daily",
                    "operation": "fetch",
                    "status": "success",
                    "base_url": FAKE_URL,
                }
            ],
            "llm_runs": [
                {
                    "provider": "openai",
                    "model": "gpt-test",
                    "call_type": "analysis",
                    "status": "success",
                    "api_key": FAKE_API_KEY,
                }
            ],
            "pipeline_stage_runs": [
                {"stage": "fetch", "status": "success", "duration_ms": 12}
            ],
        },
        "raw_result": {
            "code": "600519",
            "name": "Kweichow Moutai",
            "model_used": "gpt-test",
            "decision_type": "buy",
            "operation_advice": "accumulate on dips",
            "analysis_summary": "bullish with risk check",
            "sentiment_score": 72,
            "dashboard": {
                "core_conclusion": {
                    "decision_type": "buy",
                    "operation_advice": "accumulate on dips",
                    "confidence_level": "中",
                    "analysis_summary": "bullish with risk check",
                },
                "strategy_synthesis": {
                    "final_signal": "buy",
                    "consensus_level": "partial",
                    "conflict_severity": "low",
                    "conflict_count": 1,
                    "supporting_skills": ["momentum"],
                    "opposing_skills": ["mean_reversion"],
                },
                "committee_deliberation": {
                    "status": "completed",
                    "personas": [{"persona_id": "value", "signal": "buy"}],
                },
            },
        },
        "context_snapshot": {
            "analysis_context_pack_overview": {
                "data_quality": {"status": "ok", "warnings": []},
            }
        },
    }


def test_export_schema_contract() -> None:
    src = _source_payload()
    result = build_reasoning_trace_package(
        run_id="q-1",
        stock_code="600519",
        market="CN",
        diagnostics=src["diagnostics"],
        raw_result=src["raw_result"],
        context_snapshot=src["context_snapshot"],
        config=SimpleNamespace(
            agent_observability_enabled=True,
            agent_observability_deep_payload=False,
            agent_multi_strategy_deliberation=False,
            agent_risk_override=True,
            generation_backend="litellm",
            report_type="simple",
            report_language="zh",
        ),
    )
    package = result.package
    assert package["schema_version"] == SCHEMA_VERSION
    assert package["run"]["run_id"] == "q-1"
    assert package["run"]["stock_code"] == "600519"
    assert package["run"]["config_fingerprint"]
    assert isinstance(package["agents"], list)
    assert len(package["agents"]) >= 1
    assert "synthesis" in package
    assert package["synthesis"]["final_conclusion"]["final_signal"] == "buy"
    assert package["data_sources"]["data_quality_status"]["status"] == "ok"
    assert "sources" in package["coverage"]
    assert "not_recorded" in package["coverage"]
    ReasoningTraceExportResponse.model_validate(package)
    json.dumps(package, ensure_ascii=False, allow_nan=False)
    assert result.markdown.startswith("# Reasoning Trace")


def test_redaction_strips_secrets_from_export() -> None:
    """Mandatory acceptance: injected secrets must never appear in the export."""
    src = _source_payload()
    result = build_reasoning_trace_package(
        run_id="q-secret",
        diagnostics=src["diagnostics"],
        raw_result=src["raw_result"],
        context_snapshot=src["context_snapshot"],
    )
    blob = json.dumps(result.package, ensure_ascii=False) + "\n" + result.markdown
    assert FAKE_API_KEY not in blob
    assert FAKE_TOKEN not in blob
    assert "p4ssw0rd" not in blob
    # Local home path segments should be redacted by shared sanitizer.
    assert FAKE_PATH not in blob
    assert "sk-test-secret-key" not in blob


def test_export_disabled_by_default() -> None:
    assert is_reasoning_trace_export_enabled(SimpleNamespace()) is False
    assert (
        is_reasoning_trace_export_enabled(
            SimpleNamespace(reasoning_trace_export_enabled=False)
        )
        is False
    )
    service = ReasoningTraceExportService(
        history_service=SimpleNamespace(),
        config=SimpleNamespace(reasoning_trace_export_enabled=False),
    )
    with pytest.raises(ReasoningTraceExportDisabled):
        service.ensure_enabled()


def test_export_enabled_flag() -> None:
    assert (
        is_reasoning_trace_export_enabled(
            SimpleNamespace(reasoning_trace_export_enabled=True)
        )
        is True
    )


def test_size_budget_sets_explicit_truncation_marker() -> None:
    events = []
    for i in range(80):
        events.append(
            {
                "event_type": "agent.phase_end",
                "name": f"phase-{i}",
                "sequence": i,
                "attrs": {
                    "agent": f"agent-{i % 5}",
                    "summary": ("x" * 2000),
                },
            }
        )
    result = build_reasoning_trace_package(
        run_id="q-big",
        diagnostics={"agent_events": events, "provider_runs": [], "llm_runs": []},
        raw_result={
            "code": "AAPL",
            "decision_type": "hold",
            "dashboard": {
                "committee_deliberation": {
                    "notes": ["y" * 3000 for _ in range(20)],
                    "personas": [{"persona_id": f"p{i}", "text": "z" * 2000} for i in range(30)],
                },
                "strategy_synthesis": {
                    "final_signal": "hold",
                    "detail": "w" * 8000,
                },
            },
        },
        max_chars=8_000,
    )
    assert result.package.get("truncated") is True
    assert result.package.get("truncation", {}).get("marker") == "truncated"
    assert result.package["truncation"]["reason"] == "export_size_budget_exceeded"


def test_service_export_for_record_uses_history() -> None:
    src = _source_payload()
    record = SimpleNamespace(
        query_id="q-1",
        code="600519",
        name="Kweichow Moutai",
        model_used="gpt-test",
        created_at=None,
        context_snapshot=json.dumps(
            {
                "diagnostics": src["diagnostics"],
                "analysis_context_pack_overview": src["context_snapshot"][
                    "analysis_context_pack_overview"
                ],
            }
        ),
        raw_result=json.dumps(src["raw_result"]),
    )
    history = SimpleNamespace(
        _resolve_record=lambda record_id: record,
        _parse_diagnostic_json_field=lambda value, field: (
            json.loads(value) if isinstance(value, str) and value.strip() else value
        ),
    )
    service = ReasoningTraceExportService(
        history_service=history,
        config=SimpleNamespace(
            reasoning_trace_export_enabled=True,
            reasoning_trace_export_max_chars=500_000,
        ),
    )
    result = service.export_for_record("1")
    assert result.package["schema_version"] == SCHEMA_VERSION
    assert result.package["run"]["stock_code"] == "600519"
    blob = json.dumps(result.package, ensure_ascii=False)
    assert FAKE_API_KEY not in blob


def test_service_not_found() -> None:
    history = SimpleNamespace(
        _resolve_record=lambda record_id: None,
        _parse_diagnostic_json_field=lambda value, field: value,
    )
    service = ReasoningTraceExportService(
        history_service=history,
        config=SimpleNamespace(reasoning_trace_export_enabled=True),
    )
    with pytest.raises(ReasoningTraceNotFound):
        service.export_for_record("missing")


def test_complete_json_and_markdown_responses_obey_hard_budget() -> None:
    huge_quality = {
        "status": "ok",
        "warnings": ["w" * 20_000 for _ in range(100)],
        "unprojected_blob": "x" * 100_000,
    }
    for output_format, include_markdown in (("json", True), ("markdown", True)):
        result = build_reasoning_trace_package(
            run_id="budget-run",
            context_snapshot={
                "analysis_context_pack_overview": {"data_quality": huge_quality}
            },
            raw_result={"analysis_summary": "s" * 100_000},
            max_chars=10_000,
            include_markdown=include_markdown,
            output_format=output_format,
        )
        if output_format == "json":
            assert len(result.to_json_text()) <= 10_000
        else:
            assert len(result.markdown) <= 10_000
        assert result.package["truncated"] is True


def test_non_finite_and_unknown_numeric_values_are_not_exported() -> None:
    result = build_reasoning_trace_package(
        run_id="finite-run",
        diagnostics={
            "provider_runs": [{"duration_ms": math.inf}],
            "llm_runs": [{"duration_ms": math.nan, "usage": {"total_tokens": math.inf}}],
            "pipeline_stage_runs": [{"duration_ms": -math.inf}],
            "agent_events": [{"event_type": "agent.end", "duration_ms": math.nan}],
        },
        raw_result={"sentiment_score": math.inf},
        include_markdown=True,
    )
    blob = result.to_json_text()
    assert "NaN" not in blob
    assert "Infinity" not in blob
    ReasoningTraceExportResponse.model_validate(result.package)
    json.dumps(result.package, allow_nan=False)


def test_supported_credential_and_path_corpus_has_zero_hits() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.signaturevalue1234567890"
    opaque = "opaqueTokenValueABCDEF1234567890abcdefghijklmnop"
    paths = [
        "/private/var/folders/secret/file.txt",
        "/workspace/project/.env",
        r"C:\\Users\\alice\\secret.env",
        r"\\server\share\secret.env",
        "~/private/secret.env",
        "../private/secret.env",
        "./private/secret.env",
    ]
    narrative = " ".join([jwt, opaque, *paths])
    result = build_reasoning_trace_package(
        run_id="redaction-run",
        diagnostics={
            "agent_events": [
                {
                    "event_type": "agent.decision",
                    "attrs": {"agent": "research", "summary": narrative},
                }
            ]
        },
        include_markdown=True,
    )
    blob = result.to_json_text() + result.markdown
    for secret in (jwt, opaque, *paths):
        assert secret not in blob


def test_event_and_source_caps_are_explicit() -> None:
    events = [
        {"event_type": "agent.phase", "sequence": index, "attrs": {"agent": "a"}}
        for index in range(201)
    ]
    result = build_reasoning_trace_package(
        run_id="cap-run",
        diagnostics={"agent_events": events},
        include_markdown=False,
    )
    assert result.package["truncated"] is True
    entry = next(
        item
        for item in result.package["coverage"]["sources"]
        if item["source"] == "diagnostics.agent_events"
    )
    assert entry["original_count"] == 201
    assert entry["returned_count"] == 200
    assert entry["dropped_count"] == 1
    assert entry["export_truncated"] is True
    assert any(
        drop["reason"] == "export_event_cap"
        for drop in result.package["truncation"]["dropped"]
    )


def test_source_retention_marker_is_preserved() -> None:
    result = build_reasoning_trace_package(
        run_id="capture-run",
        diagnostics={
            "agent_events": [{"event_type": "agent.phase", "attrs": {"agent": "a"}}],
            "agent_events_capture": {
                "original_count": 250,
                "returned_count": 200,
                "dropped_count": 50,
                "truncated": True,
            },
        },
        include_markdown=False,
    )
    entry = next(
        item
        for item in result.package["coverage"]["sources"]
        if item["source"] == "diagnostics.agent_events"
    )
    assert entry["source_truncated"] is True
    assert entry["original_count"] == 250
    # Capture-stage retention loss is preserved verbatim from the marker.
    assert entry["source_dropped_count"] == 50
    # ...and total loss is accounted against what the response actually carries:
    # only one event survived into the payload, so 249 of 250 are missing.
    assert entry["returned_count"] == 1
    assert entry["dropped_count"] == 249
    assert entry["original_count"] - entry["returned_count"] == entry["dropped_count"]
    assert entry["present"] is True


def test_record_query_and_trace_identities_are_distinct() -> None:
    def export(record_id: int):
        record = SimpleNamespace(
            id=record_id,
            query_id="shared-query",
            code="AAPL",
            name="Apple",
            model_used="test",
            created_at=None,
            context_snapshot={"diagnostics": {"trace_id": f"trace-{record_id}"}},
            raw_result={},
        )
        history = SimpleNamespace(
            _resolve_record=lambda value: record,
            _parse_diagnostic_json_field=lambda value, field: value,
        )
        return ReasoningTraceExportService(
            history_service=history,
            config=SimpleNamespace(reasoning_trace_export_enabled=True),
        ).export_for_record(str(record_id), include_markdown=False)

    first = export(1).package["run"]
    second = export(2).package["run"]
    assert first["record_id"] == "1"
    assert second["record_id"] == "2"
    assert first["query_id"] == second["query_id"] == "shared-query"
    assert first["trace_id"] != second["trace_id"]


def test_runtime_budget_is_defensively_clamped() -> None:
    assert resolve_max_export_chars(
        SimpleNamespace(reasoning_trace_export_max_chars=10**12)
    ) == MAX_MAX_EXPORT_CHARS


def test_markdown_keeps_untrusted_markup_in_code() -> None:
    dangerous = '<img src="https://tracker.invalid/pixel"> [click](https://evil.invalid)'
    result = build_reasoning_trace_package(
        run_id="markdown-run",
        diagnostics={
            "agent_events": [
                {
                    "event_type": "agent.decision",
                    "attrs": {"agent": "research", "summary": dangerous},
                }
            ]
        },
        output_format="markdown",
        include_markdown=True,
    )
    assert "\n    {" in result.markdown
    assert "<img" not in result.markdown
    assert "\\u003cimg" in result.markdown


def test_run_diagnostics_persists_capture_loss_counts() -> None:
    from src.services.run_diagnostics import RunDiagnosticContext

    context = RunDiagnosticContext(trace_id="capture-counter")
    for index in range(205):
        context.record_agent_event(
            {"event_type": "agent.phase", "sequence": index, "attrs": {"agent": "a"}}
        )
    snapshot = context.snapshot()
    assert len(snapshot["agent_events"]) == 200
    assert snapshot["agent_events_capture"] == {
        "original_count": 205,
        "returned_count": 200,
        "dropped_count": 5,
        "truncated": True,
    }


def test_many_agent_budget_drops_keep_truncation_ledger_typed() -> None:
    events = [
        {
            "event_type": "agent.decision",
            "sequence": index,
            "attrs": {"agent": f"agent-{index}", "summary": "x" * 500},
        }
        for index in range(200)
    ]
    result = build_reasoning_trace_package(
        run_id="many-agents",
        diagnostics={"agent_events": events},
        max_chars=10_000,
        include_markdown=True,
    )
    assert len(result.to_json_text()) <= 10_000
    ReasoningTraceExportResponse.model_validate(result.package)
    assert len(result.package["truncation"]["dropped"]) <= 128


# --- Merge-gate counterexample regressions (PR #975 four returned contracts) ---

PROD_QUERY_ID = "9f2c1ab84e7d4f0b8c3a5d6e7f801234"
PROD_TRACE_ID = "0123456789abcdef0123456789abcdef"


def _coverage(package: Dict[str, Any], source: str) -> Dict[str, Any]:
    return next(
        item for item in package["coverage"]["sources"] if item["source"] == source
    )


def test_production_uuid_identities_survive_opaque_token_redaction() -> None:
    """Blocker 1: 32-char UUID hex correlation ids must not become [REDACTED]."""
    result = build_reasoning_trace_package(
        run_id=PROD_TRACE_ID,
        record_id="77",
        query_id=PROD_QUERY_ID,
        lookup_key=PROD_QUERY_ID,
        lookup_mode="latest_by_query_id",
        diagnostics={"trace_id": PROD_TRACE_ID, "query_id": PROD_QUERY_ID},
        include_markdown=False,
    )
    run = result.package["run"]
    assert run["query_id"] == PROD_QUERY_ID
    assert run["trace_id"] == PROD_TRACE_ID
    assert run["run_id"] == PROD_TRACE_ID
    assert run["record_id"] == "77"
    assert run["lookup_key"] == PROD_QUERY_ID
    assert "[REDACTED]" not in json.dumps(run)
    ReasoningTraceExportResponse.model_validate(result.package)


@pytest.mark.parametrize(
    "secret",
    [FAKE_PATH, FAKE_URL, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlWFla"],
)
def test_identity_restoration_never_resurrects_credential_shapes(secret: str) -> None:
    """Blocker 1 guard: identity preservation must not become a redaction bypass."""
    result = build_reasoning_trace_package(
        run_id=secret,
        record_id="1",
        query_id=secret,
        lookup_key=secret,
        diagnostics={"trace_id": secret},
        include_markdown=False,
    )
    assert secret not in result.to_json_text()


def test_budget_drop_updates_coverage_atomically() -> None:
    """Blocker 2: a size-budget drop must not leave present/returned/dropped stale."""
    events = [
        {
            "event_type": "agent.step",
            "name": "n" * 300,
            "status": "ok",
            "attrs": {"agent": f"role{index % 3}"},
        }
        for index in range(150)
    ]
    provider_runs = [
        {"provider": "p" * 60, "data_type": "d" * 60, "operation": "o" * 60, "status": "ok"}
        for _ in range(100)
    ]
    result = build_reasoning_trace_package(
        run_id="budget-run",
        diagnostics={"agent_events": events, "provider_runs": provider_runs},
        max_chars=10_000,
        include_markdown=False,
    )
    package = result.package
    assert len(result.to_json_text()) <= 10_000
    assert package["data_sources"]["provider_trace"] == []
    entry = _coverage(package, "diagnostics.provider_runs")
    assert entry["present"] is False
    assert entry["absent"] is True
    assert entry["returned_count"] == 0
    assert entry["dropped_count"] == 100
    assert entry["export_truncated"] is True
    events_entry = _coverage(package, "diagnostics.agent_events")
    assert events_entry["present"] is False
    assert events_entry["returned_count"] == 0


def test_every_coverage_entry_matches_the_returned_payload() -> None:
    """Blocker 2: count and presence invariants hold for every source."""
    package = build_reasoning_trace_package(
        run_id="invariant-run",
        diagnostics=_source_payload()["diagnostics"],
        raw_result=_source_payload().get("raw_result") or {"dashboard": {}},
        include_markdown=False,
    ).package
    actual = {
        "diagnostics.provider_runs": len(package["data_sources"]["provider_trace"]),
        "diagnostics.llm_runs": len(package["data_sources"]["llm_runs"]),
        "diagnostics.pipeline_stage_runs": len(package["data_sources"]["pipeline_stage_runs"]),
        "diagnostics.agent_events": sum(
            len(agent["events"]) for agent in package["agents"]
        ),
    }
    for entry in package["coverage"]["sources"]:
        assert entry["absent"] is not entry["present"]
        if entry["source"] in actual:
            assert entry["returned_count"] == actual[entry["source"]]
            assert entry["present"] is bool(actual[entry["source"]])


def test_value_clipping_is_recorded_in_the_loss_ledger() -> None:
    """Blocker 2: _clip_text must never shrink content silently."""
    result = build_reasoning_trace_package(
        run_id="clip-run",
        raw_result={"dashboard": {"core_conclusion": {"analysis_summary": "z" * 50_000}}},
        include_markdown=False,
    )
    package = result.package
    assert package["truncated"] is True
    assert any(
        drop["path"] == "dashboard.synthesis" and drop["reason"] == "value_clipped"
        for drop in package["truncation"]["dropped"]
    )


def test_empty_source_does_not_claim_synthesis_coverage() -> None:
    """Blocker 3: an empty raw_result must report absent, not a null container."""
    package = build_reasoning_trace_package(
        run_id="empty-run", raw_result={}, diagnostics={}, include_markdown=False
    ).package
    entry = _coverage(package, "dashboard.synthesis")
    assert entry["present"] is False
    assert entry["absent"] is True
    assert package["synthesis"] == {
        "disagreement": {},
        "consensus": {},
        "final_conclusion": {},
    }


def test_malformed_only_events_report_absent_with_loss() -> None:
    """Blocker 3: malformed-only sources must not claim presence."""
    package = build_reasoning_trace_package(
        run_id="malformed-run",
        diagnostics={"agent_events": ["not-a-mapping", 42, None]},
        include_markdown=False,
    ).package
    entry = _coverage(package, "diagnostics.agent_events")
    assert entry["present"] is False
    assert entry["returned_count"] == 0
    assert entry["export_truncated"] is True
    assert "malformed_source_entries" in entry["reasons"]


def test_legacy_record_at_capture_cap_reports_unknown_loss() -> None:
    """Blocker 3: a marker-less record at the historic cap cannot prove no loss."""
    events = [{"event_type": "agent.phase", "attrs": {"agent": "a"}} for _ in range(200)]
    package = build_reasoning_trace_package(
        run_id="legacy-run", diagnostics={"agent_events": events}, include_markdown=False
    ).package
    entry = _coverage(package, "diagnostics.agent_events")
    assert entry["source_truncated_unknown"] is True
    assert entry["original_count"] is None
    assert entry["dropped_count"] is None
    assert "legacy_capture_loss_unknown" in entry["reasons"]
    ReasoningTraceExportResponse.model_validate(package)


def test_current_marker_reports_exact_capture_loss() -> None:
    """Blocker 3: the current runtime marker keeps exact, provable accounting."""
    events = [{"event_type": "agent.phase", "attrs": {"agent": "a"}} for _ in range(200)]
    package = build_reasoning_trace_package(
        run_id="current-run",
        diagnostics={
            "agent_events": events,
            "agent_events_capture": {
                "original_count": 201,
                "returned_count": 200,
                "dropped_count": 1,
                "truncated": True,
            },
        },
        include_markdown=False,
    ).package
    entry = _coverage(package, "diagnostics.agent_events")
    assert entry["source_truncated_unknown"] is False
    assert entry["source_truncated"] is True
    assert entry["original_count"] == 201
    assert entry["source_dropped_count"] == 1


def _export_with_resolver(requested: str, record: SimpleNamespace):
    history = SimpleNamespace(
        _resolve_record=lambda value: record,
        _parse_diagnostic_json_field=lambda value, field: value,
    )
    return ReasoningTraceExportService(
        history_service=history,
        config=SimpleNamespace(reasoning_trace_export_enabled=True),
    ).export_for_record(requested, include_markdown=False)


def test_numeric_query_fallback_reports_actual_resolution_mode() -> None:
    """Blocker 4: numeric key resolved via query fallback is not a primary_key hit."""
    record = SimpleNamespace(
        id=77,
        query_id="123",
        code="600519",
        name="N",
        model_used="m",
        created_at=None,
        context_snapshot={"diagnostics": {}},
        raw_result={},
    )
    run = _export_with_resolver("123", record).package["run"]
    assert run["lookup_key"] == "123"
    assert run["record_id"] == "77"
    assert run["lookup_mode"] == "latest_by_query_id"


def test_numeric_primary_key_hit_still_reports_primary_key() -> None:
    """Blocker 4: numeric PK/query collision must attribute to the primary key."""
    record = SimpleNamespace(
        id=123,
        query_id="123",
        code="600519",
        name="N",
        model_used="m",
        created_at=None,
        context_snapshot={"diagnostics": {}},
        raw_result={},
    )
    run = _export_with_resolver("123", record).package["run"]
    assert run["record_id"] == "123"
    assert run["lookup_mode"] == "primary_key"


def test_non_numeric_lookup_reports_query_mode() -> None:
    """Blocker 4: string query ids keep the latest-by-query attribution."""
    record = SimpleNamespace(
        id=9,
        query_id=PROD_QUERY_ID,
        code="600519",
        name="N",
        model_used="m",
        created_at=None,
        context_snapshot={"diagnostics": {}},
        raw_result={},
    )
    run = _export_with_resolver(PROD_QUERY_ID, record).package["run"]
    assert run["record_id"] == "9"
    assert run["query_id"] == PROD_QUERY_ID
    assert run["lookup_mode"] == "latest_by_query_id"
