# -*- coding: utf-8 -*-
"""Compatibility facade for the canonical Slack sender."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.slack_sender import (
    Config,
    Optional,
    SlackSender,
    chunk_content_by_max_bytes,
    json,
    log_safe_exception,
    logger,
    logging,
    requests,
    safe_post,
)


__all__ = (
    "Config",
    "Optional",
    "SlackSender",
    "chunk_content_by_max_bytes",
    "json",
    "log_safe_exception",
    "logger",
    "logging",
    "requests",
    "safe_post",
)

_load_legacy_module("src.notification_parts.senders.slack_sender", globals(), __all__)
del _load_legacy_module
