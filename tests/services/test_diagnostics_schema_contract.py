# -*- coding: utf-8 -*-
"""Frozen run-diagnostics schema contract for issue #1076 first slice."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from src.services.diagnostics.schema import (
    DIAGNOSTIC_COMPONENT_STATUSES,
    DIAGNOSTIC_SNAPSHOT_KEYS,
    DIAGNOSTIC_SNAPSHOT_OPTIONAL_KEYS,
    DIAGNOSTIC_SUMMARY_COMPONENT_KEYS,
    DIAGNOSTIC_SUMMARY_KEYS,
    DIAGNOSTIC_SUMMARY_STATUSES,
    PIPELINE_STAGE_STATUSES,
    PROVIDER_RUN_OPTIONAL_KEYS,
    PROVIDER_RUN_REQUIRED_KEYS,
    DataQualityEvidenceRecord,
    HistoryRun,
    LLMRun,
    NotificationRun,
    PipelineStageRun,
    ProviderRun,
    RunDiagnosticComponent,
    RunDiagnosticSummary,
    sanitize_diagnostic_metadata,
    sanitize_diagnostic_text,
    sanitize_finite_diagnostic_metadata,
)
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    build_run_diagnostic_summary,
    current_diagnostic_snapshot,
    observe_pipeline_stage,
    record_history_run,
    record_llm_run,
    record_notification_run,
    record_provider_run,
    reset_run_diagnostic_context,
)

_CREATED_AT = "2026-08-20T00:00:00"


def test_schema_module_does_not_import_collect() -> None:
    source = Path("src/services/diagnostics/schema.py").read_text(encoding="utf-8")
    assert "diagnostics.collect" not in source
    assert "from src.services.diagnostics.collect" not in source


def test_empty_snapshot_keys_and_list_shapes() -> None:
    token = activate_run_diagnostic_context(trace_id="trace-empty")
    try:
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    assert set(snapshot) == set(DIAGNOSTIC_SNAPSHOT_KEYS)
    assert set(snapshot).isdisjoint(DIAGNOSTIC_SNAPSHOT_OPTIONAL_KEYS)
    assert snapshot["trace_id"] == "trace-empty"
    for key in (
        "provider_runs",
        "data_quality_evidence",
        "llm_runs",
        "notification_runs",
        "history_runs",
        "pipeline_stage_runs",
        "agent_events",
    ):
        assert snapshot[key] == []
    assert snapshot["agent_events_capture"] == {
        "original_count": 0,
        "returned_count": 0,
        "dropped_count": 0,
        "truncated": False,
    }


def test_success_provider_run_omits_none_and_pins_required_keys() -> None:
    payload = ProviderRun(
        trace_id="trace-success",
        data_type="daily_data",
        provider="UnitFetcher",
        operation="get_daily_data",
        success=True,
        record_count=2,
        created_at=_CREATED_AT,
    ).to_dict()

    assert payload == {
        "trace_id": "trace-success",
        "data_type": "daily_data",
        "provider": "UnitFetcher",
        "operation": "get_daily_data",
        "success": True,
        "record_count": 2,
        "created_at": _CREATED_AT,
    }
    assert set(PROVIDER_RUN_REQUIRED_KEYS).issubset(payload)
    assert "error_message_sanitized" not in payload
    for key in PROVIDER_RUN_OPTIONAL_KEYS:
        if key != "record_count":
            assert key not in payload


def test_degraded_run_payloads_include_error_fields() -> None:
    provider = ProviderRun(
        trace_id="trace-degraded",
        data_type="realtime_quote",
        provider="FirstQuote",
        operation="get_realtime_quote",
        success=False,
        error_type="TimeoutError",
        error_message_sanitized="token=<redacted>",
        fallback_to="SecondQuote",
        created_at=_CREATED_AT,
    ).to_dict()
    assert provider == {
        "trace_id": "trace-degraded",
        "data_type": "realtime_quote",
        "provider": "FirstQuote",
        "operation": "get_realtime_quote",
        "success": False,
        "error_type": "TimeoutError",
        "error_message_sanitized": "token=<redacted>",
        "fallback_to": "SecondQuote",
        "created_at": _CREATED_AT,
    }

    llm = LLMRun(
        trace_id="trace-degraded",
        provider="deepseek",
        model="deepseek-chat",
        success=False,
        error_type="RateLimitError",
        error_message_sanitized="quota exceeded",
        created_at=_CREATED_AT,
    ).to_dict()
    assert llm["success"] is False
    assert llm["error_type"] == "RateLimitError"
    assert "tokens" not in llm

    stage = PipelineStageRun(
        trace_id="trace-degraded",
        stage="fetch",
        status="degraded",
        input_summary={"stock_code": "600519"},
        duration_ms=12,
        degraded=True,
        retryable=True,
        started_at=_CREATED_AT,
        ended_at=_CREATED_AT,
        degradation_reason="provider timeout",
        error_type="TimeoutError",
        error_message_sanitized="token=<redacted>",
    ).to_dict()
    assert stage["status"] == "degraded"
    assert stage["degraded"] is True
    assert stage["status"] in PIPELINE_STAGE_STATUSES
    assert stage["error_message_sanitized"] == "token=<redacted>"


def test_empty_and_degraded_summary_shapes() -> None:
    empty = build_run_diagnostic_summary()
    assert empty["status"] == "unknown"
    assert empty["status"] in DIAGNOSTIC_SUMMARY_STATUSES
    assert set(empty) <= set(DIAGNOSTIC_SUMMARY_KEYS)
    assert "copy_text" in empty
    assert set(empty["components"]) == set(DIAGNOSTIC_SUMMARY_COMPONENT_KEYS)
    for component in empty["components"].values():
        assert component["status"] in DIAGNOSTIC_COMPONENT_STATUSES

    token = activate_run_diagnostic_context(trace_id="trace-summary-degraded")
    try:
        record_provider_run(
            data_type="realtime_quote",
            provider="FirstQuote",
            operation="get_realtime_quote",
            success=False,
            error_type="TimeoutError",
            error_message="token=secret-token",
            fallback_to="SecondQuote",
        )
        record_provider_run(
            data_type="realtime_quote",
            provider="SecondQuote",
            operation="get_realtime_quote",
            success=True,
        )
        record_llm_run(success=True, model="deepseek-chat")
        record_notification_run(channel="wechat", status="success", success=True)
        record_history_run(report_saved=True, analysis_history_id=9)
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    summary = build_run_diagnostic_summary(
        context_snapshot={"diagnostics": snapshot},
        raw_result={"success": True, "model_used": "deepseek-chat"},
        report_saved=True,
    )
    assert summary["status"] == "degraded"
    assert summary["status"] in DIAGNOSTIC_SUMMARY_STATUSES
    assert set(summary["components"]) == set(DIAGNOSTIC_SUMMARY_COMPONENT_KEYS)
    assert summary["components"]["realtime_quote"]["status"] == "degraded"
    assert summary["components"]["llm"]["status"] == "ok"
    assert "copy_text" in summary
    assert "secret-token" not in json.dumps(summary, ensure_ascii=False)


def test_record_types_omit_none_consistently() -> None:
    history = HistoryRun(
        trace_id="trace-none",
        report_saved=True,
        created_at=_CREATED_AT,
    ).to_dict()
    assert history == {
        "trace_id": "trace-none",
        "report_saved": True,
        "created_at": _CREATED_AT,
    }

    notification = NotificationRun(
        trace_id="trace-none",
        channel="wechat",
        status="success",
        success=True,
        created_at=_CREATED_AT,
    ).to_dict()
    assert "error_message_sanitized" not in notification

    component = RunDiagnosticComponent(
        key="llm",
        label="LLM",
        status="ok",
        message="ok",
        details={},
    ).to_dict()
    assert component == {
        "key": "llm",
        "label": "LLM",
        "status": "ok",
        "message": "ok",
    }

    evidence = DataQualityEvidenceRecord(
        schema_version="dq_v1",
        data_type="daily_data",
        severity="ok",
        symbol=None,
        provider=None,
        market="CN",
        instrument_type="stock",
        rejected=False,
        issues=[],
        issue_count=0,
        truncated=False,
        created_at=_CREATED_AT,
    ).to_dict()
    assert evidence["symbol"] is None
    assert evidence["provider"] is None
    assert "provenance" not in evidence


def test_schema_normalization_does_not_mutate_caller_payloads() -> None:
    original = {
        "stock_code": "600519",
        "notes": ["keep", "me"],
        "window": {"days": 30},
        "api_key": "secret-key",
        "scores": [1.0, 2.0],
    }
    notes_ref = original["notes"]
    window_ref = original["window"]
    scores_ref = original["scores"]
    frozen = copy.deepcopy(original)

    sanitized = sanitize_diagnostic_metadata(original)
    finite_value, finite = sanitize_finite_diagnostic_metadata(original)
    redacted = sanitize_diagnostic_text("Authorization: Bearer secret-token")

    assert original == frozen
    assert original["notes"] is notes_ref
    assert original["window"] is window_ref
    assert original["scores"] is scores_ref
    assert notes_ref == ["keep", "me"]
    assert sanitized is not original
    assert finite_value is not original
    assert finite is True
    assert sanitized.get("api_key") == "<redacted>"
    assert original["api_key"] == "secret-key"
    assert "secret-token" not in (redacted or "")
    notes_ref.append("mutated-after")
    assert original["notes"][-1] == "mutated-after"
    assert sanitized.get("notes") != original["notes"]


def test_to_dict_does_not_alias_or_mutate_dataclass_fields() -> None:
    issues = [{"code": "gap", "message": "missing bar"}]
    provenance = {"source": "validator"}
    evidence = DataQualityEvidenceRecord(
        schema_version="dq_v1",
        data_type="daily_data",
        severity="warn",
        symbol="600519",
        provider="UnitFetcher",
        market="CN",
        instrument_type="stock",
        rejected=False,
        issues=issues,
        issue_count=1,
        truncated=False,
        provenance=provenance,
        created_at=_CREATED_AT,
    )
    payload = evidence.to_dict()
    payload["issues"].append({"code": "mutated"})
    payload["provenance"]["source"] = "mutated"
    payload["symbol"] = "000001"
    assert evidence.issues == [{"code": "gap", "message": "missing bar"}]
    assert evidence.provenance == {"source": "validator"}
    assert evidence.symbol == "600519"

    summary = RunDiagnosticSummary(
        status="normal",
        status_label="正常",
        reason="ok",
        trace_id="trace-alias",
        components={
            "llm": RunDiagnosticComponent(
                key="llm",
                label="LLM",
                status="ok",
                message="ok",
                details={"model": "deepseek-chat"},
            )
        },
    )
    encoded = summary.to_dict()
    encoded["reason"] = "mutated"
    encoded["components"]["llm"]["details"]["model"] = "mutated"
    assert summary.reason == "ok"
    assert summary.components["llm"].details == {"model": "deepseek-chat"}

    stage = PipelineStageRun(
        trace_id="trace-alias",
        stage="fetch",
        status="success",
        input_summary={"stock_code": "600519", "window": {"days": 30}},
        duration_ms=4,
        degraded=False,
        retryable=False,
        started_at=_CREATED_AT,
        ended_at=_CREATED_AT,
        output_summary={"record_count": 1},
    )
    stage_payload = stage.to_dict()
    stage_payload["input_summary"]["stock_code"] = "000001"
    stage_payload["output_summary"]["record_count"] = 99
    assert stage.input_summary == {"stock_code": "600519", "window": {"days": 30}}
    assert stage.output_summary == {"record_count": 1}


def test_diagnostics_calls_do_not_mutate_business_inputs_or_outcomes() -> None:
    input_summary = {"stock_code": "600519", "window": {"days": 30}, "notes": ["keep"]}
    output_summary = {"record_count": 1, "flags": ["ok"]}
    analysis_outcome = {
        "success": True,
        "model_used": "deepseek-chat",
        "analysis_summary": "keep-me",
        "scores": [0.2, 0.8],
    }
    window_ref = input_summary["window"]
    notes_ref = input_summary["notes"]
    flags_ref = output_summary["flags"]
    scores_ref = analysis_outcome["scores"]
    frozen_input = copy.deepcopy(input_summary)
    frozen_output = copy.deepcopy(output_summary)
    frozen_outcome = copy.deepcopy(analysis_outcome)

    token = activate_run_diagnostic_context(trace_id="trace-non-mutation")
    try:
        stage = observe_pipeline_stage("fetch", input_summary=input_summary)
        record_provider_run(
            data_type="daily_data",
            provider="UnitFetcher",
            operation="get_daily_data",
            success=True,
            record_count=1,
        )
        record_llm_run(success=True, model="deepseek-chat")
        stage.finish(status="success", output_summary=output_summary)
        snapshot = current_diagnostic_snapshot()
        summary = build_run_diagnostic_summary(
            context_snapshot={"diagnostics": snapshot},
            raw_result=analysis_outcome,
            report_saved=True,
        )
        snapshot["provider_runs"].append({"mutated": True})
        snapshot["agent_events"].append({"mutated": True})
        rerecorded = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert input_summary == frozen_input
    assert output_summary == frozen_output
    assert analysis_outcome == frozen_outcome
    assert input_summary["window"] is window_ref
    assert input_summary["notes"] is notes_ref
    assert output_summary["flags"] is flags_ref
    assert analysis_outcome["scores"] is scores_ref
    assert summary["status"] == "normal"
    assert rerecorded is not None
    assert {"mutated": True} not in rerecorded["provider_runs"]
    assert {"mutated": True} not in rerecorded["agent_events"]
