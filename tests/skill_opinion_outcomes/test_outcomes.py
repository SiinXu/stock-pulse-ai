from __future__ import annotations

from datetime import date, datetime
import json

import pytest

from src.repositories.skill_opinion_outcome_repo import (
    SkillOpinionOutcomeRepository,
)
from src.repositories.skill_opinion_sample_repo import (
    SkillOpinionSampleRepository,
)
from src.schemas.skill_opinion_outcome import (
    SkillOpinionInput,
    SkillOpinionOutcomeEvaluator,
    StockDailyBar,
)
from src.services.skill_opinion_outcome_service import (
    SKILL_OPINION_OUTCOME_ENGINE_VERSION,
    SkillOpinionOutcomeService,
)
from src.services.skill_opinion_sample_service import SkillOpinionSampleService
from src.storage import AnalysisHistory, DatabaseManager, StockDaily


def _snapshot(
    day: str,
    *,
    market: str = "cn",
    effective_day: str | None = None,
) -> str:
    return json.dumps(
        {
            "enhanced_context": {"date": day},
            "market_phase_summary": {
                "phase": "postmarket",
                "market": market,
                "effective_daily_bar_date": effective_day or day,
            },
        }
    )


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


def _add_history(
    db: DatabaseManager,
    *,
    code: str = "600519",
    context_snapshot: str | None = None,
    items: tuple[dict, ...] = (
        {"skill_id": "alpha", "signal": "buy", "confidence": 0.8},
    ),
) -> int:
    with db.session_scope() as session:
        history = AnalysisHistory(
            query_id=f"outcome-{code}-{len(items)}",
            code=code,
            report_type="simple",
            raw_result=_raw_result(*items),
            context_snapshot=context_snapshot or _snapshot("2024-01-02"),
            created_at=datetime(2024, 1, 2, 18, 0, 0),
        )
        session.add(history)
        session.flush()
        return int(history.id)


def _seed_bars(
    db: DatabaseManager,
    *,
    code: str,
    bars: list[tuple[date, float]],
) -> None:
    with db.session_scope() as session:
        for day, close in bars:
            session.add(
                StockDaily(
                    code=code,
                    date=day,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                )
            )


@pytest.mark.parametrize(
    ("signal", "end_close", "expected_outcome", "expected_correct"),
    [
        ("buy", 105.0, "hit", True),
        ("strong_buy", 95.0, "miss", False),
        ("sell", 95.0, "hit", True),
        ("strong_sell", 105.0, "miss", False),
        ("buy", 100.0, "miss", False),
    ],
)
def test_pure_evaluator_uses_strict_directional_return(
    signal,
    end_close,
    expected_outcome,
    expected_correct,
) -> None:
    result = SkillOpinionOutcomeEvaluator.evaluate(
        signal=signal,
        horizon="1d",
        analysis_date=date(2024, 1, 2),
        start_bar=StockDailyBar(
            code="600519",
            date=date(2024, 1, 2),
            close=100.0,
        ),
        forward_bars=(
            StockDailyBar(
                code="600519",
                date=date(2024, 1, 3),
                close=end_close,
            ),
        ),
    )

    assert result.eval_status == "evaluated"
    assert result.outcome == expected_outcome
    assert result.direction_correct is expected_correct


def test_pure_evaluator_defers_non_finite_computed_return() -> None:
    result = SkillOpinionOutcomeEvaluator.evaluate(
        signal="buy",
        horizon="1d",
        analysis_date=date(2024, 1, 2),
        start_bar=StockDailyBar(
            code="600519",
            date=date(2024, 1, 2),
            close=5e-324,
        ),
        forward_bars=(
            StockDailyBar(
                code="600519",
                date=date(2024, 1, 3),
                close=1e308,
            ),
        ),
    )

    assert result.eval_status == "pending"
    assert result.unable_reason == "invalid_return"
    assert result.stock_return_pct is None


def test_run_materializes_and_evaluates_each_skill_own_signal(
    isolated_db,
) -> None:
    history_id = _add_history(
        isolated_db,
        items=(
            {"skill_id": "buyer", "signal": "buy", "confidence": 0.8},
            {"skill_id": "seller", "signal": "sell", "confidence": 0.7},
            {"skill_id": "observer", "signal": "hold", "confidence": 0.6},
        ),
    )
    _seed_bars(
        isolated_db,
        code="600519",
        bars=[
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 105.0),
        ],
    )

    result = SkillOpinionOutcomeService(
        db_manager=isolated_db
    ).run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d"],
        limit=3,
    )

    assert result["samples_created"] == 3
    assert result["processed_keys"] == 3
    by_skill = {item["skill_id"]: item for item in result["items"]}
    assert by_skill["buyer"]["outcome"] == "hit"
    assert by_skill["seller"]["outcome"] == "miss"
    assert by_skill["observer"]["eval_status"] == "observational"
    assert by_skill["observer"]["direction_correct"] is None
    assert by_skill["observer"]["directional_return_pct"] is None


def test_pending_retries_then_terminal_outcome_is_immutable(
    isolated_db,
) -> None:
    history_id = _add_history(isolated_db)
    _seed_bars(
        isolated_db,
        code="600519",
        bars=[(date(2024, 1, 2), 100.0)],
    )
    service = SkillOpinionOutcomeService(db_manager=isolated_db)

    pending = service.run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d"],
    )["items"][0]
    assert pending["eval_status"] == "pending"
    assert pending["unable_reason"] == "insufficient_future_data"

    _seed_bars(
        isolated_db,
        code="600519",
        bars=[(date(2024, 1, 3), 105.0)],
    )
    evaluated = service.run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d"],
    )["items"][0]
    assert evaluated["eval_status"] == "evaluated"
    assert evaluated["stock_return_pct"] == pytest.approx(5.0)

    with isolated_db.session_scope() as session:
        bar = session.query(StockDaily).filter_by(
            code="600519",
            date=date(2024, 1, 3),
        ).one()
        bar.close = 90.0
    assert service.run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d"],
    )["processed_keys"] == 0
    sample_id = SkillOpinionSampleRepository(
        isolated_db
    ).list_for_history(history_id)[0].id
    stored = SkillOpinionOutcomeRepository(isolated_db).get_outcome(
        sample_id=sample_id,
        horizon="1d",
        engine_version=SKILL_OPINION_OUTCOME_ENGINE_VERSION,
    )
    assert stored is not None
    assert stored.stock_return_pct == pytest.approx(5.0)


def test_run_limit_counts_outcome_keys_across_horizons(isolated_db) -> None:
    history_id = _add_history(
        isolated_db,
        items=(
            {"skill_id": "alpha", "signal": "buy", "confidence": 0.8},
            {"skill_id": "beta", "signal": "sell", "confidence": 0.7},
        ),
    )

    result = SkillOpinionOutcomeService(
        db_manager=isolated_db
    ).run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d", "3d", "5d", "10d"],
        limit=3,
    )

    assert result["processed_keys"] == 3
    assert result["created"] == 3
    assert len(result["items"]) == 3
    assert result["limit_unit"] == "outcome_key"


def test_exact_start_and_forward_bars_never_cross_code_shapes(
    isolated_db,
) -> None:
    history_id = _add_history(isolated_db, code="600519.SH")
    _seed_bars(
        isolated_db,
        code="600519.SH",
        bars=[(date(2024, 1, 2), 100.0)],
    )
    _seed_bars(
        isolated_db,
        code="600519",
        bars=[(date(2024, 1, 3), 105.0)],
    )

    item = SkillOpinionOutcomeService(
        db_manager=isolated_db
    ).run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d"],
    )["items"][0]

    assert item["eval_status"] == "pending"
    assert item["unable_reason"] == "insufficient_future_data"
    assert item["start_trade_date"] == "2024-01-02"
    assert item["end_trade_date"] is None


@pytest.mark.parametrize(
    ("context_snapshot", "expected_reason"),
    [
        (_snapshot("2024-01-02", market="us"), "invalid_market_phase_context"),
        (
            _snapshot(
                "2024-01-02",
                effective_day="invalid",
            ),
            "invalid_effective_daily_bar_date",
        ),
        (
            _snapshot(
                "2024-01-02",
                effective_day="2024-01-03",
            ),
            "future_effective_daily_bar_date",
        ),
        (
            json.dumps({"enhanced_context": {"date": "2024-01-02"}}),
            "missing_market_phase_context",
        ),
        (
            json.dumps(
                {
                    "enhanced_context": {"date": "2024-01-02"},
                    "market_phase_summary": {
                        "effective_daily_bar_date": "2024-01-02"
                    },
                }
            ),
            "invalid_market_phase_context",
        ),
    ],
)
def test_invalid_persisted_start_metadata_is_terminal_unable(
    isolated_db,
    context_snapshot,
    expected_reason,
) -> None:
    history_id = _add_history(
        isolated_db,
        context_snapshot=context_snapshot,
    )
    service = SkillOpinionOutcomeService(db_manager=isolated_db)

    item = service.run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d"],
    )["items"][0]

    assert item["eval_status"] == "unable"
    assert item["unable_reason"] == expected_reason
    assert service.run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d"],
    )["processed_keys"] == 0


def test_invalid_explicit_analysis_date_never_falls_back_to_created_at(
    isolated_db,
) -> None:
    history_id = _add_history(
        isolated_db,
        context_snapshot=json.dumps(
            {
                "enhanced_context": {"date": "not-a-date"},
                "market_phase_summary": {
                    "phase": "postmarket",
                    "market": "cn",
                    "effective_daily_bar_date": "2024-01-02",
                },
            }
        ),
    )

    item = SkillOpinionOutcomeService(
        db_manager=isolated_db
    ).run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d"],
    )["items"][0]

    assert item["eval_status"] == "unable"
    assert item["unable_reason"] == "invalid_analysis_date"
    assert item["analysis_date"] is None


def test_absent_analysis_date_falls_back_to_history_created_at(
    isolated_db,
) -> None:
    history_id = _add_history(
        isolated_db,
        context_snapshot=json.dumps(
            {
                "market_phase_summary": {
                    "phase": "postmarket",
                    "market": "cn",
                    "effective_daily_bar_date": "2024-01-02",
                }
            }
        ),
    )
    _seed_bars(
        isolated_db,
        code="600519",
        bars=[
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 105.0),
        ],
    )

    item = SkillOpinionOutcomeService(
        db_manager=isolated_db
    ).run_outcomes(
        analysis_history_id=history_id,
        horizons=["1d"],
    )["items"][0]

    assert item["eval_status"] == "evaluated"
    assert item["analysis_date"] == "2024-01-02"
    assert item["outcome"] == "hit"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"horizons": []},
        {"horizons": ["2d"]},
        {"skill_id": "   "},
        {"stock_code": ""},
        {"limit": 0},
        {"limit": 501},
        {"sample_id": True},
    ],
)
def test_invalid_filters_fail_before_materialization(
    isolated_db,
    kwargs,
) -> None:
    history_id = _add_history(isolated_db)

    with pytest.raises(ValueError):
        SkillOpinionOutcomeService(
            db_manager=isolated_db
        ).run_outcomes(
            analysis_history_id=history_id,
            **kwargs,
        )

    assert SkillOpinionSampleRepository(isolated_db).list_for_history(
        history_id
    ) == []


def test_repository_prefers_complete_equivalent_window(isolated_db) -> None:
    _seed_bars(
        isolated_db,
        code="600519.SH",
        bars=[(date(2024, 1, 2), 50.0)],
    )
    _seed_bars(
        isolated_db,
        code="600519",
        bars=[
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 105.0),
        ],
    )

    window = SkillOpinionOutcomeRepository(
        isolated_db
    ).resolve_daily_window(
        code_candidates=["600519.SH", "600519"],
        expected_start_date=date(2024, 1, 2),
        eval_window_days=1,
    )

    assert window is not None
    assert window.start_bar.code == "600519"
    assert window.start_bar.close == 100.0
    assert [bar.close for bar in window.forward_bars] == [105.0]


def test_outcome_rejects_sample_and_history_stock_mismatch(
    isolated_db,
) -> None:
    history_id = _add_history(
        isolated_db,
        code="AAPL",
        context_snapshot=_snapshot("2024-01-02", market="us"),
    )
    SkillOpinionSampleService(db_manager=isolated_db).persist(
        analysis_history_id=history_id,
        stock_code="MSFT",
        opinions=(
            SkillOpinionInput(
                skill_id="alpha",
                signal="buy",
                confidence=0.8,
            ),
        ),
    )
    sample_id = SkillOpinionSampleRepository(
        isolated_db
    ).list_for_history(history_id)[0].id
    _seed_bars(
        isolated_db,
        code="MSFT",
        bars=[
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 105.0),
        ],
    )

    item = SkillOpinionOutcomeService(
        db_manager=isolated_db
    ).run_outcomes(
        sample_id=sample_id,
        horizons=["1d"],
    )["items"][0]

    assert item["eval_status"] == "unable"
    assert item["unable_reason"] == "stock_code_mismatch"


def test_us_alias_and_canonical_history_code_share_one_identity(
    isolated_db,
) -> None:
    history_id = _add_history(
        isolated_db,
        code="AAPL",
        context_snapshot=_snapshot("2024-01-02", market="us"),
    )
    SkillOpinionSampleService(db_manager=isolated_db).persist(
        analysis_history_id=history_id,
        stock_code="AAPL.US",
        opinions=(
            SkillOpinionInput(
                skill_id="alpha",
                signal="buy",
                confidence=0.8,
            ),
        ),
    )
    sample_id = SkillOpinionSampleRepository(
        isolated_db
    ).list_for_history(history_id)[0].id
    _seed_bars(
        isolated_db,
        code="AAPL",
        bars=[
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 105.0),
        ],
    )

    item = SkillOpinionOutcomeService(
        db_manager=isolated_db
    ).run_outcomes(
        sample_id=sample_id,
        horizons=["1d"],
    )["items"][0]

    assert item["eval_status"] == "evaluated"
    assert item["outcome"] == "hit"
