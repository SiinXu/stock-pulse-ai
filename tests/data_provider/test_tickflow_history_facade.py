# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, and characterization for the TickFlow history slice.

Issue #1068: ``_fetch_raw_data`` and ``_normalize_data`` moved into
``src/data_provider/tickflow_parts/history.py`` and are rebound onto the
public ``TickFlowFetcher`` class.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import src.data_provider._facade_bind as shared_bind
import src.data_provider.tickflow_fetcher as tickflow_mod
import src.data_provider.tickflow_parts.facade_bind as tickflow_bind
import src.data_provider.tickflow_parts.history as history_mod
from src.data_provider.base import DataFetchError, STANDARD_COLUMNS
from src.data_provider.tickflow_fetcher import TickFlowFetcher
from src.data_provider.tickflow_parts.facade_bind import _descriptor_function
from tests.test_tickflow_fetcher import _FakeClient, _daily_rows

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "tickflow_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "tickflow_parts" / "history.py"

MOVED = (
    "_fetch_raw_data",
    "_normalize_data",
)

METHOD_SIGNATURES = {
    "_fetch_raw_data": ["self", "stock_code", "start_date", "end_date"],
    "_normalize_data": ["self", "df", "stock_code"],
}

FACADE_SIBLINGS = (
    "_to_tickflow_symbol",
    "_daily_cache_key",
    "_get_daily_cache",
    "_get_client",
    "_daily_kline_count",
    "_date_to_ms",
    "_prepare_daily_frame",
    "_set_daily_cache",
    "_coerce_frame",
    "_extract_date_series",
    "_cn_lots_to_shares",
    "_ratio_series_to_percent",
)

BOARDS_BOUND = (
    "get_main_indices",
    "get_market_stats",
    "get_sector_rankings",
)

FREE_NAMES = (
    "pd",
    "STANDARD_COLUMNS",
    "normalize_stock_code",
    "DataFetchError",
)


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TickFlowFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _make_fetcher(*, api_key: str = "sk-test") -> TickFlowFetcher:
    return TickFlowFetcher(api_key=api_key)


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(TickFlowFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_are_instance_methods(name) -> None:
    descriptor = TickFlowFetcher.__dict__[name]
    assert not isinstance(descriptor, (staticmethod, classmethod)), name
    assert inspect.isfunction(_descriptor_function(descriptor)), name


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = _descriptor_function(TickFlowFetcher.__dict__[name])
    assert method.__module__ == "src.data_provider.tickflow_fetcher", name
    assert method.__qualname__ == f"TickFlowFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    method = _descriptor_function(TickFlowFetcher.__dict__[name])
    assert method.__globals__ is vars(tickflow_mod), name
    for free_name in FREE_NAMES:
        assert free_name in method.__globals__, free_name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(TickFlowFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def test_source_and_facade_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(history_mod._HistoryMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(TickFlowFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == history_mod.__name__
    assert tuple(source_names) == history_mod.EXPECTED_HISTORY_METHOD_NAMES == MOVED


def test_tickflow_facade_bind_is_the_shared_helper() -> None:
    assert tickflow_bind.bind_methods_from_class is shared_bind.bind_methods_from_class
    assert history_mod.bind_methods_from_class is tickflow_bind.bind_methods_from_class


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


@pytest.mark.parametrize("sibling", FACADE_SIBLINGS)
def test_sibling_helpers_stay_on_the_facade(sibling) -> None:
    """The moved bodies reach these through ``self``; moving any would widen the slice."""

    assert sibling in _facade_class_methods(), sibling


@pytest.mark.parametrize("name", BOARDS_BOUND)
def test_boards_methods_stay_bound_and_are_not_live_function_defs(name) -> None:
    assert callable(getattr(TickFlowFetcher, name)), name
    assert name not in _facade_class_methods(), name


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("tickflow_fetcher" in module for module in imported)


def test_owner_introduces_no_bare_get_config_call() -> None:
    source = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "from src.config import get_config" not in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "get_config"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module != "src.config"
            assert not (node.module or "").startswith("src.config.")


def test_fetch_raw_data_is_not_wrapped_in_tenacity() -> None:
    fetch = TickFlowFetcher._fetch_raw_data
    assert callable(fetch)
    assert getattr(fetch, "__wrapped__", None) is None


def test_fetcher_instantiates_after_abstract_clearing() -> None:
    assert not TickFlowFetcher.__abstractmethods__
    fetcher = _make_fetcher()
    assert isinstance(fetcher, TickFlowFetcher)


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.tickflow_fetcher as facade",
                    "import src.data_provider.tickflow_parts.history as history",
                    "",
                    "history_names = history.EXPECTED_HISTORY_METHOD_NAMES",
                    "boards_names = ('get_main_indices', 'get_market_stats', 'get_sector_rankings')",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    bound = {}",
                    "    owner = history._HistoryMethods",
                    "    for name in history_names:",
                    "        source[name] = descriptor_function(vars(owner)[name])",
                    "        bound[name] = descriptor_function(",
                    "            vars(facade.TickFlowFetcher)[name]",
                    "        )",
                    "        assert bound[name] is not source[name]",
                    "        assert bound[name].__code__ is source[name].__code__",
                    "        assert bound[name].__globals__ is vars(facade)",
                    "        assert bound[name].__module__ == (",
                    "            'src.data_provider.tickflow_fetcher'",
                    "        )",
                    "        assert bound[name].__qualname__ == (",
                    "            f'TickFlowFetcher.{name}'",
                    "        )",
                    "    for name in boards_names:",
                    "        assert callable(getattr(facade.TickFlowFetcher, name))",
                    "    return source, bound",
                    "",
                    body,
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_reloading_history_rereads_and_rebinds_the_owner() -> None:
    _run_reload_contract(
        """
old_class = facade.TickFlowFetcher
before_source, before_bound = bindings()
history = importlib.reload(history)
assert facade.TickFlowFetcher is old_class
after_source, after_bound = bindings()
for name in history_names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
    assert after_bound[name].__globals__ is vars(facade)
    assert after_bound[name].__module__ == 'src.data_provider.tickflow_fetcher'
"""
    )


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.tickflow_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def _fetch_raw_data(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial,
            _Target,
            vars(tickflow_mod),
            expected_names=MOVED,
        )


@pytest.mark.parametrize("code", ("AAPL", "SPX", "QQQ", "BRK.B", "HK00700", "00700.HK"))
def test_us_hk_codes_reject_before_client(code) -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(daily_data=_daily_rows())
    fetcher._client = client
    with pytest.raises(DataFetchError, match="only supports A-share/ETF symbols"):
        fetcher._fetch_raw_data(code, "2024-01-01", "2024-01-03")
    assert client.klines.get_calls == []


@pytest.mark.parametrize("api_key", ("", "   "))
def test_empty_or_whitespace_api_key_raises_after_convert(api_key) -> None:
    fetcher = _make_fetcher(api_key=api_key)
    with patch.object(fetcher, "_build_client") as build:
        with pytest.raises(DataFetchError, match="TickFlow API key is not configured"):
            fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03")
    build.assert_not_called()


def test_daily_kline_normalizes_lots_to_shares_and_derived_pct_chg() -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(daily_data=_daily_rows())
    fetcher._client = client

    raw = fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03")
    normalized = fetcher._normalize_data(raw, "600519")

    call = client.klines.get_calls[0]
    assert call["symbol"] == "600519.SH"
    assert call["period"] == "1d"
    assert call["count"] == 30
    assert call["adjust"] == "none"
    assert call["as_dataframe"] is True
    assert normalized.iloc[0]["volume"] == 10000
    assert normalized.iloc[1]["volume"] == 20000
    assert normalized.iloc[1]["pct_chg"] == pytest.approx(10.0)


def test_existing_pct_chg_column_is_kept_as_percent() -> None:
    rows = _daily_rows()
    rows["pct_chg"] = [0.0, 0.5]
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(daily_data=rows)

    normalized = fetcher._normalize_data(
        fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03"),
        "600519",
    )
    assert normalized.iloc[1]["pct_chg"] == pytest.approx(0.5)


def test_change_pct_column_is_converted_from_ratio() -> None:
    rows = _daily_rows()
    rows["change_pct"] = [0.0, 0.005]
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(daily_data=rows)

    normalized = fetcher._normalize_data(
        fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03"),
        "600519",
    )
    assert normalized.iloc[1]["pct_chg"] == pytest.approx(0.5)


@pytest.mark.parametrize("raw", (pd.DataFrame(), None))
def test_empty_or_missing_raw_frame_returns_standard_columns(raw) -> None:
    fetcher = _make_fetcher()
    normalized = fetcher._normalize_data(raw, "600519")
    assert list(normalized.columns) == ["code", *STANDARD_COLUMNS]
    assert normalized.empty


def test_cache_hit_returns_copy_and_skips_klines_get() -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(daily_data=_daily_rows())
    fetcher._client = client

    first = fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03")
    second = fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03")

    assert len(client.klines.get_calls) == 1
    assert first.equals(second)
    assert first is not second


def test_kline_exception_is_wrapped_as_data_fetch_error() -> None:
    class _BoomKlines:
        def get(self, *args, **kwargs):
            raise Exception("network down")

    class _BoomClient:
        def __init__(self):
            self.klines = _BoomKlines()

    fetcher = _make_fetcher()
    fetcher._client = _BoomClient()
    with pytest.raises(
        DataFetchError,
        match="TickFlow daily K-line request failed: network down",
    ) as exc_info:
        fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03")
    assert isinstance(exc_info.value.__cause__, Exception)
    assert str(exc_info.value.__cause__) == "network down"


def test_prepare_daily_frame_data_fetch_error_is_not_rewrapped() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(daily_data=_daily_rows())
    with patch.object(
        fetcher,
        "_prepare_daily_frame",
        side_effect=DataFetchError("truncated incomplete history"),
    ):
        with pytest.raises(DataFetchError, match="truncated incomplete history") as exc_info:
            fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03")
    assert "K-line request failed" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_instance_to_tickflow_symbol_patch_is_visible_from_fetch() -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(daily_data=_daily_rows())
    fetcher._client = client
    with patch.object(fetcher, "_to_tickflow_symbol", return_value=None) as convert:
        with pytest.raises(DataFetchError, match="only supports A-share/ETF symbols"):
            fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03")
    convert.assert_called_once_with("600519")
    assert client.klines.get_calls == []


def test_normalize_hits_patched_facade_normalize_stock_code() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(daily_data=_daily_rows())
    raw = fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-03")
    with patch(
        "src.data_provider.tickflow_fetcher.normalize_stock_code",
        return_value="SENTINEL",
    ) as normalize:
        normalized = fetcher._normalize_data(raw, "600519")
    normalize.assert_called_once_with("600519")
    assert (normalized["code"] == "SENTINEL").all()


@pytest.mark.parametrize(
    ("code", "symbol"),
    (
        ("510300", "510300.SH"),
        ("sh510300", "510300.SH"),
        ("159919", "159919.SZ"),
        ("430047", "430047.BJ"),
        ("bj430047", "430047.BJ"),
    ),
)
def test_etf_and_bse_symbols_convert_and_fetch(code, symbol) -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(daily_data=_daily_rows(symbol))
    fetcher._client = client
    fetcher._fetch_raw_data(code, "2024-01-01", "2024-01-03")
    assert client.klines.get_calls[0]["symbol"] == symbol
