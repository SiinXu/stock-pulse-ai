# -*- coding: utf-8 -*-
"""Contract and storage tests for bounded watchlist scoring."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Sequence

import pytest

from api.v1.schemas.watchlist_scores import WatchlistScoreResponse
from src.services.watchlist_score_service import (
    SCORE_STATUS_SCORED,
    SCORE_STATUS_UNANALYZED,
    SORT_MANUAL,
    SORT_SCORE_ASC,
    SORT_SCORE_DESC,
    WatchlistScoreService,
)
from src.storage import AnalysisHistory, DatabaseManager, DecisionSignalRecord


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _analysis(
    *,
    code: str,
    sentiment_score: Any = 70,
    created_at: datetime | None = None,
    analysis_id: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=analysis_id,
        code=code,
        sentiment_score=sentiment_score,
        operation_advice="Buy",
        created_at=created_at or datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
        report_type="detailed",
    )


def _signal(
    *,
    stock_code: str,
    source_report_id: int = 1,
    action: str = "buy",
    confidence: Any = 0.8,
    signal_id: int = 10,
    status: str = "active",
    expires_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=signal_id,
        stock_code=stock_code,
        action=action,
        confidence=confidence,
        status=status,
        source_type="analysis",
        source_report_id=source_report_id,
        decision_profile="balanced",
        created_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
        expires_at=expires_at or datetime(2026, 8, 10, tzinfo=timezone.utc),
    )


def _service(
    analyses: Mapping[str, Any] | None = None,
    signals: Mapping[str, Any] | None = None,
    *,
    analysis_timezone=None,
) -> WatchlistScoreService:
    analysis_map = dict(analyses or {})
    signal_map = dict(signals or {})
    query_log: List[str] = []

    def analysis_loader(codes: Sequence[str]) -> Dict[str, Any]:
        query_log.append(f"analysis:{len(codes)}")
        return analysis_map

    def signal_loader(codes: Sequence[str]) -> Dict[str, Any]:
        query_log.append(f"signals:{len(codes)}")
        return signal_map

    service = WatchlistScoreService(
        analysis_loader=analysis_loader,
        signal_loader=signal_loader,
        clock=lambda: NOW,
        analysis_timezone=analysis_timezone,
    )
    service._query_log = query_log  # type: ignore[attr-defined]
    return service


def test_unanalyzed_never_invents_zero() -> None:
    payload = _service().score_symbols(["AAPL", "600519"])
    assert payload["formula_version"] == "watchlist_score_v1"
    assert payload["sort"] == SORT_MANUAL
    assert payload["source_rows"] == {"analysis": 0, "signals": 0}
    for item in payload["items"]:
        assert item["status"] == SCORE_STATUS_UNANALYZED
        assert item["score"] is None
        assert item["factors"] == []


def test_scored_factor_provenance_and_source_coherence() -> None:
    service = _service(
        analyses={"600519": _analysis(code="600519", sentiment_score=72, analysis_id=5)},
        signals={
            "600519": _signal(
                stock_code="600519",
                source_report_id=5,
                action="strong_buy",
                confidence=0.9,
            )
        },
    )
    item = service.score_symbols(["600519"])["items"][0]
    assert item["status"] == SCORE_STATUS_SCORED
    assert item["score"] == 76
    assert item["freshness"] == "recent"
    signal_factor = item["factors"][1]
    assert signal_factor["status"] == "applied"
    assert signal_factor["source"]["source_report_id"] == 5
    assert signal_factor["source"]["profile"] == "balanced"
    assert signal_factor["source"]["as_of"].tzinfo is not None


def test_unrelated_signal_is_structurally_ignored() -> None:
    service = _service(
        analyses={"AAPL": _analysis(code="AAPL", sentiment_score=50, analysis_id=5)},
        signals={"AAPL": _signal(stock_code="AAPL", source_report_id=4, action="strong_buy")},
    )
    item = service.score_symbols(["AAPL"])["items"][0]
    assert item["score"] == 50
    assert item["degraded_reasons"] == ["incoherent_signal_source"]
    assert item["factors"][1]["status"] == "ignored"


def test_signal_expiry_boundary_is_excluded() -> None:
    service = _service(
        analyses={"AAPL": _analysis(code="AAPL", sentiment_score=50, analysis_id=5)},
        signals={
            "AAPL": _signal(
                stock_code="AAPL",
                source_report_id=5,
                action="strong_buy",
                expires_at=NOW,
            )
        },
    )
    item = service.score_symbols(["AAPL"])["items"][0]
    assert item["score"] == 50
    assert item["degraded_reasons"] == ["expired_signal"]


@pytest.mark.parametrize("status", ["invalidated", "archived", "expired"])
def test_terminal_signal_states_are_ignored(status: str) -> None:
    item = _service(
        analyses={"AAPL": _analysis(code="AAPL", sentiment_score=50, analysis_id=5)},
        signals={"AAPL": _signal(stock_code="AAPL", source_report_id=5, status=status)},
    ).score_symbols(["AAPL"])["items"][0]
    assert item["score"] == 50
    assert item["degraded_reasons"] == ["inactive_signal"]


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), float("-inf"), -0.1, 1.1])
def test_invalid_confidence_never_changes_score_or_leaks_non_finite_json(confidence: float) -> None:
    service = _service(
        analyses={"AAPL": _analysis(code="AAPL", sentiment_score=50, analysis_id=5)},
        signals={"AAPL": _signal(stock_code="AAPL", source_report_id=5, confidence=confidence)},
    )
    payload = service.score_symbols(["AAPL"])
    assert payload["items"][0]["score"] == 50
    assert payload["items"][0]["degraded_reasons"] == ["invalid_signal_confidence"]
    response = WatchlistScoreResponse(**payload)
    json.dumps(response.model_dump(mode="json"), allow_nan=False)


@pytest.mark.parametrize("sentiment", [None, float("nan"), float("inf"), -1, 101])
def test_invalid_sentiment_is_unanalyzed_with_reason(sentiment: Any) -> None:
    item = _service(
        analyses={"AAPL": _analysis(code="AAPL", sentiment_score=sentiment)}
    ).score_symbols(["AAPL"])["items"][0]
    assert item["status"] == SCORE_STATUS_UNANALYZED
    assert item["score"] is None
    assert item["degraded_reasons"] == ["invalid_sentiment"]
    assert item["factors"][0]["value"] is None


def test_local_naive_analysis_time_is_normalized_at_source_boundary() -> None:
    shanghai = timezone(timedelta(hours=8))
    service = WatchlistScoreService(
        analysis_loader=lambda _codes: {
            "AAPL": _analysis(
                code="AAPL",
                created_at=datetime(2026, 8, 8, 19, 0),
            )
        },
        signal_loader=lambda _codes: {},
        clock=lambda: datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc) + timedelta(hours=25),
        analysis_timezone=shanghai,
    )
    item = service.score_symbols(["AAPL"])["items"][0]
    assert item["as_of"] == datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc)
    assert item["age_days"] == 1


def test_future_clock_skew_clamps_age_to_zero() -> None:
    item = _service(
        analyses={"AAPL": _analysis(code="AAPL", created_at=NOW + timedelta(minutes=5))}
    ).score_symbols(["AAPL"])["items"][0]
    assert item["age_days"] == 0
    assert item["freshness"] == "today"


def test_missing_analysis_timestamp_is_explicitly_unknown() -> None:
    analysis = _analysis(code="AAPL")
    analysis.created_at = None
    item = _service(analyses={"AAPL": analysis}).score_symbols(["AAPL"])["items"][0]
    assert item["as_of"] is None
    assert item["age_days"] is None
    assert item["freshness"] == "unknown"


def test_market_alias_plan_includes_hk_bare_and_avoids_duplicate_identity() -> None:
    candidate_to_key, code_to_key = WatchlistScoreService._query_identity_plan(["00700.HK"])
    assert candidate_to_key["00700"] == code_to_key["00700.HK"]
    assert candidate_to_key["HK00700"] == code_to_key["00700.HK"]
    with pytest.raises(ValueError, match="duplicate market identities"):
        WatchlistScoreService._normalize_input_codes(["00700", "HK00700"])


@pytest.mark.parametrize(
    ("requested", "stored"),
    [
        ("600519.SH", "600519"),
        ("00700.HK", "00700"),
        ("AAPL.US", "AAPL"),
        ("7203.T", "7203.T"),
        ("005930.KS", "005930.KS"),
        ("2330.TW", "2330.TW"),
    ],
)
def test_supported_market_identity_variants_match_without_cross_market_fallback(
    requested: str,
    stored: str,
) -> None:
    item = _service(
        analyses={stored: _analysis(code=stored, sentiment_score=61)}
    ).score_symbols([requested])["items"][0]
    assert item["status"] == "scored"
    assert item["score"] == 61


def test_manual_and_opt_in_score_sort_are_stable() -> None:
    service = _service(
        analyses={
            "AAPL": _analysis(code="AAPL", sentiment_score=40, analysis_id=1),
            "MSFT": _analysis(code="MSFT", sentiment_score=90, analysis_id=2),
        }
    )
    assert [row["stock_code"] for row in service.score_symbols(["MSFT", "AAPL"])["items"]] == ["MSFT", "AAPL"]
    assert [row["stock_code"] for row in service.score_symbols(["MSFT", "AAPL"], sort=SORT_SCORE_ASC)["items"]] == ["AAPL", "MSFT"]
    assert [row["stock_code"] for row in service.score_symbols(["AAPL", "MSFT"], sort=SORT_SCORE_DESC)["items"]] == ["MSFT", "AAPL"]


def test_batch_loaders_are_called_once_and_rows_are_reported() -> None:
    service = _service(analyses={"AAPL": _analysis(code="AAPL")})
    payload = service.score_symbols(["AAPL", "MSFT"])
    assert len([entry for entry in service._query_log if entry.startswith("analysis:")]) == 1  # type: ignore[attr-defined]
    assert len([entry for entry in service._query_log if entry.startswith("signals:")]) == 1  # type: ignore[attr-defined]
    assert payload["query_count"] == {"analysis": 1, "signals": 1}
    assert payload["source_rows"] == {"analysis": 1, "signals": 0}


def test_storage_queries_return_only_top_one_per_identity_and_expire_due_rows(tmp_path) -> None:
    DatabaseManager.reset_instance()
    database = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'scores.sqlite'}")
    try:
        with database.get_session() as session:
            for index in range(120):
                session.add(AnalysisHistory(
                    code="AAPL",
                    sentiment_score=40 + (index % 20),
                    created_at=datetime(2026, 8, 1) + timedelta(minutes=index),
                ))
            latest = AnalysisHistory(
                code="00700",
                sentiment_score=88,
                created_at=datetime(2026, 8, 9, 8, 0),
            )
            session.add(latest)
            session.commit()
            session.refresh(latest)
            for index in range(120):
                session.add(DecisionSignalRecord(
                    stock_code="00700",
                    market="hk",
                    source_type="analysis",
                    source_report_id=latest.id,
                    trigger_source="test",
                    action="buy",
                    confidence=0.8,
                    status="active",
                    created_at=datetime(2026, 8, 9, 8, 1) + timedelta(seconds=index),
                    expires_at=datetime(2026, 8, 10),
                ))
            session.add(DecisionSignalRecord(
                stock_code="00700",
                market="hk",
                source_type="analysis",
                source_report_id=latest.id,
                trigger_source="test",
                action="strong_buy",
                confidence=1.0,
                status="active",
                created_at=datetime(2026, 8, 9, 9, 0),
                expires_at=datetime(2026, 8, 9, 12, 0),
            ))
            session.commit()

        payload = WatchlistScoreService(
            db_manager=database,
            clock=lambda: NOW,
            analysis_timezone=timezone.utc,
        ).score_symbols(["AAPL", "00700.HK"])
        assert payload["query_count"] == {"analysis": 1, "signals": 1}
        assert payload["source_rows"] == {"analysis": 2, "signals": 1}
        assert payload["items"][1]["status"] == "scored"
        with database.get_session() as session:
            expired = session.query(DecisionSignalRecord).filter(
                DecisionSignalRecord.action == "strong_buy"
            ).one()
            assert expired.status == "expired"
    finally:
        DatabaseManager.reset_instance()


def test_invalid_sort_and_too_many_codes_fail_without_truncation() -> None:
    with pytest.raises(ValueError, match="sort mode"):
        _service().score_symbols(["AAPL"], sort="random")
    with pytest.raises(ValueError, match="at most 200"):
        _service().score_symbols([f"X{index}" for index in range(201)])
