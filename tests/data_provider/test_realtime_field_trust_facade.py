# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and patch-seam guards for field-trust extraction."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import src.data_provider.base as base
import src.data_provider.manager_parts.realtime_field_trust_methods as realtime
from src.data_provider.base import DataFetcherManager
from src.data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "realtime_field_trust_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


def test_realtime_field_trust_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = realtime.EXPECTED_REALTIME_FIELD_TRUST_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_owner_module_exists_for_realtime_field_trust_extraction() -> None:
    assert OWNER_PATH.is_file()
    assert "realtime_field_trust_methods" in BASE_PATH.read_text(encoding="utf-8")
    importlib.import_module(
        "src.data_provider.manager_parts.realtime_field_trust_methods"
    )


def test_realtime_field_trust_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(realtime._RealtimeFieldTrustMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == realtime.__name__
    assert tuple(source_names) == realtime.EXPECTED_REALTIME_FIELD_TRUST_METHOD_NAMES


def test_facade_patch_seam_intercepts_try_fetcher_quote() -> None:
    primary = UnifiedRealtimeQuote(
        code="AAPL",
        name="Apple",
        source=RealtimeSource.LONGBRIDGE,
        price=1688.0,
    )
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "_try_fetcher_quote",
        return_value=None,
    ) as mocked:
        quote = manager._supplement_quote("AAPL", primary, "YfinanceFetcher")
    assert quote is primary
    mocked.assert_called_once()
    assert mocked.call_args.args[1] == "YfinanceFetcher"


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "from types import SimpleNamespace",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.realtime_field_trust_methods as realtime",
                    "",
                    "names = realtime.EXPECTED_REALTIME_FIELD_TRUST_METHOD_NAMES",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        return descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    facade = {}",
                    "    for name in names:",
                    "        source[name] = descriptor_function(",
                    "            vars(realtime._RealtimeFieldTrustMethods)[name]",
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
realtime = importlib.reload(realtime)
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
realtime = importlib.reload(realtime)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_rebound_try_fetcher_quote_uses_facade_unavailable_seam() -> None:
    recorded = []
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        base,
        "record_provider_run",
        side_effect=lambda **kwargs: recorded.append(kwargs),
    ):
        quote = manager._try_fetcher_quote("AAPL", "MissingFetcher")
    assert quote is None
    assert recorded
    assert recorded[0]["error_type"] == "unavailable"
    assert recorded[0]["provider"] == "MissingFetcher"
