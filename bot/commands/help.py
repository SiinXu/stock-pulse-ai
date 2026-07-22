# -*- coding: utf-8 -*-
"""
===================================
Help command
===================================

Displays the list of available commands and usage instructions.
"""

from typing import List

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse


class HelpCommand(BotCommand):
    """
    Help command
    
    Displays the list of all available commands and usage instructions.
    You can also view detailed help for specific commands.
    
    Usage:
        /help         - Show all commands?
        /help analyze - Show? analyze Detailed Command Help
    """
    
    @property
    def name(self) -> str:
        return "help"
    
    @property
    def aliases(self) -> List[str]:
        return ["h", "帮助", "?"]
    
    @property
    def description(self) -> str:
        return "显示帮助信息"
    
    @property
    def usage(self) -> str:
        return "/help [命令名]"
    
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """Execute help command"""
        # Delayed import to avoid circular dependency
        from bot.dispatcher import get_dispatcher
        
        dispatcher = get_dispatcher()
        
        # If a command name is specified, display detailed help for that command.
        if args:
            cmd_name = args[0]
            command = dispatcher.get_command(cmd_name)
            
            if command is None:
                return BotResponse.error_response(f"未知命令: {cmd_name}")
            
            # Build detailed help
            help_text = self._format_command_help(command, dispatcher.command_prefix)
            return BotResponse.markdown_response(help_text)
        
        # Displays the list of all commands
        commands = dispatcher.list_commands(include_hidden=False)
        prefix = dispatcher.command_prefix
        
        help_text = self._format_help_list(commands, prefix)
        return BotResponse.markdown_response(help_text)
    
    def _format_help_list(self, commands: List[BotCommand], prefix: str) -> str:
        """Format a list of commands"""
        lines = [
            "📚 **股票分析助手 - 命令帮助**",
            "",
            "可用命令：",
            "",
        ]
        
        for cmd in commands:
            # Command name and alias
            aliases_str = ""
            if cmd.aliases:
                # Filter out Chinese aliases, only display English aliases
                en_aliases = [a for a in cmd.aliases if a.isascii()]
                if en_aliases:
                    aliases_str = f" ({', '.join(prefix + a for a in en_aliases[:2])})"
            
            lines.append(f"• {prefix}{cmd.name}{aliases_str} - {cmd.description}")
            lines.append("")

        lines.extend([
            "",
            "---",
            f"💡 输入 {prefix}help <命令名> 查看详细用法",
            "",
            "**示例：**",
            "",
            f"• {prefix}analyze 600519 - A 股 / A-share",
            "",
            f"• {prefix}analyze HK00700 - 港股 / Hong Kong",
            "",
            f"• {prefix}analyze AAPL - 美股 / US",
            "",
            f"• {prefix}market - 查看大盘复盘",
            "",
            f"• {prefix}batch - 批量分析自选股",
        ])
        
        return "\n".join(lines)
    
    def _format_command_help(self, command: BotCommand, prefix: str) -> str:
        """Format a single command's detailed help"""
        lines = [
            f"📖 **{prefix}{command.name}** - {command.description}",
            "",
            f"**用法：** `{command.usage}`",
            "",
        ]
        
        # Alias.
        if command.aliases:
            aliases = [f"`{prefix}{a}`" if a.isascii() else f"`{a}`" for a in command.aliases]
            lines.append(f"**别名：** {', '.join(aliases)}")
            lines.append("")
        
        # Permissions
        if command.admin_only:
            lines.append("⚠️ **需要管理员权限**")
            lines.append("")
        
        return "\n".join(lines)
