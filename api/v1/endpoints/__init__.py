# -*- coding: utf-8 -*-
"""
===================================
API v1 Endpoints Module initialization
===================================

Responsibilities:
1. Declare all endpoint routing modules
"""

from api.v1.endpoints import (
    health,
    analysis,
    history,
    stocks,
    backtest,
    system_config,
    auth,
    agent,
    usage,
    portfolio,
    alerts,
    decision_signals,
    alphasift,
)
__all__ = [
    "health",
    "analysis",
    "history",
    "stocks",
    "backtest",
    "system_config",
    "auth",
    "agent",
    "usage",
    "portfolio",
    "alerts",
    "decision_signals",
    "alphasift",
]
