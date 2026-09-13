# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, and characterization for TickFlow stock identity.

Issue #1068: ``get_stock_name``, ``_extract_instrument_name``, and
``get_stock_list`` moved into
``src/data_provider/tickflow_parts/stock_identity.py`` and are rebound onto the
public ``TickFlowFetcher`` class.
"""

from __future__ import annotations

import ast
import inspect
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.data_provider._facade_bind as shared_bind
import src.data_provider.tickflow_fetcher as tickflow_mod
import src.data_provider.tickflow_parts.facade_bind as tickflow_bind
import src.data_provider.tickflow_parts.stock_identity as identity_mod
from src.data_provider.tickflow_fetcher import TickFlowFetcher
from src.data_provider.tickflow_parts.facade_bind import _descriptor_function
from tests.test_tickflow_fetcher import (
    _FakeClient,
    _PermissionLikeError,
    _quote,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "tickflow_fetcher.py"
OWNER_PATH = (
    REPO_ROOT / "src" / "data_provider" / "tickflow_parts" / "stock_identity.py"
)

MOVED = (
    "get_stock_name",
    "_extract_instrument_name",
    "get_stock_list",
)

METHOD_SIGNATURES = {
    "get_stock_name": ["self", "stock_code"],
    "_extract_instrument_name": ["instrument"],
    "get_stock_list": ["self"],
}

FACADE_SIBLINGS = (
    "__init__",
    "close",
    "_build_client",
    "_get_client",
    "_to_tickflow_symbol",
    "_store_quotes",
    "_get_cached_quote",
    "_get_realtime_cache_ttl",
    "_extract_name",
    "_extract_universe_entries",
    "_extract_universe_symbols",
    "_is_cn_equity_symbol",
    "_is_universe_permission_error",
)

BOARDS_BOUND = (
    "get_main_indices",
    "get_market_stats",
    "get_sector_rankings",
)

HISTORY_BOUND = (
    "_fetch_raw_data",
    "_normalize_data",
)

REALTIME_BOUND = (
    "get_realtime_quote",
    "_quote_to_unified_quote",
    "_format_provider_timestamp",
)

FREE_NAMES = (
    "logger",
    "log_safe_exception",
    "normalize_stock_code",
    "_CN_UNIVERSE_ID",
    "pd",
)

FORBIDDEN_SIBLING_TOKENS = (
    "tushare_parts.realtime",
    "tushare_parts.chip",
    "tushare_parts.trade_time",
    "tushare_parts.stock_identity",
    "efinance_parts.realtime",
    "efinance_parts.symbols",
    "efinance_parts.info",
    "efinance_parts.rate_limit",
    "efinance_parts.timeout_client",
    "efinance_parts.eastmoney_errors",
    "yfinance_parts.realtime",
    "longbridge_parts.realtime",
)

EMPTY_LIST_COLUMNS = ["code", "name", "industry", "area", "market"]


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


class _RecordingQuotes:
    def __init__(self, payload=None, error=None):
        self.payload = [] if payload is None else payload
        self.error = error
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.payload


class _RecordingInstruments:
    def __init__(self, payload=None, error=None):
        self.payload = {"name": "InstrumentName"} if payload is None else payload
        self.error = error
        self.calls = []

    def get(self, symbol):
        self.calls.append(symbol)
        if self.error is not None:
            raise self.error
        return self.payload


class _RecordingUniverses:
    def __init__(self, payload=None, error=None):
        self.payload = {"symbols": []} if payload is None else payload
        self.error = error
        self.calls = []

    def get(self, universe_id):
        self.calls.append(universe_id)
        if self.error is not None:
            raise self.error
        return self.payload


class _IdentityClient:
    def __init__(self, *, quotes=None, instruments=None, universes=None):
        self.quotes = quotes or _RecordingQuotes()
        self.instruments = instruments or _RecordingInstruments()
        self.universes = universes or _RecordingUniverses()


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(TickFlowFetcher, name))


def test_extract_instrument_name_remains_a_staticmethod() -> None:
    descriptor = TickFlowFetcher.__dict__["_extract_instrument_name"]
    assert isinstance(descriptor, staticmethod)
    assert inspect.isfunction(_descriptor_function(descriptor))


@pytest.mark.parametrize("name", ("get_stock_name", "get_stock_list"))
def test_identity_public_methods_are_instance_methods(name) -> None:
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
    for name, source_descriptor in vars(identity_mod._StockIdentityMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(TickFlowFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == identity_mod.__name__
    assert tuple(source_names) == identity_mod.EXPECTED_STOCK_IDENTITY_METHOD_NAMES == MOVED


def test_tickflow_facade_bind_is_the_shared_helper() -> None:
    assert tickflow_bind.bind_methods_from_class is shared_bind.bind_methods_from_class
    assert identity_mod.bind_methods_from_class is tickflow_bind.bind_methods_from_class
    assert identity_mod.bind_stock_identity_methods_facade.__code__ is not None


def test_owner_module_declares_exactly_the_slice() -> None:
    assert identity_mod.EXPECTED_STOCK_IDENTITY_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_StockIdentityMethods"
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


@pytest.mark.parametrize("name", BOARDS_BOUND + HISTORY_BOUND + REALTIME_BOUND)
def test_other_bound_methods_stay_bound_and_are_not_live_function_defs(name) -> None:
    assert callable(getattr(TickFlowFetcher, name)), name
    assert name not in _facade_class_methods(), name


def test_owner_module_does_not_trip_sibling_production_import_greps() -> None:
    """Sibling production-import guards substring-match these tokens."""

    text = OWNER_PATH.read_text(encoding="utf-8")
    for token in FORBIDDEN_SIBLING_TOKENS:
        assert token not in text, token


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


@pytest.mark.parametrize("name", ("get_stock_name", "get_stock_list"))
def test_identity_methods_are_not_wrapped_in_tenacity(name) -> None:
    method = getattr(TickFlowFetcher, name)
    assert callable(method)
    assert getattr(method, "__wrapped__", None) is None


def test_fetcher_instantiates_after_binding() -> None:
    assert not TickFlowFetcher.__abstractmethods__
    fetcher = _make_fetcher()
    assert isinstance(fetcher, TickFlowFetcher)


def test_owner_and_facade_do_not_grow_a_stock_name_cache() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[_quote("600519.SH", name="Kweichow")])
    assert fetcher.get_stock_name("600519") == "Kweichow"
    fetcher.get_stock_list()
    assert not hasattr(fetcher, "_stock_name_cache")
    assert "_stock_name_cache" not in OWNER_PATH.read_text(encoding="utf-8")
    assert "_stock_name_cache" not in FACADE_PATH.read_text(encoding="utf-8")


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.tickflow_fetcher as facade",
                    "import src.data_provider.tickflow_parts.stock_identity as identity",
                    "from tests.test_tickflow_fetcher import _FakeClient, _quote",
                    "",
                    "identity_names = identity.EXPECTED_STOCK_IDENTITY_METHOD_NAMES",
                    "boards_names = ('get_main_indices', 'get_market_stats', 'get_sector_rankings')",
                    "history_names = ('_fetch_raw_data', '_normalize_data')",
                    "realtime_names = ('get_realtime_quote', '_quote_to_unified_quote', '_format_provider_timestamp')",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    bound = {}",
                    "    owner = identity._StockIdentityMethods",
                    "    for name in identity_names:",
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
                    "    for name in boards_names + history_names + realtime_names:",
                    "        assert callable(getattr(facade.TickFlowFetcher, name))",
                    "    assert callable(facade.TickFlowFetcher._extract_universe_symbols)",
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


def test_reloading_identity_rereads_and_rebinds_the_owner() -> None:
    _run_reload_contract(
        """
old_class = facade.TickFlowFetcher
before_source, before_bound = bindings()
identity = importlib.reload(identity)
assert facade.TickFlowFetcher is old_class
after_source, after_bound = bindings()
for name in identity_names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
    assert after_bound[name].__globals__ is vars(facade)
    assert after_bound[name].__module__ == 'src.data_provider.tickflow_fetcher'
for name in boards_names + history_names + realtime_names:
    assert callable(getattr(facade.TickFlowFetcher, name))
assert callable(facade.TickFlowFetcher._extract_universe_symbols)
assert facade.TickFlowFetcher._extract_universe_symbols(
    {"symbols": ["600519.SH", "AAPL"]}
) == ["600519.SH", "AAPL"]
fetcher = facade.TickFlowFetcher(api_key="sk-test")
fetcher._client = _FakeClient(
    universe_data=[
        _quote("600103.SH", change_pct=0.02),
        _quote("002078.SZ", change_pct=0.04),
        _quote("000001.SZ", change_pct=-0.01),
    ],
    universe_list=[
        {"id": "CN_Equity_SW1_A", "name": "SW1轻工制造"},
        {"id": "CN_Equity_SW1_B", "name": "SW1轻工制造"},
        {"id": "CN_Equity_SW1_C", "name": "SW1银行"},
        {"id": "CN_Equity_SW2_D", "name": "SW2造纸"},
    ],
    universe_batch={
        "CN_Equity_SW1_A": {"symbols": ["600103.SH"]},
        "CN_Equity_SW1_B": {"symbols": ["600103.SH", "002078.SZ"]},
        "CN_Equity_SW1_C": {"symbols": ["000001.SZ"]},
    },
)
top, bottom = fetcher.get_sector_rankings(1)
assert top[0]["name"] == "轻工制造"
assert bottom[0]["name"] == "银行"
"""
    )


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.tickflow_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_stock_name(self):  # pragma: no cover - shape only
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


@pytest.mark.parametrize("code", ("AAPL", "HK00700", "00700.HK"))
def test_us_hk_codes_reject_before_quote_or_instrument_lookup(code) -> None:
    fetcher = _make_fetcher()
    quotes = _RecordingQuotes(payload=[_quote("600519.SH", name="Kweichow")])
    instruments = _RecordingInstruments(payload={"name": "ShouldNotRun"})
    fetcher._client = _IdentityClient(quotes=quotes, instruments=instruments)

    assert fetcher.get_stock_name(code) is None
    assert quotes.calls == []
    assert instruments.calls == []


@pytest.mark.parametrize("api_key", ("", "   "))
def test_empty_or_whitespace_api_key_returns_none_and_empty_list(api_key) -> None:
    fetcher = _make_fetcher(api_key=api_key)
    with patch.object(fetcher, "_build_client") as build:
        assert fetcher.get_stock_name("600519") is None
        frame = fetcher.get_stock_list()
    build.assert_not_called()
    assert list(frame.columns) == EMPTY_LIST_COLUMNS
    assert frame.empty


def test_quote_cache_hit_skips_quotes_get() -> None:
    fetcher = _make_fetcher()
    quotes = _RecordingQuotes(payload=[_quote("600519.SH", name="Kweichow")])
    instruments = _RecordingInstruments()
    fetcher._client = _IdentityClient(quotes=quotes, instruments=instruments)
    stored = fetcher._store_quotes([_quote("600519.SH", name="Kweichow")])
    assert stored == 1

    assert fetcher.get_stock_name("600519") == "Kweichow"
    assert quotes.calls == []
    assert instruments.calls == []


def test_get_stock_name_does_not_call_realtime_cache_ttl() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[_quote("600519.SH", name="Kweichow")])
    with patch.object(fetcher, "_get_realtime_cache_ttl") as ttl:
        assert fetcher.get_stock_name("600519") == "Kweichow"
    ttl.assert_not_called()


def test_quote_lookup_fail_open_falls_through_to_instrument() -> None:
    fetcher = _make_fetcher()
    quotes = _RecordingQuotes(error=RuntimeError("quote down"))
    instruments = _RecordingInstruments(payload={"name": "FromInstrument"})
    fetcher._client = _IdentityClient(quotes=quotes, instruments=instruments)
    with patch("src.data_provider.tickflow_fetcher.log_safe_exception") as logged:
        assert fetcher.get_stock_name("600519") == "FromInstrument"
    logged.assert_called_once()
    kwargs = logged.call_args.kwargs
    assert kwargs["error_code"] == "tickflow_quote_name_lookup_failed"
    assert kwargs["level"] == logging.DEBUG
    assert kwargs["context"] == {"symbol": "600519.SH"}
    assert instruments.calls == ["600519.SH"]


def test_nameless_quote_falls_through_to_instrument() -> None:
    fetcher = _make_fetcher()
    quotes = _RecordingQuotes(payload=[_quote("600519.SH")])
    instruments = _RecordingInstruments(payload={"short_name": "FromInstrument"})
    fetcher._client = _IdentityClient(quotes=quotes, instruments=instruments)

    assert fetcher.get_stock_name("600519") == "FromInstrument"
    assert instruments.calls == ["600519.SH"]


@pytest.mark.parametrize(
    "payload, expected",
    (
        ({"name": "FromName"}, "FromName"),
        ({"short_name": "FromShort"}, "FromShort"),
        ({"display_name": "FromDisplay"}, "FromDisplay"),
        ({"ext": {"name": "FromExt"}}, "FromExt"),
        ([{"name": "FromList"}], "FromList"),
        ([], None),
        ("not-a-dict", None),
        ({"name": "  Trimmed  "}, "Trimmed"),
    ),
)
def test_extract_instrument_name_fields(payload, expected) -> None:
    assert TickFlowFetcher._extract_instrument_name(payload) == expected


def test_instrument_fail_open_is_debug_and_returns_none() -> None:
    fetcher = _make_fetcher()
    quotes = _RecordingQuotes(payload=[_quote("600519.SH")])
    instruments = _RecordingInstruments(error=RuntimeError("instrument down"))
    fetcher._client = _IdentityClient(quotes=quotes, instruments=instruments)
    with patch("src.data_provider.tickflow_fetcher.log_safe_exception") as logged:
        assert fetcher.get_stock_name("600519") is None
    logged.assert_called_once()
    kwargs = logged.call_args.kwargs
    assert kwargs["error_code"] == "tickflow_instrument_lookup_failed"
    assert kwargs["level"] == logging.DEBUG
    assert kwargs["context"] == {"symbol": "600519.SH"}


def test_universe_permission_error_logs_info_and_returns_empty_frame() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(universe_data=_PermissionLikeError("universe forbidden"))
    with patch("src.data_provider.tickflow_fetcher.logger.info") as info:
        with patch("src.data_provider.tickflow_fetcher.log_safe_exception") as logged:
            frame = fetcher.get_stock_list()
    logged.assert_not_called()
    info.assert_called_once()
    assert "universe list is not available" in info.call_args.args[0]
    assert list(frame.columns) == EMPTY_LIST_COLUMNS
    assert frame.empty


def test_universe_other_error_logs_warning_and_returns_empty_frame() -> None:
    fetcher = _make_fetcher()
    universes = _RecordingUniverses(error=RuntimeError("network down"))
    fetcher._client = _IdentityClient(universes=universes)
    with patch("src.data_provider.tickflow_fetcher.log_safe_exception") as logged:
        frame = fetcher.get_stock_list()
    logged.assert_called_once()
    kwargs = logged.call_args.kwargs
    assert kwargs["error_code"] == "tickflow_stock_universe_lookup_failed"
    assert kwargs["level"] == logging.WARNING
    assert kwargs["context"] == {"universe": "CN_Equity_A"}
    assert list(frame.columns) == EMPTY_LIST_COLUMNS
    assert frame.empty


def test_stock_list_filters_non_cn_rows_and_keeps_blank_optional_fields() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(
        universe_data={
            "symbols": [
                {"symbol": "600519.SH", "name": "Kweichow"},
                {"code": "000001.SZ", "short_name": "Ping An"},
                "AAPL",
            ]
        }
    )

    frame = fetcher.get_stock_list()

    assert list(frame["code"]) == ["600519", "000001"]
    assert list(frame["name"]) == ["Kweichow", "Ping An"]
    assert list(frame["industry"]) == ["", ""]
    assert list(frame["area"]) == ["", ""]
    assert list(frame["market"]) == ["SH", "SZ"]


def test_universe_symbol_helpers_stay_on_the_facade_and_keep_class_lookup() -> None:
    entries = TickFlowFetcher._extract_universe_entries(
        {"symbols": [{"symbol": "600519.SH", "name": "Kweichow"}, "AAPL"]}
    )
    assert entries == [
        {"symbol": "600519.SH", "name": "Kweichow"},
        {"symbol": "AAPL", "name": ""},
    ]
    assert TickFlowFetcher._extract_universe_symbols(
        {"symbols": ["600519.SH", "AAPL"]}
    ) == ["600519.SH", "AAPL"]


def test_instance_to_tickflow_symbol_patch_is_visible_from_name() -> None:
    fetcher = _make_fetcher()
    quotes = _RecordingQuotes(payload=[_quote("600519.SH", name="Kweichow")])
    instruments = _RecordingInstruments()
    fetcher._client = _IdentityClient(quotes=quotes, instruments=instruments)
    with patch.object(fetcher, "_to_tickflow_symbol", return_value=None) as convert:
        assert fetcher.get_stock_name("600519") is None
    convert.assert_called_once_with("600519")
    assert quotes.calls == []
    assert instruments.calls == []


def test_instance_get_client_patch_is_visible_from_name_and_list() -> None:
    fetcher = _make_fetcher()
    quotes = _RecordingQuotes(payload=[_quote("600519.SH", name="Kweichow")])
    fetcher._client = _IdentityClient(quotes=quotes)
    with patch.object(fetcher, "_get_client", return_value=None) as get_client:
        assert fetcher.get_stock_name("600519") is None
        frame = fetcher.get_stock_list()
    assert get_client.call_count == 2
    assert quotes.calls == []
    assert list(frame.columns) == EMPTY_LIST_COLUMNS
    assert frame.empty


def test_stock_list_hits_patched_facade_normalize_stock_code() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(
        universe_data={"symbols": [{"symbol": "600519.SH", "name": "Kweichow"}]}
    )
    with patch(
        "src.data_provider.tickflow_fetcher.normalize_stock_code",
        return_value="SENTINEL",
    ) as normalize:
        with patch.object(fetcher, "_is_cn_equity_symbol", return_value=True):
            frame = fetcher.get_stock_list()
    normalize.assert_called()
    assert list(frame["code"]) == ["SENTINEL"]


def test_get_realtime_cache_ttl_stays_on_facade_and_is_unused_by_name_lookup() -> None:
    assert "_get_realtime_cache_ttl" in _facade_class_methods()
    with patch(
        "src.config.get_config",
        return_value=SimpleNamespace(realtime_cache_ttl=42),
    ):
        assert TickFlowFetcher._get_realtime_cache_ttl() == 42
    fetcher = _make_fetcher()
    fetcher._store_quotes([_quote("600519.SH", name="Kweichow")])
    with patch.object(
        TickFlowFetcher,
        "_get_realtime_cache_ttl",
        return_value=1,
    ) as ttl:
        assert fetcher.get_stock_name("600519") == "Kweichow"
    ttl.assert_not_called()
