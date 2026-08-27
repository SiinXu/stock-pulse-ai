# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for chip-distribution extraction."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.data_provider.base as base
import src.data_provider.manager_parts.chip_distribution_methods as chip_distribution
from src.data_provider.base import DataFetcherManager
from src.data_provider.realtime_types import ChipDistribution, get_chip_circuit_breaker


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "chip_distribution_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_chip_distribution_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = chip_distribution.EXPECTED_CHIP_DISTRIBUTION_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_get_chip_distribution_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager.get_chip_distribution)
    assert list(signature.parameters) == ["self", "stock_code"]
    assert signature.parameters["stock_code"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_get_chip_distribution_has_no_validation_wrapper_token() -> None:
    method = DataFetcherManager.__dict__["get_chip_distribution"]
    assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_chip_distribution_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "chip_distribution_methods" in source
    assert "bind_chip_distribution_methods_facade" in source
    assert "def get_chip_distribution(" not in source
    assert "def get_stock_name(" in source
    importlib.import_module("src.data_provider.manager_parts.chip_distribution_methods")


def test_chip_distribution_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(chip_distribution._ChipDistributionMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == chip_distribution.__name__
    assert tuple(source_names) == chip_distribution.EXPECTED_CHIP_DISTRIBUTION_METHOD_NAMES


def test_chip_distribution_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    assert names.index("_SUPPLEMENT_FIELDS") < names.index("get_chip_distribution")
    assert names.index("get_chip_distribution") < names.index("_MONEY_FLOW_CACHE_TTL_SECONDS")
    assert names.index("get_chip_distribution") < names.index("_money_flow_timestamp")
    assert names.index("get_chip_distribution") < names.index("get_stock_name")


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.chip_distribution_methods as chip_distribution",
                    "",
                    "names = chip_distribution.EXPECTED_CHIP_DISTRIBUTION_METHOD_NAMES",
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
                    "            vars(chip_distribution._ChipDistributionMethods)[name]",
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
chip_distribution = importlib.reload(chip_distribution)
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
chip_distribution = importlib.reload(chip_distribution)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_crypto_does_not_probe_providers() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch(
        "src.config.get_config",
        side_effect=AssertionError("crypto chip must not read config"),
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        side_effect=AssertionError("crypto chip must not probe providers"),
    ), patch.object(
        DataFetcherManager,
        "_call_fetcher_method",
        side_effect=AssertionError("crypto chip must not call fetchers"),
    ):
        assert manager.get_chip_distribution("crypto:BTC") is None


def test_disabled_chip_does_not_probe_providers() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch(
        "src.config.get_config",
        return_value=SimpleNamespace(enable_chip_distribution=False),
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        side_effect=AssertionError("disabled chip must not probe providers"),
    ), patch.object(
        DataFetcherManager,
        "_call_fetcher_method",
        side_effect=AssertionError("disabled chip must not call fetchers"),
    ):
        assert manager.get_chip_distribution("600519") is None


def test_facade_patch_seam_intercepts_capability_lookup() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch(
        "src.config.get_config",
        return_value=SimpleNamespace(enable_chip_distribution=True),
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        return_value=[],
    ) as mocked:
        assert manager.get_chip_distribution("600519") is None
    mocked.assert_called_once()
    assert mocked.call_args.args[0] == "chip_distribution"


def test_unavailable_tushare_chip_skips_without_record_failure() -> None:
    breaker = get_chip_circuit_breaker()
    breaker.reset()

    class _ChipFetcher:
        def __init__(self, name: str, priority: int, result):
            self.name = name
            self.priority = priority
            self._result = result
            self.calls = 0

        def get_chip_distribution(self, stock_code: str):
            self.calls += 1
            return self._result

    tushare = _ChipFetcher(
        "TushareFetcher",
        0,
        ChipDistribution(
            code="600519",
            profit_ratio=0.61,
            avg_cost=12.3,
            concentration_90=0.13,
        ),
    )
    akshare = _ChipFetcher(
        "AkShareFetcher",
        1,
        ChipDistribution(
            code="600519",
            profit_ratio=0.62,
            avg_cost=12.5,
            concentration_90=0.14,
        ),
    )
    manager = DataFetcherManager(fetchers=[tushare, akshare])
    with patch(
        "src.config.get_config",
        return_value=SimpleNamespace(enable_chip_distribution=True),
    ), patch.object(
        breaker,
        "is_available",
        side_effect=lambda source: source != "tushare_chip",
    ), patch.object(
        breaker,
        "record_failure",
        wraps=breaker.record_failure,
    ) as record_failure:
        chip = manager.get_chip_distribution("600519")
    assert chip is akshare._result
    assert tushare.calls == 0
    assert akshare.calls == 1
    record_failure.assert_not_called()


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


def test_package_export_still_exposes_data_fetcher_manager() -> None:
    from src.data_provider import DataFetcherManager as PackageManager

    assert PackageManager is DataFetcherManager
    assert inspect.isclass(PackageManager)
