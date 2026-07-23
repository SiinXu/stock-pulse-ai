# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.notification_parts.senders.ntfy_sender`."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.ntfy_sender import (
    Config,
    NtfySender,
    Optional,
    Tuple,
    annotations,
    datetime,
    logger,
    logging,
    requests,
    resolve_ntfy_endpoint,
    safe_post,
    unquote,
    urlparse,
    urlunparse,
)


__all__ = (
    "Config",
    "NtfySender",
    "Optional",
    "Tuple",
    "annotations",
    "datetime",
    "logger",
    "logging",
    "requests",
    "resolve_ntfy_endpoint",
    "safe_post",
    "unquote",
    "urlparse",
    "urlunparse",
)

_load_legacy_module("src.notification_parts.senders.ntfy_sender", globals(), __all__)
del _load_legacy_module
