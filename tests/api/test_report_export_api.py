# -*- coding: utf-8 -*-
"""API tests for history report export endpoints."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.v1.endpoints import report_export as export_endpoint
from src.services.history_service import MarkdownReportGenerationError
from src.services.report_export_service import (
    ReportExportDependencyError,
    ReportExportFontError,
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
            raise MarkdownReportGenerationError("boom", record_id=record_id)
        return self.markdown


def _patch_history(monkeypatch, service: _FakeHistoryService):
    monkeypatch.setattr(export_endpoint, "HistoryService", lambda _db: service)


def test_capabilities_endpoint_returns_md_available(monkeypatch):
    response = export_endpoint.get_report_export_capabilities()
    assert response.status_code == 200
    body = response.body
    # JSONResponse stores rendered body
    import json

    data = json.loads(body)
    assert data["formats"]["md"]["available"] is True
    assert data["office_formats_status"] == "not_implemented"
    assert "font_path" not in data["formats"]["pdf"]


def test_export_markdown_attachment(monkeypatch):
    md = "# 测试报告\n\n内容"
    _patch_history(monkeypatch, _FakeHistoryService(md, {"id": 7}))
    response = export_endpoint.export_history_report(
        "7", format="md", db_manager=object()
    )
    assert response.status_code == 200
    assert response.media_type.startswith("text/markdown")
    assert response.body.decode("utf-8") == md
    assert "stockpulse-report-7.md" in response.headers["content-disposition"]
    assert response.headers["x-stockpulse-export-format"] == "md"


def test_export_not_found(monkeypatch):
    _patch_history(monkeypatch, _FakeHistoryService(None, detail=None))
    with pytest.raises(HTTPException) as exc:
        export_endpoint.export_history_report("missing", format="md", db_manager=object())
    assert exc.value.status_code == 404
    assert exc.value.detail["error"] == "not_found"


def test_export_invalid_format(monkeypatch):
    _patch_history(monkeypatch, _FakeHistoryService("# ok", {"id": 1}))
    with pytest.raises(HTTPException) as exc:
        export_endpoint.export_history_report("1", format="xlsx", db_manager=object())
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "export_format_invalid"


def test_export_pdf_dependency_missing_returns_503(monkeypatch):
    _patch_history(monkeypatch, _FakeHistoryService("# ok", {"id": 1}))

    def _raise(*_a, **_k):
        raise ReportExportDependencyError("fpdf2 missing")

    monkeypatch.setattr(export_endpoint, "export_report", _raise)
    with pytest.raises(HTTPException) as exc:
        export_endpoint.export_history_report("1", format="pdf", db_manager=object())
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "export_dependency_missing"
    assert "install_hint" in exc.value.detail.get("params", {})


def test_export_pdf_font_missing_returns_503(monkeypatch):
    _patch_history(monkeypatch, _FakeHistoryService("# ok", {"id": 1}))

    def _raise(*_a, **_k):
        raise ReportExportFontError("no font")

    monkeypatch.setattr(export_endpoint, "export_report", _raise)
    with pytest.raises(HTTPException) as exc:
        export_endpoint.export_history_report("1", format="pdf", db_manager=object())
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "export_font_missing"


def test_export_generation_failure_returns_500(monkeypatch):
    _patch_history(
        monkeypatch,
        _FakeHistoryService("# ok", {"id": 1}, raise_gen=True),
    )
    with pytest.raises(HTTPException) as exc:
        export_endpoint.export_history_report("1", format="md", db_manager=object())
    assert exc.value.status_code == 500
    assert exc.value.detail["error"] == "generation_failed"
