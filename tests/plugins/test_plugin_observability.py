# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Lifecycle audit, health check, and data-provider auto-bind regressions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from data_provider import DataFetcherManager, DataProvider, DataProviderRegistration
from src.plugins import (
    PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV,
    PLUGIN_LIFECYCLE_EVENT_TYPE,
    ExtensionContract,
    ExtensionRegistry,
    Plugin,
    PluginContext,
    PluginLifecycleAuditor,
    PluginManager,
    PluginManifest,
    build_data_provider_bound_registry,
    data_provider_auto_bind_enabled,
    try_build_auto_bound_registry,
)
from src.services.security_audit_service import SecurityAuditUnavailable
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.2.3",
            "minAppVersion": "1.0.0",
            "description": "Observability fixture.",
            "author": "StockPulse Tests",
            "permissions": [],
            "apiVersion": "1",
        }
    )


@dataclass
class _Template:
    template_id: str


class _RecordingPlugin(Plugin):
    def __init__(
        self,
        manifest: PluginManifest,
        *,
        fail_onload: bool = False,
        registration_id: str = "fixture",
    ) -> None:
        super().__init__(manifest)
        self.fail_onload = fail_onload
        self.registration_id = registration_id
        self.load_count = 0
        self.unload_count = 0

    def onload(self, context: PluginContext) -> None:
        self.load_count += 1
        context.register(
            "report_template",
            self.registration_id,
            _Template(self.registration_id),
        )
        if self.fail_onload:
            raise RuntimeError("token=onload-secret")

    def onunload(self) -> None:
        self.unload_count += 1


def _manager(audit: Any = None) -> PluginManager:
    registry = ExtensionRegistry(
        {
            "report_template": ExtensionContract(
                identity_resolver=lambda implementation: implementation.template_id,
                validator=lambda implementation: isinstance(implementation, _Template),
            )
        }
    )
    return PluginManager(
        application_version="2.0.0",
        registry=registry,
        audit=audit,
        audit_enabled=audit is not None,
    )


class _FailingAudit(SecurityAuditRecorderStub):
    def record_attempt(self, **fields: Any) -> None:
        raise SecurityAuditUnavailable()

    def record_completion(self, **fields: Any) -> None:
        raise SecurityAuditUnavailable()


class _FallbackProvider(DataProvider):
    name = "ObservabilityFallbackProvider"
    priority = 500

    def get_daily_data(
        self,
        stock_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 30,
    ) -> pd.DataFrame:
        del stock_code, start_date, end_date, days
        return pd.DataFrame(
            {
                "date": ["2026-01-02"],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1],
                "amount": [1.0],
                "pct_chg": [0.0],
            }
        )


class _FailingProvider(DataProvider):
    name = "ObservabilityFailingProvider"
    priority = 10

    def get_daily_data(
        self,
        stock_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 30,
    ) -> pd.DataFrame:
        del stock_code, start_date, end_date, days
        raise RuntimeError("provider unavailable")


class _FailingProviderPlugin(Plugin):
    def onload(self, context: PluginContext) -> None:
        context.register(
            "data_provider",
            "observability-failing-provider",
            DataProviderRegistration(
                provider_id="observability-failing-provider",
                factory=_FailingProvider,
                markets=frozenset({"cn"}),
                capabilities=frozenset({"daily_data"}),
            ),
            contract_version="1",
            priority=_FailingProvider.priority,
        )


def test_lifecycle_audit_records_load_enable_disable_and_onload_failed() -> None:
    audit = SecurityAuditRecorderStub()
    manager = _manager(audit)
    healthy = _RecordingPlugin(_manifest("stockpulse.healthy-plugin"))
    failing = _RecordingPlugin(
        _manifest("stockpulse.failing-plugin"),
        fail_onload=True,
        registration_id="failing",
    )
    manager.register(healthy, source="builtin")
    manager.register(failing, source="builtin")

    assert manager.load("stockpulse.healthy-plugin").success is True
    assert manager.disable("stockpulse.healthy-plugin").success is True
    assert manager.enable("stockpulse.healthy-plugin").success is True
    failed = manager.load("stockpulse.failing-plugin")
    assert failed.success is False
    assert failed.error_code == "plugin_onload_failed"

    actions = [item["action"] for item in audit.completions]
    assert actions == [
        "plugin.load",
        "plugin.disable",
        "plugin.enable",
        "plugin.load",
    ]
    assert all(
        item["event_type"] == PLUGIN_LIFECYCLE_EVENT_TYPE for item in audit.attempts
    )
    assert all(
        item["event_type"] == PLUGIN_LIFECYCLE_EVENT_TYPE for item in audit.completions
    )
    assert audit.completions[0]["outcome"] == "success"
    assert audit.completions[0]["target_id"] == "stockpulse.healthy-plugin"
    last = audit.completions[-1]
    assert last["outcome"] == "failure"
    assert last["reason_code"] == "plugin_onload_failed"
    assert last["target_id"] == "stockpulse.failing-plugin"
    assert last["metadata"]["error_code"] == "plugin_onload_failed"
    assert "token=onload-secret" not in repr(audit.attempts + audit.completions)


def test_lifecycle_auditor_reuses_lazy_default_recorder(monkeypatch) -> None:
    audit = SecurityAuditRecorderStub()
    factory_calls = 0

    def build_recorder():
        nonlocal factory_calls
        factory_calls += 1
        return audit

    monkeypatch.setattr(
        "src.services.security_audit_service.get_security_audit_service",
        build_recorder,
    )
    auditor = PluginLifecycleAuditor()

    first = auditor.begin(plugin_id="stockpulse.first", operation="load")
    auditor.complete(
        plugin_id="stockpulse.first",
        operation="load",
        success=True,
        correlation_id=first,
    )
    second = auditor.begin(plugin_id="stockpulse.second", operation="enable")
    auditor.complete(
        plugin_id="stockpulse.second",
        operation="enable",
        success=True,
        correlation_id=second,
    )

    assert factory_calls == 1
    assert auditor.recorder is audit
    assert len(audit.attempts) == 2
    assert len(audit.completions) == 2


def test_lifecycle_audit_records_reload_completion(tmp_path: Path) -> None:
    audit = SecurityAuditRecorderStub()
    package = tmp_path / "external-plugin"
    package.mkdir()
    (package / "manifest.json").write_text(
        """
        {
          "id": "stockpulse.reload-audit",
          "name": "Reload Audit",
          "version": "1.0.0",
          "minAppVersion": "1.0.0",
          "description": "Reload audit fixture",
          "author": "StockPulse Tests",
          "permissions": [],
          "apiVersion": "1",
          "entrypoint": "plugin.py:Plugin"
        }
        """.strip(),
        encoding="utf-8",
    )
    (package / "plugin.py").write_text(
        "from src.plugins import Plugin as BasePlugin\n"
        "\n"
        "class Plugin(BasePlugin):\n"
        "    def onload(self, context):\n"
        "        return None\n",
        encoding="utf-8",
    )
    registry = ExtensionRegistry()
    manager = PluginManager(
        application_version="2.0.0",
        registry=registry,
        audit=audit,
        audit_enabled=True,
    )
    from src.plugins.loader import ExternalPluginLoader

    loaded = ExternalPluginLoader(manager).register_one(package)
    assert loaded.success is True
    assert manager.load("stockpulse.reload-audit").success is True

    attempts_before = len(audit.attempts)
    completions_before = len(audit.completions)
    reload_result = manager.reload("stockpulse.reload-audit")
    assert reload_result.success is True
    assert reload_result.reloaded is True

    reload_attempts = audit.attempts[attempts_before:]
    reload_completions = audit.completions[completions_before:]
    assert [item["action"] for item in reload_attempts] == ["plugin.reload"]
    assert [item["action"] for item in reload_completions] == ["plugin.reload"]
    assert reload_completions[0]["outcome"] == "success"
    assert reload_completions[0]["target_id"] == "stockpulse.reload-audit"
    assert (
        reload_completions[0]["correlation_id"]
        == reload_attempts[0]["correlation_id"]
    )


def test_lifecycle_audit_failure_does_not_block_plugin_load() -> None:
    manager = _manager(_FailingAudit())
    plugin = _RecordingPlugin(_manifest("stockpulse.audit-isolated"))
    manager.register(plugin, source="builtin")

    result = manager.load("stockpulse.audit-isolated")

    assert result.success is True
    assert result.state == "enabled"
    assert plugin.load_count == 1


def test_operator_enable_of_registered_plugin_audits_enable_not_startup_load() -> None:
    audit = SecurityAuditRecorderStub()
    manager = _manager(audit)
    plugin = _RecordingPlugin(_manifest("stockpulse.operator-enable"))
    manager.register(plugin, source="builtin")

    result = manager.set_enabled(
        "stockpulse.operator-enable",
        True,
        require_audit=True,
        actor_type="administrator",
        actor_id="local_operator",
    )

    assert result.success is True
    assert result.operation == "enable"
    assert [event["action"] for event in audit.attempts] == ["plugin.enable"]
    assert [event["action"] for event in audit.completions] == ["plugin.enable"]
    assert audit.attempts[0]["actor_type"] == "administrator"


def test_health_check_exposes_state_and_last_error_code() -> None:
    manager = _manager()
    healthy = _RecordingPlugin(_manifest("stockpulse.healthy-plugin"))
    failing = _RecordingPlugin(
        _manifest("stockpulse.failing-plugin"),
        fail_onload=True,
        registration_id="failing",
    )
    manager.register(healthy, source="builtin")
    manager.register(failing, source="builtin")
    manager.load("stockpulse.healthy-plugin")
    manager.load("stockpulse.failing-plugin")

    report = manager.health_check()
    by_id = {entry.plugin_id: entry for entry in report.plugins}

    assert report.total == 2
    assert by_id["stockpulse.healthy-plugin"].state == "enabled"
    assert by_id["stockpulse.healthy-plugin"].last_error_code is None
    assert by_id["stockpulse.healthy-plugin"].version == "1.2.3"
    assert "report_template" in by_id["stockpulse.healthy-plugin"].extension_points
    assert by_id["stockpulse.failing-plugin"].state == "failed"
    assert by_id["stockpulse.failing-plugin"].last_error_code == "plugin_onload_failed"

    as_dict = report.as_dict()
    assert as_dict["total"] == 2
    assert isinstance(as_dict["generated_at"], str)
    assert as_dict["plugins"][0]["plugin_id"]


def test_last_error_survives_disable_and_clears_after_successful_recovery() -> None:
    manager = _manager()
    plugin = _RecordingPlugin(
        _manifest("stockpulse.recovery-plugin"),
        fail_onload=True,
    )
    manager.register(plugin, source="builtin")

    assert manager.load("stockpulse.recovery-plugin").success is False
    assert manager.disable("stockpulse.recovery-plugin").success is True
    assert (
        manager.health_check().plugins[0].last_error_code
        == "plugin_onload_failed"
    )

    plugin.fail_onload = False
    assert manager.enable("stockpulse.recovery-plugin").success is True
    assert manager.health_check().plugins[0].last_error_code is None


def test_single_plugin_failure_does_not_block_other_plugins() -> None:
    manager = _manager()
    failing = _RecordingPlugin(
        _manifest("stockpulse.failing-plugin"),
        fail_onload=True,
        registration_id="failing",
    )
    healthy = _RecordingPlugin(_manifest("stockpulse.healthy-plugin"))
    manager.register(failing, source="builtin")
    manager.register(healthy, source="builtin")

    results = manager.load_all()

    assert [item.success for item in results] == [False, True]
    assert manager.snapshot("stockpulse.failing-plugin").state == "failed"
    assert manager.snapshot("stockpulse.healthy-plugin").state == "enabled"
    health = manager.health_check()
    assert {entry.plugin_id: entry.state for entry in health.plugins} == {
        "stockpulse.failing-plugin": "failed",
        "stockpulse.healthy-plugin": "enabled",
    }


def test_data_provider_auto_bind_flag_defaults_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, raising=False)
    assert data_provider_auto_bind_enabled() is False
    monkeypatch.setenv(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, "false")
    assert data_provider_auto_bind_enabled() is False
    monkeypatch.setenv(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, "true")
    assert data_provider_auto_bind_enabled() is True


def test_data_provider_auto_bind_flag_loads_through_shared_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.config import Config

    monkeypatch.setenv("ENV_FILE", os.devnull)
    monkeypatch.setenv(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, "true")
    config = Config._load_from_env()

    assert config.plugin_data_provider_auto_bind_enabled is True
    assert data_provider_auto_bind_enabled(config) is True


def test_data_provider_auto_bind_discovers_providers_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.application_services import ApplicationServices
    from src.plugins import PLUGIN_APPLICATION_VERSION

    example = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "plugins"
        / "example-provider"
    )
    import shutil

    shutil.copytree(example, tmp_path / "example-provider")
    monkeypatch.setenv("PLUGINS_DIR", str(tmp_path))
    monkeypatch.setenv(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, "true")
    monkeypatch.setenv("PROVIDER_ADAPTIVE_PRIORITY_ENABLED", "false")
    monkeypatch.setenv("PROVIDER_CIRCUIT_BREAKER_ENABLED", "false")
    monkeypatch.setenv("PROVIDER_DAILY_CACHE_ENABLED", "false")
    DataFetcherManager.reset_daily_source_health()

    providers = DataFetcherManager(fetchers=[_FallbackProvider()])
    registry, error = try_build_auto_bound_registry(providers)
    assert error is None
    assert registry is providers.plugin_registry

    plugins = PluginManager(
        application_version=PLUGIN_APPLICATION_VERSION,
        registry=registry,
        audit_enabled=False,
    )
    services = ApplicationServices(plugin_manager=plugins)
    try:
        loads = services.start_plugins()
        assert any(result.success for result in loads)
        assert "ExampleReferenceProvider" in providers.available_fetchers
        frame, source = providers.get_daily_data("600519")
        assert source == "ExampleReferenceProvider"
        assert len(frame) == 2
    finally:
        services.close()
        DataFetcherManager.reset_daily_source_health()


def test_data_provider_auto_bind_off_keeps_manual_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.application_services import ApplicationServices
    from src.plugins import PLUGIN_APPLICATION_VERSION

    example = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "plugins"
        / "example-provider"
    )
    import shutil

    shutil.copytree(example, tmp_path / "example-provider")
    monkeypatch.setenv("PLUGINS_DIR", str(tmp_path))
    monkeypatch.delenv(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, raising=False)

    providers = DataFetcherManager(fetchers=[_FallbackProvider()])
    # Default process-style manager: unbound data_provider contract.
    plugins = PluginManager(
        application_version=PLUGIN_APPLICATION_VERSION,
        audit_enabled=False,
    )
    services = ApplicationServices(plugin_manager=plugins)
    try:
        services.start_plugins()
        # Plugin may load but provider is not injected into this manager.
        assert providers.available_fetchers == ["ObservabilityFallbackProvider"]
    finally:
        services.close()


def test_build_data_provider_bound_registry_requires_live_backend() -> None:
    providers = DataFetcherManager(fetchers=[_FallbackProvider()])
    registry = build_data_provider_bound_registry(providers)
    contract = registry.extension_contract("data_provider")
    assert contract.backend is not None
    assert registry is not providers.plugin_registry

    unbound = try_build_auto_bound_registry(
        providers,
        env={PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV: "false"},
    )
    assert unbound == (None, None)

    bound, error = try_build_auto_bound_registry(
        providers,
        env={PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV: "true"},
    )
    assert error is None
    assert bound is providers.plugin_registry


def test_application_services_auto_bind_composition_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default ApplicationServices must call auto-bind when the flag is on."""

    from src.application_services import (
        ApplicationServices,
        reset_application_services,
        set_application_services,
    )
    from src.config import Config
    from src.services.stock_service import StockService

    example = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "plugins"
        / "example-provider"
    )
    import shutil

    shutil.copytree(example, tmp_path / "example-provider")
    monkeypatch.setenv("PLUGINS_DIR", str(tmp_path))
    # The application root must honor its injected Config without consulting
    # the ambient environment a second time.
    monkeypatch.delenv(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, raising=False)
    monkeypatch.setenv("PROVIDER_ADAPTIVE_PRIORITY_ENABLED", "false")
    monkeypatch.setenv("PROVIDER_CIRCUIT_BREAKER_ENABLED", "false")
    monkeypatch.setenv("PROVIDER_DAILY_CACHE_ENABLED", "false")
    DataFetcherManager.reset_daily_source_health()

    # Inject a manager with one fallback so offline daily data still resolves.
    providers = DataFetcherManager(fetchers=[_FallbackProvider()])
    services = ApplicationServices(
        config=Config(plugin_data_provider_auto_bind_enabled=True),
        data_fetcher_manager=providers,
        plugins_dir=tmp_path,
    )
    set_application_services(services)
    try:
        assert services.data_fetcher_manager is providers
        assert services.plugin_manager.registry is providers.plugin_registry
        loads = services.start_plugins()
        assert any(result.success for result in loads)
        assert "ExampleReferenceProvider" in providers.available_fetchers
        result = StockService().get_history_data("600519")
        assert [item["close"] for item in result["data"]] == [100.5, 101.25]
    finally:
        reset_application_services()
        DataFetcherManager.reset_daily_source_health()


def test_application_services_bound_provider_failure_uses_service_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.application_services import (
        ApplicationServices,
        reset_application_services,
        set_application_services,
    )
    from src.config import Config
    from src.services.stock_service import StockService

    monkeypatch.setenv(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, "true")
    monkeypatch.setenv("PROVIDER_ADAPTIVE_PRIORITY_ENABLED", "false")
    monkeypatch.setenv("PROVIDER_CIRCUIT_BREAKER_ENABLED", "false")
    monkeypatch.setenv("PROVIDER_DAILY_CACHE_ENABLED", "false")
    DataFetcherManager.reset_daily_source_health()
    providers = DataFetcherManager(fetchers=[_FallbackProvider()])
    plugin = _FailingProviderPlugin(_manifest("stockpulse.failing-provider"))
    services = ApplicationServices(
        config=Config(plugin_data_provider_auto_bind_enabled=True),
        data_fetcher_manager=providers,
        builtin_plugins=(plugin,),
        plugins_dir="",
    )
    set_application_services(services)
    try:
        assert services.start_plugins()[0].success is True
        result = StockService().get_history_data("600519")
        assert [item["close"] for item in result["data"]] == [1.0]
    finally:
        reset_application_services()
        DataFetcherManager.reset_daily_source_health()


def test_application_services_auto_bind_defaults_off_keeps_unbound_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.application_services import ApplicationServices
    from src.config import Config

    monkeypatch.delenv(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, raising=False)
    services = ApplicationServices(
        config=Config(plugin_data_provider_auto_bind_enabled=False),
        builtin_plugins=(),
    )
    try:
        assert services.data_fetcher_manager is None
        # Unbound process registry is not a DataFetcherManager registry.
        assert services.plugin_manager.registry is not None
    finally:
        services.close()
