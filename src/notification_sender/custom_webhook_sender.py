# -*- coding: utf-8 -*-
"""Compatibility facade for the canonical custom webhook sender."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.custom_webhook_sender import (
    Any,
    Callable,
    Config,
    CustomWebhookSender,
    Dict,
    List,
    Optional,
    Template,
    Tuple,
    chunk_content_by_max_bytes,
    is_dingtalk_session_webhook_url,
    json,
    log_safe_exception,
    logger,
    logging,
    requests,
    safe_post,
    sanitize_exception_chain,
    slice_at_max_bytes,
    time,
)


__all__ = (
    "Any",
    "Callable",
    "Config",
    "CustomWebhookSender",
    "Dict",
    "List",
    "Optional",
    "Template",
    "Tuple",
    "chunk_content_by_max_bytes",
    "is_dingtalk_session_webhook_url",
    "json",
    "log_safe_exception",
    "logger",
    "logging",
    "requests",
    "safe_post",
    "sanitize_exception_chain",
    "slice_at_max_bytes",
    "time",
)

_load_legacy_module(
    "src.notification_parts.senders.custom_webhook_sender", globals(), __all__
)
del _load_legacy_module
