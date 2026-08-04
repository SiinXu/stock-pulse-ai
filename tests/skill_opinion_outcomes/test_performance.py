from __future__ import annotations

from datetime import datetime
from itertools import count

import pytest
from sqlalchemy import insert

from src.repositories.skill_opinion_outcome_repo import (
    SkillOpinionOutcomeRepository,
)
from src.repositories.skill_opinion_tables import (
    skill_opinion_outcome_table,
    skill_opinion_sample_table,
)
from src.services.skill_opinion_outcome_service import (
    SKILL_OPINION_OUTCOME_ENGINE_VERSION,
)
from src.services.skill_opinion_performance_service import (
    SkillOpinionPerformanceService,
)
from src.storage import AnalysisHistory, DatabaseManager


_ROW_SEQUENCE = count(1)
_FIXED_NOW = datetime(2026, 8, 4, 12, 0, 0)


def _add_outcome(
    db: DatabaseManager,
    *,
    skill_id: str = "alpha",
    horizon: str = "1d",
    engine_version: str = SKILL_OPINION_OUTCOME_ENGINE_VERSION,
    eval_status: str,
    outcome: str | None = None,
    directional_return_pct: float | None = None,
) -> None:
    with db.session_scope() as session:
        history = AnalysisHistory(
            query_id=(
                f"stats-{skill_id}-{horizon}-{eval_status}-"
                f"{next(_ROW_SEQUENCE)}"
            ),
            code="600519",
            report_type="simple",
            created_at=_FIXED_NOW,
        )
        session.add(history)
        session.flush()
        sample_result = session.execute(
            insert(skill_opinion_sample_table).values(
                analysis_history_id=history.id,
                stock_code="600519",
                skill_id=skill_id,
                skill_version=None,
                signal=(
                    "hold" if eval_status == "observational" else "buy"
                ),
                confidence=0.8,
                horizon=None,
                data_quality_level=None,
                opinion_created_at=None,
                sample_schema_version="skill-opinion-sample-v1",
                created_at=_FIXED_NOW,
            )
        )
        sample_id = int(sample_result.inserted_primary_key[0])
        session.execute(
            insert(skill_opinion_outcome_table).values(
                skill_opinion_sample_id=sample_id,
                horizon=horizon,
                engine_version=engine_version,
                eval_status=eval_status,
                outcome=outcome,
                direction_correct=(
                    outcome == "hit" if eval_status == "evaluated" else None
                ),
                unable_reason=(
                    "invalid_metadata"
                    if eval_status == "unable"
                    else None
                ),
                analysis_date=None,
                start_trade_date=None,
                end_trade_date=None,
                start_price=None,
                end_close=None,
                stock_return_pct=None,
                directional_return_pct=directional_return_pct,
                created_at=_FIXED_NOW,
                updated_at=_FIXED_NOW,
            )
        )


def _add_evaluated_rows(
    db: DatabaseManager,
    *,
    skill_id: str = "alpha",
    horizon: str = "1d",
    engine_version: str = SKILL_OPINION_OUTCOME_ENGINE_VERSION,
    hit: int,
    miss: int,
) -> None:
    for _ in range(hit):
        _add_outcome(
            db,
            skill_id=skill_id,
            horizon=horizon,
            engine_version=engine_version,
            eval_status="evaluated",
            outcome="hit",
            directional_return_pct=2.0,
        )
    for _ in range(miss):
        _add_outcome(
            db,
            skill_id=skill_id,
            horizon=horizon,
            engine_version=engine_version,
            eval_status="evaluated",
            outcome="miss",
            directional_return_pct=-1.0,
        )


def test_repository_aggregates_raw_bucket_counts(isolated_db) -> None:
    _add_evaluated_rows(isolated_db, hit=1, miss=1)
    _add_outcome(
        isolated_db,
        eval_status="observational",
        outcome="observational",
    )
    _add_outcome(isolated_db, eval_status="unable")
    _add_outcome(isolated_db, eval_status="pending")

    buckets = SkillOpinionOutcomeRepository(
        isolated_db
    ).list_performance_buckets(
        engine_version=SKILL_OPINION_OUTCOME_ENGINE_VERSION,
    )

    assert len(buckets) == 1
    bucket = buckets[0]
    assert bucket.total == 5
    assert bucket.pending == 1
    assert bucket.evaluated == 2
    assert bucket.observational == 1
    assert bucket.unable == 1
    assert bucket.hit == 1
    assert bucket.miss == 1
    assert bucket.avg_directional_return_pct == pytest.approx(0.5)


def test_insufficient_bucket_keeps_metrics_private(isolated_db) -> None:
    _add_evaluated_rows(isolated_db, hit=18, miss=11)
    for _ in range(5):
        _add_outcome(
            isolated_db,
            eval_status="observational",
            outcome="observational",
        )
        _add_outcome(isolated_db, eval_status="unable")
        _add_outcome(isolated_db, eval_status="pending")

    bucket = SkillOpinionPerformanceService(
        db_manager=isolated_db
    ).get_stats()["buckets"][0]

    assert bucket["evaluated"] == 29
    assert bucket["sample_sufficient"] is False
    assert bucket["sample_status"] == "observational"
    assert bucket["hit_rate_pct"] is None
    assert bucket["miss_rate_pct"] is None
    assert bucket["avg_directional_return_pct"] is None
    assert bucket["unable_rate_pct"] is None


def test_exact_threshold_unlocks_metrics_with_terminal_denominator(
    isolated_db,
) -> None:
    _add_evaluated_rows(isolated_db, hit=18, miss=12)
    _add_outcome(
        isolated_db,
        eval_status="observational",
        outcome="observational",
    )
    _add_outcome(isolated_db, eval_status="unable")
    _add_outcome(isolated_db, eval_status="unable")
    for _ in range(10):
        _add_outcome(isolated_db, eval_status="pending")

    bucket = SkillOpinionPerformanceService(
        db_manager=isolated_db
    ).get_stats()["buckets"][0]

    assert bucket["total"] == 43
    assert bucket["evaluated"] == 30
    assert bucket["sample_sufficient"] is True
    assert bucket["hit_rate_pct"] == 60.0
    assert bucket["miss_rate_pct"] == 40.0
    assert bucket["avg_directional_return_pct"] == 0.8
    assert bucket["unable_rate_pct"] == 6.06


def test_sibling_buckets_cannot_combine_to_unlock_metrics(
    isolated_db,
) -> None:
    for skill_id, horizon, engine_version in (
        ("alpha", "1d", SKILL_OPINION_OUTCOME_ENGINE_VERSION),
        ("alpha", "3d", SKILL_OPINION_OUTCOME_ENGINE_VERSION),
        ("beta", "1d", SKILL_OPINION_OUTCOME_ENGINE_VERSION),
        ("alpha", "1d", "skill-opinion-outcome-v2"),
    ):
        _add_evaluated_rows(
            isolated_db,
            skill_id=skill_id,
            horizon=horizon,
            engine_version=engine_version,
            hit=16,
            miss=0,
        )

    service = SkillOpinionPerformanceService(db_manager=isolated_db)
    current = service.get_stats()["buckets"]
    future = service.get_stats(
        engine_version="skill-opinion-outcome-v2"
    )["buckets"]

    assert len(current) == 3
    assert all(bucket["evaluated"] == 16 for bucket in current)
    assert all(bucket["sample_sufficient"] is False for bucket in current)
    assert len(future) == 1
    assert future[0]["sample_sufficient"] is False


def test_filters_and_ordering_use_exact_bucket_identity(isolated_db) -> None:
    for skill_id, horizon, repetitions in (
        ("zeta", "3d", 3),
        ("alpha", "10d", 2),
        ("alpha", "1d", 2),
        ("beta", "5d", 3),
    ):
        _add_evaluated_rows(
            isolated_db,
            skill_id=skill_id,
            horizon=horizon,
            hit=repetitions,
            miss=0,
        )

    service = SkillOpinionPerformanceService(db_manager=isolated_db)
    buckets = service.get_stats()["buckets"]
    filtered = service.get_stats(
        skill_ids=["alpha", "missing", "alpha"],
        horizons=["10d"],
    )["buckets"]

    assert [
        (bucket["skill_id"], bucket["horizon"], bucket["total"])
        for bucket in buckets
    ] == [
        ("beta", "5d", 3),
        ("zeta", "3d", 3),
        ("alpha", "1d", 2),
        ("alpha", "10d", 2),
    ]
    assert [
        (bucket["skill_id"], bucket["horizon"])
        for bucket in filtered
    ] == [("alpha", "10d")]

    single_skill = service.get_stats(skill_id="beta")["buckets"]
    assert [bucket["skill_id"] for bucket in single_skill] == ["beta"]


@pytest.mark.parametrize(
    "filters",
    [
        {"skill_id": "   "},
        {"skill_ids": []},
        {"skill_ids": ["alpha"], "skill_id": "alpha"},
        {"horizons": []},
        {"horizons": ["2d"]},
        {"engine_version": "   "},
    ],
)
def test_invalid_statistics_filters_fail_closed(
    isolated_db,
    filters,
) -> None:
    with pytest.raises(ValueError):
        SkillOpinionPerformanceService(
            db_manager=isolated_db
        ).get_stats(**filters)
