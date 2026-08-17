# -*- coding: utf-8 -*-
"""StockService field-trust projection for API and analysis (Issue #1129)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from src.data_provider.base import DataFetcherManager
from src.data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote
from src.services.stock_service import StockService
from tests.data_provider.test_field_trust import _DummyFetcher, _make_quote, _mock_config


def _fresh_complete_quote() -> UnifiedRealtimeQuote:
    return _make_quote(
        source=RealtimeSource.EFINANCE,
        provider_timestamp=datetime.now(timezone.utc).isoformat(),
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


@patch("src.config.get_config")
def test_service_projects_fresh_quote_for_analysis(mock_get_config, monkeypatch):
    from src.application_services import reset_application_services
    from src.config import Config

    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    reset_application_services()
    Config.reset_instance()
    mock_get_config.return_value = _mock_config()
    manager = DataFetcherManager(
        fetchers=[_DummyFetcher("EfinanceFetcher", 0, result=_fresh_complete_quote())]
    )
    service = StockService(data_fetcher_manager=manager)

    view = service.get_field_trust("600519")

    assert view["status"] == "ok"
    assert view["metadata_present"] is True
    assert view["quote_source"] == "efinance"
    assert view["analysis_input"]["confidence"] == "high"
    assert view["analysis_input"]["gaps"] == []
    assert any(row["provider"] == "efinance" for row in view["provider_health"])
    price = next(entry for entry in view["fields"] if entry["field"] == "price")
    assert price["staleness"] == "fresh"
    assert price["source"] == "efinance"
    reset_application_services()
    Config.reset_instance()


@patch("src.config.get_config")
def test_service_unavailable_when_all_providers_fail(mock_get_config, monkeypatch):
    from src.application_services import reset_application_services
    from src.config import Config

    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    reset_application_services()
    Config.reset_instance()
    mock_get_config.return_value = _mock_config()
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, error=RuntimeError("down")),
            _DummyFetcher("AkshareFetcher", 1, error=RuntimeError("down")),
        ]
    )
    service = StockService(data_fetcher_manager=manager)

    view = service.get_field_trust("600519")

    assert view["status"] == "unavailable"
    assert view["metadata_present"] is False
    assert view["fields"] == []
    assert view["analysis_input"]["confidence"] == "low"
    assert view["analysis_input"]["gaps"][0]["code"] == "quote_unavailable"
    reset_application_services()
    Config.reset_instance()


@patch("src.config.get_config")
def test_service_degrades_when_comparison_raises(mock_get_config, monkeypatch):
    """Reviewer counterexample: comparison exception must not stay status=ok."""
    from src.application_services import reset_application_services
    from src.config import Config

    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    reset_application_services()
    Config.reset_instance()
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(source=RealtimeSource.EFINANCE, provider_timestamp=fresh_ts)
    secondary = _make_quote(source=RealtimeSource.AKSHARE_EM, pe_ratio=25.5)
    secondary.price = 200.0
    manager = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, result=secondary),
        ]
    )
    service = StockService(data_fetcher_manager=manager)

    with patch(
        "src.data_provider.data_validation.compare_cross_source_quotes",
        side_effect=RuntimeError("comparison exploded"),
    ):
        view = service.get_field_trust("600519")

    assert view["status"] == "degraded"
    assert view["analysis_input"]["confidence"] != "high"
    assert any(
        check.get("reason") == "comparison_failed"
        for check in view["conflict_checks"]
    )
    assert any(
        gap["code"] == "conflict_check_skipped"
        for gap in view["analysis_input"]["gaps"]
    )
    reset_application_services()
    Config.reset_instance()


def test_service_degrades_when_quote_has_no_trust_metadata():
    quote = UnifiedRealtimeQuote(
        code="600519",
        name="贵州茅台",
        source=RealtimeSource.EFINANCE,
        price=1688.0,
    )
    manager = SimpleNamespace(get_realtime_quote=lambda _code: quote)
    service = StockService(data_fetcher_manager=manager)

    view = service.get_field_trust("600519")

    assert view["status"] == "degraded"
    assert view["metadata_present"] is False
    assert view["analysis_input"]["confidence"] == "low"
    assert any(
        gap["code"] == "metadata_absent" for gap in view["analysis_input"]["gaps"]
    )
