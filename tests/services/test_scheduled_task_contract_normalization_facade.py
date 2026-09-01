# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the contract slice.

The contract normalization and schema-fence recovery methods moved into
``src/services/scheduled_task_parts/contract_normalization.py`` and are rebound
onto ``ScheduledTaskService``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import src.services.scheduled_task_service as service_mod
import src.services.scheduled_task_parts.contract_normalization as contract_mod
from src.services.scheduled_task_service import ScheduledTaskService

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "services" / "scheduled_task_service.py"
OWNER_PATH = (
    REPO_ROOT
    / "src"
    / "services"
    / "scheduled_task_parts"
    / "contract_normalization.py"
)

MOVED = (
    "_schema_is_supported",
    "_normalize_contract",
    "_recover_supported_schema_fences",
)

# Pre-slice shapes, read from origin/main before the move.
METHOD_SIGNATURES = {
    "_schema_is_supported": ["schema_version"],
    "_normalize_contract": ["contract"],
    "_recover_supported_schema_fences": ["self", "now"],
}
DESCRIPTOR_KINDS = {
    "_schema_is_supported": staticmethod,
    "_normalize_contract": staticmethod,
}

# Reached through `self`; all stay on the facade.
FACADE_SIBLINGS = ("_run_item", "_validate_persisted_task")

# The three domains this package already owned; binding must not disturb them.
PRE_EXISTING_BOUND = (
    "_conflict_wait_fields",
    "_running_admission_fields",
    "_dispatch_failure_fields",
)


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_service(name) -> None:
    assert callable(getattr(ScheduledTaskService, name))


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    descriptor = vars(ScheduledTaskService)[name]
    function = (
        descriptor.__func__
        if isinstance(descriptor, (staticmethod, classmethod))
        else descriptor
    )
    assert function.__globals__ is vars(service_mod), name
    assert function.__module__ == "src.services.scheduled_task_service", name


@pytest.mark.parametrize("name,kind", sorted(DESCRIPTOR_KINDS.items()))
def test_descriptor_kinds_are_preserved(name, kind) -> None:
    assert isinstance(vars(ScheduledTaskService)[name], kind)


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(ScheduledTaskService, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ScheduledTaskService"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


@pytest.mark.parametrize("sibling", FACADE_SIBLINGS)
def test_siblings_stay_on_the_facade(sibling) -> None:
    assert sibling in _facade_class_methods(), sibling


@pytest.mark.parametrize("name", PRE_EXISTING_BOUND)
def test_previously_bound_domains_are_not_disturbed(name) -> None:
    assert callable(getattr(ScheduledTaskService, name)), name


def test_owner_module_reuses_the_package_clone_helpers() -> None:
    """This package already carries clone helpers in admission_fields; a new
    copy here would repeat the drift #1612 consolidated in data_provider."""

    from src.services.scheduled_task_parts.admission_fields import (
        _clone_facade_descriptor as shared_clone,
    )

    assert contract_mod._clone_facade_descriptor is shared_clone
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "_clone_facade_descriptor" not in defined


def test_owner_module_imports_every_attribute_root_it_uses() -> None:
    """`re`-style misses: attribute roots never appear as bare Name loads."""

    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported, bound = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.FunctionDef):
            bound.update(arg.arg for arg in node.args.args)
            bound.update(arg.arg for arg in node.args.kwonlyargs)
            bound.add(node.name)
    roots = {
        node.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    assert roots - bound - {"self", "cls"} <= imported


def test_owner_reload_rebinds_and_leaves_other_domains_intact() -> None:
    importlib.reload(contract_mod)
    for name in MOVED:
        assert callable(getattr(ScheduledTaskService, name)), name
    for name in PRE_EXISTING_BOUND:
        assert callable(getattr(ScheduledTaskService, name)), name


def test_schema_is_supported_accepts_the_current_version() -> None:
    """Direct unit test of the extracted pure predicate."""

    from src.schemas.scheduled_task import SCHEDULED_TASK_SCHEMA_VERSION

    assert ScheduledTaskService._schema_is_supported(SCHEDULED_TASK_SCHEMA_VERSION)


def test_schema_is_supported_rejects_an_unknown_version() -> None:
    assert not ScheduledTaskService._schema_is_supported(999999)
