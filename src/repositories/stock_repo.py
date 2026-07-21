# -*- coding: utf-8 -*-
"""
===================================
Stock Data Access Layer
===================================

Responsibilities:
1. Encapsulate database operations for stock data.
2. Provides daily data query interface
"""

import logging
from datetime import date
from typing import Optional, List, Dict, Any

import pandas as pd
from sqlalchemy import and_, desc, select

from src.storage import DatabaseManager, StockDaily
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class StockRepository:
    """
    Stock Data Access Layer
    
    Encapsulate database operations for the StockDaily table.
    """
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize the data access layer
        
        Args:
            db_manager: database manager (optional, uses singleton by default)
        """
        self.db = db_manager or DatabaseManager.get_instance()
    
    def get_latest(self, code: str, days: int = 2) -> List[StockDaily]:
        """
        Get data for the last N days
        
        Args:
            code: stock code
            days: number of days to fetch
            
        Returns:
            StockDaily object list (sorted by date descending)
        """
        try:
            return self.db.get_latest_data(code, days)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Latest stock data lookup failed",
                exc,
                error_code="latest_stock_data_lookup_failed",
                context={"stock_code": code},
            )
            return []
    
    def get_range(
        self,
        code: str,
        start_date: date,
        end_date: date
    ) -> List[StockDaily]:
        """
        Get data within a specified date range
        
        Args:
            code: stock code
            start_date: start date
            end_date: End date
            
        Returns:
            StockDaily object list
        """
        try:
            return self.db.get_data_range(code, start_date, end_date)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Stock date range lookup failed",
                exc,
                error_code="stock_date_range_lookup_failed",
                context={"stock_code": code},
            )
            return []
    
    def save_dataframe(
        self,
        df: pd.DataFrame,
        code: str,
        data_source: str = "Unknown"
    ) -> int:
        """
        Save DataFrame to database
        
        Args:
            df: DataFrame containing intraday data
            code: stock code
            data_source: Data source
            
        Returns:
            Number of records saved
        """
        try:
            return self.db.save_daily_data(df, code, data_source)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Daily stock data persistence failed",
                exc,
                error_code="daily_stock_data_save_failed",
                context={"stock_code": code, "data_source": data_source},
            )
            return 0
    
    def has_today_data(self, code: str, target_date: Optional[date] = None) -> bool:
        """
        Check if data exists for a specified date.
        
        Args:
            code: stock code
            target_date: Target date (default to today)
            
        Returns:
            Does data exist?
        """
        try:
            return self.db.has_today_data(code, target_date)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Stock data existence check failed",
                exc,
                error_code="stock_data_existence_check_failed",
                context={"stock_code": code},
            )
            return False
    
    def get_analysis_context(
        self, 
        code: str, 
        target_date: Optional[date] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the analysis context
        
        Args:
            code: stock code
            target_date: Target date
            
        Returns:
            Analyze moving average indicator
        """
        try:
            return self.db.get_analysis_context(code, target_date)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Stock analysis context lookup failed",
                exc,
                error_code="stock_analysis_context_lookup_failed",
                context={"stock_code": code},
            )
            return None

    def get_start_daily(self, *, code: str, analysis_date: date) -> Optional[StockDaily]:
        """Return StockDaily for analysis_date (preferred) or nearest previous date."""
        with self.db.get_session() as session:
            row = session.execute(
                select(StockDaily)
                .where(and_(StockDaily.code == code, StockDaily.date <= analysis_date))
                .order_by(desc(StockDaily.date))
                .limit(1)
            ).scalar_one_or_none()
            return row

    def get_daily_on_date(self, *, code: str, target_date: date) -> Optional[StockDaily]:
        """Return StockDaily for the exact target_date without trading-day fallback."""
        with self.db.get_session() as session:
            row = session.execute(
                select(StockDaily)
                .where(and_(StockDaily.code == code, StockDaily.date == target_date))
                .limit(1)
            ).scalar_one_or_none()
            return row

    def get_forward_bars(self, *, code: str, analysis_date: date, eval_window_days: int) -> List[StockDaily]:
        """Return forward daily bars after analysis_date, up to eval_window_days."""
        with self.db.get_session() as session:
            rows = session.execute(
                select(StockDaily)
                .where(and_(StockDaily.code == code, StockDaily.date > analysis_date))
                .order_by(StockDaily.date)
                .limit(eval_window_days)
            ).scalars().all()
            return list(rows)
