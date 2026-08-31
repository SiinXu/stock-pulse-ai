# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and legacy-symbol tests for the Tushare realtime slice.

Issue #1068: ``get_realtime_quote`` and ``_get_legacy_realtime_symbol`` moved
into ``src/data_provider/tushare_parts/realtime.py`` and are rebound onto the
public ``TushareFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import src.data_provider.tushare_fetcher as tushare_mod
import src.data_provider.tushare_parts.realtime as realtime_mod
from src.data_provider.tushare_fetcher import TushareFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "tushare_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "tushare_parts" / "realtime.py"

MOVED = (
    "_get_legacy_realtime_symbol",
    "get_realtime_quote",
)

METHOD_SIGNATURES = {
    "_get_legacy_realtime_symbol": ["stock_code"],
    "get_realtime_quote": ["self", "stock_code"],
}

# Reached through `self` by the moved bodies; all stay on the facade.
FACADE_SIBLINGS = (
    "get_trade_time",
    "get_chip_distribution",
    "_get_trade_dates",
    "_pick_trade_date",
    "_get_china_now",
)

# Domains this package already owned before the slice; binding must still work.
PRE_EXISTING_BOUND = (
    "get_daily_data",
    "_convert_stock_code",
    "get_main_indices",
    "get_stock_name",
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


def _make_fetcher() -> TushareFetcher:
    with patch.object(TushareFetcher, "_init_api", return_value=None):
        fetcher = TushareFetcher()
    fetcher._api = MagicMock()
    return fetcher


def _legacy_quote_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "name": "平安银行",
                "price": "10.94",
                "pre_close": "10.88",
                "volume": "1000",
                "amount": "2000",
                "high": "11.00",
                "low": "10.80",
                "open": "10.90",
            }
        ]
    )


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(TushareFetcher, name))


def test_legacy_symbol_helper_stays_a_classmethod() -> None:
    assert isinstance(
        TushareFetcher.__dict__["_get_legacy_realtime_symbol"], classmethod
    )


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = _descriptor_function(TushareFetcher.__dict__[name])
    assert method.__module__ == "src.data_provider.tushare_fetcher", name
    assert method.__qualname__ == f"TushareFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    method = _descriptor_function(TushareFetcher.__dict__[name])
    assert method.__globals__ is vars(tushare_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(TushareFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def test_source_and_facade_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(realtime_mod._RealtimeMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(TushareFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == realtime_mod.__name__
    assert tuple(source_names) == realtime_mod.EXPECTED_REALTIME_METHOD_NAMES == MOVED


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TushareFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_owner_module_declares_exactly_the_slice() -> None:
    assert realtime_mod.EXPECTED_REALTIME_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_RealtimeMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


@pytest.mark.parametrize("sibling", FACADE_SIBLINGS)
def test_chip_and_trade_calendar_helpers_stay_on_the_facade(sibling) -> None:
    """The moved bodies must not pull chip or trade-time helpers with them."""

    assert sibling in _facade_class_methods(), sibling


def test_rate_limited_client_state_stays_on_the_facade() -> None:
    source = FACADE_PATH.read_text(encoding="utf-8")
    for attribute in ("_api", "_check_rate_limit", "_call_api_with_rate_limit"):
        assert attribute in source, attribute


@pytest.mark.parametrize("name", PRE_EXISTING_BOUND)
def test_previously_bound_domains_are_not_disturbed(name) -> None:
    method = getattr(TushareFetcher, name, None)
    assert callable(method), name


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("SH000001", "sh000001"),
        ("000001.SH", "sh000001"),
        ("399001", "sz399001"),
        ("SZ399001", "sz399001"),
        ("399006", "sz399006"),
        ("000300", "sh000300"),
        ("SZ000001", "000001"),
        ("600519", "600519"),
        ("830001", "bj830001"),
    ),
)
def test_legacy_realtime_symbol_preserves_exchange_hints(raw, expected) -> None:
    assert TushareFetcher._get_legacy_realtime_symbol(raw) == expected


def test_moved_bodies_still_reach_a_patched_facade_global() -> None:
    original = tushare_mod.normalize_stock_code
    try:
        tushare_mod.normalize_stock_code = lambda code: "SENTINEL"
        assert TushareFetcher._get_legacy_realtime_symbol("600519") == "SENTINEL"
    finally:
        tushare_mod.normalize_stock_code = original


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("tushare_fetcher" in module for module in imported)


def test_owner_reload_rebinds_and_leaves_other_domains_intact() -> None:
    importlib.reload(realtime_mod)
    for name in MOVED:
        method = _descriptor_function(TushareFetcher.__dict__[name])
        assert method.__globals__ is vars(tushare_mod), name
        assert method.__qualname__ == f"TushareFetcher.{name}", name
    for name in PRE_EXISTING_BOUND:
        assert callable(getattr(TushareFetcher, name, None)), name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.tushare_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_realtime_quote(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(tushare_mod), expected_names=MOVED,
        )


def test_missing_api_returns_none_without_network() -> None:
    fetcher = _make_fetcher()
    fetcher._api = None
    assert fetcher.get_realtime_quote("600519") is None


def test_hk_codes_are_skipped() -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "_check_rate_limit") as rate_limit:
        assert fetcher.get_realtime_quote("hk00700") is None
        assert fetcher.get_realtime_quote("00700") is None
    rate_limit.assert_not_called()


@patch.dict(sys.modules, {"tushare": MagicMock()})
def test_legacy_path_uses_public_facade_and_legacy_symbol() -> None:
    fetcher = _make_fetcher()
    fetcher._api.quotation.side_effect = Exception("quota")
    tushare_module = sys.modules["tushare"]
    tushare_module.get_realtime_quotes.return_value = _legacy_quote_frame()

    quote = fetcher.get_realtime_quote("SZ000001")

    assert quote is not None
    assert quote.code == "000001"
    assert quote.name == "平安银行"
    assert quote.price == 10.94
    tushare_module.get_realtime_quotes.assert_called_once_with("000001")
    fetcher._api.quotation.assert_called_once()


@patch.dict(sys.modules, {"tushare": MagicMock()})
def test_legacy_index_symbol_path_keeps_sh_hint() -> None:
    fetcher = _make_fetcher()
    fetcher._api.quotation.side_effect = Exception("quota")
    tushare_module = sys.modules["tushare"]
    tushare_module.get_realtime_quotes.return_value = _legacy_quote_frame()

    quote = fetcher.get_realtime_quote("SH000001")

    assert quote is not None
    tushare_module.get_realtime_quotes.assert_called_once_with("sh000001")


@patch.dict(sys.modules, {"tushare": MagicMock()})
def test_legacy_failure_fails_open_to_none() -> None:
    fetcher = _make_fetcher()
    fetcher._api.quotation.side_effect = Exception("quota")
    tushare_module = sys.modules["tushare"]
    tushare_module.get_realtime_quotes.side_effect = Exception("legacy down")

    assert fetcher.get_realtime_quote("600519") is None
