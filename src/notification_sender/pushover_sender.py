# -*- coding: utf-8 -*-
"""
Pushover Send Notification Service

Responsibilities:
1. Send Pushover messages via Pushover API
"""
import logging
from typing import Optional
from datetime import datetime
import requests

from src.config import Config
from src.utils.sanitize import log_safe_exception
from src.formatters import markdown_to_plain_text


logger = logging.getLogger(__name__)


class PushoverSender:
    
    def __init__(self, config: Config):
        """
        Initialize Pushover configuration

        Args:
            config: Configuration object
        """
        self._pushover_config = {
            'user_key': getattr(config, 'pushover_user_key', None),
            'api_token': getattr(config, 'pushover_api_token', None),
        }
        
    def _is_pushover_configured(self) -> bool:
        """Verify Pushover configuration is complete"""
        return bool(self._pushover_config['user_key'] and self._pushover_config['api_token'])

    def send_to_pushover(
        self,
        content: str,
        title: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Push message to Pushover
        
        Pushover API Format:
        POST https://api.pushover.net/1/messages.json
        {
            "token": "Apply API Token",
            "user": "User Key",
            "message": "Message content",
            "title": "Title(Optional)"
        }
        
        Pushover Features:
        - Supports multi-platform push on iOS/Android/desktop
        - Message limited to 1024 characters
        - Supports priority settings.
        - Supports HTML format
        
        Args:
            content: Message content (Markdown format, converted to plain text)
            title: Message title (optional, defaults to "Stock Analysis Report")

        Returns:
            Whether sent successfully
        """
        if not self._is_pushover_configured():
            logger.warning("Pushover 配置不完整，跳过推送")
            return False
        
        user_key = self._pushover_config['user_key']
        api_token = self._pushover_config['api_token']
        
        # Pushover API Endpoint
        api_url = "https://api.pushover.net/1/messages.json"
        
        # Process message titles
        if title is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            title = f"📈 股票分析报告 - {date_str}"
        
        # Pushover Message Limit 1024 Characters
        max_length = 1024
        
        # Convert Markdown to plain text (Pushover supports HTML, but plain text is more universal)
        plain_content = markdown_to_plain_text(content)
        
        if len(plain_content) <= max_length:
            # Single message sending
            return self._send_pushover_message(api_url, user_key, api_token, plain_content, title, timeout_seconds=timeout_seconds)
        else:
            # Segment long messages
            return self._send_pushover_chunked(
                api_url,
                user_key,
                api_token,
                plain_content,
                title,
                max_length,
                timeout_seconds=timeout_seconds,
            )
      
    def _send_pushover_message(
        self, 
        api_url: str, 
        user_key: str, 
        api_token: str, 
        message: str, 
        title: str,
        priority: int = 0,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Send single Pushover message
        
        Args:
            api_url: Pushover API Endpoint
            user_key: User Key
            api_token: Apply API Token
            message: Message content
            title: message title
            priority: priority (-2 ~ 2, default 0)
        """
        try:
            payload = {
                "token": api_token,
                "user": user_key,
                "message": message,
                "title": title,
                "priority": priority,
            }
            
            response = requests.post(api_url, data=payload, timeout=timeout_seconds or 30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 1:
                    logger.info("Pushover 消息发送成功")
                    return True
                else:
                    errors = result.get('errors', ['未知错误'])
                    logger.error(f"Pushover 返回错误: {errors}")
                    return False
            else:
                logger.error(f"Pushover 请求失败: HTTP {response.status_code}")
                logger.debug(f"响应内容: {response.text}")
                return False
                
        except Exception as exc:
            log_safe_exception(
                logger,
                "Pushover message delivery failed",
                exc,
                error_code="pushover_delivery_failed",
            )
            return False
    
    def _send_pushover_chunked(
        self, 
        api_url: str, 
        user_key: str, 
        api_token: str, 
        content: str, 
        title: str,
        max_length: int,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Segment long Pushover messages
        
        Split by paragraphs, ensuring each paragraph does not exceed the maximum length.
        """
        import time
        
        # Split by paragraphs (lines or double newlines).
        if "────────" in content:
            sections = content.split("────────")
            separator = "────────"
        else:
            sections = content.split("\n\n")
            separator = "\n\n"
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for section in sections:
            # Calculate the actual length after adding this section
            # join() only places delimiters between elements, not after each element
            # So: the first element does not need a delimiter, subsequent elements require a delimiter to connect.
            if current_chunk:
                # Existing elements, adding a new element requires: current length + separator + new section
                new_length = current_length + len(separator) + len(section)
            else:
                # First element, no delimiter.
                new_length = len(section)
            
            if new_length > max_length:
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                current_chunk = [section]
                current_length = len(section)
            else:
                current_chunk.append(section)
                current_length = new_length
        
        if current_chunk:
            chunks.append(separator.join(current_chunk))
        
        total_chunks = len(chunks)
        success_count = 0
        
        logger.info(f"Pushover 分批发送：共 {total_chunks} 批")
        
        for i, chunk in enumerate(chunks):
            # Add pagination markers to titles
            chunk_title = f"{title} ({i+1}/{total_chunks})" if total_chunks > 1 else title
            
            if self._send_pushover_message(
                api_url,
                user_key,
                api_token,
                chunk,
                chunk_title,
                timeout_seconds=timeout_seconds,
            ):
                success_count += 1
                logger.info(f"Pushover 第 {i+1}/{total_chunks} 批发送成功")
            else:
                logger.error(f"Pushover 第 {i+1}/{total_chunks} 批发送失败")
            
            # Batch interval to avoid rate limits
            if i < total_chunks - 1:
                time.sleep(1)

        return success_count == total_chunks
