# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, and behavioral tests for efinance info.

Issue #1068: per-symbol info lookups and enhanced-data orchestration moved into
``src/data_provider/efinance_parts/info.py`` and are rebound onto the public
``EfinanceFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

import src.data_provider.efinance_fetcher as efinance_mod
import src.data_provider.efinance_parts.info as info_mod
from src.data_provider.efinance_fetcher import EfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_parts" / "info.py"

MOVED = (
    "get_base_info",
    "get_belong_board",
    "get_enhanced_data",
)

METHOD_SIGNATURES = {
    "get_base_info": ["self", "stock_code"],
    "get_belong_board": ["self", "stock_code"],
    "get_enhanced_data": ["self", "stock_code", "days"],
}


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


def _stub_efinance(**stock_attrs):
    stock = SimpleNamespace(**stock_attrs)
    return {"efinance": SimpleNamespace(stock=stock)}


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
    assert EfinanceFetcher.__dict__[name].__globals__ is vars(efinance_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(EfinanceFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]
    if name == "get_enhanced_data":
        assert signature.parameters["days"].default == 60


def test_source_and_facade_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(info_mod._InfoMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(EfinanceFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == info_mod.__name__
    assert tuple(source_names) == info_mod.EXPECTED_INFO_METHOD_NAMES == MOVED


def test_owner_module_declares_exactly_the_slice() -> None:
    assert info_mod.EXPECTED_INFO_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_InfoMethods"
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


def test_production_imports_stay_on_the_facade() -> None:
    src_root = REPO_ROOT / "src"
    offenders = []
    for path in src_root.rglob("*.py"):
        if "efinance_parts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "efinance_parts.info" in text and path.name != "efinance_fetcher.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(info_mod)
    for name in MOVED:
        method = EfinanceFetcher.__dict__[name]
        assert method.__globals__ is vars(efinance_mod), name
        assert method.__qualname__ == f"EfinanceFetcher.{name}", name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.efinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_base_info(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial,
            _Target,
            vars(efinance_mod),
            expected_names=MOVED,
        )


def test_fetcher_instantiates_with_patch_disabled() -> None:
    assert not EfinanceFetcher.__abstractmethods__
    fetcher = _make_fetcher()
    assert isinstance(fetcher, EfinanceFetcher)
    assert fetcher.sleep_min == 0
    assert fetcher.sleep_max == 0


def test_rate_limit_helpers_stay_on_the_facade() -> None:
    for helper in ("_set_random_user_agent", "_enforce_rate_limit"):
        assert helper in EfinanceFetcher.__dict__, helper
        assert inspect.isfunction(EfinanceFetcher.__dict__[helper])


def test_get_base_info_series_becomes_dict() -> None:
    fetcher = _make_fetcher()
    series = pd.Series({"市盈率": 10.0, "市净率": 2.0})
    original = efinance_mod._ef_call_with_timeout

    def fake_timeout(*args, **kwargs):
        return series

    try:
        efinance_mod._ef_call_with_timeout = fake_timeout
        with patch.dict("sys.modules", _stub_efinance(get_base_info=object())):
            with patch.object(fetcher, "_set_random_user_agent") as ua, patch.object(
                fetcher, "_enforce_rate_limit"
            ) as rate:
                result = fetcher.get_base_info("600519")
        ua.assert_called_once()
        rate.assert_called_once()
        assert result == {"市盈率": 10.0, "市净率": 2.0}
        assert (
            EfinanceFetcher.__dict__["get_base_info"].__globals__["_ef_call_with_timeout"]
            is fake_timeout
        )
    finally:
        efinance_mod._ef_call_with_timeout = original


def test_get_base_info_none_and_empty_frame_return_none() -> None:
    fetcher = _make_fetcher()
    original = efinance_mod._ef_call_with_timeout
    try:
        efinance_mod._ef_call_with_timeout = lambda *a, **k: None
        with patch.dict("sys.modules", _stub_efinance(get_base_info=object())):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                assert fetcher.get_base_info("600519") is None

        efinance_mod._ef_call_with_timeout = lambda *a, **k: pd.DataFrame()
        with patch.dict("sys.modules", _stub_efinance(get_base_info=object())):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                assert fetcher.get_base_info("600519") is None
    finally:
        efinance_mod._ef_call_with_timeout = original


def test_get_base_info_nonempty_frame_uses_first_row() -> None:
    fetcher = _make_fetcher()
    frame = pd.DataFrame({"市盈率": [11.0, 12.0], "市净率": [1.5, 1.6]})
    original = efinance_mod._ef_call_with_timeout
    try:
        efinance_mod._ef_call_with_timeout = lambda *a, **k: frame
        with patch.dict("sys.modules", _stub_efinance(get_base_info=object())):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                result = fetcher.get_base_info("600519")
        assert result == {"市盈率": 11.0, "市净率": 1.5}
    finally:
        efinance_mod._ef_call_with_timeout = original


def test_get_base_info_generic_exception_returns_none() -> None:
    fetcher = _make_fetcher()
    with patch.dict("sys.modules", _stub_efinance(get_base_info=object())):
        with patch(
            "src.data_provider.efinance_fetcher._ef_call_with_timeout",
            side_effect=RuntimeError("boom"),
        ):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                with patch(
                    "src.data_provider.efinance_fetcher.log_safe_exception"
                ) as logged:
                    assert fetcher.get_base_info("600519") is None
    logged.assert_called_once()
    assert logged.call_args.kwargs["error_code"] == "efinance_stock_base_info_failed"


def test_get_base_info_timeout_is_not_a_dedicated_branch() -> None:
    fetcher = _make_fetcher()
    with patch.dict("sys.modules", _stub_efinance(get_base_info=object())):
        with patch(
            "src.data_provider.efinance_fetcher._ef_call_with_timeout",
            side_effect=FuturesTimeoutError(),
        ):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                with patch(
                    "src.data_provider.efinance_fetcher.log_safe_exception"
                ) as logged:
                    assert fetcher.get_base_info("600519") is None
    logged.assert_called_once()
    assert logged.call_args.kwargs["error_code"] == "efinance_stock_base_info_failed"


def test_get_belong_board_returns_nonempty_frame() -> None:
    fetcher = _make_fetcher()
    frame = pd.DataFrame({"板块名称": ["白酒", "贵州"]})
    original = efinance_mod._ef_call_with_timeout
    try:
        efinance_mod._ef_call_with_timeout = lambda *a, **k: frame
        with patch.dict("sys.modules", _stub_efinance(get_belong_board=object())):
            with patch.object(fetcher, "_set_random_user_agent") as ua, patch.object(
                fetcher, "_enforce_rate_limit"
            ) as rate:
                result = fetcher.get_belong_board("600519")
        ua.assert_called_once()
        rate.assert_called_once()
        assert result is frame
    finally:
        efinance_mod._ef_call_with_timeout = original


def test_get_belong_board_empty_returns_none() -> None:
    fetcher = _make_fetcher()
    original = efinance_mod._ef_call_with_timeout
    try:
        efinance_mod._ef_call_with_timeout = lambda *a, **k: pd.DataFrame()
        with patch.dict("sys.modules", _stub_efinance(get_belong_board=object())):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                assert fetcher.get_belong_board("600519") is None
    finally:
        efinance_mod._ef_call_with_timeout = original


def test_get_belong_board_timeout_skips_membership_error() -> None:
    fetcher = _make_fetcher()
    with patch.dict("sys.modules", _stub_efinance(get_belong_board=object())):
        with patch(
            "src.data_provider.efinance_fetcher._ef_call_with_timeout",
            side_effect=FuturesTimeoutError(),
        ):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                with patch(
                    "src.data_provider.efinance_fetcher.log_safe_exception"
                ) as logged:
                    assert fetcher.get_belong_board("600519") is None
    logged.assert_not_called()


def test_get_belong_board_generic_exception_returns_none() -> None:
    fetcher = _make_fetcher()
    with patch.dict("sys.modules", _stub_efinance(get_belong_board=object())):
        with patch(
            "src.data_provider.efinance_fetcher._ef_call_with_timeout",
            side_effect=RuntimeError("boom"),
        ):
            with patch.object(fetcher, "_set_random_user_agent"), patch.object(
                fetcher, "_enforce_rate_limit"
            ):
                with patch(
                    "src.data_provider.efinance_fetcher.log_safe_exception"
                ) as logged:
                    assert fetcher.get_belong_board("600519") is None
    logged.assert_called_once()
    assert logged.call_args.kwargs["error_code"] == "efinance_stock_board_membership_failed"


def test_get_enhanced_data_calls_instance_lookups() -> None:
    fetcher = _make_fetcher()
    daily = pd.DataFrame({"close": [1.0]})
    quote = object()
    info = {"pe": 1}
    board = pd.DataFrame({"板块": ["白酒"]})
    with patch.object(fetcher, "get_daily_data", return_value=daily) as daily_m:
        with patch.object(fetcher, "get_realtime_quote", return_value=quote) as quote_m:
            with patch.object(fetcher, "get_base_info", return_value=info) as info_m:
                with patch.object(
                    fetcher, "get_belong_board", return_value=board
                ) as board_m:
                    result = fetcher.get_enhanced_data("600519", days=30)
    daily_m.assert_called_once_with("600519", days=30)
    quote_m.assert_called_once_with("600519")
    info_m.assert_called_once_with("600519")
    board_m.assert_called_once_with("600519")
    assert result == {
        "code": "600519",
        "daily_data": daily,
        "realtime_quote": quote,
        "base_info": info,
        "belong_board": board,
    }


def test_get_enhanced_data_swallows_daily_exception() -> None:
    fetcher = _make_fetcher()
    with patch.object(
        fetcher, "get_daily_data", side_effect=RuntimeError("daily boom")
    ):
        with patch.object(fetcher, "get_realtime_quote", return_value="q"):
            with patch.object(fetcher, "get_base_info", return_value="i"):
                with patch.object(fetcher, "get_belong_board", return_value="b"):
                    with patch(
                        "src.data_provider.efinance_fetcher.log_safe_exception"
                    ) as logged:
                        result = fetcher.get_enhanced_data("600519")
    assert result["code"] == "600519"
    assert result["daily_data"] is None
    assert result["realtime_quote"] == "q"
    assert result["base_info"] == "i"
    assert result["belong_board"] == "b"
    logged.assert_called_once()
    assert logged.call_args.kwargs["error_code"] == "efinance_daily_data_failed"
