# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Enable/disable persistence, disabled-not-invoked, and hot-reload regressions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import plugins as plugins_endpoint
from src.plugins import (
    EventHookRegistration,
    ExtensionContract,
    ExtensionRegistry,
    Plugin,
    PluginContext,
    PluginLifecycleStateStore,
    PluginManager,
    PluginManifest,
)
from src.services.security_audit_service import SecurityAuditUnavailable
from tests.security_audit_test_utils import SecurityAuditRecorderStub
from src.plugins.event_hooks import event_hook_extension_contract
from src.plugins.loader import ExternalPluginLoader


def _manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": "Lifecycle control fixture.",
            "author": "StockPulse Tests",
            "permissions": [],
            "apiVersion": "1",
        }
    )


@dataclass
class _Template:
    template_id: str


class _TemplateBackend:
    def __init__(self) -> None:
        self.items: dict[str, object] = {}

    def contains(self, registration_id: str) -> bool:
        return registration_id in self.items

    def register(self, registration_id: str, implementation: object) -> None:
        self.items[registration_id] = implementation

    def unregister(self, registration_id: str, implementation: object) -> None:
        if self.items.get(registration_id) is implementation:
            del self.items[registration_id]


class _RecordingPlugin(Plugin):
    def __init__(
        self,
        manifest: PluginManifest,
        *,
        points: tuple[str, ...] = ("report_template",),
        registration_id: str = "fixture",
    ) -> None:
        super().__init__(manifest)
        self.points = points
        self.registration_id = registration_id
        self.load_count = 0
        self.unload_count = 0

    def onload(self, context: PluginContext) -> None:
        self.load_count += 1
        for point in self.points:
            if point == "report_template":
                context.register(
                    "report_template",
                    self.registration_id,
                    _Template(self.registration_id),
                )
            elif point == "event_hook":
                context.register(
                    "event_hook",
                    self.registration_id,
                    EventHookRegistration(
                        hook_id=self.registration_id,
                        event_names=frozenset({"analysis.started"}),
                        callback=lambda event: None,
                    ),
                )
            elif point == "agent_tool":
                context.register(
                    "agent_tool",
                    self.registration_id,
                    {
                        "name": self.registration_id,
                        "description": "fixture",
                        "parameters": {"type": "object", "properties": {}},
                        "handler": lambda **kwargs: {"ok": True},
                    },
                )
            elif point == "analysis_strategy":
                context.register(
                    "analysis_strategy",
                    self.registration_id,
                    {
                        "id": self.registration_id,
                        "name": self.registration_id,
                        "description": "fixture strategy",
                    },
                )
            elif point == "notification_channel":
                context.register(
                    "notification_channel",
                    self.registration_id,
                    lambda config: object(),
                )
            elif point == "data_provider":
                context.register(
                    "data_provider",
                    self.registration_id,
                    object(),
                )

    def onunload(self) -> None:
        self.unload_count += 1


def _manager(
    *,
    state_store: PluginLifecycleStateStore | None = None,
    with_hooks: bool = False,
) -> tuple[PluginManager, _TemplateBackend]:
    backend = _TemplateBackend()
    contracts: dict = {
        "report_template": ExtensionContract(
            identity_resolver=lambda implementation: implementation.template_id,
            validator=lambda implementation: hasattr(implementation, "template_id"),
            backend=backend,
        )
    }
    if with_hooks:
        contracts["event_hook"] = event_hook_extension_contract()
    for point, identity in (
        ("agent_tool", lambda impl: impl["name"] if isinstance(impl, dict) else "x"),
        (
            "analysis_strategy",
            lambda impl: impl["id"] if isinstance(impl, dict) else "x",
        ),
        ("notification_channel", lambda impl: "channel"),
        ("data_provider", lambda impl: "provider"),
    ):
        contracts.setdefault(
            point,
            ExtensionContract(
                identity_resolver=identity,
                validator=lambda implementation: True,
            ),
        )
    manager = PluginManager(
        application_version="2.0.0",
        registry=ExtensionRegistry(contracts),
        state_store=state_store or PluginLifecycleStateStore.memory(),
    )
    return manager, backend


def test_toggle_persistence_round_trip(tmp_path: Path) -> None:
    state_path = tmp_path / "plugin_lifecycle_state.json"
    store = PluginLifecycleStateStore(state_path, persist=True)
    manager, backend = _manager(state_store=store)
    plugin = _RecordingPlugin(_manifest("persist-plugin"))
    assert manager.register(plugin, source="external").success
    assert manager.load("persist-plugin").success
    assert backend.contains("fixture")

    disabled = manager.set_enabled("persist-plugin", False)
    assert disabled.success is True
    assert disabled.state == "disabled"
    assert not backend.contains("fixture")
    assert store.is_disabled("persist-plugin") is True
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert "persist-plugin" in payload["disabled_plugin_ids"]

    manager2, backend2 = _manager(state_store=PluginLifecycleStateStore(state_path))
    plugin2 = _RecordingPlugin(_manifest("persist-plugin"))
    assert manager2.register(plugin2, source="external").success
    loaded = manager2.load("persist-plugin")
    assert loaded.success is True
    assert loaded.state == "disabled"
    assert plugin2.load_count == 0
    assert manager2.enabled_registrations() == ()
    assert not backend2.contains("fixture")

    enabled = manager2.set_enabled("persist-plugin", True)
    assert enabled.success is True
    assert enabled.state == "enabled"
    assert plugin2.load_count == 1
    assert manager2.state_store.is_disabled("persist-plugin") is False
    # Disk should reflect the enable after manager2 wrote it.
    store_reloaded = PluginLifecycleStateStore(state_path, persist=True)
    assert store_reloaded.is_disabled("persist-plugin") is False


@pytest.mark.parametrize(
    "point",
    [
        "report_template",
        "event_hook",
        "agent_tool",
        "analysis_strategy",
        "notification_channel",
        "data_provider",
    ],
)
def test_disabled_plugin_not_invoked_per_hook_type(point: str) -> None:
    store = PluginLifecycleStateStore.memory()
    store.set_disabled("hook-plugin", True)
    manager, _backend = _manager(state_store=store, with_hooks=True)
    plugin = _RecordingPlugin(
        _manifest("hook-plugin"),
        points=(point,),
        registration_id=f"{point}-id",
    )
    assert manager.register(plugin, source="external").success
    result = manager.load("hook-plugin")
    assert result.state == "disabled"
    assert plugin.load_count == 0
    assert manager.enabled_registrations(point) == ()  # type: ignore[arg-type]
    assert manager.registrations(point) == ()  # type: ignore[arg-type]


def test_reload_swaps_external_fixture_code(tmp_path: Path) -> None:
    root = tmp_path / "plugins" / "swap-plugin"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "id": "swap-plugin",
                "name": "swap-plugin",
                "version": "1.0.0",
                "minAppVersion": "1.0.0",
                "description": "Hot reload fixture.",
                "author": "StockPulse Tests",
                "permissions": [],
            }
        ),
        encoding="utf-8",
    )
    (root / "plugin.py").write_text(
        """
from src.plugins import Plugin as BasePlugin, PluginContext

class Plugin(BasePlugin):
    MARKER = "v1"
    def onload(self, context: PluginContext) -> None:
        class T:
            template_id = "swap-template"
        context.register("report_template", "swap-template", T())
""",
        encoding="utf-8",
    )

    store = PluginLifecycleStateStore.memory()
    manager, backend = _manager(state_store=store)
    loader = ExternalPluginLoader(manager)
    registered = loader.register_from_directory(tmp_path / "plugins")
    assert registered[0].success is True
    assert manager.load("swap-plugin").success is True
    assert backend.contains("swap-template")
    first_impl = backend.items["swap-template"]

    time.sleep(0.02)
    (root / "plugin.py").write_text(
        """
from src.plugins import Plugin as BasePlugin, PluginContext

class Plugin(BasePlugin):
    MARKER = "v2"
    def onload(self, context: PluginContext) -> None:
        class T:
            template_id = "swap-template"
            marker = "v2"
        context.register("report_template", "swap-template", T())
""",
        encoding="utf-8",
    )

    reload_result = manager.reload("swap-plugin")
    assert reload_result.success is True
    assert reload_result.reloaded is True
    assert reload_result.restart_required is False
    assert manager.snapshot("swap-plugin").state == "enabled"
    assert backend.contains("swap-template")
    second_impl = backend.items["swap-template"]
    assert second_impl is not first_impl
    assert getattr(second_impl, "marker", None) == "v2"


def test_builtin_reload_requires_restart() -> None:
    manager, _ = _manager()
    plugin = _RecordingPlugin(_manifest("builtin-plugin"))
    assert manager.register(plugin, source="builtin").success
    assert manager.load("builtin-plugin").success
    result = manager.reload("builtin-plugin")
    assert result.success is False
    assert result.restart_required is True
    assert result.error_code == "plugin_reload_restart_required"
    assert manager.snapshot("builtin-plugin").state == "enabled"


def test_extension_surface_v1_contract_constant() -> None:
    from src.plugins import (
        PLUGIN_EXTENSION_SURFACE_VERSION,
        PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS,
    )

    assert PLUGIN_EXTENSION_SURFACE_VERSION == 1
    assert "Plugin" in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS


def test_plugins_api_list_and_toggle(tmp_path: Path) -> None:
    from src.application_services import (
        ApplicationServices,
        reset_application_services,
        set_application_services,
    )

    reset_application_services()
    store = PluginLifecycleStateStore(tmp_path / "state.json", persist=True)
    manager, _ = _manager(state_store=store)
    plugin = _RecordingPlugin(_manifest("api-plugin"))
    manager.register(plugin, source="external", package_root=tmp_path)
    manager.load("api-plugin")
    manager.bind_lifecycle_auditor(SecurityAuditRecorderStub())

    services = ApplicationServices(plugin_manager=manager, plugins_dir="")
    set_application_services(services)
    try:
        app = FastAPI()
        app.include_router(plugins_endpoint.router, prefix="/api/v1/plugins")
        client = TestClient(app)
        listed = client.get("/api/v1/plugins")
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == "api-plugin"
        assert body["items"][0]["state"] == "enabled"
        assert body["items"][0]["last_error_code"] is None

        health = client.get("/api/v1/plugins/health")
        assert health.status_code == 200
        health_body = health.json()
        assert health_body["total"] == 1
        assert health_body["plugins"][0]["plugin_id"] == "api-plugin"
        assert health_body["plugins"][0]["state"] == "enabled"
        assert health_body["plugins"][0]["last_error_code"] is None
        assert "generated_at" in health_body

        disabled = client.post(
            "/api/v1/plugins/api-plugin/lifecycle",
            json={"action": "disable"},
        )
        assert disabled.status_code == 200
        assert disabled.json()["success"] is True
        assert disabled.json()["state"] == "disabled"
        assert manager.snapshot("api-plugin").state == "disabled"
        assert store.is_disabled("api-plugin") is True

        enabled = client.post(
            "/api/v1/plugins/api-plugin/lifecycle",
            json={"action": "enable"},
        )
        assert enabled.status_code == 200
        assert enabled.json()["state"] == "enabled"

        restart = client.post(
            "/api/v1/plugins/api-plugin/lifecycle",
            json={"action": "reload"},
        )
        assert restart.status_code == 200
        assert "restart_required" in restart.json()
    finally:
        reset_application_services()


def test_plugins_api_attempt_audit_failure_prevents_mutation(tmp_path: Path) -> None:
    from src.application_services import (
        ApplicationServices,
        reset_application_services,
        set_application_services,
    )

    class FailingAttemptAudit(SecurityAuditRecorderStub):
        def record_attempt(self, **fields) -> None:
            raise SecurityAuditUnavailable()

    reset_application_services()
    manager, _ = _manager()
    plugin = _RecordingPlugin(_manifest("audit-attempt-plugin"))
    manager.register(plugin, source="external", package_root=tmp_path)
    manager.load("audit-attempt-plugin")
    manager.bind_lifecycle_auditor(FailingAttemptAudit())
    set_application_services(
        ApplicationServices(plugin_manager=manager, plugins_dir="")
    )
    try:
        app = FastAPI()
        app.include_router(plugins_endpoint.router, prefix="/api/v1/plugins")
        response = TestClient(app).post(
            "/api/v1/plugins/audit-attempt-plugin/lifecycle",
            json={"action": "disable"},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "error": "security_audit_unavailable",
            "message": "Security audit storage is unavailable",
            "operation_completed": False,
        }
        assert manager.snapshot("audit-attempt-plugin").state == "enabled"
        assert plugin.unload_count == 0
    finally:
        reset_application_services()


def test_plugins_api_completion_audit_failure_reports_real_outcome(
    tmp_path: Path,
) -> None:
    from src.application_services import (
        ApplicationServices,
        reset_application_services,
        set_application_services,
    )

    class FailingCompletionAudit(SecurityAuditRecorderStub):
        def record_completion(self, **fields) -> None:
            raise SecurityAuditUnavailable()

    reset_application_services()
    manager, _ = _manager()
    plugin = _RecordingPlugin(_manifest("audit-completion-plugin"))
    manager.register(plugin, source="external", package_root=tmp_path)
    manager.load("audit-completion-plugin")
    audit = FailingCompletionAudit()
    manager.bind_lifecycle_auditor(audit)
    set_application_services(
        ApplicationServices(plugin_manager=manager, plugins_dir="")
    )
    try:
        attempts_before = len(audit.attempts)
        app = FastAPI()
        app.include_router(plugins_endpoint.router, prefix="/api/v1/plugins")
        response = TestClient(app).post(
            "/api/v1/plugins/audit-completion-plugin/lifecycle",
            json={"action": "disable"},
        )
        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["error"] == "security_audit_unavailable"
        assert detail["operation_completed"] is True
        assert detail["operation_success"] is True
        assert detail["state"] == "disabled"
        assert detail["error_code"] is None
        assert detail["message"] is None
        assert detail["restart_required"] is False
        assert detail["reloaded"] is False
        assert manager.snapshot("audit-completion-plugin").state == "disabled"
        assert plugin.unload_count == 1
        operator_attempts = audit.attempts[attempts_before:]
        assert len(operator_attempts) == 1
        assert operator_attempts[0]["action"] == "plugin.disable"
        assert operator_attempts[0]["actor_type"] == "administrator"
        assert operator_attempts[0]["actor_id"] == "local_operator"
    finally:
        reset_application_services()


def test_plugins_api_completion_audit_failure_preserves_reload_result() -> None:
    from src.application_services import (
        ApplicationServices,
        reset_application_services,
        set_application_services,
    )

    class FailingCompletionAudit(SecurityAuditRecorderStub):
        def record_completion(self, **fields) -> None:
            raise SecurityAuditUnavailable()

    reset_application_services()
    manager, _ = _manager()
    plugin = _RecordingPlugin(_manifest("audit-reload-plugin"))
    manager.register(plugin, source="builtin")
    manager.load("audit-reload-plugin")
    manager.bind_lifecycle_auditor(FailingCompletionAudit())
    set_application_services(
        ApplicationServices(plugin_manager=manager, plugins_dir="")
    )
    try:
        app = FastAPI()
        app.include_router(plugins_endpoint.router, prefix="/api/v1/plugins")
        response = TestClient(app).post(
            "/api/v1/plugins/audit-reload-plugin/lifecycle",
            json={"action": "reload"},
        )

        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["error"] == "security_audit_unavailable"
        assert detail["operation_completed"] is True
        assert detail["operation_success"] is False
        assert detail["state"] == "enabled"
        assert detail["error_code"] == "plugin_reload_restart_required"
        assert detail["restart_required"] is True
        assert detail["reloaded"] is False
        assert "process restart" in detail["message"]
    finally:
        reset_application_services()
