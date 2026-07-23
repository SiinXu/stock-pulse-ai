# -*- coding: utf-8 -*-
"""Compatibility facade for the canonical Telegram sender."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.telegram_sender import (
    Config,
    Optional,
    TelegramSender,
    log_safe_exception,
    logger,
    logging,
    re,
    requests,
    safe_post,
    time,
)


__all__ = (
    "Config",
    "Optional",
    "TelegramSender",
    "log_safe_exception",
    "logger",
    "logging",
    "re",
    "requests",
    "safe_post",
    "time",
)

_load_legacy_module("src.notification_parts.senders.telegram_sender", globals(), __all__)
del _load_legacy_module
