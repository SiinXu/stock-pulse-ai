# -*- coding: utf-8 -*-
"""
===================================
命令处理器模块
===================================

包含所有机器人命令的实现。
"""

from src.bot.commands.base import BotCommand
from src.bot.commands.help import HelpCommand
from src.bot.commands.status import StatusCommand
from src.bot.commands.analyze import AnalyzeCommand
from src.bot.commands.market import MarketCommand
from src.bot.commands.batch import BatchCommand
from src.bot.commands.ask import AskCommand
from src.bot.commands.chat import ChatCommand
from src.bot.commands.research import ResearchCommand
from src.bot.commands.strategies import StrategiesCommand
from src.bot.commands.history import HistoryCommand

# All available commands (for auto-registration)
ALL_COMMANDS = [
    HelpCommand,
    StatusCommand,
    AnalyzeCommand,
    MarketCommand,
    BatchCommand,
    AskCommand,
    ChatCommand,
    ResearchCommand,
    StrategiesCommand,
    HistoryCommand,
]

__all__ = [
    'BotCommand',
    'HelpCommand',
    'StatusCommand',
    'AnalyzeCommand',
    'MarketCommand',
    'BatchCommand',
    'AskCommand',
    'ChatCommand',
    'ResearchCommand',
    'StrategiesCommand',
    'HistoryCommand',
    'ALL_COMMANDS',
]
