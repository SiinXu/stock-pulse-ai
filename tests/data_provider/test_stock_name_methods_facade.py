# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for stock-name extraction."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import pandas as pd

import src.data_provider.base as base
import src.data_provider.manager_parts.stock_name_methods as stock_name
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "stock_name_methods.py"
)

UNMAPPED_CN_CODE = "999997"


class _StockListFetcher:
    def __init__(self, name: str, frame):
        self.name = name
        self.priority = 0
        self._frame = frame
        self.calls = 0

    def get_stock_list(self):
        self.calls += 1
        if isinstance(self._frame, Exception):
            raise self._frame
        return self._frame


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_stock_name_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = stock_name.EXPECTED_STOCK_NAME_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_get_stock_name_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager.get_stock_name)
    assert list(signature.parameters) == ["self", "stock_code", "allow_realtime"]
    assert signature.parameters["stock_code"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    allow_realtime = signature.parameters["allow_realtime"]
    assert allow_realtime.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert allow_realtime.default is True


def test_get_stock_name_has_no_validation_wrapper_token() -> None:
    method = DataFetcherManager.__dict__["get_stock_name"]
    assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_public_prefetch_stock_names_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager.prefetch_stock_names)
    assert list(signature.parameters) == ["self", "stock_codes", "use_bulk"]
    for name in ("self", "stock_codes", "use_bulk"):
        assert signature.parameters[name].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["use_bulk"].default is False


def test_public_batch_get_stock_names_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager.batch_get_stock_names)
    assert list(signature.parameters) == ["self", "stock_codes"]
    assert signature.parameters["self"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["stock_codes"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_prefetch_and_batch_have_no_validation_wrapper_token() -> None:
    for name in ("prefetch_stock_names", "batch_get_stock_names"):
        method = DataFetcherManager.__dict__[name]
        assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_stock_name_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "stock_name_methods" in source
    assert "bind_stock_name_methods_facade" in source
    assert "def get_stock_name(" not in source
    assert "get_stock_name = None" in source
    assert "def prefetch_stock_names(" not in source
    assert "def batch_get_stock_names(" not in source
    assert "prefetch_stock_names = None" in source
    assert "batch_get_stock_names = None" in source
    facade_tree = ast.parse(source)
    for node in ast.walk(facade_tree):
        if isinstance(node, ast.ClassDef) and node.name == "DataFetcherManager":
            facade_defs = {
                child.name for child in node.body if isinstance(child, ast.FunctionDef)
            }
            assert "prefetch_stock_names" not in facade_defs
            assert "batch_get_stock_names" not in facade_defs
    owner_tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    owner_defs = []
    for node in ast.walk(owner_tree):
        if isinstance(node, ast.ClassDef) and node.name == "_StockNameMethods":
            owner_defs = [
                child.name for child in node.body if isinstance(child, ast.FunctionDef)
            ]
    assert owner_defs == [
        "get_stock_name",
        "prefetch_stock_names",
        "batch_get_stock_names",
    ]
    importlib.import_module("src.data_provider.manager_parts.stock_name_methods")


def test_stock_name_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(stock_name._StockNameMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == stock_name.__name__
    assert tuple(source_names) == stock_name.EXPECTED_STOCK_NAME_METHOD_NAMES
    assert stock_name.EXPECTED_STOCK_NAME_METHOD_NAMES == (
        "get_stock_name",
        "prefetch_stock_names",
        "batch_get_stock_names",
    )


def test_stock_name_placeholder_preserves_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    assert names.index("get_chip_distribution") < names.index("get_money_flow")
    assert names.index("get_money_flow") < names.index("get_stock_name")
    assert names.index("get_stock_name") < names.index("get_belong_boards")
    assert names.index("get_belong_boards") < names.index("prefetch_stock_names")
    assert names.index("prefetch_stock_names") < names.index("batch_get_stock_names")
    assert names.index("batch_get_stock_names") < names.index("get_main_indices")
    assert names.index("get_main_indices") < names.index("get_market_stats")
    assert names.index("get_market_stats") < names.index("_run_with_timeout")


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.stock_name_methods as stock_name",
                    "",
                    "names = stock_name.EXPECTED_STOCK_NAME_METHOD_NAMES",
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
                    "            vars(stock_name._StockNameMethods)[name]",
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
stock_name = importlib.reload(stock_name)
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
stock_name = importlib.reload(stock_name)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_memory_cache_hit_short_circuits_before_static_map() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "_get_cached_stock_name",
        return_value="Cached Name",
    ), patch(
        "src.data_provider.base.get_index_stock_name",
        side_effect=AssertionError("cache hit must not read the index"),
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        side_effect=AssertionError("cache hit must not probe providers"),
    ):
        assert manager.get_stock_name("600519") == "Cached Name"


def test_index_lookup_uses_facade_module_patch_seam() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch(
        "src.data_provider.base.get_index_stock_name",
        return_value="Index Name",
    ) as index_lookup, patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        side_effect=AssertionError("index hit must not probe providers"),
    ):
        assert manager.get_stock_name(UNMAPPED_CN_CODE, allow_realtime=False) == "Index Name"
    index_lookup.assert_called_once_with(UNMAPPED_CN_CODE)


def test_local_only_mode_returns_empty_without_provider_or_realtime() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch(
        "src.data_provider.base.get_index_stock_name",
        return_value=None,
    ), patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=True,
    ), patch.object(
        DataFetcherManager,
        "get_realtime_quote",
        side_effect=AssertionError("local-only must not query realtime"),
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        side_effect=AssertionError("local-only must not probe providers"),
    ):
        assert manager.get_stock_name(UNMAPPED_CN_CODE) == ""


def test_allow_realtime_false_skips_realtime_probe_but_keeps_providers() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch(
        "src.data_provider.base.get_index_stock_name",
        return_value=None,
    ), patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "get_realtime_quote",
        side_effect=AssertionError("allow_realtime=False must not query realtime"),
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        return_value=[],
    ) as capability:
        assert manager.get_stock_name(UNMAPPED_CN_CODE, allow_realtime=False) == ""
    capability.assert_called_once()
    assert capability.call_args.args[0] == "stock_name"
    assert capability.call_args.kwargs["market"] == "cn"


def test_realtime_quote_receives_raw_code_and_caches_result() -> None:
    manager = DataFetcherManager(fetchers=[])
    quote = SimpleNamespace(name="Realtime Name")
    with patch(
        "src.data_provider.base.get_index_stock_name",
        return_value=None,
    ), patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "get_realtime_quote",
        return_value=quote,
    ) as realtime, patch.object(
        DataFetcherManager,
        "_cache_stock_name",
        return_value=None,
    ) as cache_store, patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        side_effect=AssertionError("realtime hit must not probe providers"),
    ):
        assert manager.get_stock_name(f"SH{UNMAPPED_CN_CODE}") == "Realtime Name"
    realtime.assert_called_once_with(f"SH{UNMAPPED_CN_CODE}", log_final_failure=False)
    cache_store.assert_called_once_with(UNMAPPED_CN_CODE, "Realtime Name")


def test_us_code_skips_non_us_capable_builtin_fetcher_via_in_body_seam() -> None:
    class _NameFetcher:
        def __init__(self, name: str, result: str):
            self.name = name
            self.priority = 0
            self._result = result
            self.calls = 0

        def get_stock_name(self, stock_code: str):
            self.calls += 1
            return self._result

    akshare = _NameFetcher("AkShareFetcher", "Wrong Name")
    yfinance = _NameFetcher("YfinanceFetcher", "Apple Inc.")
    manager = DataFetcherManager(fetchers=[akshare, yfinance])
    with patch(
        "src.data_provider.base.get_index_stock_name",
        return_value=None,
    ), patch(
        "src.data_provider.akshare_fetcher._is_us_code",
        return_value=True,
    ) as is_us_code, patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        return_value=[akshare, yfinance],
    ), patch.object(
        DataFetcherManager,
        "_is_fetcher_available",
        return_value=True,
    ):
        assert manager.get_stock_name("ZZZZ", allow_realtime=False) == "Apple Inc."
    is_us_code.assert_called_once_with("ZZZZ")
    assert akshare.calls == 0
    assert yfinance.calls == 1


def test_provider_exception_logs_safely_and_falls_back_to_next_source() -> None:
    class _BoomFetcher:
        name = "AkShareFetcher"
        priority = 0

        def get_stock_name(self, stock_code: str):
            raise RuntimeError("boom")

    class _OkFetcher:
        name = "TushareFetcher"
        priority = 1

        def __init__(self):
            self.calls = 0

        def get_stock_name(self, stock_code: str):
            self.calls += 1
            return "Fallback Name"

    boom = _BoomFetcher()
    ok = _OkFetcher()
    manager = DataFetcherManager(fetchers=[boom, ok])
    with patch(
        "src.data_provider.base.get_index_stock_name",
        return_value=None,
    ), patch(
        "src.data_provider.base.log_safe_exception",
    ) as log_safe, patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        return_value=[boom, ok],
    ), patch.object(
        DataFetcherManager,
        "_is_fetcher_available",
        return_value=True,
    ):
        assert manager.get_stock_name(UNMAPPED_CN_CODE, allow_realtime=False) == "Fallback Name"
    assert ok.calls == 1
    log_safe.assert_called_once()
    assert log_safe.call_args.kwargs["error_code"] == (
        "data_provider_stock_name_lookup_failed"
    )


def test_prefetch_empty_list_and_local_only_are_noops() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "get_stock_name",
        side_effect=AssertionError("empty/local-only prefetch must not call get_stock_name"),
    ), patch.object(
        DataFetcherManager,
        "batch_get_stock_names",
        side_effect=AssertionError("empty/local-only prefetch must not call batch_get_stock_names"),
    ):
        manager.prefetch_stock_names([])
        with patch.object(
            DataFetcherManager,
            "is_market_data_local_only",
            return_value=True,
        ):
            manager.prefetch_stock_names(["600519"])


def test_prefetch_use_bulk_false_normalizes_and_skips_realtime() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "get_stock_name",
        return_value="",
    ) as get_name, patch.object(
        DataFetcherManager,
        "batch_get_stock_names",
        side_effect=AssertionError("use_bulk=False must not call batch_get_stock_names"),
    ):
        manager.prefetch_stock_names(["SH600519", "000001"], use_bulk=False)
    get_name.assert_has_calls(
        [
            call("600519", allow_realtime=False),
            call("000001", allow_realtime=False),
        ]
    )


def test_prefetch_use_bulk_true_delegates_to_batch_get_stock_names() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "batch_get_stock_names",
        return_value={},
    ) as batch, patch.object(
        DataFetcherManager,
        "get_stock_name",
        side_effect=AssertionError("use_bulk=True must not call get_stock_name"),
    ):
        manager.prefetch_stock_names(["SH600519", "000001"], use_bulk=True)
    batch.assert_called_once_with(["600519", "000001"])


def test_batch_get_stock_names_cache_hit_skips_providers() -> None:
    manager = DataFetcherManager(fetchers=[])
    manager._stock_name_cache["600519"] = "贵州茅台"
    manager._stock_name_cache["000001"] = "平安银行"
    with patch.object(
        manager,
        "_ensure_concurrency_guards",
        wraps=manager._ensure_concurrency_guards,
    ) as guards, patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        side_effect=AssertionError("cache hit must not probe stock_list providers"),
    ), patch.object(
        DataFetcherManager,
        "get_stock_name",
        side_effect=AssertionError("cache hit must not fall back to get_stock_name"),
    ):
        assert manager.batch_get_stock_names(["600519", "000001"]) == {
            "600519": "贵州茅台",
            "000001": "平安银行",
        }
    guards.assert_called()


def test_batch_get_stock_names_local_only_returns_cache_only() -> None:
    manager = DataFetcherManager(fetchers=[])
    manager._stock_name_cache["600519"] = "贵州茅台"
    with patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=True,
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        side_effect=AssertionError("local-only bulk must not probe stock_list"),
    ), patch.object(
        DataFetcherManager,
        "get_stock_name",
        side_effect=AssertionError("local-only bulk must not fall back to get_stock_name"),
    ):
        assert manager.batch_get_stock_names(["600519", "000001"]) == {
            "600519": "贵州茅台",
        }


def test_batch_get_stock_names_ignores_none_and_empty_stock_list() -> None:
    none_fetcher = _StockListFetcher("NoneListFetcher", None)
    empty_fetcher = _StockListFetcher(
        "EmptyListFetcher",
        pd.DataFrame(columns=["code", "name"]),
    )
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        return_value=[none_fetcher, empty_fetcher],
    ), patch.object(
        DataFetcherManager,
        "_provider_supports_capability",
        return_value=True,
    ), patch.object(
        DataFetcherManager,
        "_is_fetcher_available",
        return_value=True,
    ), patch.object(
        DataFetcherManager,
        "get_stock_name",
        return_value="Fallback Name",
    ) as get_name:
        assert manager.batch_get_stock_names(["600519"]) == {"600519": "Fallback Name"}
    assert none_fetcher.calls == 1
    assert empty_fetcher.calls == 1
    get_name.assert_called_once_with("600519")


def test_batch_get_stock_names_skips_unsupported_market_then_rejects_cross_market_rows() -> None:
    hk_fetcher = _StockListFetcher(
        "HongKongStockListFetcher",
        pd.DataFrame(
            {
                "code": ["HK00700", "600519"],
                "name": ["Tencent", "Plugin CN Name"],
            }
        ),
    )
    manager = DataFetcherManager(fetchers=[])

    def supports(_fetcher, _capability, market):
        return market == "hk"

    with patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        return_value=[hk_fetcher],
    ), patch.object(
        DataFetcherManager,
        "_provider_supports_capability",
        side_effect=supports,
    ), patch.object(
        DataFetcherManager,
        "_is_fetcher_available",
        return_value=True,
    ), patch.object(
        DataFetcherManager,
        "get_stock_name",
        return_value="Fallback CN Name",
    ) as get_name:
        cn_only = manager.batch_get_stock_names(["600519"])
        mixed = manager.batch_get_stock_names(["600519", "HK00700"])
    assert cn_only == {"600519": "Fallback CN Name"}
    assert hk_fetcher.calls == 1
    assert mixed == {
        "HK00700": "Tencent",
        "600519": "Fallback CN Name",
    }
    assert manager._stock_name_cache["HK00700"] == "Tencent"
    assert "600519" not in manager._stock_name_cache or manager._stock_name_cache.get("600519") != "Plugin CN Name"
    assert get_name.call_count == 2
    get_name.assert_has_calls([call("600519"), call("600519")])


def test_batch_get_stock_names_provider_exception_logs_and_continues() -> None:
    boom = _StockListFetcher("BoomListFetcher", RuntimeError("boom"))
    ok = _StockListFetcher(
        "OkListFetcher",
        pd.DataFrame({"code": ["000001"], "name": ["平安银行"]}),
    )
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        return_value=[boom, ok],
    ), patch.object(
        DataFetcherManager,
        "_provider_supports_capability",
        return_value=True,
    ), patch.object(
        DataFetcherManager,
        "_is_fetcher_available",
        return_value=True,
    ), patch(
        "src.data_provider.base.log_safe_exception",
    ) as log_safe, patch.object(
        DataFetcherManager,
        "get_stock_name",
        return_value="Fallback Name",
    ) as get_name:
        assert manager.batch_get_stock_names(["600519", "000001"]) == {
            "000001": "平安银行",
            "600519": "Fallback Name",
        }
    assert boom.calls == 1
    assert ok.calls == 1
    log_safe.assert_called_once()
    assert log_safe.call_args.kwargs["error_code"] == (
        "data_provider_bulk_stock_name_lookup_failed"
    )
    get_name.assert_called_once_with("600519")


def test_all_sources_failed_returns_empty_string() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch(
        "src.data_provider.base.get_index_stock_name",
        return_value=None,
    ), patch.object(
        DataFetcherManager,
        "is_market_data_local_only",
        return_value=False,
    ), patch.object(
        DataFetcherManager,
        "get_realtime_quote",
        return_value=None,
    ), patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        return_value=[],
    ):
        assert manager.get_stock_name(UNMAPPED_CN_CODE) == ""


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
