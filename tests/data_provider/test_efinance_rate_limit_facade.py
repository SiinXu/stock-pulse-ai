# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, and behavioral tests for efinance rate-limit helpers.

Issue #1068: UA rotation, request pacing, and history-failure formatting moved
into ``src/data_provider/efinance_parts/rate_limit.py`` and are rebound onto
the public ``EfinanceFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.data_provider.efinance_fetcher as efinance_mod
import src.data_provider.efinance_parts.rate_limit as rate_limit_mod
from src.data_provider.efinance_fetcher import EfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_parts" / "rate_limit.py"

MOVED = (
    "_build_history_failure_message",
    "_set_random_user_agent",
    "_enforce_rate_limit",
)

STATICMETHODS = ("_build_history_failure_message",)

INSTANCE_METHODS = (
    "_set_random_user_agent",
    "_enforce_rate_limit",
)

METHOD_SIGNATURES = {
    "_build_history_failure_message": [
        "stock_code",
        "beg_date",
        "end_date",
        "exc",
        "elapsed",
        "is_etf",
    ],
    "_set_random_user_agent": ["self"],
    "_enforce_rate_limit": ["self"],
}


def _descriptor(name: str):
    return EfinanceFetcher.__dict__[name]


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


def _facade_body(name: str):
    return _descriptor_function(_descriptor(name))


def _make_fetcher() -> EfinanceFetcher:
    with patch(
        "src.data_provider.efinance_fetcher.get_config",
        return_value=SimpleNamespace(enable_eastmoney_patch=False),
    ):
        return EfinanceFetcher(sleep_min=0, sleep_max=0)


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


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(EfinanceFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = _descriptor(name)
    assert method.__module__ == "src.data_provider.efinance_fetcher", name
    assert method.__qualname__ == f"EfinanceFetcher.{name}", name


@pytest.mark.parametrize("name", INSTANCE_METHODS)
def test_instance_method_free_names_resolve_through_the_facade_globals(name) -> None:
    assert _descriptor(name).__globals__ is vars(efinance_mod), name


@pytest.mark.parametrize("name", STATICMETHODS)
def test_staticmethod_free_names_resolve_through_the_facade_globals(name) -> None:
    method = _descriptor(name)
    assert isinstance(method, staticmethod), name
    assert method.__func__.__globals__ is vars(efinance_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(EfinanceFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]
    if name == "_build_history_failure_message":
        assert signature.parameters["is_etf"].default is False


def test_history_failure_helper_remains_a_staticmethod() -> None:
    assert isinstance(_descriptor("_build_history_failure_message"), staticmethod)
    assert not isinstance(_descriptor("_set_random_user_agent"), staticmethod)
    assert not isinstance(_descriptor("_enforce_rate_limit"), staticmethod)
    assert not isinstance(_descriptor("_set_random_user_agent"), classmethod)
    assert not isinstance(_descriptor("_enforce_rate_limit"), classmethod)


def test_source_and_facade_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(rate_limit_mod._RateLimitMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(EfinanceFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == rate_limit_mod.__name__
    assert tuple(source_names) == rate_limit_mod.EXPECTED_RATE_LIMIT_METHOD_NAMES == MOVED


def test_owner_module_declares_exactly_the_slice() -> None:
    assert rate_limit_mod.EXPECTED_RATE_LIMIT_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_RateLimitMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


def test_remaining_facade_class_methods_are_only_init() -> None:
    assert _facade_class_methods() == {"__init__"}


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
        if "efinance_parts.rate_limit" in text and path.name != "efinance_fetcher.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(rate_limit_mod)
    for name in MOVED:
        method = _descriptor(name)
        body = _facade_body(name)
        assert body.__globals__ is vars(efinance_mod), name
        assert method.__qualname__ == f"EfinanceFetcher.{name}", name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.efinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def _set_random_user_agent(self):  # pragma: no cover - shape only
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


def test_set_random_user_agent_uses_patched_facade_user_agents() -> None:
    fetcher = _make_fetcher()
    sentinel = "SENTINEL-UA-" + ("X" * 60)
    original = efinance_mod.USER_AGENTS
    try:
        efinance_mod.USER_AGENTS = [sentinel]
        with patch.object(efinance_mod.random, "choice", wraps=efinance_mod.random.choice) as choice:
            fetcher._set_random_user_agent()
        choice.assert_called_once_with([sentinel])
    finally:
        efinance_mod.USER_AGENTS = original


def test_set_random_user_agent_swallows_generic_exception() -> None:
    fetcher = _make_fetcher()
    with patch.object(efinance_mod.random, "choice", side_effect=RuntimeError("boom")):
        with patch.object(efinance_mod, "log_safe_exception") as logged:
            fetcher._set_random_user_agent()
    logged.assert_called_once()
    args, kwargs = logged.call_args
    assert args[0] is efinance_mod.logger
    assert args[1] == "Efinance user agent selection failed"
    assert isinstance(args[2], RuntimeError)
    assert kwargs["error_code"] == "efinance_user_agent_selection_failed"
    assert kwargs["level"] == logging.DEBUG


def test_enforce_rate_limit_skips_extra_sleep_when_last_request_is_none() -> None:
    fetcher = _make_fetcher()
    fetcher._last_request_time = None
    with patch.object(efinance_mod.time, "sleep") as extra_sleep:
        with patch.object(fetcher, "random_sleep") as jitter:
            with patch.object(efinance_mod.time, "time", return_value=123.0):
                fetcher._enforce_rate_limit()
    extra_sleep.assert_not_called()
    jitter.assert_called_once_with(0, 0)
    assert fetcher._last_request_time == 123.0


def test_enforce_rate_limit_extra_sleeps_when_interval_is_short() -> None:
    fetcher = _make_fetcher()
    fetcher.sleep_min = 1.5
    fetcher.sleep_max = 3.0
    fetcher._last_request_time = 100.0
    with patch.object(efinance_mod.time, "sleep") as extra_sleep:
        with patch.object(fetcher, "random_sleep") as jitter:
            with patch.object(efinance_mod.time, "time", side_effect=[100.5, 102.0]):
                fetcher._enforce_rate_limit()
    extra_sleep.assert_called_once()
    slept = extra_sleep.call_args[0][0]
    assert slept == pytest.approx(1.0)
    jitter.assert_called_once_with(1.5, 3.0)
    assert fetcher._last_request_time == 102.0


def test_build_history_failure_message_uses_patched_facade_classifier() -> None:
    original_classify = efinance_mod._classify_eastmoney_error
    original_endpoint = efinance_mod.EASTMONEY_HISTORY_ENDPOINT
    try:
        efinance_mod._classify_eastmoney_error = lambda exc: ("sentinel_cat", "sentinel_detail")
        efinance_mod.EASTMONEY_HISTORY_ENDPOINT = "sentinel.endpoint"
        category, message = EfinanceFetcher._build_history_failure_message(
            "600519",
            "20240101",
            "20240131",
            RuntimeError("x"),
            1.25,
            is_etf=True,
        )
        assert category == "sentinel_cat"
        assert "endpoint=sentinel.endpoint" in message
        assert "stock_code=600519" in message
        assert "market_type=ETF" in message
        assert "range=20240101~20240131" in message
        assert "category=sentinel_cat" in message
        assert "error_type=RuntimeError" in message
        assert "elapsed=1.25s" in message
        assert "detail=sentinel_detail" in message

        _, stock_message = EfinanceFetcher._build_history_failure_message(
            "600519",
            "20240101",
            "20240131",
            RuntimeError("x"),
            0.5,
        )
        assert "market_type=stock" in stock_message
    finally:
        efinance_mod._classify_eastmoney_error = original_classify
        efinance_mod.EASTMONEY_HISTORY_ENDPOINT = original_endpoint


def test_info_body_still_reaches_rebound_rate_limit_helpers() -> None:
    fetcher = _make_fetcher()
    original = efinance_mod._ef_call_with_timeout
    try:
        efinance_mod._ef_call_with_timeout = lambda *a, **k: None
        with patch.dict(
            "sys.modules",
            {"efinance": SimpleNamespace(stock=SimpleNamespace(get_base_info=object()))},
        ):
            with patch.object(fetcher, "_set_random_user_agent") as ua, patch.object(
                fetcher, "_enforce_rate_limit"
            ) as rate:
                assert fetcher.get_base_info("600519") is None
        ua.assert_called_once()
        rate.assert_called_once()
    finally:
        efinance_mod._ef_call_with_timeout = original
