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
        return StockAnalysisPipeline(config=config)


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
