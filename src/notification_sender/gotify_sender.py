# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.notification_parts.senders.gotify_sender`."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.gotify_sender import (
    Config,
    GotifySender,
    Optional,
    annotations,
    datetime,
    logger,
    logging,
    requests,
    resolve_gotify_message_endpoint,
    safe_post,
    urlparse,
    urlunparse,
)


__all__ = (
    "Config",
    "GotifySender",
    "Optional",
    "annotations",
    "datetime",
    "logger",
    "logging",
    "requests",
    "resolve_gotify_message_endpoint",
    "safe_post",
    "urlparse",
    "urlunparse",
)

_load_legacy_module("src.notification_parts.senders.gotify_sender", globals(), __all__)
del _load_legacy_module
