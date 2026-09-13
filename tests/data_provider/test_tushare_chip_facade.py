# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and characterization tests for the Tushare chip slice.

Issue #1068: ``get_chip_distribution`` and ``compute_cyq_metrics`` moved into
``src/data_provider/tushare_parts/chip.py`` and are rebound onto the public
``TushareFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import src.data_provider._facade_bind as shared_bind
import src.data_provider.tushare_fetcher as tushare_mod
import src.data_provider.tushare_parts.chip as chip_mod
import src.data_provider.tushare_parts.facade_bind as tushare_bind
from src.data_provider.tushare_fetcher import TushareFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "tushare_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "tushare_parts" / "chip.py"

MOVED = (
    "get_chip_distribution",
    "compute_cyq_metrics",
)

METHOD_SIGNATURES = {
    "get_chip_distribution": ["self", "stock_code"],
    "compute_cyq_metrics": ["self", "df", "current_price"],
}

FACADE_SIBLINGS = (
    "__init__",
    "_determine_priority",
    "is_available",
)

PRE_EXISTING_BOUND = (
    "get_trade_time",
    "get_realtime_quote",
    "get_daily_data",
)

CHINESE_METRIC_KEYS = (
    "获利比例",
    "平均成本",
    "90成本-低",
    "90成本-高",
    "90集中度",
    "70成本-低",
    "70成本-高",
    "70集中度",
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


def _make_fetcher() -> TushareFetcher:
    with patch.object(TushareFetcher, "_init_api", return_value=None):
        fetcher = TushareFetcher()
    fetcher._api = MagicMock()
    return fetcher


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TushareFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _chip_frame() -> pd.DataFrame:
    return pd.DataFrame({"price": [9.0, 10.0, 11.0], "percent": [20.0, 50.0, 30.0]})


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(TushareFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_are_instance_methods(name) -> None:
    descriptor = TushareFetcher.__dict__[name]
    assert not isinstance(descriptor, (staticmethod, classmethod)), name
    assert inspect.isfunction(_descriptor_function(descriptor)), name


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = _descriptor_function(TushareFetcher.__dict__[name])
    assert method.__module__ == "src.data_provider.tushare_fetcher", name
    assert method.__qualname__ == f"TushareFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    method = _descriptor_function(TushareFetcher.__dict__[name])
    assert method.__globals__ is vars(tushare_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(TushareFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def test_source_and_facade_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(chip_mod._ChipMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(TushareFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == chip_mod.__name__
    assert tuple(source_names) == chip_mod.EXPECTED_CHIP_METHOD_NAMES == MOVED


def test_owner_module_declares_exactly_the_slice() -> None:
    assert chip_mod.EXPECTED_CHIP_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_ChipMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


@pytest.mark.parametrize("sibling", FACADE_SIBLINGS)
def test_availability_helpers_stay_on_the_facade(sibling) -> None:
    assert sibling in _facade_class_methods(), sibling


@pytest.mark.parametrize("name", PRE_EXISTING_BOUND)
def test_previously_bound_domains_are_not_disturbed(name) -> None:
    method = getattr(TushareFetcher, name, None)
    assert callable(method), name


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("tushare_fetcher" in module for module in imported)


def test_binder_is_the_shared_reexport() -> None:
    assert chip_mod.bind_methods_from_class is tushare_bind.bind_methods_from_class
    assert tushare_bind.bind_methods_from_class is shared_bind.bind_methods_from_class


def test_production_imports_stay_on_the_facade() -> None:
    src_root = REPO_ROOT / "src"
    offenders = []
    for path in src_root.rglob("*.py"):
        if "tushare_parts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "tushare_parts.chip" in text and path.name != "tushare_fetcher.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_owner_reload_rebinds_and_leaves_other_domains_intact() -> None:
    importlib.reload(chip_mod)
    for name in MOVED:
        method = _descriptor_function(TushareFetcher.__dict__[name])
        assert method.__globals__ is vars(tushare_mod), name
        assert method.__qualname__ == f"TushareFetcher.{name}", name
    for name in PRE_EXISTING_BOUND:
        assert callable(getattr(TushareFetcher, name, None)), name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.tushare_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_chip_distribution(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(tushare_mod), expected_names=MOVED,
        )


def test_fetcher_still_instantiates_with_init_api_patched() -> None:
    fetcher = _make_fetcher()
    assert isinstance(fetcher, TushareFetcher)
    assert fetcher._api is not None


def test_patched_us_classifier_is_followed_by_the_rebound_body() -> None:
    original = tushare_mod._is_us_code
    original_logger = tushare_mod.logger
    sentinel = MagicMock()
    try:
        tushare_mod._is_us_code = lambda code: True
        tushare_mod.logger = sentinel
        fetcher = _make_fetcher()
        with patch.object(fetcher, "_call_api_with_rate_limit") as api_mock:
            assert fetcher.get_chip_distribution("600519") is None
        api_mock.assert_not_called()
        sentinel.warning.assert_called()
        assert "不支持美股" in sentinel.warning.call_args.args[0]
    finally:
        tushare_mod._is_us_code = original
        tushare_mod.logger = original_logger


def test_patched_etf_classifier_is_followed_by_the_rebound_body() -> None:
    original_us = tushare_mod._is_us_code
    original_etf = tushare_mod._is_etf_code
    original_logger = tushare_mod.logger
    sentinel = MagicMock()
    try:
        tushare_mod._is_us_code = lambda code: False
        tushare_mod._is_etf_code = lambda code: True
        tushare_mod.logger = sentinel
        fetcher = _make_fetcher()
        with patch.object(fetcher, "_call_api_with_rate_limit") as api_mock:
            assert fetcher.get_chip_distribution("600519") is None
        api_mock.assert_not_called()
        sentinel.warning.assert_called()
        assert "不支持 ETF" in sentinel.warning.call_args.args[0]
    finally:
        tushare_mod._is_us_code = original_us
        tushare_mod._is_etf_code = original_etf
        tushare_mod.logger = original_logger


def test_patched_hk_classifier_is_followed_by_the_rebound_body() -> None:
    original_us = tushare_mod._is_us_code
    original_etf = tushare_mod._is_etf_code
    original_hk = tushare_mod._is_hk_market
    original_logger = tushare_mod.logger
    sentinel = MagicMock()
    try:
        tushare_mod._is_us_code = lambda code: False
        tushare_mod._is_etf_code = lambda code: False
        tushare_mod._is_hk_market = lambda code: True
        tushare_mod.logger = sentinel
        fetcher = _make_fetcher()
        with patch.object(fetcher, "_call_api_with_rate_limit") as api_mock:
            assert fetcher.get_chip_distribution("600519") is None
        api_mock.assert_not_called()
        sentinel.warning.assert_called()
        assert "不支持港股" in sentinel.warning.call_args.args[0]
    finally:
        tushare_mod._is_us_code = original_us
        tushare_mod._is_etf_code = original_etf
        tushare_mod._is_hk_market = original_hk
        tushare_mod.logger = original_logger


@pytest.mark.parametrize("code", ("AAPL", "SPX", "QQQ", "BRK.B"))
def test_us_codes_return_none_without_api(code) -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "_call_api_with_rate_limit") as api_mock, patch.object(
        tushare_mod.logger, "warning"
    ) as warning:
        assert fetcher.get_chip_distribution(code) is None
    api_mock.assert_not_called()
    warning.assert_called()
    assert "不支持美股" in warning.call_args.args[0]


@pytest.mark.parametrize("code", ("510300", "sh510300", "159919"))
def test_etf_codes_return_none_without_api(code) -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "_call_api_with_rate_limit") as api_mock, patch.object(
        tushare_mod.logger, "warning"
    ) as warning:
        assert fetcher.get_chip_distribution(code) is None
    api_mock.assert_not_called()
    warning.assert_called()
    assert "不支持 ETF" in warning.call_args.args[0]


@pytest.mark.parametrize("code", ("HK00700", "00700.HK"))
def test_hk_codes_return_none_without_api(code) -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "_call_api_with_rate_limit") as api_mock, patch.object(
        tushare_mod.logger, "warning"
    ) as warning:
        assert fetcher.get_chip_distribution(code) is None
    api_mock.assert_not_called()
    warning.assert_called()
    assert "不支持港股" in warning.call_args.args[0]


def test_missing_trade_date_returns_none_without_convert_or_chips() -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "get_trade_time", return_value=None) as trade_time, patch.object(
        fetcher, "_convert_stock_code"
    ) as convert, patch.object(fetcher, "_call_api_with_rate_limit") as api_mock:
        assert fetcher.get_chip_distribution("600519") is None
    trade_time.assert_called_once_with(early_time="00:00", late_time="19:00")
    convert.assert_not_called()
    api_mock.assert_not_called()


@pytest.mark.parametrize("chips", (None, pd.DataFrame()))
def test_empty_chips_frame_returns_implicit_none_without_daily(chips) -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "get_trade_time", return_value="20260317"), patch.object(
        fetcher, "_convert_stock_code", return_value="600519.SH"
    ), patch.object(fetcher, "_call_api_with_rate_limit", return_value=chips) as api_mock:
        assert fetcher.get_chip_distribution("600519") is None
    api_mock.assert_called_once_with(
        "cyq_chips",
        ts_code="600519.SH",
        start_date="20260317",
        end_date="20260317",
    )


@pytest.mark.parametrize("daily", (None, pd.DataFrame()))
def test_empty_daily_frame_after_chips_returns_none(daily) -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "get_trade_time", return_value="20260317"), patch.object(
        fetcher, "_convert_stock_code", return_value="600519.SH"
    ), patch.object(
        fetcher, "_call_api_with_rate_limit", side_effect=[_chip_frame(), daily]
    ) as api_mock:
        assert fetcher.get_chip_distribution("600519") is None
    assert api_mock.call_count == 2
    assert api_mock.call_args_list[1].args[0] == "daily"


def test_chip_distribution_happy_path_metrics_and_source_default() -> None:
    fetcher = _make_fetcher()
    fetcher._api.trade_cal.return_value = pd.DataFrame(
        {"cal_date": ["20260317", "20260314"], "is_open": [1, 1]}
    )
    fetcher._api.cyq_chips.return_value = _chip_frame()
    fetcher._api.daily.return_value = pd.DataFrame({"close": [10.5]})

    with patch.object(
        fetcher, "_get_china_now", return_value=datetime(2026, 3, 17, 20, 0)
    ), patch.object(fetcher, "_check_rate_limit") as rate_limit_mock:
        chip = fetcher.get_chip_distribution("600519")

    assert chip is not None
    assert chip.date == "2026-03-17"
    assert chip.source == "akshare"
    assert chip.profit_ratio == pytest.approx(0.7)
    assert chip.avg_cost == pytest.approx(10.1)
    assert chip.concentration_90 == pytest.approx(0.1)
    assert chip.concentration_70 == pytest.approx(0.1)
    assert rate_limit_mock.call_count == 3


def test_compute_cyq_metrics_uses_chinese_keys() -> None:
    fetcher = _make_fetcher()
    metrics = fetcher.compute_cyq_metrics(_chip_frame(), 10.5)
    assert tuple(metrics) == CHINESE_METRIC_KEYS
    assert metrics["获利比例"] == pytest.approx(0.7)
    assert metrics["平均成本"] == pytest.approx(10.1)
    assert metrics["90集中度"] == pytest.approx(0.1)
    assert metrics["70集中度"] == pytest.approx(0.1)


def test_patched_compute_cyq_metrics_is_reached_through_self() -> None:
    fetcher = _make_fetcher()
    sentinel_metrics = {
        "获利比例": 0.5,
        "平均成本": 1.0,
        "90成本-低": 1.0,
        "90成本-高": 2.0,
        "90集中度": 0.2,
        "70成本-低": 1.0,
        "70成本-高": 2.0,
        "70集中度": 0.2,
    }
    with patch.object(fetcher, "get_trade_time", return_value="20260317"), patch.object(
        fetcher, "_convert_stock_code", return_value="600519.SH"
    ), patch.object(
        fetcher,
        "_call_api_with_rate_limit",
        side_effect=[_chip_frame(), pd.DataFrame({"close": [10.5]})],
    ), patch.object(
        fetcher, "compute_cyq_metrics", return_value=sentinel_metrics
    ) as compute:
        chip = fetcher.get_chip_distribution("600519")
    compute.assert_called_once()
    assert chip is not None
    assert chip.profit_ratio == 0.5
    assert chip.avg_cost == 1.0


def test_exception_path_returns_none_without_raising() -> None:
    fetcher = _make_fetcher()
    with patch.object(fetcher, "get_trade_time", side_effect=RuntimeError("boom")), patch.object(
        tushare_mod, "log_safe_exception"
    ) as logged:
        assert fetcher.get_chip_distribution("600519") is None
    logged.assert_called_once()
    assert logged.call_args.kwargs["error_code"] == "tushare_chip_distribution_failed"
