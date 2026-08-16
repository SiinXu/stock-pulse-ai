# -*- coding: utf-8 -*-
"""Field-level trust metadata on the realtime quote fallback chain (Issue #1129)."""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

try:
    json_repair_available = importlib.util.find_spec("json_repair") is not None
except ValueError:
    json_repair_available = "json_repair" in sys.modules

if not json_repair_available and "json_repair" not in sys.modules:
    sys.modules["json_repair"] = MagicMock()

from data_provider import field_trust
from data_provider.base import DataFetcherManager
from data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote


class _DummyFetcher:
    def __init__(self, name: str, priority: int, result=None, error: Exception | None = None):
        self.name = name
        self.priority = priority
        self._result = result
        self._error = error

    def get_realtime_quote(self, *args, **kwargs):
        if self._error is not None:
            raise self._error
        return self._result


def _make_quote(
    code: str = "600519",
    source: RealtimeSource = RealtimeSource.EFINANCE,
    **overrides,
) -> UnifiedRealtimeQuote:
    return UnifiedRealtimeQuote(
        code=code,
        name="贵州茅台",
        source=source,
        price=1688.0,
        change_pct=1.2,
        **overrides,
    )


def _mock_config():
    return SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
        realtime_cache_ttl=600,
    )


@pytest.fixture
def validation_enabled(monkeypatch):
    from src.application_services import reset_application_services
    from src.config import Config

    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("DATA_VALIDATION_STRICT", "false")
    reset_application_services()
    Config.reset_instance()
    yield
    reset_application_services()
    Config.reset_instance()


@pytest.fixture
def validation_disabled(monkeypatch):
    from src.application_services import reset_application_services
    from src.config import Config

    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "false")
    reset_application_services()
    Config.reset_instance()
    yield
    reset_application_services()
    Config.reset_instance()


@patch("src.config.get_config")
def test_primary_and_supplement_field_attribution(mock_get_config, validation_enabled):
    """Fields keep the provider that actually produced them."""
    mock_get_config.return_value = _mock_config()
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    primary = _make_quote(source=RealtimeSource.EFINANCE, provider_timestamp=stale_ts)
    supplement = _make_quote(source=RealtimeSource.AKSHARE_EM, pe_ratio=25.5)
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, result=supplement),
        ]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is primary
    trust = quote.field_trust
    assert trust is not None
    assert trust["schema_version"] == field_trust.FIELD_TRUST_SCHEMA_VERSION

    price_entry = trust["fields"]["price"]
    assert price_entry["source"] == "efinance"
    assert price_entry["origin"] == "primary"
    # 2h-old provider timestamp exceeds the 600s TTL: visibly stale.
    assert price_entry["staleness"] == field_trust.STALENESS_STALE
    assert price_entry["is_stale"] is True
    assert price_entry["stale_seconds"] > 600

    pe_entry = trust["fields"]["pe_ratio"]
    assert pe_entry["source"] == "akshare_em"
    assert pe_entry["origin"] == "supplement"
    # Supplement timestamps are not TTL-normalized: never claim freshness.
    assert pe_entry["staleness"] == field_trust.STALENESS_UNKNOWN


@patch("src.config.get_config")
def test_conflict_recorded_when_providers_disagree(mock_get_config, validation_enabled):
    """Cross-provider divergence is surfaced, not silently resolved."""
    mock_get_config.return_value = _mock_config()
    primary = _make_quote(source=RealtimeSource.EFINANCE)
    conflicting = _make_quote(source=RealtimeSource.AKSHARE_EM, volume_ratio=1.5)
    conflicting.price = 2100.0  # ~24% divergence from 1688.0
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, result=conflicting),
        ]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is primary
    # Conflict never overwrites the primary observation.
    assert quote.price == 1688.0
    trust = quote.field_trust
    conflict_fields = {entry["field"] for entry in trust["conflicts"]}
    assert "price" in conflict_fields
    price_conflict = next(
        entry for entry in trust["conflicts"] if entry["field"] == "price"
    )
    providers = {item["provider"]: item["value"] for item in price_conflict["values"]}
    assert providers["efinance"] == 1688.0
    assert providers["AkshareFetcher"] == 2100.0
    assert trust["fields"]["price"]["conflict"] is True
    assert any(
        check["status"] == field_trust.CONFLICT_CHECK_EVALUATED
        for check in trust["conflict_checks"]
    )


@patch("src.config.get_config")
def test_validation_disabled_records_skipped_conflict_check(
    mock_get_config, validation_disabled
):
    """A skipped comparison must not imply agreement between providers."""
    mock_get_config.return_value = _mock_config()
    primary = _make_quote(source=RealtimeSource.EFINANCE)
    supplement = _make_quote(source=RealtimeSource.AKSHARE_EM, pe_ratio=25.5)
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, result=supplement),
        ]
    )

    quote = manager.get_realtime_quote("600519")

    trust = quote.field_trust
    assert trust["conflicts"] == []
    skipped = [
        check
        for check in trust["conflict_checks"]
        if check["status"] == field_trust.CONFLICT_CHECK_SKIPPED
    ]
    assert skipped
    assert skipped[0]["reason"] == "validation_disabled"


@patch("src.config.get_config")
def test_unknown_provider_timestamp_yields_unknown_staleness(
    mock_get_config, validation_enabled
):
    """No provider timestamp means unknown staleness, never fresh."""
    mock_get_config.return_value = _mock_config()
    primary = _make_quote(source=RealtimeSource.EFINANCE, volume_ratio=1.1,
                          turnover_rate=0.5, pe_ratio=20.0, pb_ratio=5.0,
                          total_mv=1.0, circ_mv=1.0, amplitude=1.0,
                          iopv=1.0, nav=1.0)
    manager = DataFetcherManager(
        fetchers=[_DummyFetcher("EfinanceFetcher", 0, result=primary)]
    )

    quote = manager.get_realtime_quote("600519")

    trust = quote.field_trust
    assert trust["fields"]["price"]["staleness"] == field_trust.STALENESS_UNKNOWN
    assert trust["fields"]["price"]["is_stale"] is None


def test_finalize_never_marks_missing_fields():
    """Absent values get no trust entry at all (nothing to trust)."""
    quote = _make_quote()
    quote.is_stale = False
    field_trust.finalize(quote)
    assert "pe_ratio" not in quote.field_trust["fields"]
    assert quote.field_trust["fields"]["price"]["staleness"] == field_trust.STALENESS_FRESH


def test_record_helpers_tolerate_broken_quotes():
    """Trust recording must never break the quote path."""
    field_trust.record_supplement(None, ["price"], None)
    field_trust.finalize(None)
    field_trust.record_conflict_check(
        None, primary_provider="a", secondary_provider="b", status="skipped"
    )
    field_trust.record_cross_source_result(
        None, None, primary_provider="a", secondary_provider="b"
    )
