# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.notification_parts.senders.serverchan3_sender`."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.serverchan3_sender import (
    Config,
    Optional,
    Serverchan3Sender,
    datetime,
    log_safe_exception,
    logger,
    logging,
    re,
    requests,
    safe_post,
)


__all__ = (
    "Config",
    "Optional",
    "Serverchan3Sender",
    "datetime",
    "log_safe_exception",
    "logger",
    "logging",
    "re",
    "requests",
    "safe_post",
)

_load_legacy_module("src.notification_parts.senders.serverchan3_sender", globals(), __all__)
del _load_legacy_module
