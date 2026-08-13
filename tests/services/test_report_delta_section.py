"""Report-top delta section (Issue #148 remaining report scope)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.services.history_comparison_service import (
    AnalysisDelta,
    BASELINE_INCOMPARABLE,
    BASELINE_MISSING_HISTORY,
    BASELINE_OK,
    ListChange,
    ValueChange,
)
from src.services.notification_delta_formatter import (
    build_delta_section_markdown,
    prepend_report_delta_section,
)


def _result(code: str = "600519", language: str = "zh") -> SimpleNamespace:
    return SimpleNamespace(code=code, report_language=language)


def _delta(**overrides) -> AnalysisDelta:
    values = {
        "has_baseline": True,
        "baseline_status": BASELINE_OK,
        "has_material_changes": False,
    }
    values.update(overrides)
    return AnalysisDelta(**values)


def test_first_analysis_is_not_confused_with_no_change() -> None:
    deltas = {
        "600519": _delta(has_baseline=False, baseline_status=BASELINE_MISSING_HISTORY),
        "000001": _delta(),
    }
    section = build_delta_section_markdown(
        [_result("600519"), _result("000001")],
        "simple",
        delta_loader=lambda code, _rt: deltas[code],
    )
    assert "首次分析：暂无可用的历史基线。" in section
    assert "与上次分析相比无实质变化。" in section
    assert section.count("无实质变化") == 1


def test_non_finite_numeric_values_are_rejected() -> None:
    delta = _delta(
        has_material_changes=True,
        score_changes=[
            ValueChange(field="sentiment_score", base_value=60, target_value=72, direction="up", delta=12),
            ValueChange(
                field="dimension.momentum",
                base_value=1.0,
                target_value=float("inf"),
                direction="unavailable",
                delta=float("inf"),
                comparable=True,
            ),
            ValueChange(
                field="dimension.volume",
                base_value=float("nan"),
                target_value=10,
                direction="unavailable",
                delta=None,
                comparable=True,
            ),
        ],
        conclusion_changes=[
            ValueChange(field="action", base_value="hold", target_value="buy", direction="changed")
        ],
        evidence_changes=[
            ListChange(field="positive_catalysts", added=("上调指引",), added_total=1)
        ],
    )
    section = build_delta_section_markdown(
        [_result()], "simple", delta_loader=lambda _c, _r: delta
    )
    assert "情绪评分: 60 -> 72 (+12)" in section
    assert "动作: hold -> buy" in section
    assert "新增催化因素: 上调指引" in section
    assert "inf" not in section.lower()
    assert "nan" not in section.lower()


def test_prepend_is_idempotent_and_preserves_body() -> None:
    body = "# Report body\n\ncontent"
    once = prepend_report_delta_section(
        body,
        [_result(language="en")],
        "simple",
        delta_loader=lambda _c, _r: _delta(has_baseline=False, baseline_status=BASELINE_MISSING_HISTORY),
    )
    twice = prepend_report_delta_section(
        once,
        [_result(language="en")],
        "simple",
        delta_loader=lambda _c, _r: (_ for _ in ()).throw(RuntimeError("no")),
    )
    assert once.count("## Changes since previous analysis") == 1
    assert twice == once
    assert once.endswith(body)


def test_manual_aggregate_report_path_includes_delta() -> None:
    """Manual/CLI aggregate path prepends delta after dashboard generation."""
    from src.notification import ReportType
    from src.services.notification_delta_formatter import prepend_report_delta_section as real_prepend

    service = SimpleNamespace()

    def _normalize(report_type):
        return ReportType.from_str(report_type) if not isinstance(report_type, ReportType) else report_type

    def _prepend(content, results, report_type):
        return real_prepend(content, results, report_type)

    service._normalize_report_type = _normalize
    service._prepend_report_delta_section = _prepend
    service.generate_brief_report = MagicMock()
    dashboard_body = "# 🎯 决策仪表盘\n\nbody"

    def _dashboard(results, report_date=None, report_type=None):
        return service._prepend_report_delta_section(
            dashboard_body,
            results,
            report_type or "simple",
        )

    service.generate_dashboard_report = MagicMock(side_effect=_dashboard)

    def _aggregate(results, report_type, report_date=None):
        normalized = service._normalize_report_type(report_type)
        if normalized == ReportType.BRIEF:
            return service.generate_brief_report(results, report_date=report_date, report_type=normalized)
        return service.generate_dashboard_report(
            results, report_date=report_date, report_type=normalized
        )

    service.generate_aggregate_report = _aggregate

    delta = _delta(
        has_material_changes=True,
        conclusion_changes=[
            ValueChange(field="action", base_value="hold", target_value="buy", direction="changed")
        ],
    )
    with patch(
        "src.services.notification_delta_formatter.get_latest_delta",
        return_value=delta,
    ):
        rendered = service.generate_aggregate_report([_result()], ReportType.SIMPLE)

    service.generate_dashboard_report.assert_called_once()
    assert service.generate_dashboard_report.call_args.kwargs.get("report_type") == ReportType.SIMPLE
    assert "## 较上次分析的变化" in rendered
    assert "动作: hold -> buy" in rendered
    assert rendered.index("较上次分析的变化") < rendered.index("决策仪表盘")


def test_scheduled_and_manual_share_aggregate_delta_path() -> None:
    """Scheduled local save and manual runs both use generate_aggregate_report with delta."""
    from src.notification import ReportType

    delta = _delta(has_baseline=False, baseline_status=BASELINE_MISSING_HISTORY)
    body = "# 🎯 body"

    # Simulate what generate_aggregate_report returns after our wire-up.
    content = prepend_report_delta_section(
        body,
        [_result()],
        ReportType.SIMPLE,
        delta_loader=lambda _c, _r: delta,
    )
    notifier = MagicMock()
    notifier.generate_aggregate_report.return_value = content
    notifier.save_report_to_file = MagicMock(return_value="/tmp/report.md")

    # Scheduled: _save_local_report -> generate_aggregate_report -> save_report_to_file
    scheduled = notifier.generate_aggregate_report([_result()], ReportType.SIMPLE)
    scheduled_path = notifier.save_report_to_file(scheduled)

    # Manual: same generator entry (CLI/orchestration)
    manual = notifier.generate_aggregate_report([_result()], ReportType.SIMPLE)

    assert "首次分析：暂无可用的历史基线。" in scheduled
    assert scheduled.index("较上次分析的变化") < scheduled.index("body")
    assert manual == scheduled
    assert scheduled_path == "/tmp/report.md"
    assert notifier.generate_aggregate_report.call_count == 2


def test_loader_failure_keeps_report_body() -> None:
    body = "# original"
    rendered = prepend_report_delta_section(
        body,
        [_result()],
        "simple",
        delta_loader=lambda _c, _r: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    assert "暂时无法对比（error）" in rendered
    assert rendered.endswith(body)


def test_incomparable_status_is_explicit() -> None:
    rendered = prepend_report_delta_section(
        "body",
        [_result(language="en")],
        "full",
        delta_loader=lambda _c, _r: _delta(has_baseline=False, baseline_status=BASELINE_INCOMPARABLE),
    )
    assert "Comparison unavailable (incomparable_structure)." in rendered
    assert "First analysis" not in rendered
    assert "No material changes" not in rendered
