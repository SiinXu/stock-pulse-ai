# -*- coding: utf-8 -*-
"""
===================================
Stock Analysis Command
===================================

Analyze a specified stock and call AI to generate an analysis report.
"""

import logging
from typing import List, Optional

from bot.commands.base import BotCommand
from bot.application_context import to_analysis_request_context
from bot.models import BotMessage, BotResponse
from bot.stock_symbols import (
    BotStockSymbolError,
    parse_bot_stock_symbol,
    supported_stock_formats_message,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class AnalyzeCommand(BotCommand):
    """Submit one supported stock symbol for AI analysis.

    Examples:
        /analyze 600519       - Analyze an A-share with the simple report.
        /analyze HK00700      - Analyze a Hong Kong stock.
        /analyze AAPL full    - Analyze a US stock with the full report.
    """
    
    @property
    def name(self) -> str:
        return "analyze"
    
    @property
    def aliases(self) -> List[str]:
        return ["a", "分析", "查"]
    
    @property
    def description(self) -> str:
        return "分析 A 股、港股或美股"
    
    @property
    def usage(self) -> str:
        return "/analyze <600519|HK00700|AAPL> [full]"
    
    def validate_args(self, args: List[str]) -> Optional[str]:
        """Validate parameters"""
        if not args:
            return (
                "请输入股票代码 / Please provide a stock symbol.\n"
                f"{supported_stock_formats_message()}"
            )

        try:
            parse_bot_stock_symbol(args[0])
        except BotStockSymbolError as exc:
            return str(exc)
        
        return None
    
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """Execute analysis command"""
        if not args:
            return BotResponse.error_response(
                "请输入股票代码 / Please provide a stock symbol.\n"
                f"{supported_stock_formats_message()}"
            )

        try:
            symbol = parse_bot_stock_symbol(args[0])
        except BotStockSymbolError as exc:
            return BotResponse.error_response(str(exc))

        code = symbol.code
        
        # Check if a full report is required (defaults to brief, pass full/complete/detailed to switch)
        report_type = "simple"
        if len(args) > 1 and args[1].lower() in ["full", "完整", "详细"]:
            report_type = "full"
        logger.info(
            "[AnalyzeCommand] Analyzing stock: code=%s market=%s report_type=%s",
            code,
            symbol.market,
            report_type,
        )
        
        try:
            # Submit to the unified task execution authority: same queue, Task ID with API/Web
            # Deduplication keys, status enumeration and error classification, Bot no longer maintains parallel task lifecycles.
            from src.services.task_queue import get_task_queue, DuplicateTaskError
            from src.enums import ReportType

            task = get_task_queue().submit_task(
                stock_code=code,
                report_type=report_type,
                query_source="bot",
                request_context=to_analysis_request_context(message),
            )
        except DuplicateTaskError:
            # Unified authoritative deduplication by normalized stock code; old path without deduplication will trigger concurrent analysis.
            return BotResponse.markdown_response(
                f"⏳ **该股票正在分析中**\n\n"
                f"• 股票代码: `{code}`\n\n"
                f"• 市场 / Market: {symbol.market_display_name}\n\n"
                f"请等待当前分析完成后再试。"
            )
        except Exception as exc:
            # broad-exception: fallback_recorded - bot command boundary must not leak a traceback; the failure is safe-logged and mapped to a stable public reply.
            log_safe_exception(
                logger,
                "[AnalyzeCommand] Analysis execution failed",
                exc,
                error_code="bot_analyze_failed",
                context={
                    "stock_code": code,
                    "market": symbol.market,
                    "report_type": report_type,
                },
            )
            return BotResponse.error_response("分析失败，请稍后重试")

        task_id = task.task_id or ""
        return BotResponse.markdown_response(
            f"✅ **分析任务已提交**\n\n"
            f"• 股票代码: `{code}`\n"
            f"• 市场 / Market: {symbol.market_display_name}\n"
            f"• 报告类型: {ReportType.from_str(report_type).display_name}\n"
            f"• 任务 ID: `{task_id[:20]}...`\n\n"
            f"分析完成后将自动推送结果。"
        )
