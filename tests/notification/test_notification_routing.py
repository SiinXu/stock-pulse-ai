# -*- coding: utf-8 -*-
"""Tests for notification route channel parsing."""

from src.notification_routing import ROUTABLE_NOTIFICATION_CHANNELS, split_notification_route_channels


def test_ntfy_and_gotify_are_routable_notification_channels() -> None:
    valid, invalid = split_notification_route_channels(["wechat", "ntfy", "gotify", "not-a-channel"])

    assert "ntfy" in ROUTABLE_NOTIFICATION_CHANNELS
    assert "gotify" in ROUTABLE_NOTIFICATION_CHANNELS
    assert valid == ["wechat", "ntfy", "gotify"]
    assert invalid == ["not-a-channel"]


def test_route_parser_accepts_only_the_supplied_plugin_snapshot() -> None:
    valid, invalid = split_notification_route_channels(
        ["wechat", "private_sink", "disabled_sink"],
        allowed_channels=(*ROUTABLE_NOTIFICATION_CHANNELS, "private_sink"),
    )

    assert valid == ["wechat", "private_sink"]
    assert invalid == ["disabled_sink"]
