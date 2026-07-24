# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""End-to-end coverage for the repository's reference provider plugin."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterator

import pandas as pd
import pytest

from data_provider import DataFetcherManager, DataProvider
from src.application_services import ApplicationServices
from src.plugins import PLUGIN_APPLICATION_VERSION, PluginManager


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE_PLUGIN = _REPOSITORY_ROOT / "examples" / "plugins" / "example-provider"
_PLUGIN_ID = "stockpulse.example-provider"
_PROVIDER_ID = "example-daily-data"


class _FallbackProvider(DataProvider):
    name = "ExampleTestFallbackProvider"
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


def _build_services() -> tuple[ApplicationServices, DataFetcherManager, PluginManager]:
    providers = DataFetcherManager(fetchers=[_FallbackProvider()])
    plugins = PluginManager(
        application_version=PLUGIN_APPLICATION_VERSION,
        registry=providers.plugin_registry,
    )
    return (
        ApplicationServices(plugin_manager=plugins),
        providers,
        plugins,
    )


def _copy_example(root: Path, directory_name: str) -> None:
    shutil.copytree(_EXAMPLE_PLUGIN, root / directory_name)


def _write_failing_provider(root: Path) -> None:
    candidate = root / "01-failing-provider"
    candidate.mkdir()
    manifest = {
        "id": "stockpulse.failing-provider-test",
        "name": "Failing Provider Test",
        "version": "1.0.0",
        "minAppVersion": PLUGIN_APPLICATION_VERSION,
        "description": "Exercises provider factory isolation.",
        "author": "StockPulse Tests",
        "permissions": [],
        "apiVersion": "1",
        "entrypoint": "plugin.py:Plugin",
    }
    (candidate / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (candidate / "plugin.py").write_text(
        "from data_provider import DataProviderRegistration\n"
        "from src.plugins import Plugin as BasePlugin\n"
        "\n"
        "def create_provider():\n"
        "    raise RuntimeError('provider initialization failed')\n"
        "\n"
        "class Plugin(BasePlugin):\n"
        "    def onload(self, context):\n"
        "        registration = DataProviderRegistration(\n"
        "            provider_id='failing-provider-test',\n"
        "            factory=create_provider,\n"
        "            markets=frozenset({'cn'}),\n"
        "            capabilities=frozenset({'daily_data'}),\n"
        "        )\n"
        "        context.register(\n"
        "            'data_provider',\n"
        "            registration.provider_id,\n"
        "            registration,\n"
        "        )\n",
        encoding="utf-8",
    )


def test_reference_provider_remains_opt_in_when_plugins_dir_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PLUGINS_DIR", raising=False)
    services, providers, plugins = _build_services()

    try:
        assert services.start_plugins() == ()
        assert services.external_plugin_results == ()
        assert plugins.plugin_ids() == ()
        assert providers.available_fetchers == ["ExampleTestFallbackProvider"]
    finally:
        services.close()


def test_reference_provider_registers_loads_routes_and_disables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUGINS_DIR", str(_EXAMPLE_PLUGIN.parent))
    services, providers, plugins = _build_services()

    try:
        loads = services.start_plugins()

        assert [
            (
                result.candidate,
                result.plugin_id,
                result.success,
                result.state,
                result.error_code,
            )
            for result in services.external_plugin_results
        ] == [("example-provider", _PLUGIN_ID, True, "registered", None)]
        assert [
            (result.plugin_id, result.operation, result.success, result.state)
            for result in loads
        ] == [(_PLUGIN_ID, "load", True, "enabled")]
        assert [
            registration.registration_id
            for registration in plugins.registrations("data_provider")
        ] == [_PROVIDER_ID]
        assert providers.available_fetchers == [
            "ExampleReferenceProvider",
            "ExampleTestFallbackProvider",
        ]

        frame, source = providers.get_daily_data("600519")

        assert source == "ExampleReferenceProvider"
        assert frame["close"].tolist() == [100.5, 101.25]

        disabled = plugins.disable(_PLUGIN_ID)

        assert (disabled.success, disabled.state, disabled.error_code) == (
            True,
            "disabled",
            None,
        )
        assert plugins.registrations("data_provider") == ()
        assert providers.available_fetchers == ["ExampleTestFallbackProvider"]
    finally:
        services.close()


def test_invalid_manifest_and_provider_initialization_failure_are_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = tmp_path / "00-invalid-manifest"
    invalid.mkdir()
    (invalid / "manifest.json").write_text("{not-json", encoding="utf-8")
    _write_failing_provider(tmp_path)
    _copy_example(tmp_path, "02-example-provider")
    monkeypatch.setenv("PLUGINS_DIR", str(tmp_path))
    services, providers, plugins = _build_services()

    try:
        loads = services.start_plugins()

        assert [result.candidate for result in services.external_plugin_results] == [
            "00-invalid-manifest",
            "01-failing-provider",
            "02-example-provider",
        ]
        assert [
            result.error_code for result in services.external_plugin_results
        ] == ["external_manifest_invalid", None, None]
        assert [result.plugin_id for result in loads] == [
            "stockpulse.failing-provider-test",
            _PLUGIN_ID,
        ]
        assert [result.success for result in loads] == [False, True]
        assert loads[0].error_code == "native_registry_registration_failed"
        assert plugins.snapshot("stockpulse.failing-provider-test").state == "failed"
        assert plugins.snapshot(_PLUGIN_ID).state == "enabled"
        assert providers.available_fetchers == [
            "ExampleReferenceProvider",
            "ExampleTestFallbackProvider",
        ]

        frame, source = providers.get_daily_data("600519")

        assert source == "ExampleReferenceProvider"
        assert len(frame) == 2
    finally:
        services.close()

    assert plugins.snapshot("stockpulse.failing-provider-test").state == "disabled"
    assert plugins.snapshot(_PLUGIN_ID).state == "disabled"


def test_provider_author_docs_preserve_timeout_and_startup_ownership() -> None:
    author_guide = (
        _REPOSITORY_ROOT / "docs" / "data-provider-plugin-authoring.md"
    ).read_text(encoding="utf-8")
    plugin_contract = (
        _REPOSITORY_ROOT / "docs" / "plugin-extension-contract.md"
    ).read_text(encoding="utf-8")
    stability_docs = tuple(
        (_REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in (
            "docs/data-source-stability.md",
            "docs/data-source-stability_EN.md",
        )
    )
    normalized_guide = " ".join(author_guide.split())
    normalized_contract = " ".join(plugin_contract.split())

    assert "does not impose a universal deadline" in normalized_guide
    assert "finite connect/read or SDK transport timeouts" in normalized_guide
    assert "timeout policy" not in author_guide
    assert "does not impose a universal deadline" in normalized_contract
    assert "finite transport timeouts" in normalized_contract

    for content in stability_docs:
        assert "`ApplicationServices.start_plugins()`" in content
        assert "`PLUGINS_DIR`" in content
        assert "`DataFetcherManager.plugin_registry`" in content
        assert "data-provider-plugin-authoring.md" in content
        assert "transport timeout" in content
        assert "X2b/GATE-P3" not in content
