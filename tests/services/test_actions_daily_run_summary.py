# -*- coding: utf-8 -*-
"""Tests for Actions daily-run plain-language summary (#850)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.services.actions_daily_run_summary import (
    DailyRunSummary,
    append_github_step_summary,
    build_and_emit_summary,
    build_status_for_failure,
    build_status_for_non_trading_day,
    build_status_from_counts,
    failure_notify_enabled,
    format_step_summary_markdown,
    load_run_status,
    maybe_send_failure_notification,
    resolve_summary,
    sanitize_summary_text,
    write_run_status,
)
from src.services.actions_outcome_codes import (
    CODE_MISSING_LLM,
    CODE_NON_TRADING_DAY,
    CODE_PARTIAL,
    CODE_SUCCESS,
    CODE_TIMEOUT,
    CODE_UNKNOWN,
    OUTCOME_FAILED,
    OUTCOME_PARTIAL,
    OUTCOME_SKIPPED,
    OUTCOME_SUCCESS,
    has_any_llm_secret,
)


class _FakeSender:
    def __init__(self, *, succeed: bool = True, raise_exc: bool = False) -> None:
        self.succeed = succeed
        self.raise_exc = raise_exc
        self.calls: List[Dict[str, Any]] = []

    def send(self, content: str, **kwargs: Any) -> bool:
        if self.raise_exc:
            raise RuntimeError("boom")
        self.calls.append({"content": content, **kwargs})
        return self.succeed


def test_all_green_summary_from_status() -> None:
    status = build_status_from_counts(
        ok_count=3,
        failed_count=0,
        attempted_codes=["600519", "hk00700", "AAPL"],
        successful_codes=["600519", "hk00700", "AAPL"],
    )
    summary = resolve_summary(status=status, exit_code=0, job_status="success")
    assert summary.outcome == OUTCOME_SUCCESS
    assert summary.primary_code == CODE_SUCCESS
    assert summary.ok_count == 3
    assert summary.notify is False
    md = format_step_summary_markdown(summary)
    assert "运行成功" in md
    assert "Run succeeded" in md


def test_partial_summary_from_status() -> None:
    status = build_status_from_counts(
        ok_count=1,
        failed_count=2,
        attempted_codes=["600519", "000001", "AAPL"],
        successful_codes=["600519"],
    )
    summary = resolve_summary(status=status, exit_code=0)
    assert summary.outcome == OUTCOME_PARTIAL
    assert summary.primary_code == CODE_PARTIAL
    assert summary.notify is False


def test_all_failed_summary_from_status() -> None:
    status = build_status_from_counts(
        ok_count=0,
        failed_count=2,
        attempted_codes=["600519", "000001"],
        successful_codes=[],
        no_llm=True,
    )
    summary = resolve_summary(status=status, exit_code=0)
    assert summary.outcome == OUTCOME_FAILED
    assert summary.primary_code == CODE_MISSING_LLM
    assert summary.notify is True
    md = format_step_summary_markdown(summary)
    assert "missing_llm" in md


def test_non_trading_day_status() -> None:
    status = build_status_for_non_trading_day(stock_codes=["600519"], force_run=False)
    summary = resolve_summary(status=status, exit_code=0, job_status="success")
    assert summary.outcome == OUTCOME_SKIPPED
    assert summary.primary_code == CODE_NON_TRADING_DAY
    assert summary.notify is False
    assert "force_run" in format_step_summary_markdown(summary)


def test_write_and_load_run_status_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "run_status.json"
    doc = build_status_from_counts(
        ok_count=1, failed_count=0, attempted_codes=["AAPL"], successful_codes=["AAPL"]
    )
    assert write_run_status(doc, path) == path
    loaded = load_run_status(path)
    assert loaded is not None
    assert loaded.outcome == OUTCOME_SUCCESS
    assert loaded.stocks[0].code == "AAPL"


def test_failure_notify_degrades_when_disabled() -> None:
    summary = DailyRunSummary(
        outcome=OUTCOME_FAILED,
        primary_code=CODE_UNKNOWN,
        ok_count=0,
        failed_count=1,
        skipped_count=0,
        headline_zh="失败",
        headline_en="failed",
        action_zh="看日志",
        action_en="see logs",
        notify=True,
        source="test",
    )
    sender = _FakeSender()
    result = maybe_send_failure_notification(
        summary, environ={"FAILURE_NOTIFY_ENABLED": "false"}, sender=sender
    )
    assert result["attempted"] is False
    assert sender.calls == []


def test_failure_notify_degrades_when_no_system_error_channels() -> None:
    summary = DailyRunSummary(
        outcome=OUTCOME_FAILED,
        primary_code=CODE_UNKNOWN,
        ok_count=0,
        failed_count=1,
        skipped_count=0,
        headline_zh="失败",
        headline_en="failed",
        action_zh="看日志",
        action_en="see logs",
        notify=True,
        source="test",
    )
    sender = _FakeSender()
    result = maybe_send_failure_notification(summary, environ={}, sender=sender)
    assert result["attempted"] is False
    assert sender.calls == []


def test_failure_notify_sends_short_text() -> None:
    summary = DailyRunSummary(
        outcome=OUTCOME_FAILED,
        primary_code=CODE_MISSING_LLM,
        ok_count=0,
        failed_count=1,
        skipped_count=0,
        headline_zh="未检测到可用模型 Key",
        headline_en="No usable model API key",
        action_zh="添加 GEMINI_API_KEY",
        action_en="Add GEMINI_API_KEY",
        notify=True,
        source="test",
    )
    sender = _FakeSender(succeed=True)
    result = maybe_send_failure_notification(
        summary,
        environ={"FAILURE_NOTIFY_ENABLED": "true", "NOTIFICATION_SYSTEM_ERROR_CHANNELS": "custom"},
        sender=sender,
    )
    assert result["attempted"] is True and result["sent"] is True
    assert sender.calls[0]["route_type"] == "system_error"
    assert "sk-" not in sender.calls[0]["content"]


def test_failure_notify_exception_is_fail_open() -> None:
    summary = DailyRunSummary(
        outcome=OUTCOME_FAILED,
        primary_code=CODE_UNKNOWN,
        ok_count=0,
        failed_count=1,
        skipped_count=0,
        headline_zh="失败",
        headline_en="failed",
        action_zh="看日志",
        action_en="see logs",
        notify=True,
        source="test",
    )
    result = maybe_send_failure_notification(
        summary, environ={"FAILURE_NOTIFY_ENABLED": "true"}, sender=_FakeSender(raise_exc=True)
    )
    assert result["attempted"] is True and result["sent"] is False


def test_sanitize_summary_redacts_common_secret_shapes() -> None:
    cleaned = sanitize_summary_text("token=sk-abc123SECRET and Authorization: Bearer supersecretvalue")
    assert "sk-abc123SECRET" not in cleaned
    assert "supersecretvalue" not in cleaned


def test_timeout_from_job_status() -> None:
    summary = resolve_summary(
        status=None,
        exit_code=None,
        job_status="cancelled",
        environ={"GEMINI_API_KEY": "x", "STOCK_LIST": "600519"},
    )
    assert summary.primary_code == CODE_TIMEOUT


def test_fallback_missing_llm_from_env() -> None:
    summary = resolve_summary(
        status=None, exit_code=1, job_status="failure", environ={"STOCK_LIST": "600519"}
    )
    assert summary.primary_code == CODE_MISSING_LLM


def test_failure_notify_enabled_defaults() -> None:
    assert failure_notify_enabled({"NOTIFICATION_SYSTEM_ERROR_CHANNELS": "email"}) is True
    assert failure_notify_enabled({}) is False
    assert failure_notify_enabled({"FAILURE_NOTIFY_ENABLED": "true"}) is True
    assert failure_notify_enabled(
        {"FAILURE_NOTIFY_ENABLED": "false", "NOTIFICATION_SYSTEM_ERROR_CHANNELS": "email"}
    ) is False


def test_build_and_emit_writes_step_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    status_path = tmp_path / "run_status.json"
    summary_path = tmp_path / "step_summary.md"
    write_run_status(
        build_status_from_counts(
            ok_count=2, failed_count=0, attempted_codes=["A", "B"], successful_codes=["A", "B"]
        ),
        status_path,
    )
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    summary = build_and_emit_summary(
        status_path=status_path,
        exit_code=0,
        job_status="success",
        write_step_summary=True,
        notify_on_failure=False,
        environ={"GITHUB_STEP_SUMMARY": str(summary_path)},
    )
    assert summary.outcome == OUTCOME_SUCCESS
    assert "Daily Analysis" in summary_path.read_text(encoding="utf-8")


def test_append_step_summary_fail_open_without_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert append_github_step_summary("# hello\n") is False
    assert "hello" in capsys.readouterr().out


def test_has_any_llm_secret_presence_only() -> None:
    assert has_any_llm_secret({"GEMINI_API_KEY": "abc"}) is True
    assert has_any_llm_secret({}) is False


def test_status_for_failure_sanitizes_detail() -> None:
    doc = build_status_for_failure(detail="Authorization: Bearer supersecretvalue")
    detail = (doc.steps[0].detail or "") + str(doc.extra)
    assert "supersecretvalue" not in detail


def test_script_main_always_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.actions_daily_run_summary import main

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    assert main([
        "--status", str(tmp_path / "missing.json"),
        "--exit-code", "1",
        "--job-status", "failure",
        "--no-write-step-summary",
    ]) == 0
