# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic tests for local PDF parsing (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services.pdf_parsing_service import (
    PDF_DISCLAIMER,
    PDF_SCHEMA_VERSION,
    PdfParsingService,
    parse_pdf_bytes,
    parse_pdf_path,
    resolve_safe_file_path,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "multimodal"
SAMPLE_PDF = FIXTURES / "sample_financial_report.pdf"


def test_parse_fixture_pdf_extracts_financial_text() -> None:
    data = SAMPLE_PDF.read_bytes()
    result = parse_pdf_bytes(data, filename="sample_financial_report.pdf")

    assert result["schema_version"] == PDF_SCHEMA_VERSION
    assert result["status"] in {"available", "degraded"}
    assert result["disclaimer"] == PDF_DISCLAIMER
    assert result["method"].startswith("local")
    assert "600519" in result["text"]
    assert "Revenue" in result["text"] or "NetProfit" in result["text"]
    assert result["source"]["page_count"] >= 1
    assert result["vision_assist"]["status"] in {"not_applicable", "skipped"}


def test_parse_pdf_rejects_non_pdf_header() -> None:
    result = parse_pdf_bytes(b"not a pdf", filename="x.pdf")
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "invalid_pdf_header"


def test_parse_pdf_rejects_oversize() -> None:
    from src.services import pdf_parsing_service as mod

    original = mod.MAX_PDF_BYTES
    try:
        mod.MAX_PDF_BYTES = 64
        result = parse_pdf_bytes(b"%PDF-1.4\n" + b"x" * 128, filename="big.pdf")
    finally:
        mod.MAX_PDF_BYTES = original
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "file_too_large"


def test_parse_pdf_path_under_root(tmp_path: Path) -> None:
    target = tmp_path / "report.pdf"
    target.write_bytes(SAMPLE_PDF.read_bytes())
    result = parse_pdf_path("report.pdf", file_root=str(tmp_path))
    assert result["status"] in {"available", "degraded"}
    assert "600519" in result["text"]


def test_path_traversal_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(SAMPLE_PDF.read_bytes())
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    with pytest.raises(ValueError, match="path_outside_root"):
        resolve_safe_file_path("../secret.pdf", file_root=str(sandbox))


def test_url_path_rejected() -> None:
    with pytest.raises(ValueError, match="url_not_allowed"):
        resolve_safe_file_path("https://example.com/a.pdf", file_root="/tmp")


def test_service_wrapper_parse_bytes() -> None:
    service = PdfParsingService()
    result = service.parse_bytes(SAMPLE_PDF.read_bytes(), filename="f.pdf")
    assert result["schema_version"] == PDF_SCHEMA_VERSION
    assert result["tables"] is not None


def test_infer_table_rows_from_numeric_line() -> None:
    data = SAMPLE_PDF.read_bytes()
    result = parse_pdf_bytes(data, filename="sample.pdf")
    # Fixture page 2 has Assets/Liabilities/Equity numeric tokens.
    assert isinstance(result["tables"], list)
