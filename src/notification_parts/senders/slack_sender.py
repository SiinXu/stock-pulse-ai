# -*- coding: utf-8 -*-
"""
Slack 发送提醒服务

职责：
1. 通过 Slack Bot API 或 Incoming Webhook 发送 Slack 消息
   （同时配置时优先使用 Bot API，确保文本与图片发送到同一频道）
"""
import logging
import json
from typing import Optional

import requests

from src.security.outbound_policy import safe_post

from src.config import Config
from src.formatters import chunk_content_by_max_bytes
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

# Slack Block Kit single section block text field limit is 3000 characters
_BLOCK_TEXT_LIMIT = 3000
# Slack chat.postMessage / Webhook text field limit is approximately 40000 characters, conservatively set to 39000
_TEXT_LIMIT = 39000


class SlackSender:

    def __init__(self, config: Config):
        """
        初始化 Slack 配置

        Args:
            config: 配置对象
        """
        self._slack_webhook_url = getattr(config, 'slack_webhook_url', None)
        self._slack_bot_token = getattr(config, 'slack_bot_token', None)
        self._slack_channel_id = getattr(config, 'slack_channel_id', None)
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)

    @property
    def _use_bot(self) -> bool:
        """Bot 配置完整时优先走 Bot API，保证文本和图片使用同一传输通道。"""
        return bool(self._slack_bot_token and self._slack_channel_id)

    def _is_slack_configured(self) -> bool:
        """检查 Slack 配置是否完整（支持 Webhook 或 Bot API）"""
        return self._use_bot or bool(self._slack_webhook_url)

    def send_to_slack(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        推送消息到 Slack（支持 Webhook 和 Bot API）

        传输优先级与 _send_slack_image() 保持一致：Bot > Webhook，
        避免文本走 Webhook、图片走 Bot 导致消息落入不同频道。

        Args:
            content: Markdown 格式的消息内容

        Returns:
            是否发送成功
        """
        # Divide bytes into blocks to avoid single messages exceeding the limit.
        try:
            chunks = chunk_content_by_max_bytes(content, _TEXT_LIMIT, add_page_marker=True)
        except Exception as exc:  # broad-exception: fallback_recorded - Chunking failure is logged before whole-message fallback.
            log_safe_exception(
                logger,
                "Slack message chunking failed; using the complete message",
                exc,
                error_code="slack_message_chunking_failed",
            )
            chunks = [content]

        # Prioritize using Bot API (_send_slack_image consistent)
        if self._use_bot:
            return all(self._send_slack_bot(chunk, timeout_seconds=timeout_seconds) for chunk in chunks)

        # Then use Webhook.
        if self._slack_webhook_url:
            return all(self._send_slack_webhook(chunk, timeout_seconds=timeout_seconds) for chunk in chunks)

        logger.warning("Slack 配置不完整，跳过推送")
        return False

    def _build_blocks(self, content: str) -> list:
        """
        将内容构建为 Slack Block Kit 格式

        如果内容超过单个 section block 限制，会自动拆分为多个 block。
        """
        blocks = []
        # Shard by block text limit.
        pos = 0
        while pos < len(content):
            segment = content[pos:pos + _BLOCK_TEXT_LIMIT]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": segment
                }
            })
            pos += _BLOCK_TEXT_LIMIT
        return blocks

    def _send_slack_webhook(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        使用 Incoming Webhook 发送消息到 Slack

        Args:
            content: 消息内容

        Returns:
            是否发送成功
        """
        try:
            payload = {
                "text": content,
                "blocks": self._build_blocks(content),
            }
            response = safe_post(
                self._slack_webhook_url,
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=timeout_seconds or 15,
                verify=self._webhook_verify_ssl,
                transport=requests,
            )
            if response.status_code == 200 and response.text == "ok":
                logger.info("Slack Webhook 消息发送成功")
                return True
            logger.error(f"Slack Webhook 发送失败: HTTP {response.status_code} {response.text[:200]}")
            return False
        except Exception as exc:  # broad-exception: fallback_recorded - Webhook failure is safely logged and isolated.
            log_safe_exception(
                logger,
                "Slack webhook delivery failed",
                exc,
                error_code="slack_webhook_delivery_failed",
            )
            return False

    def _send_slack_bot(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        使用 Bot API (chat.postMessage) 发送消息到 Slack

        Args:
            content: 消息内容

        Returns:
            是否发送成功
        """
        try:
            headers = {
                'Authorization': f'Bearer {self._slack_bot_token}',
                'Content-Type': 'application/json; charset=utf-8',
            }
            payload = {
                "channel": self._slack_channel_id,
                "text": content,
                "blocks": self._build_blocks(content),
            }
            response = safe_post(
                'https://slack.com/api/chat.postMessage',
                data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                headers=headers,
                timeout=timeout_seconds or 15,
                transport=requests,
            )
            result = response.json()
            if result.get("ok"):
                logger.info("Slack Bot 消息发送成功")
                return True
            logger.error(f"Slack Bot 发送失败: {result.get('error', 'unknown')}")
            return False
        except Exception as exc:  # broad-exception: fallback_recorded - Bot failure is safely logged and isolated.
            log_safe_exception(
                logger,
                "Slack Bot delivery failed",
                exc,
                error_code="slack_bot_delivery_failed",
            )
            return False

    def _send_slack_image(self, image_bytes: bytes, fallback_content: str = "") -> bool:
        """
        发送图片到 Slack

        Bot 模式下使用 files.getUploadURLExternal + files.completeUploadExternal
        (Slack 新版文件上传 API)；Webhook 模式下回退为文本。

        Args:
            image_bytes: PNG 图片字节
            fallback_content: 图片发送失败时的回退文本

        Returns:
            是否发送成功
        """
        # Bot mode: Using the new file upload API
        if self._use_bot:
            headers = {'Authorization': f'Bearer {self._slack_bot_token}'}
            try:
                # Step 1: Get the upload URL through the outbound safety policy.
                resp1 = safe_post(
                    'https://slack.com/api/files.getUploadURLExternal',
                    headers=headers,
                    data={
                        'filename': 'report.png',
                        'length': len(image_bytes),
                    },
                    timeout=30,
                    transport=requests,
                )
                result1 = resp1.json()
                if not result1.get("ok"):
                    logger.error("Slack 获取上传 URL 失败: %s", result1.get('error', 'unknown'))
                    raise RuntimeError(result1.get('error', 'unknown'))

                upload_url = result1['upload_url']
                file_id = result1['file_id']

                # Step 2: Upload the raw file body; multipart is not supported.
                resp2 = safe_post(
                    upload_url,
                    data=image_bytes,
                    headers={'Content-Type': 'application/octet-stream'},
                    timeout=30,
                    transport=requests,
                )
                if resp2.status_code != 200:
                    logger.error("Slack 文件上传失败: HTTP %s", resp2.status_code)
                    raise RuntimeError(f"HTTP {resp2.status_code}")

                # Step 3: Complete the upload and share it with the channel.
                resp3 = safe_post(
                    'https://slack.com/api/files.completeUploadExternal',
                    headers={**headers, 'Content-Type': 'application/json'},
                    json={
                        'files': [{'id': file_id, 'title': '股票分析报告'}],
                        'channel_id': self._slack_channel_id,
                    },
                    timeout=30,
                    transport=requests,
                )
                result3 = resp3.json()
                if result3.get("ok"):
                    logger.info("Slack Bot 图片发送成功")
                    return True
                logger.error("Slack 完成上传失败: %s", result3.get('error', 'unknown'))
            except Exception as exc:  # broad-exception: fallback_recorded - Image failure is safely logged before fallback.
                log_safe_exception(
                    logger,
                    "Slack Bot image delivery failed",
                    exc,
                    error_code="slack_bot_image_delivery_failed",
                )

        # Webhook Mode or Bot Upload Failed: Fallback to Text
        if fallback_content:
            logger.info("Slack 图片不支持或失败，回退为文本发送")
            return self.send_to_slack(fallback_content)

        logger.warning("Slack 图片发送失败，且无回退内容")
        return False
