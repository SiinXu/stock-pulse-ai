# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Runtime regressions for plugin-owned notification channels."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

from src.application_services import (
    ApplicationServices,
    get_application_services,
    get_installed_application_services,
    reset_application_services,
    set_application_services,
)
from main import __dispatch_cli
from src.config import Config
from src.core.pipeline import StockAnalysisPipeline
from src.core.pipeline_stage_results import PipelineStageRunner
from src.enums import ReportType
from src.notification import NotificationService
from src.notification_noise import reset_notification_noise_state
from src.plugins import (
    NotificationAdapterResult,
    NotificationChannelRegistry,
    NotificationRequest,
    Plugin,
    PluginContext,
    PluginManager,
    PluginManifest,
    build_application_extension_registry,
    build_notification_channel_extension_contract,
)


@pytest.fixture(autouse=True)
def _clean_application_root():
    reset_application_services()
    reset_notification_noise_state()
    yield
    reset_application_services()
    reset_notification_noise_state()


def _config(**overrides: object) -> Config:
    return Config(stock_list=[], **overrides)


def _manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": f"Test notification plugin {plugin_id}",
            "author": "StockPulse tests",
            "permissions": [],
        }
    )


class _NotificationPlugin(Plugin):
    def __init__(
        self,
        plugin_id: str,
        factory: object,
        events: list[str] | None = None,
    ) -> None:
        super().__init__(_manifest(plugin_id))
        self._factory = factory
        self._events = events

    def onload(self, context: PluginContext) -> None:
        if self._events is not None:
            self._events.append(f"load:{self.manifest.id}")
        context.register(
            "notification_channel",
            self._factory.channel_id,  # type: ignore[attr-defined]
            self._factory,
        )

    def onunload(self) -> None:
        if self._events is not None:
            self._events.append(f"unload:{self.manifest.id}")


def _adapter_factory(
    channel_id: str,
    calls: list[NotificationRequest],
    *,
    available: bool = True,
    result: NotificationAdapterResult | None = None,
    send_callback: Callable[[NotificationRequest], object] | None = None,
    configs: list[object] | None = None,
):
    class Adapter:
        display_name = f"Test {channel_id}"

        def __init__(self, config: object) -> None:
            if configs is not None:
                configs.append(config)

        def is_available(self) -> bool:
            return available

        def send(self, request: NotificationRequest) -> object:
            calls.append(request)
            if send_callback is not None:
                return send_callback(request)
            return result or NotificationAdapterResult(success=True)

    Adapter.channel_id = channel_id
    return Adapter


def _install(
    monkeypatch: pytest.MonkeyPatch,
    config: Config,
    *plugins: Plugin,
) -> ApplicationServices:
    services = ApplicationServices(
        config=config,
        builtin_plugins=plugins,
        plugins_dir="",
    )
    set_application_services(services)
    return services


def test_register_route_and_result_mapping_use_the_core_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[NotificationRequest] = []
    configs: list[object] = []
    factory = _adapter_factory(
        "private_log",
        calls,
        result=NotificationAdapterResult(
            success=False,
            error_code="temporary_failure",
            retryable=True,
            diagnostics="token=private-token https://private.example/hook",
        ),
        configs=configs,
    )
    config = _config(
        notification_report_channels=["private_log"],
        custom_webhook_urls=["https://core.example/hook"],
    )
    unrelated_global_config = _config()
    monkeypatch.setattr(
        "src.notification.get_config",
        lambda: unrelated_global_config,
    )
    services = _install(
        monkeypatch,
        config,
        _NotificationPlugin("test.private-log", factory),
    )
    service = NotificationService()
    static_calls: list[str] = []
    monkeypatch.setattr(
        service,
        "send_to_custom",
        lambda content: static_calls.append(content) or True,
    )

    dispatch = service.send_with_results(
        "private report",
        email_stock_codes=["600519"],
        route_type="report",
        severity="warning",
    )

    assert services.plugin_load_results[0].success is True
    assert configs == [config]
    assert service._config is config
    assert len(calls) == 1
    assert calls[0].content == "private report"
    assert calls[0].route_type == "report"
    assert calls[0].severity == "warning"
    assert calls[0].stock_codes == ("600519",)
    assert dict(calls[0].metadata) == {}
    with pytest.raises(TypeError):
        calls[0].metadata["mutated"] = True  # type: ignore[index]
    assert static_calls == []
    assert dispatch.dispatched is True
    assert dispatch.success is False
    assert dispatch.status == "all_failed"
    assert len(dispatch.channel_results) == 1
    attempt = dispatch.channel_results[0]
    assert attempt.channel == "private_log"
    assert attempt.error_code == "temporary_failure"
    assert attempt.retryable is True
    assert "private-token" not in (attempt.diagnostics or "")
    assert "private.example" not in (attempt.diagnostics or "")


def test_unavailable_or_unmatched_plugin_route_never_falls_back_to_broadcast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[NotificationRequest] = []
    config = _config(
        notification_report_channels=["offline_sink"],
        custom_webhook_urls=["https://core.example/hook"],
    )
    _install(
        monkeypatch,
        config,
        _NotificationPlugin(
            "test.offline-sink",
            _adapter_factory("offline_sink", calls, available=False),
        ),
    )
    service = NotificationService()
    static_calls: list[str] = []
    monkeypatch.setattr(
        service,
        "send_to_custom",
        lambda content: static_calls.append(content) or True,
    )

    dispatch = service.send_with_results("report", route_type="report")

    assert dispatch.dispatched is False
    assert dispatch.status == "no_channel"
    assert calls == []
    assert static_calls == []


def test_availability_failures_are_redacted_and_later_plugin_remains_target(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[NotificationRequest] = []

    def factory_with_availability(channel_id: str, probe: Callable[[], object]):
        class Adapter:
            display_name = f"Test {channel_id}"

            def __init__(self, _config: object) -> None:
                return None

            def is_available(self) -> object:
                return probe()

            def send(
                self,
                request: NotificationRequest,
            ) -> NotificationAdapterResult:
                calls.append(request)
                return NotificationAdapterResult(success=True)

        Adapter.channel_id = channel_id
        return Adapter

    def raise_secret() -> object:
        raise RuntimeError(
            "token=availability-secret https://private.example/hook"
        )

    _install(
        monkeypatch,
        _config(),
        _NotificationPlugin(
            "test.availability-exception",
            factory_with_availability("availability_exception", raise_secret),
        ),
        _NotificationPlugin(
            "test.availability-invalid",
            factory_with_availability(
                "availability_invalid",
                lambda: "yes",
            ),
        ),
        _NotificationPlugin(
            "test.availability-healthy",
            factory_with_availability("availability_healthy", lambda: True),
        ),
    )
    service = NotificationService()

    with caplog.at_level(logging.WARNING):
        with service._notification_delivery_snapshot(None) as targets:
            target_ids = [target.channel_id for target in targets]

    assert target_ids == ["availability_healthy"]
    assert "notification_channel_availability_failed" in caplog.text
    assert "notification_channel_availability_invalid" in caplog.text
    assert "availability-secret" not in caplog.text
    assert "private.example" not in caplog.text


def test_real_check_notify_formats_plugin_lifecycle_states_without_enum_crash(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    available_calls: list[NotificationRequest] = []
    unavailable_calls: list[NotificationRequest] = []
    disabled_calls: list[NotificationRequest] = []

    class FailedFactory:
        channel_id = "failed_sink"
        display_name = "Failed Sink"

        def __init__(self, _config: object) -> None:
            return None

        def is_available(self, required: object) -> bool:
            return bool(required)

        def send(
            self,
            request: NotificationRequest,
        ) -> NotificationAdapterResult:
            return NotificationAdapterResult(success=bool(request))

    config = _config(
        custom_webhook_urls=["https://core.example/hook"],
        notification_report_channels=[
            "custom",
            "available_sink",
            "unavailable_sink",
            "disabled_sink",
            "failed_sink",
            "unknown_sink",
        ]
    )
    services = _install(
        monkeypatch,
        config,
        _NotificationPlugin(
            "test.cli-available",
            _adapter_factory("available_sink", available_calls),
        ),
        _NotificationPlugin(
            "test.cli-unavailable",
            _adapter_factory(
                "unavailable_sink",
                unavailable_calls,
                available=False,
            ),
        ),
        _NotificationPlugin(
            "test.cli-disabled",
            _adapter_factory("disabled_sink", disabled_calls),
        ),
        _NotificationPlugin("test.cli-failed", FailedFactory),
    )
    assert services.plugin_manager.disable("test.cli-disabled").success is True

    exit_code = __dispatch_cli(
        config,
        SimpleNamespace(check_notify=True),
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "自定义Webhook" in output
    assert "Test available_sink (available_sink): available" in output
    assert (
        "Test unavailable_sink (unavailable_sink): enabled_unavailable"
        in output
    )
    assert "Test disabled_sink (disabled_sink): disabled" in output
    assert "Failed Sink (failed_sink): failed" in output
    assert "unknown_sink (unknown_sink): unknown" in output


def test_root_close_records_terminal_unloaded_channel_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _install(
        monkeypatch,
        _config(),
        _NotificationPlugin(
            "test.unloaded-state",
            _adapter_factory("unloaded_state", []),
        ),
    )
    registry = services.notification_channel_registry

    services.close()

    assert [
        (entry.channel_id, entry.state)
        for entry in registry.lifecycle_snapshot()
    ] == [("unloaded_state", "unloaded")]


def test_adapter_exception_is_redacted_and_later_channel_still_runs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    failed_calls: list[NotificationRequest] = []
    healthy_calls: list[NotificationRequest] = []

    def fail(_request: NotificationRequest) -> NotificationAdapterResult:
        raise RuntimeError("token=private-token https://private.example/hook")

    config = _config()
    _install(
        monkeypatch,
        config,
        _NotificationPlugin(
            "test.failing-channel",
            _adapter_factory(
                "failing_channel",
                failed_calls,
                send_callback=fail,
            ),
        ),
        _NotificationPlugin(
            "test.healthy-channel",
            _adapter_factory("healthy_channel", healthy_calls),
        ),
    )
    service = NotificationService()

    with caplog.at_level(logging.ERROR):
        dispatch = service.send_with_results("report")

    assert [attempt.channel for attempt in dispatch.channel_results] == [
        "failing_channel",
        "healthy_channel",
    ]
    assert dispatch.status == "partial_failed"
    assert dispatch.success is True
    assert dispatch.channel_results[0].error_code == "exception"
    assert "private-token" not in (
        dispatch.channel_results[0].diagnostics or ""
    )
    assert "private-token" not in caplog.text
    assert "private.example" not in caplog.text
    assert len(failed_calls) == 1
    assert len(healthy_calls) == 1


def test_custom_manager_derives_or_rejects_exact_notification_registry_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    native_registry = NotificationChannelRegistry(lambda: config)
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_application_extension_registry(
            lambda: object(),
            additional_contracts={
                "notification_channel": (
                    build_notification_channel_extension_contract(
                        native_registry
                    )
                )
            },
        ),
    )

    services = ApplicationServices(
        config=config,
        plugin_manager=manager,
        plugins_dir="",
    )
    assert services.notification_channel_registry is native_registry

    mismatched_registry = NotificationChannelRegistry(lambda: config)
    other_manager = PluginManager(
        application_version="3.26.3",
        registry=build_application_extension_registry(
            lambda: object(),
            additional_contracts={
                "notification_channel": (
                    build_notification_channel_extension_contract(
                        native_registry
                    )
                )
            },
        ),
    )
    with pytest.raises(ValueError, match="must be paired"):
        ApplicationServices(
            config=config,
            plugin_manager=other_manager,
            notification_channel_registry=mismatched_registry,
            plugins_dir="",
        )

    manager_without_notification_backend = PluginManager(
        application_version="3.26.3",
        registry=build_application_extension_registry(lambda: object()),
    )
    with pytest.raises(ValueError, match="must be paired"):
        ApplicationServices(
            config=config,
            plugin_manager=manager_without_notification_backend,
            notification_channel_registry=mismatched_registry,
            plugins_dir="",
        )


def test_notification_registry_config_authority_must_match_application_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_config = _config()
    other_config = _config(notification_report_channels=["other_sink"])
    native_registry = NotificationChannelRegistry(lambda: other_config)
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_application_extension_registry(
            lambda: object(),
            additional_contracts={
                "notification_channel": (
                    build_notification_channel_extension_contract(
                        native_registry
                    )
                )
            },
        ),
    )

    with pytest.raises(ValueError, match="Config must be paired"):
        ApplicationServices(
            config=root_config,
            plugin_manager=manager,
            plugins_dir="",
        )


def test_disable_and_reenable_rebuilds_adapter_from_the_same_root_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_config = _config(notification_report_channels=["reload_sink"])
    unrelated_global_config = _config()
    configs: list[object] = []
    calls: list[NotificationRequest] = []
    services = _install(
        monkeypatch,
        root_config,
        _NotificationPlugin(
            "test.reload-sink",
            _adapter_factory("reload_sink", calls, configs=configs),
        ),
    )
    monkeypatch.setattr(
        "src.notification.get_config",
        lambda: unrelated_global_config,
    )

    first_service = NotificationService()
    disable_result = services.plugin_manager.disable("test.reload-sink")
    enable_result = services.plugin_manager.enable("test.reload-sink")
    second_service = NotificationService()

    assert disable_result.success is True
    assert disable_result.deferred is False
    assert enable_result.success is True
    assert configs == [root_config, root_config]
    assert first_service._config is root_config
    assert second_service._config is root_config


def test_default_root_reload_updates_service_then_reenable_refreshes_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_config = _config(notification_report_channels=["refresh_sink"])
    second_config = _config(notification_report_channels=["refresh_sink"])
    current_config = [first_config]
    configs: list[object] = []
    monkeypatch.setattr(
        "src.config.get_config",
        lambda: current_config[0],
    )
    services = ApplicationServices(
        builtin_plugins=(
            _NotificationPlugin(
                "test.refresh-sink",
                _adapter_factory("refresh_sink", [], configs=configs),
            ),
        ),
        plugins_dir="",
    )
    set_application_services(services)

    first_service = NotificationService()
    current_config[0] = second_config
    second_service = NotificationService()

    assert first_service._config is first_config
    assert second_service._config is second_config
    assert configs == [first_config]

    assert services.plugin_manager.disable("test.refresh-sink").success is True
    assert services.plugin_manager.enable("test.refresh-sink").success is True
    assert configs == [first_config, second_config]


def test_report_only_service_defers_default_root_until_delivery_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    monkeypatch.setattr("src.notification.get_config", lambda: config)
    monkeypatch.setattr("src.config.get_config", lambda: config)

    service = NotificationService()

    assert get_installed_application_services() is None
    assert service._config is config
    assert service.is_available() is False
    installed = get_installed_application_services()
    assert installed is not None
    assert installed.config is config
    assert service._application_services is installed


def test_lazy_delivery_binding_rejects_a_different_root_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_config = _config()
    root_config = _config(notification_report_channels=["other_sink"])
    monkeypatch.setattr(
        "src.notification.get_config",
        lambda: service_config,
    )
    service = NotificationService()
    set_application_services(
        ApplicationServices(config=root_config, plugins_dir="")
    )

    with pytest.raises(RuntimeError, match="Config are not paired"):
        service.is_available()


def test_custom_manager_without_notification_backend_keeps_builtin_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(custom_webhook_urls=["https://core.example/hook"])
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_application_extension_registry(lambda: object()),
    )
    services = ApplicationServices(
        config=config,
        plugin_manager=manager,
        plugins_dir="",
    )
    set_application_services(services)
    service = NotificationService()
    monkeypatch.setattr(service, "send_to_custom", lambda _content: True)

    assert manager.registry.native_backend("notification_channel") is None
    assert services.notification_channel_registry.snapshot() == ()
    assert service.send("builtin") is True


def test_invalid_adapter_result_fails_closed_and_later_channel_still_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_calls: list[NotificationRequest] = []
    healthy_calls: list[NotificationRequest] = []
    config = _config()
    _install(
        monkeypatch,
        config,
        _NotificationPlugin(
            "test.invalid-result",
            _adapter_factory(
                "invalid_result",
                invalid_calls,
                send_callback=lambda _request: object(),
            ),
        ),
        _NotificationPlugin(
            "test.after-invalid-result",
            _adapter_factory("after_invalid", healthy_calls),
        ),
    )

    dispatch = NotificationService().send_with_results("report")

    assert dispatch.success is True
    assert dispatch.status == "partial_failed"
    assert [attempt.channel for attempt in dispatch.channel_results] == [
        "invalid_result",
        "after_invalid",
    ]
    assert dispatch.channel_results[0].error_code == (
        "notification_adapter_result_invalid"
    )
    assert len(invalid_calls) == 1
    assert len(healthy_calls) == 1


def test_factory_failure_is_redacted_and_does_not_block_later_plugin(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingFactory:
        channel_id = "factory_failure"
        display_name = "Factory Failure"

        def __init__(self, _config: object) -> None:
            raise RuntimeError(
                "token=private-factory-token https://private.example/factory"
            )

    healthy_calls: list[NotificationRequest] = []
    with caplog.at_level(logging.ERROR):
        services = _install(
            monkeypatch,
            _config(),
            _NotificationPlugin("test.factory-failure", FailingFactory),
            _NotificationPlugin(
                "test.after-factory-failure",
                _adapter_factory("after_factory_failure", healthy_calls),
            ),
        )

    assert [result.success for result in services.plugin_load_results] == [
        False,
        True,
    ]
    assert services.plugin_load_results[0].error_code == (
        "native_registry_registration_failed"
    )
    assert [
        entry.channel_id
        for entry in services.notification_channel_registry.snapshot()
    ] == ["after_factory_failure"]
    assert "private-factory-token" not in caplog.text
    assert "private.example" not in caplog.text


@pytest.mark.parametrize(
    "bad_factory",
    (
        type(
            "OptionalFactoryArgument",
            (),
            {
                "channel_id": "bad_signature",
                "display_name": "Bad Signature",
                "__init__": lambda self, _config, optional=None: None,
                "is_available": lambda self: True,
                "send": lambda self, request: NotificationAdapterResult(
                    success=bool(request)
                ),
            },
        ),
        type(
            "AvailabilityNeedsArgument",
            (),
            {
                "channel_id": "bad_signature",
                "display_name": "Bad Signature",
                "__init__": lambda self, _config: None,
                "is_available": lambda self, required: bool(required),
                "send": lambda self, request: NotificationAdapterResult(
                    success=bool(request)
                ),
            },
        ),
        type(
            "SendNeedsArgument",
            (),
            {
                "channel_id": "bad_signature",
                "display_name": "Bad Signature",
                "__init__": lambda self, _config: None,
                "is_available": lambda self: True,
                "send": lambda self, request, required: NotificationAdapterResult(
                    success=bool(request) and bool(required)
                ),
            },
        ),
        type(
            "OptionalAvailabilityArgument",
            (),
            {
                "channel_id": "bad_signature",
                "display_name": "Bad Signature",
                "__init__": lambda self, _config: None,
                "is_available": lambda self, optional=None: optional is None,
                "send": lambda self, request: NotificationAdapterResult(
                    success=bool(request)
                ),
            },
        ),
        type(
            "VariadicSend",
            (),
            {
                "channel_id": "bad_signature",
                "display_name": "Bad Signature",
                "__init__": lambda self, _config: None,
                "is_available": lambda self: True,
                "send": lambda self, request, *extra: NotificationAdapterResult(
                    success=bool(request) and not extra
                ),
            },
        ),
        type(
            "MismatchedDisplayName",
            (),
            {
                "channel_id": "bad_signature",
                "display_name": "Factory Name",
                "__init__": lambda self, _config: setattr(
                    self, "display_name", "Adapter Name"
                ),
                "is_available": lambda self: True,
                "send": lambda self, request: NotificationAdapterResult(
                    success=bool(request)
                ),
            },
        ),
    ),
)
def test_invalid_adapter_shape_fails_before_publication_and_later_plugin_loads(
    monkeypatch: pytest.MonkeyPatch,
    bad_factory: object,
) -> None:
    healthy_calls: list[NotificationRequest] = []
    services = _install(
        monkeypatch,
        _config(),
        _NotificationPlugin("test.bad-adapter-shape", bad_factory),
        _NotificationPlugin(
            "test.after-bad-adapter-shape",
            _adapter_factory("after_bad_shape", healthy_calls),
        ),
    )

    assert [result.success for result in services.plugin_load_results] == [
        False,
        True,
    ]
    assert [
        entry.channel_id
        for entry in services.notification_channel_registry.snapshot()
    ] == ["after_bad_shape"]


def test_hostile_adapter_descriptor_fails_closed_and_later_plugin_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HostileAdapter:
        channel_id = "hostile_descriptor"
        display_name = "Hostile Descriptor"

        @property
        def is_available(self):
            raise RuntimeError("token=descriptor-secret https://private.example")

        def send(self, request: NotificationRequest) -> NotificationAdapterResult:
            return NotificationAdapterResult(success=bool(request))

    class HostileFactory:
        channel_id = "hostile_descriptor"
        display_name = "Hostile Descriptor"

        def __init__(self, _config: object) -> None:
            return None

        def __new__(cls, _config: object):
            return object.__new__(HostileAdapter)

    healthy_calls: list[NotificationRequest] = []
    services = _install(
        monkeypatch,
        _config(),
        _NotificationPlugin("test.hostile-descriptor", HostileFactory),
        _NotificationPlugin(
            "test.after-hostile-descriptor",
            _adapter_factory("after_hostile", healthy_calls),
        ),
    )

    assert [result.success for result in services.plugin_load_results] == [
        False,
        True,
    ]
    assert [
        entry.channel_id
        for entry in services.notification_channel_registry.snapshot()
    ] == ["after_hostile"]


def test_core_applies_noise_and_image_prep_before_adapter_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[NotificationRequest] = []
    config = _config(
        markdown_to_image_channels=["image_sink"],
        notification_dedup_ttl_seconds=60,
    )
    _install(
        monkeypatch,
        config,
        _NotificationPlugin(
            "test.image-sink",
            _adapter_factory("image_sink", calls),
        ),
    )
    image_calls: list[str] = []
    monkeypatch.setattr(
        "src.md2img.markdown_to_image",
        lambda content, **_kwargs: image_calls.append(content) or b"image-bytes",
    )
    service = NotificationService()

    first = service.send_with_results("report", dedup_key="plugin-image")
    second = service.send_with_results("report", dedup_key="plugin-image")

    assert first.success is True
    assert second.status == "noise_suppressed"
    assert len(calls) == 1
    assert calls[0].image_bytes == b"image-bytes"
    assert image_calls == ["report"]


def test_default_aggregate_pipeline_delivers_plugin_once_with_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[NotificationRequest] = []
    config = _config(notification_report_channels=["aggregate_sink"])
    _install(
        monkeypatch,
        config,
        _NotificationPlugin(
            "test.aggregate-sink",
            _adapter_factory("aggregate_sink", calls),
        ),
    )
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    pipeline.notifier = NotificationService()
    pipeline.config = config
    pipeline._generate_aggregate_report = lambda _results, _report_type: "report"
    pipeline._refresh_saved_diagnostic_snapshot = lambda **_kwargs: None
    results = [SimpleNamespace(code="600519", query_id="aggregate-query")]

    first = pipeline._send_notifications(results, ReportType.SIMPLE)
    second = pipeline._send_notifications(results, ReportType.SIMPLE)

    assert first is None
    assert second is None
    assert len(calls) == 1
    assert calls[0].content == "report"
    assert calls[0].route_type == "report"
    assert calls[0].severity == "info"
    assert calls[0].stock_codes == ("600519",)


def test_builtin_and_plugin_canonical_id_collisions_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_calls: list[NotificationRequest] = []
    second_calls: list[NotificationRequest] = []
    config = _config()
    services = _install(
        monkeypatch,
        config,
        _NotificationPlugin(
            "test.builtin-collision",
            _adapter_factory("wechat", []),
        ),
        _NotificationPlugin(
            "test.first-owner",
            _adapter_factory("duplicate_sink", first_calls),
        ),
        _NotificationPlugin(
            "test.second-owner",
            _adapter_factory("duplicate_sink", second_calls),
        ),
    )

    assert [result.success for result in services.plugin_load_results] == [
        False,
        True,
        False,
    ]
    assert [result.error_code for result in services.plugin_load_results] == [
        "native_registration_conflict",
        None,
        "extension_registration_conflict",
    ]
    assert [
        entry.channel_id
        for entry in services.notification_channel_registry.snapshot()
    ] == ["duplicate_sink"]


def test_disable_and_unload_remove_adapter_from_later_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[NotificationRequest] = []
    events: list[str] = []
    config = _config(notification_report_channels=["removable_sink"])
    services = _install(
        monkeypatch,
        config,
        _NotificationPlugin(
            "test.removable-sink",
            _adapter_factory("removable_sink", calls),
            events,
        ),
    )
    service = NotificationService()

    assert service.send("first", route_type="report") is True
    assert services.plugin_manager.disable("test.removable-sink").success is True
    with caplog.at_level(logging.WARNING):
        second = service.send_with_results("second", route_type="report")

    assert second.dispatched is False
    assert second.status == "no_channel"
    assert len(calls) == 1
    assert events == [
        "load:test.removable-sink",
        "unload:test.removable-sink",
    ]
    assert "removable_sink" in caplog.text
    assert services.notification_channel_registry.snapshot() == ()


def test_dispatch_snapshot_survives_plugin_disable_during_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_calls: list[NotificationRequest] = []
    second_calls: list[NotificationRequest] = []
    services_holder: list[ApplicationServices] = []
    second_unloaded = threading.Event()

    def disable_second(
        _request: NotificationRequest,
    ) -> NotificationAdapterResult:
        result = services_holder[0].plugin_manager.disable(
            "test.snapshot-second"
        )
        assert result.success is False
        assert result.state == "enabled"
        assert result.error_code == "plugin_lifecycle_deferred"
        assert result.deferred is True
        return NotificationAdapterResult(success=True)

    def send_second(
        _request: NotificationRequest,
    ) -> NotificationAdapterResult:
        assert second_unloaded.is_set() is False
        return NotificationAdapterResult(success=True)

    class SecondPlugin(_NotificationPlugin):
        def onunload(self) -> None:
            second_unloaded.set()
            super().onunload()

    config = _config()
    services = _install(
        monkeypatch,
        config,
        _NotificationPlugin(
            "test.snapshot-first",
            _adapter_factory(
                "snapshot_first",
                first_calls,
                send_callback=disable_second,
            ),
        ),
        SecondPlugin(
            "test.snapshot-second",
            _adapter_factory(
                "snapshot_second",
                second_calls,
                send_callback=send_second,
            ),
        ),
    )
    services_holder.append(services)
    service = NotificationService()

    first = service.send_with_results("first")
    second = service.send_with_results("second")

    assert [attempt.channel for attempt in first.channel_results] == [
        "snapshot_first",
        "snapshot_second",
    ]
    assert len(second_calls) == 1
    assert [attempt.channel for attempt in second.channel_results] == [
        "snapshot_first"
    ]
    assert [
        entry.channel_id
        for entry in services.notification_channel_registry.snapshot()
    ] == ["snapshot_first"]
    assert second_unloaded.is_set() is True


def test_dispatch_reader_can_reenter_after_queueing_same_thread_disable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[NotificationRequest] = []
    services_holder: list[ApplicationServices] = []
    service_holder: list[NotificationService] = []
    nested_dispatches: list[object] = []
    unloaded = threading.Event()

    def disable_then_reenter(
        request: NotificationRequest,
    ) -> NotificationAdapterResult:
        if request.content == "outer":
            result = services_holder[0].plugin_manager.disable(
                "test.reentrant-reader"
            )
            assert result.error_code == "plugin_lifecycle_deferred"
            assert result.deferred is True
            nested_dispatches.append(
                service_holder[0].send_with_results("inner")
            )
            assert unloaded.is_set() is False
        return NotificationAdapterResult(success=True)

    class ResourcePlugin(_NotificationPlugin):
        def onunload(self) -> None:
            unloaded.set()
            super().onunload()

    services = _install(
        monkeypatch,
        _config(),
        ResourcePlugin(
            "test.reentrant-reader",
            _adapter_factory(
                "reentrant_reader",
                calls,
                send_callback=disable_then_reenter,
            ),
        ),
    )
    services_holder.append(services)
    service = NotificationService()
    service_holder.append(service)

    outer_dispatch = service.send_with_results("outer")

    assert outer_dispatch.success is True
    assert nested_dispatches[0].success is True
    assert [request.content for request in calls] == ["outer", "inner"]
    assert unloaded.is_set() is True
    assert services.notification_channel_registry.snapshot() == ()


def test_deferred_disable_blocks_new_snapshot_until_existing_readers_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_started = threading.Event()
    release_existing = threading.Event()
    disable_queued = threading.Event()
    origin_done = threading.Event()
    later_done = threading.Event()
    unloaded = threading.Event()
    calls: list[NotificationRequest] = []
    services_holder: list[ApplicationServices] = []

    def send(
        request: NotificationRequest,
    ) -> NotificationAdapterResult:
        if request.content == "existing":
            existing_started.set()
            assert release_existing.wait(timeout=5)
        elif request.content == "origin":
            result = services_holder[0].plugin_manager.disable(
                "test.deferred-writer-preference"
            )
            assert result.error_code == "plugin_lifecycle_deferred"
            assert result.deferred is True
            disable_queued.set()
        return NotificationAdapterResult(success=True)

    class ResourcePlugin(_NotificationPlugin):
        def onunload(self) -> None:
            unloaded.set()
            super().onunload()

    services = _install(
        monkeypatch,
        _config(),
        ResourcePlugin(
            "test.deferred-writer-preference",
            _adapter_factory(
                "deferred_writer_preference",
                calls,
                send_callback=send,
            ),
        ),
    )
    services_holder.append(services)
    service = NotificationService()
    dispatches: dict[str, object] = {}
    existing = threading.Thread(
        target=lambda: dispatches.update(
            existing=service.send_with_results("existing")
        )
    )
    origin = threading.Thread(
        target=lambda: (
            dispatches.update(origin=service.send_with_results("origin")),
            origin_done.set(),
        )
    )
    later = threading.Thread(
        target=lambda: (
            dispatches.update(later=service.send_with_results("later")),
            later_done.set(),
        )
    )
    existing.start()
    assert existing_started.wait(timeout=5)
    origin.start()
    assert disable_queued.wait(timeout=5)
    assert origin_done.wait(timeout=5)
    later.start()

    try:
        assert later_done.wait(timeout=0.2) is False
        assert unloaded.is_set() is False
    finally:
        release_existing.set()
        existing.join(timeout=5)
        origin.join(timeout=5)
        later.join(timeout=5)

    assert existing.is_alive() is False
    assert origin.is_alive() is False
    assert later.is_alive() is False
    assert unloaded.is_set() is True
    assert [request.content for request in calls] == ["existing", "origin"]
    assert dispatches["existing"].success is True
    assert dispatches["origin"].success is True
    assert dispatches["later"].status == "no_channel"


@pytest.mark.parametrize("lifecycle_operation", ("replace", "reset", "close"))
def test_concurrent_root_lifecycle_waits_for_inflight_adapter(
    monkeypatch: pytest.MonkeyPatch,
    lifecycle_operation: str,
) -> None:
    send_started = threading.Event()
    release_send = threading.Event()
    lifecycle_done = threading.Event()
    unloaded = threading.Event()
    observations: list[bool] = []
    calls: list[NotificationRequest] = []

    def blocking_send(
        _request: NotificationRequest,
    ) -> NotificationAdapterResult:
        send_started.set()
        assert release_send.wait(timeout=5)
        observations.append(unloaded.is_set())
        return NotificationAdapterResult(success=True)

    class ResourcePlugin(_NotificationPlugin):
        def onunload(self) -> None:
            unloaded.set()
            super().onunload()

    first = _install(
        monkeypatch,
        _config(),
        ResourcePlugin(
            "test.blocking-root-lifecycle",
            _adapter_factory(
                "blocking_root_lifecycle",
                calls,
                send_callback=blocking_send,
            ),
        ),
    )
    second = ApplicationServices(config=_config(), plugins_dir="")
    service = NotificationService()
    send_results: list[object] = []

    sender = threading.Thread(
        target=lambda: send_results.append(
            service.send_with_results("report")
        )
    )

    def run_lifecycle() -> None:
        if lifecycle_operation == "replace":
            set_application_services(second)
        elif lifecycle_operation == "reset":
            reset_application_services()
        else:
            first.close()
        lifecycle_done.set()

    lifecycle = threading.Thread(target=run_lifecycle)
    sender.start()
    assert send_started.wait(timeout=5)
    lifecycle.start()

    try:
        assert lifecycle_done.wait(timeout=0.2) is False
        assert unloaded.is_set() is False
    finally:
        release_send.set()
        sender.join(timeout=5)
        lifecycle.join(timeout=5)

    assert sender.is_alive() is False
    assert lifecycle.is_alive() is False
    assert observations == [False]
    assert unloaded.is_set() is True
    assert len(calls) == 1
    assert send_results[0].success is True


def test_same_thread_root_replacement_is_deferred_until_send_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unloaded = threading.Event()
    observed_roots: list[ApplicationServices] = []
    calls: list[NotificationRequest] = []
    second = ApplicationServices(config=_config(), plugins_dir="")

    def replace_root(
        _request: NotificationRequest,
    ) -> NotificationAdapterResult:
        set_application_services(second)
        observed_roots.append(get_application_services())
        assert unloaded.is_set() is False
        return NotificationAdapterResult(success=True)

    class ReplacedPlugin(_NotificationPlugin):
        def onunload(self) -> None:
            unloaded.set()
            super().onunload()

    first = _install(
        monkeypatch,
        _config(),
        ReplacedPlugin(
            "test.same-thread-replacement",
            _adapter_factory(
                "same_thread_replacement",
                calls,
                send_callback=replace_root,
            ),
        ),
    )

    dispatch = NotificationService().send_with_results("report")

    assert dispatch.success is True
    assert observed_roots == [first]
    assert get_application_services() is second
    assert unloaded.is_set() is True
    assert len(calls) == 1


def test_concurrent_disable_waits_for_both_inflight_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    both_started = threading.Event()
    release_sends = threading.Event()
    disable_done = threading.Event()
    unloaded = threading.Event()
    calls: list[NotificationRequest] = []
    send_count = 0
    send_count_lock = threading.Lock()

    def blocking_send(
        _request: NotificationRequest,
    ) -> NotificationAdapterResult:
        nonlocal send_count
        with send_count_lock:
            send_count += 1
            if send_count == 2:
                both_started.set()
        assert release_sends.wait(timeout=5)
        assert unloaded.is_set() is False
        return NotificationAdapterResult(success=True)

    class ResourcePlugin(_NotificationPlugin):
        def onunload(self) -> None:
            unloaded.set()
            super().onunload()

    services = _install(
        monkeypatch,
        _config(),
        ResourcePlugin(
            "test.two-inflight-sends",
            _adapter_factory(
                "two_inflight_sends",
                calls,
                send_callback=blocking_send,
            ),
        ),
    )
    service = NotificationService()
    dispatches: list[object] = []
    senders = [
        threading.Thread(
            target=lambda content=content: dispatches.append(
                service.send_with_results(content)
            )
        )
        for content in ("first", "second")
    ]
    for sender in senders:
        sender.start()
    assert both_started.wait(timeout=5)

    disable_results: list[object] = []
    disable = threading.Thread(
        target=lambda: (
            disable_results.append(
                services.plugin_manager.disable("test.two-inflight-sends")
            ),
            disable_done.set(),
        )
    )
    disable.start()

    try:
        assert disable_done.wait(timeout=0.2) is False
        assert unloaded.is_set() is False
    finally:
        release_sends.set()
        for sender in senders:
            sender.join(timeout=5)
        disable.join(timeout=5)

    assert all(sender.is_alive() is False for sender in senders)
    assert disable.is_alive() is False
    assert len(calls) == 2
    assert all(dispatch.success is True for dispatch in dispatches)
    assert disable_results[0].success is True
    assert disable_results[0].deferred is False
    assert unloaded.is_set() is True


def test_adapter_exception_releases_lease_for_waiting_disable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send_started = threading.Event()
    release_send = threading.Event()
    disable_done = threading.Event()
    unloaded = threading.Event()

    def failing_send(
        _request: NotificationRequest,
    ) -> NotificationAdapterResult:
        send_started.set()
        assert release_send.wait(timeout=5)
        raise RuntimeError("token=lease-secret https://private.example/hook")

    class ResourcePlugin(_NotificationPlugin):
        def onunload(self) -> None:
            unloaded.set()
            super().onunload()

    services = _install(
        monkeypatch,
        _config(),
        ResourcePlugin(
            "test.exception-lease",
            _adapter_factory(
                "exception_lease",
                [],
                send_callback=failing_send,
            ),
        ),
    )
    service = NotificationService()
    dispatches: list[object] = []
    sender = threading.Thread(
        target=lambda: dispatches.append(
            service.send_with_results("report")
        )
    )
    disable_results: list[object] = []
    disable = threading.Thread(
        target=lambda: (
            disable_results.append(
                services.plugin_manager.disable("test.exception-lease")
            ),
            disable_done.set(),
        )
    )
    sender.start()
    assert send_started.wait(timeout=5)
    disable.start()

    try:
        assert disable_done.wait(timeout=0.2) is False
    finally:
        release_send.set()
        sender.join(timeout=5)
        disable.join(timeout=5)

    assert sender.is_alive() is False
    assert disable.is_alive() is False
    assert dispatches[0].status == "all_failed"
    assert disable_results[0].success is True
    assert unloaded.is_set() is True


def test_external_replacement_can_join_sender_with_deferred_disable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disable_queued = threading.Event()
    release_send = threading.Event()
    replacement_done = threading.Event()
    sender_holder: list[threading.Thread] = []
    services_holder: list[ApplicationServices] = []
    deferred_results: list[object] = []
    join_observations: list[bool] = []

    def queue_disable(
        _request: NotificationRequest,
    ) -> NotificationAdapterResult:
        deferred_results.append(
            services_holder[0].plugin_manager.disable(
                "test.join-safe-disable"
            )
        )
        disable_queued.set()
        assert release_send.wait(timeout=5)
        return NotificationAdapterResult(success=True)

    class JoiningPlugin(_NotificationPlugin):
        def onunload(self) -> None:
            sender_holder[0].join(timeout=5)
            join_observations.append(sender_holder[0].is_alive())
            super().onunload()

    first = _install(
        monkeypatch,
        _config(),
        JoiningPlugin(
            "test.join-safe-disable",
            _adapter_factory(
                "join_safe_disable",
                [],
                send_callback=queue_disable,
            ),
        ),
    )
    services_holder.append(first)
    second = ApplicationServices(config=_config(), plugins_dir="")
    service = NotificationService()
    dispatches: list[object] = []
    sender = threading.Thread(
        target=lambda: dispatches.append(
            service.send_with_results("report")
        )
    )
    sender_holder.append(sender)
    replacement = threading.Thread(
        target=lambda: (
            set_application_services(second),
            replacement_done.set(),
        )
    )
    sender.start()
    assert disable_queued.wait(timeout=5)
    replacement.start()

    try:
        assert replacement_done.wait(timeout=0.2) is False
    finally:
        release_send.set()
        sender.join(timeout=5)
        replacement.join(timeout=5)

    assert sender.is_alive() is False
    assert replacement.is_alive() is False
    assert deferred_results[0].deferred is True
    assert join_observations == [False]
    assert dispatches[0].success is True
    assert get_application_services() is second


def test_external_replacement_owns_deferred_unload_before_sender_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disable_queued = threading.Event()
    release_send = threading.Event()
    replacement_close_entered = threading.Event()
    allow_replacement_close = threading.Event()
    services_holder: list[ApplicationServices] = []
    unload_threads: list[threading.Thread] = []

    def queue_disable(
        _request: NotificationRequest,
    ) -> NotificationAdapterResult:
        result = services_holder[0].plugin_manager.disable(
            "test.replacement-owns-unload"
        )
        assert result.deferred is True
        disable_queued.set()
        assert release_send.wait(timeout=5)
        return NotificationAdapterResult(success=True)

    class ThreadRecordingPlugin(_NotificationPlugin):
        def onunload(self) -> None:
            unload_threads.append(threading.current_thread())
            super().onunload()

    first = _install(
        monkeypatch,
        _config(),
        ThreadRecordingPlugin(
            "test.replacement-owns-unload",
            _adapter_factory(
                "replacement_owns_unload",
                [],
                send_callback=queue_disable,
            ),
        ),
    )
    services_holder.append(first)
    second = ApplicationServices(config=_config(), plugins_dir="")
    original_close = first._close_plugins

    def delayed_close():
        replacement_close_entered.set()
        assert allow_replacement_close.wait(timeout=5)
        return original_close()

    monkeypatch.setattr(first, "_close_plugins", delayed_close)
    service = NotificationService()
    dispatches: list[object] = []
    sender = threading.Thread(
        target=lambda: dispatches.append(
            service.send_with_results("report")
        ),
        name="notification-sender",
    )
    replacement = threading.Thread(
        target=lambda: set_application_services(second),
        name="application-root-replacement",
    )

    sender.start()
    assert disable_queued.wait(timeout=5)
    replacement.start()
    assert replacement_close_entered.wait(timeout=5)

    try:
        release_send.set()
        sender.join(timeout=5)
    finally:
        allow_replacement_close.set()
        replacement.join(timeout=5)

    assert sender.is_alive() is False
    assert replacement.is_alive() is False
    assert dispatches[0].success is True
    assert unload_threads == [replacement]
    assert first._notification_writer_reservations == 0
    assert first._notification_transition_reservations == 0
    assert first._deferred_notification_lifecycle == []
    assert get_application_services() is second


def test_example_plugin_loads_from_parent_directory_and_delivers_to_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _config(notification_report_channels=["example_log"])
    monkeypatch.setattr("src.notification.get_config", lambda: config)
    examples_dir = Path(__file__).parents[2] / "examples" / "plugins"
    services = ApplicationServices(config=config, plugins_dir=examples_dir)
    set_application_services(services)
    service = NotificationService()

    with caplog.at_level(logging.INFO):
        dispatch = service.send_with_results(
            "example report",
            route_type="report",
        )

    expected_candidates = {
        candidate.name
        for candidate in examples_dir.iterdir()
        if candidate.is_dir() and (candidate / "manifest.json").is_file()
    }
    registrations = {
        result.candidate: result
        for result in services.external_plugin_results
    }
    loads = {
        result.plugin_id: result for result in services.plugin_load_results
    }
    assert set(registrations) == expected_candidates
    assert all(result.success is True for result in registrations.values())
    assert loads["example-notification-channel"].success is True
    assert loads["stockpulse.example-provider"].success is False
    assert loads["stockpulse.example-provider"].error_code == (
        "extension_implementation_invalid"
    )
    assert dispatch.success is True
    assert [attempt.channel for attempt in dispatch.channel_results] == [
        "example_log"
    ]
    assert "Example notification delivered" in caplog.text
    assert "example report" not in caplog.text
