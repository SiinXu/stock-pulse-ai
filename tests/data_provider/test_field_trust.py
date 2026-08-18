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

from src.data_provider import field_trust
from src.data_provider.base import DataFetcherManager
from src.data_provider.plugin_registry import DataProviderRegistration
from src.data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote


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


class _PluginFetcher(_DummyFetcher):
    def __init__(
        self,
        name: str,
        priority: int,
        provider_id: str,
        result=None,
        error: Exception | None = None,
        markets: frozenset[str] | None = None,
    ):
        super().__init__(name, priority, result=result, error=error)
        self._registration = DataProviderRegistration(
            provider_id=provider_id,
            factory=lambda: self,
            markets=markets or frozenset({"cn"}),
            capabilities=frozenset({"realtime_quote"}),
        )

    def _manager_plugin_registration(self):
        return self._registration


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


def _mock_config(*, ttl: int = 600, validation_enabled: bool = True):
    return SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
        realtime_cache_ttl=ttl,
        data_validation_enabled=validation_enabled,
        data_validation_strict=False,
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
def test_fresh_primary_fields_are_attributed(mock_get_config, validation_enabled):
    """A recent primary quote is fresh, attributed, and high-confidence."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(
        source=RealtimeSource.EFINANCE,
        provider_timestamp=fresh_ts,
        volume_ratio=1.1,
        turnover_rate=0.5,
        pe_ratio=20.0,
        pb_ratio=5.0,
        total_mv=1.0,
        circ_mv=1.0,
        amplitude=1.0,
        iopv=1.0,
        nav=1.0,
    )
    manager = DataFetcherManager(
        fetchers=[_DummyFetcher("EfinanceFetcher", 0, result=primary)]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is primary
    trust = quote.field_trust
    assert trust is not None
    assert trust["schema_version"] == field_trust.FIELD_TRUST_SCHEMA_VERSION
    price_entry = trust["fields"]["price"]
    assert price_entry["source"] == "efinance"
    assert price_entry["origin"] == "primary"
    assert price_entry["staleness"] == field_trust.STALENESS_FRESH
    assert price_entry["is_stale"] is False
    assert price_entry["conflict"] is False
    analysis = trust["analysis_input"]
    assert analysis["confidence"] == field_trust.CONFIDENCE_HIGH
    assert analysis["gaps"] == []
    health_providers = {row["provider"] for row in trust["provider_health"]}
    assert "efinance" in health_providers
    serialized = quote.to_dict()
    assert serialized["field_trust"]["analysis_input"]["confidence"] == "high"


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
    analysis = trust["analysis_input"]
    assert analysis["confidence"] == field_trust.CONFIDENCE_LOW
    assert any(gap["code"] == "stale" for gap in analysis["gaps"])


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
    assert providers["akshare_em"] == 2100.0
    assert trust["fields"]["price"]["conflict"] is True
    assert any(
        check["status"] == field_trust.CONFLICT_CHECK_EVALUATED
        for check in trust["conflict_checks"]
    )
    analysis = trust["analysis_input"]
    assert analysis["confidence"] == field_trust.CONFIDENCE_LOW
    assert any(gap["code"] == "conflict" for gap in analysis["gaps"])
    serialized = quote.to_dict()
    assert serialized["field_trust"]["analysis_input"]["conflict_count"] >= 1


@patch("src.config.get_config")
def test_validation_disabled_records_skipped_conflict_check(
    mock_get_config, validation_disabled
):
    """A skipped comparison must not imply agreement between providers."""
    mock_get_config.return_value = _mock_config(validation_enabled=False)
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
    analysis = trust["analysis_input"]
    assert analysis["confidence"] != field_trust.CONFIDENCE_HIGH
    assert any(gap["code"] == "conflict_check_skipped" for gap in analysis["gaps"])


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
    assert trust["analysis_input"]["confidence"] != field_trust.CONFIDENCE_HIGH


@patch("src.config.get_config")
def test_provider_failure_is_recorded_on_fallback(mock_get_config, validation_enabled):
    """A failed preferred provider is health + gap, not silently dropped."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    fallback = _make_quote(
        source=RealtimeSource.AKSHARE_EM,
        provider_timestamp=fresh_ts,
        volume_ratio=1.1,
        turnover_rate=0.5,
        pe_ratio=20.0,
        pb_ratio=5.0,
        total_mv=1.0,
        circ_mv=1.0,
        amplitude=1.0,
        iopv=1.0,
        nav=1.0,
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, error=RuntimeError("efinance down")),
            _DummyFetcher("AkshareFetcher", 1, result=fallback),
        ]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is fallback
    trust = quote.field_trust
    assert quote.fallback_from == "efinance"
    statuses = {(row["provider"], row["status"]) for row in trust["provider_health"]}
    assert ("efinance", "failed") in statuses
    assert ("akshare_em", "ok") in statuses
    analysis = trust["analysis_input"]
    assert any(gap["code"] == "provider_failed" for gap in analysis["gaps"])
    assert analysis["confidence"] == field_trust.CONFIDENCE_LOW
    assert analysis["failed_provider_count"] >= 1


@patch("src.config.get_config")
def test_comparison_exception_does_not_imply_agreement(
    mock_get_config, validation_enabled
):
    """A failed comparison must degrade trust instead of reading as agreement."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(
        source=RealtimeSource.EFINANCE,
        provider_timestamp=fresh_ts,
    )
    secondary = _make_quote(source=RealtimeSource.AKSHARE_EM, volume_ratio=1.5)
    secondary.price = 200.0
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, result=secondary),
        ]
    )

    with patch(
        "src.data_provider.data_validation.compare_cross_source_quotes",
        side_effect=RuntimeError("comparison exploded"),
    ):
        quote = manager.get_realtime_quote("600519")

    assert quote is primary
    assert quote.price == 1688.0
    trust = quote.field_trust
    skipped = [
        check
        for check in trust["conflict_checks"]
        if check.get("reason") == "comparison_failed"
    ]
    assert skipped
    assert skipped[0]["status"] == field_trust.CONFLICT_CHECK_SKIPPED
    assert skipped[0]["secondary_provider"] == "akshare_em"
    assert trust["analysis_input"]["confidence"] != field_trust.CONFIDENCE_HIGH
    assert any(
        gap["code"] == "conflict_check_skipped" for gap in trust["analysis_input"]["gaps"]
    )


@patch("src.config.get_config")
def test_post_primary_provider_failure_is_recorded(
    mock_get_config, validation_enabled
):
    """A failed later source must appear on health after a primary quote exists."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(
        source=RealtimeSource.EFINANCE,
        provider_timestamp=fresh_ts,
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, error=RuntimeError("akshare down")),
        ]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is primary
    trust = quote.field_trust
    statuses = {(row["provider"], row["status"]) for row in trust["provider_health"]}
    assert ("efinance", "ok") in statuses
    assert ("akshare_em", "failed") in statuses
    assert trust["analysis_input"]["confidence"] == field_trust.CONFIDENCE_LOW
    assert any(gap["code"] == "provider_failed" for gap in trust["analysis_input"]["gaps"])


@patch("src.config.get_config")
def test_supplement_quote_records_comparison_failure_and_empty_attempt(
    mock_get_config, validation_enabled
):
    """US/HK supplement path must record failed checks and later-source empty."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(
        code="AAPL",
        source=RealtimeSource.LONGBRIDGE,
        provider_timestamp=fresh_ts,
    )
    secondary = _make_quote(code="AAPL", source=RealtimeSource.AKSHARE_EM, pe_ratio=18.0)
    secondary.price = 200.0
    manager = DataFetcherManager(fetchers=[])

    with patch.object(manager, "_try_fetcher_quote", return_value=secondary), patch(
        "src.data_provider.data_validation.compare_cross_source_quotes",
        side_effect=RuntimeError("comparison exploded"),
    ):
        quote = manager._supplement_quote("AAPL", primary, "AkshareFetcher")

    assert quote is primary
    assert quote.price == 1688.0
    skipped = [
        check
        for check in quote.field_trust["conflict_checks"]
        if check.get("reason") == "comparison_failed"
    ]
    assert skipped
    assert skipped[0]["status"] == field_trust.CONFLICT_CHECK_SKIPPED
    assert skipped[0]["secondary_provider"] == "akshare_em"

    empty_primary = _make_quote(
        code="AAPL",
        source=RealtimeSource.LONGBRIDGE,
        provider_timestamp=fresh_ts,
    )
    with patch.object(manager, "_try_fetcher_quote", return_value=None):
        empty_quote = manager._supplement_quote("AAPL", empty_primary, "YfinanceFetcher")
    # finalize has not run on this helper path; inspect attempts directly.
    attempts = {
        (row["provider"], row["status"])
        for row in empty_quote.field_trust["provider_attempts"]
    }
    assert ("yfinance", "empty") in attempts


@patch("src.config.get_config")
def test_supplement_quote_records_post_primary_exception(
    mock_get_config, validation_enabled
):
    """A later-source exception on the supplement path is a failed attempt."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(
        code="AAPL",
        source=RealtimeSource.LONGBRIDGE,
        provider_timestamp=fresh_ts,
    )
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        manager, "_try_fetcher_quote", side_effect=RuntimeError("yfinance down")
    ):
        quote = manager._supplement_quote("AAPL", primary, "YfinanceFetcher")

    assert quote is primary
    attempts = {
        (row["provider"], row["status"])
        for row in quote.field_trust["provider_attempts"]
    }
    assert ("yfinance", "failed") in attempts


@patch("src.config.get_config")
def test_all_providers_fail_returns_none(mock_get_config, validation_enabled):
    """Total provider failure stays None; callers must degrade, not invent a quote."""
    mock_get_config.return_value = _mock_config()
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, error=RuntimeError("down")),
            _DummyFetcher("AkshareFetcher", 1, error=RuntimeError("also down")),
        ]
    )

    quote = manager.get_realtime_quote("600519")

    assert quote is None


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
    field_trust.record_provider_attempt(None, provider="x", status="failed")
    absent = field_trust.project_analysis_input(None)
    assert absent["confidence"] == field_trust.CONFIDENCE_LOW
    assert absent["gaps"][0]["code"] == "metadata_absent"


def test_concrete_builtin_source_tokens_are_not_fallback():
    """Yfinance / Finnhub / AlphaVantage / HK Sina stay distinct identities."""
    assert RealtimeSource.YFINANCE.value == "yfinance"
    assert RealtimeSource.FINNHUB.value == "finnhub"
    assert RealtimeSource.ALPHAVANTAGE.value == "alphavantage"
    assert RealtimeSource.AKSHARE_SINA.value == "akshare_sina"
    for source in (
        RealtimeSource.YFINANCE,
        RealtimeSource.FINNHUB,
        RealtimeSource.ALPHAVANTAGE,
        RealtimeSource.AKSHARE_SINA,
    ):
        quote = _make_quote(source=source)
        field_trust.finalize(quote)
        assert quote.field_trust["fields"]["price"]["source"] == source.value
        assert source.value != RealtimeSource.FALLBACK.value


@patch("src.config.get_config")
def test_us_primary_failure_attaches_to_successful_fallback(
    mock_get_config, validation_enabled
):
    """US/HK fallback_from stays first-failure; every prior non-ok is attached."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    success = _make_quote(
        code="AAPL",
        source=RealtimeSource.YFINANCE,
        provider_timestamp=fresh_ts,
        volume_ratio=1.1,
        turnover_rate=0.5,
        pe_ratio=20.0,
        pb_ratio=5.0,
        total_mv=1.0,
        circ_mv=1.0,
        amplitude=1.0,
        iopv=1.0,
        nav=1.0,
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("LongbridgeFetcher", 0, error=RuntimeError("lb down")),
            _DummyFetcher("YfinanceFetcher", 1, result=success),
        ]
    )

    quote = manager.get_realtime_quote("AAPL")

    assert quote is success
    assert quote.fallback_from == "longbridge"
    statuses = {(row["provider"], row["status"]) for row in quote.field_trust["provider_health"]}
    assert ("longbridge", "failed") in statuses
    assert ("yfinance", "ok") in statuses


@patch("src.config.get_config")
def test_yfinance_finnhub_conflict_keeps_distinct_sources(
    mock_get_config, validation_enabled
):
    """US extras must compare yfinance vs finnhub, not two fallbacks."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(
        code="AAPL",
        source=RealtimeSource.YFINANCE,
        provider_timestamp=fresh_ts,
    )
    secondary = _make_quote(
        code="AAPL",
        source=RealtimeSource.FINNHUB,
        pe_ratio=22.0,
    )
    secondary.price = 210.0
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("YfinanceFetcher", 0, result=primary),
            _DummyFetcher("FinnhubFetcher", 1, result=secondary),
        ]
    )

    quote = manager.get_realtime_quote("AAPL")

    assert quote is primary
    assert quote.source is RealtimeSource.YFINANCE
    assert quote.price == 1688.0
    trust = quote.field_trust
    price_conflict = next(
        entry for entry in trust["conflicts"] if entry["field"] == "price"
    )
    providers = {item["provider"]: item["value"] for item in price_conflict["values"]}
    assert "fallback" not in providers
    assert providers["yfinance"] == 1688.0
    assert providers["finnhub"] == 210.0
    assert trust["fields"]["pe_ratio"]["source"] == "finnhub"


@patch("src.config.get_config")
def test_supplement_swallows_real_fetcher_exception(
    mock_get_config, validation_enabled
):
    """A raising secondary fetcher is swallowed by _try_fetcher_quote as failed."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(
        code="AAPL",
        source=RealtimeSource.LONGBRIDGE,
        provider_timestamp=fresh_ts,
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("YfinanceFetcher", 0, error=RuntimeError("yfinance down")),
        ]
    )

    quote = manager._supplement_quote("AAPL", primary, "YfinanceFetcher")

    assert quote is primary
    attempts = {
        (row["provider"], row["status"])
        for row in quote.field_trust["provider_attempts"]
    }
    assert ("yfinance", "failed") in attempts
    assert quote.price == 1688.0


@patch("src.config.get_config")
def test_crypto_fail_then_success_attaches_prior_attempt(
    mock_get_config, validation_enabled
):
    """Crypto fallback keeps the failed provider on the successful quote."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    success = _make_quote(
        code="crypto:BTC",
        source=RealtimeSource.COINGECKO,
        provider_timestamp=fresh_ts,
        volume_ratio=1.1,
        turnover_rate=0.5,
        pe_ratio=20.0,
        pb_ratio=5.0,
        total_mv=1.0,
        circ_mv=1.0,
        amplitude=1.0,
        iopv=1.0,
        nav=1.0,
    )
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("CryptoFailFetcher", 0, error=RuntimeError("coingecko 429")),
            _DummyFetcher("CryptoOkFetcher", 1, result=success),
        ]
    )

    quote = manager.get_realtime_quote("crypto:BTC")

    assert quote is success
    assert quote.source is RealtimeSource.COINGECKO
    statuses = {(row["provider"], row["status"]) for row in quote.field_trust["provider_health"]}
    assert ("cryptofail", "failed") in statuses
    assert ("coingecko", "ok") in statuses
    assert quote.fallback_from is None


@patch("src.config.get_config")
def test_plugin_failures_use_registration_id(mock_get_config, validation_enabled):
    """Plugin attempts use registration id; concrete quote.source still wins."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    success = _make_quote(
        source=RealtimeSource.EFINANCE,
        provider_timestamp=fresh_ts,
        volume_ratio=1.1,
        turnover_rate=0.5,
        pe_ratio=20.0,
        pb_ratio=5.0,
        total_mv=1.0,
        circ_mv=1.0,
        amplitude=1.0,
        iopv=1.0,
        nav=1.0,
    )
    manager = DataFetcherManager(
        fetchers=[
            _PluginFetcher(
                "CommunityFailFetcher",
                1,
                "community-alpha",
                error=RuntimeError("plugin down"),
            ),
            _PluginFetcher(
                "CommunityOkFetcher",
                2,
                "community-beta",
                result=success,
            ),
        ]
    )

    quote, plugin_name = manager._try_plugin_realtime_quote("600519", "cn")

    assert quote is success
    assert plugin_name == "CommunityOkFetcher"
    attempts = {
        (row["provider"], row["status"])
        for row in quote.field_trust["provider_attempts"]
    }
    assert ("community-alpha", "failed") in attempts
    field_trust.finalize(quote)
    # Concrete quote.source wins over the plugin registration id.
    assert quote.field_trust["fields"]["price"]["source"] == "efinance"


@patch("src.config.get_config")
def test_attempt_sinks_are_independent(mock_get_config, validation_enabled):
    """Two sinks record exactly one result each and never share state."""
    mock_get_config.return_value = _mock_config()
    finnhub = _make_quote(code="AAPL", source=RealtimeSource.FINNHUB)
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("YfinanceFetcher", 0, error=RuntimeError("down")),
            _DummyFetcher("FinnhubFetcher", 1, result=finnhub),
        ]
    )
    sink_a = field_trust.QuoteAttemptSink()
    sink_b = field_trust.QuoteAttemptSink()

    first = manager._try_fetcher_quote("AAPL", "YfinanceFetcher", _attempt_sink=sink_a)
    second = manager._try_fetcher_quote("AAPL", "FinnhubFetcher", _attempt_sink=sink_b)

    assert first is None
    assert second is finnhub
    assert sink_a.snapshot() == {
        "provider": "yfinance",
        "status": "failed",
        "circuit_key": "yfinance",
    }
    assert sink_b.snapshot() == {
        "provider": "finnhub",
        "status": "ok",
        "circuit_key": "finnhub",
    }
    sink_a.record("other", field_trust.PROVIDER_STATUS_OK)
    assert sink_a.status == "failed"
    assert sink_b.provider == "finnhub"


def test_circuit_key_mapping_finds_tencent_etf_hk_snapshots():
    """Health lookup uses same-route aliases without renaming display tokens."""
    snapshots = {
        "akshare_tencent": {
            "source": "akshare_tencent",
            "state": "closed",
            "available": True,
            "health_score": 91.0,
        },
        "akshare_etf": {
            "source": "akshare_etf",
            "state": "open",
            "available": False,
            "health_score": 12.0,
        },
        "akshare_hk_em": {
            "source": "akshare_hk_em",
            "state": "closed",
            "available": True,
            "health_score": 88.0,
        },
        "akshare_hk_sina": {
            "source": "akshare_hk_sina",
            "state": "open",
            "available": False,
            "health_score": 8.0,
        },
    }
    payload = {
        "provider_attempts": [
            {"provider": "tencent", "status": "ok", "role": "primary"},
            {"provider": "akshare_em", "status": "empty", "role": "attempted"},
            {
                "provider": "akshare_hk",
                "status": "ok",
                "role": "attempted",
                "circuit_key": "akshare_hk_em",
            },
            {
                "provider": "akshare_sina",
                "status": "failed",
                "role": "attempted",
                "circuit_key": "akshare_hk_sina",
            },
        ]
    }
    tencent_snap = field_trust.resolve_circuit_snapshot("tencent", snapshots)
    etf_snap = field_trust.resolve_circuit_snapshot("akshare_etf", snapshots)
    hk_snap = field_trust.resolve_circuit_snapshot(
        "akshare_hk", snapshots, circuit_key="akshare_hk_em"
    )
    sina_snap = field_trust.resolve_circuit_snapshot(
        "akshare_sina", snapshots, circuit_key="akshare_hk_sina"
    )
    assert tencent_snap.get("source") == "akshare_tencent"
    assert etf_snap.get("source") == "akshare_etf"
    assert hk_snap.get("source") == "akshare_hk_em"
    assert sina_snap.get("source") == "akshare_hk_sina"
    cn_em_guess = field_trust.resolve_circuit_snapshot("akshare_em", snapshots)
    assert cn_em_guess == {}

    with patch.object(field_trust, "_circuit_snapshots", return_value=snapshots):
        rows = {row["provider"]: row for row in field_trust.build_provider_health(payload)}
    assert rows["tencent"]["provider"] == "tencent"
    assert rows["tencent"]["circuit_state"] == "closed"
    assert rows["tencent"]["available"] is True
    assert rows["akshare_em"]["provider"] == "akshare_em"
    assert rows["akshare_em"]["available"] is None
    assert rows["akshare_hk"]["provider"] == "akshare_hk"
    assert rows["akshare_hk"]["circuit_state"] == "closed"
    assert rows["akshare_hk"]["available"] is True
    assert rows["akshare_sina"]["provider"] == "akshare_sina"
    assert rows["akshare_sina"]["available"] is False
    assert "akshare_tencent" not in rows


def test_simultaneous_cn_etf_hk_circuits_do_not_cross_attach():
    """CN, ETF, and HK snapshots present together must stay on their own rows."""
    snapshots = {
        "akshare_em": {
            "source": "akshare_em",
            "state": "closed",
            "available": True,
            "health_score": 90.0,
        },
        "akshare_etf": {
            "source": "akshare_etf",
            "state": "open",
            "available": False,
            "health_score": 11.0,
        },
        "akshare_sina": {
            "source": "akshare_sina",
            "state": "closed",
            "available": True,
            "health_score": 85.0,
        },
        "akshare_hk_sina": {
            "source": "akshare_hk_sina",
            "state": "open",
            "available": False,
            "health_score": 7.0,
        },
        "akshare_hk_em": {
            "source": "akshare_hk_em",
            "state": "closed",
            "available": True,
            "health_score": 80.0,
        },
    }
    payload = {
        "provider_attempts": [
            {
                "provider": "akshare_em",
                "status": "ok",
                "role": "primary",
                "circuit_key": "akshare_em",
            },
            {
                "provider": "akshare_em",
                "status": "empty",
                "role": "attempted",
                "circuit_key": "akshare_etf",
            },
            {
                "provider": "akshare_sina",
                "status": "failed",
                "role": "attempted",
                "circuit_key": "akshare_sina",
            },
            {
                "provider": "akshare_sina",
                "status": "failed",
                "role": "attempted",
                "circuit_key": "akshare_hk_sina",
            },
            {
                "provider": "akshare_em",
                "status": "ok",
                "role": "attempted",
                "circuit_key": "akshare_hk_em",
            },
        ]
    }
    with patch.object(field_trust, "_circuit_snapshots", return_value=snapshots):
        rows = field_trust.build_provider_health(payload)
    by_circuit = {}
    for attempt, row in zip(payload["provider_attempts"], rows):
        assert row["provider"] == attempt["provider"]
        by_circuit[attempt["circuit_key"]] = row

    assert by_circuit["akshare_em"]["available"] is True
    assert by_circuit["akshare_etf"]["available"] is False
    assert by_circuit["akshare_sina"]["available"] is True
    assert by_circuit["akshare_hk_sina"]["available"] is False
    assert by_circuit["akshare_hk_em"]["available"] is True
    assert by_circuit["akshare_em"]["health_score"] == 90.0
    assert by_circuit["akshare_etf"]["health_score"] == 11.0
    assert by_circuit["akshare_em"]["available"] != by_circuit["akshare_etf"]["available"]
    assert (
        by_circuit["akshare_sina"]["available"]
        != by_circuit["akshare_hk_sina"]["available"]
    )


def test_derive_circuit_key_keeps_market_routes_distinct():
    """Coarse display tokens resolve to the exact CN/ETF/HK circuit."""
    assert field_trust.derive_circuit_key("akshare_em", stock_code="600519") == "akshare_em"
    assert field_trust.derive_circuit_key("akshare_sina", stock_code="600519") == "akshare_sina"
    assert field_trust.derive_circuit_key("akshare_em", stock_code="510300") == "akshare_etf"
    assert field_trust.derive_circuit_key("akshare_em", stock_code="00700") == "akshare_hk_em"
    assert field_trust.derive_circuit_key("akshare_sina", stock_code="00700") == "akshare_hk_sina"
    assert field_trust.derive_circuit_key("tencent", stock_code="600519") == "akshare_tencent"
    assert field_trust.derive_circuit_key("longbridge", stock_code="00700") == "longbridge"
    assert field_trust.derive_circuit_key("yfinance", stock_code="AAPL") == "yfinance"
    assert (
        field_trust.derive_circuit_key(
            "akshare_em",
            stock_code="510300",
            circuit_key="akshare_etf",
        )
        == "akshare_etf"
    )


_PUBLIC_QUOTE_SERIALIZATION_KEYS = {
    "code",
    "name",
    "source",
    "fetched_at",
    "provider_timestamp",
    "is_stale",
    "stale_seconds",
    "fallback_from",
    "market",
    "currency",
    "data_quality",
    "missing_fields",
    "granularity",
    "amount_period",
    "data_quality_evidence",
    "field_trust",
    "price",
    "change_pct",
    "change_amount",
    "volume",
    "amount",
    "volume_ratio",
    "turnover_rate",
    "amplitude",
    "open_price",
    "high",
    "low",
    "pre_close",
    "pe_ratio",
    "pb_ratio",
    "total_mv",
    "circ_mv",
    "change_60d",
    "high_52w",
    "low_52w",
    "iopv",
    "nav",
}


@patch("src.config.get_config")
def test_routed_quote_keeps_circuit_identity_off_public_payload(
    mock_get_config, validation_enabled
):
    """Routed quotes keep exact circuit identity internally, not on to_dict."""
    from dataclasses import fields as dataclass_fields

    mock_get_config.return_value = _mock_config()
    quote = _make_quote(code="00700", source=RealtimeSource.AKSHARE_EM)
    manager = DataFetcherManager(
        fetchers=[_DummyFetcher("AkshareFetcher", 0, result=quote)]
    )
    with patch.object(manager, "_longbridge_preferred", return_value=False):
        routed = manager.get_realtime_quote("00700")

    assert routed is quote
    assert field_trust.quote_circuit_key(quote) == "akshare_hk_em"
    assert any(
        attempt.get("provider") == "akshare_em"
        and attempt.get("circuit_key") == "akshare_hk_em"
        for attempt in quote.field_trust["provider_attempts"]
    )

    serialized = quote.to_dict()
    assert "circuit_key" not in serialized
    assert set(serialized) <= _PUBLIC_QUOTE_SERIALIZATION_KEYS
    assert serialized["code"] == "00700"
    assert serialized["name"] == "贵州茅台"
    assert serialized["source"] == "akshare_em"
    assert serialized["price"] == 1688.0
    assert serialized["change_pct"] == 1.2
    assert "circuit_key" not in {
        item.name for item in dataclass_fields(UnifiedRealtimeQuote)
    }


def test_unavailable_attempts_degrade_analysis_confidence():
    """Unavailable later-source attempts are gaps, never high-confidence."""
    quote = _make_quote()
    quote.is_stale = False
    field_trust.record_provider_attempt(
        quote, provider="yfinance", status=field_trust.PROVIDER_STATUS_OK, role="primary"
    )
    field_trust.record_provider_attempt(
        quote,
        provider="longbridge",
        status=field_trust.PROVIDER_STATUS_UNAVAILABLE,
    )
    field_trust.finalize(quote)
    analysis = quote.field_trust["analysis_input"]
    assert analysis["confidence"] == field_trust.CONFIDENCE_LOW
    assert analysis["failed_provider_count"] >= 1
    assert any(gap["code"] == "provider_unavailable" for gap in analysis["gaps"])


@patch("src.config.get_config")
def test_yfinance_primary_with_unavailable_us_extras(
    mock_get_config, validation_enabled
):
    """Real US route: Yfinance succeeds while Longbridge/Finnhub/AV are absent."""
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    success = _make_quote(
        code="AAPL",
        source=RealtimeSource.YFINANCE,
        provider_timestamp=fresh_ts,
    )
    manager = DataFetcherManager(
        fetchers=[_DummyFetcher("YfinanceFetcher", 0, result=success)]
    )

    quote = manager.get_realtime_quote("AAPL")

    assert quote is success
    assert quote.source is RealtimeSource.YFINANCE
    statuses = {
        (row["provider"], row["status"])
        for row in quote.field_trust["provider_health"]
    }
    assert ("yfinance", "ok") in statuses
    assert ("longbridge", "unavailable") in statuses
    assert ("finnhub", "unavailable") in statuses
    assert ("alphavantage", "unavailable") in statuses
    assert quote.field_trust["analysis_input"]["confidence"] != field_trust.CONFIDENCE_HIGH
    assert any(
        gap["code"] == "provider_unavailable"
        for gap in quote.field_trust["analysis_input"]["gaps"]
    )
