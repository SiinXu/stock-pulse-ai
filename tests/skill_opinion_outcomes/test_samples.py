from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def test_sample_identity_and_duplicate_skill_validation(isolated_db) -> None:
    history_id = _add_history(isolated_db, raw_result="{}")
    service = SkillOpinionSampleService(db_manager=isolated_db)
    valid = SkillOpinionInput(
        skill_id="alpha",
        signal="buy",
        confidence=0.5,
    )

    with pytest.raises(ValueError, match="stock_code is required"):
        service.persist(
            analysis_history_id=history_id,
            stock_code="",
            opinions=(valid,),
        )
    with pytest.raises(ValueError, match="stock_code exceeds"):
        service.persist(
            analysis_history_id=history_id,
            stock_code="X" * 17,
            opinions=(valid,),
        )
    with pytest.raises(ValueError, match="one row per skill_id"):
        service.persist(
            analysis_history_id=history_id,
            stock_code="600519",
            opinions=(valid, valid),
        )
    with pytest.raises(ValueError, match="analysis_history_id"):
        service.persist(
            analysis_history_id=0,
            stock_code="600519",
            opinions=(valid,),
        )


def test_sample_repository_rejects_ineligible_batches(isolated_db) -> None:
    repo = SkillOpinionSampleRepository(isolated_db)
    service = SkillOpinionSampleService(repo=repo)

    assert repo.insert_missing([]) == 0
    assert repo.insert_missing([{"skill_id": "missing-history"}]) == 0
    assert repo.insert_missing(
        [
            {
                "analysis_history_id": 999_999,
                "stock_code": "600519",
                "skill_id": "missing-history",
            }
        ]
    ) == 0
    assert repo.get_history(999_999) is None
    assert service.materialize_history(999_999) == 0

    empty_history_id = _add_history(isolated_db, raw_result="{}")
    assert service.materialize_history(empty_history_id) == 0


def test_pending_materialization_validates_and_applies_stock_filter(
    isolated_db,
) -> None:
    matching_id = _add_history(
        isolated_db,
        code="600519",
        raw_result=_raw_result(
            {"skill_id": "alpha", "signal": "buy", "confidence": 0.7}
        ),
    )
    other_id = _add_history(
        isolated_db,
        code="000001",
        raw_result=_raw_result(
            {"skill_id": "beta", "signal": "sell", "confidence": 0.6}
        ),
    )
    service = SkillOpinionSampleService(db_manager=isolated_db)

    assert service.materialize_pending(limit="2", stock_code="600519") == {
        "histories_scanned": 1,
        "samples_created": 1,
    }
    assert len(
        SkillOpinionSampleRepository(isolated_db).list_for_history(matching_id)
    ) == 1
    assert SkillOpinionSampleRepository(isolated_db).list_for_history(
        other_id
    ) == []
    with pytest.raises(ValueError, match="stock_code must not be blank"):
        service.materialize_pending(stock_code="   ")
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        service.materialize_pending(limit=object())
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        service.materialize_pending(limit=True)


def test_projection_supports_persisted_payload_shapes_and_malformed_inputs(
) -> None:
    item = {"skill_id": "alpha", "signal": "buy", "confidence": 0.7}
    synthesis = {
        "strategy_synthesis": {
            "supporting_skills": [item],
            "opposing_skills": {},
        }
    }

    direct = SkillOpinionSampleService._opinions_from_raw_result(synthesis)
    nested_raw = SkillOpinionSampleService._opinions_from_raw_result(
        {"raw_response": json.dumps(synthesis)}
    )

    assert [opinion.skill_id for opinion in direct] == ["alpha"]
    assert nested_raw == direct
    assert SkillOpinionSampleService._opinions_from_raw_result(None) == []
    assert SkillOpinionSampleService._opinions_from_raw_result("not-json") == []
    assert SkillOpinionSampleService._opinions_from_raw_result([]) == []
    assert SkillOpinionSampleService._strategy_synthesis(
        {"raw_response": "{}"}
    ) is None
    assert SkillOpinionSampleService._project_opinion("not-a-mapping") is None
    assert SkillOpinionSampleService._project_opinion(
        {"skill_id": "X" * 129, "signal": "buy", "confidence": 0.5}
    ) is None
    assert SkillOpinionSampleService._project_opinion(
        {"skill_id": "alpha", "signal": "buy", "confidence": float("nan")}
    ) is None


def test_data_quality_projection_fails_closed_for_malformed_context() -> None:
    service = SkillOpinionSampleService

    assert service._data_quality_level(None) is None
    assert service._data_quality_level({}) is None
    assert service._data_quality_level(
        {"analysis_context_pack_overview": "invalid"}
    ) is None
    assert service._data_quality_level(
        {"analysis_context_pack_overview": {"data_quality": "invalid"}}
    ) is None
    assert service._data_quality_level(
        {
            "analysis_context_pack_overview": {
                "data_quality": {"level": "unexpected"}
            }
        }
    ) is None
    assert service._mapping(json.dumps({"ok": True})) == {"ok": True}
    assert service._mapping(json.dumps(["not", "a", "mapping"])) is None


@pytest.mark.parametrize(
    ("opinion", "message"),
    [
        (object(), "SkillOpinionInput"),
        (
            SkillOpinionInput(skill_id="", signal="buy", confidence=0.5),
            "valid skill_id",
        ),
        (
            SkillOpinionInput(
                skill_id="X" * 129,
                signal="buy",
                confidence=0.5,
            ),
            "skill_id exceeds",
        ),
        (
            SkillOpinionInput(skill_id="alpha", signal="buy", confidence=True),
            "confidence must be numeric",
        ),
        (
            SkillOpinionInput(
                skill_id="alpha",
                signal="buy",
                confidence=object(),
            ),
            "confidence must be numeric",
        ),
        (
            SkillOpinionInput(
                skill_id="alpha",
                signal="buy",
                confidence=0.5,
                skill_version="X" * 65,
            ),
            "text exceeds 64",
        ),
        (
            SkillOpinionInput(
                skill_id="alpha",
                signal="buy",
                confidence=0.5,
                observed_at="not-a-datetime",
            ),
            "observed_at must be a datetime",
        ),
    ],
)
def test_explicit_opinion_shape_validation(opinion, message) -> None:
    with pytest.raises(ValueError, match=message):
        SkillOpinionSampleService._validated_opinion(opinion)


def test_explicit_persistence_normalizes_optional_and_aware_fields(
    isolated_db,
) -> None:
    history_id = _add_history(isolated_db, raw_result="{}")
    observed_at = datetime(
        2024,
        1,
        2,
        20,
        30,
        tzinfo=timezone(timedelta(hours=8)),
    )
    service = SkillOpinionSampleService(db_manager=isolated_db)

    assert service.persist(
        analysis_history_id=str(history_id),
        stock_code="600519",
        opinions=(
            SkillOpinionInput(
                skill_id=" alpha ",
                signal=" BUY ",
                confidence="0.75",
                skill_version=" v1 ",
                horizon=" 1d ",
                observed_at=observed_at,
            ),
        ),
        data_quality_level="UNEXPECTED",
    ) == 1

    row = SkillOpinionSampleRepository(isolated_db).list_for_history(
        history_id
    )[0]
    assert row.skill_id == "alpha"
    assert row.signal == "buy"
    assert row.confidence == 0.75
    assert row.skill_version == "v1"
    assert row.horizon == "1d"
    assert row.opinion_created_at == datetime(2024, 1, 2, 12, 30)
    assert row.data_quality_level is None
