# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Runtime regressions for plugin-owned notification channels."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import pytest

from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.config import Config
from src.notification import NotificationService
from src.notification_noise import reset_notification_noise_state
from src.plugins import (
    NotificationAdapterResult,
    NotificationRequest,
    Plugin,
    PluginContext,
    PluginManifest,
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
    monkeypatch.setattr("src.notification.get_config", lambda: config)
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

    def disable_second(
        _request: NotificationRequest,
    ) -> NotificationAdapterResult:
        result = services_holder[0].plugin_manager.disable(
            "test.snapshot-second"
        )
        assert result.success is True
        return NotificationAdapterResult(success=True)

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
        _NotificationPlugin(
            "test.snapshot-second",
            _adapter_factory("snapshot_second", second_calls),
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

    example_registration = next(
        result
        for result in services.external_plugin_results
        if result.plugin_id == "example-notification-channel"
    )
    example_load = next(
        result
        for result in services.plugin_load_results
        if result.plugin_id == "example-notification-channel"
    )
    assert example_registration.success is True
    assert example_load.success is True
    assert dispatch.success is True
    assert [attempt.channel for attempt in dispatch.channel_results] == [
        "example_log"
    ]
    assert "Example notification delivered" in caplog.text
    assert "example report" not in caplog.text
