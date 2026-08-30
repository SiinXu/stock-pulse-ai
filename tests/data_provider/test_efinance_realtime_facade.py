# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, cache, and reload tests for the efinance stock quote.

Issue #1068: ``get_realtime_quote`` moved into
``src/data_provider/efinance_parts/realtime.py`` and is rebound onto the public
``EfinanceFetcher`` class. Everything a caller or test could observe must be
unchanged. ``_realtime_cache`` stays on the facade so ``get_market_stats``
shares it. ETF codes still dispatch through ``_get_etf_realtime_quote``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
import textwrap
import time
import types
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

import src.data_provider.efinance_fetcher as efinance_mod
import src.data_provider.efinance_parts.etf as etf_mod
import src.data_provider.efinance_parts.realtime as realtime_mod
from src.data_provider.efinance_fetcher import EfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_parts" / "realtime.py"
MOVED = ("get_realtime_quote",)
# Stock-path methods that stay on the facade after the realtime slice.
#
# ``get_sector_rankings``, ``get_market_stats``, and ``get_main_indices`` were
# in this list until the market-board slice moved them into
# ``efinance_parts.market_boards``, matching the domain that
# ``akshare_parts.market_boards`` already owns. They are asserted from
# ``test_efinance_market_boards_facade`` now.
UNMOVED_FACADE_METHODS = (
    "_fetch_raw_data",
    "_fetch_stock_data",
    "_normalize_data",
    "get_base_info",
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


def _make_fetcher() -> EfinanceFetcher:
    with patch(
        "src.data_provider.efinance_fetcher.get_config",
        return_value=SimpleNamespace(enable_eastmoney_patch=False),
    ):
        return EfinanceFetcher(sleep_min=0, sleep_max=0)


def _quote_frame(code: str = "600519") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "股票代码": [code],
            "股票名称": ["贵州茅台"],
            "最新价": [1700.0],
            "涨跌幅": [1.2],
            "涨跌额": [20.0],
            "成交量": [1000],
            "成交额": [1_700_000.0],
            "换手率": [0.5],
            "振幅": [2.0],
            "最高": [1710.0],
            "最低": [1680.0],
            "开盘": [1690.0],
            "量比": [1.1],
            "市盈率": [30.0],
            "总市值": [2e12],
            "流通市值": [2e12],
            "昨收": [1680.0],
        }
    )


@pytest.fixture
def restore_realtime_cache():
    cache = efinance_mod._realtime_cache
    previous = dict(cache)
    try:
        yield cache
    finally:
        cache.clear()
        cache.update(previous)


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    method = getattr(EfinanceFetcher, name)
    assert callable(method)
    assert method is not None


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    """ADR-006: the rebound body must not advertise the owner module."""

    method = EfinanceFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.efinance_fetcher", name
    assert method.__qualname__ == f"EfinanceFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    """The patch seam that makes ``patch("...efinance_fetcher.X")`` still work."""

    method = EfinanceFetcher.__dict__[name]
    assert method.__globals__ is vars(efinance_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(EfinanceFetcher, name))
    assert list(signature.parameters) == ["self", "stock_code"]


def test_source_and_facade_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(realtime_mod._RealtimeMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(EfinanceFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == realtime_mod.__name__
    assert tuple(source_names) == realtime_mod.EXPECTED_REALTIME_METHOD_NAMES == MOVED


def test_moved_body_ast_matches_between_source_and_facade() -> None:
    source_tree = ast.parse(
        textwrap.dedent(
            inspect.getsource(realtime_mod._RealtimeMethods.get_realtime_quote)
        )
    )
    facade_tree = ast.parse(
        textwrap.dedent(inspect.getsource(EfinanceFetcher.get_realtime_quote))
    )
    assert ast.dump(source_tree, include_attributes=False) == ast.dump(
        facade_tree, include_attributes=False
    )


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
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EfinanceFetcher"
    )
    defined = {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in MOVED:
        assert name not in defined, name
    for name in UNMOVED_FACADE_METHODS:
        assert name in defined, name


def test_module_level_helpers_and_cache_stay_on_the_facade() -> None:
    """No helper or cache object travels with the slice."""

    assert isinstance(efinance_mod._realtime_cache, dict)
    assert realtime_mod._realtime_cache is None
    for helper in (
        "_is_etf_code",
        "_ef_call_with_timeout",
        "get_realtime_circuit_breaker",
        "safe_float",
        "safe_int",
    ):
        assert getattr(efinance_mod, helper) is not None, helper


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("efinance_fetcher" in module for module in imported)


def test_production_imports_stay_on_the_facade() -> None:
    src_root = REPO_ROOT / "src"
    offenders = []
    for path in src_root.rglob("*.py"):
        if "efinance_parts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "efinance_parts.realtime" in text and path.name != "efinance_fetcher.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_moved_body_uses_patched_facade_timeout_helper(restore_realtime_cache) -> None:
    """Real facade-global patch: the rebound body must see module dict writes."""

    fetcher = _make_fetcher()
    restore_realtime_cache["data"] = None
    restore_realtime_cache["timestamp"] = 0
    frame = _quote_frame()
    calls: list[object] = []

    def fake_timeout(fn, *args, **kwargs):
        calls.append(fn)
        return frame

    class Open:
        def is_available(self, key):
            return True

        def record_success(self, key):
            return None

        def record_failure(self, *args):
            raise AssertionError("successful quote must not trip the breaker")

    fake_quotes = object()
    fake_efinance = types.SimpleNamespace(
        stock=types.SimpleNamespace(get_realtime_quotes=fake_quotes)
    )
    original_timeout = efinance_mod._ef_call_with_timeout
    original_breaker = efinance_mod.get_realtime_circuit_breaker
    try:
        efinance_mod._ef_call_with_timeout = fake_timeout
        efinance_mod.get_realtime_circuit_breaker = lambda: Open()
        with patch.dict(sys.modules, {"efinance": fake_efinance}):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                quote = fetcher.get_realtime_quote("600519")
    finally:
        efinance_mod._ef_call_with_timeout = original_timeout
        efinance_mod.get_realtime_circuit_breaker = original_breaker

    assert calls == [fake_quotes]
    assert quote is not None
    assert quote.code == "600519"
    assert quote.price == 1700.0
    assert restore_realtime_cache["data"] is frame


def test_quote_and_market_stats_share_the_facade_cache_object(
    restore_realtime_cache,
) -> None:
    fetcher = _make_fetcher()
    frame = _quote_frame()
    restore_realtime_cache["data"] = frame
    restore_realtime_cache["timestamp"] = time.time()
    assert efinance_mod._realtime_cache is restore_realtime_cache
    fake_efinance = types.SimpleNamespace(
        stock=types.SimpleNamespace(
            get_realtime_quotes=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("shared cache must not hit the API")
            )
        )
    )
    with patch.dict(sys.modules, {"efinance": fake_efinance}):
        with patch.object(fetcher, "_set_random_user_agent"), patch.object(
            fetcher, "_enforce_rate_limit"
        ):
            with patch(
                "src.data_provider.efinance_fetcher._ef_call_with_timeout"
            ) as call:
                quote = fetcher.get_realtime_quote("600519")
                stats = fetcher.get_market_stats()
                call.assert_not_called()
    assert quote is not None
    assert quote.price == 1700.0
    assert stats is not None
    assert stats["up_count"] >= 1
    assert efinance_mod._realtime_cache is restore_realtime_cache


def test_etf_codes_dispatch_through_etf_realtime_quote() -> None:
    fetcher = _make_fetcher()
    sentinel = object()
    with patch.object(
        fetcher, "_get_etf_realtime_quote", return_value=sentinel
    ) as etf_quote:
        with patch("src.data_provider.efinance_fetcher._ef_call_with_timeout") as call:
            result = fetcher.get_realtime_quote("510300")
    etf_quote.assert_called_once_with("510300")
    call.assert_not_called()
    assert result is sentinel


def test_facade_global_etf_classifier_patch_reroutes_stock_codes() -> None:
    fetcher = _make_fetcher()
    original = efinance_mod._is_etf_code
    try:
        efinance_mod._is_etf_code = lambda code: True
        with patch.object(
            fetcher, "_get_etf_realtime_quote", return_value="etf-path"
        ) as etf_quote:
            with patch(
                "src.data_provider.efinance_fetcher._ef_call_with_timeout"
            ) as call:
                result = fetcher.get_realtime_quote("600519")
        etf_quote.assert_called_once_with("600519")
        call.assert_not_called()
        assert result == "etf-path"
    finally:
        efinance_mod._is_etf_code = original


def test_open_circuit_skips_timeout_helper() -> None:
    class Closed:
        def is_available(self, key):
            assert key == "efinance"
            return False

        def record_success(self, *args):
            raise AssertionError("open circuit must not record success")

        def record_failure(self, *args):
            raise AssertionError("open circuit must not record failure")

    fake_efinance = types.SimpleNamespace(
        stock=types.SimpleNamespace(get_realtime_quotes=object())
    )
    fetcher = _make_fetcher()
    with patch.dict(sys.modules, {"efinance": fake_efinance}):
        with patch(
            "src.data_provider.efinance_fetcher.get_realtime_circuit_breaker",
            return_value=Closed(),
        ):
            with patch(
                "src.data_provider.efinance_fetcher._ef_call_with_timeout"
            ) as call:
                assert fetcher.get_realtime_quote("600519") is None
                call.assert_not_called()


def test_timeout_records_circuit_failure_and_returns_none(
    restore_realtime_cache,
) -> None:
    restore_realtime_cache["data"] = None
    restore_realtime_cache["timestamp"] = 0
    recorded: list[tuple[str, str]] = []

    class Open:
        def is_available(self, key):
            return True

        def record_success(self, key):
            raise AssertionError("timeout must not record success")

        def record_failure(self, key, reason):
            recorded.append((key, reason))

    fake_efinance = types.SimpleNamespace(
        stock=types.SimpleNamespace(get_realtime_quotes=object())
    )
    fetcher = _make_fetcher()
    with patch.dict(sys.modules, {"efinance": fake_efinance}):
        with patch(
            "src.data_provider.efinance_fetcher.get_realtime_circuit_breaker",
            return_value=Open(),
        ):
            with patch(
                "src.data_provider.efinance_fetcher._ef_call_with_timeout",
                side_effect=FuturesTimeoutError(),
            ):
                with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                    fetcher, "_enforce_rate_limit"
                ):
                    assert fetcher.get_realtime_quote("600519") is None
    assert recorded == [("efinance", "timeout")]


def test_expected_names_mismatch_is_an_import_error() -> None:
    """An incomplete rebind must fail loudly instead of leaving ``None``."""

    from src.data_provider.efinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def not_the_quote(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial,
            _Target,
            vars(efinance_mod),
            expected_names=realtime_mod.EXPECTED_REALTIME_METHOD_NAMES,
        )


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.efinance_fetcher as facade",
                    "import src.data_provider.efinance_parts.etf as etf",
                    "import src.data_provider.efinance_parts.market_boards as boards",
                    "import src.data_provider.efinance_parts.realtime as realtime",
                    "",
                    "etf_names = etf.EXPECTED_ETF_METHOD_NAMES",
                    "realtime_names = realtime.EXPECTED_REALTIME_METHOD_NAMES",
                    "boards_names = boards.EXPECTED_MARKET_BOARD_METHOD_NAMES",
                    "owners = (",
                    "    (etf_names, lambda: etf._EtfMethods),",
                    "    (realtime_names, lambda: realtime._RealtimeMethods),",
                    "    (boards_names, lambda: boards._MarketBoardsMethods),",
                    ")",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    bound = {}",
                    "    for names, owner in owners:",
                    "        for name in names:",
                    "            source[name] = descriptor_function(vars(owner())[name])",
                    "            bound[name] = descriptor_function(",
                    "                vars(facade.EfinanceFetcher)[name]",
                    "            )",
                    "            assert bound[name] is not source[name]",
                    "            assert bound[name].__code__ is source[name].__code__",
                    "            assert bound[name].__globals__ is vars(facade)",
                    "            assert bound[name].__module__ == (",
                    "                'src.data_provider.efinance_fetcher'",
                    "            )",
                    "            assert bound[name].__qualname__ == (",
                    "                f'EfinanceFetcher.{name}'",
                    "            )",
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


def test_reloading_realtime_rereads_and_rebinds_both_owners() -> None:
    _run_reload_contract(
        """
old_class = facade.EfinanceFetcher
before_source, before_bound = bindings()
realtime = importlib.reload(realtime)
assert facade.EfinanceFetcher is old_class
after_source, after_bound = bindings()
assert after_source['get_realtime_quote'] is not before_source['get_realtime_quote']
assert after_bound['get_realtime_quote'] is not before_bound['get_realtime_quote']
assert after_bound['get_realtime_quote'].__code__ is after_source['get_realtime_quote'].__code__
for name in (*etf_names, *boards_names):
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
    assert after_bound[name].__globals__ is vars(facade)
"""
    )


def test_reloading_etf_also_rebinds_realtime() -> None:
    _run_reload_contract(
        """
old_class = facade.EfinanceFetcher
before_source, before_bound = bindings()
etf = importlib.reload(etf)
assert facade.EfinanceFetcher is old_class
after_source, after_bound = bindings()
for name in etf_names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
assert after_bound['get_realtime_quote'] is not before_bound['get_realtime_quote']
assert after_bound['get_realtime_quote'].__globals__ is vars(facade)
assert after_bound['get_realtime_quote'].__code__ is after_source['get_realtime_quote'].__code__
for name in boards_names:
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
"""
    )


def test_reloading_boards_also_rebinds_realtime() -> None:
    _run_reload_contract(
        """
old_class = facade.EfinanceFetcher
before_source, before_bound = bindings()
boards = importlib.reload(boards)
assert facade.EfinanceFetcher is old_class
after_source, after_bound = bindings()
for name in boards_names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
assert after_bound['get_realtime_quote'] is not before_bound['get_realtime_quote']
assert after_bound['get_realtime_quote'].__code__ is after_source['get_realtime_quote'].__code__
for name in etf_names:
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
"""
    )


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(realtime_mod)
    method = EfinanceFetcher.__dict__["get_realtime_quote"]
    assert method.__globals__ is vars(efinance_mod)
    assert method.__qualname__ == "EfinanceFetcher.get_realtime_quote"
    for name in etf_mod.EXPECTED_ETF_METHOD_NAMES:
        etf_method = EfinanceFetcher.__dict__[name]
        assert etf_method.__globals__ is vars(efinance_mod), name
        assert etf_method.__qualname__ == f"EfinanceFetcher.{name}", name
