# -*- coding: utf-8 -*-
"""
===================================
Service layer module initialization.
===================================

Responsibilities:
1. Declare exportable service classes (delayed import, avoid pulling in heavy dependencies such as LLM during startup)

Usage:
    Import directly from submodules, for example:
    from src.services.history_service import HistoryService
"""


def __getattr__(name: str):
    """Delayed import: Only load corresponding submodules when accessed through src.services.X"""
    _lazy_map = {
        "AnalysisService": "src.services.analysis_service",
        "BacktestService": "src.services.backtest_service",
        "HistoryService": "src.services.history_service",
        "StockService": "src.services.stock_service",
    }
    if name in _lazy_map:
        import importlib
        module = importlib.import_module(_lazy_map[name])
        return getattr(module, name)
    raise AttributeError(f"module 'src.services' has no attribute {name!r}")


__all__ = [
    "AnalysisService",
    "BacktestService",
    "HistoryService",
    "StockService",
]
