# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for local OCR extraction (issue #196)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services.ocr_extraction_service import (
    MAX_OCR_IMAGE_BYTES,
    OCR_SCHEMA_VERSION,
    OcrExtractionService,
    assess_ocr_dependencies,
    normalize_ocr_langs,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ocr"


def test_normalize_ocr_langs_defaults_and_rejects_junk() -> None:
    assert normalize_ocr_langs(None) == "chi_sim+eng"
    assert normalize_ocr_langs(" eng ") == "eng"
    assert normalize_ocr_langs("chi_sim+eng") == "chi_sim+eng"
    assert normalize_ocr_langs("../../etc") == "chi_sim+eng"
    assert normalize_ocr_langs("a+b+c+d+e+f+g+h+i") == "chi_sim+eng"


def test_assess_ocr_dependencies_missing_python_packages() -> None:
    report = assess_ocr_dependencies(import_probe=lambda _name: False)
    assert report["ready"] is False
    assert report["reason"] == "python_deps_missing"


def test_extract_rejects_path_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())
    service = OcrExtractionService(file_root=str(root), engine=lambda *_a, **_k: "x")
    payload = service.extract_path(str(outside))
    assert payload["schema_version"] == OCR_SCHEMA_VERSION
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "path_outside_root"


def test_extract_rejects_oversized_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    huge = root / "huge.png"
    header = (FIXTURES / "sample_statement_en.png").read_bytes()[:64]
    huge.write_bytes(header + b"\x00" * (MAX_OCR_IMAGE_BYTES + 1))
    service = OcrExtractionService(file_root=str(root), engine=lambda *_a, **_k: "x")
    payload = service.extract_path("huge.png")
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "file_too_large"


def test_extract_rejects_bad_extension_and_mime(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "notes.txt").write_text("not an image", encoding="utf-8")
    (root / "spoof.png").write_bytes(b"not-a-real-png-payload!!!!")
    service = OcrExtractionService(file_root=str(root), engine=lambda *_a, **_k: "x")
    assert service.extract_path("notes.txt")["reason_code"] == "unsupported_extension"
    assert service.extract_path("spoof.png")["reason_code"] in {"mime_mismatch", "image_too_small"}


def test_extract_english_statement_with_injected_engine(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "statement.png").write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())

    def engine(image_bytes: bytes, mime_type: str, langs: str) -> str:
        assert mime_type == "image/png"
        assert langs == "eng"
        assert image_bytes.startswith(b"\x89PNG")
        return "Account Statement 2026-08-01\nAAPL  qty:120  price:198.50  value:23820.00\n600519 qty:10"

    service = OcrExtractionService(file_root=str(root), engine=engine, langs="eng")
    payload = service.extract_path("statement.png", langs="eng")
    assert payload["status"] == "available"
    assert "AAPL" in payload["text"]
    assert "600519" in payload["text"]
    assert payload["engine"] == "injected"


def test_extract_chinese_statement_fixture_with_injected_engine(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "statement_zh.png").write_bytes((FIXTURES / "sample_statement_zh.png").read_bytes())

    def engine(image_bytes: bytes, mime_type: str, langs: str) -> str:
        assert "chi_sim" in langs
        return "对账单 2026-08-01\n贵州茅台 600519 数量10 市值16500.00\n腾讯控股 00700 数量50"

    service = OcrExtractionService(file_root=str(root), engine=engine, langs="chi_sim+eng")
    payload = service.extract_path("statement_zh.png")
    assert payload["status"] == "available"
    assert "贵州茅台" in payload["text"]
    assert "600519" in payload["text"]
    assert "00700" in payload["text"]


def test_extract_timeout(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "slow.png").write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())

    def slow_engine(*_a, **_k) -> str:
        import time
        time.sleep(2)
        return "late"

    service = OcrExtractionService(file_root=str(root), engine=slow_engine, timeout_seconds=1)
    payload = service.extract_path("slow.png")
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "ocr_timeout"


def test_missing_dependencies_without_injected_engine(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "statement.png").write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())
    service = OcrExtractionService(file_root=str(root), dependency_probe=lambda _n: False)
    payload = service.extract_path("statement.png")
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "python_deps_missing"


@pytest.mark.skipif(
    assess_ocr_dependencies()["ready"] is not True,
    reason="system Tesseract + pytesseract not installed",
)
def test_real_tesseract_english_fixture_when_available(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "statement.png").write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())
    service = OcrExtractionService(file_root=str(root), langs="eng")
    payload = service.extract_path("statement.png", langs="eng")
    assert payload["status"] in {"available", "degraded"}
    if payload["status"] == "available":
        joined = payload["text"].upper()
        assert "AAPL" in joined or "600519" in joined or "STATEMENT" in joined
