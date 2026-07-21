# -*- coding: utf-8 -*-
"""
===================================
Stock Data Service Layer
===================================

Responsibilities:
1. Encapsulate stock data retrieval logic
2. Provides real-time quote and historical data interface
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from src.repositories.stock_repo import StockRepository
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class StockService:
    """
    Stock Data Service
    
    Encapsulate business logic for fetching stock data.
    """
    
    def __init__(self):
        """Initialize stock data service"""
        self.repo = StockRepository()
    
    def get_realtime_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time stock quotes
        
        Args:
            stock_code: stock code
            
        Returns:
            Real-time data dictionary
        """
        try:
            # Call the data retriever to get real-time quotes
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            quote = manager.get_realtime_quote(stock_code)
            
            if quote is None:
                logger.warning(f"获取 {stock_code} 实时行情失败")
                return None
            
            # UnifiedRealtimeQuote is a dataclass, uses getattr for safe field access
            # Field mapping: UnifiedRealtimeQuote -> API response
            # - code -> stock_code
            # - name -> stock_name
            # - price -> current_price
            # - change_amount -> change
            # - change_pct -> change_percent
            # - open_price -> open
            # - high -> high
            # - low -> low
            # - pre_close -> prev_close
            # - volume -> volume
            # - amount -> amount
            return {
                "stock_code": getattr(quote, "code", stock_code),
                "stock_name": getattr(quote, "name", None),
                "current_price": getattr(quote, "price", 0.0) or 0.0,
                "change": getattr(quote, "change_amount", None),
                "change_percent": getattr(quote, "change_pct", None),
                "open": getattr(quote, "open_price", None),
                "high": getattr(quote, "high", None),
                "low": getattr(quote, "low", None),
                "prev_close": getattr(quote, "pre_close", None),
                "volume": getattr(quote, "volume", None),
                "amount": getattr(quote, "amount", None),
                "update_time": datetime.now().isoformat(),
            }
            
        except ImportError:
            logger.warning("DataFetcherManager 未找到，使用占位数据")
            return self._get_placeholder_quote(stock_code)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Realtime quote lookup failed",
                exc,
                error_code="realtime_quote_lookup_failed",
                context={"stock_code": stock_code},
            )
            return None
    
    def get_history_data(
        self,
        stock_code: str,
        period: str = "daily",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get historical stock quotes
        
        Args:
            stock_code: stock code
            period: K Line cycle (daily/weekly/monthly)
            days: number of days to fetch
            
        Returns:
            Historical market data dictionary
            
        Raises:
            ValueError: Raised when period is not daily (weekly/monthly not yet implemented)
        """
        # Validate period parameter, only supports daily
        if period != "daily":
            raise ValueError(
                f"暂不支持 '{period}' 周期，目前仅支持 'daily'。"
                "weekly/monthly 聚合功能将在后续版本实现。"
            )
        
        try:
            # Call the data retriever to get historical data
            from data_provider.base import DataFetcherManager
            
            manager = DataFetcherManager()
            df, source = manager.get_daily_data(stock_code, days=days)
            
            if df is None or df.empty:
                logger.warning(f"获取 {stock_code} 历史数据失败")
                return {"stock_code": stock_code, "period": period, "data": []}
            
            # Get stock name
            stock_name = manager.get_stock_name(stock_code)
            
            # Convert to Response Format
            data = []
            for _, row in df.iterrows():
                date_val = row.get("date")
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)
                
                data.append({
                    "date": date_str,
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)) if row.get("volume") else None,
                    "amount": float(row.get("amount", 0)) if row.get("amount") else None,
                    "change_percent": float(row.get("pct_chg", 0)) if row.get("pct_chg") else None,
                })
            
            return {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "period": period,
                "data": data,
            }
            
        except ImportError:
            logger.warning("DataFetcherManager 未找到，返回空数据")
            return {"stock_code": stock_code, "period": period, "data": []}
        except Exception as exc:
            log_safe_exception(
                logger,
                "Historical stock data lookup failed",
                exc,
                error_code="historical_stock_data_lookup_failed",
                context={"stock_code": stock_code, "period": period},
            )
            return {"stock_code": stock_code, "period": period, "data": []}
    
    def _get_placeholder_quote(self, stock_code: str) -> Dict[str, Any]:
        """
        Get placeholder market data (for testing)
        
        Args:
            stock_code: stock code
            
        Returns:
            Placeholder market data
        """
        return {
            "stock_code": stock_code,
            "stock_name": f"股票{stock_code}",
            "current_price": 0.0,
            "change": None,
            "change_percent": None,
            "open": None,
            "high": None,
            "low": None,
            "prev_close": None,
            "volume": None,
            "amount": None,
            "update_time": datetime.now().isoformat(),
        }
