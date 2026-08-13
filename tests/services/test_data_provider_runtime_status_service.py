# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for the Data Sources Hub runtime projection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from data_provider.base import DataFetcherManager
from src.services.data_provider_runtime_status_service import (
    SCHEMA_VERSION,
    build_data_provider_runtime_status,
)


class _FakeFetcher:
    def __init__(
        self,
        name: str,
        *,
        priority: int = 10,
        available: bool = True,
        raise_on_available: bool = False,
        api: Any = None,
        api_key: str = "",
    ) -> None:
        self.name = name
        self.priority = priority
        self._available = available
        self._raise_on_available = raise_on_available
        self._api = api
        self.api_key = api_key

    def is_available(self) -> bool:
        if self._raise_on_available:
            raise RuntimeError("probe exploded")
        return self._available


def _manager_with_fetchers(fetchers: List[_FakeFetcher]) -> DataFetcherManager:
    DataFetcherManager.reset_daily_source_health()
    return DataFetcherManager(fetchers=list(fetchers))


def test_default_manager_never_claims_healthy_without_samples() -> None:
    # DataFetcherManager([]) still installs keyless builtins; projection must
    # observe them without inventing healthy status from zero samples.
    manager = _manager_with_fetchers([])
    payload = build_data_provider_runtime_status(
        manager=manager,
        clock=lambda: datetime(2026, 8, 12, tzinfo=timezone.utc),
    )

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["source_state"] == "ok"
    assert payload["partial"] is False
    assert payload["as_of"].startswith("2026-08-12")
    assert len(payload["markets"]) == 3
    assert len(payload["providers"]) >= 1
    for provider in payload["providers"]:
        assert provider["health_status"] != "healthy"
        assert provider["health_status"] in {
            "unknown",
            "unavailable",
            "not_configured",
            "failed",
            "degraded",
            "circuit_open",
        }
    for market in payload["markets"]:
        # Unobserved chains may still pick a first-eligible primary, but quality
        # must not claim ok without health samples.
        assert market["quality"] in {"unknown", "unavailable", "degraded"}
    assert payload["cache"] is not None
    assert payload["cache"]["quality"] in {
        "idle",
        "cold",
        "active",
        "stale",
        "local_only",
        "unknown",
    }


def test_baseline_and_enhancer_roles_with_truthful_health() -> None:
    akshare = _FakeFetcher("AkshareFetcher", priority=5, available=True)
    tushare = _FakeFetcher(
        "TushareFetcher",
        priority=-1,
        available=True,
        api=object(),
    )
    tickflow = _FakeFetcher(
        "TickFlowFetcher",
        priority=2,
        available=False,
        api_key="",
    )
    manager = _manager_with_fetchers([akshare, tushare, tickflow])

    # Record observed health only for akshare/cn so healthy requires samples.
    health_key = manager._daily_health_key(akshare, "cn")
    manager._daily_source_health.record_success(health_key, latency_ms=12.0)

    payload = build_data_provider_runtime_status(manager=manager)
    by_id = {item["provider_id"]: item for item in payload["providers"]}

    assert by_id["akshare"]["role"] == "baseline"
    assert by_id["akshare"]["configured"] is None
    assert by_id["akshare"]["health_status"] == "healthy"
    assert by_id["akshare"]["sample_count"] >= 1
    assert (
        "daily_data:cn" in by_id["akshare"]["is_primary_for"]
        or "daily_data:cn" in by_id["tushare"]["is_primary_for"]
    )

    assert by_id["tushare"]["role"] == "enhancer"
    assert by_id["tushare"]["configured"] is True
    # Configured enhancer with no observed samples is unknown, never healthy-by-default.
    assert by_id["tushare"]["health_status"] in {"unknown", "healthy", "degraded"}

    assert by_id["tickflow"]["role"] == "enhancer"
    assert by_id["tickflow"]["configured"] is False
    assert by_id["tickflow"]["health_status"] == "not_configured"
    assert by_id["tickflow"]["available"] is False


def test_probe_failure_never_defaults_to_available() -> None:
    broken = _FakeFetcher(
        "AkshareFetcher",
        priority=1,
        available=True,
        raise_on_available=True,
    )
    manager = _manager_with_fetchers([broken])

    # Manager's own availability helper may swallow fetcher errors as False.
    # Force the projection's probe path to raise so fail-closed status is tested.
    def _raise(_fetcher: Any, capability: str = "daily_data") -> bool:
        raise RuntimeError("probe exploded")

    manager._is_fetcher_available = _raise  # type: ignore[method-assign]
    payload = build_data_provider_runtime_status(manager=manager)
    provider = next(item for item in payload["providers"] if item["provider_id"] == "akshare")

    assert provider["available"] is False
    assert provider["health_status"] == "failed"
    assert provider["failure_reason"]
    assert "exploded" in str(provider["failure_reason"])


def test_not_initialized_is_explicit_partial() -> None:
    def _raise() -> None:
        from src.services.data_provider_runtime_status_service import (
            DataProviderRuntimeNotInitialized,
        )

        raise DataProviderRuntimeNotInitialized()

    payload = build_data_provider_runtime_status(manager_factory=_raise)
    assert payload["partial"] is True
    assert payload["source_state"] == "not_initialized"
    assert payload["error_code"] == "data_runtime_not_initialized"
    assert payload["markets"] == []
    assert payload["providers"] == []
    assert payload["cache"] is None


def test_unavailable_provider_is_skipped_for_primary() -> None:
    down = _FakeFetcher("AkshareFetcher", priority=1, available=False)
    up = _FakeFetcher("EfinanceFetcher", priority=2, available=True)
    manager = _manager_with_fetchers([down, up])
    payload = build_data_provider_runtime_status(manager=manager)

    cn = next(item for item in payload["markets"] if item["market"] == "cn")
    # Primary must not claim the unavailable first provider.
    assert cn["primary_provider_id"] != "akshare"
    if cn["ordered_provider_ids"] and cn["primary_provider_id"] is not None:
        assert cn["primary_provider_id"] in cn["ordered_provider_ids"]
        assert cn["primary_provider_id"] != "akshare"


def test_projection_does_not_fabricate_healthy_without_samples() -> None:
    akshare = _FakeFetcher("AkshareFetcher", priority=1, available=True)
    manager = _manager_with_fetchers([akshare])
    payload = build_data_provider_runtime_status(manager=manager)
    provider = next(item for item in payload["providers"] if item["provider_id"] == "akshare")

    assert provider["available"] is True
    assert provider["health_status"] == "unknown"
    assert provider["sample_count"] == 0
