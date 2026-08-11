# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Import-boundary and compatibility tests for runtime assembly."""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _import_targets_from_source(source: str, *, module_name: str) -> set[str]:
    """Return absolute import targets, including from-import member paths."""
    tree = ast.parse(source)
    package_parts = module_name.split(".")[:-1]
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue

        if node.level:
            parent_count = node.level - 1
            module_parts = package_parts[: len(package_parts) - parent_count]
        else:
            module_parts = []
        if node.module:
            module_parts.extend(node.module.split("."))

        imported_module = ".".join(module_parts)
        if imported_module:
            targets.add(imported_module)
        for alias in node.names:
            if alias.name == "*":
                continue
            targets.add(".".join([*module_parts, *alias.name.split(".")]))
    return targets


def _module_import_targets(relative_path: str) -> set[str]:
    """Return all absolute import targets found anywhere in a source file."""
    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / relative_path).read_text(encoding="utf-8")
    module_name = ".".join(Path(relative_path).with_suffix("").parts)
    return _import_targets_from_source(source, module_name=module_name)


def test_native_adapter_does_not_import_factory():
    """Guard the resolved factory <-> native adapter import cycle."""
    targets = _module_import_targets("src/agent/runtime/native_adapter.py")
    assert "src.agent.factory" not in targets
    assert "src.agent.runtime_assembly" in targets


def test_runtime_assembly_leaf_does_not_import_factory_or_native_adapter():
    """Keep the runtime assembly leaf free of both higher-level modules."""
    targets = _module_import_targets("src/agent/runtime_assembly.py")
    assert "src.agent.factory" not in targets
    assert "src.agent.runtime.native_adapter" not in targets


def test_factory_reexports_runtime_assembly_entrypoints():
    """Preserve both public factory import paths as leaf function identities."""
    from src.agent import factory, runtime_assembly

    assert factory.get_tool_registry is runtime_assembly.get_tool_registry
    assert factory.build_agent_executor is runtime_assembly.build_agent_executor


@pytest.mark.parametrize(
    ("source", "module_name", "expected"),
    [
        (
            "from src.agent import factory\n",
            "src.agent.runtime.native_adapter",
            "src.agent.factory",
        ),
        (
            "from src.agent.runtime import native_adapter\n",
            "src.agent.runtime_assembly",
            "src.agent.runtime.native_adapter",
        ),
        (
            "from .. import factory\n",
            "src.agent.runtime.native_adapter",
            "src.agent.factory",
        ),
        (
            "from .runtime import native_adapter\n",
            "src.agent.runtime_assembly",
            "src.agent.runtime.native_adapter",
        ),
    ],
)
def test_import_guard_resolves_from_import_module_members(
    source: str,
    module_name: str,
    expected: str,
):
    """Prevent package-member and relative imports from bypassing the guard."""
    assert expected in _import_targets_from_source(source, module_name=module_name)


def test_factory_forwarded_patches_restore_leaf_state():
    """Keep nested legacy patches and cache resets bound to one leaf state."""
    from src.agent import factory, runtime_assembly

    original_registry = runtime_assembly._TOOL_REGISTRY
    original_builder = runtime_assembly.build_agent_executor
    registry_marker = object()
    outer_builder = MagicMock(name="outer_builder")
    inner_builder = MagicMock(name="inner_builder")
    try:
        assert "_TOOL_REGISTRY" not in vars(factory)
        assert "build_agent_executor" not in vars(factory)
        factory._TOOL_REGISTRY = registry_marker

        with patch.object(factory, "_TOOL_REGISTRY", None):
            assert runtime_assembly._TOOL_REGISTRY is None
        assert factory._TOOL_REGISTRY is registry_marker
        assert runtime_assembly._TOOL_REGISTRY is registry_marker

        with patch.object(factory, "build_agent_executor", outer_builder):
            assert runtime_assembly.build_agent_executor is outer_builder
            with patch.object(factory, "build_agent_executor", inner_builder):
                assert runtime_assembly.build_agent_executor is inner_builder
            assert runtime_assembly.build_agent_executor is outer_builder
        assert runtime_assembly.build_agent_executor is original_builder
    finally:
        factory._TOOL_REGISTRY = original_registry
        factory.build_agent_executor = original_builder


def test_factory_runtime_signature_keeps_eager_annotations():
    """Preserve the retained factory function's annotation metadata."""
    from typing import List, Optional

    from src.agent import factory
    from src.config import Config

    assert factory.build_agent_runtime.__annotations__ == {
        "config": Optional[Config],
        "skills": Optional[List[str]],
    }


def test_strict_explicit_skill_selection_rejects_runtime_disappearance():
    """Scheduled research must never replace a missing Persona with defaults."""
    from src.agent.runtime_assembly import _resolve_selected_skill_ids

    with pytest.raises(
        ValueError,
        match="Unknown explicitly selected Agent skill ids: persona_tail_risk",
    ):
        _resolve_selected_skill_ids(
            requested_skills=["persona_tail_risk"],
            configured_skills=None,
            default_skills=["bull_trend"],
            available_skill_ids={"bull_trend"},
            strict_skill_selection=True,
        )


def test_non_strict_unknown_skill_selection_keeps_legacy_fallback():
    """Existing callers retain the current permissive selection behavior."""
    from src.agent.runtime_assembly import _resolve_selected_skill_ids

    selected, explicit = _resolve_selected_skill_ids(
        requested_skills=["persona_tail_risk"],
        configured_skills=None,
        default_skills=["bull_trend"],
        available_skill_ids={"bull_trend"},
    )

    assert selected == ["bull_trend"]
    assert explicit is False


def _optional_tool_declarations(registry):
    _generation, _entries, declarations = registry.capability_inventory_snapshot()
    return {declaration.name: declaration for declaration in declarations}


@pytest.mark.parametrize(
    "outcome, expected_reason",
    [
        ("raises", "construction_failed"),
        ("returns_none", "construction_produced_no_tool"),
    ],
)
def test_configured_optional_tool_absence_keeps_construction_provenance(
    outcome,
    expected_reason,
):
    """A configured factory that produced nothing is never ``not_registered``."""
    from src.agent import runtime_assembly
    from src.agent.tools import valuation_tools

    def _build(config, **kwargs):
        if outcome == "raises":
            raise RuntimeError("valuation dependency unavailable")
        return None

    original_registry = runtime_assembly._TOOL_REGISTRY
    services = MagicMock()
    services.config = MagicMock(valuation_agent_tool_enabled=True)
    try:
        runtime_assembly._TOOL_REGISTRY = None
        with patch.object(valuation_tools, "build_valuation_tool", _build), patch(
            "src.application_services.get_application_services",
            return_value=services,
        ):
            registry = runtime_assembly.get_tool_registry()
    finally:
        runtime_assembly._TOOL_REGISTRY = original_registry

    declaration = _optional_tool_declarations(registry)[
        valuation_tools.VALUATION_TOOL_NAME
    ]
    assert valuation_tools.VALUATION_TOOL_NAME not in registry
    assert declaration.configured is True
    assert declaration.dependency_ready is False
    assert declaration.reason_code == expected_reason
