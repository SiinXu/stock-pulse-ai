# -*- coding: utf-8 -*-
"""API contracts for typed, bounded history report export."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from api.v1.endpoints import report_export as export_endpoint
from src.services.history_service import MarkdownReportGenerationError
from src.services.report_export_service import (
    ReportExportBusyError,
    ReportExportDependencyError,
    ReportExportFontError,
    ReportExportLimitError,
    ReportExportWorkerError,
)


class _FakeHistoryService:
    def __init__(self, markdown, detail=None, *, raise_gen: bool = False):
        self.markdown = markdown
        self.detail = detail if detail is not None else {"id": 42, "query_id": "q-42"}
        self.raise_gen = raise_gen

    def resolve_and_get_detail(self, record_id):
        return self.detail

    def get_markdown_report(self, record_id):
        if self.raise_gen:
            raise MarkdownReportGenerationError("raw provider detail", record_id=record_id)
        return self.markdown


def _patch_history(monkeypatch, service: _FakeHistoryService):
    monkeypatch.setattr(export_endpoint, "HistoryService", lambda _db: service)


def test_capabilities_endpoint_returns_typed_sanitized_model(monkeypatch):
    monkeypatch.setattr(
        export_endpoint,
        "get_export_capabilities",
        lambda language: {
            "formats": {
                "md": {
                    "available": True,
                    "status": "ready",
                    "media_type": "text/markdown; charset=utf-8",
                    "dependency": None,
                    "dependency_installed": True,
                    "font_validated": None,
                    "missing_glyph_count": 0,
                },
                "html": {
                    "available": True,
                    "status": "ready",
                    "media_type": "text/html; charset=utf-8",
                    "dependency": "markdown-it-py",
                    "dependency_installed": True,
                    "dependency_version": "4.2.0",
                    "font_validated": None,
                    "missing_glyph_count": 0,
                },
                "pdf": {
                    "available": False,
                    "status": "font_coverage_missing",
                    "media_type": "application/pdf",
                    "dependency": "fpdf2",
                    "dependency_installed": True,
                    "dependency_version": "2.8.3",
                    "font_validated": False,
                    "missing_glyph_count": 4,
                },
            },
            "requested_language": language,
            "supported_query_formats": ["md", "html", "pdf"],
            "office_formats_status": "html_only",
            "chart_handling": "markdown_images_omitted_without_destinations",
            "pdf_limits": {
                "max_input_bytes": 1_000_000,
                "max_pages": 100,
                "max_table_rows": 500,
                "max_table_columns": 12,
                "max_output_bytes": 25_165_824,
                "max_render_seconds": 20.0,
                "max_concurrency": 2,
            },
        },
    )
    response = export_endpoint.get_report_export_capabilities("zh")
    assert response.formats.md.available is True
    assert response.formats.html.available is True
    assert response.formats.pdf.status == "font_coverage_missing"
    assert response.office_formats_status == "html_only"
    assert "font_path" not in response.model_dump_json()


def test_export_markdown_attachment_uses_rfc5987_unicode_filename(monkeypatch):
    markdown = "# 测试报告\n\n内容"
    _patch_history(monkeypatch, _FakeHistoryService(markdown, {"id": "中钨高新"}))
    response = export_endpoint.export_history_report(
        "中钨高新", format="md", db_manager=object()
    )
    assert response.status_code == 200
    assert response.media_type.startswith("text/markdown")
    assert response.body.decode("utf-8") == markdown
    header = response.headers["content-disposition"]
    assert 'filename="stockpulse-report.md"' in header
    assert "filename*=UTF-8''stockpulse-report-%E4%B8%AD" in header
    assert len(header) < 1024


def test_content_disposition_blocks_header_injection_and_bounds_length():
    header = export_endpoint.build_content_disposition("报告\r\nX-Evil: yes" + "长" * 500 + ".pdf")
    assert "\r" not in header and "\n" not in header
    assert "X-Evil" not in header
    assert header.startswith("attachment; filename=")
    assert len(header) < 1024


def test_export_not_found(monkeypatch):
    _patch_history(monkeypatch, _FakeHistoryService(None, detail=None))
    with pytest.raises(HTTPException) as exc:
        export_endpoint.export_history_report("missing", format="md", db_manager=object())
    assert exc.value.status_code == 404
    assert exc.value.detail["error"] == "not_found"


def test_export_invalid_format_direct_call_still_returns_stable_400(monkeypatch):
    _patch_history(monkeypatch, _FakeHistoryService("# ok", {"id": 1}))
    with pytest.raises(HTTPException) as exc:
        export_endpoint.export_history_report("1", format="xlsx", db_manager=object())
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "export_format_invalid"


def test_export_invalid_format_http_contract_is_400():
    from api.app import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    response = TestClient(app).get("/api/v1/history/1/export?format=xlsx")
    assert response.status_code == 400
    assert response.json()["error"] == "export_format_invalid"


@pytest.mark.parametrize(
    ("raised", "status", "code"),
    [
        (ReportExportDependencyError("/secret/backend parser"), 503, "export_dependency_missing"),
        (ReportExportFontError("/secret/font.ttf parser detail"), 503, "export_font_missing"),
        (ReportExportLimitError("input too large"), 413, "export_limit_exceeded"),
        (ReportExportBusyError(), 429, "export_busy"),
        (ReportExportWorkerError(), 503, "export_worker_unavailable"),
    ],
)
def test_export_error_mapping_is_bounded_and_sanitized(monkeypatch, raised, status, code):
    _patch_history(monkeypatch, _FakeHistoryService("# ok", {"id": 1}))

    def _raise(*_args, **_kwargs):
        raise raised

    monkeypatch.setattr(export_endpoint, "export_report", _raise)
    with pytest.raises(HTTPException) as exc:
        export_endpoint.export_history_report("1", format="pdf", db_manager=object())
    assert exc.value.status_code == status
    assert exc.value.detail["error"] == code
    payload = json.dumps(exc.value.detail)
    assert "/secret/" not in payload
    assert "parser detail" not in payload


def test_generation_failure_does_not_expose_raw_service_detail(monkeypatch):
    _patch_history(monkeypatch, _FakeHistoryService("# ok", {"id": 1}, raise_gen=True))
    with pytest.raises(HTTPException) as exc:
        export_endpoint.export_history_report("1", format="md", db_manager=object())
    assert exc.value.status_code == 500
    assert "raw provider detail" not in json.dumps(exc.value.detail)


def test_openapi_has_typed_capability_enum_and_all_binary_media():
    from api.app import create_app

    schema = create_app().openapi()
    capabilities = schema["paths"]["/api/v1/history/export/capabilities"]["get"]
    assert capabilities["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ReportExportCapabilitiesResponse"
    )
    export = schema["paths"]["/api/v1/history/{record_id}/export"]["get"]
    format_parameter = next(item for item in export["parameters"] if item["name"] == "format")
    assert format_parameter["schema"]["enum"] == ["md", "html", "pdf"]
    content = export["responses"]["200"]["content"]
    assert content["application/pdf"]["schema"] == {"type": "string", "format": "binary"}
    assert content["text/markdown"]["schema"] == {"type": "string", "format": "binary"}
    assert content["text/html"]["schema"] == {"type": "string", "format": "binary"}


def test_export_html_attachment_uses_html_suffix(monkeypatch):
    markdown = "# 测试报告\n\n内容"
    _patch_history(monkeypatch, _FakeHistoryService(markdown, {"id": 7}))
    monkeypatch.setattr(
        export_endpoint,
        "export_report",
        lambda *args, **kwargs: type(
            "Artifact",
            (),
            {
                "content": b"<!DOCTYPE html><html><body>ok</body></html>",
                "media_type": "text/html; charset=utf-8",
                "filename": "stockpulse-report-7.html",
                "format": "html",
            },
        )(),
    )
    response = export_endpoint.export_history_report(
        "7", format="html", db_manager=object()
    )
    assert response.status_code == 200
    assert response.media_type.startswith("text/html")
    assert ".html" in response.headers["content-disposition"]
    assert response.headers["X-StockPulse-Export-Format"] == "html"
