# -*- coding: utf-8 -*-
"""
ServerChan3 notification service

Responsibilities:
1. via Serversauce3 API send Serversauce3 message
"""
import logging
from typing import Optional
import requests
from datetime import datetime
import re

from src.config import Config
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)


class Serverchan3Sender:
    
    def __init__(self, config: Config):
        """
        Initialization ServerFlavor3 Configuration

        Args:
            config: Configuration object
        """
        self._serverchan3_sendkey = getattr(config, 'serverchan3_sendkey', None)
        
    def send_to_serverchan3(
        self,
        content: str,
        title: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """
        Push message to Serversauce3

        ServerChan3 API format:
        POST https://sctapi.ftqq.com/{sendkey}.send
        Or
        POST https://{num}.push.ft07.com/send/{sendkey}.send
        {
            "title": "Message title",
            "desp": "Message content",
            "options": {}
        }

        ServerChan3 features:
        - Domestic push service, supports multiple domestic system push channels, can push without a backend
        - Simple and easy-to-use API interface

        Args:
            content: Message content in Markdown format
            title: Message title (optional)

        Returns:
            Whether sent successfully
        """
        if not self._serverchan3_sendkey:
            logger.warning("Server酱3 SendKey 未配置，跳过推送")
            return False

        # Process message titles
        if title is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            title = f"📈 股票分析报告 - {date_str}"

        try:
            # Construct URL based on sendkey
            sendkey = self._serverchan3_sendkey
            if sendkey.startswith('sctp'):
                match = re.match(r'sctp(\d+)t', sendkey)
                if match:
                    num = match.group(1)
                    url = f"https://{num}.push.ft07.com/send/{sendkey}.send"
                else:
                    logger.error("Invalid sendkey format for sctp")
                    return False
            else:
                url = f"https://sctapi.ftqq.com/{sendkey}.send"

            # Build request parameters
            params = {
                'title': title,
                'desp': content,
                'options': {}
            }

            # Send request
            headers = {
                'Content-Type': 'application/json;charset=utf-8'
            }
            response = requests.post(url, json=params, headers=headers, timeout=timeout_seconds or 10)

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Server酱3 消息发送成功: {result}")
                return True
            else:
                logger.error(f"Server酱3 请求失败: HTTP {response.status_code}")
                logger.error(f"响应内容: {response.text}")
                return False

        except Exception as exc:
            log_safe_exception(
                logger,
                "ServerChan3 message delivery failed",
                exc,
                error_code="serverchan3_delivery_failed",
            )
            return False
