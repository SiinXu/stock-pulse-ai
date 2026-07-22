# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Lifecycle and fault-isolation regressions for ``PluginManager``."""

from __future__ import annotations

import concurrent.futures
import threading
from dataclasses import dataclass

import pytest

from src.plugins import (
    ExtensionContract,
    ExtensionRegistry,
    Plugin,
    PluginContext,
    PluginContextClosedError,
    PluginManager,
    PluginManifest,
)


def _manifest(
    plugin_id: str,
    *,
    min_app_version: str = "1.0.0",
    api_version: str = "1",
) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": min_app_version,
            "description": "Lifecycle test plugin.",
            "author": "StockPulse Tests",
            "permissions": [],
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
        registration_ids: tuple[str, ...] = (),
        *,
        fail_onload: bool = False,
        fail_onunload: bool = False,
    ) -> None:
        super().__init__(manifest)
        self.registration_ids = registration_ids
        self.fail_onload = fail_onload
        self.fail_onunload = fail_onunload
        self.load_count = 0
        self.unload_count = 0
        self.last_context: PluginContext | None = None

    def onload(self, context: PluginContext) -> None:
        self.load_count += 1
        self.last_context = context
        for registration_id in self.registration_ids:
            context.register(
                "report_template",
                registration_id,
                _Template(registration_id),
            )
        if self.fail_onload:
            raise RuntimeError("token=onload-secret")

    def onunload(self) -> None:
        self.unload_count += 1
        if self.fail_onunload:
            raise RuntimeError("password=onunload-secret")


class _Backend:
    def __init__(self) -> None:
        self.items: dict[str, object] = {}
        self.unregister_order: list[str] = []
        self.fail_unregister = False

    def contains(self, registration_id: str) -> bool:
        return registration_id in self.items

    def register(self, registration_id: str, implementation: object) -> None:
        self.items[registration_id] = implementation

    def unregister(self, registration_id: str, implementation: object) -> None:
        self.unregister_order.append(registration_id)
        if self.fail_unregister:
            raise RuntimeError("token=cleanup-secret")
        if self.items.get(registration_id) is implementation:
            del self.items[registration_id]


def _manager_with_backend(backend: _Backend) -> PluginManager:
    registry = ExtensionRegistry(
        {
            "report_template": ExtensionContract(
                identity_resolver=lambda implementation: implementation.template_id,
                validator=lambda implementation: isinstance(implementation, _Template),
                backend=backend,
            )
        }
    )
    return PluginManager(application_version="2.0.0", registry=registry)


def test_register_is_separate_from_load_and_lifecycle_is_exactly_once() -> None:
    manager = PluginManager(application_version="2.0.0")
    plugin = _RecordingPlugin(_manifest("example-plugin"), ("daily",))

    registered = manager.register(plugin, source="builtin")

    assert registered.success is True
    assert registered.state == "registered"
    assert plugin.load_count == 0
    assert manager.registrations() == ()
    assert manager.enable("example-plugin").error_code == "plugin_invalid_state"

    assert manager.load("example-plugin").success is True
    assert manager.load("example-plugin").success is True
    assert manager.enable("example-plugin").success is True
    assert plugin.load_count == 1
    assert len(manager.registrations("report_template")) == 1

    assert manager.disable("example-plugin").success is True
    assert manager.disable("example-plugin").success is True
    assert plugin.unload_count == 1
    assert manager.registrations() == ()

    assert manager.enable("example-plugin").success is True
    assert plugin.load_count == 2
    assert manager.disable("example-plugin").success is True
    assert plugin.unload_count == 2


def test_register_rejects_app_api_duplicate_and_invalid_source_contracts() -> None:
    manager = PluginManager(application_version="1.5.0", supported_api_versions={"1"})
    future = _RecordingPlugin(_manifest("future-plugin", min_app_version="2.0.0"))
    newer_api = _RecordingPlugin(_manifest("api-plugin", api_version="2"))

    assert manager.register(future, source="builtin").error_code == "plugin_app_version_unsupported"
    assert manager.register(newer_api, source="builtin").error_code == "plugin_api_version_unsupported"
    assert manager.plugin_ids() == ()

    compatible = _RecordingPlugin(_manifest("compatible-plugin"))
    assert manager.register(compatible, source="builtin").success is True
    duplicate = manager.register(_RecordingPlugin(_manifest("compatible-plugin")), source="external")
    assert duplicate.error_code == "plugin_id_conflict"
    assert manager.register(compatible, source="invalid").error_code == "plugin_source_invalid"  # type: ignore[arg-type]
    assert manager.register(compatible, source=[]).error_code == "plugin_source_invalid"  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        PluginManager(application_version="1.0")
    with pytest.raises(ValueError):
        PluginManager(application_version=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        PluginManager(application_version="1.0.0", supported_api_versions=set())


def test_onload_failure_cleans_in_reverse_order() -> None:
    backend = _Backend()
    manager = _manager_with_backend(backend)
    plugin = _RecordingPlugin(
        _manifest("failing-plugin"),
        ("first", "second"),
        fail_onload=True,
    )
    manager.register(plugin, source="builtin")

    result = manager.load("failing-plugin")

    assert result.success is False
    assert result.state == "failed"
    assert result.error_code == "plugin_onload_failed"
    assert backend.unregister_order == ["second", "first"]
    assert backend.items == {}
    assert manager.registrations() == ()


def test_load_all_continues_after_failed_plugin() -> None:
    manager = PluginManager(application_version="2.0.0")
    failing = _RecordingPlugin(
        _manifest("failing-plugin"),
        ("failing",),
        fail_onload=True,
    )
    healthy = _RecordingPlugin(_manifest("healthy-plugin"), ("healthy",))
    manager.register(failing, source="builtin")
    manager.register(healthy, source="builtin")

    results = manager.load_all()

    assert [result.success for result in results] == [False, True]
    assert manager.snapshot("failing-plugin").state == "failed"  # type: ignore[union-attr]
    assert manager.snapshot("healthy-plugin").state == "enabled"  # type: ignore[union-attr]
    assert [item.registration_id for item in manager.registrations()] == ["healthy"]


def test_concurrent_load_calls_invoke_onload_once() -> None:
    manager = PluginManager(application_version="2.0.0")
    started = threading.Event()
    release = threading.Event()

    class BlockingPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            self.load_count += 1
            self.last_context = context
            started.set()
            assert release.wait(timeout=2)

    plugin = BlockingPlugin(_manifest("blocking-plugin"))
    manager.register(plugin, source="builtin")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(manager.load, "blocking-plugin")
        assert started.wait(timeout=2)
        second = executor.submit(manager.load, "blocking-plugin")
        release.set()
        results = (first.result(timeout=2), second.result(timeout=2))

    assert all(result.success for result in results)
    assert plugin.load_count == 1


def test_context_rejects_registration_after_onload_returns() -> None:
    manager = PluginManager(application_version="2.0.0")
    plugin = _RecordingPlugin(_manifest("context-plugin"))
    manager.register(plugin, source="builtin")
    manager.load("context-plugin")

    assert plugin.last_context is not None
    assert plugin.last_context.active is False
    with pytest.raises(PluginContextClosedError) as raised:
        plugin.last_context.register(
            "report_template",
            "late",
            _Template("late"),
        )
    assert raised.value.error_code == "plugin_context_closed"


def test_onunload_failure_still_disables_and_cleans_exactly_once() -> None:
    manager = PluginManager(application_version="2.0.0")
    plugin = _RecordingPlugin(
        _manifest("unload-plugin"),
        ("daily",),
        fail_onunload=True,
    )
    manager.register(plugin, source="builtin")
    manager.load("unload-plugin")

    result = manager.disable("unload-plugin")

    assert result.success is False
    assert result.state == "disabled"
    assert result.error_code == "plugin_onunload_failed"
    assert manager.registrations() == ()
    assert manager.disable("unload-plugin").success is True
    assert plugin.unload_count == 1


def test_native_cleanup_failure_keeps_failed_state_until_retry() -> None:
    backend = _Backend()
    manager = _manager_with_backend(backend)
    plugin = _RecordingPlugin(_manifest("cleanup-plugin"), ("daily",))
    manager.register(plugin, source="builtin")
    manager.load("cleanup-plugin")
    backend.fail_unregister = True

    failed = manager.disable("cleanup-plugin")

    assert failed.success is False
    assert failed.state == "failed"
    assert failed.error_code == "native_registry_unregistration_failed"
    assert manager.registrations() != ()
    assert plugin.unload_count == 1

    backend.fail_unregister = False
    retried = manager.disable("cleanup-plugin")
    assert retried.success is True
    assert retried.state == "disabled"
    assert manager.registrations() == ()
    assert plugin.unload_count == 1


def test_disable_all_continues_after_unload_failure() -> None:
    manager = PluginManager(application_version="2.0.0")
    first = _RecordingPlugin(_manifest("first-plugin"), fail_onunload=True)
    second = _RecordingPlugin(_manifest("second-plugin"))
    manager.register(first, source="builtin")
    manager.register(second, source="builtin")
    manager.load_all()

    results = manager.disable_all()

    assert [result.plugin_id for result in results] == ["second-plugin", "first-plugin"]
    assert [result.success for result in results] == [True, False]
    assert manager.snapshot("first-plugin").state == "disabled"  # type: ignore[union-attr]
    assert manager.snapshot("second-plugin").state == "disabled"  # type: ignore[union-attr]


def test_missing_plugin_returns_stable_failure() -> None:
    manager = PluginManager(application_version="2.0.0")

    assert manager.load("missing").error_code == "plugin_not_found"
    assert manager.enable("missing").error_code == "plugin_not_found"
    assert manager.disable("missing").error_code == "plugin_not_found"
