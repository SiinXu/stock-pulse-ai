# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, retry, and ABC tests for the efinance history slice.

Issue #1068: stock-path daily fetch/normalize moved into
``src/data_provider/efinance_parts/history.py`` and are rebound onto the
public ``EfinanceFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

import src.data_provider.efinance_fetcher as efinance_mod
import src.data_provider.efinance_parts.history as history_mod
from src.data_provider.base import DataFetchError
from src.data_provider.efinance_fetcher import EfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_parts" / "history.py"

MOVED = (
    "_fetch_raw_data",
    "_fetch_stock_data",
    "_normalize_data",
)

METHOD_SIGNATURES = {
    "_fetch_raw_data": ["self", "stock_code", "start_date", "end_date"],
    "_fetch_stock_data": ["self", "stock_code", "start_date", "end_date"],
    "_normalize_data": ["self", "df", "stock_code"],
}


def _facade_body(name: str):
    method = EfinanceFetcher.__dict__[name]
    return getattr(method, "__wrapped__", method)


def _make_fetcher() -> EfinanceFetcher:
    with patch(
        "src.data_provider.efinance_fetcher.get_config",
        return_value=SimpleNamespace(enable_eastmoney_patch=False),
    ):
        return EfinanceFetcher(sleep_min=0, sleep_max=0)


def _ohlcv_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-05-25", "2026-05-26"],
            "开盘": [10.0, 10.5],
            "收盘": [10.8, 11.0],
            "最高": [11.0, 11.2],
            "最低": [9.8, 10.1],
            "成交量": [1000, 1200],
            "成交额": [10000, 12000],
            "涨跌幅": [1.0, 1.2],
            "股票代码": ["600519", "600519"],
        }
    )


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(EfinanceFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = EfinanceFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.efinance_fetcher", name
    assert method.__qualname__ == f"EfinanceFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    assert _facade_body(name).__globals__ is vars(efinance_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(EfinanceFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EfinanceFetcher"
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


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("efinance_fetcher" in module for module in imported)


def test_facade_bind_is_a_re_export_not_a_copy() -> None:
    """#1612 consolidated these helpers; this package must not add a copy."""

    from src.data_provider._facade_bind import bind_methods_from_class as shared
    from src.data_provider.efinance_parts.facade_bind import bind_methods_from_class

    assert bind_methods_from_class is shared


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(history_mod)
    for name in MOVED:
        method = EfinanceFetcher.__dict__[name]
        body = getattr(method, "__wrapped__", method)
        assert body.__globals__ is vars(efinance_mod), name
        assert method.__qualname__ == f"EfinanceFetcher.{name}", name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.efinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def _fetch_raw_data(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(efinance_mod), expected_names=MOVED,
        )


def test_fetcher_instantiates_after_abstract_clearing() -> None:
    assert not EfinanceFetcher.__abstractmethods__
    fetcher = _make_fetcher()
    assert isinstance(fetcher, EfinanceFetcher)


def test_fetch_raw_data_keeps_tenacity_retry_wrapper() -> None:
    fetch = EfinanceFetcher._fetch_raw_data
    assert callable(fetch)
    assert getattr(fetch, "__wrapped__", None) is not None


def test_us_code_raises_before_timeout_helper() -> None:
    fetcher = _make_fetcher()
    with patch.object(
        efinance_mod,
        "_ef_call_with_timeout",
        side_effect=AssertionError("US skip must not call Eastmoney"),
    ) as timeout:
        with pytest.raises(DataFetchError, match="不支持美股"):
            fetcher._fetch_raw_data("AAPL", "2026-05-25", "2026-05-27")
    timeout.assert_not_called()


def test_instance_stock_data_patch_is_visible_from_fetch_raw_data() -> None:
    fetcher = _make_fetcher()
    sentinel = pd.DataFrame({"ok": [1]})
    with patch.object(fetcher, "_fetch_stock_data", return_value=sentinel) as stock:
        with patch.object(efinance_mod, "_ef_call_with_timeout") as timeout:
            result = fetcher._fetch_raw_data("600519", "2026-05-25", "2026-05-27")
    stock.assert_called_once_with("600519", "2026-05-25", "2026-05-27")
    timeout.assert_not_called()
    assert result is sentinel


def test_moved_fetch_sees_patched_timeout_helper() -> None:
    fetcher = _make_fetcher()
    sentinel = pd.DataFrame({"日期": ["2026-05-25"]})
    original = efinance_mod._ef_call_with_timeout

    def fake_timeout(*args, **kwargs):
        return sentinel

    try:
        efinance_mod._ef_call_with_timeout = fake_timeout
        with patch.dict(
            "sys.modules",
            {"efinance": SimpleNamespace(stock=SimpleNamespace(get_quote_history=object()))},
        ):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                result = fetcher._fetch_stock_data("600519", "2026-05-25", "2026-05-27")
        assert result is sentinel
        assert (
            EfinanceFetcher.__dict__["_fetch_stock_data"].__globals__["_ef_call_with_timeout"]
            is fake_timeout
        )
    finally:
        efinance_mod._ef_call_with_timeout = original



def test_moved_normalize_sees_patched_standard_columns() -> None:
    original = efinance_mod.STANDARD_COLUMNS
    fetcher = _make_fetcher()
    raw = _ohlcv_frame()
    try:
        efinance_mod.STANDARD_COLUMNS = ["date", "close"]
        normalized = fetcher._normalize_data(raw, "600519")
        assert list(normalized.columns) == ["code", "date", "close"]
    finally:
        efinance_mod.STANDARD_COLUMNS = original
