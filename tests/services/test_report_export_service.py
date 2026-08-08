# -*- coding: utf-8 -*-
"""Unit tests for report export service (Markdown always; PDF optional)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.services import report_export_service as export_mod
from src.services.report_export_service import (
    ReportExportDependencyError,
    ReportExportFontError,
    ReportExportFormatError,
    capabilities_public_view,
    export_markdown_bytes,
    export_pdf_bytes,
    export_report,
    get_export_capabilities,
    resolve_pdf_font_path,
)


SAMPLE_ZH = """# 中钨高新 000657 分析报告

**生成日期**: 2026-08-09

## 结论摘要

当前趋势偏多，建议**持有**观察。关键风险：行业周期波动。

### 评分

| 维度 | 分数 |
| --- | ---: |
| 趋势 | 72 |
| 估值 | 58 |

## 操作建议

1. 关注放量突破
2. 止损位 12.50

![K线图](https://example.invalid/chart.png)

> 免责声明：本报告仅供研究参考，不构成投资建议。
"""


def test_export_markdown_always_available():
    artifact = export_markdown_bytes(SAMPLE_ZH, filename_stem="demo")
    assert artifact.format == "md"
    assert artifact.media_type.startswith("text/markdown")
    assert artifact.filename == "demo.md"
    assert "中钨高新".encode("utf-8") in artifact.content
    assert artifact.content.decode("utf-8") == SAMPLE_ZH


def test_export_report_md_roundtrip():
    artifact = export_report(SAMPLE_ZH, "MD", filename_stem="stockpulse-report-1")
    assert artifact.format == "md"
    assert artifact.filename.endswith(".md")


def test_export_rejects_unknown_format():
    with pytest.raises(ReportExportFormatError) as exc:
        export_report(SAMPLE_ZH, "docx")
    assert exc.value.error_code == "export_format_invalid"
    assert "docx" in exc.value.message.lower() or "Unsupported" in exc.value.message


def test_export_rejects_empty_content():
    with pytest.raises(ReportExportFormatError) as exc:
        export_report("   ", "md")
    assert exc.value.error_code == "export_empty"


def test_capabilities_marks_office_remaining():
    caps = get_export_capabilities()
    assert caps["formats"]["md"]["available"] is True
    assert caps["office_formats_status"] == "not_implemented"
    assert caps["chart_handling"] == "markdown_images_omitted"
    public = capabilities_public_view(caps)
    pdf = public["formats"]["pdf"]
    assert "font_path" not in pdf
    assert "install_hint" in pdf


def test_pdf_missing_dependency_raises(monkeypatch):
    monkeypatch.setattr(export_mod, "is_pdf_dependency_available", lambda: False)
    with pytest.raises(ReportExportDependencyError) as exc:
        export_pdf_bytes(SAMPLE_ZH)
    assert exc.value.error_code == "export_dependency_missing"
    assert "fpdf2" in exc.value.message
    assert "requirements-report-export" in exc.value.install_hint


def test_pdf_missing_font_raises(monkeypatch):
    monkeypatch.setattr(export_mod, "is_pdf_dependency_available", lambda: True)
    monkeypatch.setattr(export_mod, "resolve_pdf_font_path", lambda **_k: None)
    with pytest.raises(ReportExportFontError) as exc:
        export_pdf_bytes(SAMPLE_ZH)
    assert exc.value.error_code == "export_font_missing"
    assert "REPORT_EXPORT_PDF_FONT_PATH" in exc.value.message


def test_resolve_font_prefers_configured(tmp_path, monkeypatch):
    font = tmp_path / "FakeFont.ttf"
    font.write_bytes(b"not-a-real-font")
    monkeypatch.setenv("REPORT_EXPORT_PDF_FONT_PATH", str(font))
    resolved = resolve_pdf_font_path(candidates=())
    assert resolved == str(font.resolve())


def test_resolve_font_skips_ttc(tmp_path):
    ttc = tmp_path / "CJK.ttc"
    ttc.write_bytes(b"ttc")
    ttf = tmp_path / "ok.ttf"
    ttf.write_bytes(b"ttf")
    resolved = resolve_pdf_font_path(configured=None, candidates=[str(ttc), str(ttf)])
    assert resolved == str(ttf.resolve())


@pytest.mark.skipif(
    not export_mod.is_pdf_dependency_available(),
    reason="optional fpdf2 not installed",
)
def test_pdf_chinese_export_when_font_available():
    font = resolve_pdf_font_path()
    if not font:
        pytest.skip("no CJK-capable .ttf/.otf font on this host")
    artifact = export_pdf_bytes(
        SAMPLE_ZH,
        filename_stem="zh-report",
        title="中钨高新报告",
        font_path=font,
    )
    assert artifact.format == "pdf"
    assert artifact.media_type == "application/pdf"
    assert artifact.filename == "zh-report.pdf"
    assert artifact.content.startswith(b"%PDF")
    assert len(artifact.content) > 500
    # Image omission note should appear in the PDF stream as UTF-16/embedded text;
    # at minimum the PDF is well-formed and non-trivial.
    out = Path("/tmp/stockpulse-t19-zh-export.pdf")
    out.write_bytes(artifact.content)
    assert out.stat().st_size == len(artifact.content)
