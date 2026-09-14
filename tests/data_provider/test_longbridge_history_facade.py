# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, retry, and ABC tests for Longbridge history.

Issue #1068: ``_fetch_raw_data`` and ``_normalize_data`` moved into
``src/data_provider/longbridge_parts/history.py`` and are rebound onto the
public ``LongbridgeFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
import time
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import src.data_provider.longbridge_fetcher as longbridge_mod
import src.data_provider.longbridge_parts.history as history_mod
from src.data_provider.base import STANDARD_COLUMNS
from src.data_provider.longbridge_fetcher import LongbridgeFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "longbridge_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "longbridge_parts" / "history.py"

MOVED = (
    "_fetch_raw_data",
    "_normalize_data",
)

METHOD_SIGNATURES = {
    "_fetch_raw_data": ["self", "stock_code", "start_date", "end_date"],
    "_normalize_data": ["self", "df", "stock_code"],
}

CONNECTION_STAYS = (
    "_get_ctx",
    "_is_available",
    "is_available_for_request",
    "_is_connection_error",
    "_mark_connection_cooldown",
    "_invalidate_ctx",
)

REALTIME_BOUND = (
    "_ts_sort_key",
    "_compute_volume_ratio",
    "_get_static_info",
    "get_stock_name",
    "get_realtime_quote",
)


def _facade_body(name: str):
    method = LongbridgeFetcher.__dict__[name]
    return getattr(method, "__wrapped__", method)


def _make_fetcher() -> LongbridgeFetcher:
    fetcher = LongbridgeFetcher()
    fetcher._available = True
    return fetcher


def _ensure_openapi_import() -> None:
    try:
        from longbridge.openapi import AdjustType, Period  # noqa: F401
    except ImportError:
        mock_openapi = types.ModuleType("longbridge.openapi")
        mock_openapi.Period = SimpleNamespace(Day=object())
        mock_openapi.AdjustType = SimpleNamespace(ForwardAdjust=object())
        sys.modules.setdefault("longbridge", types.ModuleType("longbridge"))
        sys.modules["longbridge.openapi"] = mock_openapi


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LongbridgeFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(LongbridgeFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = LongbridgeFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.longbridge_fetcher", name
    assert method.__qualname__ == f"LongbridgeFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    assert _facade_body(name).__globals__ is vars(longbridge_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(LongbridgeFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


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


@pytest.mark.parametrize("name", CONNECTION_STAYS)
def test_connection_methods_stay_on_the_facade(name) -> None:
    assert name in _facade_class_methods(), name


@pytest.mark.parametrize("name", REALTIME_BOUND)
def test_realtime_methods_stay_bound_and_are_not_live_function_defs(name) -> None:
    assert callable(getattr(LongbridgeFetcher, name)), name
    assert name not in _facade_class_methods(), name


def test_fetch_raw_data_keeps_provider_retry_wrapper() -> None:
    fetch = LongbridgeFetcher._fetch_raw_data
    assert callable(fetch)
    assert getattr(fetch, "__wrapped__", None) is not None


def test_fetcher_instantiates_after_abstract_clearing() -> None:
    assert not LongbridgeFetcher.__abstractmethods__
    fetcher = LongbridgeFetcher()
    assert isinstance(fetcher, LongbridgeFetcher)


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("longbridge_fetcher" in module for module in imported)


def test_owner_module_introduces_no_bare_get_config_call() -> None:
    source = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "from src.config import get_config" not in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "get_config"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module != "src.config"
            assert not (node.module or "").startswith("src.config.")


def test_facade_bind_is_a_re_export_not_a_copy() -> None:
    from src.data_provider._facade_bind import bind_methods_from_class as shared
    from src.data_provider.longbridge_parts.facade_bind import bind_methods_from_class

    assert bind_methods_from_class is shared
    assert history_mod.bind_methods_from_class is bind_methods_from_class


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(history_mod)
    for name in MOVED:
        method = LongbridgeFetcher.__dict__[name]
        body = getattr(method, "__wrapped__", method)
        assert body.__globals__ is vars(longbridge_mod), name
        assert method.__qualname__ == f"LongbridgeFetcher.{name}", name
    for name in REALTIME_BOUND:
        function = LongbridgeFetcher.__dict__[name]
        assert callable(getattr(LongbridgeFetcher, name)), name
        assert function.__globals__ is vars(longbridge_mod), name
    assert getattr(LongbridgeFetcher._fetch_raw_data, "__wrapped__", None) is not None


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.longbridge_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def _fetch_raw_data(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(longbridge_mod), expected_names=MOVED,
        )


def test_daily_data_skips_request_during_cooldown() -> None:
    fetcher = _make_fetcher()
    ctx = MagicMock()
    fetcher._ctx = ctx
    fetcher._cooldown_until = time.time() + 30

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        fetcher._fetch_raw_data("AAPL", "2026-05-01", "2026-05-08")

    ctx.history_candlesticks_by_date.assert_not_called()


def test_invalid_symbol_raises_before_sdk_import() -> None:
    fetcher = _make_fetcher()
    with pytest.raises(ValueError, match="Cannot convert"):
        fetcher._fetch_raw_data("600519", "2026-05-01", "2026-05-08")


def test_missing_ctx_raises_runtime_error() -> None:
    fetcher = _make_fetcher()
    fetcher._ctx = None
    with patch.object(fetcher, "_get_ctx", return_value=None):
        with pytest.raises(RuntimeError, match="QuoteContext not available"):
            fetcher._fetch_raw_data("AAPL", "2026-05-01", "2026-05-08")


def test_connection_error_marks_cooldown_then_reraises() -> None:
    _ensure_openapi_import()
    fetcher = _make_fetcher()
    ctx = MagicMock()
    ctx.history_candlesticks_by_date.side_effect = Exception("client is closed")
    fetcher._ctx = ctx

    with patch(
        "src.data_provider.longbridge_fetcher._connection_cooldown_seconds",
        return_value=30,
    ):
        with pytest.raises(Exception, match="client is closed"):
            fetcher._fetch_raw_data("AAPL", "2026-05-01", "2026-05-08")

    assert fetcher._cooldown_until > time.time()
    assert fetcher._ctx is None


def test_empty_candles_return_empty_frame() -> None:
    _ensure_openapi_import()
    fetcher = _make_fetcher()
    ctx = MagicMock()
    ctx.history_candlesticks_by_date.return_value = []
    fetcher._ctx = ctx

    result = fetcher._fetch_raw_data("AAPL", "2026-05-01", "2026-05-08")
    assert result.empty


def test_candles_without_timestamp_are_skipped() -> None:
    _ensure_openapi_import()
    fetcher = _make_fetcher()
    ctx = MagicMock()
    skipped = SimpleNamespace(
        timestamp=None, open=1, high=2, low=0.5, close=1.5, volume=10, turnover=100
    )
    kept = SimpleNamespace(
        timestamp=datetime(2026, 5, 1),
        open=10,
        high=11,
        low=9,
        close=10.5,
        volume=100,
        turnover=1000,
    )
    ctx.history_candlesticks_by_date.return_value = [skipped, kept]
    fetcher._ctx = ctx

    result = fetcher._fetch_raw_data("AAPL", "2026-05-01", "2026-05-08")
    assert list(result["date"]) == ["2026-05-01"]
    assert result.loc[0, "close"] == 10.5
    assert result.loc[0, "turnover"] == 1000.0


def test_moved_fetch_sees_patched_to_longbridge_symbol() -> None:
    fetcher = _make_fetcher()
    original = longbridge_mod._to_longbridge_symbol
    try:
        longbridge_mod._to_longbridge_symbol = lambda *a, **k: None
        with pytest.raises(ValueError, match="Cannot convert"):
            fetcher._fetch_raw_data("AAPL", "2026-05-01", "2026-05-08")
        assert (
            _facade_body("_fetch_raw_data").__globals__["_to_longbridge_symbol"]
            is longbridge_mod._to_longbridge_symbol
        )
    finally:
        longbridge_mod._to_longbridge_symbol = original


def test_normalize_empty_returns_standard_columns() -> None:
    fetcher = _make_fetcher()
    out = fetcher._normalize_data(pd.DataFrame(), "AAPL")
    assert list(out.columns) == list(STANDARD_COLUMNS)
    assert out.empty


def test_normalize_renames_turnover_and_computes_pct_chg() -> None:
    fetcher = _make_fetcher()
    raw = pd.DataFrame(
        {
            "date": ["2026-05-01", "2026-05-02"],
            "open": [10.0, 11.0],
            "high": [11.0, 12.0],
            "low": [9.0, 10.0],
            "close": [10.0, 11.0],
            "volume": [100, 120],
            "turnover": [1000.0, 1200.0],
        }
    )
    out = fetcher._normalize_data(raw, "AAPL")
    assert list(out.columns) == list(STANDARD_COLUMNS)
    assert "turnover" not in out.columns
    assert pd.isna(out.loc[0, "pct_chg"])
    assert out.loc[1, "pct_chg"] == pytest.approx(10.0)
    assert out.loc[1, "amount"] == 1200.0
