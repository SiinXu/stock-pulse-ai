# -*- coding: utf-8 -*-
"""
AstrBot sends reminder service

Responsibilities:
1. Send AstrBot messages via Astrbot API
"""
import logging
import json
import hmac
import hashlib
from typing import Optional

import requests

from src.config import Config
from src.utils.sanitize import log_safe_exception
from src.formatters import markdown_to_html_document


logger = logging.getLogger(__name__)


class AstrbotSender:
    
    def __init__(self, config: Config):
        """
        Initialize AstrBot configuration

        Args:
            config: Configuration object
        """
        self._astrbot_config = {
            'astrbot_url': getattr(config, 'astrbot_url', None),
            'astrbot_token': getattr(config, 'astrbot_token', None),
        }
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)
        
    def _is_astrbot_configured(self) -> bool:
        """Check AstrBot configuration completeness (supports Bot or Webhook)"""
        # If the URL is configured, it's considered available.
        url_ok = bool(self._astrbot_config['astrbot_url'])
        return url_ok

    def send_to_astrbot(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Push message to AstrBot (via adapter support)

        Args:
            content: Markdown Message content format

        Returns:
            Whether sent successfully
        """
        if self._astrbot_config['astrbot_url']:
            return self._send_astrbot(content, timeout_seconds=timeout_seconds)

        logger.warning("AstrBot 配置不完整，跳过推送")
        return False


    def _send_astrbot(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        import time
        """
        使用 Bot API 发送消息到 AstrBot

        Args:
            content: Markdown 格式的消息内容

        Returns:
            是否发送成功
        """

        html_content = markdown_to_html_document(content)

        try:
            payload = {
                'content': html_content
            }
            signature =  ""
            timestamp = str(int(time.time()))
            if self._astrbot_config['astrbot_token']:
                """计算请求签名"""
                payload_json = json.dumps(payload, sort_keys=True)
                sign_data = f"{timestamp}.{payload_json}".encode('utf-8')
                key = self._astrbot_config['astrbot_token']
                signature = hmac.new(
                    key.encode('utf-8'),
                    sign_data,
                    hashlib.sha256
                ).hexdigest()
            url = self._astrbot_config['astrbot_url']
            response = requests.post(
                url, json=payload, timeout=timeout_seconds or 10,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": signature,
                    "X-Timestamp": timestamp
                },
                verify=self._webhook_verify_ssl
            )

            if response.status_code == 200:
                logger.info("AstrBot 消息发送成功")
                return True
            else:
                logger.error(f"AstrBot 发送失败: {response.status_code} {response.text}")
                return False
        except Exception as exc:
            log_safe_exception(
                logger,
                "AstrBot message delivery failed",
                exc,
                error_code="astrbot_delivery_failed",
            )
            return False
