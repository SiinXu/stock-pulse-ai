# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Load, permission, ToolSurface deny, and citability for the alt-data example plugin."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterator

import pytest

import src.agent.runtime_assembly as runtime_assembly
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.runtime_assembly import get_tool_registry
from src.agent.stock_scope import StockScope
from src.agent.tools.alternative_data_tools import (
    ALT_DATA_MAX_RESULT_BYTES,
    ALT_DATA_PERMISSION,
    CORPORATE_EVENTS_TOOL_NAME,
)
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.config import Config
from src.plugins import MANIFEST_PERMISSIONS_UNDECLARED
from src.services.alternative_data_governance import project_alternative_data_evidence
from tests.security_audit_test_utils import SecurityAuditRecorderStub


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE_PLUGIN = _REPOSITORY_ROOT / "examples" / "plugins" / "example-alternative-data"
_PLUGIN_ID = "stockpulse.example-alternative-data"


@pytest.fixture(autouse=True)
def _clean_application_root() -> Iterator[None]:
    reset_application_services()
    cache_state = (
        runtime_assembly._SKILL_MANAGER_PROTOTYPE,
        runtime_assembly._SKILL_MANAGER_CUSTOM_DIR,
        runtime_assembly._SKILL_MANAGER_CATALOG_TOKEN,
        runtime_assembly._SKILL_MANAGER_CATALOG_GENERATION,
    )
    runtime_assembly._SKILL_MANAGER_PROTOTYPE = None
    runtime_assembly._SKILL_MANAGER_CUSTOM_DIR = runtime_assembly._SENTINEL
    runtime_assembly._SKILL_MANAGER_CATALOG_TOKEN = runtime_assembly._SENTINEL
    runtime_assembly._SKILL_MANAGER_CATALOG_GENERATION = -1
    yield
    reset_application_services()
    (
        runtime_assembly._SKILL_MANAGER_PROTOTYPE,
        runtime_assembly._SKILL_MANAGER_CUSTOM_DIR,
        runtime_assembly._SKILL_MANAGER_CATALOG_TOKEN,
        runtime_assembly._SKILL_MANAGER_CATALOG_GENERATION,
    ) = cache_state


def _install_example(tmp_path: Path, source: Path = _EXAMPLE_PLUGIN) -> ApplicationServices:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    services = ApplicationServices(
        config=Config(stock_list=[]),
        plugins_dir=str(tmp_path),
    )
    set_application_services(services)
    return services


def test_example_plugin_ships_manifest_entrypoint_and_readme() -> None:
    assert (_EXAMPLE_PLUGIN / "manifest.json").is_file()
    assert (_EXAMPLE_PLUGIN / "plugin.py").is_file()
    assert (_EXAMPLE_PLUGIN / "README.md").is_file()
    manifest = json.loads((_EXAMPLE_PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] == _PLUGIN_ID
    assert ALT_DATA_PERMISSION in manifest["permissions"]


def test_plugin_registers_citable_corporate_events_tool(tmp_path: Path) -> None:
    services = _install_example(tmp_path)
    try:
        loads = {result.plugin_id: result for result in services.plugin_load_results}
        assert loads[_PLUGIN_ID].success is True
        assert loads[_PLUGIN_ID].state == "enabled"

        registry = get_tool_registry()
        tool = registry.get(CORPORATE_EVENTS_TOOL_NAME)
        assert tool is not None
        assert ALT_DATA_PERMISSION in tool.policy.permissions
        assert tool.enforce_contract is True

        session = BoundToolSession(
            registry,
            execution_id="alt-data-plugin-e2e",
            allowed_tools=[CORPORATE_EVENTS_TOOL_NAME],
            granted_permissions=[ALT_DATA_PERMISSION],
            stock_scope=StockScope(
                expected_stock_code="600519",
                allowed_stock_codes={"600519"},
            ),
            backend="test",
            max_result_bytes=ALT_DATA_MAX_RESULT_BYTES,
            security_audit=SecurityAuditRecorderStub(),
        )
        result = session.execute(
            CORPORATE_EVENTS_TOOL_NAME,
            {"stock_code": "600519", "language_hint": "en"},
        )
        assert result["ok"] is True
        payload = result["result"]
        assert payload["status"] == "available"
        assert payload["authority"] == "non_authoritative"
        assert payload["role"] == "supporting_only"
        assert payload["events"]
        projection = project_alternative_data_evidence(payload)
        assert projection.evidence_items
        assert all(
            conclusion.stratum not in {"verified_fact", "decision"}
            for conclusion in projection.conclusions
        )

        disable = services.plugin_manager.disable(_PLUGIN_ID)
        assert disable.success is True
        assert get_tool_registry().get(CORPORATE_EVENTS_TOOL_NAME) is None
    finally:
        services.close()


def test_plugin_tool_denied_without_capability(tmp_path: Path) -> None:
    services = _install_example(tmp_path)
    try:
        registry = get_tool_registry()
        assert registry.get(CORPORATE_EVENTS_TOOL_NAME) is not None
        session = BoundToolSession(
            registry,
            execution_id="alt-data-plugin-deny",
            allowed_tools=[CORPORATE_EVENTS_TOOL_NAME],
            granted_permissions=[],
            stock_scope=StockScope(
                expected_stock_code="600519",
                allowed_stock_codes={"600519"},
            ),
            backend="test",
            max_result_bytes=ALT_DATA_MAX_RESULT_BYTES,
            security_audit=SecurityAuditRecorderStub(),
        )
        result = session.execute(
            CORPORATE_EVENTS_TOOL_NAME,
            {"stock_code": "600519"},
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "permission_denied"
        assert "alt_data:read" in result["error"]["details"]["missing_capabilities"]
    finally:
        services.close()


def test_undeclared_manifest_permissions_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / "example-alternative-data"
    shutil.copytree(_EXAMPLE_PLUGIN, target)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["permissions"] = []
    manifest["id"] = "stockpulse.example-alternative-data-bad-perms"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    services = ApplicationServices(
        config=Config(stock_list=[]),
        plugins_dir=str(tmp_path),
    )
    set_application_services(services)
    try:
        loads = {
            result.plugin_id: result for result in services.plugin_load_results
        }
        bad = loads["stockpulse.example-alternative-data-bad-perms"]
        assert bad.success is False
        assert bad.error_code == MANIFEST_PERMISSIONS_UNDECLARED
        assert get_tool_registry().get(CORPORATE_EVENTS_TOOL_NAME) is None
    finally:
        services.close()
