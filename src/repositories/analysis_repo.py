# -*- coding: utf-8 -*-
"""
===================================
Analyze historical data access layer
===================================

Responsibilities:
1. Encapsulate database operations for analyzing historical data.
2. Provide CRUD interfaces
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from src.storage import DatabaseManager, AnalysisHistory
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_DELETE_BY_CODE_BATCH_SIZE = 10_000


class AnalysisRepository:
    """
    Analyze historical data access layer
    
    Encapsulate database operations for AnalysisHistory table
    """
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize the data access layer
        
        Args:
            db_manager: database manager (optional, uses singleton by default)
        """
        self.db = db_manager or DatabaseManager.get_instance()
    
    def get_by_query_id(self, query_id: str) -> Optional[AnalysisHistory]:
        """
        Retrieve the analysis record based on query_id
        
        Args:
            query_id: query ID
            
        Returns:
            AnalysisHistory object, Return if Not Exists None
        """
        try:
            records = self.db.get_analysis_history(query_id=query_id, limit=1)
            return records[0] if records else None
        except Exception as exc:
            log_safe_exception(
                logger,
                "Analysis record lookup failed",
                exc,
                error_code="analysis_record_lookup_failed",
                context={"query_id": query_id},
            )
            return None
    
    def get_list(
        self,
        code: Optional[str] = None,
        days: int = 30,
        limit: int = 50
    ) -> List[AnalysisHistory]:
        """
        Get the list of analysis records
        
        Args:
            code: stock code filtering
            days: time range (days)
            limit: return limit
            
        Returns:
            AnalysisHistory object list
        """
        try:
            return self.db.get_analysis_history(
                code=code,
                days=days,
                limit=limit
            )
        except Exception as exc:
            log_safe_exception(
                logger,
                "Analysis record list failed",
                exc,
                error_code="analysis_record_list_failed",
                context={"stock_code": code or "all"},
            )
            return []
    
    def save(
        self,
        result: Any,
        query_id: str,
        report_type: str,
        news_content: Optional[str] = None,
        context_snapshot: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Save the analysis result
        
        Args:
            result: analysis result object
            query_id: query ID
            report_type: report type
            news_content: News Content
            context_snapshot: Context Snapshot
            
        Returns:
            ID of the saved AnalysisHistory row, or 0 on failure
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
            log_safe_exception(
                logger,
                "Analysis result persistence failed",
                exc,
                error_code="analysis_result_save_failed",
                context={"query_id": query_id, "report_type": report_type},
            )
            return 0
    
    def count_by_code(self, code: str, days: int = 30) -> int:
        """
        Count the analysis records for a specified stock.
        
        Args:
            code: stock code
            days: time range (days)
            
        Returns:
            Record the quantity
        """
        try:
            records = self.db.get_analysis_history(code=code, days=days, limit=1000)
            return len(records)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Analysis record count failed",
                exc,
                error_code="analysis_record_count_failed",
                context={"stock_code": code},
            )
            return 0

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
                raise RuntimeError("history deletion made no progress")
            deleted += batch_deleted

            if len(records) < _DELETE_BY_CODE_BATCH_SIZE:
                break

        return deleted
