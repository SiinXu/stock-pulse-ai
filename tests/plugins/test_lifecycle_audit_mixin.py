# -*- coding: utf-8 -*-
"""Composition, signature, and MRO characterization for the lifecycle audit slice.

Issue #1080: the audit envelope moved into
``src/plugins/lifecycle_audit_mixin.py``. Unlike the ADR-006 rebind used in
``data_provider``, ``src/plugins`` composes by real mixin inheritance, so the
contract to protect is the MRO and the method signatures.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.plugins.lifecycle import PluginLifecycleMixin
from src.plugins.lifecycle_audit_mixin import PluginLifecycleAuditMixin
from src.plugins.manager import PluginManager

REPO_ROOT = Path(__file__).resolve().parents[2]
LIFECYCLE_PATH = REPO_ROOT / "src" / "plugins" / "lifecycle.py"
OWNER_PATH = REPO_ROOT / "src" / "plugins" / "lifecycle_audit_mixin.py"

MOVED = (
    "_audit_metadata_for",
    "_audit_begin",
    "_audit_complete",
    "_audited_operation",
    "_audited_reload",
)

# Pre-slice shapes, read from origin/main before the move. Keyword-only names
# are listed separately because that distinction is the part most easily lost.
POSITIONAL = {
    "_audit_metadata_for": ["self", "record"],
    "_audit_begin": ["self", "record"],
    "_audit_complete": ["self", "record"],
    "_audited_operation": ["self", "plugin_id", "operation", "run"],
    "_audited_reload": ["self", "plugin_id"],
}
KEYWORD_ONLY = {
    "_audit_metadata_for": [],
    "_audit_begin": ["actor_id", "actor_type", "operation", "plugin_id", "required"],
    "_audit_complete": [
        "actor_id",
        "actor_type",
        "correlation_id",
        "error_code",
        "operation",
        "plugin_id",
        "required",
        "success",
    ],
    "_audited_operation": ["actor_id", "actor_type", "require_audit"],
    "_audited_reload": ["actor_id", "actor_type", "require_audit"],
}

# Transitions and auditor state that stay on PluginLifecycleMixin.
STAYS_ON_LIFECYCLE = ("_enable", "_disable", "_reload", "_forget", "_set_last_error")


@pytest.mark.parametrize("name", MOVED)
def test_methods_remain_reachable_from_the_manager(name) -> None:
    assert callable(getattr(PluginManager, name))


@pytest.mark.parametrize("name", MOVED)
def test_positional_parameters_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(PluginManager, name))
    positional = [
        key
        for key, value in signature.parameters.items()
        if value.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]
    assert positional == POSITIONAL[name]


@pytest.mark.parametrize("name", MOVED)
def test_keyword_only_parameters_are_unchanged(name) -> None:
    """Keyword-only names are the part a careless move silently drops."""

    signature = inspect.signature(getattr(PluginManager, name))
    keyword_only = sorted(
        key
        for key, value in signature.parameters.items()
        if value.kind is inspect.Parameter.KEYWORD_ONLY
    )
    assert keyword_only == KEYWORD_ONLY[name]


def test_audit_mixin_is_in_the_manager_mro() -> None:
    assert PluginLifecycleAuditMixin in PluginManager.__mro__


def test_lifecycle_mixin_inherits_the_audit_mixin() -> None:
    """Composition must go through PluginLifecycleMixin, not a second manager base."""

    assert PluginLifecycleAuditMixin in PluginLifecycleMixin.__mro__
    assert PluginLifecycleAuditMixin not in PluginManager.__bases__


def test_manager_bases_are_unchanged() -> None:
    """The slice must not alter PluginManager's own base list."""

    assert [base.__name__ for base in PluginManager.__bases__] == [
        "PluginSettingsUpdateMixin",
        "PluginSettingsQueryMixin",
        "PluginSnapshotMixin",
        "PluginRegistrationMixin",
        "PluginInventoryMixin",
        "PluginLifecycleMixin",
    ]


@pytest.mark.parametrize("name", MOVED)
def test_bodies_no_longer_live_in_lifecycle(name) -> None:
    tree = ast.parse(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PluginLifecycleMixin"
    )
    defined = {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert name not in defined


@pytest.mark.parametrize("name", STAYS_ON_LIFECYCLE)
def test_transitions_stay_on_the_lifecycle_mixin(name) -> None:
    tree = ast.parse(LIFECYCLE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PluginLifecycleMixin"
    )
    defined = {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert name in defined


def test_owner_module_declares_exactly_the_slice() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "PluginLifecycleAuditMixin"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def test_owner_module_does_not_import_lifecycle() -> None:
    """Inheritance goes lifecycle -> audit; the reverse would be a cycle."""

    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("lifecycle" in module and "audit" not in module for module in imported)
