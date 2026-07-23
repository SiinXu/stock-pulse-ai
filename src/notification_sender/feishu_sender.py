# -*- coding: utf-8 -*-
"""Compatibility facade for the canonical Feishu sender."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.feishu_sender import (
    Any,
    Config,
    Dict,
    FEISHU_DOMAIN,
    FEISHU_FILE_SDK_AVAILABLE,
    FEISHU_SDK_AVAILABLE,
    FeishuSender,
    LARK_DOMAIN,
    MIN_MAX_BYTES,
    Optional,
    PAGE_MARKER_SAFE_BYTES,
    Path,
    base64,
    chunk_content_by_max_bytes,
    format_feishu_markdown,
    hashlib,
    hmac,
    json,
    log_safe_exception,
    logger,
    logging,
    os,
    requests,
    safe_post,
    threading,
    time,
    uuid_mod,
)

if FEISHU_SDK_AVAILABLE:
    from src.notification_parts.senders.feishu_sender import (  # noqa: F401
        CreateMessageRequest,
        CreateMessageRequestBody,
    )


__all__ = (
    "Any",
    "Config",
    *(("CreateMessageRequest", "CreateMessageRequestBody") if FEISHU_SDK_AVAILABLE else ()),
    "Dict",
    "FEISHU_DOMAIN",
    "FEISHU_FILE_SDK_AVAILABLE",
    "FEISHU_SDK_AVAILABLE",
    "FeishuSender",
    "LARK_DOMAIN",
    "MIN_MAX_BYTES",
    "Optional",
    "PAGE_MARKER_SAFE_BYTES",
    "Path",
    "base64",
    "chunk_content_by_max_bytes",
    "format_feishu_markdown",
    "hashlib",
    "hmac",
    "json",
    "log_safe_exception",
    "logger",
    "logging",
    "os",
    "requests",
    "safe_post",
    "threading",
    "time",
    "uuid_mod",
)

_load_legacy_module("src.notification_parts.senders.feishu_sender", globals(), __all__)
del _load_legacy_module
