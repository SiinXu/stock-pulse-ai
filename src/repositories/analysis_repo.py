# -*- coding: utf-8 -*-
"""
===================================
分析历史数据访问层
===================================

职责：
1. 封装分析历史数据的数据库操作
2. 提供 CRUD 接口
"""

import logging
from typing import Optional, List, Dict, Any

from src.repositories.base import BaseRepository, RepositoryError
from src.storage import DatabaseManager, AnalysisHistory
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_DELETE_BY_CODE_BATCH_SIZE = 10_000


class AnalysisRepository(BaseRepository):
    """
    分析历史数据访问层
    
    封装 AnalysisHistory 表的数据库操作
    """
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        初始化数据访问层
        
        Args:
            db_manager: 数据库管理器（可选，默认使用单例）
        """
        super().__init__(db_manager)
    
    def get_by_query_id(self, query_id: str) -> Optional[AnalysisHistory]:
        """
        根据 query_id 获取分析记录
        
        Args:
            query_id: 查询 ID
            
        Returns:
            AnalysisHistory 对象，不存在返回 None

        Raises:
            RepositoryError: when the underlying query fails
        """
        try:
            records = self.db.get_analysis_history(query_id=query_id, limit=1)
            return records[0] if records else None
        except Exception as exc:
            context = {"query_id": query_id}
            log_safe_exception(
                logger,
                "Analysis record lookup failed",
                exc,
                error_code="analysis_record_lookup_failed",
                context=context,
            )
            raise RepositoryError(
                "Analysis record lookup failed",
                error_code="analysis_record_lookup_failed",
                context=context,
            ) from exc
    
    def get_list(
        self,
        code: Optional[str] = None,
        days: int = 30,
        limit: int = 50
    ) -> List[AnalysisHistory]:
        """
        获取分析记录列表
        
        Args:
            code: 股票代码筛选
            days: 时间范围（天）
            limit: 返回数量限制
            
        Returns:
            AnalysisHistory 对象列表

        Raises:
            RepositoryError: when the underlying query fails
        """
        try:
            return self.db.get_analysis_history(
                code=code,
                days=days,
                limit=limit
            )
        except Exception as exc:
            context = {"stock_code": code or "all"}
            log_safe_exception(
                logger,
                "Analysis record list failed",
                exc,
                error_code="analysis_record_list_failed",
                context=context,
            )
            raise RepositoryError(
                "Analysis record list failed",
                error_code="analysis_record_list_failed",
                context=context,
            ) from exc
    
    def save(
        self,
        result: Any,
        query_id: str,
        report_type: str,
        news_content: Optional[str] = None,
        context_snapshot: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        保存分析结果
        
        Args:
            result: 分析结果对象
            query_id: 查询 ID
            report_type: 报告类型
            news_content: 新闻内容
            context_snapshot: 上下文快照
            
        Returns:
            新保存的 AnalysisHistory.id

        Raises:
            RepositoryError: when persistence fails (does not return 0)
        """
        try:
            return self.db.save_analysis_history(
                result=result,
                query_id=query_id,
                report_type=report_type,
                news_content=news_content,
                context_snapshot=context_snapshot
            )
        except Exception as exc:
            context = {"query_id": query_id, "report_type": report_type}
            log_safe_exception(
                logger,
                "Analysis result persistence failed",
                exc,
                error_code="analysis_result_save_failed",
                context=context,
            )
            raise RepositoryError(
                "Analysis result persistence failed",
                error_code="analysis_result_save_failed",
                context=context,
            ) from exc
    
    def count_by_code(self, code: str, days: int = 30) -> int:
        """
        统计指定股票的分析记录数
        
        Args:
            code: 股票代码
            days: 时间范围（天）
            
        Returns:
            记录数量

        Raises:
            RepositoryError: when the underlying query fails
        """
        try:
            records = self.db.get_analysis_history(code=code, days=days, limit=1000)
            return len(records)
        except Exception as exc:
            context = {"stock_code": code}
            log_safe_exception(
                logger,
                "Analysis record count failed",
                exc,
                error_code="analysis_record_count_failed",
                context=context,
            )
            raise RepositoryError(
                "Analysis record count failed",
                error_code="analysis_record_count_failed",
                context=context,
            ) from exc

    def delete_by_stock_codes(self, stock_codes: List[str]) -> int:
        """Delete all history rows matching any canonical code variant.

        Each storage deletion is an atomic batch, while a large multi-batch
        deletion intentionally preserves the existing best-effort semantics.
        Re-reading the first page avoids offset drift as rows are removed.
        """
        codes = list(dict.fromkeys(str(code or "").strip() for code in stock_codes))
        codes = [code for code in codes if code]
        if not codes:
            return 0

        deleted = 0
        try:
            while True:
                records, _ = self.db.get_analysis_history_paginated(
                    code=codes,
                    limit=_DELETE_BY_CODE_BATCH_SIZE,
                )
                record_ids = [record.id for record in records if record.id is not None]
                if not record_ids:
                    break

                batch_deleted = self.db.delete_analysis_history_records(record_ids)
                if batch_deleted == 0:
                    raise RepositoryError(
                        "history deletion made no progress",
                        error_code="analysis_history_delete_no_progress",
                        context={"stock_codes": codes},
                    )
                deleted += batch_deleted

                if len(records) < _DELETE_BY_CODE_BATCH_SIZE:
                    break
        except RepositoryError:
            raise
        except Exception as exc:
            context = {"stock_codes": codes}
            log_safe_exception(
                logger,
                "Analysis history deletion failed",
                exc,
                error_code="analysis_history_delete_failed",
                context=context,
            )
            raise RepositoryError(
                "Analysis history deletion failed",
                error_code="analysis_history_delete_failed",
                context=context,
            ) from exc

        return deleted
