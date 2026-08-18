# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline, network-free key-path workloads for performance baselines.

These workloads intentionally use realistic sizes (multi-year daily bars,
multi-stock report batches) so baselines reflect production-ish work rather
than micro-slices chosen for flattering numbers.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from src.perf.collector import (
    activate_collector,
    perf_span,
    reset_collector,
    set_collection_enabled_override,
)

OHLCV_ROWS = 750
REPORT_BATCH_SIZE = 12
TREND_ITERATIONS = 8
INDICATOR_ITERATIONS = 12
REPORT_ITERATIONS = 6


def _synthetic_ohlcv(rows: int = OHLCV_ROWS, seed: int = 227) -> pd.DataFrame:
    """Build deterministic synthetic OHLCV bars."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=rows)
    steps = rng.normal(loc=0.0004, scale=0.015, size=rows)
    close = 100.0 * np.cumprod(1.0 + steps)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.01, size=rows))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.01, size=rows))
    volume = rng.integers(200_000, 5_000_000, size=rows)
    return pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _run_timed(
    name: str,
    category: str,
    fn: Callable[[], Any],
    *,
    iterations: int,
    notes: str,
) -> Dict[str, Any]:
    fn()
    started = time.perf_counter()
    with perf_span(name, category=category):
        for _ in range(iterations):
            fn()
    duration_ms = (time.perf_counter() - started) * 1000.0
    ops_per_sec = (iterations / (duration_ms / 1000.0)) if duration_ms > 0 else 0.0
    return {
        "name": name,
        "category": category,
        "iterations": iterations,
        "duration_ms": round(duration_ms, 3),
        "ops_per_sec": round(ops_per_sec, 3),
        "notes": notes,
    }


def workload_data_fetch_indicators() -> Dict[str, Any]:
    """Data-path: indicator calculation on multi-year synthetic OHLCV."""
    from src.data_provider.base import BaseFetcher

    class _IndicatorHost(BaseFetcher):
        def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
            raise NotImplementedError("offline workload does not fetch network data")

        def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
            return df

    host = _IndicatorHost()
    frame = _synthetic_ohlcv()

    def _once() -> pd.DataFrame:
        return host._calculate_indicators(frame)

    return _run_timed(
        "data_fetch_indicators",
        "data_fetch",
        _once,
        iterations=INDICATOR_ITERATIONS,
        notes=f"BaseFetcher._calculate_indicators on {OHLCV_ROWS} synthetic daily bars",
    )


def workload_analysis_trend() -> Dict[str, Any]:
    """Analysis-path: StockTrendAnalyzer on multi-year synthetic bars."""
    from src.stock_analyzer import StockTrendAnalyzer

    analyzer = StockTrendAnalyzer()
    frame = _synthetic_ohlcv(seed=2271)

    def _once() -> Any:
        return analyzer.analyze(frame, "600519")

    return _run_timed(
        "analysis_trend",
        "analysis_run",
        _once,
        iterations=TREND_ITERATIONS,
        notes=f"StockTrendAnalyzer.analyze on {OHLCV_ROWS} synthetic daily bars",
    )


def _make_analysis_result(index: int) -> Any:
    from src.analyzer import AnalysisResult

    code = f"60051{index % 10}"
    return AnalysisResult(
        code=code,
        name=f"Synthetic-{index}",
        sentiment_score=55 + (index % 30),
        trend_prediction="看多" if index % 2 == 0 else "震荡",
        operation_advice="持有",
        decision_type="hold",
        confidence_level="中",
        report_language="zh",
        analysis_summary=f"Offline perf baseline summary for {code}.",
        technical_analysis="MA alignment mixed; volume stable.",
        risk_warning="Not investment advice. Synthetic offline fixture.",
        current_price=100.0 + index,
        change_pct=0.5 * ((index % 5) - 2),
        dashboard={
            "core_conclusion": {"one_sentence": f"Synthetic conclusion {index}"},
            "battle_plan": {
                "entry_zone": "98-102",
                "stop_loss": "95",
                "take_profit": "110",
            },
            "intelligence": {
                "earnings_outlook": "stable",
                "sentiment_summary": "neutral",
                "risk_alerts": ["liquidity", "sector rotation"],
            },
            "signal_attribution": {
                "technical_indicators": 40,
                "news_sentiment": 20,
                "fundamentals": 20,
                "market_conditions": 20,
            },
        },
        success=True,
    )


def workload_report_generate() -> Dict[str, Any]:
    """Report-path: single-stock + multi-stock daily report rendering."""
    from tests.litellm_stub import ensure_litellm_stub

    ensure_litellm_stub()
    from src.notification import NotificationService

    service = NotificationService()
    results = [_make_analysis_result(i) for i in range(REPORT_BATCH_SIZE)]

    def _once() -> tuple[str, str]:
        single = service.generate_single_stock_report(results[0])
        daily = service.generate_daily_report(results)
        return single, daily

    return _run_timed(
        "report_generate",
        "report_generate",
        _once,
        iterations=REPORT_ITERATIONS,
        notes=(
            f"generate_single_stock_report + generate_daily_report "
            f"for {REPORT_BATCH_SIZE} synthetic AnalysisResult rows"
        ),
    )


KEY_PATH_WORKLOADS: Mapping[str, Callable[[], Dict[str, Any]]] = {
    "data_fetch_indicators": workload_data_fetch_indicators,
    "analysis_trend": workload_analysis_trend,
    "report_generate": workload_report_generate,
}


def run_workload(name: str) -> Dict[str, Any]:
    """Run one named offline workload."""
    try:
        fn = KEY_PATH_WORKLOADS[name]
    except KeyError as exc:
        known = ", ".join(sorted(KEY_PATH_WORKLOADS))
        raise ValueError(f"unknown workload {name!r}; known: {known}") from exc
    return fn()


def run_all_workloads(
    names: Optional[Sequence[str]] = None,
    *,
    collect: bool = True,
) -> Dict[str, Any]:
    """Run selected (or all) offline workloads and return a report dict."""
    selected = list(names) if names else list(KEY_PATH_WORKLOADS.keys())
    token = None
    collector = None
    if collect:
        set_collection_enabled_override(True)
        collector, token = activate_collector()

    workloads: List[Dict[str, Any]] = []
    try:
        for name in selected:
            workloads.append(run_workload(name))
    finally:
        if collect:
            set_collection_enabled_override(None)
            if token is not None:
                reset_collector(token)

    report: Dict[str, Any] = {
        "schema_version": "perf-baseline-v1",
        "workloads": workloads,
    }
    if collector is not None:
        report["collector"] = collector.snapshot()
    return report
