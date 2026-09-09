# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, retry, and ABC tests for the yfinance history slice.

Issue #1068: daily fetch/normalize moved into
``src/data_provider/yfinance_parts/history.py`` and are rebound onto the
public ``YfinanceFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from tenacity import RetryError

import src.data_provider.yfinance_fetcher as yfinance_mod
import src.data_provider.yfinance_parts.history as history_mod
from src.data_provider.base import DataFetchError
from src.data_provider.yfinance_fetcher import YfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "yfinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "yfinance_parts" / "history.py"

MOVED = (
    "_fetch_raw_data",
    "_normalize_data",
)

METHOD_SIGNATURES = {
    "_fetch_raw_data": ["self", "stock_code", "start_date", "end_date"],
    "_normalize_data": ["self", "df", "stock_code"],
}

UNMOVED_FACADE_METHODS = (
    "_convert_stock_code",
    "_is_us_stock",
    "_is_jp_kr_suffix_stock",
    "_is_tw_suffix_stock",
)


def _facade_body(name: str):
    method = YfinanceFetcher.__dict__[name]
    return getattr(method, "__wrapped__", method)


def _ohlcv_frame(*, empty: bool = False) -> pd.DataFrame:
    if empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "Open": [10.0, 10.5],
            "High": [11.0, 11.2],
            "Low": [9.8, 10.1],
            "Close": [10.8, 11.0],
            "Volume": [1000, 1200],
        },
        index=pd.DatetimeIndex(["2026-05-25", "2026-05-26"]),
    )


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(YfinanceFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = YfinanceFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.yfinance_fetcher", name
    assert method.__qualname__ == f"YfinanceFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    assert _facade_body(name).__globals__ is vars(yfinance_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(YfinanceFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "YfinanceFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_owner_module_declares_exactly_the_slice() -> None:
    assert history_mod.EXPECTED_HISTORY_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_HistoryMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


@pytest.mark.parametrize("name", UNMOVED_FACADE_METHODS)
def test_unmoved_methods_stay_on_the_facade(name) -> None:
    assert name in _facade_class_methods(), name


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("yfinance_fetcher" in module for module in imported)


def test_facade_bind_is_a_re_export_not_a_copy() -> None:
    """#1612 consolidated these helpers; this package must not add a copy."""

    from src.data_provider._facade_bind import bind_methods_from_class as shared
    from src.data_provider.yfinance_parts.facade_bind import bind_methods_from_class

    assert bind_methods_from_class is shared


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(history_mod)
    for name in MOVED:
        method = YfinanceFetcher.__dict__[name]
        body = getattr(method, "__wrapped__", method)
        assert body.__globals__ is vars(yfinance_mod), name
        assert method.__qualname__ == f"YfinanceFetcher.{name}", name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.yfinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def _fetch_raw_data(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(yfinance_mod), expected_names=MOVED,
        )


def test_fetcher_instantiates_after_abstract_clearing() -> None:
    assert not YfinanceFetcher.__abstractmethods__
    fetcher = YfinanceFetcher()
    assert isinstance(fetcher, YfinanceFetcher)


def test_fetch_raw_data_keeps_tenacity_retry_wrapper() -> None:
    fetch = YfinanceFetcher._fetch_raw_data
    assert callable(fetch)
    assert getattr(fetch, "__wrapped__", None) is not None


def test_moved_normalize_sees_patched_standard_columns() -> None:
    original = yfinance_mod.STANDARD_COLUMNS
    fetcher = YfinanceFetcher()
    raw = _ohlcv_frame()
    try:
        yfinance_mod.STANDARD_COLUMNS = ["date", "close"]
        normalized = fetcher._normalize_data(raw, "AAPL")
        assert list(normalized.columns) == ["code", "date", "close"]
    finally:
        yfinance_mod.STANDARD_COLUMNS = original


def test_moved_fetch_sees_patched_http_guard() -> None:
    seen = {"entered": False}

    class _Guard:
        def __enter__(self):
            seen["entered"] = True
            return self

        def __exit__(self, *exc):
            return False

    original = yfinance_mod._yfinance_http_guard
    try:
        yfinance_mod._yfinance_http_guard = lambda: _Guard()
        with patch("yfinance.download", return_value=_ohlcv_frame()) as download:
            frame = YfinanceFetcher()._fetch_raw_data("AAPL", "2026-05-25", "2026-05-27")
        download.assert_called_once()
        assert seen["entered"] is True
        assert not frame.empty
    finally:
        yfinance_mod._yfinance_http_guard = original


def test_moved_fetch_sees_instance_convert_stock_code_patch() -> None:
    fetcher = YfinanceFetcher()
    with patch.object(fetcher, "_convert_stock_code", return_value="SENTINEL") as convert:
        with patch("yfinance.download", return_value=_ohlcv_frame()) as download:
            fetcher._fetch_raw_data("AAPL", "2026-05-25", "2026-05-27")
    convert.assert_called_once_with("AAPL")
    assert download.call_args.kwargs["tickers"] == "SENTINEL"


def test_retry_retries_connection_error_outside_remap() -> None:
    calls = {"n": 0}

    def _raise_connection(_stock_code: str) -> str:
        calls["n"] += 1
        raise ConnectionError("transient daily convert")

    fetcher = YfinanceFetcher()
    with patch.object(fetcher, "_convert_stock_code", side_effect=_raise_connection):
        with patch("tenacity.nap.sleep", return_value=None):
            with pytest.raises(RetryError) as exc_info:
                fetcher._fetch_raw_data("AAPL", "2026-05-25", "2026-05-27")
    assert isinstance(exc_info.value.last_attempt.exception(), ConnectionError)
    assert calls["n"] == 3


def test_retry_retries_timeout_error_outside_remap() -> None:
    calls = {"n": 0}

    def _raise_timeout(_stock_code: str) -> str:
        calls["n"] += 1
        raise TimeoutError("transient daily convert")

    fetcher = YfinanceFetcher()
    with patch.object(fetcher, "_convert_stock_code", side_effect=_raise_timeout):
        with patch("tenacity.nap.sleep", return_value=None):
            with pytest.raises(RetryError) as exc_info:
                fetcher._fetch_raw_data("AAPL", "2026-05-25", "2026-05-27")
    assert isinstance(exc_info.value.last_attempt.exception(), TimeoutError)
    assert calls["n"] == 3


def test_retry_does_not_retry_data_fetch_error() -> None:
    calls = {"n": 0}

    def _raise_data(_stock_code: str) -> str:
        calls["n"] += 1
        raise DataFetchError("permanent convert failure")

    fetcher = YfinanceFetcher()
    with patch.object(fetcher, "_convert_stock_code", side_effect=_raise_data):
        with pytest.raises(DataFetchError, match="permanent convert failure"):
            fetcher._fetch_raw_data("AAPL", "2026-05-25", "2026-05-27")
    assert calls["n"] == 1


def test_empty_download_raises_data_fetch_error() -> None:
    with patch("yfinance.download", return_value=_ohlcv_frame(empty=True)):
        with pytest.raises(DataFetchError, match="未查询到"):
            YfinanceFetcher()._fetch_raw_data("AAPL", "2026-05-25", "2026-05-27")


def test_generic_sdk_exception_remaps_to_data_fetch_error() -> None:
    with patch("yfinance.download", side_effect=RuntimeError("sdk boom")):
        with patch.object(yfinance_mod, "log_safe_exception") as logged:
            with pytest.raises(DataFetchError, match="获取数据失败") as exc_info:
                YfinanceFetcher()._fetch_raw_data("AAPL", "2026-05-25", "2026-05-27")
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    logged.assert_called_once()
    assert logged.call_args.kwargs["error_code"] == "yfinance_daily_http_failed"
