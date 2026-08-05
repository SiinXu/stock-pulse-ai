# -*- coding: utf-8 -*-
"""Tests for notification dispatch ports injection and default wiring."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Optional
from unittest import mock

import pytest

from src.notification import (
    ChannelAttemptResult,
    NotificationChannel,
    NotificationService,
)
from src.notification_parts import dispatch as dispatch_mod
from src.notification_parts.dispatch import (
    DispatchFacadePorts,
    DispatchPorts,
    _prepare_full_report_image,
    _send_to_static_channel,
    build_default_dispatch_ports,
    configure_dispatch_ports,
    get_dispatch_ports,
)


class _FakeChannelService:
    """Minimal static-channel surface for ports golden comparison."""

    def __init__(self) -> None:
        self._markdown_to_image_channels = {NotificationChannel.CUSTOM.value}
        self._markdown_to_image_max_chars = 15000
        self._stock_email_groups: list = []
        self.sent: list[tuple[str, Optional[bytes]]] = []

    def send_to_custom(self, content: str) -> bool:
        self.sent.append(("text", None))
        return True

    def _send_custom_webhook_image(
        self,
        image_bytes: bytes,
        fallback_content: str = "",
    ) -> bool:
        self.sent.append(("image", image_bytes))
        return True

    def _should_use_image_for_channel(
        self,
        channel: Any,
        image_bytes: Optional[bytes],
    ) -> bool:
        return (
            channel.value in self._markdown_to_image_channels
            and image_bytes is not None
        )


def _legacy_prepare_image(service, content, target_channels, *, aggregate: bool):
    """Mirror pre-ports shared-image preparation for golden comparison."""

    from src.md2img import markdown_to_image

    channel_ids = tuple(
        channel.value
        if isinstance(channel, NotificationChannel)
        else channel.channel_id
        for channel in target_channels
    )
    needing = tuple(
        channel_id
        for channel_id in channel_ids
        if channel_id in service._markdown_to_image_channels
        and channel_id
        not in {
            NotificationChannel.NTFY.value,
            NotificationChannel.GOTIFY.value,
            *((NotificationChannel.WECHAT.value,) if aggregate else ()),
        }
    )
    if not needing:
        return None, frozenset()
    image_bytes = markdown_to_image(
        content,
        max_chars=service._markdown_to_image_max_chars,
    )
    return image_bytes, frozenset()


def test_default_ports_image_builder_matches_legacy_md2img_call():
    """Default image_builder call shape equals the previous deferred import."""

    ports = build_default_dispatch_ports()
    content = "# report body"
    max_chars = 1234
    with mock.patch(
        "src.md2img.markdown_to_image",
        return_value=b"png-bytes",
    ) as mock_md2img:
        got = ports.image_builder(content, max_chars=max_chars)
    assert got == b"png-bytes"
    mock_md2img.assert_called_once_with(content, max_chars=max_chars)


def test_prepare_full_report_image_ports_match_legacy_golden():
    """Ports-backed shared image prep matches the legacy call and outcome."""

    service = _FakeChannelService()
    targets = [NotificationChannel.CUSTOM]
    content = "golden markdown"
    with mock.patch(
        "src.md2img.markdown_to_image",
        return_value=b"shared-png",
    ) as mock_md2img:
        legacy_bytes, legacy_failed = _legacy_prepare_image(
            service,
            content,
            targets,
            aggregate=False,
        )
        ports_outcome = _prepare_full_report_image(
            service,
            content,
            targets,
            aggregate=False,
        )
    assert ports_outcome.image_bytes == legacy_bytes == b"shared-png"
    assert ports_outcome.failed_channel_ids == legacy_failed
    assert mock_md2img.call_count == 2
    assert mock_md2img.call_args_list[0] == mock_md2img.call_args_list[1]


def test_static_channel_image_path_uses_injected_builder():
    """A fake channel receives the same image path under injected ports."""

    service = _FakeChannelService()
    calls: list[tuple[str, int]] = []

    def fake_builder(content: str, *, max_chars: int) -> bytes:
        calls.append((content, max_chars))
        return b"injected-png"

    base = build_default_dispatch_ports()
    configure_dispatch_ports(
        DispatchPorts(
            image_builder=fake_builder,
            normalize_stock_code=base.normalize_stock_code,
            report_type_cls=base.report_type_cls,
            facade=base.facade,
        )
    )
    try:
        outcome = _prepare_full_report_image(
            service,
            "hello",
            [NotificationChannel.CUSTOM],
            aggregate=False,
        )
        assert outcome.image_bytes == b"injected-png"
        ok = _send_to_static_channel(
            service,
            NotificationChannel.CUSTOM,
            "hello",
            image_bytes=outcome.image_bytes,
            email_stock_codes=None,
            email_send_to_all=False,
            route_type="report",
        )
        assert ok is True
        assert service.sent == [("image", b"injected-png")]
        assert calls == [("hello", service._markdown_to_image_max_chars)]
    finally:
        configure_dispatch_ports(build_default_dispatch_ports())


def test_get_dispatch_ports_returns_configured_instance():
    """Composition installs a stable process-wide ports object."""

    ports = build_default_dispatch_ports()
    configure_dispatch_ports(ports)
    assert get_dispatch_ports() is ports
    configure_dispatch_ports(build_default_dispatch_ports())


def test_notification_service_import_configures_default_ports():
    """Importing the public facade configures dispatch ports for free functions."""

    # Import side-effect already ran; re-configure and confirm facade symbols.
    ports = get_dispatch_ports()
    assert ports.facade.NotificationChannel is NotificationChannel
    assert ports.facade.ChannelAttemptResult is ChannelAttemptResult
    assert callable(ports.image_builder)
    assert NotificationService is not None
