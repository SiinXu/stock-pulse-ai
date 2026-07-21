# -*- coding: utf-8 -*-
"""
===================================
A-shares Watchlist Analysis System - Analysis service layer
===================================

Responsibilities:
1. Encapsulate the core analysis logic, supporting multiple callers (CLI, WebUI, Bot).
2. Provides a clear API interface, not dependent on command-line parameters
3. Supports dependency injection for easier testing and expansion.
4. Manage and configure analysis workflows uniformly
"""

import uuid
from typing import List, Optional

from src.analyzer import AnalysisResult
from src.core.market_review import run_market_review
from src.core.pipeline import StockAnalysisPipeline
from src.config import Config, get_config
from src.enums import ReportType
from src.notification import NotificationService


def analyze_stock(
    stock_code: str,
    config: Config = None,
    full_report: bool = False,
    notifier: Optional[NotificationService] = None,
) -> Optional[AnalysisResult]:
    """
    Analyze a single stock

    Args:
        stock_code: stock code
        config: Configuration object (optional, defaults to singleton)
        full_report: Generate full report?
        notifier: Notification Service (optional)

    Returns:
        Analysis results object
    """
    if config is None:
        config = get_config()

    # Create an analysis pipeline
    pipeline = StockAnalysisPipeline(
        config=config,
        query_id=uuid.uuid4().hex,
        query_source="cli"
    )

    # Use notification service (if available)
    if notifier:
        pipeline.notifier = notifier

    # Set report type based on full_report parameter
    report_type = ReportType.FULL if full_report else ReportType.SIMPLE

    # Run single stock analysis
    result = pipeline.process_single_stock(
        code=stock_code,
        skip_analysis=False,
        single_stock_notify=notifier is not None,
        report_type=report_type,
    )

    return result


def analyze_stocks(
    stock_codes: List[str],
    config: Config = None,
    full_report: bool = False,
    notifier: Optional[NotificationService] = None,
) -> List[AnalysisResult]:
    """
    Analyze multiple stocks

    Args:
        stock_codes: List of stock codes
        config: Configuration object (optional, defaults to singleton)
        full_report: Generate full report?
        notifier: Notification Service (optional)

    Returns:
        List of analysis results.
    """
    if config is None:
        config = get_config()

    results = []
    for stock_code in stock_codes:
        result = analyze_stock(stock_code, config, full_report, notifier)
        if result:
            results.append(result)

    return results


def perform_market_review(
    config: Config = None,
    notifier: Optional[NotificationService] = None,
) -> Optional[str]:
    """
    Execute market review

    Args:
        config: Configuration object (optional, defaults to singleton)
        notifier: Notification Service (optional)

    Returns:
        Market review report content
    """
    if config is None:
        config = get_config()

    # Create an analysis pipeline to get analyzer and search_service
    pipeline = StockAnalysisPipeline(
        config=config,
        query_id=uuid.uuid4().hex,
        query_source="cli",
    )

    # Use the provided notification service or create a new one.
    review_notifier = notifier or pipeline.notifier

    # Call the market review function
    return run_market_review(
        notifier=review_notifier,
        analyzer=pipeline.analyzer,
        search_service=pipeline.search_service,
        config=config,
        trigger_source="service",
    )
