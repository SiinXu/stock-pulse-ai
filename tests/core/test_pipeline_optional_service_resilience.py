# -*- coding: utf-8 -*-
"""Regression tests for optional pipeline service degradation logs."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.core.pipeline import StockAnalysisPipeline


def _make_config() -> SimpleNamespace:
    return SimpleNamespace(
        max_workers=2,
        save_context_snapshot=False,
        bocha_api_keys=[],
        tavily_api_keys=[],
        anspire_api_keys=[],
        brave_api_keys=[],
        serpapi_keys=[],
        minimax_api_keys=[],
        searxng_base_urls=[],
        searxng_public_instances_enabled=False,
        news_max_age_days=7,
        news_strategy_profile="short",
        enable_realtime_quote=False,
        realtime_source_priority=[],
        enable_chip_distribution=False,
        social_sentiment_api_key="",
        social_sentiment_api_url="https://example.invalid/social",
    )


def _build_pipeline(config: SimpleNamespace) -> StockAnalysisPipeline:
    with patch("src.core.pipeline.get_db", return_value=MagicMock()), \
         patch("src.core.pipeline.DataFetcherManager", return_value=MagicMock()), \
         patch("src.core.pipeline.StockTrendAnalyzer", return_value=MagicMock()), \
         patch("src.core.pipeline.GeminiAnalyzer", return_value=MagicMock()), \
         patch("src.core.pipeline.NotificationService", return_value=MagicMock()):
        return StockAnalysisPipeline(config=config, data_fetcher_manager=MagicMock())


def test_search_service_init_failure_logs_safe_diagnostic_and_failure_state(caplog):
    config = _make_config()
    social_service = MagicMock()
    social_service.is_available = False
    canary = "search-init-canary"
    sensitive_error = (
        f"search init failed api_key={canary} at "
        f"https://private.example.invalid/search?token={canary}"
    )

    with patch("src.core.pipeline.SearchService", side_effect=RuntimeError(sensitive_error)), \
         patch("src.core.pipeline.SocialSentimentService", return_value=social_service), \
         caplog.at_level(logging.WARNING, logger="src.core.pipeline"):
        pipeline = _build_pipeline(config)

    assert pipeline.search_service is None

    init_failure_records = [
        record
        for record in caplog.records
        if "Search service initialization failed; continuing without search" in record.message
    ]
    assert len(init_failure_records) == 1
    assert init_failure_records[0].exc_info is None
    assert "error_code=pipeline_search_service_init_failed" in init_failure_records[0].message
    assert "exception_type=RuntimeError" in init_failure_records[0].message
    assert "[REDACTED]" in init_failure_records[0].message
    assert "[REDACTED_URL]" in init_failure_records[0].message
    assert canary not in caplog.text
    assert "private.example.invalid" not in caplog.text
    assert "Traceback (most recent call last)" not in caplog.text
    assert (
        "Search service is unavailable because initialization or a dependency failed"
        in caplog.text
    )
    assert (
        "Search service is unavailable because no search capability is configured"
        not in caplog.text
    )


def test_social_sentiment_init_failure_logs_safe_diagnostic(caplog):
    config = _make_config()
    search_service = MagicMock()
    search_service.is_available = False
    canary = "social-init-canary"
    sensitive_error = (
        f"social init failed Authorization: Bearer {canary} at "
        f"https://private.example.invalid/social?token={canary}"
    )

    with patch("src.core.pipeline.SearchService", return_value=search_service), \
         patch("src.core.pipeline.SocialSentimentService", side_effect=RuntimeError(sensitive_error)), \
         caplog.at_level(logging.WARNING, logger="src.core.pipeline"):
        pipeline = _build_pipeline(config)

    assert pipeline.social_sentiment_service is None

    init_failure_records = [
        record
        for record in caplog.records
        if "Social sentiment service initialization failed" in record.message
    ]
    assert len(init_failure_records) == 1
    assert init_failure_records[0].exc_info is None
    assert "error_code=pipeline_social_sentiment_service_init_failed" in init_failure_records[0].message
    assert "exception_type=RuntimeError" in init_failure_records[0].message
    assert "[REDACTED]" in init_failure_records[0].message
    assert "[REDACTED_URL]" in init_failure_records[0].message
    assert canary not in caplog.text
    assert "private.example.invalid" not in caplog.text
    assert "Traceback (most recent call last)" not in caplog.text


def test_hotspot_init_failure_is_debug_fail_open_and_does_not_skip_search(caplog):
    config = _make_config()
    search_service = MagicMock()
    search_service.is_available = False
    social_service = MagicMock()
    social_service.is_available = False
    canary = "hotspot-init-canary"
    sensitive_error = (
        f"hotspot init failed api_key={canary} at "
        f"https://private.example.invalid/hotspot?token={canary}"
    )
    hotspot_ctor = MagicMock(side_effect=RuntimeError(sensitive_error))
    search_ctor = MagicMock(return_value=search_service)

    with patch("src.core.pipeline.MarketHotspotService", hotspot_ctor), patch(
        "src.core.pipeline.SearchService", search_ctor
    ), patch(
        "src.core.pipeline.SocialSentimentService",
        return_value=social_service,
    ), caplog.at_level(logging.DEBUG, logger="src.core.pipeline"):
        pipeline = _build_pipeline(config)

    assert pipeline.market_hotspot_service is None
    assert pipeline.search_service is search_service
    hotspot_ctor.assert_called_once()
    assert "fetcher_manager" in hotspot_ctor.call_args.kwargs
    search_ctor.assert_called_once()

    init_failure_records = [
        record
        for record in caplog.records
        if "Market hotspot service initialization failed; continuing without hotspot data"
        in record.message
    ]
    assert len(init_failure_records) == 1
    assert init_failure_records[0].levelno == logging.DEBUG
    assert init_failure_records[0].exc_info is None
    assert "error_code=pipeline_market_hotspot_service_init_failed" in init_failure_records[0].message
    assert "exception_type=RuntimeError" in init_failure_records[0].message
    assert "[REDACTED]" in init_failure_records[0].message
    assert "[REDACTED_URL]" in init_failure_records[0].message
    assert canary not in caplog.text
    assert "private.example.invalid" not in caplog.text
    assert "Traceback (most recent call last)" not in caplog.text


def test_search_init_failure_still_constructs_social_sentiment_service():
    config = _make_config()
    social_service = MagicMock()
    social_service.is_available = False
    social_ctor = MagicMock(return_value=social_service)

    with patch(
        "src.core.pipeline.SearchService",
        side_effect=RuntimeError("search boom"),
    ), patch("src.core.pipeline.SocialSentimentService", social_ctor):
        pipeline = _build_pipeline(config)

    assert pipeline.search_service is None
    assert pipeline.social_sentiment_service is social_service
    social_ctor.assert_called_once_with(
        api_key=config.social_sentiment_api_key,
        api_url=config.social_sentiment_api_url,
    )


def test_search_service_unavailable_when_not_configured_logs_unconfigured_state(caplog):
    config = _make_config()
    search_service = MagicMock()
    search_service.is_available = False
    social_service = MagicMock()
    social_service.is_available = False

    with patch("src.core.pipeline.SearchService", return_value=search_service) as search_ctor, \
         patch("src.core.pipeline.SocialSentimentService", return_value=social_service), \
         caplog.at_level(logging.INFO, logger="src.core.pipeline"):
        pipeline = _build_pipeline(config)

    assert pipeline.search_service is search_service
    search_ctor.assert_called_once()
    kwargs = search_ctor.call_args.kwargs
    assert kwargs["rss_news_feed_urls"] is None
    assert kwargs["rss_news_fetch_timeout_sec"] == 8.0
    assert kwargs["news_strategy_profile"] == "short"
    assert (
        "Search service is unavailable because no search capability is configured"
        in caplog.text
    )
    assert "Search service initialization failed" not in caplog.text
    assert (
        "Search service is unavailable because initialization or a dependency failed"
        not in caplog.text
    )


def test_search_init_failure_keeps_realtime_and_chip_logs_before_search_status(caplog):
    config = _make_config()
    social_service = MagicMock()
    social_service.is_available = False

    with patch(
        "src.core.pipeline.SearchService",
        side_effect=RuntimeError("search boom"),
    ), patch("src.core.pipeline.SocialSentimentService", return_value=social_service), \
         caplog.at_level(logging.INFO, logger="src.core.pipeline"):
        pipeline = _build_pipeline(config)

    assert pipeline.search_service is None
    messages = [record.message for record in caplog.records]
    realtime_idx = messages.index(
        "Realtime quotes disabled; historical close prices will be used"
    )
    chip_idx = messages.index("Chip-distribution analysis disabled")
    status_idx = messages.index(
        "Search service is unavailable because initialization or a dependency failed"
    )
    assert realtime_idx < chip_idx < status_idx


def test_social_sentiment_available_logs_us_stocks_only(caplog):
    config = _make_config()
    search_service = MagicMock()
    search_service.is_available = False
    social_service = MagicMock()
    social_service.is_available = True

    with patch("src.core.pipeline.SearchService", return_value=search_service), \
         patch("src.core.pipeline.SocialSentimentService", return_value=social_service), \
         caplog.at_level(logging.INFO, logger="src.core.pipeline"):
        pipeline = _build_pipeline(config)

    assert pipeline.social_sentiment_service is social_service
    assert "Social sentiment service enabled (Reddit/X/Polymarket, US stocks only)" in caplog.text


def test_emit_progress_logs_safe_identifier_context_when_callback_fails(caplog):
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.query_id = "query-123"
    canary = "progress-message-canary"

    def _fail_callback(progress, message):
        raise RuntimeError(f"cannot send {progress}:{message}")

    pipeline.progress_callback = _fail_callback

    with caplog.at_level(logging.WARNING, logger="src.core.pipeline"):
        pipeline._emit_progress(
            55,
            f"fetching news api_key={canary} https://private.example.invalid?token={canary}",
        )

    records = [record for record in caplog.records if "Pipeline progress callback failed" in record.message]
    assert len(records) == 1
    record = records[0]
    assert "progress=55" in record.message
    assert "query_id=query-123" in record.message
    assert "error_code=pipeline_progress_callback_failed" in record.message
    assert "exception_type=RuntimeError" in record.message
    assert canary not in caplog.text
    assert "private.example.invalid" not in caplog.text
    assert "Traceback (most recent call last)" not in caplog.text
