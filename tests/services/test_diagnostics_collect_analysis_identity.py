# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Prove diagnostics collect helpers do not change analysis outcomes (#1076).

Collection may write only to the diagnostic snapshot side channel. Nested
caller-owned summaries, a held ``AnalysisResult`` / ``raw_result``, and the
original analysis object after an internal collect-helper failure must stay
unchanged. Tests call the real ``src.services.run_diagnostics`` facade helpers
and do not replace ``observe_pipeline_stage``, ``record_provider_run``, or
``record_llm_run``.
"""

from __future__ import annotations

import copy
from typing import Any, Dict

import pandas as pd
import pytest

from src.analyzer import AnalysisResult
from src.data_provider.base import BaseFetcher, DataFetcherManager
from src.services.diagnostics import collect as diagnostics_collect
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    attach_prompt_artifact_versions,
    current_diagnostic_snapshot,
    get_current_diagnostic_context,
    observe_pipeline_stage,
    record_data_quality_evidence,
    record_llm_run,
    record_llm_run_started,
    record_provider_run,
    reset_run_diagnostic_context,
)


def test_facade_collect_helpers_are_the_real_implementations() -> None:
    """Lock the public facade to the real collect helpers, not test doubles."""
    assert observe_pipeline_stage is diagnostics_collect.observe_pipeline_stage
    assert record_data_quality_evidence is (
        diagnostics_collect.record_data_quality_evidence
    )
    assert attach_prompt_artifact_versions is (
        diagnostics_collect.attach_prompt_artifact_versions
    )


def _nested_window() -> Dict[str, Any]:
    return {"days": 30, "notes": ["keep-me"]}


def _nested_issues() -> list[dict[str, Any]]:
    return [{"code": "stale_bar", "detail": {"age": 2}}]


def _prompt_trace() -> Dict[str, Any]:
    return {
        "schema_version": "1",
        "skills": [
            {
                "kind": "skill",
                "artifact_id": "skill-a",
                "version": "1.0",
                "content_hash": "abc123hash",
                "lifecycle": "active",
            }
        ],
        "prompts": [],
        "active_skill_ids": ["skill-a"],
        "skill_versions": {"skill-a": "1.0"},
        "prompt_version": "p1",
    }


def _make_analysis_result() -> AnalysisResult:
    """Build one analysis object whose nested dicts are shared with raw_result."""
    window = _nested_window()
    issues = _nested_issues()
    trace = _prompt_trace()
    dashboard = {
        "window": window,
        "issues": issues,
        "core_conclusion": {"one_sentence": "hold the name brand"},
        "prompt_trace": trace,
    }
    return AnalysisResult(
        code="600519",
        name="Kweichow Moutai",
        sentiment_score=62,
        trend_prediction="sideways",
        operation_advice="hold",
        decision_type="hold",
        analysis_summary="keep-me",
        model_used="stub-llm",
        dashboard=dashboard,
        market_snapshot={"price": 1680.5, "window": window},
        success=True,
    )


def _business_fields(result: AnalysisResult) -> Dict[str, Any]:
    """JSON-equal business payload, excluding the diagnostics side channel."""
    payload = copy.deepcopy(result.to_dict())
    payload.pop("diagnostic_context_snapshot", None)
    return payload


def _summaries_from_result(result: AnalysisResult) -> Dict[str, Any]:
    """Caller-owned summaries that alias nested AnalysisResult / raw_result state."""
    dashboard = result.dashboard or {}
    return {
        "input": {
            "stock_code": result.code,
            "window": dashboard["window"],
            "dashboard": dashboard,
        },
        "output": {
            "analysis_success": bool(result.success),
            "model": result.model_used,
            "issues": dashboard["issues"],
        },
        "trace": dashboard["prompt_trace"],
        "issues": dashboard["issues"],
    }


def _collect_against_held_result(result: AnalysisResult) -> AnalysisResult:
    """Run the real collect helpers against one held analysis object."""
    summaries = _summaries_from_result(result)
    stage = observe_pipeline_stage(
        "analyze",
        input_summary=summaries["input"],
        retryable=False,
    )
    record_provider_run(
        data_type="daily_data",
        provider="UnitFetcher",
        operation="get_daily_data",
        success=True,
        record_count=1,
    )
    record_llm_run_started(model=result.model_used, call_type="analysis")
    record_llm_run(
        success=bool(result.success),
        model=result.model_used,
        call_type="analysis",
        duration_ms=12,
    )
    stage.finish(status="success", output_summary=summaries["output"])
    attach_prompt_artifact_versions(summaries["trace"])
    record_data_quality_evidence(
        data_type="daily_data",
        severity="warn",
        symbol=result.code,
        provider="UnitFetcher",
        market="cn",
        instrument_type="equity",
        rejected=False,
        issues=summaries["issues"],
    )
    return result


def test_nested_caller_owned_summaries_cannot_mutate_recorded_or_analysis() -> None:
    """Nested caller summaries must not alias the recorded copy or raw_result."""
    result = _make_analysis_result()
    raw_result = result.to_dict()
    dashboard_ref = result.dashboard
    window_ref = result.dashboard["window"]
    issues_ref = result.dashboard["issues"]
    trace_ref = result.dashboard["prompt_trace"]
    frozen_business = _business_fields(result)
    frozen_window = copy.deepcopy(window_ref)
    frozen_issues = copy.deepcopy(issues_ref)
    frozen_skill_id = trace_ref["skills"][0]["artifact_id"]

    assert raw_result["dashboard"] is dashboard_ref
    assert raw_result["dashboard"]["window"] is window_ref
    assert raw_result["market_snapshot"]["window"] is window_ref

    token = activate_run_diagnostic_context(trace_id="trace-nested-identity")
    try:
        returned = _collect_against_held_result(result)
        context = get_current_diagnostic_context()
        assert context is not None
        recorded_input = context.pipeline_stage_runs[0].input_summary
        recorded_output = context.pipeline_stage_runs[0].output_summary
        recorded_evidence = context.data_quality_evidence[0].issues
        recorded_versions = copy.deepcopy(context.prompt_artifact_versions or {})
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert returned is result
    assert _business_fields(result) == frozen_business
    assert recorded_input["window"] is not window_ref
    assert recorded_input["dashboard"] is not dashboard_ref
    assert recorded_output["issues"] is not issues_ref
    assert recorded_evidence is not issues_ref
    assert recorded_evidence[0] is not issues_ref[0]

    window_ref["days"] = 1
    window_ref["notes"].append("caller-mutated")
    issues_ref[0]["code"] = "caller-mutated"
    issues_ref[0]["detail"]["age"] = 99
    trace_ref["skills"][0]["artifact_id"] = "caller-mutated"
    result.analysis_summary = "caller-mutated-summary"

    assert recorded_input["window"]["days"] == frozen_window["days"]
    assert recorded_input["window"]["notes"] == frozen_window["notes"]
    assert recorded_output["issues"][0]["code"] == frozen_issues[0]["code"]
    assert recorded_evidence[0]["code"] == frozen_issues[0]["code"]
    assert recorded_versions["skills"][0]["artifact_id"] == frozen_skill_id

    recorded_input["window"]["days"] = 999
    recorded_input["dashboard"]["core_conclusion"]["one_sentence"] = "mutated-copy"
    recorded_output["issues"][0]["code"] = "recorded-mutated"
    recorded_evidence[0]["code"] = "recorded-mutated"

    assert window_ref["days"] == 1
    assert result.dashboard["window"]["days"] == 1
    assert raw_result["dashboard"]["window"]["days"] == 1
    assert raw_result["market_snapshot"]["window"]["days"] == 1
    assert result.dashboard["core_conclusion"]["one_sentence"] == "hold the name brand"
    assert raw_result["dashboard"]["core_conclusion"]["one_sentence"] == (
        "hold the name brand"
    )
    assert issues_ref[0]["code"] == "caller-mutated"
    assert raw_result["dashboard"]["issues"][0]["code"] == "caller-mutated"
    assert snapshot is not None
    assert snapshot["pipeline_stage_runs"]
    assert result.dashboard is dashboard_ref


def test_diagnostics_active_vs_inactive_leaves_business_fields_equal() -> None:
    """Active vs inactive collect must leave analysis business fields identical."""
    inactive_result = _make_analysis_result()
    active_result = _make_analysis_result()
    frozen = _business_fields(inactive_result)

    inactive_returned = _collect_against_held_result(inactive_result)
    inactive_snapshot = current_diagnostic_snapshot()

    token = activate_run_diagnostic_context(trace_id="trace-active-identity")
    try:
        active_returned = _collect_against_held_result(active_result)
        active_snapshot = current_diagnostic_snapshot()
        context = get_current_diagnostic_context()
    finally:
        reset_run_diagnostic_context(token)

    assert inactive_returned is inactive_result
    assert active_returned is active_result
    assert inactive_snapshot is None
    assert active_snapshot is not None
    assert context is not None
    assert context.pipeline_stage_runs
    assert context.provider_runs
    assert context.llm_runs
    assert _business_fields(inactive_result) == frozen
    assert _business_fields(active_result) == frozen
    assert _business_fields(active_result) == _business_fields(inactive_result)
    assert not hasattr(active_result, "diagnostic_context_snapshot")
    assert not hasattr(inactive_result, "diagnostic_context_snapshot")


class _SuccessfulDailyFetcher(BaseFetcher):
    name = "IdentityDailyFetcher"
    priority = 1

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        raise NotImplementedError

    def get_daily_data(self, stock_code, start_date=None, end_date=None, days=30):
        _ = (stock_code, start_date, end_date, days)
        return pd.DataFrame(
            [
                {
                    "date": "2026-05-22",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "volume": 100,
                    "amount": 200,
                    "pct_chg": 1,
                }
            ]
        )


class _StubAnalyzer:
    """LLM stand-in. Diagnostics still go through the real record_llm_run helper."""

    def __init__(self, result: AnalysisResult) -> None:
        self._result = result

    def analyze(self, *args: Any, **kwargs: Any) -> AnalysisResult:
        _ = (args, kwargs)
        return self._result


def test_provider_and_llm_stubs_leave_analysis_equal_with_real_collect() -> None:
    """Stub providers/LLM, keep real collect helpers, and compare business fields."""
    inactive_result = _make_analysis_result()
    active_result = _make_analysis_result()
    frozen = _business_fields(inactive_result)

    inactive_manager = DataFetcherManager(fetchers=[_SuccessfulDailyFetcher()])
    inactive_df, inactive_source = inactive_manager.get_daily_data("600519")
    inactive_llm = _StubAnalyzer(inactive_result).analyze()
    record_llm_run_started(model=inactive_llm.model_used, call_type="analysis")
    record_llm_run(
        success=bool(inactive_llm.success),
        model=inactive_llm.model_used,
        call_type="analysis",
        duration_ms=8,
    )

    token = activate_run_diagnostic_context(
        trace_id="trace-provider-llm-identity",
        stock_code="600519",
    )
    try:
        active_manager = DataFetcherManager(fetchers=[_SuccessfulDailyFetcher()])
        stage = observe_pipeline_stage(
            "fetch",
            input_summary={"stock_code": active_result.code},
        )
        active_df, active_source = active_manager.get_daily_data("600519")
        stage.finish(
            status="success",
            output_summary={"record_count": int(len(active_df))},
        )
        active_llm = _StubAnalyzer(active_result).analyze()
        record_llm_run_started(model=active_llm.model_used, call_type="analysis")
        record_llm_run(
            success=bool(active_llm.success),
            model=active_llm.model_used,
            call_type="analysis",
            duration_ms=8,
        )
        snapshot = current_diagnostic_snapshot()
        context = get_current_diagnostic_context()
    finally:
        reset_run_diagnostic_context(token)

    assert inactive_llm is inactive_result
    assert active_llm is active_result
    assert inactive_source == active_source == "IdentityDailyFetcher"
    assert list(inactive_df.columns) == list(active_df.columns)
    assert inactive_df.equals(active_df)
    assert _business_fields(inactive_result) == frozen
    assert _business_fields(active_result) == frozen
    assert snapshot is not None
    assert context is not None
    assert [run.provider for run in context.provider_runs] == ["IdentityDailyFetcher"]
    assert context.llm_runs
    assert context.pipeline_stage_runs[0].stage == "fetch"


class _UnprintableValue:
    """Force collect sanitization to fail without touching analysis fields."""

    def __str__(self) -> str:
        """Raise so the collect helper must fail open."""
        raise RuntimeError("cannot stringify diagnostic value")


def test_collect_helper_failure_returns_original_analysis_object(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Internal collect failures must fail open and keep the same analysis object."""
    result = _make_analysis_result()
    original = result
    frozen = _business_fields(result)
    dashboard_ref = result.dashboard
    raw_result = result.to_dict()

    token = activate_run_diagnostic_context(trace_id="trace-collect-fail-open")
    try:
        context = get_current_diagnostic_context()
        assert context is not None

        def _fail_provider(provider_run: Any) -> None:
            _ = provider_run
            raise RuntimeError("provider diagnostic sink unavailable")

        def _fail_llm(llm_run: Any) -> None:
            _ = llm_run
            raise RuntimeError("llm diagnostic sink unavailable")

        monkeypatch.setattr(context, "record_provider_run", _fail_provider)
        monkeypatch.setattr(context, "record_llm_run", _fail_llm)

        returned_after_unprintable = observe_pipeline_stage(
            "analyze",
            input_summary={"unexpected": _UnprintableValue(), "stock_code": result.code},
        )
        returned_after_unprintable.finish(
            status="success",
            output_summary={"analysis_success": True},
        )
        record_provider_run(
            data_type="daily_data",
            provider="UnitFetcher",
            operation="get_daily_data",
            success=True,
            record_count=1,
        )
        record_llm_run(
            success=True,
            model=result.model_used,
            call_type="analysis",
        )
        returned = result
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert returned is original
    assert returned is result
    assert result.dashboard is dashboard_ref
    assert raw_result["dashboard"] is dashboard_ref
    assert _business_fields(result) == frozen
    assert result.analysis_summary == "keep-me"
    assert snapshot is not None
    assert "Pipeline stage input summary sanitization failed" in caplog.text
    assert "Provider diagnostic record failed" in caplog.text
    assert "LLM diagnostic record failed" in caplog.text
