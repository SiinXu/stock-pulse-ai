# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.notification_parts.senders.dingtalk_sender`."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.dingtalk_sender import (
    Config,
    DingtalkSender,
    Optional,
    base64,
    chunk_content_by_max_bytes,
    hashlib,
    hmac,
    log_safe_exception,
    logger,
    logging,
    requests,
    safe_post,
    time,
    urllib,
)


__all__ = (
    "Config",
    "DingtalkSender",
    "Optional",
    "base64",
    "chunk_content_by_max_bytes",
    "hashlib",
    "hmac",
    "log_safe_exception",
    "logger",
    "logging",
    "requests",
    "safe_post",
    "time",
    "urllib",
)

_load_legacy_module("src.notification_parts.senders.dingtalk_sender", globals(), __all__)
del _load_legacy_module
