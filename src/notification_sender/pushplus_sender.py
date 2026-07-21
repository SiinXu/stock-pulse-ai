# -*- coding: utf-8 -*-
"""
PushPlus sends reminder services

Responsibilities:
1. Send PushPlus messages via PushPlus API
"""
import logging
import time
from typing import Optional
from datetime import datetime
import requests

from src.config import Config
from src.utils.sanitize import log_safe_exception
from src.formatters import chunk_content_by_max_bytes


logger = logging.getLogger(__name__)


class PushplusSender:
    
    def __init__(self, config: Config):
        """
        Initialize PushPlus configuration

        Args:
            config: Configuration object
        """
        self._pushplus_token = getattr(config, 'pushplus_token', None)
        self._pushplus_topic = getattr(config, 'pushplus_topic', None)
        self._pushplus_max_bytes = getattr(config, 'pushplus_max_bytes', 20000)
        
    def send_to_pushplus(
        self,
        content: str,
        title: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Push message to PushPlus

        PushPlus API format:
        POST http://www.pushplus.plus/send
        {
            "token": "User token",
            "title": "Message title",
            "content": "Message content",
            "template": "html/txt/json/markdown"
        }

        PushPlus Features:
        - Domestic push service, free quota sufficient
        - Supports WeChat public account push
        - Supports multiple message formats

        Args:
            content: Message content in Markdown format
            title: Message title (optional)

        Returns:
            Whether sent successfully
        """
        if not self._pushplus_token:
            logger.warning("PushPlus Token 未配置，跳过推送")
            return False

        api_url = "http://www.pushplus.plus/send"

        if title is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            title = f"📈 股票分析报告 - {date_str}"

        try:
            content_bytes = len(content.encode('utf-8'))
            if content_bytes > self._pushplus_max_bytes:
                logger.info(
                    "PushPlus 消息内容超长(%s字节/%s字符)，将分批发送",
                    content_bytes,
                    len(content),
                )
                return self._send_pushplus_chunked(
                    api_url,
                    content,
                    title,
                    self._pushplus_max_bytes,
                )

            return self._send_pushplus_message(api_url, content, title, timeout_seconds=timeout_seconds)
        except Exception as exc:
            log_safe_exception(
                logger,
                "PushPlus message delivery failed",
                exc,
                error_code="pushplus_delivery_failed",
            )
            return False

    def _send_pushplus_message(
        self,
        api_url: str,
        content: str,
        title: str,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        payload = {
            "token": self._pushplus_token,
            "title": title,
            "content": content,
            "template": "markdown",
        }

        if self._pushplus_topic:
            payload["topic"] = self._pushplus_topic

        response = requests.post(api_url, json=payload, timeout=timeout_seconds or 10)

        if response.status_code == 200:
            result = response.json()
            if result.get('code') == 200:
                logger.info("PushPlus 消息发送成功")
                return True

            error_msg = result.get('msg', '未知错误')
            logger.error(f"PushPlus 返回错误: {error_msg}")
            return False

        logger.error(f"PushPlus 请求失败: HTTP {response.status_code}")
        return False

    def _send_pushplus_chunked(self, api_url: str, content: str, title: str, max_bytes: int) -> bool:
        """Batch send long PushPlus messages, reserving space in the JSON payload."""
        budget = max(1000, max_bytes - 1500)
        chunks = chunk_content_by_max_bytes(content, budget, add_page_marker=True)
        total_chunks = len(chunks)
        success_count = 0

        logger.info(f"PushPlus 分批发送：共 {total_chunks} 批")

        for i, chunk in enumerate(chunks):
            chunk_title = f"{title} ({i+1}/{total_chunks})" if total_chunks > 1 else title
            if self._send_pushplus_message(api_url, chunk, chunk_title):
                success_count += 1
                logger.info(f"PushPlus 第 {i+1}/{total_chunks} 批发送成功")
            else:
                logger.error(f"PushPlus 第 {i+1}/{total_chunks} 批发送失败")

            if i < total_chunks - 1:
                time.sleep(1)

        return success_count == total_chunks
