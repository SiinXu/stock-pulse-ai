# -*- coding: utf-8 -*-
"""
===================================
钉钉平台适配器
===================================

处理钉钉机器人的 Webhook 回调。

钉钉机器人文档：
https://open.dingtalk.com/document/robots/robot-overview
"""

import hashlib
import hmac
import base64
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import quote_plus

from bot.platforms.base import BotPlatform
from bot.models import BotMessage, BotResponse, WebhookResponse, ChatType
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class DingtalkPlatform(BotPlatform):
    """
    钉钉平台适配器
    
    支持：
    - 企业内部机器人回调
    - 群机器人 Outgoing 回调
    - 消息签名验证
    
    配置要求：
    - DINGTALK_APP_KEY: 应用 AppKey
    - DINGTALK_APP_SECRET: 应用 AppSecret（用于签名验证）
    """
    
    def __init__(self):
        from src.config import get_config
        config = get_config()
        
        self._app_key = getattr(config, 'dingtalk_app_key', None)
        self._app_secret = getattr(config, 'dingtalk_app_secret', None)
    
    @property
    def platform_name(self) -> str:
        return "dingtalk"
    
    def verify_request(self, headers: Dict[str, str], body: bytes) -> bool:
        """
        验证钉钉请求签名
        
        钉钉签名算法：
        1. 获取 timestamp 和 sign
        2. 计算：base64(hmac_sha256(timestamp + "\n" + app_secret))
        3. 比对签名
        """
        if not self._app_secret:
            logger.warning(
                "[DingTalk] app_secret is not configured; skipping signature verification"
            )
            return True
        
        timestamp = headers.get('timestamp', '')
        sign = headers.get('sign', '')
        
        if not timestamp or not sign:
            logger.warning("[DingTalk] Signature parameters are missing")
            return True  # May be an unsigned request.
        
        # Validation timestamp (valid for 1 hour)
        try:
            request_time = int(timestamp)
            current_time = int(time.time() * 1000)
            if abs(current_time - request_time) > 3600 * 1000:
                logger.warning("[DingTalk] Request timestamp has expired")
                return False
        except ValueError:
            logger.warning("[DingTalk] Request timestamp is invalid")
            return False
        
        # Calculate signature
        string_to_sign = f"{timestamp}\n{self._app_secret}"
        hmac_code = hmac.new(
            self._app_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        expected_sign = base64.b64encode(hmac_code).decode('utf-8')
        
        if sign != expected_sign:
            logger.warning("[DingTalk] Signature verification failed")
            return False
        
        return True
    
    def handle_challenge(self, data: Dict[str, Any]) -> Optional[WebhookResponse]:
        """钉钉不需要 URL 验证"""
        return None
    
    def parse_message(self, data: Dict[str, Any]) -> Optional[BotMessage]:
        """
        解析钉钉消息
        
        钉钉 Outgoing 机器人消息格式：
        {
            "msgtype": "text",
            "text": {
                "content": "@机器人 /analyze 600519"
            },
            "msgId": "xxx",
            "createAt": "1234567890",
            "conversationType": "2",  # 1=单聊, 2=群聊
            "conversationId": "xxx",
            "conversationTitle": "群名",
            "senderId": "xxx",
            "senderNick": "用户昵称",
            "senderCorpId": "xxx",
            "senderStaffId": "xxx",
            "chatbotUserId": "xxx",
            "atUsers": [{"dingtalkId": "xxx", "staffId": "xxx"}],
            "isAdmin": false,
            "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=xxx",
            "sessionWebhookExpiredTime": 1234567890
        }
        """
        # Check the message type
        msg_type = data.get('msgtype', '')
        if msg_type != 'text':
            logger.debug(
                "[DingTalk] Ignoring non-text message: type_length=%d",
                len(str(msg_type)),
            )
            return None
        
        # Get message content
        text_content = data.get('text', {})
        raw_content = text_content.get('content', '')
        
        # Extracts command (excluding @robot)
        content = self._extract_command(raw_content)
        
        # Check if a robot was mentioned (@ed)
        at_users = data.get('atUsers', [])
        mentioned = len(at_users) > 0
        
        # Session type
        conversation_type = data.get('conversationType', '')
        if conversation_type == '1':
            chat_type = ChatType.PRIVATE
        elif conversation_type == '2':
            chat_type = ChatType.GROUP
        else:
            chat_type = ChatType.UNKNOWN
        
        # Create timestamp
        create_at = data.get('createAt', '')
        try:
            timestamp = datetime.fromtimestamp(int(create_at) / 1000)
        except (ValueError, TypeError):
            timestamp = datetime.now()
        
        # Save the session webhook for replying
        session_webhook = data.get('sessionWebhook', '')
        
        return BotMessage(
            platform=self.platform_name,
            message_id=data.get('msgId', ''),
            user_id=data.get('senderId', ''),
            user_name=data.get('senderNick', ''),
            chat_id=data.get('conversationId', ''),
            chat_type=chat_type,
            content=content,
            raw_content=raw_content,
            mentioned=mentioned,
            mentions=[u.get('dingtalkId', '') for u in at_users],
            timestamp=timestamp,
            raw_data={
                **data,
                '_session_webhook': session_webhook,
            },
        )
    
    def _extract_command(self, text: str) -> str:
        """
        提取命令内容（去除 @机器人）
        
        钉钉的 @用户 格式通常是 @昵称 后跟空格
        """
        # Simple processing: remove the leading @xxx part
        import re
        # Matches the beginning of @xxx (can be Chinese or English)
        text = re.sub(r'^@[\S]+\s*', '', text.strip())
        return text.strip()
    
    def format_response(
        self, 
        response: BotResponse, 
        message: BotMessage
    ) -> WebhookResponse:
        """
        格式化钉钉响应
        
        钉钉 Outgoing 机器人可以直接在响应中返回消息。
        也可以使用 sessionWebhook 异步发送。
        
        响应格式：
        {
            "msgtype": "text" | "markdown",
            "text": {"content": "xxx"},
            "markdown": {"title": "xxx", "text": "xxx"},
            "at": {"atUserIds": ["xxx"], "isAtAll": false}
        }
        """
        if not response.text:
            return WebhookResponse.success()
        
        # Build the response
        if response.markdown:
            body = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "股票分析助手",
                    "text": response.text,
                }
            }
        else:
            body = {
                "msgtype": "text",
                "text": {
                    "content": response.text,
                }
            }
        
        # Sender
        if response.at_user and message.user_id:
            body["at"] = {
                "atUserIds": [message.user_id],
                "isAtAll": False,
            }
        
        return WebhookResponse.success(body)
    
    def send_by_session_webhook(
        self, 
        session_webhook: str, 
        response: BotResponse,
        message: BotMessage
    ) -> bool:
        """
        通过 sessionWebhook 发送消息
        
        适用于需要异步发送或多条消息的场景。
        
        Args:
            session_webhook: 钉钉提供的会话 Webhook URL
            response: 响应对象
            message: 原始消息对象
            
        Returns:
            是否发送成功
        """
        if not session_webhook:
            logger.warning("[DingTalk] No sessionWebhook is available")
            return False
        
        import requests
        
        try:
            # Build message
            if response.markdown:
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": "股票分析助手",
                        "text": response.text,
                    }
                }
            else:
                payload = {
                    "msgtype": "text",
                    "text": {
                        "content": response.text,
                    }
                }
            
            # Sender
            if response.at_user and message.user_id:
                payload["at"] = {
                    "atUserIds": [message.user_id],
                    "isAtAll": False,
                }
            
            # Send request
            resp = requests.post(
                session_webhook,
                json=payload,
                timeout=10
            )
            
            if resp.status_code == 200:
                result = resp.json()
                if result.get('errcode') == 0:
                    logger.info("[DingTalk] sessionWebhook delivery succeeded")
                    return True
                else:
                    error_code = result.get('errcode')
                    safe_error_code = error_code if isinstance(error_code, (int, float)) else "unknown"
                    logger.error(
                        "[DingTalk] sessionWebhook delivery failed: error_code=%s",
                        safe_error_code,
                    )
                    return False
            else:
                logger.error(
                    "[DingTalk] sessionWebhook request failed: status_code=%s",
                    resp.status_code,
                )
                return False
                
        except Exception as exc:
            log_safe_exception(
                logger,
                "[DingTalk] sessionWebhook delivery failed",
                exc,
                error_code="bot_dingtalk_session_webhook_failed",
            )
            return False
