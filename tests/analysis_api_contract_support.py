# -*- coding: utf-8 -*-
"""Shared imports, fixtures, and payloads for analysis API contract tests."""

import atexit
import asyncio
from concurrent.futures import Future
from datetime import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

_ORIGINAL_ENVIRON = dict(os.environ)
_MODULE_TEMP_DIR = tempfile.TemporaryDirectory()
_MODULE_ENV_FILE = Path(_MODULE_TEMP_DIR.name) / ".env"
_MODULE_ENV_FILE.write_text("STOCK_LIST=600519,000001\n", encoding="utf-8")
os.environ["ENV_FILE"] = str(_MODULE_ENV_FILE)

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

try:
    from api.app import create_app
    from api.v1.endpoints import analysis as analysis_endpoint_module
    from api.v1.endpoints.analysis import (
        trigger_analysis,
        trigger_market_review,
        _handle_sync_analysis,
        _build_analysis_report,
        _load_sync_fundamental_sources,
        get_analysis_status,
        get_task_list,
    )
except Exception:  # pragma: no cover - optional dependency environments
    create_app = None
    analysis_endpoint_module = None
    trigger_analysis = None
    trigger_market_review = None
    _handle_sync_analysis = None
    _build_analysis_report = None
    _load_sync_fundamental_sources = None
    get_analysis_status = None
    get_task_list = None

from src.enums import ReportType
from src.services.analysis_service import AnalysisService
from src.services.image_stock_extractor import _call_litellm_vision
from src.services.task_queue import AnalysisTaskQueue, TaskInfo as QueueTaskInfo, TaskStatus
from src.task_execution import deep_thaw

__all__ = (
    "ANY",
    "AnalysisService",
    "AnalysisTaskQueue",
    "Future",
    "MagicMock",
    "Path",
    "QueueTaskInfo",
    "ReportType",
    "SimpleNamespace",
    "TaskStatus",
    "_analysis_context_pack_overview",
    "_build_analysis_report",
    "_call_litellm_vision",
    "_handle_sync_analysis",
    "_load_sync_fundamental_sources",
    "_market_phase_summary",
    "_market_structure_context",
    "activate_test_environment",
    "analysis_endpoint_module",
    "asyncio",
    "create_app",
    "datetime",
    "deep_thaw",
    "get_analysis_status",
    "get_task_list",
    "json",
    "patch",
    "restore_test_environment",
    "tempfile",
    "trigger_analysis",
    "trigger_market_review",
    "unittest",
)


def activate_test_environment() -> None:
    os.environ["ENV_FILE"] = str(_MODULE_ENV_FILE)


def restore_test_environment() -> None:
    current_test = os.environ.get("PYTEST_CURRENT_TEST")
    for key in list(os.environ):
        if key == "PYTEST_CURRENT_TEST":
            continue
        if key not in _ORIGINAL_ENVIRON:
            os.environ.pop(key, None)
    os.environ.update(_ORIGINAL_ENVIRON)
    if current_test is not None:
        os.environ["PYTEST_CURRENT_TEST"] = current_test


atexit.register(_MODULE_TEMP_DIR.cleanup)


def _analysis_context_pack_overview() -> dict:
    return {
        "pack_version": "1.0",
        "created_at": "2026-04-10T08:30:00+00:00",
        "subject": {
            "code": "600519",
            "stock_name": "贵州茅台",
            "market": "cn",
        },
        "blocks": [
            {
                "key": "quote",
                "label": "行情",
                "status": "available",
                "source": "mock",
                "warnings": [],
                "missing_reasons": [],
            },
            {
                "key": "news",
                "label": "新闻",
                "status": "missing",
                "source": None,
                "warnings": [],
                "missing_reasons": ["news_context_missing"],
            },
        ],
        "counts": {
            "available": 1,
            "missing": 1,
            "not_supported": 0,
            "fallback": 0,
            "stale": 0,
            "estimated": 0,
            "partial": 0,
            "fetch_failed": 0,
        },
        "data_quality": {
            "overall_score": 88,
            "level": "good",
            "block_scores": {
                "quote": 100,
                "daily_bars": 100,
                "technical": 100,
                "news": 35,
                "fundamentals": 100,
                "chip": 100,
            },
            "limitations": [],
        },
        "warnings": ["news_context_missing"],
        "metadata": {
            "trigger_source": "api",
            "news_result_count": 0,
        },
    }


def _market_structure_context() -> dict:
    return {
        "schema_version": "market-structure-v1",
        "status": "partial",
        "market": "cn",
        "market_theme_context": {
            "schema_version": "market-theme-v1",
            "status": "partial",
            "market": "cn",
            "active_themes": [{"name": "机器人概念"}],
        },
        "stock_market_position": {
            "schema_version": "stock-market-position-v1",
            "status": "partial",
            "stock_code": "300024",
            "market": "cn",
            "primary_theme": {"name": "机器人概念"},
        },
    }


def _market_phase_summary() -> dict:
    return {
        "market": "cn",
        "phase": "intraday",
        "market_local_time": "2026-03-27T10:00:00+08:00",
        "session_date": "2026-03-27",
        "effective_daily_bar_date": "2026-03-26",
        "is_trading_day": True,
        "is_market_open_now": True,
        "is_partial_bar": True,
        "minutes_to_open": None,
        "minutes_to_close": 300,
        "trigger_source": "api",
        "analysis_intent": "auto",
        "warnings": ["partial_bar"],
    }
