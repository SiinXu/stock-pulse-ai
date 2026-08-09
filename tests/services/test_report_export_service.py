# -*- coding: utf-8 -*-
"""Contract tests for lossless Markdown and bounded optional PDF export."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services import report_export_service as export_mod
from src.services.report_export_service import (
    PdfBackendStatus,
    ReportExportBusyError,
    ReportExportDependencyError,
    ReportExportFontError,
    ReportExportFormatError,
    ReportExportLimitError,
    capabilities_public_view,
    export_markdown_bytes,
    export_pdf_bytes,
    export_report,
    get_export_capabilities,
    inspect_font_file,
    missing_font_codepoints,
    resolve_pdf_font_path,
)


SAMPLE_ZH = """# 中钨高新 000657 分析报告

**生成日期**: 2026-08-09

## 结论摘要

当前趋势偏多，建议**持有**观察。关键风险：行业周期波动。

| 维度 | 分数 | 完整证据 |
| --- | ---: | --- |
| 趋势 | 72 | 这是超过四十个字符后仍必须完整保留的关键投资证据，不能静默截断或跨列重叠，而且最后的唯一标记也必须存在。 |
| 估值 | 58 | 风险句也必须换行并跨页完整保留。 |

1. 关注放量突破
   - 嵌套条件必须保留
2. 止损位 12.50

[研究链接](https://example.invalid/private?token=link-secret)
![K线图](https://example.invalid/chart(v2).png?token=image-secret "signed chart")

> 免责声明：本报告仅供研究参考，不构成投资建议。
"""


def _font_covering(text: str) -> str:
    for candidate in export_mod._DEFAULT_FONT_CANDIDATES:
        if inspect_font_file(candidate).valid and not missing_font_codepoints(candidate, text):
            return candidate
    pytest.skip("host has no validated single-face font covering this fixture")


def _clear_pdf_cache() -> None:
    with export_mod._PDF_CACHE_LOCK:
        export_mod._PDF_CACHE.clear()
        export_mod._PDF_CACHE_BYTES = 0


def test_export_markdown_is_exact_and_always_available():
    artifact = export_markdown_bytes(SAMPLE_ZH, filename_stem="demo")
    assert artifact.format == "md"
    assert artifact.media_type.startswith("text/markdown")
    assert artifact.filename == "demo.md"
    assert artifact.content.decode("utf-8") == SAMPLE_ZH


def test_export_report_md_roundtrip_and_format_bounds():
    assert export_report(SAMPLE_ZH, "MD").content.decode("utf-8") == SAMPLE_ZH
    with pytest.raises(ReportExportFormatError) as exc:
        export_report(SAMPLE_ZH, "docx")
    assert exc.value.error_code == "export_format_invalid"
    with pytest.raises(ReportExportFormatError) as exc:
        export_report("   ", "md")
    assert exc.value.error_code == "export_empty"


def test_capabilities_are_language_aware_and_never_expose_paths(monkeypatch, tmp_path):
    invalid = tmp_path / "operator-secret" / "broken.ttf"
    invalid.parent.mkdir()
    invalid.write_bytes(b"not-a-font")
    monkeypatch.setattr(export_mod, "_configured_font_path", lambda: str(invalid))
    caps = get_export_capabilities("zh")
    assert caps["formats"]["md"]["available"] is True
    assert caps["formats"]["pdf"]["available"] is False
    assert caps["formats"]["pdf"]["status"] == "configured_font_invalid"
    assert caps["requested_language"] == "zh"
    assert caps["chart_handling"] == "markdown_images_omitted_without_destinations"
    public = capabilities_public_view(caps)
    assert "font_path" not in str(public)
    assert str(invalid) not in str(public)
    assert public["pdf_limits"]["max_pages"] == export_mod.MAX_PDF_PAGES


def test_pdf_rejects_missing_or_conflicting_backend(monkeypatch):
    monkeypatch.setattr(
        export_mod,
        "inspect_pdf_backend",
        lambda: PdfBackendStatus(False, "legacy_namespace_conflict", "1.7.2"),
    )
    with pytest.raises(ReportExportDependencyError) as exc:
        export_pdf_bytes("# Report")
    assert exc.value.error_code == "export_dependency_missing"
    assert "requirements-report-export" in exc.value.install_hint


def test_backend_detects_legacy_only_namespace(monkeypatch):
    def _version(distribution):
        assert distribution == "fpdf2"
        raise export_mod.importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(export_mod.importlib.metadata, "version", _version)
    monkeypatch.setattr(
        export_mod.importlib.metadata,
        "packages_distributions",
        lambda: {"fpdf": ["fpdf"]},
    )
    backend = export_mod.inspect_pdf_backend()
    assert backend.available is False
    assert backend.status == "legacy_namespace_conflict"
    assert backend.dependency_installed is False


def test_backend_rejects_missing_ast_support_dependency(monkeypatch):
    real_version = export_mod.importlib.metadata.version

    def _version(distribution):
        if distribution == "markdown-it-py":
            raise export_mod.importlib.metadata.PackageNotFoundError
        return real_version(distribution)

    monkeypatch.setattr(export_mod.importlib.metadata, "version", _version)
    backend = export_mod.inspect_pdf_backend()
    assert backend.available is False
    assert backend.status == "dependency_missing"
    assert backend.dependency_installed is True


def test_capabilities_distinguish_installed_but_conflicting_backend(monkeypatch):
    monkeypatch.setattr(
        export_mod,
        "inspect_pdf_backend",
        lambda: PdfBackendStatus(False, "legacy_namespace_conflict", "2.8.3"),
    )
    pdf = get_export_capabilities("en")["formats"]["pdf"]
    assert pdf["available"] is False
    assert pdf["dependency_installed"] is True
    assert pdf["status"] == "legacy_namespace_conflict"


def test_font_disappearing_before_cache_lookup_is_sanitized(monkeypatch):
    monkeypatch.setattr(
        export_mod,
        "inspect_pdf_backend",
        lambda: PdfBackendStatus(True, "ready", "2.8.3"),
    )
    monkeypatch.setattr(
        export_mod,
        "_resolve_font_for_text",
        lambda *_args, **_kwargs: ("/operator/secret/font.ttf", "font_parsed", 0),
    )
    monkeypatch.setattr(
        export_mod,
        "_cache_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("/operator/secret/font.ttf")),
    )
    with pytest.raises(ReportExportFontError) as exc:
        export_pdf_bytes("# Report")
    assert exc.value.error_code == "export_font_invalid"
    assert "/operator/" not in exc.value.message


def test_explicit_invalid_font_fails_closed_without_candidate_fallback(tmp_path):
    invalid = tmp_path / "FakeFont.ttf"
    invalid.write_bytes(b"not-a-real-font")
    valid = _font_covering("Report")
    assert resolve_pdf_font_path(configured=str(invalid), candidates=[valid]) is None
    assert inspect_font_file(str(invalid)).status == "font_invalid"


def test_default_font_resolution_skips_parseable_candidate_without_required_glyphs(monkeypatch):
    monkeypatch.setattr(export_mod, "_DEFAULT_FONT_CANDIDATES", ("latin.ttf", "complete.ttf"))
    monkeypatch.setattr(
        export_mod,
        "inspect_font_file",
        lambda _path: export_mod.FontInspection(True, "font_parsed", frozenset()),
    )
    monkeypatch.setattr(
        export_mod,
        "missing_font_codepoints",
        lambda path, _text: frozenset({1}) if path == "latin.ttf" else frozenset(),
    )
    monkeypatch.setattr(Path, "resolve", lambda self: self)
    resolved, status, missing_count = export_mod._resolve_font_for_text(
        "中文",
        configured=None,
    )
    assert resolved == "complete.ttf"
    assert status == "font_parsed"
    assert missing_count == 0


def test_markdown_ast_discards_complete_image_and_link_destinations():
    blocks = export_mod._parse_markdown_blocks(SAMPLE_ZH)
    visible = export_mod._rendered_text(blocks)
    assert "研究链接" in visible
    assert "K线图" in visible
    assert "图表/图片已在 PDF 导出中省略" in visible
    assert "link-secret" not in visible
    assert "image-secret" not in visible
    assert "chart(v2)" not in visible
    assert "https://" not in visible


def test_markdown_ast_preserves_nested_list_depth_and_complete_table_cells():
    blocks = export_mod._parse_markdown_blocks(SAMPLE_ZH)
    list_items = [payload for kind, payload in blocks if kind == "list_item"]
    assert [item["depth"] for item in list_items] == [1, 2, 1]
    table = next(payload for kind, payload in blocks if kind == "table")
    assert table["rows"][0][2].endswith("最后的唯一标记也必须存在。")
    assert len(table["rows"][0][2]) > 40


def test_pdf_input_and_table_shape_limits_fail_explicitly(monkeypatch):
    monkeypatch.setattr(
        export_mod,
        "inspect_pdf_backend",
        lambda: PdfBackendStatus(True, "ready", "2.8.3"),
    )
    with pytest.raises(ReportExportLimitError) as exc:
        export_pdf_bytes("x" * (export_mod.MAX_PDF_INPUT_BYTES + 1))
    assert exc.value.error_code == "export_input_too_large"

    columns = export_mod.MAX_TABLE_COLUMNS + 1
    header = "|" + "|".join(f"h{i}" for i in range(columns)) + "|"
    separator = "|" + "|".join("---" for _ in range(columns)) + "|"
    row = "|" + "|".join(f"v{i}" for i in range(columns)) + "|"
    with pytest.raises(ReportExportLimitError) as exc:
        export_pdf_bytes("\n".join((header, separator, row)))
    assert exc.value.error_code == "export_table_columns_exceeded"


def test_pdf_deadline_starts_before_ast_and_font_work(monkeypatch):
    clock = iter((100.0, 100.0, 121.0))
    monkeypatch.setattr(export_mod.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        export_mod,
        "inspect_pdf_backend",
        lambda: PdfBackendStatus(True, "ready", "2.8.3"),
    )
    with pytest.raises(ReportExportLimitError) as exc:
        export_pdf_bytes("# Report")
    assert exc.value.error_code == "export_deadline_exceeded"
    assert exc.value.status_code == 503


@pytest.mark.skipif(
    not export_mod.is_pdf_dependency_available(),
    reason="optional fpdf2 not installed",
)
def test_pdf_rejects_report_glyphs_missing_from_otherwise_valid_font():
    font = _font_covering("StockPulse report")
    missing = missing_font_codepoints(font, "🚨")
    if not missing:
        pytest.skip("selected host font happens to cover the counterexample emoji")
    with pytest.raises(ReportExportFontError) as exc:
        export_pdf_bytes("# StockPulse report 🚨", font_path=font)
    assert exc.value.error_code == "export_font_coverage_missing"


@pytest.mark.skipif(
    not export_mod.is_pdf_dependency_available(),
    reason="optional fpdf2 not installed",
)
def test_pdf_long_table_wraps_across_pages_without_text_deletion(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    long_evidence = "Complete evidence sentence " * 18
    rows = "\n".join(
        f"| row-{index} | {long_evidence} unique-tail-{index} |"
        for index in range(26)
    )
    markdown = (
        "# Full report\n\n"
        "| Record | Evidence |\n| --- | --- |\n"
        f"{rows}\n\n"
        "> Disclaimer: research only; not investment advice.\n"
    )
    font = _font_covering(export_mod._rendered_text(export_mod._parse_markdown_blocks(markdown)))
    _clear_pdf_cache()
    artifact = export_pdf_bytes(markdown, font_path=font, filename_stem="long-table")
    output = tmp_path / "long-table.pdf"
    output.write_bytes(artifact.content)
    reader = pypdf.PdfReader(str(output))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(reader.pages) > 1
    assert extracted.count("Record") >= 2  # repeated table header
    assert "unique-tail-0" in extracted
    assert "unique-tail-25" in extracted
    assert "Disclaimer: research only; not investment advice." in extracted


def test_busy_capacity_has_explicit_retryable_error(monkeypatch):
    class _BusySemaphore:
        def acquire(self, *, blocking):
            assert blocking is False
            return False

        def release(self):  # pragma: no cover - acquire is false
            raise AssertionError("release must not run")

    font = _font_covering("Report")
    monkeypatch.setattr(export_mod, "_PDF_SEMAPHORE", _BusySemaphore())
    _clear_pdf_cache()
    with pytest.raises(ReportExportBusyError) as exc:
        export_pdf_bytes("# Report", font_path=font)
    assert exc.value.error_code == "export_busy"
