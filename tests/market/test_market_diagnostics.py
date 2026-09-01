# -*- coding: utf-8 -*-
"""Characterization and unit tests for the extracted diagnostics helpers (Issue #1085 step 8)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.market.analyzer as analyzer_mod
import src.market.diagnostics as diagnostics_mod
from src.market.analyzer import MarketAnalyzer
from tests.market.test_market_degradation import _make_analyzer

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = REPO_ROOT / "src" / "market" / "analyzer.py"
OWNER_PATH = REPO_ROOT / "src" / "market" / "diagnostics.py"

TWO = (
    ("_generation_log_redaction_values", "generation_log_redaction_values"),
    ("_sanitize_generation_diagnostic", "sanitize_generation_diagnostic"),
)

METHOD_SIGNATURES = {
    "_generation_log_redaction_values": ["self", "error"],
    "_sanitize_generation_diagnostic": ["self", "error", "redaction_values"],
}


@pytest.mark.parametrize("method_name,function_name", TWO)
def test_methods_remain_on_the_analyzer_facade(method_name, function_name) -> None:
    assert callable(getattr(MarketAnalyzer, method_name))
    assert callable(getattr(diagnostics_mod, function_name))


@pytest.mark.parametrize("method_name,function_name", TWO)
def test_module_level_alias_is_re_exported(method_name, function_name) -> None:
    assert getattr(analyzer_mod, function_name) is getattr(diagnostics_mod, function_name)


@pytest.mark.parametrize("method_name,_fn", TWO)
def test_public_signatures_are_unchanged(method_name, _fn) -> None:
    signature = inspect.signature(getattr(MarketAnalyzer, method_name))
    assert list(signature.parameters) == METHOD_SIGNATURES[method_name]


def test_sanitize_keeps_redaction_values_keyword_only() -> None:
    """`redaction_values` must stay keyword-only, as it was before the move."""

    signature = inspect.signature(MarketAnalyzer._sanitize_generation_diagnostic)
    parameter = signature.parameters["redaction_values"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None


def test_delegator_forwards_redaction_values() -> None:
    """The regression this slice actually hit.

    Dropping `redaction_values` from the delegating call makes the sanitizer
    recompute the value set, which renders the exception snapshot a second
    time. The contract tests catch it as `render_count == 2`; this pins the
    delegation shape directly.
    """

    tree = ast.parse(ANALYZER_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MarketAnalyzer"
    )
    method = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_sanitize_generation_diagnostic"
    )
    call = method.body[0].value
    assert isinstance(call, ast.Call)
    assert [kw.arg for kw in call.keywords] == ["redaction_values"]


def test_owner_module_exports_exactly_the_slice() -> None:
    assert set(diagnostics_mod.__all__) == {fn for _m, fn in TWO}


def test_owner_module_does_not_import_the_analyzer() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any(module.endswith(".analyzer") for module in imported)


def test_owner_module_has_no_residual_self_reference() -> None:
    """A bare `self` (not `self.`) survived the first rename and raised NameError."""

    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "self"
    }
    assert names == set()


# --- Direct unit tests of the extracted functions -----------------------------------


def _owner(**overrides):
    """Minimal owner: sanitize calls back into the redaction helper, so the
    stub must provide it exactly as MarketAnalyzer does."""

    namespace = SimpleNamespace(config=SimpleNamespace(), analyzer=None)
    namespace._generation_log_redaction_values = (
        lambda error=None: diagnostics_mod.generation_log_redaction_values(
            namespace, error
        )
    )
    for key, value in overrides.items():
        setattr(namespace, key, value)
    return namespace


def test_redaction_values_returns_a_set_without_an_error() -> None:
    assert isinstance(diagnostics_mod.generation_log_redaction_values(_owner()), set)


def test_redaction_values_tolerates_an_arbitrary_exception() -> None:
    values = diagnostics_mod.generation_log_redaction_values(
        _owner(), RuntimeError("boom")
    )
    assert isinstance(values, set)


def test_sanitize_returns_a_string_for_an_arbitrary_exception() -> None:
    result = diagnostics_mod.sanitize_generation_diagnostic(
        _owner(), RuntimeError("boom")
    )
    assert isinstance(result, str)


def test_sanitize_accepts_precomputed_redaction_values() -> None:
    result = diagnostics_mod.sanitize_generation_diagnostic(
        _owner(), RuntimeError("boom"), redaction_values={"secret"}
    )
    assert isinstance(result, str)


def test_facade_and_free_function_agree() -> None:
    analyzer = _make_analyzer()
    error = RuntimeError("boom")
    assert analyzer._sanitize_generation_diagnostic(
        error
    ) == diagnostics_mod.sanitize_generation_diagnostic(analyzer, error)
