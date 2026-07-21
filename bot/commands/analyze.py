# -*- coding: utf-8 -*-
"""
===================================
股票分析命令
===================================

分析指定股票，调用 AI 生成分析报告。
"""

import re
import logging
from typing import List, Optional

from bot.commands.base import BotCommand
from bot.application_context import to_analysis_request_context
from bot.models import BotMessage, BotResponse
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class AnalyzeCommand(BotCommand):
    """
    股票分析命令
    
    分析指定股票代码，生成 AI 分析报告并推送。
    
    用法：
        /analyze 600519       - 分析贵州茅台（精简报告）
        /analyze 600519 full  - 分析并生成完整报告
    """
    
    @property
    def name(self) -> str:
        return "analyze"
    
    @property
    def aliases(self) -> List[str]:
        return ["a", "分析", "查"]
    
    @property
    def description(self) -> str:
        return "分析指定股票"
    
    @property
    def usage(self) -> str:
        return "/analyze <股票代码> [full]"
    
    def validate_args(self, args: List[str]) -> Optional[str]:
        """验证参数"""
        if not args:
            return "请输入股票代码"
        
        code = args[0].upper()

        # 验证股票代码格式
        # A股：6位数字
        # 港股：HK+5位数字
        # 美股：1-5个大写字母+.+2个后缀字母
        is_a_stock = re.match(r'^\d{6}$', code)
        is_hk_stock = re.match(r'^HK\d{5}$', code)
        is_us_stock = re.match(r'^[A-Z]{1,5}(\.[A-Z]{1,2})?$', code)

        if not (is_a_stock or is_hk_stock or is_us_stock):
            return f"无效的股票代码: {code}（A股6位数字 / 港股HK+5位数字 / 美股1-5个字母）"
        
        return None
    
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """执行分析命令"""
        code = resolve_index_stock_code_for_analysis(args[0])
        
        # 检查是否需要完整报告（默认精简，传 full/完整/详细 切换）
        report_type = "simple"
        if len(args) > 1 and args[1].lower() in ["full", "完整", "详细"]:
            report_type = "full"
        logger.info(
            "[AnalyzeCommand] Analyzing stock: code=%s report_type=%s",
            code,
            report_type,
        )
        
        try:
            # 提交到统一任务执行权威：与 API/Web 共用同一 queue、Task ID、
            # 去重键、状态枚举与错误分类，Bot 不再维护平行的任务生命周期。
            from src.services.task_queue import get_task_queue, DuplicateTaskError
            from src.enums import ReportType

            task = get_task_queue().submit_task(
                stock_code=code,
                report_type=report_type,
                query_source="bot",
                request_context=to_analysis_request_context(message),
            )
        except DuplicateTaskError:
            # 统一权威按规范化股票代码去重；旧路径无去重，会重复触发并发分析。
            return BotResponse.markdown_response(
                f"⏳ **该股票正在分析中**\n\n"
                f"• 股票代码: `{code}`\n\n"
                f"请等待当前分析完成后再试。"
            )
        except Exception as exc:
            # broad-exception: fallback_recorded - bot command boundary must not leak a traceback; the failure is safe-logged and mapped to a stable public reply.
            log_safe_exception(
                logger,
                "[AnalyzeCommand] Analysis execution failed",
                exc,
                error_code="bot_analyze_failed",
                context={"stock_code": code, "report_type": report_type},
            )
            return BotResponse.error_response("分析失败，请稍后重试")

        task_id = task.task_id or ""
        return BotResponse.markdown_response(
            f"✅ **分析任务已提交**\n\n"
            f"• 股票代码: `{code}`\n"
            f"• 报告类型: {ReportType.from_str(report_type).display_name}\n"
            f"• 任务 ID: `{task_id[:20]}...`\n\n"
            f"分析完成后将自动推送结果。"
        )
