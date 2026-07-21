# -*- coding: utf-8 -*-
"""
===================================
Platform adapter module
===================================

A dictionary containing Webhook handling and message parsing logic for each platform.

Supports two access modes:
1. Webhook Mode: Requires Public IP, Configure Callback URL
2. Streaming mode: No public IP required, via long WebSocket connection (supported by DingTalk and Feishu)
"""

from bot.platforms.base import BotPlatform
from bot.platforms.dingtalk import DingtalkPlatform

# All available platforms (Webhook mode)
ALL_PLATFORMS = {
    'dingtalk': DingtalkPlatform,
}

# DingTalk Stream mode (optional)
try:
    from bot.platforms.dingtalk_stream import (
        DingtalkStreamClient,
        DingtalkStreamHandler,
        get_dingtalk_stream_client,
        start_dingtalk_stream_background,
        DINGTALK_STREAM_AVAILABLE,
    )
except ImportError:
    DINGTALK_STREAM_AVAILABLE = False
    DingtalkStreamClient = None
    DingtalkStreamHandler = None
    get_dingtalk_stream_client = lambda: None
    start_dingtalk_stream_background = lambda: False

# Feishu Stream mode (optional)
try:
    from bot.platforms.feishu_stream import (
        FeishuStreamClient,
        FeishuStreamHandler,
        FeishuReplyClient,
        get_feishu_stream_client,
        start_feishu_stream_background,
        FEISHU_SDK_AVAILABLE,
    )
except ImportError:
    FEISHU_SDK_AVAILABLE = False
    FeishuStreamClient = None
    FeishuStreamHandler = None
    FeishuReplyClient = None
    get_feishu_stream_client = lambda: None
    start_feishu_stream_background = lambda: False

__all__ = [
    'BotPlatform',
    'DingtalkPlatform',
    'ALL_PLATFORMS',
    # DingTalk Stream mode
    'DingtalkStreamClient',
    'DingtalkStreamHandler',
    'get_dingtalk_stream_client',
    'start_dingtalk_stream_background',
    'DINGTALK_STREAM_AVAILABLE',
    # Feishu Stream mode
    'FeishuStreamClient',
    'FeishuStreamHandler',
    'FeishuReplyClient',
    'get_feishu_stream_client',
    'start_feishu_stream_background',
    'FEISHU_SDK_AVAILABLE',
]
