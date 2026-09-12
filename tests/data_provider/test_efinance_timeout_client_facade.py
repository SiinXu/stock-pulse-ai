# -*- coding: utf-8 -*-
"""Facade identity, clone, patch, reload, and bounded-wait tests for efinance timeout client.

Issue #1068: the module-level ``_ef_call_with_timeout`` helper moved into
``src/data_provider/efinance_parts/timeout_client.py`` and is cloned onto
the public ``efinance_fetcher`` module.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import src.data_provider.efinance_fetcher as efinance_mod
import src.data_provider.efinance_parts.timeout_client as timeout_client_mod
from src.data_provider.efinance_fetcher import EfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_parts" / "timeout_client.py"

MOVED = ("_ef_call_with_timeout",)
UNMOVED_MODULE_FUNCTIONS = (
    "_is_etf_code",
    "_build_eastmoney_etf_secid",
    "_is_us_code",
    "_classify_eastmoney_error",
)


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


def _facade_module_functions() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _make_fetcher() -> EfinanceFetcher:
    with patch(
        "src.data_provider.efinance_fetcher.get_config",
        return_value=SimpleNamespace(enable_eastmoney_patch=False),
    ):
        return EfinanceFetcher(sleep_min=0, sleep_max=0)


def _patch_facade_executor(result=None, result_side_effect=None):
    fake_future = MagicMock()
    if result_side_effect is not None:
        fake_future.result.side_effect = result_side_effect
    else:
        fake_future.result.return_value = result
    fake_executor = MagicMock()
    fake_executor.submit.return_value = fake_future
    fake_pool = MagicMock(return_value=fake_executor)
    return fake_pool, fake_executor, fake_future


def test_timeout_helper_remains_callable_on_the_facade_module() -> None:
    assert callable(efinance_mod._ef_call_with_timeout)


def test_timeout_helper_is_not_a_class_method() -> None:
    assert "_ef_call_with_timeout" not in _facade_class_methods()
    assert "_ef_call_with_timeout" not in EfinanceFetcher.__dict__


def test_module_and_qualname_still_point_at_the_facade() -> None:
    helper = efinance_mod._ef_call_with_timeout
    assert helper.__module__ == "src.data_provider.efinance_fetcher"
    assert helper.__qualname__ == "_ef_call_with_timeout"
    assert helper.__name__ == "_ef_call_with_timeout"


def test_signature_is_unchanged() -> None:
    signature = inspect.signature(efinance_mod._ef_call_with_timeout)
    assert list(signature.parameters) == ["func", "args", "timeout", "kwargs"]
    assert signature.parameters["timeout"].default is None
    assert signature.parameters["timeout"].kind is inspect.Parameter.KEYWORD_ONLY


def test_free_names_resolve_through_the_facade_globals() -> None:
    assert efinance_mod._ef_call_with_timeout.__globals__ is vars(efinance_mod)


def test_cloned_helper_is_not_the_owner_object() -> None:
    cloned = efinance_mod._ef_call_with_timeout
    owner = timeout_client_mod._ef_call_with_timeout
    assert cloned is not owner
    assert cloned.__code__ is owner.__code__


def test_owner_module_declares_exactly_the_slice() -> None:
    assert timeout_client_mod.EXPECTED_TIMEOUT_CLIENT_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_ef_call_with_timeout" in defined


def test_body_no_longer_lives_as_facade_module_function() -> None:
    defined = _facade_module_functions()
    assert "_ef_call_with_timeout" not in defined
    for name in UNMOVED_MODULE_FUNCTIONS:
        assert name in defined, name


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

    from src.data_provider._facade_bind import (
        _clone_facade_function as shared_clone,
        bind_methods_from_class as shared_bind,
    )
    from src.data_provider.efinance_parts.facade_bind import (
        _clone_facade_function,
        bind_methods_from_class,
    )

    assert bind_methods_from_class is shared_bind
    assert _clone_facade_function is shared_clone


def test_production_imports_stay_on_the_facade() -> None:
    src_root = REPO_ROOT / "src"
    offenders = []
    for path in src_root.rglob("*.py"):
        if "efinance_parts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "efinance_parts.timeout_client" in text and path.name != "efinance_fetcher.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_owner_reload_re_clones_onto_the_facade() -> None:
    importlib.reload(timeout_client_mod)
    helper = efinance_mod._ef_call_with_timeout
    assert callable(helper)
    assert helper.__globals__ is vars(efinance_mod)
    assert helper.__module__ == "src.data_provider.efinance_fetcher"
    assert helper.__qualname__ == "_ef_call_with_timeout"
    assert helper is not timeout_client_mod._ef_call_with_timeout
    assert helper.__code__ is timeout_client_mod._ef_call_with_timeout.__code__


def test_success_path_returns_func_result() -> None:
    fake_pool, fake_executor, fake_future = _patch_facade_executor(result="ok")
    original = efinance_mod.ThreadPoolExecutor
    try:
        efinance_mod.ThreadPoolExecutor = fake_pool
        result = efinance_mod._ef_call_with_timeout(lambda: "unused")
        assert result == "ok"
        fake_pool.assert_called_once_with(max_workers=1)
        fake_executor.submit.assert_called_once()
        fake_executor.shutdown.assert_called_once_with(wait=False)
    finally:
        efinance_mod.ThreadPoolExecutor = original


def test_none_timeout_uses_patched_facade_ef_call_timeout() -> None:
    fake_pool, _fake_executor, fake_future = _patch_facade_executor(result="ok")
    original_pool = efinance_mod.ThreadPoolExecutor
    original_timeout = efinance_mod._EF_CALL_TIMEOUT
    try:
        efinance_mod.ThreadPoolExecutor = fake_pool
        efinance_mod._EF_CALL_TIMEOUT = 5
        efinance_mod._ef_call_with_timeout(lambda: "x")
        fake_future.result.assert_called_once_with(timeout=5)
    finally:
        efinance_mod.ThreadPoolExecutor = original_pool
        efinance_mod._EF_CALL_TIMEOUT = original_timeout


def test_explicit_timeout_is_passed_to_future_result() -> None:
    fake_pool, _fake_executor, fake_future = _patch_facade_executor(result="ok")
    original = efinance_mod.ThreadPoolExecutor
    try:
        efinance_mod.ThreadPoolExecutor = fake_pool
        efinance_mod._ef_call_with_timeout(lambda: "x", timeout=2)
        fake_future.result.assert_called_once_with(timeout=2)
    finally:
        efinance_mod.ThreadPoolExecutor = original


def test_future_result_timeout_raises_through_to_the_caller() -> None:
    fake_pool, fake_executor, _fake_future = _patch_facade_executor(
        result_side_effect=efinance_mod.FuturesTimeoutError("timed out"),
    )
    original = efinance_mod.ThreadPoolExecutor
    try:
        efinance_mod.ThreadPoolExecutor = fake_pool
        with pytest.raises(efinance_mod.FuturesTimeoutError):
            efinance_mod._ef_call_with_timeout(lambda: None, timeout=1)
        fake_executor.shutdown.assert_called_once_with(wait=False)
    finally:
        efinance_mod.ThreadPoolExecutor = original


def test_shutdown_wait_false_runs_on_success() -> None:
    fake_pool, fake_executor, _fake_future = _patch_facade_executor(result="ok")
    original = efinance_mod.ThreadPoolExecutor
    try:
        efinance_mod.ThreadPoolExecutor = fake_pool
        efinance_mod._ef_call_with_timeout(lambda: "ok", timeout=1)
        fake_executor.shutdown.assert_called_once_with(wait=False)
    finally:
        efinance_mod.ThreadPoolExecutor = original


def test_source_implements_non_with_executor_construction() -> None:
    text = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for with_node in ast.walk(tree):
        if not isinstance(with_node, ast.With):
            continue
        for item in with_node.items:
            call = item.context_expr
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            assert name != "ThreadPoolExecutor"
    assert "ThreadPoolExecutor(max_workers=1)" in text
    assert "shutdown(wait=False)" in text
    assert "Do NOT use 'with ThreadPoolExecutor" in text


def test_info_body_still_reaches_a_patched_facade_helper() -> None:
    sentinel = object()
    original = efinance_mod._ef_call_with_timeout
    try:
        efinance_mod._ef_call_with_timeout = lambda *args, **kwargs: sentinel
        method = EfinanceFetcher.__dict__["get_base_info"]
        assert method.__globals__["_ef_call_with_timeout"]("fn") is sentinel
    finally:
        efinance_mod._ef_call_with_timeout = original


def test_fetcher_instantiates_after_timeout_client_bind() -> None:
    assert not EfinanceFetcher.__abstractmethods__
    fetcher = _make_fetcher()
    assert isinstance(fetcher, EfinanceFetcher)
    assert fetcher.sleep_min == 0
    assert fetcher.sleep_max == 0


def test_real_executor_success_with_explicit_timeout() -> None:
    result = efinance_mod._ef_call_with_timeout(lambda x, y=0: x + y, 1, y=2, timeout=1)
    assert result == 3
