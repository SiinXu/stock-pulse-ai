# -*- coding: utf-8 -*-
"""
===================================
Robot message model
===================================

Define a unified message and response model, shielding differences across platforms.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List


class ChatType(str, Enum):
    """Session type"""
    GROUP = "group"      # Chat room
    PRIVATE = "private"  # Private chat
    UNKNOWN = "unknown"  # Unknown.


class Platform(str, Enum):
    """Platform type"""
    FEISHU = "feishu"        # Feishu
    DINGTALK = "dingtalk"    # DingTalk
    WECOM = "wecom"          # WeCom
    TELEGRAM = "telegram"    # Telegram
    UNKNOWN = "unknown"      # Unknown.


@dataclass
class BotMessage:
    """
    Use a unified robot message model
    
    Standardize message formats from each platform to be compatible with the command processor.
    
    Attributes:
        platform: platform identifier
        message_id: Message ID(platform original data ID)
        user_id: Sender ID
        user_name: Sender name
        chat_id: group chat ID or private chat ID
        chat_type: conversation type
        content: message text content (excluding @robot parts)
        raw_content: raw message content
        mentioned: whether mentioned the robot
        mentions: user list
        timestamp: message timestamp
        raw_data: raw request data (platform-specific, for debugging)
    """
    platform: str
    message_id: str
    user_id: str
    user_name: str
    chat_id: str
    chat_type: ChatType
    content: str
    raw_content: str = ""
    mentioned: bool = False
    mentions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def get_command_and_args(self, prefix: str = "/") -> tuple:
        """
        Parse commands and parameters
        
        Args:
            prefix: command prefix, default "/"
            
        Returns:
            (command, args) Tuple, If ("analyze", ["600519"])
            If not a command, return (None, [])
        """
        text = self.content.strip()
        
        # Check if it starts with a command prefix
        if not text.startswith(prefix):
            # Attempt to match Chinese commands (no prefix)
            chinese_commands = {
                '分析': 'analyze',
                '大盘': 'market',
                '批量': 'batch',
                '帮助': 'help',
                '状态': 'status',
            }
            for cn_cmd, en_cmd in chinese_commands.items():
                if text.startswith(cn_cmd):
                    args = text[len(cn_cmd):].strip().split()
                    return en_cmd, args
            return None, []
        
        # Remove prefix
        text = text[len(prefix):]
        
        # Splitting command and parameters
        parts = text.split()
        if not parts:
            return None, []
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        return command, args
    
    def is_command(self, prefix: str = "/") -> bool:
        """Check if the message is a command"""
        cmd, _ = self.get_command_and_args(prefix)
        return cmd is not None


@dataclass
class BotResponse:
    """
    Use a unified robot response model
    
    Command processor returns this model, which is converted to a platform-specific format by the platform adapter.
    
    Attributes:
        text: reply text
        markdown: Whether the content is Markdown
        at_user: Whether to @sender
        reply_to_message: Reply to original message?
        extra: Extra data (platform-specific)
    """
    text: str
    markdown: bool = False
    at_user: bool = True
    reply_to_message: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def text_response(cls, text: str, at_user: bool = True) -> 'BotResponse':
        """Create plain text response"""
        return cls(text=text, markdown=False, at_user=at_user)
    
    @classmethod
    def markdown_response(cls, text: str, at_user: bool = True) -> 'BotResponse':
        """Create Markdown response"""
        return cls(text=text, markdown=True, at_user=at_user)
    
    @classmethod
    def error_response(cls, message: str) -> 'BotResponse':
        """Create error response"""
        return cls(text=f"❌ 错误：{message}", markdown=False, at_user=True)


@dataclass
class WebhookResponse:
    """
    Response model for Webhook
    
    Platform adapter returns this model, including HTTP response content.
    
    Attributes:
        status_code: HTTP Status code
        body: Response body (dictionary, will be JSON serialized)
        headers: additional response headers
    """
    status_code: int = 200
    body: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def success(cls, body: Optional[Dict] = None) -> 'WebhookResponse':
        """Create a success response"""
        return cls(status_code=200, body=body or {})
    
    @classmethod
    def challenge(cls, challenge: str) -> 'WebhookResponse':
        """Create validation response (for platform URL verification)"""
        return cls(status_code=200, body={"challenge": challenge})
    
    @classmethod
    def error(cls, message: str, status_code: int = 400) -> 'WebhookResponse':
        """Create error response"""
        return cls(status_code=status_code, body={"error": message})
