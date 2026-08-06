# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for the frozen plugin extension surface v1 (ADR-007)."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

import src.plugins as plugins_pkg
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.config import Config
from src.notification import NotificationService
from src.notification_noise import reset_notification_noise_state
from src.plugins import (
    EXTENSION_POINTS,
    PLUGIN_APPLICATION_VERSION,
    PLUGIN_EXTENSION_SURFACE_VERSION,
    PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS,
    PLUGIN_EXTENSION_SURFACE_V1_POINT_ORDER,
    PLUGIN_EXTENSION_SURFACE_V1_POINTS,
    NotificationAdapterResult,
    NotificationRequest,
    Plugin,
    PluginContext,
    PluginContextClosedError,
    PluginManifest,
    PluginRegistryError,
)
from src.plugins.registry import ExtensionRegistry
from src.plugins.registry import PluginContext as RegistryPluginContext


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_REFERENCE_NOTIFICATION = (
    _REPOSITORY_ROOT / "examples" / "plugins" / "example-notification-channel"
)
_REFERENCE_PROVIDER = _REPOSITORY_ROOT / "examples" / "plugins" / "example-provider"


@pytest.fixture(autouse=True)
def _clean_application_root() -> object:
    reset_application_services()
    reset_notification_noise_state()
    yield
    reset_application_services()
    reset_notification_noise_state()


def _manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": PLUGIN_APPLICATION_VERSION,
            "description": f"Surface contract plugin {plugin_id}",
            "author": "StockPulse tests",
            "permissions": [],
            "apiVersion": "1",
            "entrypoint": "plugin.py:Plugin",
        }
    )


def test_surface_version_and_points_are_frozen() -> None:
    assert PLUGIN_EXTENSION_SURFACE_VERSION == 1
    assert PLUGIN_EXTENSION_SURFACE_V1_POINT_ORDER == (
        "data_provider",
        "analysis_strategy",
        "agent_tool",
        "notification_channel",
        "report_template",
        "event_hook",
    )
    assert frozenset(PLUGIN_EXTENSION_SURFACE_V1_POINT_ORDER) == (
        PLUGIN_EXTENSION_SURFACE_V1_POINTS
    )
    assert EXTENSION_POINTS == PLUGIN_EXTENSION_SURFACE_V1_POINT_ORDER
    assert frozenset(EXTENSION_POINTS) == PLUGIN_EXTENSION_SURFACE_V1_POINTS


def test_author_exports_are_published_on_package_root() -> None:
    public_names = set(plugins_pkg.__all__)
    missing = sorted(PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS - public_names)
    assert missing == [], f"frozen author exports missing from __all__: {missing}"
    for name in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS:
        assert hasattr(plugins_pkg, name), name


def _imported_src_plugins_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.plugins":
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.startswith("src.plugins."):
                names.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.plugins" or alias.name.startswith(
                    "src.plugins."
                ):
                    names.add(alias.name)
    return names


def test_reference_notification_plugin_uses_only_frozen_author_exports() -> None:
    source = (_REFERENCE_NOTIFICATION / "plugin.py").read_text(encoding="utf-8")
    imported = _imported_src_plugins_names(source)
    from_root = {name for name in imported if not name.startswith("src.plugins")}
    submodule = {name for name in imported if name.startswith("src.plugins.")}
    assert submodule == set(), f"reference plugin imports internal modules: {submodule}"
    unexpected = sorted(from_root - PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS)
    assert unexpected == [], f"non-frozen author imports: {unexpected}"


def test_reference_notification_plugin_full_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = Config(
        stock_list=[],
        notification_report_channels=["example_log"],
    )
    monkeypatch.setattr("src.notification.get_config", lambda: config)
    plugins_dir = _REFERENCE_NOTIFICATION.parent
    services = ApplicationServices(config=config, plugins_dir=plugins_dir)
    set_application_services(services)

    loads = {result.plugin_id: result for result in services.plugin_load_results}
    assert loads["example-notification-channel"].success is True
    assert loads["example-notification-channel"].state == "enabled"

    snapshot_ids = {
        entry.channel_id
        for entry in services.notification_channel_registry.snapshot()
    }
    assert "example_log" in snapshot_ids

    service = NotificationService()
    with caplog.at_level(logging.INFO):
        dispatch = service.send_with_results(
            "surface v1 reference report",
            route_type="report",
        )

    assert dispatch.success is True
    assert [attempt.channel for attempt in dispatch.channel_results] == [
        "example_log"
    ]
    assert "Example notification delivered" in caplog.text
    assert "surface v1 reference report" not in caplog.text

    disable = services.plugin_manager.disable("example-notification-channel")
    assert disable.success is True
    assert disable.state == "disabled"
    assert "example_log" not in {
        entry.channel_id
        for entry in services.notification_channel_registry.snapshot()
    }

    enable = services.plugin_manager.enable("example-notification-channel")
    assert enable.success is True
    assert enable.state == "enabled"
    assert "example_log" in {
        entry.channel_id
        for entry in services.notification_channel_registry.snapshot()
    }


def test_plugin_registering_unlisted_extension_point_fails_loudly() -> None:
    class HostileMarketplacePlugin(Plugin):
        def onload(self, context: PluginContext) -> None:
            context.register(
                "marketplace",  # type: ignore[arg-type]
                "remote-store",
                object(),
            )

    services = ApplicationServices(config=Config(stock_list=[]))
    plugin = HostileMarketplacePlugin(_manifest("stockpulse.hostile-marketplace"))
    registered = services.plugin_manager.register(plugin, source="external")
    assert registered.success is True
    loaded = services.plugin_manager.load("stockpulse.hostile-marketplace")
    assert loaded.success is False
    assert loaded.state == "failed"
    assert loaded.error_code == "extension_point_unsupported"


def test_direct_registry_rejects_unlisted_extension_point() -> None:
    registry = ExtensionRegistry()
    with pytest.raises(PluginRegistryError) as raised:
        registry.register(
            plugin_id="stockpulse.hostile-ui",
            extension_point="ui_component",  # type: ignore[arg-type]
            registration_id="panel",
            implementation=object(),
        )
    assert raised.value.error_code == "extension_point_unsupported"


def test_closed_context_rejects_registration_loudly() -> None:
    registry = ExtensionRegistry()
    context = RegistryPluginContext("stockpulse.closed-context", registry)
    context.close()
    with pytest.raises(PluginContextClosedError) as raised:
        context.register(
            "notification_channel",
            "late_channel",
            object(),
        )
    assert raised.value.error_code == "plugin_context_closed"


class _FrozenSurfaceNotificationAdapter:
    channel_id = "frozen_surface_log"
    display_name = "Frozen Surface Log"

    def __init__(self, config: object) -> None:
        del config

    def is_available(self) -> bool:
        return True

    def send(self, request: NotificationRequest) -> NotificationAdapterResult:
        del request
        return NotificationAdapterResult(success=True)


def test_plugin_using_only_frozen_surface_loads_and_registers() -> None:
    class SurfaceOnlyPlugin(Plugin):
        def onload(self, context: PluginContext) -> None:
            context.register(
                "notification_channel",
                _FrozenSurfaceNotificationAdapter.channel_id,
                _FrozenSurfaceNotificationAdapter,
                contract_version="1",
            )

    services = ApplicationServices(config=Config(stock_list=[]))
    plugin = SurfaceOnlyPlugin(_manifest("stockpulse.surface-only-notification"))
    assert services.plugin_manager.register(plugin, source="builtin").success
    loaded = services.plugin_manager.load("stockpulse.surface-only-notification")
    assert loaded.success is True
    assert loaded.state == "enabled"
    assert "frozen_surface_log" in {
        entry.channel_id
        for entry in services.notification_channel_registry.snapshot()
    }


def test_reference_packages_ship_with_manifests() -> None:
    assert (_REFERENCE_PROVIDER / "manifest.json").is_file()
    assert (_REFERENCE_PROVIDER / "plugin.py").is_file()
    assert (_REFERENCE_NOTIFICATION / "manifest.json").is_file()
    source = (_REFERENCE_PROVIDER / "plugin.py").read_text(encoding="utf-8")
    imported = _imported_src_plugins_names(source)
    from_root = {name for name in imported if not name.startswith("src.plugins")}
    submodule = {name for name in imported if name.startswith("src.plugins.")}
    assert submodule == set()
    unexpected = sorted(from_root - PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS)
    assert unexpected == [], f"provider reference non-frozen imports: {unexpected}"
