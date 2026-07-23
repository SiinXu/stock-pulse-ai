# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.notification_parts.capabilities`."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.capabilities import (
    Any,
    CHANNEL_PROFILES,
    CHANNEL_RENDERER_PRESETS,
    ChannelProfile,
    Dict,
    Mapping,
    Optional,
    PreparedMessage,
    RendererPreset,
    Tuple,
    all_channel_profiles,
    all_renderer_presets,
    annotations,
    dataclass,
    get_channel_profile,
    get_renderer_preset,
    normalize_channel_name,
)


__all__ = (
    "Any",
    "CHANNEL_PROFILES",
    "CHANNEL_RENDERER_PRESETS",
    "ChannelProfile",
    "Dict",
    "Mapping",
    "Optional",
    "PreparedMessage",
    "RendererPreset",
    "Tuple",
    "all_channel_profiles",
    "all_renderer_presets",
    "annotations",
    "dataclass",
    "get_channel_profile",
    "get_renderer_preset",
    "normalize_channel_name",
)

_load_legacy_module("src.notification_parts.capabilities", globals(), __all__)
del _load_legacy_module
