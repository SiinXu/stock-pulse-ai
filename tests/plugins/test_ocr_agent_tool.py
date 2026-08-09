# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Registration tests for the built-in offline OCR plugin (issue #196)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.agent.tools.ocr_tools import OCR_TOOL_NAME
from src.agent.tools.registry import ToolRegistry
from src.plugins import PluginManager, build_agent_tool_extension_registry
from src.plugins.builtin import get_configured_builtin_plugins
from src.plugins.builtin.ocr import OcrAgentToolPlugin
from src.services.ocr_extraction_service import OcrExtractionService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ocr"


def _config(root, *, enabled=True):
    return SimpleNamespace(
        ocr_agent_tool_enabled=enabled,
        ocr_file_root=str(root) if root is not None else None,
        multimodal_file_root=None,
        ocr_langs="eng",
        ocr_timeout_seconds=30,
        kronos_enabled=False,
    )


def test_disabled_configuration_is_absent_from_builtin_catalog() -> None:
    plugins = get_configured_builtin_plugins(_config(None, enabled=False))
    assert all(not isinstance(plugin, OcrAgentToolPlugin) for plugin in plugins)


def test_enabled_configuration_includes_ocr_plugin(tmp_path: Path) -> None:
    plugins = get_configured_builtin_plugins(_config(tmp_path, enabled=True))
    assert any(isinstance(plugin, OcrAgentToolPlugin) for plugin in plugins)


def test_plugin_registers_agent_tool_when_ready(tmp_path: Path) -> None:
    (tmp_path / "statement.png").write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())

    def factory() -> OcrExtractionService:
        return OcrExtractionService(file_root=str(tmp_path), engine=lambda *_a, **_k: "AAPL 120")

    registry = ToolRegistry()
    manager = PluginManager(application_version="3.26.3", registry=build_agent_tool_extension_registry(registry))
    plugin = OcrAgentToolPlugin(_config(tmp_path, enabled=True), service_factory=factory, require_engine_at_register=False)
    assert manager.register(plugin, source="builtin").success is True
    assert manager.load(plugin.manifest.id).success is True
    tool = registry.get(OCR_TOOL_NAME)
    assert tool is not None
    payload = tool.handler(file_path="statement.png")
    assert payload["status"] == "available"
    assert "AAPL" in payload["text"]
