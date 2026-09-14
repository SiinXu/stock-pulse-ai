# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, and characterization for the TickFlow realtime slice.

Issue #1068: ``get_realtime_quote``, ``_quote_to_unified_quote``, and
``_format_provider_timestamp`` moved into
``src/data_provider/tickflow_parts/realtime.py`` and are rebound onto the
public ``TickFlowFetcher`` class.
"""

from __future__ import annotations

import ast
import inspect
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.data_provider._facade_bind as shared_bind
import src.data_provider.tickflow_fetcher as tickflow_mod
import src.data_provider.tickflow_parts.facade_bind as tickflow_bind
import src.data_provider.tickflow_parts.prefetch as prefetch_mod
import src.data_provider.tickflow_parts.realtime as realtime_mod
from src.data_provider.realtime_types import RealtimeSource
from src.data_provider.tickflow_fetcher import TickFlowFetcher
from src.data_provider.tickflow_parts.facade_bind import _descriptor_function
from tests.test_tickflow_fetcher import _FakeClient, _quote

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "tickflow_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "tickflow_parts" / "realtime.py"

MOVED = (
    "get_realtime_quote",
    "_quote_to_unified_quote",
    "_format_provider_timestamp",
)

METHOD_SIGNATURES = {
    "get_realtime_quote": ["self", "stock_code"],
    "_quote_to_unified_quote": ["self", "stock_code", "quote"],
    "_format_provider_timestamp": ["value"],
}

FACADE_SIBLINGS = (
    "__init__",
    "close",
    "_build_client",
    "_get_client",
    "_to_tickflow_symbol",
    "_exchange_from_code",
    "_store_quotes",
    "_get_cached_quote",
    "_get_realtime_cache_ttl",
    "_safe_float",
    "_cn_lots_to_shares",
    "_ratio_to_percent",
    "_extract_name",
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

IDENTITY_BOUND = (
    "get_stock_name",
    "_extract_instrument_name",
    "get_stock_list",
)

DAILY_PREFETCH_BOUND = (
    "prefetch_daily_klines",
    "_iter_batch_frames",
)

REALTIME_PREFETCH_BOUND = (
    "prefetch_realtime_quotes",
)

FREE_NAMES = (
    "logger",
    "log_safe_exception",
    "normalize_stock_code",
    "UnifiedRealtimeQuote",
    "RealtimeSource",
    "datetime",
    "timezone",
)

MILLISECOND_TIMESTAMP = 1704153600000
MILLISECOND_ISO = datetime.fromtimestamp(1704153600.0, timezone.utc).isoformat()


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


def test_format_provider_timestamp_remains_a_staticmethod() -> None:
    descriptor = TickFlowFetcher.__dict__["_format_provider_timestamp"]
    assert isinstance(descriptor, staticmethod)
    assert inspect.isfunction(_descriptor_function(descriptor))


@pytest.mark.parametrize("name", ("get_realtime_quote", "_quote_to_unified_quote"))
def test_quote_methods_are_instance_methods(name) -> None:
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
    for name, source_descriptor in vars(realtime_mod._RealtimeMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(TickFlowFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == realtime_mod.__name__
    assert tuple(source_names) == realtime_mod.EXPECTED_REALTIME_METHOD_NAMES == MOVED


def test_tickflow_facade_bind_is_the_shared_helper() -> None:
    assert tickflow_bind.bind_methods_from_class is shared_bind.bind_methods_from_class
    assert realtime_mod.bind_methods_from_class is tickflow_bind.bind_methods_from_class


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
def test_sibling_helpers_stay_on_the_facade(sibling) -> None:
    """The moved bodies reach these through ``self``; moving any would widen the slice."""

    assert sibling in _facade_class_methods(), sibling


@pytest.mark.parametrize(
    "name",
    BOARDS_BOUND
    + HISTORY_BOUND
    + IDENTITY_BOUND
    + DAILY_PREFETCH_BOUND
    + REALTIME_PREFETCH_BOUND,
)
def test_other_bound_methods_stay_bound_and_are_not_live_function_defs(name) -> None:
    assert callable(getattr(TickFlowFetcher, name)), name
    assert name not in _facade_class_methods(), name


def test_realtime_prefetch_is_rebound_from_the_prefetch_owner() -> None:
    method = _descriptor_function(TickFlowFetcher.__dict__["prefetch_realtime_quotes"])
    source = _descriptor_function(
        vars(prefetch_mod._RealtimePrefetchMethods)["prefetch_realtime_quotes"]
    )
    assert method is not source
    assert method.__code__ is source.__code__
    assert method.__module__ == "src.data_provider.tickflow_fetcher"
    assert method.__qualname__ == "TickFlowFetcher.prefetch_realtime_quotes"
    assert method.__globals__ is vars(tickflow_mod)
    signature = inspect.signature(TickFlowFetcher.prefetch_realtime_quotes)
    assert list(signature.parameters) == ["self", "stock_codes", "batch_size"]
    assert signature.parameters["batch_size"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["batch_size"].default is None
    assert prefetch_mod.EXPECTED_REALTIME_PREFETCH_METHOD_NAMES == REALTIME_PREFETCH_BOUND
    tree = ast.parse(
        (REPO_ROOT / "src" / "data_provider" / "tickflow_parts" / "prefetch.py").read_text(
            encoding="utf-8"
        )
    )
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_RealtimePrefetchMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == {"prefetch_realtime_quotes"}
    assert prefetch_mod.EXPECTED_PREFETCH_METHOD_NAMES == (
        "prefetch_daily_klines",
        "_iter_batch_frames",
    )


def test_owner_module_does_not_trip_sibling_realtime_import_greps() -> None:
    """Sibling production-import guards substring-match these tokens."""

    text = OWNER_PATH.read_text(encoding="utf-8")
    assert "tushare_parts.realtime" not in text
    assert "efinance_parts.realtime" not in text
    assert "longbridge_parts.realtime" not in text
    assert "yfinance_parts.realtime" not in text


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


def test_get_realtime_quote_is_not_wrapped_in_tenacity() -> None:
    fetch = TickFlowFetcher.get_realtime_quote
    assert callable(fetch)
    assert getattr(fetch, "__wrapped__", None) is None


def test_fetcher_instantiates_after_binding() -> None:
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
                    "import src.data_provider.tickflow_parts.realtime as realtime",
                    "",
                    "realtime_names = realtime.EXPECTED_REALTIME_METHOD_NAMES",
                    "boards_names = ('get_main_indices', 'get_market_stats', 'get_sector_rankings')",
                    "history_names = ('_fetch_raw_data', '_normalize_data')",
                    "identity_names = ('get_stock_name', '_extract_instrument_name', 'get_stock_list')",
                    "daily_prefetch_names = ('prefetch_daily_klines', '_iter_batch_frames')",
                    "realtime_prefetch_names = ('prefetch_realtime_quotes',)",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    bound = {}",
                    "    owner = realtime._RealtimeMethods",
                    "    for name in realtime_names:",
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
                    "    sibling = boards_names + history_names + identity_names + daily_prefetch_names + realtime_prefetch_names",
                    "    for name in sibling:",
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


def test_reloading_realtime_rereads_and_rebinds_the_owner() -> None:
    _run_reload_contract(
        """
old_class = facade.TickFlowFetcher
before_source, before_bound = bindings()
realtime = importlib.reload(realtime)
assert facade.TickFlowFetcher is old_class
after_source, after_bound = bindings()
for name in realtime_names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
    assert after_bound[name].__globals__ is vars(facade)
    assert after_bound[name].__module__ == 'src.data_provider.tickflow_fetcher'
sibling = boards_names + history_names + identity_names + daily_prefetch_names + realtime_prefetch_names
for name in sibling:
    assert callable(getattr(facade.TickFlowFetcher, name))
"""
    )


def test_reloading_prefetch_rebinds_realtime_prefetch() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.tickflow_fetcher as facade",
                    "import src.data_provider.tickflow_parts.prefetch as prefetch",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    return descriptor",
                    "",
                    "name = 'prefetch_realtime_quotes'",
                    "before_source = descriptor_function(",
                    "    vars(prefetch._RealtimePrefetchMethods)[name]",
                    ")",
                    "before_bound = descriptor_function(",
                    "    vars(facade.TickFlowFetcher)[name]",
                    ")",
                    "prefetch = importlib.reload(prefetch)",
                    "after_source = descriptor_function(",
                    "    vars(prefetch._RealtimePrefetchMethods)[name]",
                    ")",
                    "after_bound = descriptor_function(",
                    "    vars(facade.TickFlowFetcher)[name]",
                    ")",
                    "assert after_source is not before_source",
                    "assert after_bound is not before_bound",
                    "assert after_bound.__code__ is after_source.__code__",
                    "assert after_bound.__globals__ is vars(facade)",
                    "assert after_bound.__module__ == 'src.data_provider.tickflow_fetcher'",
                    "assert callable(facade.TickFlowFetcher.prefetch_daily_klines)",
                    "assert callable(facade.TickFlowFetcher.get_stock_name)",
                    "assert callable(facade.TickFlowFetcher.get_realtime_quote)",
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.tickflow_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_realtime_quote(self):  # pragma: no cover - shape only
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


def test_realtime_quote_maps_ratios_to_percent_and_lots_to_shares() -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(symbols_data=[_quote("600519.SH", name="Kweichow")])
    fetcher._client = client

    quote = fetcher.get_realtime_quote("600519")

    assert client.quotes.calls[0]["symbols"] == ["600519.SH"]
    assert quote.source is RealtimeSource.TICKFLOW
    assert quote.code == "600519"
    assert quote.name == "Kweichow"
    assert quote.volume == 10000
    assert quote.change_pct == pytest.approx(10.0)
    assert quote.amplitude == pytest.approx(20.0)
    assert quote.turnover_rate == pytest.approx(3.0)
    assert quote.change_amount == pytest.approx(1.0)
    assert quote.provider_timestamp == MILLISECOND_ISO


def test_name_falls_back_from_ext_name_to_quote_name() -> None:
    raw = _quote("600519.SH")
    raw["name"] = "FromQuote"
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[raw])

    quote = fetcher.get_realtime_quote("600519")

    assert quote.name == "FromQuote"


def test_last_price_falls_back_to_price() -> None:
    raw = _quote("600519.SH")
    raw.pop("last_price")
    raw["price"] = 12.5
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[raw])

    quote = fetcher.get_realtime_quote("600519")

    assert quote.price == pytest.approx(12.5)


def test_missing_last_price_and_price_returns_none() -> None:
    raw = _quote("600519.SH")
    raw.pop("last_price")
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[raw])

    assert fetcher.get_realtime_quote("600519") is None


def test_change_amount_prefers_ext_then_derives_from_prev_close() -> None:
    with_ext = _quote("600519.SH")
    with_ext["ext"]["change_amount"] = 2.5
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[with_ext])
    assert fetcher.get_realtime_quote("600519").change_amount == pytest.approx(2.5)

    derived = _quote("600519.SH", last_price=11.0, prev_close=10.0)
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[derived])
    assert fetcher.get_realtime_quote("600519").change_amount == pytest.approx(1.0)


def test_change_pct_derives_from_prev_close_when_ext_ratio_missing() -> None:
    raw = _quote("600519.SH", last_price=11.0, prev_close=10.0)
    raw["ext"].pop("change_pct", None)
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[raw])

    quote = fetcher.get_realtime_quote("600519")

    assert quote.change_pct == pytest.approx(10.0)


@pytest.mark.parametrize("code", ("AAPL", "SPX", "QQQ", "BRK.B", "HK00700", "00700.HK"))
def test_us_hk_codes_reject_before_client(code) -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(symbols_data=[_quote("600519.SH")])
    fetcher._client = client

    assert fetcher.get_realtime_quote(code) is None
    assert client.quotes.calls == []


def test_cache_hit_skips_quotes_get() -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(symbols_data=[_quote("600519.SH", name="Kweichow")])
    fetcher._client = client
    stored = fetcher._store_quotes([_quote("600519.SH", name="Kweichow")])
    assert stored == 1

    quote = fetcher.get_realtime_quote("600519")

    assert quote is not None
    assert quote.name == "Kweichow"
    assert client.quotes.calls == []


def test_prefetch_realtime_quotes_warms_the_same_quote_cache() -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(symbols_data=[_quote("600519.SH")])
    fetcher._client = client

    assert fetcher.prefetch_realtime_quotes(["600519"]) == 1
    quote = fetcher.get_realtime_quote("600519")

    assert quote is not None
    assert len(client.quotes.calls) == 1


@pytest.mark.parametrize("api_key", ("", "   "))
def test_empty_or_whitespace_api_key_returns_none_without_build(api_key) -> None:
    fetcher = _make_fetcher(api_key=api_key)
    with patch.object(fetcher, "_build_client") as build:
        assert fetcher.get_realtime_quote("600519") is None
    build.assert_not_called()


def test_quotes_get_exception_is_fail_open_and_logged() -> None:
    class _BoomQuotes:
        def get(self, **kwargs):
            raise Exception("network down")

    class _BoomClient:
        def __init__(self):
            self.quotes = _BoomQuotes()

    fetcher = _make_fetcher()
    fetcher._client = _BoomClient()
    with patch("src.data_provider.tickflow_fetcher.log_safe_exception") as logged:
        assert fetcher.get_realtime_quote("600519") is None
    logged.assert_called_once()
    kwargs = logged.call_args.kwargs
    assert kwargs["error_code"] == "tickflow_realtime_quote_failed"
    assert kwargs["context"] == {"symbol": "600519.SH"}
    assert kwargs["level"] == logging.WARNING


def test_empty_quotes_after_store_returns_none() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[])

    assert fetcher.get_realtime_quote("600519") is None


def test_quote_mapping_hits_patched_facade_normalize_stock_code() -> None:
    fetcher = _make_fetcher()
    raw = _quote("600519.SH")
    with patch(
        "src.data_provider.tickflow_fetcher.normalize_stock_code",
        return_value="SENTINEL",
    ) as normalize:
        quote = fetcher._quote_to_unified_quote("600519", raw)
    normalize.assert_called_once_with("600519")
    assert quote.code == "SENTINEL"


def test_instance_to_tickflow_symbol_patch_is_visible_from_quote() -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(symbols_data=[_quote("600519.SH")])
    fetcher._client = client
    with patch.object(fetcher, "_to_tickflow_symbol", return_value=None) as convert:
        assert fetcher.get_realtime_quote("600519") is None
    convert.assert_called_once_with("600519")
    assert client.quotes.calls == []


def test_instance_get_client_patch_is_visible_from_quote() -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(symbols_data=[_quote("600519.SH")])
    fetcher._client = client
    with patch.object(fetcher, "_get_client", return_value=None) as get_client:
        assert fetcher.get_realtime_quote("600519") is None
    get_client.assert_called_once_with()
    assert client.quotes.calls == []


def test_get_realtime_cache_ttl_stays_on_facade_and_reads_config() -> None:
    assert "_get_realtime_cache_ttl" in _facade_class_methods()
    with patch(
        "src.config.get_config",
        return_value=SimpleNamespace(realtime_cache_ttl=42),
    ):
        assert TickFlowFetcher._get_realtime_cache_ttl() == 42


def test_get_realtime_cache_ttl_falls_back_on_exception() -> None:
    with patch("src.config.get_config", side_effect=RuntimeError("boom")):
        assert TickFlowFetcher._get_realtime_cache_ttl() == 600


@pytest.mark.parametrize("value", (None, ""))
def test_format_provider_timestamp_empty_is_none(value) -> None:
    assert TickFlowFetcher._format_provider_timestamp(value) is None


def test_format_provider_timestamp_non_numeric_string_is_kept() -> None:
    assert TickFlowFetcher._format_provider_timestamp("not-a-time") == "not-a-time"


@pytest.mark.parametrize("value", (0, -1, 0.0))
def test_format_provider_timestamp_non_positive_numeric_is_none(value) -> None:
    assert TickFlowFetcher._format_provider_timestamp(value) is None


def test_format_provider_timestamp_milliseconds_and_seconds() -> None:
    assert TickFlowFetcher._format_provider_timestamp(MILLISECOND_TIMESTAMP) == MILLISECOND_ISO
    assert TickFlowFetcher._format_provider_timestamp(1704153600) == MILLISECOND_ISO


def test_prefetch_realtime_quotes_swallows_batch_exceptions() -> None:
    class _BoomQuotes:
        def get(self, **kwargs):
            raise Exception("batch down")

    class _BoomClient:
        def __init__(self):
            self.quotes = _BoomQuotes()

    fetcher = _make_fetcher()
    fetcher._client = _BoomClient()
    with patch("src.data_provider.tickflow_fetcher.log_safe_exception") as logged:
        assert fetcher.prefetch_realtime_quotes(["600519"]) == 0
    logged.assert_called_once()
    assert logged.call_args.kwargs["error_code"] == "tickflow_batch_realtime_quote_failed"


def test_prefetch_realtime_quotes_missing_client_returns_zero() -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "_get_client", return_value=None) as get_client:
        with patch.object(fetcher, "_store_quotes") as store:
            assert fetcher.prefetch_realtime_quotes(["600519"]) == 0
    get_client.assert_called_once_with()
    store.assert_not_called()


def test_prefetch_realtime_quotes_empty_dedupe_returns_zero() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[_quote("600519.SH")])
    with patch.object(fetcher, "_dedupe_symbols", return_value=[]) as dedupe:
        with patch.object(fetcher, "_store_quotes") as store:
            assert fetcher.prefetch_realtime_quotes(["600519"]) == 0
    dedupe.assert_called_once()
    store.assert_not_called()
    assert fetcher._client.quotes.calls == []


def test_prefetch_realtime_quotes_store_quotes_patch_is_visible() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(symbols_data=[_quote("600519.SH")])
    with patch.object(fetcher, "_store_quotes", return_value=7) as store:
        assert fetcher.prefetch_realtime_quotes(["600519"]) == 7
    store.assert_called_once()


def test_get_stock_name_reads_and_writes_the_same_quote_cache() -> None:
    fetcher = _make_fetcher()
    client = _FakeClient(symbols_data=[_quote("600519.SH", name="Kweichow")])
    fetcher._client = client

    assert fetcher.get_stock_name("600519") == "Kweichow"
    quote = fetcher.get_realtime_quote("600519")

    assert quote is not None
    assert quote.name == "Kweichow"
    assert len(client.quotes.calls) == 1
