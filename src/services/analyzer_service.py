# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 分析服务层
===================================

职责：
1. 封装核心分析逻辑，支持多调用方（CLI、WebUI、Bot）
2. 提供清晰的API接口，不依赖于命令行参数
3. 支持依赖注入，便于测试和扩展
4. 统一管理分析流程和配置
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
    分析单只股票

    Args:
        stock_code: 股票代码
        config: 配置对象（可选，默认使用单例）
        full_report: 是否生成完整报告
        notifier: 通知服务（可选）

    Returns:
        分析结果对象
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
    分析多只股票

    Args:
        stock_codes: 股票代码列表
        config: 配置对象（可选，默认使用单例）
        full_report: 是否生成完整报告
        notifier: 通知服务（可选）

    Returns:
        分析结果列表
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
    执行大盘复盘

    Args:
        config: 配置对象（可选，默认使用单例）
        notifier: 通知服务（可选）

    Returns:
        复盘报告内容
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
