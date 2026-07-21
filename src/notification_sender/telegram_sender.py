# -*- coding: utf-8 -*-
"""
Telegram reminder service

Responsibilities:
1. Send text messages via Telegram Bot API
2. Send image messages via Telegram Bot API
"""
import logging
from typing import Optional
import requests
import time
import re

from src.config import Config
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)


class TelegramSender:

    def __init__(self, config: Config):
        """
        Initialize Telegram configuration

        Args:
            config: Configuration object
        """
        self._telegram_config = {
            'bot_token': getattr(config, 'telegram_bot_token', None),
            'chat_id': getattr(config, 'telegram_chat_id', None),
            'message_thread_id': getattr(config, 'telegram_message_thread_id', None),
        }

    def _is_telegram_configured(self) -> bool:
        """Verify Telegram configuration is complete"""
        return bool(self._telegram_config['bot_token'] and self._telegram_config['chat_id'])

    def send_to_telegram(
        self,
        content: str,
        *,
        chat_id: Optional[str] = None,
        message_thread_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Push messages to Telegram bot

        Telegram Bot API format:
        POST https://api.telegram.org/bot<token>/sendMessage
        {
            "chat_id": "xxx",
            "text": "Message content",
            "parse_mode": "Markdown"
        }

        Args:
            content: Message content in Markdown format

        Returns:
            Whether sent successfully
        """
        target_chat_id = chat_id if chat_id is not None else self._telegram_config.get("chat_id")
        target_message_thread_id = (
            message_thread_id
            if message_thread_id is not None
            else self._telegram_config.get("message_thread_id")
        )

        if not (self._telegram_config["bot_token"] and target_chat_id):
            logger.warning("Telegram 配置不完整，跳过推送")
            return False

        bot_token = self._telegram_config['bot_token']
        chat_id = target_chat_id
        message_thread_id = target_message_thread_id

        try:
            # Telegram API Endpoint
            api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            # Telegram message maximum length 4096 characters
            max_length = 4096

            telegram_content = self._convert_to_telegram_markdown(content)

            if len(telegram_content) <= max_length:
                # Single message sending
                return self._send_telegram_message(
                    api_url,
                    chat_id,
                    content,
                    message_thread_id,
                    timeout_seconds=timeout_seconds,
                )
            else:
                # Segment based on the final payload after Markdown escaping to avoid exceeding limits due to escape characters
                return self._send_telegram_chunked(
                    api_url,
                    chat_id,
                    telegram_content,
                    max_length,
                    message_thread_id,
                    timeout_seconds=timeout_seconds,
                )

        except Exception as exc:
            log_safe_exception(
                logger,
                "Telegram message delivery failed",
                exc,
                error_code="telegram_delivery_failed",
            )
            return False

    def _send_telegram_message(
        self,
        api_url: str,
        chat_id: str,
        text: str,
        message_thread_id: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
        markdown_converted: bool = False,
    ) -> bool:
        """Send a single Telegram message with exponential backoff retry (Fixes #287)"""
        # Convert Markdown to Telegram-compatible format
        telegram_text = text if markdown_converted else self._convert_to_telegram_markdown(text)

        payload = {
            "chat_id": chat_id,
            "text": telegram_text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        if message_thread_id:
            payload['message_thread_id'] = message_thread_id

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(api_url, json=payload, timeout=timeout_seconds or 10)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if attempt < max_retries:
                    delay = 2 ** attempt  # 2s, 4s
                    log_safe_exception(
                        logger,
                        "Telegram request failed; retry scheduled",
                        exc,
                        error_code="telegram_request_retry",
                        level=logging.WARNING,
                        context={
                            "attempt": attempt,
                            "max_attempts": max_retries,
                            "retry_in_seconds": delay,
                        },
                    )
                    time.sleep(delay)
                    continue
                else:
                    log_safe_exception(
                        logger,
                        "Telegram request failed after retries",
                        exc,
                        error_code="telegram_request_retries_exhausted",
                        context={"attempt": attempt},
                    )
                    return False

            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    logger.info("Telegram 消息发送成功")
                    return True
                else:
                    error_desc = result.get('description', '未知错误')
                    logger.error(f"Telegram 返回错误: {error_desc}")

                    # If Markdown parsing failed, fall back to plain text
                    if self._should_fallback_to_plain_text(error_desc=error_desc):
                        if self._send_plain_text_fallback(api_url, payload, text, timeout_seconds=timeout_seconds):
                            return True

                    return False
            elif response.status_code == 429:
                # Rate limited — respect Retry-After header
                retry_after = int(response.headers.get('Retry-After', 2 ** attempt))
                if attempt < max_retries:
                    logger.warning(f"Telegram rate limited, retrying in {retry_after}s "
                                   f"(attempt {attempt}/{max_retries})...")
                    time.sleep(retry_after)
                    continue
                else:
                    logger.error(f"Telegram rate limited after {max_retries} attempts")
                    return False
            else:
                if attempt < max_retries and response.status_code >= 500:
                    delay = 2 ** attempt
                    logger.warning(f"Telegram server error HTTP {response.status_code} "
                                   f"(attempt {attempt}/{max_retries}), retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                if self._should_fallback_to_plain_text(response_text=response.text):
                    if self._send_plain_text_fallback(api_url, payload, text, timeout_seconds=timeout_seconds):
                        return True
                logger.error(f"Telegram 请求失败: HTTP {response.status_code}")
                logger.error(f"响应内容: {response.text}")
                return False

        return False

    @staticmethod
    def _should_fallback_to_plain_text(error_desc: str = "", response_text: str = "") -> bool:
        """Detect Telegram Markdown parsing failures that should retry as plain text."""
        haystack = f"{error_desc}\n{response_text}".lower()
        markers = (
            "can't parse entities",
            "can't parse entity",
            "can't find end of the entity",
            "parse entities",
            "parse_mode",
            "markdown",
        )
        return any(marker in haystack for marker in markers)

    def _send_plain_text_fallback(
        self,
        api_url: str,
        payload: dict,
        text: str,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """Retry Telegram send without parse_mode when Markdown parsing fails."""
        logger.info("Telegram Markdown 解析失败，尝试使用纯文本格式重新发送...")
        plain_payload = dict(payload)
        plain_payload.pop('parse_mode', None)
        plain_payload['text'] = text

        try:
            response = requests.post(api_url, json=plain_payload, timeout=timeout_seconds or 10)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            log_safe_exception(
                logger,
                "Telegram plain-text fallback failed",
                exc,
                error_code="telegram_plain_text_fallback_failed",
            )
            return False

        if response.status_code == 200:
            try:
                result = response.json()
            except ValueError:
                logger.error("Telegram 纯文本回退失败: 响应不是有效 JSON")
                logger.error(f"响应内容: {response.text}")
                return False

            if result.get('ok'):
                logger.info("Telegram 消息发送成功（纯文本）")
                return True

            logger.error("Telegram 纯文本回退失败: Telegram API 返回 ok=false")
            logger.error(f"响应内容: {response.text}")
            return False

        logger.error(f"Telegram 纯文本回退失败: HTTP {response.status_code}")
        logger.error(f"响应内容: {response.text}")
        return False

    def _send_telegram_chunked(
        self,
        api_url: str,
        chat_id: str,
        content: str,
        max_length: int,
        message_thread_id: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """Segment long messages based on converted Telegram Markdown payload."""
        # Segment by paragraph.
        sections = content.split("\n---\n")
        delimiter = "\n---\n"
        delimiter_length = len(delimiter)

        current_chunk = []
        current_length = 0
        all_success = True
        chunk_index = 1

        def _flush_chunk() -> bool:
            nonlocal current_chunk, current_length, chunk_index, all_success
            if not current_chunk:
                return all_success

            chunk_content = "\n---\n".join(current_chunk)
            logger.info(f"发送 Telegram 消息块 {chunk_index}...")
            chunk_index += 1
            current_chunk = []
            current_length = 0
            if not self._send_telegram_message(
                api_url,
                chat_id,
                chunk_content,
                message_thread_id,
                timeout_seconds=timeout_seconds,
                markdown_converted=True,
            ):
                all_success = False
            return all_success

        def _split_long_section(section: str, limit: int) -> list[str]:
            if len(section) <= limit:
                return [section]
            chunks: list[str] = []
            for start in range(0, len(section), limit):
                chunks.append(section[start:start + limit])
            return chunks

        for section in sections:
            if len(section) > max_length:
                # Force segment cut based on single-segment breach, Avoid dependency"\\n---\\n"Long send caused by boundary
                if not _flush_chunk():
                    return False
                for long_chunk in _split_long_section(section, max_length):
                    logger.info(f"发送 Telegram 消息块 {chunk_index}...")
                    chunk_index += 1
                    if not self._send_telegram_message(
                        api_url,
                        chat_id,
                        long_chunk,
                        message_thread_id,
                        timeout_seconds=timeout_seconds,
                        markdown_converted=True,
                    ):
                        all_success = False
                continue

            additional_length = len(section)
            if current_chunk:
                additional_length += delimiter_length

            if current_length + additional_length > max_length:
                _flush_chunk()
                current_chunk = [section]
                current_length = len(section)
                continue

            current_chunk.append(section)
            current_length += additional_length

        # Send the last piece
        if not _flush_chunk():
            return False

        return all_success

    def _send_telegram_photo(self, image_bytes: bytes) -> bool:
        """Send image via Telegram sendPhoto API (Issue #289)."""
        if not self._is_telegram_configured():
            return False
        bot_token = self._telegram_config['bot_token']
        chat_id = self._telegram_config['chat_id']
        message_thread_id = self._telegram_config.get('message_thread_id')
        api_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        try:
            data = {"chat_id": chat_id}
            if message_thread_id:
                data['message_thread_id'] = message_thread_id
            files = {"photo": ("report.png", image_bytes, "image/png")}
            response = requests.post(api_url, data=data, files=files, timeout=30)
            if response.status_code == 200 and response.json().get('ok'):
                logger.info("Telegram 图片发送成功")
                return True
            logger.error("Telegram 图片发送失败: %s", response.text[:200])
            return False
        except Exception as exc:
            log_safe_exception(
                logger,
                "Telegram image delivery failed",
                exc,
                error_code="telegram_image_delivery_failed",
            )
            return False

    def _convert_to_telegram_markdown(self, text: str) -> str:
        """
        Convert standard Markdown to Telegram-supported format

        Telegram Markdown Limit:
        - Does not support # Title
        - Use *bold* instead of **bold**
        - Use _italic_
        """
        result = text

        # Remove # header tags (Telegram does not support)
        result = re.sub(r'^#{1,6}\s+', '', result, flags=re.MULTILINE)

        # Convert **bold** to *bold*
        result = re.sub(r'\*\*(.+?)\*\*', r'*\1*', result)

        # Escape special characters for Telegram Markdown, but preserve link syntax [text](url)
        # Step 1: temporarily protect markdown links
        import uuid as _uuid
        _link_placeholder = f"__LINK_{_uuid.uuid4().hex[:8]}__"
        _links = []
        def _save_link(m):
            _links.append(m.group(0))
            return f"{_link_placeholder}{len(_links) - 1}"
        result = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _save_link, result)

        # Step 2: escape remaining special chars
        for char in ['[', ']', '(', ')']:
            result = result.replace(char, f'\\{char}')

        # Step 3: restore links
        for i, link in enumerate(_links):
            result = result.replace(f"{_link_placeholder}{i}", link)

        return result
