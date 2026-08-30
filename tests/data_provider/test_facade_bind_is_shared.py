# -*- coding: utf-8 -*-
"""One implementation of the ADR-006 rebind helpers across fetcher parts packages.

Issue #1068: `<provider>_parts/facade_bind.py` copies were byte-identical.
They are now re-exports of `src/data_provider/_facade_bind.py`, so a fix or a
behavior change lands once instead of N times.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import src.data_provider._facade_bind as shared

REPO_ROOT = Path(__file__).resolve().parents[2]
PROVIDER_ROOT = REPO_ROOT / "src" / "data_provider"

PARTS_PACKAGES = ("akshare_parts", "efinance_parts", "tushare_parts")
HELPERS = (
    "_clone_facade_descriptor",
    "_clone_facade_function",
    "_descriptor_function",
    "bind_methods_from_class",
)


def _import_shim(package: str):
    return __import__(
        f"src.data_provider.{package}.facade_bind", fromlist=["facade_bind"]
    )


@pytest.mark.parametrize("package", PARTS_PACKAGES)
@pytest.mark.parametrize("helper", HELPERS)
def test_shim_re_exports_the_shared_object(package, helper) -> None:
    """Identity, not equality — a re-implementation would fail this."""

    assert getattr(_import_shim(package), helper) is getattr(shared, helper)


@pytest.mark.parametrize("package", PARTS_PACKAGES)
def test_shim_defines_no_implementation_of_its_own(package) -> None:
    path = PROVIDER_ROOT / package / "facade_bind.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert defined == set(), f"{package} should re-export, not define: {defined}"


def test_no_further_copies_are_added() -> None:
    """Guard against the next provider slice pasting a fifth copy."""

    offenders = []
    for path in PROVIDER_ROOT.glob("*_parts/facade_bind.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(node, ast.FunctionDef) for node in tree.body):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == [], (
        "these packages define their own rebind helpers instead of re-exporting "
        f"src/data_provider/_facade_bind.py: {offenders}"
    )


def test_manager_parts_keeps_its_own_variant_on_purpose() -> None:
    """``manager_parts`` is not a duplicate: it resolves annotations by table.

    Consolidating it would change DataFetcherManager annotation behavior, which
    is out of scope here. This test records the reason so the difference is not
    mistaken for drift.
    """

    import src.data_provider.manager_parts.daily_cache_methods as manager_bind

    assert hasattr(manager_bind, "_resolve_annotations")
    assert manager_bind._clone_facade_function is not shared._clone_facade_function


@pytest.mark.parametrize(
    "module_name,class_name,method",
    [
        ("src.data_provider.akshare_fetcher", "AkshareFetcher", "get_main_indices"),
        ("src.data_provider.efinance_fetcher", "EfinanceFetcher", "get_main_indices"),
    ],
)
def test_existing_rebinds_still_point_at_their_facade(
    module_name, class_name, method
) -> None:
    """The consolidation must not disturb any already-bound method."""

    module = __import__(module_name, fromlist=[class_name])
    bound = getattr(module, class_name).__dict__[method]
    assert bound.__module__ == module_name
    assert bound.__qualname__ == f"{class_name}.{method}"
    assert bound.__globals__ is vars(module)
