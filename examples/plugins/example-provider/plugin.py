# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic reference Data Provider plugin for authoring and tests."""

from __future__ import annotations

import pandas as pd

from data_provider import DataProvider, DataProviderRegistration
from src.plugins import Plugin as BasePlugin
from src.plugins import PluginContext


class ExampleDataProvider(DataProvider):
    """Return a small normalized daily-data fixture without network access."""

    name = "ExampleReferenceProvider"
    priority = 90

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
                "date": ["2026-01-02", "2026-01-05"],
                "open": [100.0, 100.75],
                "high": [101.0, 102.0],
                "low": [99.5, 100.25],
                "close": [100.5, 101.25],
                "volume": [1000, 1200],
                "amount": [100500.0, 121500.0],
                "pct_chg": [0.5, 0.75],
            }
        )


class Plugin(BasePlugin):
    """Register the example implementation with the provider-owned registry."""

    def onload(self, context: PluginContext) -> None:
        registration = DataProviderRegistration(
            provider_id="example-daily-data",
            factory=ExampleDataProvider,
            markets=frozenset({"cn"}),
            capabilities=frozenset({"daily_data"}),
        )
        context.register(
            "data_provider",
            registration.provider_id,
            registration,
            contract_version="1",
            priority=ExampleDataProvider.priority,
        )
