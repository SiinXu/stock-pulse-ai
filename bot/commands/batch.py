# -*- coding: utf-8 -*-
"""
===================================
Bulk analysis command
===================================

Bulk analysis of all stocks in the watchlist.
"""

import logging
import threading
import uuid
from typing import List

from bot.commands.base import BotCommand
from bot.application_context import to_analysis_request_context
from bot.models import BotMessage, BotResponse
from src.schemas.request_context import AnalysisRequestContext
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class BatchCommand(BotCommand):
    """
    Bulk analysis command
    
    Bulk analysis of the watchlist stocks configured in the list, generating a summary report.
    
    Usage:
        /batch      - analyze all watchlist stocks
        /batch 3    - Only analyze before 3 Only
    """
    
    @property
    def name(self) -> str:
        return "batch"
    
    @property
    def aliases(self) -> List[str]:
        return ["b", "批量", "全部"]
    
    @property
    def description(self) -> str:
        return "批量分析自选股"
    
    @property
    def usage(self) -> str:
        return "/batch [数量]"
    
    @property
    def admin_only(self) -> bool:
        """Bulk analysis requires administrator permissions (to prevent abuse)"""
        return False  # Can be set to True as needed.
    
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """Execute batch analysis command"""
        from src.config import get_config
        
        config = get_config()
        config.refresh_stock_list()
        
        stock_list = config.stock_list
        
        if not stock_list:
            return BotResponse.error_response(
                "自选股列表为空，请先配置 STOCK_LIST"
            )
        
        # Parse quantity parameters
        limit = None
        if args:
            try:
                limit = int(args[0])
                if limit <= 0:
                    return BotResponse.error_response("数量必须大于0")
            except ValueError:
                return BotResponse.error_response(f"无效的数量: {args[0]}")
        
        # Limit analysis quantity
        if limit:
            stock_list = stock_list[:limit]
        
        logger.info(
            "[BatchCommand] Starting batch analysis: stock_count=%d",
            len(stock_list),
        )
        
        # Execute analysis in a background thread.
        thread = threading.Thread(
            target=self._run_batch_analysis,
            args=(stock_list, to_analysis_request_context(message)),
            daemon=True
        )
        thread.start()
        
        return BotResponse.markdown_response(
            f"✅ **批量分析任务已启动**\n\n"
            f"• 分析数量: {len(stock_list)} 只\n"
            f"• 股票列表: {', '.join(stock_list[:5])}"
            f"{'...' if len(stock_list) > 5 else ''}\n\n"
            f"分析完成后将自动推送汇总报告。"
        )
    
    def _run_batch_analysis(
        self,
        stock_list: List[str],
        request_context: AnalysisRequestContext,
    ) -> None:
        """Perform batch analysis in the background."""
        try:
            from src.config import get_config
            from main import StockAnalysisPipeline
            
            config = get_config()
            
            # Create an analysis pipeline
            pipeline = StockAnalysisPipeline(
                config=config,
                request_context=request_context,
                query_id=uuid.uuid4().hex,
                query_source="bot"
            )
            
            # Execute analysis (automatically push summary report)
            results = pipeline.run(
                stock_codes=stock_list,
                dry_run=False,
                send_notification=True
            )
            
            logger.info(
                "[BatchCommand] Batch analysis completed: success_count=%d",
                len(results),
            )
            
        except Exception as exc:
            log_safe_exception(
                logger,
                "[BatchCommand] Batch analysis failed",
                exc,
                error_code="bot_batch_analysis_failed",
                context={"stock_count": len(stock_list)},
            )
