"""End-to-end path coverage for the report-top delta section (#148).

These tests exercise the real report generation, local-save, and history-markdown
pipelines. Only the history-comparison loader is stubbed so the suite stays
offline; the render, prepend, and save layers run for real.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.analyzer import AnalysisResult
from src.config import Config
from src.core.pipeline import StockAnalysisPipeline
from src.core.pipeline_stage_results import PipelineStageRunner
from src.enums import ReportType
from src.notification import NotificationService
from src.services.history_comparison_service import (
    AnalysisDelta,
    BASELINE_MISSING_HISTORY,
    BASELINE_OK,
    ValueChange,
)
from src.services.history_service import HistoryService
from src.services.notification_delta_formatter import prepend_report_delta_section


def _config(**overrides) -> Config:
    values = {
        "stock_list": [],
        "report_type": "simple",
        "report_language": "en",
        "report_history_compare_n": 0,
        "report_renderer_enabled": False,
        "report_show_llm_model": False,
        "notification_delta_first": False,
    }
    values.update(overrides)
    return Config(**values)


def _analysis_result(
    code: str = "600519",
    *,
    language: str = "en",
    score: int = 70,
    advice: str = "hold",
) -> AnalysisResult:
    return AnalysisResult(
        code=code,
        name="Test Stock",
        sentiment_score=score,
        trend_prediction="sideways",
        operation_advice=advice,
        decision_type="hold",
        confidence_level="中",
        report_language=language,
        action="hold",
        action_label="Hold",
        analysis_summary="summary",
        dashboard={
            "core_conclusion": {
                "one_sentence": "Hold for now",
                "time_sensitivity": "medium",
                "position_advice": {
                    "no_position": "wait",
                    "has_position": "hold",
                },
            },
            "intelligence": {
                "risk_alerts": ["risk-a"],
                "positive_catalysts": ["catalyst-a"],
            },
            "battle_plan": {},
            "data_perspective": {},
        },
        success=True,
    )


def _delta_first(code: str = "600519") -> AnalysisDelta:
    return AnalysisDelta(
        has_baseline=False,
        baseline_status=BASELINE_MISSING_HISTORY,
        has_material_changes=False,
        stock_code=code,
        report_type="simple",
    )


def _delta_unchanged(code: str = "600519") -> AnalysisDelta:
    return AnalysisDelta(
        has_baseline=True,
        baseline_status=BASELINE_OK,
        has_material_changes=False,
        stock_code=code,
        report_type="simple",
    )


def _delta_material(code: str = "600519") -> AnalysisDelta:
    return AnalysisDelta(
        has_baseline=True,
        baseline_status=BASELINE_OK,
        has_material_changes=True,
        stock_code=code,
        report_type="simple",
        conclusion_changes=[
            ValueChange(
                field="action",
                base_value="hold",
                target_value="buy",
                direction="changed",
            )
        ],
        score_changes=[
            ValueChange(
                field="sentiment_score",
                base_value=60,
                target_value=72,
                direction="up",
                delta=12,
            )
        ],
    )


def test_scheduled_local_report_path_persists_delta_section() -> None:
    """Scheduled/batch path: pipeline._save_local_report writes delta into the file."""
    config = _config()
    result = _analysis_result()
    saved: dict[str, str] = {}

    def _save(content: str, filename: str | None = None) -> str:
        saved["content"] = content
        return f"/tmp/{filename or 'report.md'}"

    with patch("src.notification.get_config", return_value=config), patch(
        "src.config.get_config",
        return_value=config,
    ), patch(
        "src.services.notification_delta_formatter.get_latest_delta",
        return_value=_delta_material(),
    ):
        notifier = NotificationService()
        notifier.save_report_to_file = _save  # type: ignore[method-assign]
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline._pipeline_stage_runner = PipelineStageRunner()
        pipeline.notifier = notifier
        pipeline.config = config
        pipeline._refresh_saved_diagnostic_snapshot = MagicMock()
        pipeline._save_local_report([result], ReportType.SIMPLE)

    content = saved["content"]
    assert content.startswith("## Changes since previous analysis")
    assert "### 600519" in content
    assert "Action: hold -> buy" in content
    assert "Sentiment score: 60 -> 72 (+12)" in content
    assert "Test Stock" in content


def test_manual_history_markdown_path_renders_delta_section() -> None:
    """Manual/Web path: HistoryService markdown includes the delta section."""
    result = _analysis_result(language="zh")
    record = SimpleNamespace(
        id=42,
        code="600519",
        name="Test Stock",
        report_type="simple",
        created_at=SimpleNamespace(
            strftime=lambda fmt: "2026-08-12" if "%Y" in fmt else "12:00:00"
        ),
    )

    service = HistoryService.__new__(HistoryService)
    service.db = MagicMock()
    service.db.get_analysis_history.return_value = [
        SimpleNamespace(id=42),
        SimpleNamespace(id=41),
    ]

    with patch(
        "src.services.history_comparison_service.compare_analyses",
        return_value=_delta_first(),
    ), patch(
        "src.services.history_comparison_service.get_latest_delta",
        return_value=_delta_first(),
    ):
        markdown = service._generate_single_stock_markdown(result, record)

    assert markdown.startswith("## 较上次分析的变化")
    assert "### 600519" in markdown
    assert "首次分析：暂无可用的历史基线。" in markdown
    assert "无实质变化" not in markdown
    assert "Test Stock" in markdown


def test_first_analysis_and_no_change_copy_do_not_cross_contaminate() -> None:
    config = _config()
    first = _analysis_result("AAA")
    second = _analysis_result("BBB")
    deltas = {
        "AAA": _delta_first("AAA"),
        "BBB": _delta_unchanged("BBB"),
    }

    def _loader(code: str, _report_type: str) -> AnalysisDelta:
        return deltas[code]

    with patch("src.notification.get_config", return_value=config), patch(
        "src.config.get_config",
        return_value=config,
    ), patch(
        "src.services.notification_delta_formatter.get_latest_delta",
        side_effect=_loader,
    ):
        content = NotificationService().generate_aggregate_report(
            [first, second],
            ReportType.SIMPLE,
        )

    aaa_block = content.split("### AAA", 1)[1].split("### BBB", 1)[0]
    bbb_block = content.split("### BBB", 1)[1].split("---", 1)[0]
    assert "First analysis: no previous baseline is available." in aaa_block
    assert "No material changes" not in aaa_block
    assert "No material changes since the previous analysis." in bbb_block
    assert "First analysis" not in bbb_block


def test_delta_loader_failure_leaves_report_body_and_shows_unavailable() -> None:
    config = _config()
    result = _analysis_result()

    with patch("src.notification.get_config", return_value=config), patch(
        "src.config.get_config",
        return_value=config,
    ), patch(
        "src.services.notification_delta_formatter.get_latest_delta",
        side_effect=RuntimeError("db down"),
    ):
        content = NotificationService().generate_aggregate_report(
            [result],
            ReportType.SIMPLE,
        )

    assert "## Changes since previous analysis" in content
    assert "Comparison unavailable (error)." in content
    assert "Test Stock" in content


def test_notification_delta_first_does_not_duplicate_report_section() -> None:
    config = _config()
    result = _analysis_result()
    with patch("src.notification.get_config", return_value=config), patch(
        "src.config.get_config",
        return_value=config,
    ), patch(
        "src.services.notification_delta_formatter.get_latest_delta",
        return_value=_delta_material(),
    ):
        report = NotificationService().generate_aggregate_report(
            [result],
            ReportType.SIMPLE,
        )
        combined = prepend_report_delta_section(
            report,
            [result],
            "simple",
            delta_loader=lambda *_: _delta_material(),
        )
    assert combined.count("## Changes since previous analysis") == 1
