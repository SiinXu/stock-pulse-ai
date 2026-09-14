# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, and characterization for TickFlow daily prefetch.

Issue #1068: ``prefetch_daily_klines`` and ``_iter_batch_frames`` moved into
``src/data_provider/tickflow_parts/prefetch.py`` and are rebound onto the
public ``TickFlowFetcher`` class.
"""

from __future__ import annotations

import ast
import inspect
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import src.data_provider._facade_bind as shared_bind
import src.data_provider.tickflow_fetcher as tickflow_mod
import src.data_provider.tickflow_parts.facade_bind as tickflow_bind
import src.data_provider.tickflow_parts.prefetch as prefetch_mod
from src.data_provider.base import DataFetchError
from src.data_provider.tickflow_fetcher import TickFlowFetcher
from src.data_provider.tickflow_parts.facade_bind import _descriptor_function
from tests.test_tickflow_fetcher import (
    _FakeClient,
    _PermissionLikeError,
    _daily_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "tickflow_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "tickflow_parts" / "prefetch.py"

MOVED = (
    "prefetch_daily_klines",
    "_iter_batch_frames",
)

METHOD_SIGNATURES = {
    "prefetch_daily_klines": ["self", "stock_codes", "days", "start_date", "end_date"],
    "_iter_batch_frames": ["batch_result"],
}

FACADE_SIBLINGS = (
    "_get_client",
    "_dedupe_symbols",
    "_capability_available",
    "_mark_capability",
    "_is_permission_error",
    "_daily_kline_count",
    "_date_to_ms",
    "_prepare_daily_frame",
    "_daily_cache_key",
    "_set_daily_cache",
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

IDENTITY_BOUND = (
    "get_stock_name",
    "_extract_instrument_name",
    "get_stock_list",
)

REALTIME_PREFETCH_BOUND = (
    "prefetch_realtime_quotes",
)

FREE_NAMES = (
    "logger",
    "log_safe_exception",
    "datetime",
    "timedelta",
    "_MAX_DAILY_PREFETCH_LOOKBACK_DAYS",
    "DataFetchError",
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


def _make_fetcher(*, api_key: str = "sk-test", **kwargs) -> TickFlowFetcher:
    return TickFlowFetcher(api_key=api_key, **kwargs)


# Sibling identity tests stub a client without close() and assert
# ``log_safe_exception`` was called once. Keep constructed fetchers alive so
# ``__del__`` cannot interleave a close-failed log into those assertions.
_LIVE_FETCHERS: list = []
_ORIGINAL_INIT = TickFlowFetcher.__init__


def _keep_fetcher_alive(self, *args, **kwargs):
    _ORIGINAL_INIT(self, *args, **kwargs)
    _LIVE_FETCHERS.append(self)


TickFlowFetcher.__init__ = _keep_fetcher_alive  # type: ignore[method-assign]


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(TickFlowFetcher, name))


def test_iter_batch_frames_remains_a_staticmethod() -> None:
    descriptor = TickFlowFetcher.__dict__["_iter_batch_frames"]
    assert isinstance(descriptor, staticmethod)
    assert inspect.isfunction(_descriptor_function(descriptor))


def test_prefetch_daily_klines_is_an_instance_method() -> None:
    descriptor = TickFlowFetcher.__dict__["prefetch_daily_klines"]
    assert not isinstance(descriptor, (staticmethod, classmethod))
    assert inspect.isfunction(_descriptor_function(descriptor))


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


def test_keyword_only_defaults_are_unchanged() -> None:
    signature = inspect.signature(TickFlowFetcher.prefetch_daily_klines)
    assert signature.parameters["days"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["days"].default == 30
    assert signature.parameters["start_date"].default is None
    assert signature.parameters["end_date"].default is None


def test_source_and_facade_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(prefetch_mod._PrefetchMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(TickFlowFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == prefetch_mod.__name__
    assert tuple(source_names) == prefetch_mod.EXPECTED_PREFETCH_METHOD_NAMES == MOVED


def test_tickflow_facade_bind_is_the_shared_helper() -> None:
    assert tickflow_bind.bind_methods_from_class is shared_bind.bind_methods_from_class
    assert prefetch_mod.bind_methods_from_class is tickflow_bind.bind_methods_from_class
    assert prefetch_mod.bind_prefetch_methods_facade.__code__ is not None


def test_owner_module_declares_exactly_the_slice() -> None:
    assert prefetch_mod.EXPECTED_PREFETCH_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_PrefetchMethods"
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
    BOARDS_BOUND + HISTORY_BOUND + REALTIME_BOUND + IDENTITY_BOUND + REALTIME_PREFETCH_BOUND,
)
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


def test_prefetch_daily_klines_is_not_wrapped_in_tenacity() -> None:
    method = TickFlowFetcher.prefetch_daily_klines
    assert callable(method)
    assert getattr(method, "__wrapped__", None) is None


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
                    "import src.data_provider.tickflow_parts.prefetch as prefetch",
                    "from tests.test_tickflow_fetcher import _FakeClient, _daily_rows",
                    "",
                    "prefetch_names = prefetch.EXPECTED_PREFETCH_METHOD_NAMES",
                    "boards_names = ('get_main_indices', 'get_market_stats', 'get_sector_rankings')",
                    "history_names = ('_fetch_raw_data', '_normalize_data')",
                    "realtime_names = ('get_realtime_quote', '_quote_to_unified_quote', '_format_provider_timestamp')",
                    "identity_names = ('get_stock_name', '_extract_instrument_name', 'get_stock_list')",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    bound = {}",
                    "    owner = prefetch._PrefetchMethods",
                    "    for name in prefetch_names:",
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
                    "    sibling = boards_names + history_names + realtime_names + identity_names",
                    "    for name in sibling:",
                    "        assert callable(getattr(facade.TickFlowFetcher, name))",
                    "    assert callable(facade.TickFlowFetcher.prefetch_realtime_quotes)",
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


def test_reloading_prefetch_rereads_and_rebinds_the_owner() -> None:
    _run_reload_contract(
        """
old_class = facade.TickFlowFetcher
before_source, before_bound = bindings()
prefetch = importlib.reload(prefetch)
assert facade.TickFlowFetcher is old_class
after_source, after_bound = bindings()
for name in prefetch_names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
    assert after_bound[name].__globals__ is vars(facade)
    assert after_bound[name].__module__ == 'src.data_provider.tickflow_fetcher'
sibling = boards_names + history_names + realtime_names + identity_names
for name in sibling:
    assert callable(getattr(facade.TickFlowFetcher, name))
assert callable(facade.TickFlowFetcher.prefetch_realtime_quotes)
fetcher = facade.TickFlowFetcher(api_key="sk-test")
fetcher._client = _FakeClient(
    daily_data=__import__('pandas').DataFrame(),
    batch_data={"600519.SH": _daily_rows("600519.SH")},
)
cached = fetcher.prefetch_daily_klines(
    ["600519"], start_date="2024-01-01", end_date="2024-01-03"
)
assert cached == 1
frame = fetcher.get_stock_list()
assert list(frame.columns) == ["code", "name", "industry", "area", "market"]
"""
    )


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.tickflow_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def prefetch_daily_klines(self):  # pragma: no cover - shape only
            return 0

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial,
            _Target,
            vars(tickflow_mod),
            expected_names=MOVED,
        )


def test_disabled_batch_daily_returns_zero_without_client() -> None:
    fetcher = _make_fetcher(batch_daily_enabled=False)
    fetcher._client = _FakeClient(batch_data={"600519.SH": _daily_rows("600519.SH")})
    with patch.object(fetcher, "_get_client") as get_client:
        assert fetcher.prefetch_daily_klines(["600519"], start_date="2024-01-01", end_date="2024-01-03") == 0
    get_client.assert_not_called()
    assert fetcher._client.klines.batch_calls == []


def test_unavailable_batch_capability_returns_zero() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(batch_data={"600519.SH": _daily_rows("600519.SH")})
    with patch.object(fetcher, "_capability_available", return_value=False) as available:
        assert fetcher.prefetch_daily_klines(["600519"], start_date="2024-01-01", end_date="2024-01-03") == 0
    available.assert_called_once_with("batch_daily")
    assert fetcher._client.klines.batch_calls == []


@pytest.mark.parametrize("days", ("nope", object(), None))
def test_invalid_days_logs_info_and_returns_zero(days) -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient()
    with patch("src.data_provider.tickflow_fetcher.logger.info") as info:
        assert fetcher.prefetch_daily_klines(["600519"], days=days) == 0
    info.assert_called_once()
    assert "days is invalid" in info.call_args.args[0]
    assert fetcher._client.klines.batch_calls == []


@pytest.mark.parametrize("days", (0, -1))
def test_non_positive_days_logs_info_and_returns_zero(days) -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient()
    with patch("src.data_provider.tickflow_fetcher.logger.info") as info:
        assert fetcher.prefetch_daily_klines(["600519"], days=days) == 0
    info.assert_called_once()
    assert "days must be positive" in info.call_args.args[0]
    assert fetcher._client.klines.batch_calls == []


def test_missing_client_returns_zero() -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "_get_client", return_value=None) as get_client:
        assert fetcher.prefetch_daily_klines(["600519"], start_date="2024-01-01", end_date="2024-01-03") == 0
    get_client.assert_called_once_with()


def test_empty_deduped_symbols_returns_zero() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient()
    with patch.object(fetcher, "_dedupe_symbols", return_value=[]) as dedupe:
        assert fetcher.prefetch_daily_klines(["600519"], start_date="2024-01-01", end_date="2024-01-03") == 0
    dedupe.assert_called_once()
    assert fetcher._client.klines.batch_calls == []


def test_default_window_uses_today_and_capped_lookback() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(batch_data={"600519.SH": _daily_rows("600519.SH")})

    class _FixedDateTime:
        @staticmethod
        def now():
            return datetime(2026, 9, 13)

        strptime = staticmethod(datetime.strptime)

    with patch("src.data_provider.tickflow_fetcher.datetime", _FixedDateTime):
        with patch.object(fetcher, "_date_to_ms", side_effect=lambda value, end_of_day=False: f"{value}:{end_of_day}"):
            fetcher.prefetch_daily_klines(["600519"], days=30)

    call = fetcher._client.klines.batch_calls[0]
    assert call["start_time"] == "2026-07-15:False"
    assert call["end_time"] == "2026-09-13:True"


def test_lookback_caps_at_max_daily_prefetch_days() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(batch_data={"600519.SH": _daily_rows("600519.SH")})

    class _FixedDateTime:
        @staticmethod
        def now():
            return datetime(2026, 9, 13)

        strptime = staticmethod(datetime.strptime)

    with patch("src.data_provider.tickflow_fetcher.datetime", _FixedDateTime):
        with patch(
            "src.data_provider.tickflow_fetcher._MAX_DAILY_PREFETCH_LOOKBACK_DAYS",
            10,
        ):
            with patch.object(
                fetcher,
                "_date_to_ms",
                side_effect=lambda value, end_of_day=False: f"{value}:{end_of_day}",
            ):
                fetcher.prefetch_daily_klines(["600519"], days=400)

    call = fetcher._client.klines.batch_calls[0]
    assert call["start_time"] == "2026-09-03:False"
    assert call["end_time"] == "2026-09-13:True"


def test_permission_error_marks_capability_and_skips_failed_log() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(batch_error=_PermissionLikeError("batch forbidden"))
    with patch.object(fetcher, "_mark_capability") as mark:
        with patch("src.data_provider.tickflow_fetcher.logger.info") as info:
            with patch("src.data_provider.tickflow_fetcher.log_safe_exception") as logged:
                cached = fetcher.prefetch_daily_klines(
                    ["600519"], start_date="2024-01-01", end_date="2024-01-03"
                )
    assert cached == 0
    mark.assert_called_once_with("batch_daily", False)
    logged.assert_not_called()
    messages = [call.args[0] for call in info.call_args_list]
    assert any("batch daily K-line is not available" in message for message in messages)
    complete = [
        call
        for call in info.call_args_list
        if "batch daily prefetch complete" in call.args[0]
    ]
    assert complete
    assert complete[0].args[1:4] == (0, 1, 1)


def test_other_exception_logs_warning_and_continues() -> None:
    fetcher = _make_fetcher(batch_size=1)
    fetcher._client = _FakeClient(
        batch_data={
            "600519.SH": _daily_rows("600519.SH"),
            "000001.SZ": _daily_rows("000001.SZ"),
        }
    )
    original_batch = fetcher._client.klines.batch

    def _batch(symbols, **kwargs):
        if list(symbols) == ["600519.SH"]:
            raise RuntimeError("network down")
        return original_batch(symbols, **kwargs)

    fetcher._client.klines.batch = _batch
    with patch("src.data_provider.tickflow_fetcher.log_safe_exception") as logged:
        cached = fetcher.prefetch_daily_klines(
            ["600519", "000001"],
            start_date="2024-01-01",
            end_date="2024-01-03",
        )
    assert cached == 1
    logged.assert_called_once()
    kwargs = logged.call_args.kwargs
    assert kwargs["error_code"] == "tickflow_batch_daily_kline_failed"
    assert kwargs["level"] == logging.WARNING


def test_prepare_data_fetch_error_skips_symbol() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(batch_data={"600519.SH": _daily_rows("600519.SH")})
    with patch.object(fetcher, "_prepare_daily_frame", side_effect=DataFetchError("truncated")):
        with patch.object(fetcher, "_set_daily_cache") as store:
            cached = fetcher.prefetch_daily_klines(
                ["600519"], start_date="2024-01-01", end_date="2024-01-03"
            )
    assert cached == 0
    store.assert_not_called()


def test_empty_prepared_frame_is_skipped() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(batch_data={"600519.SH": _daily_rows("600519.SH")})
    with patch.object(fetcher, "_prepare_daily_frame", return_value=pd.DataFrame()):
        with patch.object(fetcher, "_set_daily_cache") as store:
            cached = fetcher.prefetch_daily_klines(
                ["600519"], start_date="2024-01-01", end_date="2024-01-03"
            )
    assert cached == 0
    store.assert_not_called()


def test_success_marks_capability_and_stores_cache() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(batch_data={"600519.SH": _daily_rows("600519.SH")})
    with patch.object(fetcher, "_mark_capability") as mark:
        with patch.object(fetcher, "_daily_cache_key", return_value="cache-key") as key:
            with patch.object(fetcher, "_set_daily_cache") as store:
                cached = fetcher.prefetch_daily_klines(
                    ["600519"], start_date="2024-01-01", end_date="2024-01-03"
                )
    assert cached == 1
    mark.assert_called_with("batch_daily", True)
    key.assert_called_once_with("600519.SH", "2024-01-01", "2024-01-03")
    assert store.call_count == 1
    assert store.call_args.args[0] == "cache-key"


def test_instance_patches_remain_visible_from_prefetch() -> None:
    fetcher = _make_fetcher()
    fetcher._client = _FakeClient(batch_data={"600519.SH": _daily_rows("600519.SH")})
    with patch.object(fetcher, "_get_client", wraps=fetcher._get_client) as get_client:
        with patch.object(fetcher, "_dedupe_symbols", wraps=fetcher._dedupe_symbols) as dedupe:
            with patch.object(
                fetcher, "_capability_available", wraps=fetcher._capability_available
            ) as available:
                with patch.object(fetcher, "_daily_kline_count", wraps=fetcher._daily_kline_count) as count:
                    with patch.object(fetcher, "_date_to_ms", wraps=fetcher._date_to_ms) as to_ms:
                        with patch.object(
                            fetcher, "_prepare_daily_frame", wraps=fetcher._prepare_daily_frame
                        ) as prepare:
                            cached = fetcher.prefetch_daily_klines(
                                ["600519"],
                                start_date="2024-01-01",
                                end_date="2024-01-03",
                            )
    assert cached == 1
    get_client.assert_called()
    dedupe.assert_called()
    available.assert_called_with("batch_daily")
    count.assert_called()
    to_ms.assert_called()
    prepare.assert_called()


def test_iter_batch_frames_dict_uppercases_symbols() -> None:
    frame = _daily_rows("600519.SH")
    pairs = list(TickFlowFetcher._iter_batch_frames({"600519.sh": frame}))
    assert len(pairs) == 1
    assert pairs[0][0] == "600519.SH"
    assert pairs[0][1] is frame


def test_iter_batch_frames_dataframe_groups_by_symbol() -> None:
    frame = pd.concat(
        [_daily_rows("600519.SH"), _daily_rows("000001.SZ")],
        ignore_index=True,
    )
    pairs = dict(TickFlowFetcher._iter_batch_frames(frame))
    assert set(pairs) == {"600519.SH", "000001.SZ"}
    assert list(pairs["600519.SH"]["symbol"].unique()) == ["600519.SH"]
    assert list(pairs["000001.SZ"]["symbol"].unique()) == ["000001.SZ"]


def test_iter_batch_frames_dataframe_without_symbol_is_empty() -> None:
    frame = pd.DataFrame([{"open": 1}])
    assert list(TickFlowFetcher._iter_batch_frames(frame)) == []


def test_iter_batch_frames_list_skips_non_dicts_and_blank_symbols() -> None:
    rows = [
        {"symbol": "600519.SH", "close": 1},
        "skip-me",
        {"symbol": "", "close": 2},
        {"close": 3},
        {"symbol": "600519.sh", "close": 4},
        12,
    ]
    pairs = list(TickFlowFetcher._iter_batch_frames(rows))
    assert len(pairs) == 1
    symbol, frame = pairs[0]
    assert symbol == "600519.SH"
    assert list(frame["close"]) == [1, 4]
