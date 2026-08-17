# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity and rebind guards for errors/chip/daily-cache extractions."""

from __future__ import annotations

import importlib
from pathlib import Path

import data_provider.chip_helpers as chip_helpers
import data_provider.errors as errors
from data_provider.base import (
    CircuitOpenError,
    DataFetchError,
    DataFetcherManager,
    DataSourceUnavailableError,
    RateLimitError,
    _coerce_chip_metric,
    _is_meaningful_chip_distribution,
    summarize_exception,
    unwrap_exception,
)


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
ERRORS_PATH = ROOT / "src" / "data_provider" / "errors.py"
CHIP_PATH = ROOT / "src" / "data_provider" / "chip_helpers.py"
CACHE_METHODS_PATH = (
    ROOT / "src" / "data_provider" / "manager_parts" / "daily_cache_methods.py"
)


def test_error_types_and_helpers_reexport_owner_identity() -> None:
    assert DataFetchError is errors.DataFetchError
    assert RateLimitError is errors.RateLimitError
    assert DataSourceUnavailableError is errors.DataSourceUnavailableError
    assert CircuitOpenError is errors.CircuitOpenError
    assert unwrap_exception is errors.unwrap_exception
    assert summarize_exception is errors.summarize_exception
    assert issubclass(RateLimitError, DataFetchError)
    assert issubclass(CircuitOpenError, DataSourceUnavailableError)
    assert issubclass(DataSourceUnavailableError, DataFetchError)

    nested = ValueError("root")
    wrapped = RuntimeError("outer")
    wrapped.__cause__ = nested
    assert unwrap_exception(wrapped) is nested
    error_type, message = summarize_exception(wrapped)
    assert error_type == "ValueError"
    assert "outer" in message


def test_chip_helpers_reexport_owner_identity() -> None:
    assert _coerce_chip_metric is chip_helpers._coerce_chip_metric
    assert _is_meaningful_chip_distribution is chip_helpers._is_meaningful_chip_distribution
    assert _coerce_chip_metric("1.25") == 1.25
    assert _coerce_chip_metric(float("nan")) is None
    assert _is_meaningful_chip_distribution(None) is False


def test_daily_cache_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = (
        "_get_daily_data_cache",
        "is_market_data_local_only",
        "_daily_adjustment_identity",
        "_daily_cache_key",
        "_record_daily_cache_result",
        "_validate_daily_candidate",
        "get_daily_cache_stats",
        "invalidate_daily_cache",
        "_get_cached_stock_name",
        "_cache_stock_name",
    )
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        assert method.__module__ == "src.data_provider.base", name
        assert method.__qualname__.startswith("DataFetcherManager."), name


def test_daily_cache_key_and_stock_name_cache_behavior() -> None:
    manager = DataFetcherManager(fetchers=[])
    key_a = DataFetcherManager._daily_cache_key("aapl", None, "2026-07-20", 30)
    key_b = DataFetcherManager._daily_cache_key("AAPL", None, "2026-07-20", 30)
    assert key_a == key_b
    assert manager._cache_stock_name("600519", "贵州茅台") == "贵州茅台"
    assert manager._get_cached_stock_name("600519") == "贵州茅台"
    assert manager.get_daily_cache_stats()["hits"] >= 0


def test_owner_modules_exist_for_extraction_slice() -> None:
    assert ERRORS_PATH.is_file()
    assert CHIP_PATH.is_file()
    assert CACHE_METHODS_PATH.is_file()
    assert "from .errors import" in BASE_PATH.read_text(encoding="utf-8")
    assert "daily_cache_methods" in BASE_PATH.read_text(encoding="utf-8")
    importlib.import_module("data_provider.manager_parts.daily_cache_methods")
