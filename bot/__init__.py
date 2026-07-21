# -*- coding: utf-8 -*-
"""
===================================
Robot command triggers the system
===================================

Trigger stock analysis and other functions via @Robot or sending commands.
Supports Feishu, DingTalk, WeCom, Telegram, etc. multi-platform.

Module structure:
- models.py: Unified message/response model
- dispatcher.py: Command Dispatcher
- commands/: command processor
- platforms/: platform adapters
- handler.py: Webhook Processor

Usage:
1. Configure environment variables (e.g., tokens for various platforms)
2. Start WebUI service
3. Configure Webhook URL on each platform:
   - Feishu: http://your-server/bot/Feishu
   - DingTalk: http://your-server/bot/DingTalk
   - WeCom: http://your-server/bot/WeCom
   - Telegram: http://your-server/bot/telegram

Supported commands:
- /analyze <Stock Code>  - analyze specified stock
- /market             - market review
- /batch              - Batch analysis of watchlist stocks
- /help               - Show help?
- /status             - System status
"""

from bot.models import BotMessage, BotResponse, ChatType, WebhookResponse
from bot.dispatcher import CommandDispatcher, get_dispatcher

__all__ = [
    'BotMessage',
    'BotResponse',
    'ChatType',
    'WebhookResponse',
    'CommandDispatcher',
    'get_dispatcher',
]
