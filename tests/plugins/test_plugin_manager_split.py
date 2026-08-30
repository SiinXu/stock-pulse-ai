# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Characterization of the PluginManager split contract (issue #1080).

Caller / import / patch inventory (must stay stable):

- Public package: ``from src.plugins import PluginManager, ExternalPluginLoader, ...``
- Module facade: ``from src.plugins.manager import PluginManager`` and result types
- External discovery: ``from src.plugins.loader import ExternalPluginLoader``
- No production caller patches ``src.plugins.manager`` attributes today
- Composition: ``ApplicationServices`` registers builtins, then
  ``ExternalPluginLoader.register_from_directory``, then ``load_all()``
- Batch order: ``load_all`` follows registration order; ``disable_all`` reverses it
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import src.plugins as plugins_root
import src.plugins.manager as manager_mod
from src.plugins import (
    MANIFEST_PERMISSIONS_UNDECLARED,
    ExtensionContract,
    ExtensionRegistry,
    ExternalPluginLoader,
    Plugin,
    PluginContext,
    PluginManager,
    PluginManifest,
    PluginOperationResult,
    PluginState,
    build_agent_tool_extension_contract,
)
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy, ToolRegistry
from src.plugins.loader import ExternalPluginLoader as LoaderClass
from src.plugins.loader import ExternalPluginResult
from src.plugins.manifest import parse_semver


def _manifest(
    plugin_id: str,
    *,
    min_app_version: str = "1.0.0",
    api_version: str = "1",
    permissions: list[str] | None = None,
) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": min_app_version,
            "description": "Split characterization plugin.",
            "author": "StockPulse Tests",
            "permissions": [] if permissions is None else permissions,
            "apiVersion": api_version,
        }
    )


@dataclass
class _Template:
    template_id: str


class _RecordingPlugin(Plugin):
    def __init__(
        self,
        manifest: PluginManifest,
        registration_id: str | None = None,
        *,
        fail_onload: bool = False,
    ) -> None:
        super().__init__(manifest)
        self.registration_id = registration_id
        self.fail_onload = fail_onload
        self.load_count = 0
        self.unload_count = 0

    def onload(self, context: PluginContext) -> None:
        self.load_count += 1
        if self.registration_id is not None:
            context.register(
                "report_template",
                self.registration_id,
                _Template(self.registration_id),
            )
        if self.fail_onload:
            raise RuntimeError("token=onload-secret")

    def onunload(self) -> None:
        self.unload_count += 1


def _manager() -> PluginManager:
    registry = ExtensionRegistry(
        {
            "report_template": ExtensionContract(
                identity_resolver=lambda implementation: implementation.template_id,
                validator=lambda implementation: isinstance(implementation, _Template),
            )
        }
    )
    return PluginManager(application_version="2.0.0", registry=registry)


def _tool(name: str, *, permissions: list[str]) -> ToolDefinition:
    def handler(stock_code: str) -> dict[str, str]:
        return {"stock_code": stock_code}

    return ToolDefinition(
        name=name,
        description="Split characterization tool.",
        category="test",
        parameters=[
            ToolParameter(
                name="stock_code",
                description="Stock code",
                type="string",
                required=True,
            )
        ],
        handler=handler,
        policy=ToolPolicy.declared(
            read_only=True,
            side_effects=[],
            permissions=permissions,
            scope_dimensions=["stock"],
        ),
        enforce_contract=True,
    )


class _AgentToolPlugin(Plugin):
    def __init__(
        self,
        manifest: PluginManifest,
        *,
        tool_permissions: list[str],
        tool_name: str,
    ) -> None:
        super().__init__(manifest)
        self._tool_permissions = tool_permissions
        self._tool_name = tool_name

    def onload(self, context: PluginContext) -> None:
        context.register(
            "agent_tool",
            self._tool_name,
            _tool(self._tool_name, permissions=self._tool_permissions),
        )


def test_public_import_and_patch_surface_stays_on_manager_module() -> None:
    assert plugins_root.PluginManager is manager_mod.PluginManager
    assert plugins_root.PluginOperationResult is manager_mod.PluginOperationResult
    assert plugins_root.PluginReloadResult is manager_mod.PluginReloadResult
    assert plugins_root.PluginSnapshot is manager_mod.PluginSnapshot
    assert plugins_root.PluginState is manager_mod.PluginState
    assert plugins_root.PluginSource is manager_mod.PluginSource
    assert (
        plugins_root.PluginLifecycleAuditCompletionUnavailable
        is manager_mod.PluginLifecycleAuditCompletionUnavailable
    )
    assert plugins_root.PluginSettingsUpdateResult is manager_mod.PluginSettingsUpdateResult
    assert (
        plugins_root.PluginSettingsValidationError
        is manager_mod.PluginSettingsValidationError
    )
    assert LoaderClass is ExternalPluginLoader
    assert plugins_root.ExternalPluginLoader is ExternalPluginLoader
    assert plugins_root.ExternalPluginResult is ExternalPluginResult
    assert ExternalPluginLoader.__module__ == "src.plugins.loader"
    assert PluginManager.__module__ == "src.plugins.manager"
    assert PluginOperationResult is manager_mod.PluginOperationResult
    from src.plugins.manager_types import PluginOperationResult as TypedResult
    from src.plugins.manager_types import PluginState as TypedState

    assert TypedResult is manager_mod.PluginOperationResult
    assert TypedState is manager_mod.PluginState


def test_compatibility_error_decisions_remain_fail_closed() -> None:
    manager = PluginManager(application_version="1.5.0", supported_api_versions=("1",))
    compatible = _manifest("ok")
    assert manager.compatibility_error(compatible) is None
    assert (
        manager.compatibility_error(_manifest("future", min_app_version="2.0.0"))
        == "plugin_app_version_unsupported"
    )
    assert (
        manager.compatibility_error(_manifest("api", api_version="2"))
        == "plugin_api_version_unsupported"
    )
    assert manager.compatibility_error(object()) == "plugin_manifest_invalid"  # type: ignore[arg-type]


def test_load_all_follows_registration_order_and_disable_all_reverses() -> None:
    manager = _manager()
    first = _RecordingPlugin(_manifest("first-plugin"), "first")
    second = _RecordingPlugin(_manifest("second-plugin"), "second")
    third = _RecordingPlugin(_manifest("third-plugin"), "third")
    assert manager.register(first, source="builtin").success is True
    assert manager.register(second, source="builtin").success is True
    assert manager.register(third, source="builtin").success is True
    assert manager.plugin_ids() == ("first-plugin", "second-plugin", "third-plugin")
    assert tuple(item.manifest.id for item in manager.list_snapshots()) == (
        "first-plugin",
        "second-plugin",
        "third-plugin",
    )

    loaded = manager.load_all()
    assert [result.plugin_id for result in loaded] == [
        "first-plugin",
        "second-plugin",
        "third-plugin",
    ]
    assert [result.success for result in loaded] == [True, True, True]
    assert [item.registration_id for item in manager.registrations()] == [
        "first",
        "second",
        "third",
    ]

    disabled = manager.disable_all()
    assert [result.plugin_id for result in disabled] == [
        "third-plugin",
        "second-plugin",
        "first-plugin",
    ]
    assert all(result.success for result in disabled)
    assert first.unload_count == 1
    assert second.unload_count == 1
    assert third.unload_count == 1


def test_explicit_batch_ids_keep_given_order_then_reverse_on_disable() -> None:
    manager = _manager()
    for plugin_id in ("a-plugin", "b-plugin", "c-plugin"):
        assert manager.register(
            _RecordingPlugin(_manifest(plugin_id), plugin_id),
            source="builtin",
        ).success is True

    loaded = manager.load_all(("c-plugin", "a-plugin"))
    assert [result.plugin_id for result in loaded] == ["c-plugin", "a-plugin"]
    disabled = manager.disable_all(("c-plugin", "a-plugin"))
    assert [result.plugin_id for result in disabled] == ["a-plugin", "c-plugin"]


def test_empty_and_unconfigured_surfaces_do_not_invent_work() -> None:
    manager = PluginManager(application_version="2.0.0")
    assert manager.load_all() == ()
    assert manager.disable_all() == ()
    assert manager.load_all(()) == ()
    assert manager.disable_all(()) == ()
    assert manager.plugin_ids() == ()
    assert manager.list_snapshots() == ()

    loader = ExternalPluginLoader(manager)
    assert loader.register_from_directory(None) == ()
    assert loader.register_from_directory("   ") == ()


def test_first_run_without_persisted_state_loads_as_enabled() -> None:
    manager = _manager()
    plugin = _RecordingPlugin(_manifest("fresh-plugin"), "fresh")
    assert manager.register(plugin, source="builtin").success is True
    result = manager.load("fresh-plugin")
    assert result.success is True
    assert result.state == "enabled"
    assert plugin.load_count == 1
    snapshot = manager.snapshot("fresh-plugin")
    assert snapshot is not None
    assert snapshot.desired_enabled is True


def test_bad_plugin_onload_is_isolated_from_later_plugins() -> None:
    manager = _manager()
    bad = _RecordingPlugin(_manifest("bad-plugin"), "bad", fail_onload=True)
    good = _RecordingPlugin(_manifest("good-plugin"), "good")
    manager.register(bad, source="builtin")
    manager.register(good, source="builtin")

    results = manager.load_all()
    assert [result.plugin_id for result in results] == ["bad-plugin", "good-plugin"]
    assert results[0].success is False
    assert results[0].error_code == "plugin_onload_failed"
    assert results[0].state == "failed"
    assert results[1].success is True
    assert results[1].state == "enabled"
    assert [item.registration_id for item in manager.registrations()] == ["good"]


def test_permission_decision_fails_only_the_undeclared_plugin() -> None:
    registry = ExtensionRegistry(
        {
            "agent_tool": build_agent_tool_extension_contract(ToolRegistry()),
        }
    )
    manager = PluginManager(application_version="2.0.0", registry=registry)
    bad = _AgentToolPlugin(
        _manifest("bad-tool", permissions=[]),
        tool_permissions=["market_data:read"],
        tool_name="bad_tool",
    )
    good = _AgentToolPlugin(
        _manifest("good-tool", permissions=["market_data:read"]),
        tool_permissions=["market_data:read"],
        tool_name="good_tool",
    )
    manager.register(bad, source="builtin")
    manager.register(good, source="builtin")
    results = manager.load_all()
    assert results[0].error_code == MANIFEST_PERMISSIONS_UNDECLARED
    assert results[0].state == "failed"
    assert results[1].success is True
    assert {item.registration_id for item in manager.registrations("agent_tool")} == {
        "good_tool"
    }


def test_external_discovery_order_is_directory_name_sorted(tmp_path: Path) -> None:
    manager = PluginManager(application_version="2.0.0")
    root = tmp_path / "plugins"
    root.mkdir()
    source = (
        "from src.plugins import Plugin as BasePlugin\n\n"
        "class Plugin(BasePlugin):\n"
        "    pass\n"
    )
    for name, plugin_id in (("zeta", "zeta-plugin"), ("alpha", "alpha-plugin")):
        candidate = root / name
        candidate.mkdir()
        (candidate / "manifest.json").write_text(
            (
                '{"id":"%s","name":"%s","version":"1.0.0","minAppVersion":"1.0.0",'
                '"description":"order","author":"tests","permissions":[]}'
            )
            % (plugin_id, plugin_id),
            encoding="utf-8",
        )
        (candidate / "plugin.py").write_text(source, encoding="utf-8")

    results = ExternalPluginLoader(manager).register_from_directory(root)
    assert [result.plugin_id for result in results] == ["alpha-plugin", "zeta-plugin"]
    assert manager.plugin_ids() == ("alpha-plugin", "zeta-plugin")
    loaded = manager.load_all()
    assert [result.plugin_id for result in loaded] == ["alpha-plugin", "zeta-plugin"]


def test_compatibility_error_uses_the_same_semver_tuple_as_manager() -> None:
    application_version = parse_semver("1.5.0")
    assert application_version < parse_semver("2.0.0")
    assert application_version == parse_semver("1.5.0")
    manager = PluginManager(application_version="1.5.0")
    assert manager._application_version == application_version


def test_extracted_permission_helpers_match_manager_decisions() -> None:
    from src.plugins.lifecycle import PluginLifecycleMixin
    from src.plugins.permissions import compatibility_error, load_time_permission_error

    manager = PluginManager(application_version="1.5.0", supported_api_versions=("1",))
    future = _manifest("future", min_app_version="2.0.0")
    api = _manifest("api", api_version="2")
    ok = _manifest("ok")
    assert compatibility_error(
        future,
        manager._application_version,
        manager._supported_api_versions,
    ) == manager.compatibility_error(future)
    assert compatibility_error(
        api,
        manager._application_version,
        manager._supported_api_versions,
    ) == manager.compatibility_error(api)
    assert compatibility_error(
        ok,
        manager._application_version,
        manager._supported_api_versions,
    ) is None
    assert compatibility_error(
        object(),
        manager._application_version,
        manager._supported_api_versions,
    ) == "plugin_manifest_invalid"
    assert issubclass(PluginManager, PluginLifecycleMixin)
    from src.plugins.settings_query import PluginSettingsQueryMixin
    from src.plugins.settings_update import PluginSettingsUpdateMixin
    from src.plugins.snapshot import PluginSnapshotMixin

    assert issubclass(PluginManager, PluginSettingsUpdateMixin)
    assert issubclass(PluginManager, PluginSettingsQueryMixin)
    assert issubclass(PluginManager, PluginSnapshotMixin)
    assert load_time_permission_error(manifest=ok, registrations=()) is None


def test_extracted_batch_order_helpers_match_manager_snapshots() -> None:
    from src.plugins.loader import select_disable_ids, select_load_ids

    registered = ("first-plugin", "second-plugin", "third-plugin")
    assert select_load_ids(None, registered) == registered
    assert select_disable_ids(None, registered) == (
        "third-plugin",
        "second-plugin",
        "first-plugin",
    )
    explicit = ("c-plugin", "a-plugin")
    assert select_load_ids(explicit, registered) == explicit
    assert select_disable_ids(explicit, registered) == ("a-plugin", "c-plugin")
    assert select_load_ids((), registered) == ()
    assert select_disable_ids((), registered) == ()


def test_split_modules_remain_internal_host_details() -> None:
    from src.plugins.surface import PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS

    assert "PluginManager" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert "ExternalPluginLoader" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert "compatibility_error" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert "PluginLifecycleMixin" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert "PluginSettingsUpdateMixin" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert "PluginSettingsQueryMixin" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert "PluginSnapshotMixin" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert "select_load_ids" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert "PluginState" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS


def test_external_plugin_result_type_hints_resolve_at_runtime() -> None:
    from typing import get_type_hints

    hints = get_type_hints(ExternalPluginResult)
    assert hints["state"] == PluginState | None
    assert hints["plugin_id"] == str | None


def test_settings_update_mixin_owner_stays_internal() -> None:
    from src.plugins.settings_update import PluginSettingsUpdateMixin
    from src.plugins.surface import PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS

    assert issubclass(PluginManager, PluginSettingsUpdateMixin)
    assert PluginSettingsUpdateMixin.__module__ == "src.plugins.settings_update"
    assert PluginManager.update_settings.__module__ == "src.plugins.settings_update"
    assert PluginManager.__module__ == "src.plugins.manager"
    assert PluginManager.update_settings is PluginSettingsUpdateMixin.update_settings
    assert "PluginSettingsUpdateMixin" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert not hasattr(plugins_root, "PluginSettingsUpdateMixin")
    assert "PluginSettingsUpdateMixin" not in manager_mod.__all__
    assert "PluginSettingsUpdateMixin" not in getattr(plugins_root, "__all__", ())


def test_settings_query_mixin_owner_stays_internal() -> None:
    from src.plugins.lifecycle import PluginLifecycleMixin
    from src.plugins.settings_query import PluginSettingsQueryMixin
    from src.plugins.settings_update import PluginSettingsUpdateMixin
    from src.plugins.surface import PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS

    assert issubclass(PluginManager, PluginSettingsQueryMixin)
    from src.plugins.snapshot import PluginSnapshotMixin

    assert PluginManager.__bases__ == (
        PluginSettingsUpdateMixin,
        PluginSettingsQueryMixin,
        PluginSnapshotMixin,
        PluginLifecycleMixin,
    )
    assert PluginSettingsQueryMixin.__module__ == "src.plugins.settings_query"
    assert PluginManager.settings_schema.__module__ == "src.plugins.settings_query"
    assert PluginManager.settings_values.__module__ == "src.plugins.settings_query"
    assert PluginManager.__module__ == "src.plugins.manager"
    assert PluginManager.settings_schema is PluginSettingsQueryMixin.settings_schema
    assert PluginManager.settings_values is PluginSettingsQueryMixin.settings_values
    assert "PluginSettingsQueryMixin" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert not hasattr(plugins_root, "PluginSettingsQueryMixin")
    assert "PluginSettingsQueryMixin" not in manager_mod.__all__
    assert "PluginSettingsQueryMixin" not in getattr(plugins_root, "__all__", ())


def test_snapshot_unknown_id_returns_none() -> None:
    manager = _manager()
    assert manager.snapshot("missing") is None
    assert manager.contains("missing") is False


def test_snapshot_mixin_owner_stays_internal() -> None:
    from src.plugins.lifecycle import PluginLifecycleMixin
    from src.plugins.settings_query import PluginSettingsQueryMixin
    from src.plugins.settings_update import PluginSettingsUpdateMixin
    from src.plugins.snapshot import PluginSnapshotMixin
    from src.plugins.surface import PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS

    assert issubclass(PluginManager, PluginSnapshotMixin)
    assert PluginManager.__bases__ == (
        PluginSettingsUpdateMixin,
        PluginSettingsQueryMixin,
        PluginSnapshotMixin,
        PluginLifecycleMixin,
    )
    assert PluginSnapshotMixin.__module__ == "src.plugins.snapshot"
    assert PluginManager.snapshot.__module__ == "src.plugins.snapshot"
    assert PluginManager.list_snapshots.__module__ == "src.plugins.snapshot"
    assert PluginManager.plugin_ids.__module__ == "src.plugins.snapshot"
    assert PluginManager._build_snapshot.__module__ == "src.plugins.snapshot"
    assert PluginManager.__module__ == "src.plugins.manager"
    assert PluginManager.snapshot is PluginSnapshotMixin.snapshot
    assert PluginManager.list_snapshots is PluginSnapshotMixin.list_snapshots
    assert PluginManager.plugin_ids is PluginSnapshotMixin.plugin_ids
    assert PluginManager._build_snapshot is PluginSnapshotMixin._build_snapshot
    assert "PluginSnapshotMixin" not in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    assert not hasattr(plugins_root, "PluginSnapshotMixin")
    assert "PluginSnapshotMixin" not in manager_mod.__all__
    assert "PluginSnapshotMixin" not in getattr(plugins_root, "__all__", ())
    assert plugins_root.PluginSnapshot is manager_mod.PluginSnapshot


def test_register_and_contains_remain_manager_owned() -> None:
    assert PluginManager.register.__module__ == "src.plugins.manager"
    assert PluginManager.contains.__module__ == "src.plugins.manager"
    assert PluginManager.capability_inventory_snapshot.__module__ == "src.plugins.manager"
    assert PluginManager.health_check.__module__ == "src.plugins.manager"
    assert PluginManager.bind_lifecycle_auditor.__module__ == "src.plugins.manager"


def test_snapshot_reloadable_matrix(tmp_path: Path) -> None:
    manager = _manager()
    builtin = _RecordingPlugin(_manifest("builtin-plugin"), "builtin")
    assert manager.register(builtin, source="builtin").success is True
    builtin_snapshot = manager.snapshot("builtin-plugin")
    assert builtin_snapshot is not None
    assert builtin_snapshot.reloadable is False
    assert builtin_snapshot.package_root is None

    external_root = tmp_path / "ext"
    external_root.mkdir()
    external = _RecordingPlugin(_manifest("external-plugin"), "external")
    assert manager.register(
        external,
        source="external",
        package_root=external_root,
    ).success is True
    external_snapshot = manager.snapshot("external-plugin")
    assert external_snapshot is not None
    assert external_snapshot.reloadable is True
    assert external_snapshot.package_root == str(external_root.resolve())
    assert type(external_snapshot.package_root) is str

    no_root = _RecordingPlugin(_manifest("external-no-root"), "no-root")
    assert manager.register(no_root, source="external").success is True
    no_root_snapshot = manager.snapshot("external-no-root")
    assert no_root_snapshot is not None
    assert no_root_snapshot.reloadable is False
    assert no_root_snapshot.package_root is None

    gated = _RecordingPlugin(_manifest("external-gated"), "gated")
    assert manager.register(
        gated,
        source="external",
        package_root=external_root,
    ).success is True
    record = manager._plugins["external-gated"]
    record.transition = "load"
    transitioning = manager.snapshot("external-gated")
    assert transitioning is not None
    assert transitioning.reloadable is False
    record.transition = None
    record.cleanup_pending = True
    pending = manager.snapshot("external-gated")
    assert pending is not None
    assert pending.reloadable is False
    record.cleanup_pending = False
    restored = manager.snapshot("external-gated")
    assert restored is not None
    assert restored.reloadable is True


def test_capability_inventory_snapshot_stays_facade_owned() -> None:
    manager = _manager()
    plugin = _RecordingPlugin(_manifest("inventory-plugin"), "inventory")
    assert manager.register(plugin, source="builtin").success is True
    assert manager.load("inventory-plugin").success is True
    generation, lifecycle, registrations = manager.capability_inventory_snapshot()
    assert isinstance(generation, str)
    assert generation.startswith("lifecycle:")
    assert all(isinstance(item, manager_mod.PluginSnapshot) for item in lifecycle)
    assert tuple(item.manifest.id for item in lifecycle) == ("inventory-plugin",)
    assert registrations != ()
    assert PluginManager.capability_inventory_snapshot.__module__ == "src.plugins.manager"
    assert PluginManager._build_snapshot.__module__ == "src.plugins.snapshot"


def test_lifecycle_and_manager_import_in_either_order() -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    assertions = (
        "from typing import get_type_hints\n"
        "assert issubclass(manager.PluginManager, lifecycle.PluginLifecycleMixin)\n"
        "assert issubclass(\n"
        "    manager.PluginManager, settings_update.PluginSettingsUpdateMixin\n"
        ")\n"
        "assert issubclass(\n"
        "    manager.PluginManager, settings_query.PluginSettingsQueryMixin\n"
        ")\n"
        "assert issubclass(\n"
        "    manager.PluginManager, snapshot.PluginSnapshotMixin\n"
        ")\n"
        "assert manager.PluginManager.__bases__ == (\n"
        "    settings_update.PluginSettingsUpdateMixin,\n"
        "    settings_query.PluginSettingsQueryMixin,\n"
        "    snapshot.PluginSnapshotMixin,\n"
        "    lifecycle.PluginLifecycleMixin,\n"
        ")\n"
        "assert manager.PluginState is loader.PluginState\n"
        "assert get_type_hints(loader.ExternalPluginResult)['state'] "
        "== manager.PluginState | None\n"
        "assert manager.PluginManager.update_settings is "
        "settings_update.PluginSettingsUpdateMixin.update_settings\n"
        "assert manager.PluginManager.settings_schema is "
        "settings_query.PluginSettingsQueryMixin.settings_schema\n"
        "assert manager.PluginManager.settings_values is "
        "settings_query.PluginSettingsQueryMixin.settings_values\n"
        "assert manager.PluginManager.snapshot is "
        "snapshot.PluginSnapshotMixin.snapshot\n"
        "assert manager.PluginManager.list_snapshots is "
        "snapshot.PluginSnapshotMixin.list_snapshots\n"
        "assert manager.PluginManager.plugin_ids is "
        "snapshot.PluginSnapshotMixin.plugin_ids\n"
        "assert manager.PluginManager._build_snapshot is "
        "snapshot.PluginSnapshotMixin._build_snapshot\n"
        "assert manager.PluginManager.register.__module__ == "
        "'src.plugins.manager'\n"
        "assert manager.PluginManager.contains.__module__ == "
        "'src.plugins.manager'\n"
    )
    scripts = (
        (
            "import src.plugins.snapshot as snapshot\n"
            "import src.plugins.manager as manager\n"
            "import src.plugins.lifecycle as lifecycle\n"
            "import src.plugins.settings_update as settings_update\n"
            "import src.plugins.settings_query as settings_query\n"
            "import src.plugins.loader as loader\n"
        )
        + assertions,
        (
            "import src.plugins.lifecycle as lifecycle\n"
            "import src.plugins.manager as manager\n"
            "import src.plugins.settings_update as settings_update\n"
            "import src.plugins.settings_query as settings_query\n"
            "import src.plugins.snapshot as snapshot\n"
            "import src.plugins.loader as loader\n"
        )
        + assertions,
        (
            "import src.plugins.settings_update as settings_update\n"
            "import src.plugins.manager as manager\n"
            "import src.plugins.lifecycle as lifecycle\n"
            "import src.plugins.settings_query as settings_query\n"
            "import src.plugins.snapshot as snapshot\n"
            "import src.plugins.loader as loader\n"
        )
        + assertions,
        (
            "import src.plugins.settings_query as settings_query\n"
            "import src.plugins.manager as manager\n"
            "import src.plugins.lifecycle as lifecycle\n"
            "import src.plugins.settings_update as settings_update\n"
            "import src.plugins.snapshot as snapshot\n"
            "import src.plugins.loader as loader\n"
        )
        + assertions,
        (
            "import src.plugins.manager as manager\n"
            "import src.plugins.snapshot as snapshot\n"
            "import src.plugins.lifecycle as lifecycle\n"
            "import src.plugins.settings_update as settings_update\n"
            "import src.plugins.settings_query as settings_query\n"
            "import src.plugins.loader as loader\n"
        )
        + assertions,
        (
            "import src.plugins.loader as loader\n"
            "import src.plugins.snapshot as snapshot\n"
            "import src.plugins.settings_query as settings_query\n"
            "import src.plugins.settings_update as settings_update\n"
            "import src.plugins.lifecycle as lifecycle\n"
            "import src.plugins.manager as manager\n"
        )
        + assertions,
    )
    for script in scripts:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr
