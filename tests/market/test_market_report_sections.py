# -*- coding: utf-8 -*-
"""Characterization and unit tests for the extracted report-section helpers (#1085 step 9)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import src.market.analyzer as analyzer_mod
import src.market.report_sections as sections_mod
from src.market.analyzer import MarketAnalyzer

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = REPO_ROOT / "src" / "market" / "analyzer.py"
OWNER_PATH = REPO_ROOT / "src" / "market" / "report_sections.py"

# (analyzer method, module function, descriptor kind)
THREE = (
    ("_extract_report_title", "extract_report_title", staticmethod),
    ("_split_report_sections", "split_report_sections", classmethod),
    ("_insert_after_section", "insert_after_section", staticmethod),
)

METHOD_SIGNATURES = {
    "_extract_report_title": ["report"],
    "_split_report_sections": ["report"],
    "_insert_after_section": ["text", "heading_pattern", "block"],
}


@pytest.mark.parametrize("method_name,function_name,_kind", THREE)
def test_methods_remain_on_the_analyzer_facade(method_name, function_name, _kind) -> None:
    assert callable(getattr(MarketAnalyzer, method_name))
    assert callable(getattr(sections_mod, function_name))


@pytest.mark.parametrize("method_name,function_name,_kind", THREE)
def test_module_level_alias_is_re_exported(method_name, function_name, _kind) -> None:
    assert getattr(analyzer_mod, function_name) is getattr(sections_mod, function_name)


@pytest.mark.parametrize("method_name,_fn,kind", THREE)
def test_descriptor_kind_is_preserved(method_name, _fn, kind) -> None:
    """staticmethod vs classmethod is part of the public surface."""

    assert isinstance(vars(MarketAnalyzer)[method_name], kind)


@pytest.mark.parametrize("method_name,_fn,_kind", THREE)
def test_public_signatures_are_unchanged(method_name, _fn, _kind) -> None:
    signature = inspect.signature(getattr(MarketAnalyzer, method_name))
    assert list(signature.parameters) == METHOD_SIGNATURES[method_name]


def test_owner_module_exports_exactly_the_slice() -> None:
    assert set(sections_mod.__all__) == {fn for _m, fn, _k in THREE}


def test_owner_module_needs_no_owner_parameter() -> None:
    """These three are genuinely pure, unlike the other #1085 owner modules."""

    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            assert "owner" not in [a.arg for a in node.args.args], node.name


def test_owner_module_has_no_residual_self_or_cls() -> None:
    """A residual bare `self` shipped a NameError in step 8; pin it here too."""

    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    residual = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in ("self", "cls")
    }
    assert residual == set()


def test_owner_module_imports_every_module_it_uses() -> None:
    """`re` was missing on the first pass because `re.sub` is an Attribute,
    not a Name, so a Name-only free-symbol scan did not see it."""

    source = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    # Only roots that are never bound locally can be module references.
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.FunctionDef):
            bound.update(arg.arg for arg in node.args.args)
            bound.update(arg.arg for arg in node.args.kwonlyargs)
    attribute_roots = {
        node.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    assert "re" in imported
    assert attribute_roots - bound <= imported


def test_owner_module_does_not_import_the_analyzer() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any(module.endswith(".analyzer") for module in imported)


# --- Direct unit tests of the extracted functions -----------------------------------

REPORT = """# 2026-03-18 Market Review

## Section One
alpha

## Section Two
beta
"""


def test_extract_report_title_reads_the_first_heading() -> None:
    assert "2026-03-18" in sections_mod.extract_report_title(REPORT)


def test_extract_report_title_tolerates_an_empty_report() -> None:
    assert isinstance(sections_mod.extract_report_title(""), str)


def test_split_report_sections_returns_one_entry_per_heading() -> None:
    sections = sections_mod.split_report_sections(REPORT)
    assert isinstance(sections, list)
    assert all(isinstance(item, dict) for item in sections)


def test_split_report_sections_tolerates_a_report_without_headings() -> None:
    assert isinstance(sections_mod.split_report_sections("no headings here"), list)


def test_insert_after_section_places_the_block() -> None:
    result = sections_mod.insert_after_section(REPORT, r"## Section One", "INSERTED")
    assert "INSERTED" in result


def test_insert_after_section_is_a_noop_when_the_heading_is_absent() -> None:
    result = sections_mod.insert_after_section(REPORT, r"## Missing", "INSERTED")
    assert isinstance(result, str)


@pytest.mark.parametrize("method_name,function_name,_kind", THREE)
def test_facade_and_free_function_agree(method_name, function_name, _kind) -> None:
    args = {
        "_extract_report_title": (REPORT,),
        "_split_report_sections": (REPORT,),
        "_insert_after_section": (REPORT, r"## Section One", "X"),
    }[method_name]
    assert getattr(MarketAnalyzer, method_name)(*args) == getattr(
        sections_mod, function_name
    )(*args)
