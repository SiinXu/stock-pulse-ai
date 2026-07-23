# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.notification_parts.senders.astrbot_sender`."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.astrbot_sender import (
    AstrbotSender,
    Config,
    Optional,
    hashlib,
    hmac,
    json,
    log_safe_exception,
    logger,
    logging,
    markdown_to_html_document,
    requests,
    safe_post,
)


__all__ = (
    "AstrbotSender",
    "Config",
    "Optional",
    "hashlib",
    "hmac",
    "json",
    "log_safe_exception",
    "logger",
    "logging",
    "markdown_to_html_document",
    "requests",
    "safe_post",
)

_load_legacy_module("src.notification_parts.senders.astrbot_sender", globals(), __all__)
del _load_legacy_module
