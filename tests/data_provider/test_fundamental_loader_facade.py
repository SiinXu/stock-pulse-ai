# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for fundamental loader extraction."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.data_provider.base as base
import src.data_provider.manager_parts.fundamental_loader_methods as fundamental_loader
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "fundamental_loader_methods.py"
)

CONTEXT_KEYS = (
    "valuation",
    "growth",
    "earnings",
    "institution",
    "capital_flow",
    "dragon_tiger",
    "boards",
    "coverage",
    "source_chain",
    "errors",
    "status",
)
OFFSHORE_EXTRA_KEYS = ("belong_boards", "data_quality", "missing_fields")
OFFSHORE_CODES = (
    ("AAPL", "us"),
    ("0700.HK", "hk"),
    ("7203.T", "jp"),
    ("005930.KS", "kr"),
    ("2330.TW", "tw"),
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def _cfg(**overrides):
    values = {
        "enable_fundamental_pipeline": True,
        "fundamental_cache_ttl_seconds": 0,
        "fundamental_stage_timeout_seconds": 1.5,
        "fundamental_fetch_timeout_seconds": 0.8,
        "fundamental_retry_max": 1,
        "fundamental_cache_max_entries": 256,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _block(status: str = "not_supported"):
    return {"status": status, "source_chain": [], "errors": [], "data": {}}


def _empty_bundle():
    return {
        "status": "not_supported",
        "growth": {},
        "earnings": {},
        "institution": {},
        "belong_boards": [],
        "source_chain": [],
        "errors": [],
    }


def test_fundamental_loader_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = fundamental_loader.EXPECTED_FUNDAMENTAL_LOADER_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_get_fundamental_context_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager.get_fundamental_context)
    assert list(signature.parameters) == ["self", "stock_code", "budget_seconds"]
    assert signature.parameters["stock_code"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["budget_seconds"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["budget_seconds"].default is None


def test_get_fundamental_context_final_exit_keeps_validation_wrapper() -> None:
    method = DataFetcherManager.__dict__["get_fundamental_context"]
    assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is not None
    original = getattr(method, "_stockpulse_data_validation_original")
    source = _descriptor_function(
        vars(fundamental_loader._FundamentalLoaderMethods)["get_fundamental_context"]
    )
    assert original is not source
    assert original.__code__ is source.__code__


def test_owner_module_exists_for_fundamental_loader_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "fundamental_loader_methods" in source
    assert "bind_fundamental_loader_methods_facade" in source
    assert "def get_fundamental_context(" not in source
    assert "def _build_offshore_fundamental_context(" not in source
    assert "def _get_fundamental_config(" in source
    assert "def _normalize_source_chain(" in source
    importlib.import_module("src.data_provider.manager_parts.fundamental_loader_methods")


def test_fundamental_loader_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(fundamental_loader._FundamentalLoaderMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == fundamental_loader.__name__
    assert tuple(source_names) == fundamental_loader.EXPECTED_FUNDAMENTAL_LOADER_METHOD_NAMES


def test_fundamental_loader_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    assert names.index("_build_market_not_supported") < names.index(
        "_build_offshore_fundamental_context"
    )
    assert names.index("_build_offshore_fundamental_context") < names.index(
        "build_failed_fundamental_context"
    )
    assert names.index("build_failed_fundamental_context") < names.index(
        "build_validation_rejected_fundamental_context"
    )
    assert names.index("build_validation_rejected_fundamental_context") < names.index(
        "get_fundamental_context"
    )
    assert names.index("get_fundamental_context") < names.index("get_capital_flow_context")


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.fundamental_loader_methods as fundamental_loader",
                    "",
                    "names = fundamental_loader.EXPECTED_FUNDAMENTAL_LOADER_METHOD_NAMES",
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
                    "            vars(fundamental_loader._FundamentalLoaderMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(base.DataFetcherManager)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(base)",
                    "        assert facade[name].__module__ == 'src.data_provider.base'",
                    "        assert facade[name].__qualname__ == f'DataFetcherManager.{name}'",
                    "    context = vars(base.DataFetcherManager)['get_fundamental_context']",
                    "    assert getattr(",
                    "        context,",
                    "        '_stockpulse_data_validation_wrapper_token',",
                    "        None,",
                    "    ) is not None",
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
fundamental_loader = importlib.reload(fundamental_loader)
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
fundamental_loader = importlib.reload(fundamental_loader)
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


def test_disabled_pipeline_returns_not_supported_without_loaders() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch("src.config.get_config", return_value=_cfg(enable_fundamental_pipeline=False)), \
            patch.object(
                manager,
                "_build_offshore_fundamental_context",
                side_effect=AssertionError("disabled pipeline must not load offshore"),
            ), \
            patch.object(
                manager,
                "get_capital_flow_context",
                side_effect=AssertionError("disabled pipeline must not load CN feeds"),
            ):
        ctx = manager.get_fundamental_context("600519")
    assert ctx["status"] == "not_supported"
    assert "disabled" in " ".join(ctx.get("errors", [])).lower()


def test_crypto_returns_not_supported_without_equity_loaders() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch("src.config.get_config", return_value=_cfg()), \
            patch.object(
                manager,
                "_build_offshore_fundamental_context",
                side_effect=AssertionError("crypto must not use the offshore loader"),
            ), \
            patch.object(
                manager,
                "get_capital_flow_context",
                side_effect=AssertionError("crypto must not use CN feeds"),
            ):
        ctx = manager.get_fundamental_context("crypto:BTC")
    assert ctx["market"] == "crypto"
    assert ctx["status"] == "not_supported"
    assert "do not apply" in " ".join(ctx.get("errors", [])).lower()


@pytest.mark.parametrize("code,market", OFFSHORE_CODES)
def test_offshore_markets_dispatch_to_offshore_loader(code: str, market: str) -> None:
    manager = DataFetcherManager(fetchers=[])
    sentinel = {"status": "ok", "market": market}

    def _assert_no_cn_feed(*_args, **_kwargs):
        raise AssertionError("offshore dispatch must not call CN sub-block feeds")

    with patch("src.config.get_config", return_value=_cfg()), \
            patch.object(
                manager,
                "_build_offshore_fundamental_context",
                return_value=sentinel,
            ) as offshore, \
            patch.object(manager, "get_capital_flow_context", side_effect=_assert_no_cn_feed), \
            patch.object(manager, "get_dragon_tiger_context", side_effect=_assert_no_cn_feed), \
            patch.object(manager, "get_board_context", side_effect=_assert_no_cn_feed):
        ctx = manager.get_fundamental_context(code)
    assert ctx is sentinel
    offshore.assert_called_once()
    kwargs = offshore.call_args.kwargs
    assert kwargs["market"] == market


def test_cn_path_instance_patches_intercept_nested_load() -> None:
    manager = DataFetcherManager(fetchers=[])
    capital = _block("partial")
    dragon = _block("ok")
    boards = _block("partial")
    with patch("src.config.get_config", return_value=_cfg()), \
            patch.object(manager, "get_realtime_quote", return_value=None), \
            patch.object(
                manager._fundamental_adapter,
                "get_fundamental_bundle",
                return_value=_empty_bundle(),
            ), \
            patch.object(manager, "get_capital_flow_context", return_value=capital) as cf, \
            patch.object(manager, "get_dragon_tiger_context", return_value=dragon) as dt, \
            patch.object(manager, "get_board_context", return_value=boards) as bd:
        ctx = manager.get_fundamental_context("600519")
    cf.assert_called_once()
    dt.assert_called_once()
    bd.assert_called_once()
    assert ctx["capital_flow"] is capital
    assert ctx["dragon_tiger"] is dragon
    assert ctx["boards"] is boards
    for key in CONTEXT_KEYS:
        assert key in ctx


def test_etf_cn_path_marks_sub_blocks_not_supported() -> None:
    manager = DataFetcherManager(fetchers=[])
    quote = SimpleNamespace(
        pe_ratio=None,
        pb_ratio=None,
        total_mv=5.0e10,
        circ_mv=4.0e10,
        source=SimpleNamespace(value="tencent"),
    )

    def _assert_no_cn_feed(*_args, **_kwargs):
        raise AssertionError("ETF CN path must not call capital_flow/dragon_tiger/board feeds")

    with patch("src.config.get_config", return_value=_cfg()), \
            patch.object(manager, "get_realtime_quote", return_value=quote), \
            patch.object(
                manager._fundamental_adapter,
                "get_fundamental_bundle",
                return_value=_empty_bundle(),
            ), \
            patch.object(manager, "get_capital_flow_context", side_effect=_assert_no_cn_feed), \
            patch.object(manager, "get_dragon_tiger_context", side_effect=_assert_no_cn_feed), \
            patch.object(manager, "get_board_context", side_effect=_assert_no_cn_feed):
        ctx = manager.get_fundamental_context("159915")
    assert ctx["market"] == "cn"
    assert ctx["status"] in ("partial", "not_supported")
    assert ctx["coverage"]["capital_flow"] == "not_supported"
    assert ctx["coverage"]["dragon_tiger"] == "not_supported"
    assert ctx["coverage"]["boards"] == "not_supported"
    for key in CONTEXT_KEYS:
        assert key in ctx


def test_offshore_context_keeps_expected_keys() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch("src.config.get_config", return_value=_cfg()), \
            patch.object(manager, "get_realtime_quote", return_value=None), \
            patch.object(
                manager._yfinance_fundamental_adapter,
                "get_fundamental_bundle",
                return_value=_empty_bundle(),
            ), \
            patch.object(
                manager,
                "get_capital_flow_context",
                side_effect=AssertionError("offshore must not call CN capital_flow"),
            ):
        ctx = manager.get_fundamental_context("AAPL")
    assert ctx["market"] == "us"
    assert ctx["status"] == "not_supported"
    for key in CONTEXT_KEYS + OFFSHORE_EXTRA_KEYS:
        assert key in ctx
    assert ctx["coverage"]["capital_flow"] == "not_supported"
    assert ctx["coverage"]["dragon_tiger"] == "not_supported"
    assert ctx["coverage"]["boards"] == "not_supported"


def test_tw_institution_init_failure_is_fail_open() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch("src.config.get_config", return_value=_cfg()), \
            patch.object(manager, "get_realtime_quote", return_value=None), \
            patch.object(
                manager._yfinance_fundamental_adapter,
                "get_fundamental_bundle",
                return_value=_empty_bundle(),
            ), \
            patch(
                "src.data_provider.tw_institutional_fetcher.TwInstitutionalFetcher",
                side_effect=RuntimeError("init boom"),
            ):
        ctx = manager.get_fundamental_context("2330.TW")
    assert ctx["market"] == "tw"
    assert ctx["coverage"]["institution"] == "not_supported"
    assert ctx["institution"].get("data") == {}


def test_cache_key_still_includes_symbol_market_budget_as_of() -> None:
    manager = DataFetcherManager(fetchers=[])
    key = manager._get_fundamental_cache_key(
        "600519",
        1.5,
        market="cn",
        config=_cfg(fundamental_cache_ttl_seconds=120),
    )
    assert key.startswith("600519|")
    assert "|market=cn|" in key
    assert "|budget=" in key
    assert "|as_of=" in key


def test_failed_status_is_skipped_by_cache_policy() -> None:
    manager = DataFetcherManager(fetchers=[])
    cfg = _cfg(fundamental_cache_ttl_seconds=120)
    assert DataFetcherManager._should_cache_fundamental_context({"status": "failed"}) is False
    assert DataFetcherManager._should_cache_fundamental_context({"status": "ok"}) is True
    loaded = manager._get_or_load_fundamental_context(
        "600519",
        1.5,
        lambda: {"status": "failed"},
        market="cn",
        config=cfg,
    )
    assert loaded["status"] == "failed"
    assert manager._fundamental_cache == {}
