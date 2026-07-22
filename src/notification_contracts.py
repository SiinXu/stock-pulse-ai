# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.notification_parts.contracts`."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.contracts import (
    Any,
    FEISHU_APP_BOT_ENV_GROUP,
    FEISHU_STATIC_ENV_GROUPS,
    FEISHU_WEBHOOK_ENV_GROUP,
    Mapping,
    Tuple,
    annotations,
    is_dingtalk_session_webhook_url,
    is_feishu_app_bot_configured,
    is_feishu_app_bot_env_configured,
    is_feishu_static_configured,
    is_feishu_static_env_configured,
    parse_qsl,
    urlsplit,
)


__all__ = (
    "Any",
    "FEISHU_APP_BOT_ENV_GROUP",
    "FEISHU_STATIC_ENV_GROUPS",
    "FEISHU_WEBHOOK_ENV_GROUP",
    "Mapping",
    "Tuple",
    "annotations",
    "is_dingtalk_session_webhook_url",
    "is_feishu_app_bot_configured",
    "is_feishu_app_bot_env_configured",
    "is_feishu_static_configured",
    "is_feishu_static_env_configured",
    "parse_qsl",
    "urlsplit",
)

_load_legacy_module("src.notification_parts.contracts", globals(), __all__)
del _load_legacy_module
