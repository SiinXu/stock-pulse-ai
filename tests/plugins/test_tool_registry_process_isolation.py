# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Process ToolRegistry isolation vs builtin.web_search plugin load.

The PR #1470 backend-gate failure
``test_each_builtin_strategy_loads_via_plugin_path``
(``native_registration_conflict`` on ``builtin.web_search``) is test isolation
drift, not a field-trust product defect. The proven same-process order is:

1. ``test_get_tool_registry_loads_category_map_and_refreshes_cache``
2. ``test_default_production_registry_has_supported_declared_policies``
3. ``test_each_builtin_strategy_loads_via_plugin_path``
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.agent.runtime_assembly import (
    get_tool_registry,
    peek_process_tool_registry,
    reset_process_tool_registry_for_tests,
)
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        agent_skill_dir=None,
        agent_skills=None,
        agent_skill_routing="auto",
        kronos_enabled=False,
        ocr_agent_tool_enabled=False,
    )


def _reset_skill_manager_cache() -> None:
    import src.agent.runtime_assembly as runtime_assembly

    runtime_assembly._SKILL_MANAGER_PROTOTYPE = None
    runtime_assembly._SKILL_MANAGER_CUSTOM_DIR = runtime_assembly._SENTINEL
    runtime_assembly._SKILL_MANAGER_CATALOG_TOKEN = runtime_assembly._SENTINEL
    runtime_assembly._SKILL_MANAGER_CATALOG_GENERATION = -1


def test_plugin_path_survives_timeout_cache_restore_then_surface_policies() -> None:
    """Exact combination-order counterexample from PR #1470 CI.

    Pytest runs the three tests as separate items. The plugin-test autouse
    historically reset only the composition root, not the process ToolRegistry
    cache. This regression applies that same root-only reset before the plugin
    path so a timeout-cache leak would still fail, and the timeout cleanup
    must be what keeps builtin.web_search deterministic.
    """

    from tests.agent.test_tool_timeout import (
        test_get_tool_registry_loads_category_map_and_refreshes_cache,
    )
    from tests.agent.tools.test_agent_tool_surface import (
        test_default_production_registry_has_supported_declared_policies,
    )
    from tests.plugins.test_analysis_strategy_plugins import (
        test_each_builtin_strategy_loads_via_plugin_path,
    )

    monkeypatch = pytest.MonkeyPatch()
    try:
        test_get_tool_registry_loads_category_map_and_refreshes_cache(monkeypatch)
    finally:
        monkeypatch.undo()

    test_default_production_registry_has_supported_declared_policies()
    reset_application_services()
    _reset_skill_manager_cache()
    test_each_builtin_strategy_loads_via_plugin_path()


def test_plugin_autouse_clears_safety_net_after_orphaned_cache_restore() -> None:
    """Plugin isolation must survive the pre-fix timeout cache restore."""

    import src.agent.runtime_assembly as runtime_assembly
    from tests.plugins.test_analysis_strategy_plugins import (
        test_each_builtin_strategy_loads_via_plugin_path,
    )

    reset_application_services()
    reset_process_tool_registry_for_tests()

    first = get_tool_registry()
    assert first.get("search_stock_news") is not None
    runtime_assembly._TOOL_REGISTRY = None
    runtime_assembly._TOOL_REGISTRY_BUILDING = None

    rebuilt = get_tool_registry()
    assert rebuilt is not first
    assert rebuilt.get("search_stock_news") is not None

    reset_application_services()
    reset_process_tool_registry_for_tests()
    _reset_skill_manager_cache()
    test_each_builtin_strategy_loads_via_plugin_path()


def test_safety_net_occupancy_without_plugin_ownership_stays_fail_closed() -> None:
    """Empty-root safety-net leftovers still conflict; isolation must clear them.

    Isolation must not hide this by making ``contains()`` ignore occupancy of
    the same ``ALL_SEARCH_TOOLS`` objects. Fail-closed remains the product
    contract for leftover safety-net names without plugin ownership.
    """

    reset_application_services()
    reset_process_tool_registry_for_tests()
    empty = ApplicationServices(
        config=_config(),
        builtin_plugins=(),
        plugins_dir="",
    )
    set_application_services(empty)
    registry = get_tool_registry()
    assert registry.get("search_stock_news") is not None
    assert registry.get("search_comprehensive_intel") is not None
    assert peek_process_tool_registry() is registry

    services = ApplicationServices(config=_config(), plugins_dir="")
    set_application_services(services)
    web_search = next(
        result
        for result in services.plugin_load_results
        if result.plugin_id == "builtin.web_search"
    )
    assert web_search.success is False
    assert web_search.error_code == "native_registration_conflict"
