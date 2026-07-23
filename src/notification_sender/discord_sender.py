# -*- coding: utf-8 -*-
"""Compatibility facade for the canonical Discord sender."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.discord_sender import (
    Config,
    DISCORD_CHUNK_SLEEP_SECONDS,
    DISCORD_MAX_CONTENT_LENGTH,
    DISCORD_MAX_RETRIES,
    DiscordSender,
    MIN_MAX_WORDS,
    Optional,
    chunk_content_by_max_words,
    log_safe_exception,
    logger,
    logging,
    requests,
    safe_post,
    time,
)


__all__ = (
    "Config",
    "DISCORD_CHUNK_SLEEP_SECONDS",
    "DISCORD_MAX_CONTENT_LENGTH",
    "DISCORD_MAX_RETRIES",
    "DiscordSender",
    "MIN_MAX_WORDS",
    "Optional",
    "chunk_content_by_max_words",
    "log_safe_exception",
    "logger",
    "logging",
    "requests",
    "safe_post",
    "time",
)

_load_legacy_module("src.notification_parts.senders.discord_sender", globals(), __all__)
del _load_legacy_module
