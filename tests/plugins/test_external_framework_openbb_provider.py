# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline contract tests for the OpenBB external-framework demonstration plugin.

These tests never import a real OpenBB package and never touch the network.
They exercise the copy under docs/examples/external-framework-data-provider/.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pandas as pd
import pytest

from data_provider import DataFetcherManager, DataProvider
from src.application_services import ApplicationServices
from src.plugins import PLUGIN_APPLICATION_VERSION, PluginManager
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE_PLUGIN = (
    _REPOSITORY_ROOT
    / "docs"
    / "examples"
    / "external-framework-data-provider"
)
_PLUGIN_ID = "stockpulse.openbb-data-provider"
_PROVIDER_ID = "openbb-daily-data"
_PROVIDER_NAME = "OpenBBAdapterProvider"


def _load_plugin_module():
    """Import the demonstration plugin.py by path (not installed as a package)."""

    plugin_path = _EXAMPLE_PLUGIN / "plugin.py"
    module_name = "stockpulse_docs_examples_openbb_data_provider_plugin"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Ensure re-imports in the same session see a clean module object.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _FixtureOpenBBClient:
    """Injectable historical client used instead of the real OpenBB SDK."""

    def __init__(self, frame: pd.DataFrame | None = None, error: Exception | None = None):
        self.frame = frame
        self.error = error
        self.calls: list[dict[str, object]] = []

    def fetch_historical(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        timeout_seconds: float,
    ) -> pd.DataFrame:
        self.calls.append(
            {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.frame is not None
        return self.frame.copy()


class _FallbackProvider(DataProvider):
    name = "OpenBBDemoTestFallback"
    priority = 500

    def get_daily_data(
        self,
        stock_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 30,
    ) -> pd.DataFrame:
        del stock_code, start_date, end_date, days
        return pd.DataFrame(
            {
                "date": ["2026-01-02"],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1],
                "amount": [1.0],
                "pct_chg": [0.0],
            }
        )


@pytest.fixture(autouse=True)
def _deterministic_provider_policy(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PROVIDER_ADAPTIVE_PRIORITY_ENABLED", "false")
    monkeypatch.setenv("PROVIDER_CIRCUIT_BREAKER_ENABLED", "false")
    monkeypatch.setenv("PROVIDER_DAILY_CACHE_ENABLED", "false")
    DataFetcherManager.reset_daily_source_health()
    yield
    DataFetcherManager.reset_daily_source_health()


def _sample_upstream_frame() -> pd.DataFrame:
    # Heterogeneous OpenBB-like columns (mixed case, DatetimeIndex, no amount/pct).
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.5],
            "Close": [101.0, 102.5],
            "Volume": [1000, 1100],
        },
        index=pd.to_datetime(["2026-02-02", "2026-02-03"]),
    )
    frame.index.name = "date"
    return frame


class _RealShapedOBBject:
    """Minimal public OBBject conversion surface from supported OpenBB 4.7."""

    def __init__(self, frame: pd.DataFrame, method_name: str):
        self._frame = frame
        if method_name == "to_df":
            self.to_df = lambda: self._frame.copy()
        elif method_name == "to_dataframe":
            self.to_dataframe = lambda: self._frame.copy()


class _HistoricalEndpoint:
    def __init__(self, result: object = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    def historical(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _obb_with_endpoint(endpoint: _HistoricalEndpoint) -> SimpleNamespace:
    return SimpleNamespace(
        equity=SimpleNamespace(
            price=SimpleNamespace(historical=endpoint.historical),
        )
    )


def test_example_package_layout_and_manifest_contract() -> None:
    assert (_EXAMPLE_PLUGIN / "plugin.py").is_file()
    assert (_EXAMPLE_PLUGIN / "README.md").is_file()
    manifest_path = _EXAMPLE_PLUGIN / "manifest.json"
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["id"] == _PLUGIN_ID
    assert manifest["apiVersion"] == "1"
    assert manifest["entrypoint"] == "plugin.py:Plugin"
    assert manifest["minAppVersion"] == PLUGIN_APPLICATION_VERSION
    assert "openbb" in " ".join(manifest.get("permissions", [])).lower() or any(
        "openbb" in str(item).lower() for item in manifest.get("permissions", [])
    )


def test_normalize_openbb_daily_frame_maps_columns_and_derives_amount_pct() -> None:
    module = _load_plugin_module()
    normalized = module.normalize_openbb_daily_frame(_sample_upstream_frame())

    assert list(normalized.columns) == [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "pct_chg",
    ]
    assert normalized["date"].tolist() == ["2026-02-02", "2026-02-03"]
    assert normalized["close"].tolist() == [101.0, 102.5]
    assert normalized["volume"].tolist() == [1000, 1100]
    # amount derived from close * volume when upstream omits it
    assert normalized["amount"].tolist() == [101000.0, 112750.0]
    assert normalized["pct_chg"].iloc[0] == pytest.approx(0.0)
    assert normalized["pct_chg"].iloc[1] == pytest.approx((102.5 / 101.0 - 1.0) * 100.0)


@pytest.mark.parametrize("method_name", ["to_df", "to_dataframe"])
def test_supported_openbb_boundary_performs_one_provider_call_and_converts_obbject(
    method_name: str,
) -> None:
    module = _load_plugin_module()
    endpoint = _HistoricalEndpoint(
        result=_RealShapedOBBject(_sample_upstream_frame(), method_name)
    )

    frame = module._call_openbb_historical(
        _obb_with_endpoint(endpoint),
        symbol="AAPL",
        start_date="2026-02-01",
        end_date="2026-02-10",
    )

    assert frame.equals(_sample_upstream_frame())
    assert endpoint.calls == [
        {
            "symbol": "AAPL",
            "provider": "yfinance",
            "start_date": "2026-02-01",
            "end_date": "2026-02-10",
        }
    ]


def test_sdk_client_runs_supported_fake_openbb_through_real_worker_protocol(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_plugin_module()
    fake_package = tmp_path / "openbb"
    fake_package.mkdir()
    calls_path = tmp_path / "calls.json"
    fake_package.joinpath("__init__.py").write_text(
        """
import json
import os
from pathlib import Path

import pandas as pd


class _Result:
    def to_df(self):
        return pd.DataFrame(
            {
                "date": ["2026-02-02", "2026-02-03"],
                "open": [10.0, 11.0],
                "high": [11.0, 12.0],
                "low": [9.0, 10.0],
                "close": [10.5, 11.5],
                "volume": [100, 110],
            }
        )


class _Price:
    def historical(self, **kwargs):
        Path(os.environ["OPENBB_FAKE_CALLS_PATH"]).write_text(
            json.dumps([kwargs]),
            encoding="utf-8",
        )
        return _Result()


class _Equity:
    price = _Price()


class _OBB:
    equity = _Equity()


obb = _OBB()
""".lstrip(),
        encoding="utf-8",
    )
    dist_info = tmp_path / "openbb-4.7.2.dist-info"
    dist_info.mkdir()
    dist_info.joinpath("METADATA").write_text(
        "Metadata-Version: 2.1\nName: openbb\nVersion: 4.7.2\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("OPENBB_FAKE_CALLS_PATH", str(calls_path))

    provider = module.OpenBBDailyDataProvider(timeout_seconds=5.0)
    frame = provider.get_daily_data(
        "HK00700",
        start_date="2026-02-01",
        end_date="2026-02-10",
    )

    assert frame["date"].tolist() == ["2026-02-02", "2026-02-03"]
    assert frame["close"].tolist() == [10.5, 11.5]
    assert json.loads(calls_path.read_text(encoding="utf-8")) == [
        {
            "symbol": "0700.HK",
            "provider": "yfinance",
            "start_date": "2026-02-01",
            "end_date": "2026-02-10",
        }
    ]


def test_sdk_internal_type_error_is_not_retried_or_reinterpreted() -> None:
    module = _load_plugin_module()
    endpoint = _HistoricalEndpoint(error=TypeError("provider-internal failure"))

    with pytest.raises(TypeError, match="provider-internal failure"):
        module._call_openbb_historical(
            _obb_with_endpoint(endpoint),
            symbol="AAPL",
            start_date=None,
            end_date=None,
        )

    assert endpoint.calls == [{"symbol": "AAPL", "provider": "yfinance"}]


@pytest.mark.parametrize(
    ("host_symbol", "provider_symbol"),
    [
        ("AAPL", "AAPL"),
        ("HKD", "HKD"),
        ("BJ", "BJ"),
        ("600519", "600519.SS"),
        ("600519.SH", "600519.SS"),
        ("SH600519", "600519.SS"),
        ("000001", "000001.SZ"),
        ("000001.SZ", "000001.SZ"),
        ("SZ000001", "000001.SZ"),
        ("HK00700", "0700.HK"),
        ("00700.HK", "0700.HK"),
        ("0700", "0700.HK"),
    ],
)
def test_provider_maps_all_advertised_stockpulse_symbols_before_sdk_call(
    host_symbol: str,
    provider_symbol: str,
) -> None:
    module = _load_plugin_module()
    client = _FixtureOpenBBClient(frame=_sample_upstream_frame())
    provider = module.OpenBBDailyDataProvider(client=client)

    provider.get_daily_data(
        host_symbol,
        start_date="2026-02-01",
        end_date="2026-02-10",
    )

    assert client.calls[0]["symbol"] == provider_symbol


@pytest.mark.parametrize("symbol", ["920748", "BJ920748", "920748.BJ"])
def test_bse_symbols_fail_before_sdk_call(symbol: str) -> None:
    module = _load_plugin_module()
    client = _FixtureOpenBBClient(frame=_sample_upstream_frame())
    provider = module.OpenBBDailyDataProvider(client=client)

    with pytest.raises(ValueError, match="BSE symbol"):
        provider.get_daily_data(symbol)

    assert client.calls == []


def test_openbb_version_range_is_explicit() -> None:
    module = _load_plugin_module()
    module._validate_openbb_version("4.7.0")
    module._validate_openbb_version("4.7.2")
    with pytest.raises(RuntimeError, match=r"openbb>=4\.7,<4\.8"):
        module._validate_openbb_version("4.6.0")
    with pytest.raises(RuntimeError, match=r"openbb>=4\.7,<4\.8"):
        module._validate_openbb_version("4.8.0")


def test_production_timeout_kills_worker_before_late_side_effect(
    tmp_path: Path,
) -> None:
    module = _load_plugin_module()
    marker = tmp_path / "worker-survived.txt"
    command = [
        sys.executable,
        "-c",
        (
            "import pathlib, sys, time; "
            "time.sleep(0.6); "
            "pathlib.Path(sys.argv[1]).write_text('survived', encoding='utf-8')"
        ),
        str(marker),
    ]

    started = time.monotonic()
    with pytest.raises(TimeoutError, match="adapter timeout"):
        module._run_openbb_worker(
            {"symbol": "AAPL", "start_date": None, "end_date": None},
            timeout_seconds=0.1,
            command=command,
        )
    elapsed = time.monotonic() - started

    assert elapsed < 0.8
    time.sleep(0.65)
    assert not marker.exists(), "timed-out worker must be terminated and reaped"


def test_reverse_and_duplicate_dates_are_resolved_before_percentage_change() -> None:
    module = _load_plugin_module()
    frame = pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-01", "2026-01-02T12:00:00Z"],
            "open": [110.0, 100.0, 111.0],
            "high": [111.0, 101.0, 112.0],
            "low": [109.0, 99.0, 110.0],
            "close": [110.0, 100.0, 111.0],
            "volume": [10, 9, 11],
        }
    )

    normalized = module.normalize_openbb_daily_frame(frame)

    assert normalized["date"].tolist() == ["2026-01-01", "2026-01-02"]
    assert normalized["close"].tolist() == [100.0, 111.0]
    assert normalized["pct_chg"].tolist() == pytest.approx([0.0, 11.0])
    assert normalized["amount"].tolist() == [900.0, 1221.0]


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ("missing_volume", "volume"),
        ("nonnumeric_open", "open"),
        ("nonfinite_high", "high"),
        ("zero_close", "prices must be positive"),
        ("negative_volume", "volume must be non-negative"),
        ("fractional_volume", "integer-compatible"),
        ("impossible_ohlc", "OHLC bounds"),
        ("invalid_date", "required date"),
        ("negative_amount", "amount must be finite"),
    ],
)
def test_malformed_required_bars_fail_the_provider_attempt(
    case: str,
    match: str,
) -> None:
    module = _load_plugin_module()
    frame = _sample_upstream_frame().reset_index()
    if case == "missing_volume":
        frame = frame.drop(columns=["Volume"])
    elif case == "nonnumeric_open":
        frame["Open"] = frame["Open"].astype(object)
        frame.loc[0, "Open"] = "bad"
    elif case == "nonfinite_high":
        frame.loc[0, "High"] = float("inf")
    elif case == "zero_close":
        frame.loc[0, "Close"] = 0.0
    elif case == "negative_volume":
        frame.loc[0, "Volume"] = -1
    elif case == "fractional_volume":
        frame["Volume"] = frame["Volume"].astype("float64")
        frame.loc[0, "Volume"] = 1.5
    elif case == "impossible_ohlc":
        frame.loc[0, "High"] = 98.0
    elif case == "invalid_date":
        frame["date"] = frame["date"].astype(object)
        frame.loc[0, "date"] = "not-a-date"
    elif case == "negative_amount":
        frame["amount"] = [-1.0, 1.0]

    with pytest.raises(ValueError, match=match):
        module.normalize_openbb_daily_frame(frame)


def test_missing_openbb_dependency_raises_explicit_error_not_empty_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_plugin_module()
    provider = module.OpenBBDailyDataProvider()
    monkeypatch.setattr(
        module,
        "_run_openbb_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            module.MissingOpenBBDependencyError(module._MISSING_OPENBB_MESSAGE)
        ),
    )

    with pytest.raises(module.MissingOpenBBDependencyError) as excinfo:
        provider.get_daily_data("AAPL", start_date="2026-01-01", end_date="2026-01-10")

    message = str(excinfo.value)
    assert "OpenBB is not installed" in message
    assert "does not install" in message.lower() or "will not" in message.lower() or "does not" in message


def test_empty_upstream_frame_raises_for_host_fallback() -> None:
    module = _load_plugin_module()
    client = _FixtureOpenBBClient(frame=pd.DataFrame())
    provider = module.OpenBBDailyDataProvider(client=client)

    with pytest.raises(RuntimeError, match="empty"):
        provider.get_daily_data("AAPL", start_date="2026-01-01", end_date="2026-01-10")


def test_malformed_openbb_payload_is_attributed_before_exact_manager_fallback() -> None:
    module = _load_plugin_module()
    malformed = _sample_upstream_frame().drop(columns=["Volume"])
    openbb_provider = module.OpenBBDailyDataProvider(
        client=_FixtureOpenBBClient(frame=malformed)
    )
    manager = DataFetcherManager(fetchers=[openbb_provider, _FallbackProvider()])

    token = activate_run_diagnostic_context(
        trace_id="trace-openbb-malformed-fallback",
        stock_code="600519",
    )
    try:
        frame, source = manager.get_daily_data(
            "600519",
            start_date="2026-02-01",
            end_date="2026-02-10",
        )
        diagnostics = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert source == "OpenBBDemoTestFallback"
    assert frame["close"].tolist() == [1.0]
    assert [run["provider"] for run in diagnostics["provider_runs"]] == [
        _PROVIDER_NAME,
        "OpenBBDemoTestFallback",
    ]
    assert diagnostics["provider_runs"][0]["success"] is False
    assert diagnostics["provider_runs"][0]["error_type"] == "ValueError"
    assert diagnostics["provider_runs"][0]["fallback_to"] == "OpenBBDemoTestFallback"


def test_fixture_client_returns_normalized_daily_data() -> None:
    module = _load_plugin_module()
    client = _FixtureOpenBBClient(frame=_sample_upstream_frame())
    provider = module.OpenBBDailyDataProvider(client=client, timeout_seconds=9.0)

    frame = provider.get_daily_data(
        "AAPL",
        start_date="2026-02-01",
        end_date="2026-02-10",
    )

    assert provider.name == _PROVIDER_NAME
    assert list(frame.columns) == [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "pct_chg",
    ]
    assert len(frame) == 2
    assert client.calls == [
        {
            "symbol": "AAPL",
            "start_date": "2026-02-01",
            "end_date": "2026-02-10",
            "timeout_seconds": 9.0,
        }
    ]


def test_plugin_remains_opt_in_when_plugins_dir_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PLUGINS_DIR", raising=False)
    providers = DataFetcherManager(fetchers=[_FallbackProvider()])
    plugins = PluginManager(
        application_version=PLUGIN_APPLICATION_VERSION,
        registry=providers.plugin_registry,
    )
    services = ApplicationServices(plugin_manager=plugins)
    try:
        assert services.start_plugins() == ()
        assert services.external_plugin_results == ()
        assert _PLUGIN_ID not in plugins.plugin_ids()
        assert _PROVIDER_NAME not in providers.available_fetchers
    finally:
        services.close()


def test_plugin_registers_loads_routes_and_disables(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Load the real package from PLUGINS_DIR; missing OpenBB falls back host-side."""

    shutil.copytree(_EXAMPLE_PLUGIN, tmp_path / "external-framework-data-provider")
    monkeypatch.setenv("PLUGINS_DIR", str(tmp_path))

    providers = DataFetcherManager(fetchers=[_FallbackProvider()])
    plugins = PluginManager(
        application_version=PLUGIN_APPLICATION_VERSION,
        registry=providers.plugin_registry,
    )
    services = ApplicationServices(plugin_manager=plugins)

    try:
        loads = services.start_plugins()

        discovery = [
            (
                result.candidate,
                result.plugin_id,
                result.success,
                result.state,
                result.error_code,
            )
            for result in services.external_plugin_results
        ]
        assert discovery == [
            (
                "external-framework-data-provider",
                _PLUGIN_ID,
                True,
                "registered",
                None,
            )
        ]
        assert [
            (result.plugin_id, result.operation, result.success, result.state)
            for result in loads
        ] == [(_PLUGIN_ID, "load", True, "enabled")]
        assert [
            registration.registration_id
            for registration in plugins.registrations("data_provider")
        ] == [_PROVIDER_ID]
        assert _PROVIDER_NAME in providers.available_fetchers

        # The example deliberately rejects unverified BSE/yfinance coverage before
        # any optional SDK call. The manager must continue its CN fallback chain.
        frame, source = providers.get_daily_data(
            "920748",
            start_date="2026-02-01",
            end_date="2026-02-10",
        )
        assert source == "OpenBBDemoTestFallback"
        assert not frame.empty
        assert frame["close"].tolist() == [1.0]

        disabled = plugins.disable(_PLUGIN_ID)
        assert (disabled.success, disabled.state, disabled.error_code) == (
            True,
            "disabled",
            None,
        )
        assert plugins.registrations("data_provider") == ()
        assert providers.available_fetchers == ["OpenBBDemoTestFallback"]
    finally:
        services.close()


def test_adapter_guide_documents_trust_and_extension_surface() -> None:
    en = (_REPOSITORY_ROOT / "docs" / "external-framework-adapter-guide.md").read_text(
        encoding="utf-8"
    )
    zh = (_REPOSITORY_ROOT / "docs" / "external-framework-adapter-guide_zh.md").read_text(
        encoding="utf-8"
    )
    for content in (en, zh):
        assert "data_provider" in content
        assert "PLUGINS_DIR" in content
        assert "openbb" in content.lower() or "OpenBB" in content
        # Trust responsibility (EN or ZH phrasing)
        assert (
            "full process privileges" in content
            or "完整进程权限" in content
            or "no sandbox" in content
            or "无沙箱" in content
        )
        assert "No new extension points" in content or "不新增扩展点" in content
        assert "external-framework-data-provider" in content


def test_missing_dependency_path_via_import_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directly cover _import_openbb without relying on builtins.__import__ quirks."""

    module = _load_plugin_module()

    real_import = __import__

    def _block_openbb(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "openbb" or name.startswith("openbb."):
            raise ImportError("No module named 'openbb'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _block_openbb)
    with pytest.raises(module.MissingOpenBBDependencyError, match="OpenBB is not installed"):
        module._import_openbb()
