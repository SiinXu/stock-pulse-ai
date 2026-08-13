# -*- coding: utf-8 -*-
"""Unit tests for opt-in performance span collection."""

from __future__ import annotations

import time

import pytest

from src.perf.collector import (
    PerfCollector,
    activate_collector,
    get_current_collector,
    is_perf_collection_enabled,
    perf_span,
    record_span,
    reset_collector,
    set_collection_enabled_override,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_perf_flags():
    set_collection_enabled_override(None)
    yield
    set_collection_enabled_override(None)


def test_collection_default_disabled_without_override() -> None:
    assert is_perf_collection_enabled() is False


def test_perf_span_is_noop_when_disabled() -> None:
    set_collection_enabled_override(False)
    collector, token = activate_collector()
    try:
        with perf_span("should_not_record", category="test"):
            time.sleep(0.001)
        assert collector.snapshot()["span_count"] == 0
    finally:
        reset_collector(token)


def test_perf_span_is_noop_without_active_collector() -> None:
    set_collection_enabled_override(True)
    assert get_current_collector() is None
    with perf_span("no_collector"):
        pass


def test_perf_span_records_when_enabled_and_active() -> None:
    set_collection_enabled_override(True)
    collector, token = activate_collector()
    try:
        with perf_span("demo_span", category="unit", attrs={"k": 1}):
            time.sleep(0.002)
        snapshot = collector.snapshot()
        assert snapshot["span_count"] == 1
        span = snapshot["spans"][0]
        assert span["name"] == "demo_span"
        assert span["category"] == "unit"
        assert span["duration_ms"] >= 1.0
        assert span["attrs"]["k"] == 1
    finally:
        reset_collector(token)


def test_record_span_respects_disabled_flag() -> None:
    set_collection_enabled_override(False)
    collector, token = activate_collector()
    try:
        record_span("ignored", 12.5, category="x")
        assert collector.snapshot()["span_count"] == 0
    finally:
        reset_collector(token)


def test_collector_bounds_span_count() -> None:
    collector = PerfCollector(max_spans=3)
    for index in range(5):
        collector.record(f"s{index}", float(index))
    snapshot = collector.snapshot()
    assert snapshot["span_count"] == 3
    assert snapshot["dropped"] == 2
    assert [s["name"] for s in snapshot["spans"]] == ["s2", "s3", "s4"]
