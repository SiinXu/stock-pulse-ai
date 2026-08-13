# -*- coding: utf-8 -*-
"""Schema contracts for sentiment-snapshot-v1 (Issue #179)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.sentiment_snapshot import (
    SENTIMENT_DISCLAIMER,
    SENTIMENT_SNAPSHOT_SCHEMA_VERSION,
    SentimentEvidenceItem,
    SentimentSnapshot,
    SentimentSourceSummary,
)


def test_snapshot_requires_role_evidence_and_stable_version() -> None:
    snapshot = SentimentSnapshot(
        stock_code="600519",
        as_of="2026-08-12T00:00:00Z",
        status="unavailable",
        degraded=True,
        reason_code="no_data",
    )
    assert snapshot.schema_version == SENTIMENT_SNAPSHOT_SCHEMA_VERSION
    assert snapshot.role == "evidence"
    assert snapshot.method == "news_lexicon_v1"
    assert snapshot.disclaimer == SENTIMENT_DISCLAIMER
    payload = snapshot.to_public_dict()
    assert payload["role"] == "evidence"
    assert payload["score"] is None


def test_evidence_item_bounds_and_polarity() -> None:
    item = SentimentEvidenceItem(
        evidence_id="sent-abc",
        source_type="news",
        source_id="reuters",
        snippet="Company beat expectations on revenue.",
        as_of="2026-08-12T08:00:00Z",
        as_of_status="present",
        confidence=0.7,
        polarity=0.8,
    )
    assert item.polarity == 0.8
    with pytest.raises(ValidationError):
        SentimentEvidenceItem(
            evidence_id="x",
            source_type="news",
            source_id="x",
            snippet="ok",
            polarity=1.5,
        )


def test_source_summary_status_contract() -> None:
    row = SentimentSourceSummary(
        source_id="news_search",
        source_type="news",
        status="partial",
        item_count=2,
    )
    assert row.status == "partial"
    with pytest.raises(ValidationError):
        SentimentSourceSummary(
            source_id="news_search",
            source_type="news",
            status="broken",  # type: ignore[arg-type]
        )
