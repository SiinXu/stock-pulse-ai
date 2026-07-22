# -*- coding: utf-8 -*-
"""
===================================
Bot Webhook 处理器
===================================

处理各平台的 Webhook 回调，分发到命令处理器。
"""

import asyncio
import json
import logging
import threading
from typing import Dict, Optional, TYPE_CHECKING

from bot.models import WebhookResponse
from bot.dispatcher import get_dispatcher
from bot.platforms import ALL_PLATFORMS
from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from bot.platforms.base import BotPlatform  # noqa: F401

logger = logging.getLogger(__name__)

# Platform instance cache
_platform_instances: Dict[str, 'BotPlatform'] = {}


def get_platform(platform_name: str) -> Optional['BotPlatform']:
    """
    获取平台适配器实例

    使用缓存避免重复创建。

    Args:
        platform_name: 平台名称

    Returns:
        平台适配器实例，或 None
    """
    if platform_name not in _platform_instances:
        platform_class = ALL_PLATFORMS.get(platform_name)
        if platform_class:
            _platform_instances[platform_name] = platform_class()
        else:
            logger.warning("[BotHandler] Unknown platform: %s", platform_name)
            return None

    return _platform_instances[platform_name]


def handle_webhook(
    platform_name: str,
    headers: Dict[str, str],
    body: bytes,
    query_params: Optional[Dict[str, list]] = None
) -> WebhookResponse:
    """
    处理 Webhook 请求

    这是所有平台 Webhook 的统一入口。

    Args:
        platform_name: 平台名称 (feishu, dingtalk, wecom, telegram)
        headers: HTTP 请求头
        body: 请求体原始字节
        query_params: URL 查询参数（用于某些平台的验证）

    Returns:
        WebhookResponse 响应对象
    """
    logger.info("[BotHandler] Received webhook request: platform=%s", platform_name)

    # Check if the robot function is enabled
    from src.config import get_config
    config = get_config()

    if not getattr(config, 'bot_enabled', True):
        logger.info("[BotHandler] Bot integration is disabled")
        return WebhookResponse.success()

    # Get platform adapter
    platform = get_platform(platform_name)
    if not platform:
        return WebhookResponse.error(f"Unknown platform: {platform_name}", 400)

    # Parse JSON data
    try:
        data = json.loads(body.decode('utf-8')) if body else {}
    except json.JSONDecodeError as exc:
        log_safe_exception(
            logger,
            "[BotHandler] Webhook JSON parsing failed",
            exc,
            error_code="bot_webhook_invalid_json",
            level=logging.WARNING,
            context={"platform": platform_name},
        )
        return WebhookResponse.error("Invalid JSON", 400)

    logger.debug("[BotHandler] Parsed webhook payload: body_bytes=%d", len(body))

    # Handle webhooks
    message, immediate_response = platform.handle_webhook(headers, body, data)

    # If it's a validation/error response and there is no message to process, return directly
    if immediate_response and not message:
        logger.info("[BotHandler] Returning immediate verification response")
        return immediate_response

    # Delayed response (like Discord type 5): Immediately return ACK and handle command in the background
    if immediate_response and message:
        logger.info(
            "[BotHandler] Returning deferred acknowledgement and dispatching in background"
        )

        def _deferred_dispatch() -> None:
            try:
                dispatcher = get_dispatcher()
                response = dispatcher.dispatch(message)
                if response.text:
                    platform.send_followup(response, message)
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "[BotHandler] Deferred command dispatch failed",
                    exc,
                    error_code="bot_deferred_dispatch_failed",
                    context={"platform": platform_name},
                )

        threading.Thread(target=_deferred_dispatch, daemon=True).start()
        return immediate_response

    # If no messages need to be processed, return an empty response.
    if not message:
        logger.debug("[BotHandler] Webhook did not contain a processable message")
        return WebhookResponse.success()

    logger.info(
        "[BotHandler] Parsed message: chat_type=%s content_length=%d",
        message.chat_type.value,
        len(message.content),
    )

    # Forward to command processor
    dispatcher = get_dispatcher()
    response = dispatcher.dispatch(message)

    # Format the response
    if response.text:
        webhook_response = platform.format_response(response, message)
        return webhook_response

    return WebhookResponse.success()


async def handle_webhook_async(
    platform_name: str,
    headers: Dict[str, str],
    body: bytes,
    query_params: Optional[Dict[str, list]] = None
) -> WebhookResponse:
    """Async version of :func:`handle_webhook`.

    Preferred when called from an async context (e.g. FastAPI endpoint)
    to avoid blocking the event loop.
    """
    logger.info(
        "[BotHandler] Received asynchronous webhook request: platform=%s",
        platform_name,
    )

    from src.config import get_config
    config = get_config()

    if not getattr(config, 'bot_enabled', True):
        logger.info("[BotHandler] Bot integration is disabled")
        return WebhookResponse.success()

    platform = get_platform(platform_name)
    if not platform:
        return WebhookResponse.error(f"Unknown platform: {platform_name}", 400)

    try:
        data = json.loads(body.decode('utf-8')) if body else {}
    except json.JSONDecodeError as exc:
        log_safe_exception(
            logger,
            "[BotHandler] Webhook JSON parsing failed",
            exc,
            error_code="bot_webhook_invalid_json",
            level=logging.WARNING,
            context={"platform": platform_name},
        )
        return WebhookResponse.error("Invalid JSON", 400)

    logger.debug("[BotHandler] Parsed webhook payload: body_bytes=%d", len(body))

    message, immediate_response = platform.handle_webhook(headers, body, data)

    if immediate_response and not message:
        logger.info("[BotHandler] Returning immediate verification response")
        return immediate_response

    if immediate_response and message:
        logger.info(
            "[BotHandler] Returning deferred acknowledgement and dispatching asynchronously"
        )

        async def _deferred_dispatch() -> None:
            try:
                dispatcher = get_dispatcher()
                response = await dispatcher.dispatch_async(message)
                if response.text:
                    await asyncio.to_thread(platform.send_followup, response, message)
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "[BotHandler] Deferred command dispatch failed",
                    exc,
                    error_code="bot_deferred_dispatch_failed",
                    context={"platform": platform_name},
                )

        asyncio.ensure_future(_deferred_dispatch())
        return immediate_response

    if not message:
        logger.debug("[BotHandler] Webhook did not contain a processable message")
        return WebhookResponse.success()

    logger.info(
        "[BotHandler] Parsed message: chat_type=%s content_length=%d",
        message.chat_type.value,
        len(message.content),
    )

    dispatcher = get_dispatcher()
    response = await dispatcher.dispatch_async(message)

    if response.text:
        webhook_response = platform.format_response(response, message)
        return webhook_response

    return WebhookResponse.success()


def handle_feishu_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """处理飞书 Webhook"""
    return handle_webhook('feishu', headers, body)


def handle_dingtalk_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """处理钉钉 Webhook"""
    return handle_webhook('dingtalk', headers, body)


def handle_wecom_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """处理企业微信 Webhook"""
    return handle_webhook('wecom', headers, body)


def handle_telegram_webhook(headers: Dict[str, str], body: bytes) -> WebhookResponse:
    """处理 Telegram Webhook"""
    return handle_webhook('telegram', headers, body)
