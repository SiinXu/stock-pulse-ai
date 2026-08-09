# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline contract tests for the OpenBB external-framework demonstration plugin.

These tests never import a real OpenBB package and never touch the network.
They exercise the copy under docs/examples/external-framework-data-provider/.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from typing import Iterator

import pandas as pd
import pytest

from data_provider import DataFetcherManager, DataProvider
from src.application_services import ApplicationServices
from src.plugins import PLUGIN_APPLICATION_VERSION, PluginManager

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


def test_example_package_layout_and_manifest_contract() -> None:
    assert (_EXAMPLE_PLUGIN / "plugin.py").is_file()
    assert (_EXAMPLE_PLUGIN / "README.md").is_file()
    manifest_path = _EXAMPLE_PLUGIN / "manifest.json"
    assert manifest_path.is_file()

    import json

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


def test_missing_openbb_dependency_raises_explicit_error_not_empty_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_plugin_module()
    provider = module.OpenBBDailyDataProvider()

    real_import = __import__

    def _block_openbb(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "openbb" or name.startswith("openbb."):
            raise ImportError("No module named 'openbb'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _block_openbb)

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

        # Without a real OpenBB install, the live factory raises explicitly on use.
        # That must not crash the manager: eligible fallback continues (CN symbol).
        frame, source = providers.get_daily_data(
            "600519",
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

    def _raise_import():
        raise module.MissingOpenBBDependencyError(module._MISSING_OPENBB_MESSAGE)

    monkeypatch.setattr(module, "_import_openbb", _raise_import)
    client = module._SdkOpenBBClient()
    with pytest.raises(module.MissingOpenBBDependencyError, match="OpenBB is not installed"):
        client.fetch_historical(
            symbol="AAPL",
            start_date="2026-01-01",
            end_date="2026-01-05",
            timeout_seconds=1.0,
        )
