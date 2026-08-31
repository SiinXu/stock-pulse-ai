# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and calendar tests for the Tushare trade-time slice.

Issue #1068: ``_get_china_now``, ``_get_trade_dates``, ``_pick_trade_date``,
and ``get_trade_time`` moved into ``src/data_provider/tushare_parts/trade_time.py``
and are rebound onto the public ``TushareFetcher`` class.
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

import src.data_provider.tushare_fetcher as tushare_mod
import src.data_provider.tushare_parts.trade_time as trade_time_mod
from src.data_provider.tushare_fetcher import TushareFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "tushare_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "tushare_parts" / "trade_time.py"

MOVED = (
    "_get_china_now",
    "_get_trade_dates",
    "_pick_trade_date",
    "get_trade_time",
)

METHOD_SIGNATURES = {
    "_get_china_now": ["self"],
    "_get_trade_dates": ["self", "end_date"],
    "_pick_trade_date": ["trade_dates", "use_today"],
    "get_trade_time": ["self", "early_time", "late_time"],
}

# Stay on the facade class body; the moved bodies must not pull them along.
FACADE_SIBLINGS = (
    "get_chip_distribution",
    "compute_cyq_metrics",
    "is_available",
    "_determine_priority",
)

# Domains this package already owned before the slice; binding must still work.
PRE_EXISTING_BOUND = (
    "get_daily_data",
    "_convert_stock_code",
    "get_main_indices",
    "get_stock_name",
    "get_realtime_quote",
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


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(TushareFetcher, name))


def test_pick_trade_date_stays_a_staticmethod() -> None:
    assert isinstance(TushareFetcher.__dict__["_pick_trade_date"], staticmethod)


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


def test_get_trade_time_defaults_are_unchanged() -> None:
    signature = inspect.signature(TushareFetcher.get_trade_time)
    assert signature.parameters["early_time"].default == "09:30"
    assert signature.parameters["late_time"].default == "16:30"
    signature = inspect.signature(TushareFetcher._get_trade_dates)
    assert signature.parameters["end_date"].default is None


def test_source_and_facade_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(trade_time_mod._TradeTimeMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(TushareFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == trade_time_mod.__name__
    assert tuple(source_names) == trade_time_mod.EXPECTED_TRADE_TIME_METHOD_NAMES == MOVED


def test_owner_module_declares_exactly_the_slice() -> None:
    assert trade_time_mod.EXPECTED_TRADE_TIME_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_TradeTimeMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


@pytest.mark.parametrize("sibling", FACADE_SIBLINGS)
def test_chip_and_availability_helpers_stay_on_the_facade(sibling) -> None:
    """The moved bodies must not pull chip or availability helpers with them."""

    assert sibling in _facade_class_methods(), sibling


def test_calendar_cache_attributes_stay_on_the_facade() -> None:
    source = FACADE_PATH.read_text(encoding="utf-8")
    assert "self.date_list" in source
    assert "self._date_list_end" in source
    fetcher = _make_fetcher()
    assert fetcher.date_list is None
    assert fetcher._date_list_end is None


def test_rate_limited_client_state_stays_on_the_facade() -> None:
    source = FACADE_PATH.read_text(encoding="utf-8")
    for attribute in ("_api", "_check_rate_limit", "_call_api_with_rate_limit"):
        assert attribute in source, attribute
    assert "ZoneInfo" in vars(tushare_mod)
    assert "timedelta" in vars(tushare_mod)


@pytest.mark.parametrize("name", PRE_EXISTING_BOUND)
def test_previously_bound_domains_are_not_disturbed(name) -> None:
    method = getattr(TushareFetcher, name, None)
    assert callable(method), name


def test_moved_bodies_still_reach_a_patched_facade_global() -> None:
    original = tushare_mod.logger
    sentinel = MagicMock()
    try:
        tushare_mod.logger = sentinel
        fetcher = _make_fetcher()
        fetcher._api = None
        assert fetcher._get_trade_dates() == []
        fetcher._api = MagicMock()
        with patch.object(fetcher, "_get_china_now", return_value=datetime(2026, 3, 17, 20, 0)):
            fetcher._call_api_with_rate_limit = MagicMock(return_value=pd.DataFrame())
            assert fetcher._get_trade_dates("20260317") == []
        sentinel.warning.assert_called()
    finally:
        tushare_mod.logger = original


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("tushare_fetcher" in module for module in imported)


def test_production_imports_stay_on_the_facade() -> None:
    src_root = REPO_ROOT / "src"
    offenders = []
    for path in src_root.rglob("*.py"):
        if "tushare_parts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "tushare_parts.trade_time" in text and path.name != "tushare_fetcher.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_owner_reload_rebinds_and_leaves_other_domains_intact() -> None:
    importlib.reload(trade_time_mod)
    for name in MOVED:
        method = _descriptor_function(TushareFetcher.__dict__[name])
        assert method.__globals__ is vars(tushare_mod), name
        assert method.__qualname__ == f"TushareFetcher.{name}", name
    assert isinstance(TushareFetcher.__dict__["_pick_trade_date"], staticmethod)
    for name in PRE_EXISTING_BOUND:
        assert callable(getattr(TushareFetcher, name, None)), name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.tushare_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_trade_time(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(tushare_mod), expected_names=MOVED,
        )


def test_missing_api_returns_empty_calendar_without_network() -> None:
    fetcher = _make_fetcher()
    fetcher._api = None
    assert fetcher._get_trade_dates() == []
    assert fetcher.get_trade_time() is None


def test_empty_calendar_fails_open_to_none() -> None:
    fetcher = _make_fetcher()
    fetcher._api.trade_cal.return_value = pd.DataFrame()
    with patch.object(
        fetcher, "_get_china_now", return_value=datetime(2026, 3, 17, 20, 0)
    ), patch.object(fetcher, "_check_rate_limit"):
        assert fetcher.get_trade_time() is None
    assert fetcher.date_list == []
    assert fetcher._date_list_end == "20260317"


def test_pick_trade_date_empty_list_returns_none() -> None:
    assert TushareFetcher._pick_trade_date([], True) is None
    assert TushareFetcher._pick_trade_date([], False) is None


def test_get_trade_time_refreshes_trade_calendar_when_day_changes() -> None:
    fetcher = _make_fetcher()
    fetcher._api.trade_cal.side_effect = [
        pd.DataFrame({"cal_date": ["20260317", "20260314"], "is_open": [1, 1]}),
        pd.DataFrame({"cal_date": ["20260318", "20260317"], "is_open": [1, 1]}),
    ]

    with patch.object(
        fetcher,
        "_get_china_now",
        side_effect=[
            datetime(2026, 3, 17, 20, 0),
            datetime(2026, 3, 17, 20, 0),
            datetime(2026, 3, 18, 20, 0),
            datetime(2026, 3, 18, 20, 0),
        ],
    ), patch.object(fetcher, "_check_rate_limit") as rate_limit_mock:
        assert fetcher.get_trade_time(early_time="00:00", late_time="19:00") == "20260317"
        assert fetcher.get_trade_time(early_time="00:00", late_time="19:00") == "20260318"

    assert fetcher._api.trade_cal.call_count == 2
    assert rate_limit_mock.call_count == 2


def test_get_trade_time_saturday_returns_friday() -> None:
    fetcher = _make_fetcher()
    fetcher._api.trade_cal.return_value = pd.DataFrame(
        {
            "cal_date": [
                "20260314",
                "20260315",
                "20260316",
                "20260317",
                "20260318",
                "20260319",
                "20260320",
                "20260321",
            ],
            "is_open": [0, 0, 1, 1, 1, 1, 1, 0],
        }
    )

    with patch.object(
        fetcher,
        "_get_china_now",
        side_effect=[datetime(2026, 3, 21, 10, 0)] * 2,
    ), patch.object(fetcher, "_check_rate_limit"):
        result = fetcher.get_trade_time(early_time="00:00", late_time="19:00")

    assert result == "20260320"


def test_get_trade_time_in_window_returns_previous_day() -> None:
    fetcher = _make_fetcher()
    fetcher._api.trade_cal.return_value = pd.DataFrame(
        {"cal_date": ["20260319", "20260320"], "is_open": [1, 1]}
    )

    with patch.object(
        fetcher,
        "_get_china_now",
        side_effect=[datetime(2026, 3, 20, 10, 0)] * 2,
    ), patch.object(fetcher, "_check_rate_limit"):
        result = fetcher.get_trade_time(early_time="00:00", late_time="19:00")

    assert result == "20260319"


def test_chip_distribution_calls_trade_time_through_self() -> None:
    fetcher = _make_fetcher()
    fetcher._api.cyq_chips.return_value = pd.DataFrame(
        {"price": [9.0, 10.0, 11.0], "percent": [20.0, 50.0, 30.0]}
    )
    fetcher._api.daily.return_value = pd.DataFrame({"close": [10.5]})

    with patch.object(
        fetcher, "get_trade_time", return_value="20260317"
    ) as trade_time, patch.object(fetcher, "_check_rate_limit"):
        chip = fetcher.get_chip_distribution("600519")

    trade_time.assert_called_once_with(early_time="00:00", late_time="19:00")
    assert chip is not None
    assert chip.date == "2026-03-17"


def test_sector_rankings_calls_trade_time_through_self() -> None:
    fetcher = _make_fetcher()
    fetcher._api.moneyflow_ind_ths.return_value = pd.DataFrame(
        {"industry": ["AI", "消费"], "pct_change": [1.8, -0.6]}
    )

    with patch.object(
        fetcher, "get_trade_time", return_value="20260317"
    ) as trade_time, patch.object(fetcher, "_check_rate_limit"):
        top, bottom = fetcher.get_sector_rankings(n=1)

    trade_time.assert_called_once_with(early_time="00:00", late_time="15:30")
    assert top == [{"name": "AI", "change_pct": 1.8}]
    assert bottom == [{"name": "消费", "change_pct": -0.6}]
