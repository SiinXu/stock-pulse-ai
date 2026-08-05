"""Unit tests for bilingual CLI end-of-run summary rendering."""

from types import SimpleNamespace

from src.app.cli import (
    CliRunSummary,
    CliRunSummaryCapture,
    analyzer_has_no_usable_llm,
    build_notification_summary_lines,
    format_cli_run_summary,
)


def test_format_summary_ok_and_failed_counts() -> None:
    text = format_cli_run_summary(
        CliRunSummary(ok_count=2, failed_count=1, report_paths=["reports/report_x.md"])
    )
    assert "Run summary" in text
    assert "运行摘要" in text
    assert "OK=2" in text
    assert "failed/失败=1" in text
    assert "reports/report_x.md" in text
    assert "Reports / 报告" in text


def test_format_summary_no_llm_mentions_config() -> None:
    text = format_cli_run_summary(
        CliRunSummary(ok_count=0, failed_count=1, no_llm=True)
    )
    assert "no usable LLM" in text
    assert "LITELLM_MODEL" in text
    assert "GEMINI_API_KEY" in text
    assert "未检测到可用 LLM" in text
    # dry-run note should not appear when not dry_run
    assert "data-only report" not in text


def test_format_summary_dry_run_note() -> None:
    text = format_cli_run_summary(
        CliRunSummary(ok_count=1, failed_count=0, dry_run=True, no_llm=True)
    )
    assert "data-only report" in text
    assert "仅数据报告" in text
    # dry-run note takes precedence over the bare no-LLM line
    assert "no usable LLM" not in text


def test_format_summary_notifications_section() -> None:
    text = format_cli_run_summary(
        CliRunSummary(
            notifications=[
                ("email", "sent"),
                ("telegram", "skipped (dry-run)"),
            ]
        )
    )
    assert "Notifications / 通知" in text
    assert "email: sent" in text
    assert "telegram: skipped (dry-run)" in text


def test_format_summary_degrades_when_sections_empty() -> None:
    text = format_cli_run_summary(CliRunSummary())
    assert text.startswith("===== Run summary / 运行摘要 =====")
    assert "Stocks / 股票" not in text
    assert "Reports / 报告" not in text
    assert "Notifications / 通知" not in text


def test_build_notification_lines_prefer_captured_outcomes() -> None:
    capture = CliRunSummaryCapture()
    capture.channel_outcomes = [
        ("email", "sent"),
        ("email", "failed"),
        ("wechat", "sent"),
    ]
    lines = build_notification_summary_lines(
        capture=capture,
        dry_run=False,
        no_notify=False,
    )
    assert ("email", "failed") in lines
    assert ("wechat", "sent") in lines


def test_build_notification_lines_dry_run_skip() -> None:
    lines = build_notification_summary_lines(
        capture=CliRunSummaryCapture(),
        dry_run=True,
        no_notify=False,
    )
    assert lines
    assert all("dry-run" in status for _channel, status in lines)


def test_analyzer_has_no_usable_llm_reuses_is_available() -> None:
    assert analyzer_has_no_usable_llm(None) is True
    assert analyzer_has_no_usable_llm(SimpleNamespace(is_available=lambda: False)) is True
    assert analyzer_has_no_usable_llm(SimpleNamespace(is_available=lambda: True)) is False


def test_capture_records_report_path_and_channel_outcomes() -> None:
    class _Result:
        def __init__(self):
            self.channel_results = [
                SimpleNamespace(channel="__context__", success=True),
                SimpleNamespace(channel="email", success=True),
                SimpleNamespace(channel="feishu", success=False),
            ]

    class _Notifier:
        def save_report_to_file(self, content, filename=None):
            return f"reports/{filename or 'report.md'}"

        def send_with_results(self, *args, **kwargs):
            return _Result()

    notifier = _Notifier()
    capture = CliRunSummaryCapture()
    capture.install(notifier)
    path = notifier.save_report_to_file("x", filename="demo.md")
    notifier.send_with_results("body")
    capture.restore()

    assert path == "reports/demo.md"
    assert capture.report_paths == ["reports/demo.md"]
    assert ("email", "sent") in capture.channel_outcomes
    assert ("feishu", "failed") in capture.channel_outcomes
    assert all(ch != "__context__" for ch, _ in capture.channel_outcomes)
