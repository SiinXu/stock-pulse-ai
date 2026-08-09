# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused owner-consistency tests for the capability inventory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from src.capability_registry import collect_capability_records
from src.agent.tools.registry import (
    ToolDefinition,
    ToolInventoryDeclaration,
    ToolRegistry,
)

NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


class _DataRuntime:
    def __init__(self, generation: int = 1, active: tuple[Any, ...] = ()) -> None:
        self.generation = generation
        self.active = active
        self.reads = 0

    def active_provider_snapshot(self) -> tuple[int, tuple[Any, ...]]:
        self.reads += 1
        return self.generation, self.active


def _active_provider(
    provider_id: str,
    *,
    markets: tuple[str, ...],
    capabilities: tuple[str, ...],
) -> Any:
    registration = SimpleNamespace(
        provider_id=provider_id,
        markets=frozenset(markets),
        capabilities=frozenset(capabilities),
    )
    return SimpleNamespace(
        registration=registration,
        provider=SimpleNamespace(name=f"{provider_id.title()}Fetcher"),
    )


@dataclass
class _Policy:
    permissions: list[str] = field(default_factory=list)


@dataclass
class _Tool:
    name: str
    policy: _Policy = field(default_factory=_Policy)


class _ToolRegistry:
    def __init__(
        self,
        tools: tuple[_Tool, ...] = (),
        generation: int = 1,
        declarations: tuple[Any, ...] = (),
    ) -> None:
        self.tools = tools
        self.generation = generation
        self.declarations = declarations
        self.reads = 0

    def capability_inventory_snapshot(self) -> tuple[int, tuple[_Tool, ...], tuple[Any, ...]]:
        self.reads += 1
        return self.generation, self.tools, self.declarations


class _FailingToolRegistry:
    def definition_snapshot(self) -> Any:
        raise OSError("registry unavailable")


class _DriftingToolRegistry:
    def capability_inventory_snapshot(self) -> Any:
        raise RuntimeError("tool registry generation drift")


@dataclass
class _Manifest:
    id: str
    name: str
    version: str = "1.0.0"


@dataclass
class _PluginSnapshot:
    manifest: _Manifest
    state: str = "enabled"
    desired_enabled: bool = True


@dataclass
class _Registration:
    plugin_id: str
    extension_point: str
    registration_id: str
    contract_version: str = "1"


class _PluginManager:
    def __init__(
        self,
        lifecycle: tuple[_PluginSnapshot, ...] = (),
        registrations: tuple[_Registration, ...] = (),
        generation: str = "agent_tool:2",
    ) -> None:
        self.lifecycle = lifecycle
        self.registrations = registrations
        self.generation = generation
        self.reads = 0

    def capability_inventory_snapshot(
        self,
    ) -> tuple[str, tuple[_PluginSnapshot, ...], tuple[_Registration, ...]]:
        self.reads += 1
        return self.generation, self.lifecycle, self.registrations


def _collect(**kwargs: Any):
    return collect_capability_records(clock=lambda: NOW, **kwargs)


def _by_id(snapshot: Any) -> dict[str, Any]:
    return {record.capability_id: record for record in snapshot.items}


def test_empty_data_owner_does_not_fabricate_catalog_or_executability() -> None:
    runtime = _DataRuntime(generation=4)
    snapshot = _collect(data_provider_runtime=runtime, domains=("data",))

    assert snapshot.items == ()
    assert snapshot.sources[0].state == "ok"
    assert snapshot.sources[0].generation == "4"
    assert runtime.reads == 1


def test_live_provider_appears_and_unload_disappears_at_new_generation() -> None:
    runtime = _DataRuntime(
        generation=7,
        active=(_active_provider("demo", markets=("cn",), capabilities=("daily",)),),
    )
    first = _collect(data_provider_runtime=runtime, domains=("data",))
    records = _by_id(first)

    assert records["data.provider:demo"].markets == ("cn",)
    assert records["data.provider:demo"].executable is None
    assert records["data.method:daily"].provider == "demo"

    runtime.generation = 8
    runtime.active = ()
    second = _collect(data_provider_runtime=runtime, domains=("data",))
    assert second.items == ()
    assert second.sources[0].generation == "8"


def test_source_failure_is_explicit_partial_not_plausible_empty_success() -> None:
    snapshot = _collect(tool_registry=_FailingToolRegistry(), domains=("tool",))

    assert snapshot.partial is True
    assert snapshot.items == ()
    assert snapshot.sources[0].state == "error"
    assert snapshot.sources[0].error_code == "tool_source_unavailable"


def test_generation_drift_is_distinct_from_source_failure() -> None:
    snapshot = _collect(tool_registry=_DriftingToolRegistry(), domains=("tool",))

    assert snapshot.partial is True
    assert snapshot.items == ()
    assert snapshot.sources[0].state == "generation_drift"
    assert snapshot.sources[0].error_code == "tool_generation_drift"


def test_tools_use_one_owner_snapshot_and_keep_execution_unknown() -> None:
    registry = _ToolRegistry(
        (_Tool("parse_financial_pdf", _Policy(["multimodal:read"])),),
        generation=12,
    )
    snapshot = _collect(tool_registry=registry, domains=("tool",))
    record = snapshot.items[0]

    assert registry.reads == 1
    assert record.capability_id == "tool:parse_financial_pdf"
    assert record.registered is True
    assert record.grantable is None
    assert record.executable is None
    assert record.scopes == ("multimodal:read",)
    assert record.source_generation == "12"


def test_partial_optional_group_reports_each_missing_member() -> None:
    declarations = (
        SimpleNamespace(
            name="parse_financial_pdf", configured=True, dependency_ready=None,
            scopes=("multimodal:read",), reason_code=None,
        ),
        SimpleNamespace(
            name="read_price_chart", configured=True, dependency_ready=None,
            scopes=("multimodal:read",), reason_code=None,
        ),
    )
    registry = _ToolRegistry(
        (_Tool("parse_financial_pdf", _Policy(["multimodal:read"])),),
        declarations=declarations,
    )
    records = _by_id(_collect(tool_registry=registry, domains=("tool",)))

    assert records["tool:parse_financial_pdf"].registered is True
    missing = records["tool:read_price_chart"]
    assert missing.registered is False
    assert missing.configured is True
    assert missing.executable is False
    assert missing.reason_code == "not_registered"


def test_live_tool_owner_registration_and_unregistration_advance_generation() -> None:
    registry = ToolRegistry()
    registry.declare_inventory_tool(ToolInventoryDeclaration(name="demo_tool"))
    missing = _collect(tool_registry=registry, domains=("tool",))
    missing_record = _by_id(missing)["tool:demo_tool"]
    assert missing_record.registered is False

    registry.register(ToolDefinition("demo_tool", "demo", [], lambda: None))
    active = _collect(tool_registry=registry, domains=("tool",))
    active_record = _by_id(active)["tool:demo_tool"]
    assert active_record.registered is True
    assert active.sources[0].generation != missing.sources[0].generation

    registry.unregister("demo_tool")
    unloaded = _collect(tool_registry=registry, domains=("tool",))
    unloaded_record = _by_id(unloaded)["tool:demo_tool"]
    assert unloaded_record.registered is False
    assert unloaded.sources[0].generation != active.sources[0].generation


def test_plugin_lifecycle_is_not_a_contributed_capability() -> None:
    manager = _PluginManager(
        lifecycle=(_PluginSnapshot(_Manifest("demo.plugin", "Demo")),),
    )
    snapshot = _collect(plugin_manager=manager, domains=("extension",))
    record = snapshot.items[0]

    assert manager.reads == 1
    assert record.capability_type == "plugin_lifecycle"
    assert record.executable is False
    assert record.reason_code == "lifecycle_not_capability"


def test_extension_contribution_is_separate_and_execution_unknown() -> None:
    manager = _PluginManager(
        lifecycle=(_PluginSnapshot(_Manifest("demo.plugin", "Demo")),),
        registrations=(
            _Registration("demo.plugin", "agent_tool", "demo_tool", "2"),
        ),
    )
    snapshot = _collect(plugin_manager=manager, domains=("extension",))
    records = _by_id(snapshot)
    contribution = records["extension.registration:agent_tool:demo_tool"]

    assert contribution.capability_type == "extension_registration"
    assert contribution.dependencies == ("agent_tool",)
    assert contribution.version == "2"
    assert contribution.executable is None


def test_domain_filter_rejects_unknown_or_empty() -> None:
    with pytest.raises(ValueError, match="unsupported capability domains"):
        _collect(domains=("data", "nope"))
    with pytest.raises(ValueError, match="unsupported capability domains"):
        _collect(domains=())
