# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for CN fundamental sub-blocks."""

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
import src.data_provider.manager_parts.fundamental_cn_context_methods as cn_context
import src.data_provider.manager_parts.rankings_methods as rankings
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "fundamental_cn_context_methods.py"
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


def test_cn_context_methods_remain_on_data_fetcher_manager_facade() -> None:
    for name in cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_cn_context_signatures_are_unchanged() -> None:
    for name in cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES:
        signature = inspect.signature(getattr(DataFetcherManager, name))
        assert list(signature.parameters) == ["self", "stock_code", "budget_seconds"]
        for parameter in signature.parameters.values():
            assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert signature.parameters["budget_seconds"].default is None


def test_moved_names_are_not_validation_wrapped() -> None:
    for name in cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES:
        method = DataFetcherManager.__dict__[name]
        assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_cn_context_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "fundamental_cn_context_methods" in source
    assert "bind_fundamental_cn_context_methods_facade" in source
    for name in cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES:
        assert f"def {name}(" not in source
        assert f"    {name} = None" in source
    importlib.import_module(
        "src.data_provider.manager_parts.fundamental_cn_context_methods"
    )


def test_cn_context_bodies_leave_manager_and_stay_callable_on_facade() -> None:
    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    manager_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "DataFetcherManager"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES:
        assert name not in manager_defs, name
        assert callable(getattr(DataFetcherManager, name)), name


def test_cn_context_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(cn_context._FundamentalCnContextMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == cn_context.__name__
    assert tuple(source_names) == cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES


def test_cn_context_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    assert names.index("get_fundamental_context") < names.index("get_capital_flow_context")
    assert names.index("get_capital_flow_context") < names.index("get_dragon_tiger_context")
    assert names.index("get_dragon_tiger_context") < names.index("get_board_context")
    assert names.index("get_board_context") < names.index("_get_sector_rankings_with_meta")


def test_bind_returns_expected_names_in_class_body_order() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    bound = cn_context.bind_fundamental_cn_context_methods_facade(
        dummy,
        vars(base),
    )
    assert bound == cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES


def test_assemble_raises_import_error_on_expected_name_mismatch() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    extra = staticmethod(lambda self: {})
    cn_context._FundamentalCnContextMethods._extra_cn_context = extra
    try:
        bound = cn_context.bind_fundamental_cn_context_methods_facade(
            dummy,
            vars(base),
        )
        with pytest.raises(
            ImportError,
            match="Unexpected DataFetcherManager CN fundamental context methods",
        ):
            if bound != cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES:
                raise ImportError(
                    "Unexpected DataFetcherManager CN fundamental context methods: "
                    f"{bound!r}"
                )
        assert "_extra_cn_context" in bound
    finally:
        delattr(cn_context._FundamentalCnContextMethods, "_extra_cn_context")


def test_owner_module_declares_expected_names_only() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_FundamentalCnContextMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES)


def test_owner_module_has_zero_bare_get_config_and_forbidden_imports() -> None:
    source = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_prefixes = (
        "src.config",
        "src.core",
        "src.services",
        "src.data_provider.base",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "get_config"
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            assert not any(
                node.module == prefix or node.module.startswith(prefix + ".")
                for prefix in forbidden_prefixes
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == prefix or alias.name.startswith(prefix + ".")
                    for prefix in forbidden_prefixes
                )


def test_facade_keeps_payload_helpers_timeouts_tickflow_and_prefetch() -> None:
    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    manager_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "DataFetcherManager"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in (
        "_get_tickflow_fetcher",
        "prefetch_realtime_quotes",
        "prefetch_daily_klines",
        "_run_with_timeout",
        "_run_with_retry",
        "_normalize_source_chain",
        "_build_fundamental_block",
        "build_failed_fundamental_context",
        "build_validation_rejected_fundamental_context",
    ):
        assert name in manager_defs, name
    for name in rankings.EXPECTED_RANKINGS_METHOD_NAMES:
        assert name not in manager_defs, name


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.fundamental_cn_context_methods as cn_context",
                    "",
                    "names = cn_context.EXPECTED_FUNDAMENTAL_CN_CONTEXT_METHOD_NAMES",
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
                    "            vars(cn_context._FundamentalCnContextMethods)[name]",
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
cn_context = importlib.reload(cn_context)
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
cn_context = importlib.reload(cn_context)
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


def test_facade_patch_object_seam_still_intercepts_capital_flow() -> None:
    manager = DataFetcherManager(fetchers=[])
    sentinel = {"status": "ok", "patched": True}
    with patch.object(
        DataFetcherManager,
        "get_capital_flow_context",
        return_value=sentinel,
    ) as patched:
        assert manager.get_capital_flow_context("600519") is sentinel
    patched.assert_called_once_with("600519")


def test_default_root_get_config_patch_still_feeds_cn_timeout() -> None:
    manager = DataFetcherManager(fetchers=[])
    cfg = SimpleNamespace(fundamental_fetch_timeout_seconds=0)
    with patch("src.config.get_config", return_value=cfg), patch.object(
        manager,
        "_run_with_retry",
        side_effect=AssertionError("timeout<=0 must not call retry"),
    ):
        capital = manager.get_capital_flow_context("600519")
        dragon = manager.get_dragon_tiger_context("600519")
        boards = manager.get_board_context("600519")
    assert capital["status"] == "failed"
    assert dragon["status"] == "failed"
    assert boards["status"] == "failed"


def test_injected_application_services_config_wins_over_get_config_patch() -> None:
    manager = DataFetcherManager(fetchers=[])
    injected = SimpleNamespace(fundamental_fetch_timeout_seconds=0)
    patched = SimpleNamespace(fundamental_fetch_timeout_seconds=30)
    set_application_services(
        ApplicationServices(
            config=injected,
            builtin_plugins=(),
            plugins_dir="",
        )
    )
    with patch("src.config.get_config", return_value=patched), patch.object(
        manager,
        "_run_with_retry",
        side_effect=AssertionError("injected timeout 0 must not call retry"),
    ):
        ctx = manager.get_capital_flow_context("600519")
    assert ctx["status"] == "failed"


def test_get_board_context_calls_rebound_sector_rankings_with_meta() -> None:
    manager = DataFetcherManager(fetchers=[])
    facade_rankings = _descriptor_function(
        vars(DataFetcherManager)["_get_sector_rankings_with_meta"]
    )
    owner_rankings = _descriptor_function(
        vars(rankings._RankingsMethods)["_get_sector_rankings_with_meta"]
    )
    assert facade_rankings is not owner_rankings
    assert facade_rankings.__code__ is owner_rankings.__code__
    with patch.object(
        manager,
        "_get_sector_rankings_with_meta",
        return_value=([], [], [], "all failed"),
    ) as spy:
        ctx = manager.get_board_context("600519", budget_seconds=0.5)
    spy.assert_called_once_with(5)
    assert ctx["status"] == "failed"


def test_non_cn_and_etf_remain_not_supported_without_retry() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        manager,
        "_run_with_retry",
        side_effect=AssertionError("not_supported must not call retry"),
    ):
        us_ctx = manager.get_capital_flow_context("AAPL", budget_seconds=0.5)
        etf_ctx = manager.get_dragon_tiger_context("510300", budget_seconds=0.5)
        hk_boards = manager.get_board_context("hk00700", budget_seconds=0.5)
    assert us_ctx["status"] == "not_supported"
    assert etf_ctx["status"] == "not_supported"
    assert hk_boards["status"] == "not_supported"
