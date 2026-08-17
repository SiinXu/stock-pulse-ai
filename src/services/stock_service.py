# -*- coding: utf-8 -*-
"""
===================================
股票数据服务层
===================================

职责：
1. 封装股票数据获取逻辑
2. 提供实时行情和历史数据接口
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from src.repositories.stock_repo import StockRepository
from src.utils.sanitize import log_safe_exception
from data_provider.daily_cache import LocalDataMissingError

logger = logging.getLogger(__name__)


class StockService:
    """
    股票数据服务
    
    封装股票数据获取的业务逻辑
    """
    
    def __init__(self, data_fetcher_manager: Any | None = None):
        """初始化股票数据服务"""
        self.repo = StockRepository()
        self._data_fetcher_manager = data_fetcher_manager

    def _resolve_data_fetcher_manager(self):
        """Use the installed composition owner, with standalone fallback."""

        if self._data_fetcher_manager is not None:
            return self._data_fetcher_manager
        from src.application_services import get_installed_application_services

        services = get_installed_application_services()
        if services is not None and services.data_fetcher_manager is not None:
            return services.data_fetcher_manager
        from data_provider.base import DataFetcherManager

        return DataFetcherManager()
    
    def get_realtime_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票实时行情
        
        Args:
            stock_code: 股票代码
            
        Returns:
            实时行情数据字典
        """
        try:
            # Call the data retriever to get real-time quotes
            manager = self._resolve_data_fetcher_manager()
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
        except Exception as exc:  # broad-exception: fallback_recorded - quote failures are sanitized before the API returns its established unavailable result.
            log_safe_exception(
                logger,
                "Realtime quote lookup failed",
                exc,
                error_code="realtime_quote_lookup_failed",
                context={"stock_code": stock_code},
            )
            return None

    def get_field_trust(self, stock_code: str) -> Dict[str, Any]:
        """Build the field-level trust view for a stock quote (Issue #1129).

        Returns a structured dict matching ``StockFieldTrustResponse``.
        Missing trust metadata is reported explicitly (``metadata_present``
        False, status ``degraded``) so consumers can degrade visibly instead
        of rendering the quote as trusted. Conflicts stay visible; this
        method never picks one source as truth.
        """
        import math

        from src.data_provider.field_trust import (
            CONFIDENCE_LOW,
            TRUST_FIELDS,
            project_analysis_input,
        )

        base: Dict[str, Any] = {
            "schema_version": "field_trust_view/1.0",
            "stock_code": stock_code,
            "status": "unavailable",
            "metadata_present": False,
            "quote_source": None,
            "fetched_at": None,
            "provider_timestamp": None,
            "stale_seconds": None,
            "is_stale": None,
            "fallback_from": None,
            "data_quality": None,
            "missing_fields": [],
            "fields": [],
            "conflicts": [],
            "conflict_checks": [],
            "provider_health": [],
            "analysis_input": {
                "schema_version": "field_trust_analysis_input/1.0",
                "confidence": CONFIDENCE_LOW,
                "gaps": [
                    {
                        "code": "quote_unavailable",
                        "field": None,
                        "detail": "No realtime quote available from any provider",
                    }
                ],
                "conflict_count": 0,
                "failed_provider_count": 0,
            },
            "message": None,
        }

        try:
            manager = self._resolve_data_fetcher_manager()
            quote = manager.get_realtime_quote(stock_code)
        except Exception as exc:  # broad-exception: fallback_recorded - trust view reports unavailability instead of failing
            log_safe_exception(
                logger,
                "Field trust quote lookup failed",
                exc,
                error_code="field_trust_lookup_failed",
                context={"stock_code": stock_code},
            )
            quote = None

        if quote is None:
            base["message"] = "No realtime quote available from any provider"
            return base

        def _clean_number(value: Any) -> Any:
            if isinstance(value, bool) or value is None:
                return None
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None
            return number if math.isfinite(number) else None

        base["stock_code"] = getattr(quote, "code", None) or stock_code
        source = getattr(quote, "source", None)
        base["quote_source"] = getattr(source, "value", source)
        for key in (
            "fetched_at",
            "provider_timestamp",
            "stale_seconds",
            "is_stale",
            "fallback_from",
            "data_quality",
        ):
            base[key] = getattr(quote, key, None)
        base["missing_fields"] = list(getattr(quote, "missing_fields", None) or [])

        trust = getattr(quote, "field_trust", None)
        if not isinstance(trust, dict) or not isinstance(trust.get("fields"), dict):
            # Absent metadata must never read as trusted.
            base["status"] = "degraded"
            base["message"] = (
                "Quote carried no field-level trust metadata; treat all fields as unverified"
            )
            base["analysis_input"] = project_analysis_input(quote)
            return base

        base["metadata_present"] = True
        entries = []
        degraded = False
        for field_name in TRUST_FIELDS:
            raw = trust["fields"].get(field_name)
            value = _clean_number(getattr(quote, field_name, None))
            if raw is None and value is None:
                continue
            raw = raw or {}
            staleness = raw.get("staleness")
            if staleness not in ("fresh", "stale", "unknown"):
                staleness = "unknown"
            origin = raw.get("origin")
            if origin not in ("primary", "supplement"):
                origin = "unknown"
            entry = {
                "field": field_name,
                "value": value,
                "source": raw.get("source") or None,
                "origin": origin,
                "provider_timestamp": raw.get("provider_timestamp"),
                "stale_seconds": raw.get("stale_seconds"),
                "is_stale": raw.get("is_stale"),
                "staleness": staleness,
                "conflict": bool(raw.get("conflict")),
            }
            if staleness != "fresh" or entry["conflict"] or entry["source"] is None:
                degraded = True
            entries.append(entry)
        base["fields"] = entries

        conflicts = []
        for raw_conflict in trust.get("conflicts") or []:
            if not isinstance(raw_conflict, dict) or not raw_conflict.get("field"):
                continue
            values = []
            for item in raw_conflict.get("values") or []:
                if not isinstance(item, dict):
                    continue
                provider = item.get("provider")
                value = _clean_number(item.get("value"))
                if provider and value is not None:
                    values.append({"provider": str(provider), "value": value})
            conflicts.append(
                {
                    "field": str(raw_conflict["field"]),
                    "severity": str(raw_conflict.get("severity") or "warn"),
                    "relative_difference": _clean_number(
                        raw_conflict.get("relative_difference")
                    ),
                    "threshold": _clean_number(raw_conflict.get("threshold")),
                    "values": values,
                }
            )
        base["conflicts"] = conflicts
        if conflicts:
            degraded = True

        checks = []
        for raw_check in trust.get("conflict_checks") or []:
            if not isinstance(raw_check, dict):
                continue
            status = raw_check.get("status")
            checks.append(
                {
                    "primary_provider": raw_check.get("primary_provider"),
                    "secondary_provider": raw_check.get("secondary_provider"),
                    "status": status if status in ("evaluated", "skipped") else "skipped",
                    "reason": raw_check.get("reason"),
                }
            )
        base["conflict_checks"] = checks

        health_rows = []
        for raw_health in trust.get("provider_health") or []:
            if not isinstance(raw_health, dict) or not raw_health.get("provider"):
                continue
            status = raw_health.get("status")
            role = raw_health.get("role")
            health_rows.append(
                {
                    "provider": str(raw_health["provider"]),
                    "status": status
                    if status in ("ok", "failed", "empty", "unavailable")
                    else "unavailable",
                    "role": role
                    if role in ("primary", "supplement", "attempted")
                    else "attempted",
                    "circuit_state": raw_health.get("circuit_state"),
                    "available": raw_health.get("available"),
                    "health_score": _clean_number(raw_health.get("health_score")),
                }
            )
        base["provider_health"] = health_rows

        analysis = trust.get("analysis_input")
        if not isinstance(analysis, dict):
            analysis = project_analysis_input(quote)
        base["analysis_input"] = analysis
        if str(analysis.get("confidence") or "") != "high" or analysis.get("gaps"):
            degraded = True

        if not entries:
            degraded = True
            base["message"] = "No covered quote fields were attributable"
        base["status"] = "degraded" if degraded else "ok"
        return base
    
    def get_history_data(
        self,
        stock_code: str,
        period: str = "daily",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取股票历史行情
        
        Args:
            stock_code: 股票代码
            period: K 线周期 (daily/weekly/monthly)
            days: 获取天数
            
        Returns:
            历史行情数据字典
            
        Raises:
            ValueError: 当 period 不是 daily 时抛出（weekly/monthly 暂未实现）
        """
        # Validate period parameter, only supports daily
        if period != "daily":
            raise ValueError(
                f"暂不支持 '{period}' 周期，目前仅支持 'daily'。"
                "weekly/monthly 聚合功能将在后续版本实现。"
            )
        
        try:
            # Call the data retriever to get historical data
            manager = self._resolve_data_fetcher_manager()
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
            
        except LocalDataMissingError:
            raise
        except ImportError:
            logger.warning("DataFetcherManager 未找到，返回空数据")
            return {"stock_code": stock_code, "period": period, "data": []}
        except Exception as exc:  # broad-exception: fallback_recorded - history failures are sanitized before the API returns its established empty-data result.
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
        获取占位行情数据（用于测试）
        
        Args:
            stock_code: 股票代码
            
        Returns:
            占位行情数据
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
