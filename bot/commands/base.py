# -*- coding: utf-8 -*-
"""
===================================
Command base class
===================================

Define the abstract base class of command processors. All commands must inherit from this class.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional

from bot.models import BotMessage, BotResponse


class BotCommand(ABC):
    """
    Command processor abstract base class

    All commands must inherit this class and implement the abstract method.

    Using example:
        class MyCommand(BotCommand):
            @property
            def name(self) -> str:
                return "mycommand"

            @property
            def aliases(self) -> List[str]:
                return ["mc", "my command"]

            @property
            def description(self) -> str:
                return "this is my command"

            @property
            def usage(self) -> str:
                return "/mycommand [Parameters]"

            def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
                return BotResponse.text_response("Command Execution Success")
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Command name (without prefix)

        For example: "analyze" , user input "/analyze" triggers
        """
        pass

    @property
    @abstractmethod
    def aliases(self) -> List[str]:
        """
        Command aliases list

        For example: ["a", "analysis"] , user input "/a" or "analysis" can also trigger
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Command description (for help information)"""
        pass

    @property
    @abstractmethod
    def usage(self) -> str:
        """
        Usage instructions (for help information)

        For example: "/analyze <stock code>"
        """
        pass

    @property
    def hidden(self) -> bool:
        """
        Is it hidden in the help list?

        Default is False, set to True to not display in /help list
        """
        return False

    @property
    def admin_only(self) -> bool:
        """
        Only available for administrators

        Default is False, set to True requires administrator permissions
        """
        return False

    @abstractmethod
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """
        Execute command

        Args:
            message: Original message object
            args: Command parameter list (split)

        Returns:
            BotResponse response object
        """
        pass

    async def execute_async(self, message: BotMessage, args: List[str]) -> BotResponse:
        """Execute command asynchronously.

        Default to threadpool execute() for syncing `execute()` to avoid blocking event loop in asynchronous distribution links.
        """
        return await asyncio.to_thread(self.execute, message, args)

    def validate_args(self, args: List[str]) -> Optional[str]:
        """
        Validate parameters

        Subclasses can override this method to perform parameter validation.

        Args:
            args: Command parameter list

        Returns:
            If parameters are valid, return None; otherwise, return an error message.
        """
        return None

    def get_help_text(self) -> str:
        """Get help text"""
        return f"**{self.name}** - {self.description}\n用法: `{self.usage}`"
