# -*- coding: utf-8 -*-
"""
===================================
Analysis service layer.
===================================

Responsibilities:
1. Encapsulate stock analysis logic.
2. Call analyzer and pipeline to execute analysis
3. Save the analysis result to the database
"""

import logging
import copy
import uuid
from typing import Optional, Dict, Any, Callable, List

from src.repositories.analysis_repo import AnalysisRepository
from src.report_language import (
    get_sentiment_label,
    get_localized_stock_name,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)
from src.market_phase_summary import extract_market_phase_summary
from src.schemas.decision_action import build_action_fields
from src.schemas.request_context import AnalysisRequestContext
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    build_run_diagnostic_summary,
    get_current_diagnostic_context,
    reset_run_diagnostic_context,
)
from src.utils.sanitize import (
    log_safe_exception,
    sanitize_diagnostic_text,
    sanitize_exception_chain,
)

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    Analysis service.
    
    Encapsulate business logic related to stock analysis.
    """
    
    def __init__(self):
        """Initialize analysis service"""
        self.repo = AnalysisRepository()
        self.last_error: Optional[str] = None
    
    def analyze_stock(
        self,
        stock_code: str,
        report_type: str = "detailed",
        force_refresh: bool = False,
        query_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        send_notification: bool = True,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        skills: Optional[List[str]] = None,
        analysis_phase: str = "auto",
        query_source: str = "api",
        portfolio_context: Optional[Dict[str, Any]] = None,
        report_language: Optional[str] = None,
        request_context: Optional[AnalysisRequestContext] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute stock analysis

        Args:
            stock_code: stock code
            report_type: Report type (simple/detailed)
            force_refresh: Force refresh?
            query_id: optional query ID
            send_notification: Whether to send notifications (API trigger defaults to sending)
            analysis_phase: Analysis stage coverage for the request(auto/premarket/intraday/postmarket)
            request_context: Optional requester provenance and contextual reply
                targets. Bot submissions carry it so the notifier can push the
                result back to the originating conversation.
            
        Returns:
            Analysis results dictionary, containing:
            - stock_code: stock code
            - stock_name: Stock name
            - report: analysis report
        """
        try:
            self.last_error = None
            # Import analysis related modules
            from src.config import get_config
            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType
            
            # Generate query_id
            if query_id is None:
                query_id = uuid.uuid4().hex
            effective_trace_id = trace_id or query_id
            diag_token = None
            if get_current_diagnostic_context() is None:
                diag_token = activate_run_diagnostic_context(
                    trace_id=effective_trace_id,
                    query_id=query_id,
                    stock_code=stock_code,
                    trigger_source=query_source or "api",
                )
            
            # Get configuration
            config = get_config()
            normalized_report_language = normalize_report_language(report_language, default="")
            if normalized_report_language:
                config = copy.copy(config)
                config.report_language = normalized_report_language
            
            # Create an analysis pipeline
            pipeline = StockAnalysisPipeline(
                config=config,
                request_context=request_context,
                query_id=query_id,
                trace_id=effective_trace_id,
                query_source=query_source or "api",
                progress_callback=progress_callback,
                analysis_skills=skills,
                analysis_phase=analysis_phase,
                portfolio_context=portfolio_context,
            )
            
            # Determine report type (API: simple/detailed/full/brief -> ReportType)
            rt = ReportType.from_str(report_type)
            
            # Execute analysis
            result = pipeline.process_single_stock(
                code=stock_code,
                skip_analysis=False,
                single_stock_notify=send_notification,
                report_type=rt,
            )
            
            if result is None:
                logger.warning(f"分析股票 {stock_code} 返回空结果")
                self.last_error = self.last_error or f"分析股票 {stock_code} 返回空结果"
                return None

            if not getattr(result, "success", True):
                self.last_error = sanitize_diagnostic_text(
                    getattr(result, "error_message", None),
                    max_length=300,
                ) or f"分析股票 {stock_code} 失败"
                logger.warning(f"分析股票 {stock_code} 未成功完成: {self.last_error}")
                return None
            
            # Build the response
            return self._build_analysis_response(result, query_id, report_type=rt.value)
            
        except Exception as exc:
            # broad-exception: fallback_recorded - analysis fail-safe contract; records a sanitized last_error and safe log, then returns None for any pipeline failure.
            self.last_error = sanitize_exception_chain(exc)
            log_safe_exception(
                logger,
                "Stock analysis failed",
                exc,
                error_code="stock_analysis_failed",
                context={"stock_code": stock_code},
            )
            return None
        finally:
            reset_run_diagnostic_context(locals().get("diag_token"))
    
    def _build_analysis_response(
        self, 
        result: Any, 
        query_id: str,
        report_type: str = "detailed",
    ) -> Dict[str, Any]:
        """
        Build the analysis response
        
        Args:
            result: AnalysisResult object
            query_id: query ID
            report_type: normalized report type
            
        Returns:
            Formatted response dictionary
        """
        # Get target price levels
        sniper_points = {}
        if hasattr(result, 'get_sniper_points'):
            sniper_points = result.get_sniper_points() or {}
        
        # Calculate Sentiment Labels
        report_language = normalize_report_language(getattr(result, "report_language", "zh"))
        sentiment_label = get_sentiment_label(result.sentiment_score, report_language)
        stock_name = get_localized_stock_name(getattr(result, "name", None), result.code, report_language)
        action_fields = build_action_fields(
            operation_advice=getattr(result, "operation_advice", None),
            explicit_action=getattr(result, "action", None),
            report_type=report_type,
            report_language=report_language,
            sentiment_score=getattr(result, "sentiment_score", None),
            guardrail_reason=getattr(result, "guardrail_reason", None),
            align_with_score=True,
        )
        diagnostic_context = get_current_diagnostic_context()
        trace_id = diagnostic_context.trace_id if diagnostic_context is not None else query_id
        diagnostic_snapshot = diagnostic_context.snapshot() if diagnostic_context is not None else None
        diagnostic_context_snapshot = getattr(result, "diagnostic_context_snapshot", None)
        market_phase_summary = extract_market_phase_summary(diagnostic_context_snapshot)
        if isinstance(diagnostic_context_snapshot, dict):
            context_snapshot = dict(diagnostic_context_snapshot)
            if diagnostic_snapshot is not None:
                context_snapshot["diagnostics"] = diagnostic_snapshot
        elif diagnostic_snapshot is not None:
            context_snapshot = {"diagnostics": diagnostic_snapshot}
        else:
            context_snapshot = None
        diagnostic_summary = build_run_diagnostic_summary(
            context_snapshot=context_snapshot,
            raw_result=result.to_dict() if hasattr(result, "to_dict") else None,
            report_saved=True,
            query_id=query_id,
            stock_code=result.code,
        )
        
        # Build report structure
        report = {
            "meta": {
                "query_id": query_id,
                "trace_id": trace_id,
                "stock_code": result.code,
                "stock_name": stock_name,
                "report_type": report_type,
                "report_language": report_language,
                "current_price": result.current_price,
                "change_pct": result.change_pct,
                "model_used": getattr(result, "model_used", None),
                "market_phase_summary": market_phase_summary,
            },
            "summary": {
                "analysis_summary": result.analysis_summary,
                "operation_advice": localize_operation_advice(result.operation_advice, report_language),
                "action": action_fields["action"],
                "action_label": action_fields["action_label"],
                "trend_prediction": localize_trend_prediction(result.trend_prediction, report_language),
                "sentiment_score": result.sentiment_score,
                "sentiment_label": sentiment_label,
            },
            "strategy": {
                "ideal_buy": sniper_points.get("ideal_buy"),
                "secondary_buy": sniper_points.get("secondary_buy"),
                "stop_loss": sniper_points.get("stop_loss"),
                "take_profit": sniper_points.get("take_profit"),
            },
            "details": {
                "news_summary": result.news_summary,
                "technical_analysis": result.technical_analysis,
                "fundamental_analysis": result.fundamental_analysis,
                "risk_warning": result.risk_warning,
            }
        }
        if hasattr(result, "to_dict"):
            raw_result_payload = result.to_dict()
            if isinstance(raw_result_payload, dict):
                report["details"]["raw_result"] = raw_result_payload

        return {
            "query_id": query_id,
            "trace_id": trace_id,
            "stock_code": result.code,
            "stock_name": stock_name,
            "report": report,
            "diagnostic_summary": diagnostic_summary,
        }
