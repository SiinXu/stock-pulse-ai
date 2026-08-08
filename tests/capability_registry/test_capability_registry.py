# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for the read-only capability registry aggregation view."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, List, Optional

import pytest

from src.capability_registry import (
    REASON_FEATURE_DISABLED,
    REASON_MISSING_CONFIG,
    REASON_MISSING_DEPENDENCY,
    REASON_PLUGIN_DISABLED,
    CapabilityRecord,
    collect_capability_records,
)
from src.capability_registry.models import KNOWN_UNAVAILABLE_REASON_CODES


@dataclass
class _FakePolicy:
    permissions: List[str] = field(default_factory=list)


@dataclass
class _FakeTool:
    name: str
    category: str = "data"
    policy: Optional[_FakePolicy] = None


class _FakeToolRegistry:
    def __init__(self, tools: List[_FakeTool]) -> None:
        self._tools = tools

    def list_tools(self, category: Optional[str] = None) -> List[_FakeTool]:
        tools = list(self._tools)
        if category:
            tools = [tool for tool in tools if tool.category == category]
        return tools

    def list_names(self) -> List[str]:
        return [tool.name for tool in self._tools]


@dataclass
class _FakeManifest:
    id: str
    name: str


@dataclass
class _FakeSnapshot:
    manifest: _FakeManifest
    state: str
    desired_enabled: bool = True
    source: str = "builtin"
    extension_points: tuple[str, ...] = ()


class _FakePluginManager:
    def __init__(self, snapshots: List[_FakeSnapshot], registry: Any = None) -> None:
        self._snapshots = snapshots
        self.registry = registry

    def list_snapshots(self) -> tuple[_FakeSnapshot, ...]:
        return tuple(self._snapshots)


def _base_config(**overrides: Any) -> SimpleNamespace:
    data = dict(
        tushare_token=None,
        tickflow_api_key=None,
        finnhub_api_key=None,
        alphavantage_api_key=None,
        longbridge_app_key=None,
        longbridge_app_secret=None,
        longbridge_access_token=None,
        longbridge_oauth_client_id=None,
        multimodal_agent_tools_enabled=False,
        multimodal_file_root=None,
        valuation_agent_tool_enabled=False,
        kronos_enabled=False,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def _by_id(records: List[CapabilityRecord]) -> dict[str, CapabilityRecord]:
    return {record.capability_id: record for record in records}


def test_feature_disabled_reason_for_multimodal_tools() -> None:
    records = collect_capability_records(
        config=_base_config(multimodal_agent_tools_enabled=False),
        tool_registry=_FakeToolRegistry([]),
        plugin_manager=_FakePluginManager([]),
        dependency_probe=lambda _name: True,
        domains=("tool",),
    )
    multimodal = _by_id(records)["tool.optional:multimodal"]
    assert multimodal.available is False
    assert multimodal.reason_code == REASON_FEATURE_DISABLED
    assert "MULTIMODAL_AGENT_TOOLS_ENABLED" in (multimodal.reason_message or "")


def test_missing_config_reason_for_finnhub_and_multimodal_root() -> None:
    records = collect_capability_records(
        config=_base_config(
            finnhub_api_key=None,
            multimodal_agent_tools_enabled=True,
            multimodal_file_root="",
        ),
        tool_registry=_FakeToolRegistry([]),
        plugin_manager=_FakePluginManager([]),
        dependency_probe=lambda _name: True,
        domains=("data", "tool"),
    )
    by_id = _by_id(records)
    finnhub = by_id["data.provider:finnhub"]
    assert finnhub.available is False
    assert finnhub.reason_code == REASON_MISSING_CONFIG
    assert "FINNHUB_API_KEY" in (finnhub.reason_message or "")
    multimodal = by_id["tool.optional:multimodal"]
    assert multimodal.available is False
    assert multimodal.reason_code == REASON_MISSING_CONFIG
    assert "MULTIMODAL_FILE_ROOT" in (multimodal.reason_message or "")


def test_missing_dependency_reason_for_tickflow() -> None:
    records = collect_capability_records(
        config=_base_config(tickflow_api_key="present-key"),
        tool_registry=_FakeToolRegistry([]),
        plugin_manager=_FakePluginManager([]),
        dependency_probe=lambda name: name != "tickflow",
        domains=("data",),
    )
    tickflow = _by_id(records)["data.provider:tickflow"]
    assert tickflow.available is False
    assert tickflow.reason_code == REASON_MISSING_DEPENDENCY
    assert "tickflow" in (tickflow.reason_message or "")


def test_available_provider_when_config_and_deps_present() -> None:
    records = collect_capability_records(
        config=_base_config(finnhub_api_key="fh-demo", tushare_token="ts-demo"),
        tool_registry=_FakeToolRegistry([]),
        plugin_manager=_FakePluginManager([]),
        dependency_probe=lambda _name: True,
        domains=("data",),
    )
    by_id = _by_id(records)
    assert by_id["data.provider:finnhub"].available is True
    assert by_id["data.provider:tushare"].available is True
    assert by_id["data.provider:efinance"].available is True
    assert by_id["data.capability:daily_data"].available is True


def test_registered_tools_are_available_and_tokens_reflect_providers() -> None:
    tools = [
        _FakeTool(
            name="get_realtime_quote",
            policy=_FakePolicy(permissions=["market_data:read"]),
        ),
        _FakeTool(
            name="parse_financial_pdf",
            category="multimodal",
            policy=_FakePolicy(permissions=["multimodal:read"]),
        ),
    ]
    records = collect_capability_records(
        config=_base_config(
            multimodal_agent_tools_enabled=True,
            multimodal_file_root="/tmp/multimodal",
        ),
        tool_registry=_FakeToolRegistry(tools),
        plugin_manager=_FakePluginManager([]),
        dependency_probe=lambda _name: True,
        domains=("tool",),
    )
    by_id = _by_id(records)
    assert by_id["tool:get_realtime_quote"].available is True
    assert by_id["tool:parse_financial_pdf"].available is True
    assert "tool.optional:multimodal" not in by_id
    token = by_id["tool.capability:market_data:read"]
    assert token.available is True
    assert "get_realtime_quote" in token.provider



def test_plugin_disabled_reason() -> None:
    manager = _FakePluginManager([
        _FakeSnapshot(
            manifest=_FakeManifest(id="demo.plugin", name="Demo"),
            state="disabled", desired_enabled=False, extension_points=("agent_tool",),
        )
    ])
    records = collect_capability_records(
        config=_base_config(),
        tool_registry=_FakeToolRegistry([]),
        plugin_manager=manager,
        dependency_probe=lambda _name: True,
        domains=("extension",),
    )
    plugin = _by_id(records)["extension.plugin:demo.plugin"]
    assert plugin.available is False
    assert plugin.reason_code == REASON_PLUGIN_DISABLED


def test_domain_filter_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unsupported capability domains"):
        collect_capability_records(
            config=_base_config(),
            tool_registry=_FakeToolRegistry([]),
            plugin_manager=_FakePluginManager([]),
            domains=("data", "nope"),
        )


def test_reason_codes_are_documented_stable_set() -> None:
    assert REASON_FEATURE_DISABLED in KNOWN_UNAVAILABLE_REASON_CODES
    assert REASON_MISSING_CONFIG in KNOWN_UNAVAILABLE_REASON_CODES
    assert REASON_MISSING_DEPENDENCY in KNOWN_UNAVAILABLE_REASON_CODES


def test_available_record_rejects_reason_code() -> None:
    with pytest.raises(ValueError, match="must not carry"):
        CapabilityRecord(
            capability_id="x", domain="data", provider="p", available=True,
            reason_code=REASON_MISSING_CONFIG,
        )
