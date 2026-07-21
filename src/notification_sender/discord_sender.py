# -*- coding: utf-8 -*-
"""
Discord reminder service

Responsibilities:
1. Send Discord messages via webhook or Discord bot API
"""
import logging
import time
from typing import Optional

import requests

from src.config import Config
from src.utils.sanitize import log_safe_exception
from src.formatters import MIN_MAX_WORDS, chunk_content_by_max_words


logger = logging.getLogger(__name__)


DISCORD_MAX_CONTENT_LENGTH = 2000
DISCORD_MAX_RETRIES = 3
DISCORD_CHUNK_SLEEP_SECONDS = 1


class DiscordSender:
    
    def __init__(self, config: Config):
        """
        Initialize Discord configuration

        Args:
            config: Configuration object
        """
        self._discord_config = {
            'bot_token': getattr(config, 'discord_bot_token', None),
            'channel_id': getattr(config, 'discord_main_channel_id', None),
            'webhook_url': getattr(config, 'discord_webhook_url', None),
        }
        self._discord_max_words = self._normalize_max_words(
            getattr(config, 'discord_max_words', DISCORD_MAX_CONTENT_LENGTH)
        )
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)

    @staticmethod
    def _normalize_max_words(value) -> int:
        try:
            configured = int(value)
        except (TypeError, ValueError):
            configured = DISCORD_MAX_CONTENT_LENGTH
        return max(MIN_MAX_WORDS, min(configured, DISCORD_MAX_CONTENT_LENGTH))
    
    def _is_discord_configured(self) -> bool:
        """Verify Discord configuration is complete (supports Bot or Webhook)"""
        # If the Webhook or complete Bot Token+Channel is configured, it's considered available.
        bot_ok = bool(self._discord_config['bot_token'] and self._discord_config['channel_id'])
        webhook_ok = bool(self._discord_config['webhook_url'])
        return bot_ok or webhook_ok
    
    def send_to_discord(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Push message to Discord (supports Webhook and Bot API)
        
        Args:
            content: Markdown Message content format
            
        Returns:
            Whether sent successfully
        """
        # Split content to avoid a single message exceeding Discord limits
        chunks = self._split_discord_content(content)

        # Prioritize using Webhook (simple configuration, low permissions)
        if self._discord_config['webhook_url']:
            return self._send_discord_chunks(
                chunks,
                self._send_discord_webhook,
                "Webhook",
                timeout_seconds=timeout_seconds,
            )

        # Then use Bot API (high permission, requires channel_id).
        if self._discord_config['bot_token'] and self._discord_config['channel_id']:
            return self._send_discord_chunks(
                chunks,
                self._send_discord_bot,
                "Bot",
                timeout_seconds=timeout_seconds,
            )

        logger.warning("Discord 配置不完整，跳过推送")
        return False

    def _split_discord_content(self, content: str) -> list[str]:
        """Split Discord content limit messages."""
        try:
            chunks = chunk_content_by_max_words(content, self._discord_max_words)
            if len(chunks) > 1:
                chunks = chunk_content_by_max_words(
                    content,
                    self._discord_max_words,
                    add_page_marker=True,
                )
            return chunks
        except ValueError as exc:
            log_safe_exception(
                logger,
                "Discord message chunking failed",
                exc,
                error_code="discord_message_chunking_failed",
            )
            return chunk_content_by_max_words(
                content,
                DISCORD_MAX_CONTENT_LENGTH,
                add_page_marker=True,
            )

    def _send_discord_chunks(
        self,
        chunks: list[str],
        send_once,
        channel_name: str,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """Send Discord messages slice by slice; failed slices should not block subsequent slice attempts."""
        total_chunks = len(chunks)
        success_count = 0

        if total_chunks > 1:
            logger.info("Discord %s 分批发送：共 %d 批", channel_name, total_chunks)

        for i, chunk in enumerate(chunks):
            if send_once(chunk, timeout_seconds=timeout_seconds):
                success_count += 1
                if total_chunks > 1:
                    logger.info("Discord %s 第 %d/%d 批发送成功", channel_name, i + 1, total_chunks)
            else:
                logger.error("Discord %s 第 %d/%d 批发送失败", channel_name, i + 1, total_chunks)

            if i < total_chunks - 1:
                time.sleep(DISCORD_CHUNK_SLEEP_SECONDS)

        return success_count == total_chunks

  
    def _send_discord_webhook(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Use Webhook to send messages to Discord
        
        Markdown format supported by Discord webhooks
        
        Args:
            content: Markdown Message content format
            
        Returns:
            Whether sent successfully
        """
        payload = {
            'content': content,
            'username': 'A股分析机器人',
            'avatar_url': 'https://picsum.photos/200'
        }

        return self._post_discord_message(
            self._discord_config['webhook_url'],
            payload,
            success_statuses=(200, 204),
            verify=self._webhook_verify_ssl,
            timeout_seconds=timeout_seconds,
            channel_name="Webhook",
        )
    
    def _send_discord_bot(self, content: str, *, timeout_seconds: Optional[float] = None) -> bool:
        """
        Use Bot API to send messages to Discord
        
        Args:
            content: Markdown Message content format
            
        Returns:
            Whether sent successfully
        """
        headers = {
            'Authorization': f'Bot {self._discord_config["bot_token"]}',
            'Content-Type': 'application/json'
        }
        payload = {'content': content}
        url = f'https://discord.com/api/v10/channels/{self._discord_config["channel_id"]}/messages'

        return self._post_discord_message(
            url,
            payload,
            headers=headers,
            success_statuses=(200,),
            timeout_seconds=timeout_seconds,
            channel_name="Bot",
        )

    def _post_discord_message(
        self,
        url: str,
        payload: dict,
        *,
        success_statuses: tuple[int, ...],
        headers: Optional[dict] = None,
        verify: Optional[bool] = None,
        timeout_seconds: Optional[float] = None,
        channel_name: str,
    ) -> bool:
        """Send single Discord message, and reuse Telegram's limited retry logic for handling 429/5xx errors."""
        request_kwargs = {
            'json': payload,
            'timeout': timeout_seconds or 10,
        }
        if headers:
            request_kwargs['headers'] = headers
        if verify is not None:
            request_kwargs['verify'] = verify

        for attempt in range(1, DISCORD_MAX_RETRIES + 1):
            try:
                response = requests.post(url, **request_kwargs)
            except requests.exceptions.RequestException as exc:
                if attempt < DISCORD_MAX_RETRIES:
                    delay = 2 ** attempt
                    log_safe_exception(
                        logger,
                        "Discord request failed; retry scheduled",
                        exc,
                        error_code="discord_request_retry",
                        level=logging.WARNING,
                        context={
                            "channel": channel_name,
                            "attempt": attempt,
                            "max_attempts": DISCORD_MAX_RETRIES,
                            "retry_in_seconds": delay,
                        },
                    )
                    time.sleep(delay)
                    continue
                log_safe_exception(
                    logger,
                    "Discord request failed after retries",
                    exc,
                    error_code="discord_request_retries_exhausted",
                    context={"channel": channel_name, "attempt": attempt},
                )
                return False

            if response.status_code in success_statuses:
                logger.info("Discord %s 消息发送成功", channel_name)
                return True

            if response.status_code == 429 and attempt < DISCORD_MAX_RETRIES:
                retry_after = self._get_retry_after_seconds(response, attempt)
                logger.warning(
                    "Discord %s 触发限流，%s 秒后重试（%d/%d）",
                    channel_name,
                    retry_after,
                    attempt,
                    DISCORD_MAX_RETRIES,
                )
                time.sleep(retry_after)
                continue

            if response.status_code >= 500 and attempt < DISCORD_MAX_RETRIES:
                delay = 2 ** attempt
                logger.warning(
                    "Discord %s 服务端错误 HTTP %s（%d/%d），%s 秒后重试",
                    channel_name,
                    response.status_code,
                    attempt,
                    DISCORD_MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue

            logger.error(
                "Discord %s 发送失败: %s %s",
                channel_name,
                response.status_code,
                response.text,
            )
            return False

        return False

    @staticmethod
    def _get_retry_after_seconds(response, attempt: int) -> float:
        try:
            retry_after = response.json().get('retry_after')
            if retry_after is not None:
                return max(0.0, float(retry_after))
        except (AttributeError, TypeError, ValueError):
            pass

        try:
            retry_after = response.headers.get('Retry-After')
            if retry_after is not None:
                return max(0.0, float(retry_after))
        except AttributeError:
            pass

        return float(2 ** attempt)
