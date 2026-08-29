# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Real persistence, runtime-context, and HTTP coverage for plugin settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.middlewares.error_handler import add_error_handlers
from src.api.v1.endpoints import plugins as plugins_endpoint
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.plugins import (
    Plugin,
    PluginContext,
    PluginLifecycleAuditCompletionUnavailable,
    PluginLifecycleStateStore,
    PluginManager,
    PluginManifest,
    PluginSettingsPersistenceError,
    PluginSettingsStore,
    PluginSettingsUpdateResult,
    PluginSettingsValidationError,
)
from src.services.security_audit_service import SecurityAuditUnavailable
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


def _valid_values(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "threshold": 0.8,
        "mode": "fast",
        "enabled": False,
        "api_token": "super-secret-token",
    }
    payload.update(overrides)
    return payload


def _issue_codes(exc: PluginSettingsValidationError) -> list[str]:
    return [issue["code"] for issue in exc.issues]


class _TrackingSettingsStore:
    def __init__(self, inner: PluginSettingsStore) -> None:
        self._inner = inner
        self.replace_calls = 0

    def values_for(self, plugin_id: str) -> dict[str, object]:
        return self._inner.values_for(plugin_id)

    def replace(self, plugin_id: str, values: dict[str, object]) -> None:
        self.replace_calls += 1
        self._inner.replace(plugin_id, values)


class _FailingReplaceStore:
    def __init__(self, inner: PluginSettingsStore) -> None:
        self._inner = inner

    def values_for(self, plugin_id: str) -> dict[str, object]:
        return self._inner.values_for(plugin_id)

    def replace(self, plugin_id: str, values: dict[str, object]) -> None:
        raise PluginSettingsPersistenceError()


class _FailingAttemptAudit(SecurityAuditRecorderStub):
    def record_attempt(self, **fields: object) -> None:
        raise SecurityAuditUnavailable()


class _FailingCompletionAudit(SecurityAuditRecorderStub):
    def record_completion(self, **fields: object) -> None:
        raise SecurityAuditUnavailable()


def test_settings_query_unknown_id_returns_none(tmp_path: Path) -> None:
    manager, _, _ = _manager(tmp_path)
    assert manager.settings_schema("missing-plugin") is None
    assert manager.settings_values("missing-plugin") is None


def test_settings_query_returns_schema_defaults_and_overrides(tmp_path: Path) -> None:
    manager, _, _ = _manager(tmp_path)
    schema = manager.settings_schema("configurable-plugin")
    assert schema is not None
    assert [field.key for field in schema] == [
        "threshold",
        "mode",
        "enabled",
        "api_token",
    ]
    assert manager.settings_values("configurable-plugin") == {
        "threshold": 0.5,
        "mode": "safe",
        "enabled": True,
    }
    created = manager.update_settings("configurable-plugin", _valid_values())
    assert created.success is True
    assert manager.settings_values("configurable-plugin") == {
        "threshold": 0.8,
        "mode": "fast",
        "enabled": False,
        "api_token": "super-secret-token",
    }


def test_settings_query_ignores_invalid_persisted_value(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager, _, _ = _manager(tmp_path)
    manager.settings_store.replace(
        "configurable-plugin",
        {"threshold": 99.0, "mode": "safe", "enabled": True},
    )
    with caplog.at_level("WARNING"):
        values = manager.settings_values("configurable-plugin")
    assert values == {
        "threshold": 0.5,
        "mode": "safe",
        "enabled": True,
    }
    assert any(
        record.levelname == "WARNING"
        and getattr(record, "error_code", None)
        == "plugin_setting_persisted_value_invalid"
        for record in caplog.records
    )


def test_update_settings_unknown_plugin_raises_key_error(tmp_path: Path) -> None:
    manager, _, _ = _manager(tmp_path)
    with pytest.raises(KeyError) as exc:
        manager.update_settings("missing-plugin", _valid_values())
    assert exc.value.args == ("missing-plugin",)


def test_update_settings_without_declared_settings_does_not_audit_or_persist(
    tmp_path: Path,
) -> None:
    audit = SecurityAuditRecorderStub()
    settings_path = tmp_path / "plugin_settings.json"
    manager = PluginManager(
        application_version="2.0.0",
        state_store=PluginLifecycleStateStore.memory(),
        settings_store=PluginSettingsStore(settings_path, persist=True),
        audit=audit,
    )
    plugin = Plugin(
        PluginManifest.model_validate(
            {
                "id": "plain-plugin",
                "name": "Plain Plugin",
                "version": "1.0.0",
                "minAppVersion": "1.0.0",
                "description": "No declared settings.",
                "author": "StockPulse Tests",
                "permissions": [],
            }
        )
    )
    assert manager.register(plugin, source="external", package_root=tmp_path).success
    with pytest.raises(PluginSettingsValidationError) as exc:
        manager.update_settings("plain-plugin", {"threshold": 0.1})
    assert _issue_codes(exc.value) == ["plugin_settings_not_declared"]
    assert audit.attempts == []
    assert audit.completions == []
    assert not settings_path.exists()
    assert manager.settings_store.values_for("plain-plugin") == {}


def test_update_settings_rejects_non_mapping_payload(tmp_path: Path) -> None:
    manager, _, settings_path = _manager(tmp_path)
    with pytest.raises(PluginSettingsValidationError) as exc:
        manager.update_settings("configurable-plugin", ["not-an-object"])  # type: ignore[arg-type]
    assert _issue_codes(exc.value) == ["invalid_settings_payload"]
    assert not settings_path.exists()


def test_update_settings_unknown_key_does_not_persist(tmp_path: Path) -> None:
    manager, _, settings_path = _manager(tmp_path)
    with pytest.raises(PluginSettingsValidationError) as exc:
        manager.update_settings("configurable-plugin", {"unknown": "value"})
    assert "unknown_plugin_setting" in _issue_codes(exc.value)
    assert not settings_path.exists()
    assert manager.settings_store.values_for("configurable-plugin") == {}


def test_update_settings_required_sensitive_missing_and_mask_without_existing(
    tmp_path: Path,
) -> None:
    manager, _, settings_path = _manager(tmp_path)
    with pytest.raises(PluginSettingsValidationError) as omitted:
        manager.update_settings(
            "configurable-plugin",
            {"threshold": 0.1, "mode": "safe", "enabled": True},
        )
    assert "required_plugin_setting_missing" in _issue_codes(omitted.value)
    with pytest.raises(PluginSettingsValidationError) as masked:
        manager.update_settings(
            "configurable-plugin",
            _valid_values(api_token="******"),
        )
    assert "required_plugin_setting_missing" in _issue_codes(masked.value)
    assert not settings_path.exists()
    assert manager.settings_store.values_for("configurable-plugin") == {}


def test_update_settings_mask_token_preserves_existing_secret(tmp_path: Path) -> None:
    manager, _, _ = _manager(tmp_path)
    created = manager.update_settings("configurable-plugin", _valid_values())
    assert created.success is True
    preserved = manager.update_settings(
        "configurable-plugin",
        _valid_values(threshold=0.9, api_token="******"),
    )
    assert preserved.success is True
    stored = manager.settings_store.values_for("configurable-plugin")
    assert stored["api_token"] == "super-secret-token"
    assert stored["threshold"] == 0.9
    assert "******" not in stored.values()


def test_update_settings_identical_payload_skips_replace(tmp_path: Path) -> None:
    manager, _, _ = _manager(tmp_path)
    tracking = _TrackingSettingsStore(manager.settings_store)
    manager._settings_store = tracking
    first = manager.update_settings("configurable-plugin", _valid_values())
    assert first.success is True
    assert first.changed_keys
    assert tracking.replace_calls == 1
    second = manager.update_settings("configurable-plugin", _valid_values())
    assert second.success is True
    assert second.changed_keys == ()
    assert second.restart_required is False
    assert tracking.replace_calls == 1


def test_update_settings_changed_enabled_requires_restart(tmp_path: Path) -> None:
    manager, plugin, _ = _manager(tmp_path)
    assert manager.snapshot(plugin.manifest.id).state == "enabled"
    result = manager.update_settings("configurable-plugin", _valid_values())
    assert result.success is True
    assert result.changed_keys
    assert result.restart_required is True


def test_update_settings_changed_disabled_does_not_require_restart(
    tmp_path: Path,
) -> None:
    manager, plugin, _ = _manager(tmp_path)
    assert manager.disable(plugin.manifest.id).success
    assert manager.snapshot(plugin.manifest.id).state == "disabled"
    result = manager.update_settings("configurable-plugin", _valid_values())
    assert result.success is True
    assert result.changed_keys
    assert result.restart_required is False


def test_update_settings_persistence_failure_audits_then_reraises(
    tmp_path: Path,
) -> None:
    audit = SecurityAuditRecorderStub()
    settings_path = tmp_path / "plugin_settings.json"
    inner = PluginSettingsStore(settings_path, persist=True)
    inner.replace(
        "configurable-plugin",
        {"threshold": 0.5, "mode": "safe", "enabled": True, "api_token": "kept-secret"},
    )
    manager = PluginManager(
        application_version="2.0.0",
        state_store=PluginLifecycleStateStore.memory(),
        settings_store=_FailingReplaceStore(inner),
        audit=audit,
    )
    plugin = _RecordingPlugin()
    assert manager.register(plugin, source="external", package_root=tmp_path).success
    assert manager.load(plugin.manifest.id).success
    with pytest.raises(PluginSettingsPersistenceError):
        manager.update_settings("configurable-plugin", _valid_values())
    assert inner.values_for("configurable-plugin") == {
        "threshold": 0.5,
        "mode": "safe",
        "enabled": True,
        "api_token": "kept-secret",
    }
    assert json.loads(settings_path.read_text(encoding="utf-8"))["plugins"][
        "configurable-plugin"
    ]["api_token"] == "kept-secret"
    assert [item["action"] for item in audit.attempts][-1] == "plugin.settings.update"
    completion = audit.completions[-1]
    assert completion["action"] == "plugin.settings.update"
    assert completion["outcome"] == "failure"
    assert completion["reason_code"] == "plugin_settings_write_failed"


def test_update_settings_audit_completion_unavailable_keeps_successful_result(
    tmp_path: Path,
) -> None:
    manager, _, settings_path = _manager(tmp_path)
    manager.bind_lifecycle_auditor(_FailingCompletionAudit())
    with pytest.raises(PluginLifecycleAuditCompletionUnavailable) as exc:
        manager.update_settings(
            "configurable-plugin",
            _valid_values(),
            require_audit=True,
        )
    result = exc.value.result
    assert isinstance(result, PluginSettingsUpdateResult)
    assert result.success is True
    assert result.plugin_id == "configurable-plugin"
    assert result.changed_keys
    assert result.restart_required is True
    assert manager.settings_store.values_for("configurable-plugin")["api_token"] == (
        "super-secret-token"
    )
    disk = json.loads(settings_path.read_text(encoding="utf-8"))
    assert disk["plugins"]["configurable-plugin"]["api_token"] == "super-secret-token"


def test_update_settings_require_audit_fails_closed_before_persist(
    tmp_path: Path,
) -> None:
    manager, _, settings_path = _manager(tmp_path)
    manager.bind_lifecycle_auditor(_FailingAttemptAudit())
    with pytest.raises(SecurityAuditUnavailable):
        manager.update_settings(
            "configurable-plugin",
            _valid_values(),
            require_audit=True,
        )
    assert not settings_path.exists()
    assert manager.settings_store.values_for("configurable-plugin") == {}

    disabled = PluginManager(
        application_version="2.0.0",
        state_store=PluginLifecycleStateStore.memory(),
        settings_store=PluginSettingsStore(tmp_path / "disabled.json", persist=True),
        audit_enabled=False,
    )
    plugin = _RecordingPlugin()
    assert disabled.register(plugin, source="external", package_root=tmp_path).success
    assert disabled.load(plugin.manifest.id).success
    with pytest.raises(SecurityAuditUnavailable):
        disabled.update_settings(
            "configurable-plugin",
            _valid_values(),
            require_audit=True,
        )
    assert disabled.settings_store.values_for("configurable-plugin") == {}


def test_update_settings_public_reexports_remain_on_manager_facade() -> None:
    import src.plugins as plugins_root
    import src.plugins.manager as manager_mod

    assert plugins_root.PluginManager is manager_mod.PluginManager
    assert plugins_root.PluginSettingsUpdateResult is manager_mod.PluginSettingsUpdateResult
    assert (
        plugins_root.PluginSettingsValidationError
        is manager_mod.PluginSettingsValidationError
    )
    assert plugins_root.PluginLifecycleAuditCompletionUnavailable is (
        manager_mod.PluginLifecycleAuditCompletionUnavailable
    )


def test_plugins_api_settings_audit_completion_unavailable_keeps_persisted_values(
    tmp_path: Path,
) -> None:
    reset_application_services()
    manager, _, settings_path = _manager(tmp_path)
    manager.bind_lifecycle_auditor(_FailingCompletionAudit())
    set_application_services(ApplicationServices(plugin_manager=manager, plugins_dir=""))
    app = FastAPI()
    add_error_handlers(app)
    app.include_router(plugins_endpoint.router, prefix="/api/v1/plugins")
    try:
        response = TestClient(app).put(
            "/api/v1/plugins/configurable-plugin/settings",
            json={"values": _valid_values()},
        )
        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "security_audit_unavailable"
        params = body["params"]
        assert params["operation_completed"] is True
        assert params["operation_success"] is True
        assert params["restart_required"] is True
        assert manager.settings_store.values_for("configurable-plugin")["api_token"] == (
            "super-secret-token"
        )
        disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert disk["plugins"]["configurable-plugin"]["api_token"] == "super-secret-token"
    finally:
        reset_application_services()
