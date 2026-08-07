# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for official examples that complete the six-point surface.

Covers packages under ``examples/plugins/`` that lacked a runnable reference
before the plugin developer guide delivery: analysis strategy, agent tool
(load-and-register only; issue #539), report template, and event hook.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Iterator

import pytest

import src.agent.runtime_assembly as runtime_assembly
from src.agent.runtime_assembly import get_tool_registry
from src.analyzer import AnalysisResult
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.config import Config
from src.plugins import dispatch_analysis_event
from src.services.report_renderer import render_plugin_template


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES_ROOT = _REPOSITORY_ROOT / "examples" / "plugins"
_EXAMPLE_EVENT_HOOK = _EXAMPLES_ROOT / "example-event-hook"
_EXAMPLE_REPORT_TEMPLATE = _EXAMPLES_ROOT / "example-report-template"
_EXAMPLE_AGENT_TOOL = _EXAMPLES_ROOT / "example-agent-tool"
_EXAMPLE_ANALYSIS_STRATEGY = _EXAMPLES_ROOT / "example-analysis-strategy"


@pytest.fixture(autouse=True)
def _clean_application_root_and_skill_cache() -> Iterator[None]:
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


def _copy_example(root: Path, source: Path) -> Path:
    target = root / source.name
    shutil.copytree(source, target)
    return target


def _install_single_example(tmp_path: Path, source: Path) -> ApplicationServices:
    _copy_example(tmp_path, source)
    services = ApplicationServices(
        config=Config(stock_list=[]),
        plugins_dir=str(tmp_path),
    )
    set_application_services(services)
    return services


def _analysis_result() -> AnalysisResult:
    return AnalysisResult(
        code="600519",
        name="Kweichow Moutai",
        sentiment_score=72,
        trend_prediction="Bullish",
        operation_advice="Hold",
        analysis_summary="Stable outlook.",
        report_language="en",
    )


def test_example_packages_ship_manifest_and_entrypoint() -> None:
    for package in (
        _EXAMPLE_EVENT_HOOK,
        _EXAMPLE_REPORT_TEMPLATE,
        _EXAMPLE_AGENT_TOOL,
        _EXAMPLE_ANALYSIS_STRATEGY,
    ):
        assert (package / "manifest.json").is_file(), package
        assert (package / "plugin.py").is_file(), package
        assert (package / "README.md").is_file(), package


def test_example_event_hook_loads_and_receives_analysis_events(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    services = _install_single_example(tmp_path, _EXAMPLE_EVENT_HOOK)
    try:
        loads = {result.plugin_id: result for result in services.plugin_load_results}
        assert loads["example-event-hook"].success is True
        assert loads["example-event-hook"].state == "enabled"

        hook_ids = {
            registration.registration_id
            for registration in services.plugin_manager.enabled_registrations(
                "event_hook"
            )
        }
        assert "example-analysis-lifecycle" in hook_ids

        with caplog.at_level(logging.INFO, logger="plugin"):
            # Logger name is the example module path after load.
            pass
        with caplog.at_level(logging.INFO):
            dispatch_analysis_event(
                "analysis.started",
                task_id="gap-task-1",
                trace_id="gap-trace-1",
                stock_code="600519",
                trigger_source="contract-test",
            )

        assert "Example event hook received" in caplog.text
        assert "analysis.started" in caplog.text
        assert "gap-task-1" in caplog.text

        disable = services.plugin_manager.disable("example-event-hook")
        assert disable.success is True
        assert services.plugin_manager.enabled_registrations("event_hook") == ()
    finally:
        services.close()


def test_example_report_template_loads_and_renders(tmp_path: Path) -> None:
    services = _install_single_example(tmp_path, _EXAMPLE_REPORT_TEMPLATE)
    try:
        loads = {result.plugin_id: result for result in services.plugin_load_results}
        assert loads["example-report-template"].success is True
        assert loads["example-report-template"].state == "enabled"

        rendered = render_plugin_template(
            "markdown",
            [_analysis_result()],
            report_date="2026-07-24",
        )
        assert rendered == (
            "# Plugin report for 2026-07-24\n\n"
            "- Kweichow Moutai (600519): Hold"
        )

        disable = services.plugin_manager.disable("example-report-template")
        assert disable.success is True
        assert (
            render_plugin_template(
                "markdown",
                [_analysis_result()],
                report_date="2026-07-24",
            )
            is None
        )
    finally:
        services.close()


def test_example_agent_tool_loads_registers_and_invokes_handler_only(
    tmp_path: Path,
) -> None:
    """Prove load + ToolRegistry registration; not a live-agent sandbox claim.

    Issue #539 gates hardened ToolSurface execution for external agent tools.
    """

    services = _install_single_example(tmp_path, _EXAMPLE_AGENT_TOOL)
    try:
        loads = {result.plugin_id: result for result in services.plugin_load_results}
        assert loads["example-agent-tool"].success is True
        assert loads["example-agent-tool"].state == "enabled"

        registry = get_tool_registry()
        tool = registry.get("example_echo")
        assert tool is not None
        assert tool.name == "example_echo"
        assert tool.enforce_contract is True
        assert tool.policy.policy_status == "declared"
        assert tool.policy.read_only is True

        # Direct handler call is allowed in contract tests; do not run an agent.
        assert tool.handler(message="hello") == {"echo": "hello"}

        disable = services.plugin_manager.disable("example-agent-tool")
        assert disable.success is True
        assert get_tool_registry().get("example_echo") is None
    finally:
        services.close()


def test_example_analysis_strategy_loads_into_process_catalog(
    tmp_path: Path,
) -> None:
    services = _install_single_example(tmp_path, _EXAMPLE_ANALYSIS_STRATEGY)
    try:
        loads = {result.plugin_id: result for result in services.plugin_load_results}
        assert loads["example-analysis-strategy"].success is True
        assert loads["example-analysis-strategy"].state == "enabled"

        snapshot = services.analysis_strategy_snapshot()
        by_name = {
            entry.definition.name: entry for entry in snapshot.registrations
        }
        assert "example-quality-compounder" in by_name
        entry = by_name["example-quality-compounder"]
        assert entry.plugin_id == "example-analysis-strategy"
        assert entry.definition.display_name == "Example Quality Compounder"
        assert "durable cash generation" in entry.definition.instructions

        disable = services.plugin_manager.disable("example-analysis-strategy")
        assert disable.success is True
        remaining = {
            entry.definition.name
            for entry in services.analysis_strategy_snapshot().registrations
        }
        assert "example-quality-compounder" not in remaining
    finally:
        services.close()


def test_gap_examples_do_not_import_private_plugin_submodules() -> None:
    """Authors should use the package root, not ``src.plugins.*`` internals."""

    import ast

    for package in (
        _EXAMPLE_EVENT_HOOK,
        _EXAMPLE_REPORT_TEMPLATE,
        _EXAMPLE_AGENT_TOOL,
        _EXAMPLE_ANALYSIS_STRATEGY,
    ):
        source = (package / "plugin.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert not node.module.startswith(
                    "src.plugins."
                ), f"{package.name} imports private module {node.module}"
