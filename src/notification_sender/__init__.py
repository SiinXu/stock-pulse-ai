# -*- coding: utf-8 -*-
"""
===================================
通知发送层模块
===================================

提供各种通知发送服务
"""

from .astrbot_sender import AstrbotSender
from .custom_webhook_sender import CustomWebhookSender
from .discord_sender import DiscordSender
from .email_sender import EmailSender
from .feishu_sender import FeishuSender
from .gotify_sender import GotifySender, resolve_gotify_message_endpoint
from .ntfy_sender import NtfySender, resolve_ntfy_endpoint
from .pushover_sender import PushoverSender
from .pushplus_sender import PushplusSender
from .serverchan3_sender import Serverchan3Sender
from .slack_sender import SlackSender
from .telegram_sender import TelegramSender
from .wechat_sender import WechatSender, WECHAT_IMAGE_MAX_BYTES
from .dingtalk_sender import DingtalkSender


__all__ = (
    "AstrbotSender",
    "CustomWebhookSender",
    "DingtalkSender",
    "DiscordSender",
    "EmailSender",
    "FeishuSender",
    "GotifySender",
    "NtfySender",
    "PushoverSender",
    "PushplusSender",
    "Serverchan3Sender",
    "SlackSender",
    "TelegramSender",
    "WECHAT_IMAGE_MAX_BYTES",
    "WechatSender",
    "astrbot_sender",
    "custom_webhook_sender",
    "dingtalk_sender",
    "discord_sender",
    "email_sender",
    "feishu_sender",
    "gotify_sender",
    "ntfy_sender",
    "pushover_sender",
    "pushplus_sender",
    "resolve_gotify_message_endpoint",
    "resolve_ntfy_endpoint",
    "serverchan3_sender",
    "slack_sender",
    "telegram_sender",
    "wechat_sender",
)
