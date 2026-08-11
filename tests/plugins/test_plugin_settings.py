# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Real persistence, runtime-context, and HTTP coverage for plugin settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import plugins as plugins_endpoint
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.plugins import (
    Plugin,
    PluginContext,
    PluginLifecycleStateStore,
    PluginManager,
    PluginManifest,
    PluginSettingsPersistenceError,
    PluginSettingsStore,
    PluginSettingsValidationError,
)
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": "configurable-plugin",
            "name": "Configurable Plugin",
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": "Plugin settings integration fixture.",
            "author": "StockPulse Tests",
            "permissions": [],
            "settings": [
                {
                    "key": "threshold",
                    "title": "Threshold",
                    "dataType": "number",
                    "uiControl": "number",
                    "defaultValue": 0.5,
                    "validation": {"minimum": 0.0, "maximum": 1.0},
                    "displayOrder": 10,
                },
                {
                    "key": "mode",
                    "title": "Mode",
                    "dataType": "string",
                    "uiControl": "select",
                    "defaultValue": "safe",
                    "options": [
                        {"label": "Safe", "value": "safe"},
                        {"label": "Fast", "value": "fast"},
                    ],
                    "displayOrder": 20,
                },
                {
                    "key": "enabled",
                    "title": "Feature enabled",
                    "dataType": "boolean",
                    "uiControl": "switch",
                    "defaultValue": True,
                    "displayOrder": 30,
                },
                {
                    "key": "api_token",
                    "title": "API token",
                    "dataType": "string",
                    "uiControl": "password",
                    "isSensitive": True,
                    "isRequired": True,
                    "validation": {"minLength": 8, "maxLength": 128},
                    "displayOrder": 40,
                },
            ],
        }
    )


class _RecordingPlugin(Plugin):
    def __init__(self) -> None:
        super().__init__(_manifest())
        self.loaded_settings: list[dict[str, object]] = []

    def onload(self, context: PluginContext) -> None:
        self.loaded_settings.append(dict(context.settings))


def _manager(tmp_path: Path) -> tuple[PluginManager, _RecordingPlugin, Path]:
    settings_path = tmp_path / "plugin_settings.json"
    manager = PluginManager(
        application_version="2.0.0",
        state_store=PluginLifecycleStateStore.memory(),
        settings_store=PluginSettingsStore(settings_path, persist=True),
        audit=SecurityAuditRecorderStub(),
    )
    plugin = _RecordingPlugin()
    assert manager.register(plugin, source="external", package_root=tmp_path).success
    assert manager.load(plugin.manifest.id).success
    return manager, plugin, settings_path


def test_settings_store_round_trip_and_failed_write_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = PluginSettingsStore(path, persist=True)
    store.replace("configurable-plugin", {"threshold": 0.75, "enabled": True})

    reloaded = PluginSettingsStore(path, persist=True)
    assert reloaded.values_for("configurable-plugin") == {
        "enabled": True,
        "threshold": 0.75,
    }
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1

    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("file", encoding="utf-8")
    failing = PluginSettingsStore(blocked_parent / "settings.json", persist=True)
    with pytest.raises(PluginSettingsPersistenceError):
        failing.replace("configurable-plugin", {"threshold": 0.9})
    assert failing.values_for("configurable-plugin") == {}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_manager_rejects_non_finite_values(tmp_path: Path, value: float) -> None:
    manager, _, _ = _manager(tmp_path)
    with pytest.raises(PluginSettingsValidationError):
        manager.update_settings(
            "configurable-plugin",
            {
                "threshold": value,
                "mode": "safe",
                "enabled": True,
                "api_token": "long-enough-token",
            },
        )


def test_real_plugins_api_masks_persists_and_supplies_settings_on_enable(tmp_path: Path) -> None:
    reset_application_services()
    manager, plugin, settings_path = _manager(tmp_path)
    set_application_services(ApplicationServices(plugin_manager=manager, plugins_dir=""))
    app = FastAPI()
    add_error_handlers(app)
    app.include_router(plugins_endpoint.router, prefix="/api/v1/plugins")
    client = TestClient(app)
    try:
        listed = client.get("/api/v1/plugins")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["settings_count"] == 4

        initial = client.get("/api/v1/plugins/configurable-plugin/settings")
        assert initial.status_code == 200
        initial_body = initial.json()
        assert [field["key"] for field in initial_body["schema"]] == [
            "threshold",
            "mode",
            "enabled",
            "api_token",
        ]
        assert initial_body["values"] == {
            "threshold": 0.5,
            "mode": "safe",
            "enabled": True,
        }

        invalid = client.put(
            "/api/v1/plugins/configurable-plugin/settings",
            json={"values": {"unknown": "value"}},
        )
        assert invalid.status_code == 400
        assert invalid.json()["details"]["issues"][0]["code"] == "unknown_plugin_setting"
        assert not settings_path.exists()

        updated = client.put(
            "/api/v1/plugins/configurable-plugin/settings",
            json={
                "values": {
                    "threshold": 0.8,
                    "mode": "fast",
                    "enabled": False,
                    "api_token": "super-secret-token",
                }
            },
        )
        assert updated.status_code == 200
        updated_body = updated.json()
        assert updated_body["restart_required"] is True
        assert updated_body["values"]["api_token"] == updated_body["mask_token"]
        assert updated_body["masked_keys"] == ["api_token"]
        assert "super-secret-token" not in updated.text

        preserved = client.put(
            "/api/v1/plugins/configurable-plugin/settings",
            json={
                "mask_token": updated_body["mask_token"],
                "values": {
                    "threshold": 0.9,
                    "mode": "fast",
                    "enabled": False,
                    "api_token": updated_body["mask_token"],
                },
            },
        )
        assert preserved.status_code == 200
        assert manager.settings_store.values_for("configurable-plugin")["api_token"] == "super-secret-token"

        assert plugin.loaded_settings[-1] == {
            "threshold": 0.5,
            "mode": "safe",
            "enabled": True,
        }
        disabled = client.post(
            "/api/v1/plugins/configurable-plugin/lifecycle",
            json={"action": "disable"},
        )
        assert disabled.status_code == 200
        enabled = client.post(
            "/api/v1/plugins/configurable-plugin/lifecycle",
            json={"action": "enable"},
        )
        assert enabled.status_code == 200
        assert plugin.loaded_settings[-1]["threshold"] == 0.9
        assert plugin.loaded_settings[-1]["api_token"] == "super-secret-token"

        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["plugins"]["configurable-plugin"]["api_token"] == "super-secret-token"
    finally:
        reset_application_services()


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_real_plugins_api_rejects_non_finite_json(tmp_path: Path, literal: str) -> None:
    reset_application_services()
    manager, _, _ = _manager(tmp_path)
    set_application_services(ApplicationServices(plugin_manager=manager, plugins_dir=""))
    app = FastAPI()
    add_error_handlers(app)
    app.include_router(plugins_endpoint.router, prefix="/api/v1/plugins")
    try:
        response = TestClient(app).put(
            "/api/v1/plugins/configurable-plugin/settings",
            content=(
                '{"values":{"threshold":'
                + literal
                + ',"mode":"safe","enabled":true,"api_token":"long-enough-token"}}'
            ),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422
        assert response.json()["error"] == "validation_error"
        assert literal not in response.text
    finally:
        reset_application_services()
