# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and config-root characterization for #1540."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.data_provider.base as base
import src.data_provider.manager_parts.fundamental_context_methods as fundamental_context
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.config import get_config
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "fundamental_context_methods.py"
)


@pytest.fixture(autouse=True)
def _reset_application_services() -> None:
    reset_application_services()
    yield
    reset_application_services()


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_fundamental_context_methods_remain_on_data_fetcher_manager_facade() -> None:
    for name in fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_fundamental_config_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager._get_fundamental_config)
    assert list(signature.parameters) == ["self"]
    assert signature.parameters["self"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_moved_names_are_not_validation_wrapped() -> None:
    for name in fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES:
        method = DataFetcherManager.__dict__[name]
        assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_fundamental_context_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "fundamental_context_methods" in source
    assert "bind_fundamental_context_methods_facade" in source
    assert "_get_fundamental_config = None" in source
    assert "def _get_fundamental_config(" not in source
    owner_source = OWNER_PATH.read_text(encoding="utf-8")
    assert "def _get_fundamental_config(" in owner_source
    importlib.import_module("src.data_provider.manager_parts.fundamental_context_methods")


def test_fundamental_context_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(
        fundamental_context._FundamentalContextMethods
    ).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == fundamental_context.__name__
    assert tuple(source_names) == fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES


def test_fundamental_context_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    assert names.index("_run_with_retry") < names.index("_get_fundamental_config")
    assert names.index("_get_fundamental_config") < names.index("_normalize_source_chain")


def test_bind_returns_expected_names_in_class_body_order() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    bound = fundamental_context.bind_fundamental_context_methods_facade(
        dummy,
        vars(base),
    )
    assert bound == fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES


def test_assemble_raises_import_error_on_expected_name_mismatch() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    extra = staticmethod(lambda self: None)
    fundamental_context._FundamentalContextMethods._extra_context = extra
    try:
        bound = fundamental_context.bind_fundamental_context_methods_facade(
            dummy,
            vars(base),
        )
        with pytest.raises(
            ImportError,
            match="Unexpected DataFetcherManager fundamental context methods",
        ):
            if bound != fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES:
                raise ImportError(
                    "Unexpected DataFetcherManager fundamental context methods: "
                    f"{bound!r}"
                )
        assert "_extra_context" in bound
    finally:
        delattr(fundamental_context._FundamentalContextMethods, "_extra_context")


def test_owner_module_declares_expected_names_only() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_FundamentalContextMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES)
    assert defined == {"_get_fundamental_config"}


def test_owner_module_has_zero_bare_get_config_and_forbidden_imports() -> None:
    source = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_prefixes = (
        "src.config",
        "src.core",
        "src.services",
        "src.data_provider.base",
    )
    saw_application_services_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "get_config"
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            assert not any(
                node.module == prefix or node.module.startswith(prefix + ".")
                for prefix in forbidden_prefixes
            )
            if node.module == "src.application_services" or node.module.startswith(
                "src.application_services."
            ):
                saw_application_services_import = True
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == prefix or alias.name.startswith(prefix + ".")
                    for prefix in forbidden_prefixes
                )
    assert saw_application_services_import


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.fundamental_context_methods as fundamental_context",
                    "",
                    "names = fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    original = getattr(",
                    "        descriptor,",
                    "        '_stockpulse_data_validation_original',",
                    "        None,",
                    "    )",
                    "    return original if original is not None else descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    facade = {}",
                    "    for name in names:",
                    "        source[name] = descriptor_function(",
                    "            vars(fundamental_context._FundamentalContextMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(base.DataFetcherManager)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(base)",
                    "        assert facade[name].__module__ == 'src.data_provider.base'",
                    "        assert facade[name].__qualname__ == f'DataFetcherManager.{name}'",
                    "    return source, facade",
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


def test_owner_reload_rebinds_loaded_facade() -> None:
    _run_reload_contract(
        """
old_class = base.DataFetcherManager
before_source, before_facade = bindings()
fundamental_context = importlib.reload(fundamental_context)
assert base.DataFetcherManager is old_class
after_source, after_facade = bindings()
for name in names:
    assert after_source[name] is not before_source[name]
    assert after_facade[name] is not before_facade[name]
    assert after_facade[name].__code__ is after_source[name].__code__
"""
    )


def test_facade_then_owner_reload_keeps_one_current_contract() -> None:
    _run_reload_contract(
        """
old_class = base.DataFetcherManager
before_source, before_facade = bindings()
base = importlib.reload(base)
assert base.DataFetcherManager is not old_class
after_base_source, after_base_facade = bindings()
for name in names:
    assert after_base_source[name] is before_source[name]
    assert after_base_facade[name] is not before_facade[name]
reloaded_class = base.DataFetcherManager
fundamental_context = importlib.reload(fundamental_context)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_package_export_still_exposes_data_fetcher_manager() -> None:
    from src.data_provider import DataFetcherManager as PackageManager

    assert PackageManager is DataFetcherManager
    assert inspect.isclass(PackageManager)


def test_default_root_fundamental_config_is_get_config_identity() -> None:
    manager = DataFetcherManager(fetchers=[])
    assert manager._get_fundamental_config() is get_config()


def test_injected_application_services_config_wins_over_get_config_patch() -> None:
    manager = DataFetcherManager(fetchers=[])
    injected = SimpleNamespace(source="injected")
    patched = SimpleNamespace(source="patched-get-config")
    set_application_services(
        ApplicationServices(
            config=injected,
            builtin_plugins=(),
            plugins_dir="",
        )
    )
    with patch("src.config.get_config", return_value=patched):
        assert manager._get_fundamental_config() is injected
        assert manager._get_fundamental_config() is not patched


def test_reset_application_services_restores_get_config_identity() -> None:
    manager = DataFetcherManager(fetchers=[])
    injected = SimpleNamespace(source="injected")
    set_application_services(
        ApplicationServices(
            config=injected,
            builtin_plugins=(),
            plugins_dir="",
        )
    )
    assert manager._get_fundamental_config() is injected
    reset_application_services()
    assert manager._get_fundamental_config() is get_config()
