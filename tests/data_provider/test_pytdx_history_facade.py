# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, retry, and ABC tests for Pytdx history.

Issue #1068: ``_fetch_raw_data`` and ``_normalize_data`` moved into
``src/data_provider/pytdx_parts/history.py`` and are rebound onto the
public ``PytdxFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import src.data_provider.pytdx_fetcher as pytdx_mod
import src.data_provider.pytdx_parts.history as history_mod
from src.data_provider.base import DataFetchError, STANDARD_COLUMNS
from src.data_provider.pytdx_fetcher import PytdxFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "pytdx_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "pytdx_parts" / "history.py"

MOVED = (
    "_fetch_raw_data",
    "_normalize_data",
)

METHOD_SIGNATURES = {
    "_fetch_raw_data": ["self", "stock_code", "start_date", "end_date"],
    "_normalize_data": ["self", "df", "stock_code"],
}

CONNECTION_STAYS = (
    "__init__",
    "_is_in_connection_cooldown",
    "_mark_connection_cooldown",
    "is_available_for_request",
    "_get_pytdx",
    "_pytdx_session",
    "_get_market_code",
    "_build_stock_list_cache",
    "get_stock_name",
    "get_realtime_quote",
)


def _facade_body(name: str):
    method = PytdxFetcher.__dict__[name]
    return getattr(method, "__wrapped__", method)


def _make_fetcher() -> PytdxFetcher:
    return PytdxFetcher(hosts=[])


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PytdxFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(PytdxFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = PytdxFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.pytdx_fetcher", name
    assert method.__qualname__ == f"PytdxFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    assert _facade_body(name).__globals__ is vars(pytdx_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(PytdxFetcher, name))
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
def test_connection_and_sibling_methods_stay_on_the_facade(name) -> None:
    assert name in _facade_class_methods(), name
    assert callable(getattr(PytdxFetcher, name)), name


def test_fetch_raw_data_keeps_provider_retry_wrapper() -> None:
    fetch = PytdxFetcher._fetch_raw_data
    assert callable(fetch)
    assert getattr(fetch, "__wrapped__", None) is not None


def test_fetcher_instantiates_after_abstract_clearing() -> None:
    assert not PytdxFetcher.__abstractmethods__
    fetcher = PytdxFetcher(hosts=[])
    assert isinstance(fetcher, PytdxFetcher)


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("pytdx_fetcher" in module for module in imported)


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
    from src.data_provider.pytdx_parts.facade_bind import bind_methods_from_class

    assert bind_methods_from_class is shared
    assert history_mod.bind_methods_from_class is bind_methods_from_class


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(history_mod)
    for name in MOVED:
        method = PytdxFetcher.__dict__[name]
        body = getattr(method, "__wrapped__", method)
        assert body.__globals__ is vars(pytdx_mod), name
        assert method.__qualname__ == f"PytdxFetcher.{name}", name
    for name in CONNECTION_STAYS:
        assert callable(getattr(PytdxFetcher, name)), name
        assert name in _facade_class_methods(), name
    assert getattr(PytdxFetcher._fetch_raw_data, "__wrapped__", None) is not None


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.pytdx_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def _fetch_raw_data(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(pytdx_mod), expected_names=MOVED,
        )


def test_us_code_raises_without_opening_a_session() -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "_pytdx_session") as session:
        with pytest.raises(DataFetchError, match="不支持美股"):
            fetcher._fetch_raw_data("AAPL", "2024-01-01", "2024-01-10")
    session.assert_not_called()


def test_hk_code_raises_without_opening_a_session() -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "_pytdx_session") as session:
        with pytest.raises(DataFetchError, match="不支持港股"):
            fetcher._fetch_raw_data("HK00700", "2024-01-01", "2024-01-10")
    session.assert_not_called()


def test_bse_code_raises_without_opening_a_session() -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "_pytdx_session") as session:
        with pytest.raises(DataFetchError, match="不支持北交所"):
            fetcher._fetch_raw_data("920000", "2024-01-01", "2024-01-10")
    session.assert_not_called()


def test_moved_fetch_sees_patched_call_with_timeout() -> None:
    fetcher = PytdxFetcher(hosts=[("127.0.0.1", 7709)])
    sentinel = pd.DataFrame({"datetime": ["2024-01-02"], "open": [1.0]})
    with patch("src.data_provider.pytdx_fetcher.call_with_timeout", return_value=sentinel) as mocked:
        result = fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-10")
    mocked.assert_called_once()
    assert mocked.call_args.kwargs["call_name"] == "pytdx.get_security_bars"
    assert result is sentinel
    assert (
        _facade_body("_fetch_raw_data").__globals__["call_with_timeout"]
        is pytdx_mod.call_with_timeout
    )


def test_normalize_maps_columns_and_fills_pct_chg() -> None:
    fetcher = _make_fetcher()
    raw = pd.DataFrame(
        {
            "datetime": ["2024-01-01", "2024-01-02"],
            "open": [10.0, 11.0],
            "high": [11.0, 12.0],
            "low": [9.0, 10.0],
            "close": [10.0, 11.0],
            "vol": [100, 120],
            "amount": [1000.0, 1200.0],
        }
    )
    out = fetcher._normalize_data(raw, "600519")
    assert "datetime" not in out.columns
    assert "vol" not in out.columns
    assert list(out["code"]) == ["600519", "600519"]
    assert out.loc[0, "pct_chg"] == 0.0
    assert out.loc[1, "pct_chg"] == pytest.approx(10.0)
    for col in ("date", "open", "high", "low", "close", "volume", "amount", "pct_chg"):
        if col in STANDARD_COLUMNS:
            assert col in out.columns
