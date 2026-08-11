# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for default-off offline OCR Agent Tool (issue #196)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agent.tools.ocr_tools import OCR_TOOL_NAME, build_ocr_tool, register_ocr_tools
from src.agent.tools.registry import ToolRegistry, validate_tool_capability_contract
from src.services.ocr_extraction_service import OCR_SCHEMA_VERSION, OcrExtractionService

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ocr"


class _SilentLocalProcessRecorder:
    def record_attempt(self, **fields):
        del fields
        return None

    def record_completion(self, **fields):
        del fields
        return None


@pytest.fixture(autouse=True)
def _silent_local_process_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.services.local_process_audit import LocalProcessAuditor

    auditor = LocalProcessAuditor(recorder=_SilentLocalProcessRecorder())
    monkeypatch.setattr(
        "src.services.local_process_audit.get_local_process_auditor",
        lambda: auditor,
    )


def test_build_ocr_tool_default_off() -> None:
    assert build_ocr_tool(SimpleNamespace(ocr_agent_tool_enabled=False, ocr_file_root=None, multimodal_file_root=None)) is None


def test_build_ocr_tool_requires_file_root() -> None:
    assert build_ocr_tool(
        SimpleNamespace(ocr_agent_tool_enabled=True, ocr_file_root="", multimodal_file_root=None, ocr_langs="eng", ocr_timeout_seconds=30),
        require_engine_at_register=False,
    ) is None


def test_build_ocr_tool_missing_dependencies_skips_register(tmp_path: Path) -> None:
    assert build_ocr_tool(
        SimpleNamespace(ocr_agent_tool_enabled=True, ocr_file_root=str(tmp_path), multimodal_file_root=None, ocr_langs="eng", ocr_timeout_seconds=30),
        dependency_probe=lambda _n: False,
        require_engine_at_register=True,
    ) is None


def test_build_and_register_ocr_tool_when_enabled(tmp_path: Path) -> None:
    (tmp_path / "statement.png").write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())

    def factory() -> OcrExtractionService:
        return OcrExtractionService(file_root=str(tmp_path), langs="eng", engine=lambda *_a, **_k: "AAPL 198.50\n600519 1650.00")

    tool = build_ocr_tool(
        SimpleNamespace(ocr_agent_tool_enabled=True, ocr_file_root=str(tmp_path), multimodal_file_root=None, ocr_langs="eng", ocr_timeout_seconds=30),
        service_factory=factory,
        require_engine_at_register=False,
    )
    assert tool is not None
    assert tool.name == OCR_TOOL_NAME
    assert validate_tool_capability_contract(tool) is None
    registry = ToolRegistry()
    names = register_ocr_tools(
        registry,
        SimpleNamespace(ocr_agent_tool_enabled=True, ocr_file_root=str(tmp_path), multimodal_file_root=None, ocr_langs="eng", ocr_timeout_seconds=30),
        service_factory=factory,
        require_engine_at_register=False,
    )
    assert names == [OCR_TOOL_NAME]
    payload = tool.handler(file_path="statement.png")
    assert payload["schema_version"] == OCR_SCHEMA_VERSION
    assert payload["status"] == "available"
    assert "AAPL" in payload["text"]
    assert payload["content"]["instructions_authoritative"] is False
    assert payload["privacy"]["zero_remote_egress_requires"] == "LOCAL_ONLY_MODE=true"


def test_file_root_falls_back_to_multimodal_root(tmp_path: Path) -> None:
    def factory() -> OcrExtractionService:
        return OcrExtractionService(file_root=str(tmp_path), engine=lambda *_a, **_k: "ok")

    tool = build_ocr_tool(
        SimpleNamespace(ocr_agent_tool_enabled=True, ocr_file_root=None, multimodal_file_root=str(tmp_path), ocr_langs="chi_sim+eng", ocr_timeout_seconds=30),
        service_factory=factory,
        require_engine_at_register=False,
    )
    assert tool is not None
