# -*- coding: utf-8 -*-
"""Facade identity, clone, patch, reload, and category tests for efinance Eastmoney errors.

Issue #1068: the module-level ``_classify_eastmoney_error`` helper moved into
``src/data_provider/efinance_parts/eastmoney_errors.py`` and is cloned onto
the public ``efinance_fetcher`` module.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

import src.data_provider.efinance_fetcher as efinance_mod
import src.data_provider.efinance_parts.eastmoney_errors as eastmoney_errors_mod
from src.data_provider.efinance_fetcher import EfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_parts" / "eastmoney_errors.py"

MOVED = ("_classify_eastmoney_error",)


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


def test_classifier_remains_callable_on_the_facade_module() -> None:
    assert callable(efinance_mod._classify_eastmoney_error)


def test_classifier_is_not_a_class_method() -> None:
    assert "_classify_eastmoney_error" not in _facade_class_methods()
    assert "_classify_eastmoney_error" not in EfinanceFetcher.__dict__


def test_module_and_qualname_still_point_at_the_facade() -> None:
    helper = efinance_mod._classify_eastmoney_error
    assert helper.__module__ == "src.data_provider.efinance_fetcher"
    assert helper.__qualname__ == "_classify_eastmoney_error"
    assert helper.__name__ == "_classify_eastmoney_error"


def test_signature_is_unchanged() -> None:
    helper = efinance_mod._classify_eastmoney_error
    signature = inspect.signature(helper)
    assert list(signature.parameters) == ["exc"]
    assert "Exception" in str(signature.parameters["exc"].annotation)
    assert "Tuple[str, str]" in str(signature.return_annotation)


def test_free_names_resolve_through_the_facade_globals() -> None:
    assert efinance_mod._classify_eastmoney_error.__globals__ is vars(efinance_mod)
    assert "requests" in efinance_mod._classify_eastmoney_error.__globals__


def test_cloned_helper_is_not_the_owner_object() -> None:
    cloned = efinance_mod._classify_eastmoney_error
    owner = eastmoney_errors_mod._classify_eastmoney_error
    assert cloned is not owner
    assert cloned.__code__ is owner.__code__


def test_owner_module_declares_exactly_the_slice() -> None:
    assert eastmoney_errors_mod.EXPECTED_EASTMONEY_ERROR_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_classify_eastmoney_error" in defined


def test_body_no_longer_lives_as_facade_module_function() -> None:
    defined = _facade_module_functions()
    assert "_classify_eastmoney_error" not in defined


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
        if "efinance_parts.eastmoney_errors" in text and path.name != "efinance_fetcher.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_owner_module_does_not_trip_efinance_realtime_import_grep() -> None:
    """Sibling efinance production-import guards substring-match this token."""

    text = OWNER_PATH.read_text(encoding="utf-8")
    assert "efinance_parts.realtime" not in text


def test_owner_reload_re_clones_onto_the_facade() -> None:
    importlib.reload(eastmoney_errors_mod)
    helper = efinance_mod._classify_eastmoney_error
    assert callable(helper)
    assert helper.__globals__ is vars(efinance_mod)
    assert helper.__module__ == "src.data_provider.efinance_fetcher"
    assert helper.__qualname__ == "_classify_eastmoney_error"
    assert helper is not eastmoney_errors_mod._classify_eastmoney_error
    assert helper.__code__ is eastmoney_errors_mod._classify_eastmoney_error.__code__


@pytest.mark.parametrize(
    ("exc", "category"),
    [
        (ConnectionError("RemoteDisconnected"), "remote_disconnect"),
        (RuntimeError("remote end closed connection without response"), "remote_disconnect"),
        (RuntimeError("Connection aborted"), "remote_disconnect"),
        (RuntimeError("connection broken"), "remote_disconnect"),
        (RuntimeError("ProtocolError"), "remote_disconnect"),
        (TimeoutError("timed out"), "timeout"),
        (requests.exceptions.Timeout("timed out"), "timeout"),
        (requests.exceptions.ReadTimeout("Read timed out"), "timeout"),
        (requests.exceptions.ConnectTimeout("connect timed out"), "timeout"),
        (RuntimeError("readtimeout"), "timeout"),
        (RuntimeError("connecttimeout"), "timeout"),
        (RuntimeError("banned"), "rate_limit_or_anti_bot"),
        (RuntimeError("blocked"), "rate_limit_or_anti_bot"),
        (RuntimeError("频率过高"), "rate_limit_or_anti_bot"),
        (RuntimeError("rate limit"), "rate_limit_or_anti_bot"),
        (RuntimeError("too many requests"), "rate_limit_or_anti_bot"),
        (RuntimeError("HTTP 429"), "rate_limit_or_anti_bot"),
        (RuntimeError("访问限制"), "rate_limit_or_anti_bot"),
        (RuntimeError("forbidden"), "rate_limit_or_anti_bot"),
        (RuntimeError("HTTP 403"), "rate_limit_or_anti_bot"),
        (requests.exceptions.HTTPError("500"), "request_error"),
        (requests.exceptions.ConnectionError("unrelated"), "request_error"),
        (RuntimeError("plain failure"), "unknown_request_error"),
        (RuntimeError(""), "unknown_request_error"),
        (RuntimeError("ChunkedEncodingError"), "unknown_request_error"),
    ],
)
def test_classifier_categories_match_live_keyword_contract(exc: Exception, category: str) -> None:
    got_category, detail = efinance_mod._classify_eastmoney_error(exc)
    assert got_category == category
    assert detail == str(exc).strip()


def test_empty_message_keeps_empty_detail() -> None:
    category, detail = efinance_mod._classify_eastmoney_error(RuntimeError(""))
    assert category == "unknown_request_error"
    assert detail == ""


def test_timeout_isinstance_uses_facade_requests() -> None:
    class CustomTimeout(Exception):
        pass

    class CustomRequestException(Exception):
        pass

    fake_requests = SimpleNamespace(
        exceptions=SimpleNamespace(
            Timeout=CustomTimeout,
            RequestException=CustomRequestException,
        )
    )
    original = efinance_mod.requests
    try:
        efinance_mod.requests = fake_requests
        category, detail = efinance_mod._classify_eastmoney_error(CustomTimeout("boom"))
        assert category == "timeout"
        assert detail == "boom"
    finally:
        efinance_mod.requests = original


def test_build_history_failure_message_uses_patched_facade_classifier() -> None:
    original_classify = efinance_mod._classify_eastmoney_error
    try:
        efinance_mod._classify_eastmoney_error = lambda exc: ("sentinel_cat", "sentinel_detail")
        category, message = EfinanceFetcher._build_history_failure_message(
            "600519",
            "20240101",
            "20240131",
            RuntimeError("x"),
            1.25,
        )
        assert category == "sentinel_cat"
        assert "category=sentinel_cat" in message
        assert "detail=sentinel_detail" in message
    finally:
        efinance_mod._classify_eastmoney_error = original_classify


def test_fetcher_instantiates_after_eastmoney_errors_bind() -> None:
    assert not EfinanceFetcher.__abstractmethods__
    fetcher = _make_fetcher()
    assert isinstance(fetcher, EfinanceFetcher)
    assert fetcher.sleep_min == 0
    assert fetcher.sleep_max == 0
