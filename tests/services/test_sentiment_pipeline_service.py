# -*- coding: utf-8 -*-
"""Deterministic tests for the news/event sentiment pipeline (Issue #179)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.search_parts.provider_base import SearchResponse, SearchResult
from src.services.sentiment_pipeline_service import SentimentPipelineService


def _service() -> SentimentPipelineService:
    return SentimentPipelineService(
        window_days=7,
        clock=lambda: datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
    )


def test_unavailable_when_news_source_missing() -> None:
    snap = _service().build_from_intel_results(
        stock_code="AAPL",
        stock_name="Apple",
        market="us",
        intel_results=None,
        remote_search_available=False,
        news_context=None,
    )
    assert snap.status == "unavailable"
    assert snap.degraded is True
    assert snap.reason_code == "news_source_unavailable"
    assert snap.score is None
    assert snap.confidence is None
    assert snap.role == "evidence"
    assert snap.sources
    assert snap.sources[0].source_id == "news_search"
    assert snap.sources[0].status == "unavailable"


def test_bullish_score_from_structured_news() -> None:
    results = {
        "latest_news": SearchResponse(
            query="AAPL news",
            results=[
                SearchResult(
                    title="Apple beats expectations with record high iPhone demand",
                    snippet="Bullish upgrade after strong growth and profit beat expectations.",
                    url="https://example.com/1",
                    source="Wire",
                    published_date="2026-08-12T09:00:00Z",
                )
            ],
            provider="fixture",
            success=True,
        ),
        "risk_check": SearchResponse(
            query="AAPL risk",
            results=[],
            provider="fixture",
            success=True,
        ),
    }
    snap = _service().build_from_intel_results(
        stock_code="AAPL",
        market="us",
        intel_results=results,
        remote_search_available=True,
    )
    assert snap.status in {"available", "degraded"}
    assert snap.score is not None and snap.score >= 60
    assert snap.label in {"bullish", "mixed", "neutral"}
    assert snap.confidence is not None and snap.confidence > 0
    assert snap.freshness in {"fresh", "aging"}
    assert snap.evidence
    assert snap.evidence[0].source_type in {"news", "event"}
    assert snap.evidence[0].as_of_status == "present"
    assert any(row.source_id == "news_search" for row in snap.sources)


def test_bearish_score_from_risk_events() -> None:
    results = {
        "risk_check": SearchResponse(
            query="risk",
            results=[
                SearchResult(
                    title="Regulator opens investigation after profit warning",
                    snippet="Lawsuit risk and downgrade pressure after fraud allegations.",
                    url="https://example.com/risk",
                    source="Regulator Wire",
                    published_date="2026-08-12T08:00:00Z",
                )
            ],
            provider="fixture",
            success=True,
        )
    }
    snap = _service().build_from_intel_results(
        stock_code="600000",
        market="cn",
        intel_results=results,
        remote_search_available=True,
    )
    assert snap.score is not None and snap.score <= 45
    assert snap.label in {"bearish", "mixed", "neutral", "unclear"}
    assert any(item.source_type == "event" for item in snap.evidence)


def test_chinese_lexicon_and_local_intel() -> None:
    snap = _service().build_from_intel_results(
        stock_code="600519",
        stock_name="贵州茅台",
        market="cn",
        intel_results=None,
        remote_search_available=False,
        local_intel_items=[
            {
                "title": "公司超预期发布回购计划",
                "summary": "市场解读为重大利好，机构上调评级并建议增持。",
                "source": "本地资讯池",
                "published_at": "2026-08-12T07:00:00Z",
                "url": "https://example.com/local",
            }
        ],
    )
    assert snap.status in {"available", "degraded"}
    assert snap.score is not None and snap.score >= 55
    assert any(row.source_type == "local_intel" for row in snap.sources)
    assert snap.evidence


def test_text_fallback_and_public_dict() -> None:
    snap = _service().build_from_news_context(
        stock_code="TSLA",
        news_context="Tesla plunge after downgrade and profit warning.",
        remote_search_available=True,
    )
    assert snap.item_count >= 1
    assert snap.score is not None
    payload = SentimentPipelineService.snapshot_to_context_value(snap)
    assert payload["schema_version"] == "sentiment-snapshot-v1"
    assert payload["role"] == "evidence"
    assert isinstance(payload.get("evidence"), list)


def test_no_data_when_search_available_but_empty() -> None:
    snap = _service().build_from_intel_results(
        stock_code="MSFT",
        intel_results={
            "latest_news": SearchResponse(
                query="q",
                results=[],
                provider="fixture",
                success=True,
            )
        },
        remote_search_available=True,
    )
    assert snap.status == "unavailable"
    assert snap.reason_code == "no_data"
