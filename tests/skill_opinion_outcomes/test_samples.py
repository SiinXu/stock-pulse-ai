from __future__ import annotations

from datetime import datetime
import json

import pytest

from src.repositories.skill_opinion_sample_repo import (
    SkillOpinionSampleRepository,
)
from src.schemas.skill_opinion_outcome import SkillOpinionInput
from src.services.skill_opinion_sample_service import (
    SKILL_OPINION_SAMPLE_SCHEMA_VERSION,
    SkillOpinionSampleService,
)
from src.storage import AnalysisHistory, DatabaseManager


def _raw_result(*items: dict) -> str:
    return json.dumps(
        {
            "dashboard": {
                "strategy_synthesis": {
                    "supporting_skills": list(items),
                    "opposing_skills": [],
                }
            }
        }
    )


def _context() -> str:
    return json.dumps(
        {
            "analysis_context_pack_overview": {
                "data_quality": {"level": "usable"}
            }
        }
    )


def _add_history(
    db: DatabaseManager,
    *,
    raw_result: str,
    code: str = "600519",
) -> int:
    with db.session_scope() as session:
        row = AnalysisHistory(
            query_id="sample-materialization",
            code=code,
            report_type="simple",
            raw_result=raw_result,
            context_snapshot=_context(),
            created_at=datetime(2024, 1, 2, 18, 0, 0),
        )
        session.add(row)
        session.flush()
        return int(row.id)


def test_materializes_low_sensitivity_samples_idempotently(
    isolated_db,
    fixed_now,
) -> None:
    history_id = _add_history(
        isolated_db,
        raw_result=_raw_result(
            {
                "skill_id": "bull_trend",
                "signal": "buy",
                "confidence": 0.81,
                "reasoning": "must never be copied",
            },
            {
                "skill_id": "hot_theme",
                "signal": "hold",
                "confidence": 0.55,
                "raw_data": {"private": "must never be copied"},
            },
        ),
    )
    repo = SkillOpinionSampleRepository(
        isolated_db,
        clock=lambda: fixed_now,
    )
    service = SkillOpinionSampleService(repo=repo)

    assert service.materialize_history(history_id) == 2
    assert service.materialize_history(history_id) == 0

    rows = repo.list_for_history(history_id)
    assert [
        (row.skill_id, row.signal, row.confidence)
        for row in rows
    ] == [
        ("bull_trend", "buy", 0.81),
        ("hot_theme", "hold", 0.55),
    ]
    assert all(
        row.sample_schema_version == SKILL_OPINION_SAMPLE_SCHEMA_VERSION
        for row in rows
    )
    assert all(row.data_quality_level == "usable" for row in rows)
    assert all(row.skill_version is None for row in rows)
    assert all(row.horizon is None for row in rows)
    assert all(row.opinion_created_at is None for row in rows)
    assert all(row.created_at == fixed_now for row in rows)


def test_pending_materialization_scans_only_unprojected_reports(
    isolated_db,
    fixed_now,
) -> None:
    first_id = _add_history(
        isolated_db,
        raw_result=_raw_result(
            {"skill_id": "alpha", "signal": "buy", "confidence": 0.7}
        ),
    )
    second_id = _add_history(
        isolated_db,
        raw_result=_raw_result(
            {"skill_id": "beta", "signal": "sell", "confidence": 0.6}
        ),
    )
    repo = SkillOpinionSampleRepository(
        isolated_db,
        clock=lambda: fixed_now,
    )
    service = SkillOpinionSampleService(repo=repo)

    assert service.materialize_pending(limit=10) == {
        "histories_scanned": 2,
        "samples_created": 2,
    }
    assert service.materialize_pending(limit=10) == {
        "histories_scanned": 0,
        "samples_created": 0,
    }
    assert len(repo.list_for_history(first_id)) == 1
    assert len(repo.list_for_history(second_id)) == 1


def test_materialization_ignores_invalid_projected_items(
    isolated_db,
) -> None:
    history_id = _add_history(
        isolated_db,
        raw_result=_raw_result(
            {"skill_id": "valid", "signal": "sell", "confidence": 0.6},
            {"skill_id": "invalid-signal", "signal": "moon", "confidence": 0.9},
            {"skill_id": "invalid-confidence", "signal": "buy", "confidence": True},
            {
                "skill_id": "flagged-invalid",
                "signal": "hold",
                "confidence": 0.5,
                "invalid_signal": True,
            },
        ),
    )

    assert SkillOpinionSampleService(
        db_manager=isolated_db
    ).materialize_history(history_id) == 1
    rows = SkillOpinionSampleRepository(isolated_db).list_for_history(
        history_id
    )
    assert [(row.skill_id, row.signal) for row in rows] == [
        ("valid", "sell")
    ]


def test_conflicting_duplicate_projection_fails_without_partial_write(
    isolated_db,
) -> None:
    raw_result = json.dumps(
        {
            "dashboard": {
                "strategy_synthesis": {
                    "supporting_skills": [
                        {
                            "skill_id": "alpha",
                            "signal": "buy",
                            "confidence": 0.8,
                        }
                    ],
                    "opposing_skills": [
                        {
                            "skill_id": "alpha",
                            "signal": "sell",
                            "confidence": 0.8,
                        }
                    ],
                }
            }
        }
    )
    history_id = _add_history(isolated_db, raw_result=raw_result)
    service = SkillOpinionSampleService(db_manager=isolated_db)

    with pytest.raises(ValueError, match="conflicting skill facts"):
        service.materialize_history(history_id)

    assert SkillOpinionSampleRepository(isolated_db).list_for_history(
        history_id
    ) == []


@pytest.mark.parametrize(
    "confidence",
    [float("nan"), float("inf"), -0.01, 1.01, True],
)
def test_explicit_persistence_rejects_invalid_confidence(
    isolated_db,
    confidence,
) -> None:
    history_id = _add_history(isolated_db, raw_result="{}")
    service = SkillOpinionSampleService(db_manager=isolated_db)

    with pytest.raises(ValueError, match="skill opinion confidence"):
        service.persist(
            analysis_history_id=history_id,
            stock_code="600519",
            opinions=(
                SkillOpinionInput(
                    skill_id="alpha",
                    signal="buy",
                    confidence=confidence,
                ),
            ),
        )

    assert SkillOpinionSampleRepository(isolated_db).list_for_history(
        history_id
    ) == []
