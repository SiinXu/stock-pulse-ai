# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.notification_parts.route_config`."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.route_config import (
    Dict,
    Iterable,
    List,
    NOTIFICATION_ROUTE_CONFIGS,
    Optional,
    ROUTABLE_NOTIFICATION_CHANNELS,
    ROUTABLE_NOTIFICATION_CHANNEL_SET,
    Tuple,
    annotations,
    get_notification_route_config,
    parse_notification_route_channels,
    split_notification_route_channels,
)


__all__ = (
    "Dict",
    "Iterable",
    "List",
    "NOTIFICATION_ROUTE_CONFIGS",
    "Optional",
    "ROUTABLE_NOTIFICATION_CHANNELS",
    "ROUTABLE_NOTIFICATION_CHANNEL_SET",
    "Tuple",
    "annotations",
    "get_notification_route_config",
    "parse_notification_route_channels",
    "split_notification_route_channels",
)

_load_legacy_module("src.notification_parts.route_config", globals(), __all__)
del _load_legacy_module
