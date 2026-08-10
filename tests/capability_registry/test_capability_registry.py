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
class _Entry:
    name: str
    category: str = "data"
    scopes: tuple[str, ...] = ()
    definition_version: int = 1


class _ToolRegistry:
    def __init__(
        self,
        entries: tuple[_Entry, ...] = (),
        generation: int = 1,
        declarations: tuple[Any, ...] = (),
    ) -> None:
        self.entries = entries
        self.generation = generation
        self.declarations = declarations
        self.reads = 0

    def capability_inventory_snapshot(
        self,
    ) -> tuple[int, tuple[_Entry, ...], tuple[Any, ...]]:
        self.reads += 1
        return self.generation, self.entries, self.declarations


class _FailingToolRegistry:
    def capability_inventory_snapshot(self) -> Any:
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
    assert records["data.method:daily"].providers == ("demo",)

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
        (_Entry("parse_financial_pdf", scopes=("multimodal:read",)),),
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
        (_Entry("parse_financial_pdf", scopes=("multimodal:read",)),),
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


# ----- Review counterexamples (PR #976 exact-head return) -----


def test_data_source_observes_the_shared_manager_and_never_builds_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counterexample 1: a fresh manager owns an unrelated provider runtime."""

    import src.agent.tools.data_tools as data_tools

    monkeypatch.setattr(
        "src.application_services.get_installed_application_services",
        lambda: None,
    )
    original = data_tools.active_fetcher_manager()
    data_tools.reset_fetcher_manager()
    try:
        absent = _collect(domains=("data",))
        assert absent.items == ()
        assert absent.partial is True
        assert absent.sources[0].state == "not_initialized"
        assert absent.sources[0].error_code == "data_runtime_not_initialized"
        # Observing the owner must not have constructed one as a side effect.
        assert data_tools.active_fetcher_manager() is None

        manager = data_tools._get_fetcher_manager()
        present = _collect(domains=("data",))
        assert present.sources[0].state == "ok"
        expected_generation, _ = manager.data_provider_runtime.active_provider_snapshot()
        assert present.sources[0].generation == str(expected_generation)
    finally:
        data_tools.reset_fetcher_manager()
        if original is not None:
            data_tools._fetcher_manager_singleton = original


def test_data_source_prefers_the_composition_root_pipeline_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pipeline's manager outranks the Agent tool manager, not a new one."""

    import src.agent.tools.data_tools as data_tools

    root_runtime = _DataRuntime(
        generation=77,
        active=(_active_provider("root", markets=("cn",), capabilities=("daily",)),),
    )
    root_manager = SimpleNamespace(data_provider_runtime=root_runtime)
    monkeypatch.setattr(
        "src.application_services.get_installed_application_services",
        lambda: SimpleNamespace(data_fetcher_manager=root_manager),
    )
    original = data_tools.active_fetcher_manager()
    data_tools.reset_fetcher_manager()
    try:
        snapshot = _collect(domains=("data",))
    finally:
        if original is not None:
            data_tools._fetcher_manager_singleton = original

    assert snapshot.sources[0].state == "ok"
    assert snapshot.sources[0].generation == "77"
    assert _by_id(snapshot)["data.provider:root"].registered is True
    assert data_tools.active_fetcher_manager() is original


def test_mutating_a_registered_definition_cannot_change_published_scopes() -> None:
    """Counterexample 2: scopes changed while the generation stayed the same."""

    from src.agent.tools.registry import ToolPolicy

    registry = ToolRegistry()
    definition = ToolDefinition(
        "demo_tool", "demo", [], lambda: None,
        policy=ToolPolicy.declared(read_only=True, permissions=["market_data:read"]),
    )
    registry.register(definition)
    first = _collect(tool_registry=registry, domains=("tool",))

    definition.policy.permissions.append("news:read")
    second = _collect(tool_registry=registry, domains=("tool",))

    assert first.items[0].scopes == ("market_data:read",)
    assert second.items[0].scopes == first.items[0].scopes
    assert second.sources[0].generation == first.sources[0].generation

    registry.register(definition)
    third = _collect(tool_registry=registry, domains=("tool",))
    assert third.items[0].scopes == ("market_data:read", "news:read")
    assert third.sources[0].generation != first.sources[0].generation


def test_plugin_lifecycle_transition_advances_the_published_generation() -> None:
    """Counterexample 3: registered -> disabled kept the same generation."""

    from tests.plugins.test_plugin_manager import (
        _RecordingPlugin,
        _manager,
        _manifest,
    )

    manager = _manager()
    manager.register(_RecordingPlugin(_manifest("example-plugin")), source="builtin")
    manager.load("example-plugin")
    enabled = _collect(plugin_manager=manager, domains=("extension",))

    manager.disable("example-plugin")
    disabled = _collect(plugin_manager=manager, domains=("extension",))

    assert enabled.items[0].reason_code == "lifecycle_not_capability"
    assert disabled.items[0].reason_code == "plugin_not_enabled"
    assert disabled.sources[0].generation != enabled.sources[0].generation


def test_many_valid_providers_never_overflow_into_a_failed_data_source() -> None:
    """Counterexample 4: joined provider ids erased an otherwise valid source."""

    runtime = _DataRuntime(
        generation=9,
        active=tuple(
            _active_provider(
                prefix * 64, markets=("cn",), capabilities=("daily_data",),
            )
            for prefix in ("a", "b", "c")
        ),
    )
    snapshot = _collect(data_provider_runtime=runtime, domains=("data",))
    method = _by_id(snapshot)["data.method:daily_data"]

    assert snapshot.sources[0].state == "ok"
    assert snapshot.partial is False
    assert method.provider == "data_provider.runtime"
    assert method.providers == tuple(sorted(prefix * 64 for prefix in "abc"))
    assert method.provider_count == 3
    assert method.reason_code is None


def test_optional_tool_construction_failure_keeps_its_provenance() -> None:
    """Counterexample 5: a factory failure was reported as ``not_registered``."""

    registry = ToolRegistry()
    registry.declare_inventory_tool(
        ToolInventoryDeclaration(
            name="analyze_valuation",
            configured=True,
            dependency_ready=False,
            reason_code="construction_failed",
        )
    )
    record = _by_id(_collect(tool_registry=registry, domains=("tool",)))[
        "tool:analyze_valuation"
    ]

    assert record.registered is False
    assert record.configured is True
    assert record.dependency_ready is False
    assert record.reason_code == "construction_failed"
