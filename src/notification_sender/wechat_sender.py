# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.notification_parts.senders.wechat_sender`."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.wechat_sender import (
    Config,
    Optional,
    WECHAT_IMAGE_MAX_BYTES,
    WechatSender,
    base64,
    chunk_content_by_max_bytes,
    hashlib,
    log_safe_exception,
    logger,
    logging,
    requests,
    safe_post,
    time,
)


__all__ = (
    "Config",
    "Optional",
    "WECHAT_IMAGE_MAX_BYTES",
    "WechatSender",
    "base64",
    "chunk_content_by_max_bytes",
    "hashlib",
    "log_safe_exception",
    "logger",
    "logging",
    "requests",
    "safe_post",
    "time",
)

_load_legacy_module("src.notification_parts.senders.wechat_sender", globals(), __all__)
del _load_legacy_module
