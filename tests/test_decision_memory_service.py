# -*- coding: utf-8 -*-
"""Tests for the historical decision memory & reflection service (Issue #118).

These exercise the real repositories, the authoritative outcome aggregation, and
the guardrail logic against an isolated SQLite database (no mocking of the query
or aggregation layers).
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

import pytest

from src.config import Config
from src.services.decision_memory_service import (
    DecisionReflection,
    DecisionMemoryService,
    format_decision_memory_prompt_section,
    render_decision_memory_report_section,
)
from src.services.decision_signal_outcome_service import (
    DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
    DecisionSignalOutcomeService,
)
from src.services.decision_signal_service import DecisionSignalService
from src.storage import (
    DatabaseManager,
    DecisionSignalOutcomeRecord,
    DecisionSignalRecord,
    StockDaily,
)


@pytest.fixture()
def isolated_db(tmp_path):
    old_database_path = os.environ.get("DATABASE_PATH")
    db_path = tmp_path / "decision_memory.db"
    os.environ["DATABASE_PATH"] = str(db_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        if old_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = old_database_path


_FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0)


def _canon(code: str, market: str = "cn") -> str:
    return DecisionSignalService.normalize_stock_code_for_signal(code, market=market)


def _insert_signal(
    db,
    *,
    code: str = "600519",
    market: str = "cn",
    action: str = "buy",
    status: str = "active",
    created_at: datetime,
) -> int:
    with db.session_scope() as session:
        row = DecisionSignalRecord(
            stock_code=_canon(code, market),
            stock_name="Test Co",
            market=market,
            source_type="analysis",
            source_report_id=None,
            trace_id=f"trace-{code}-{action}-{created_at.isoformat()}",
            market_phase="postmarket",
            trigger_source="api",
            action=action,
            action_label=action,
            horizon="3d",
            reason="unit test",
            data_quality_summary_json=json.dumps({"level": "good"}),
            metadata_json=json.dumps({"holding_state": "unknown"}),
            plan_quality="complete",
            status=status,
            created_at=created_at,
        )
        session.add(row)
        session.flush()
        return int(row.id)


def _insert_outcome(
    db,
    *,
    signal_id: int,
    action: str = "buy",
    market: str = "cn",
    horizon: str = "3d",
    outcome: str = "hit",
    stock_return_pct: float = 5.0,
    anchor_date: date = date(2024, 5, 1),
    eval_status: str = "completed",
) -> None:
    with db.session_scope() as session:
        session.add(
            DecisionSignalOutcomeRecord(
                signal_id=signal_id,
                horizon=horizon,
                engine_version=DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
                eval_status=eval_status,
                outcome=outcome if eval_status == "completed" else None,
                direction_expected="up" if action in {"buy", "add"} else "not_up",
                anchor_date=anchor_date,
                eval_window_days=3,
                stock_return_pct=stock_return_pct,
                action=action,
                market=market,
                holding_state="unknown",
            )
        )


def _seed_signal_with_outcome(
    db,
    *,
    code: str = "600519",
    action: str = "buy",
    outcome: str = "hit",
    stock_return_pct: float = 5.0,
    age_days: int = 30,
    anchor_date: date = date(2024, 5, 1),
) -> int:
    created = _FIXED_NOW - timedelta(days=age_days)
    signal_id = _insert_signal(db, code=code, action=action, created_at=created)
    _insert_outcome(
        db,
        signal_id=signal_id,
        action=action,
        outcome=outcome,
        stock_return_pct=stock_return_pct,
        anchor_date=anchor_date,
    )
    return signal_id


def _build(db, **kwargs) -> DecisionReflection | None:
    params = dict(
        stock_code="600519",
        market="cn",
        lookback=5,
        min_age_days=3,
        min_samples=5,
        now=_FIXED_NOW,
    )
    params.update(kwargs)
    return DecisionMemoryService(
        signal_repo=None, outcome_repo=None, outcome_service=None
    ).build_reflection(**params)


# --------------------------------------------------------------------------
# No-history / disabled: zero-injection paths.
# --------------------------------------------------------------------------


def test_no_signals_returns_none(isolated_db) -> None:
    assert _build(isolated_db) is None


def test_signals_without_completed_outcomes_return_none(isolated_db) -> None:
    signal_id = _insert_signal(
        isolated_db, created_at=_FIXED_NOW - timedelta(days=30)
    )
    _insert_outcome(isolated_db, signal_id=signal_id, eval_status="unable")
    assert _build(isolated_db) is None


def test_lookback_zero_returns_none(isolated_db) -> None:
    _seed_signal_with_outcome(isolated_db)
    assert _build(isolated_db, lookback=0) is None


# --------------------------------------------------------------------------
# Guardrail 1: minimum sample threshold gates the hit-rate.
# --------------------------------------------------------------------------


def test_below_min_samples_suppresses_rate_but_lists_calls(isolated_db) -> None:
    _seed_signal_with_outcome(isolated_db, outcome="hit", stock_return_pct=6.0)
    _seed_signal_with_outcome(isolated_db, outcome="miss", stock_return_pct=-6.0)

    reflection = _build(isolated_db, min_samples=5)

    assert reflection is not None
    assert reflection.same_stock_decided == 2
    # Rate suppressed as noise below the threshold ...
    assert reflection.same_stock_hit_rate_pct is None
    # ... but the individual calls (facts) are still surfaced.
    assert len(reflection.recent_calls) == 2


def test_at_min_samples_surfaces_hit_rate(isolated_db) -> None:
    for _ in range(3):
        _seed_signal_with_outcome(isolated_db, outcome="hit", stock_return_pct=5.0)
    for _ in range(2):
        _seed_signal_with_outcome(isolated_db, outcome="miss", stock_return_pct=-5.0)

    reflection = _build(isolated_db, min_samples=5)

    assert reflection is not None
    assert reflection.same_stock_decided == 5
    # 3 hit / (3 hit + 2 miss) = 60% via the authoritative aggregation.
    assert reflection.same_stock_hit_rate_pct == 60.0


def test_neutral_outcomes_excluded_from_rate_denominator(isolated_db) -> None:
    for _ in range(5):
        _seed_signal_with_outcome(isolated_db, outcome="hit", stock_return_pct=5.0)
    _seed_signal_with_outcome(isolated_db, outcome="neutral", stock_return_pct=0.1)

    reflection = _build(isolated_db, lookback=10, min_samples=5)

    assert reflection is not None
    assert reflection.same_stock_neutrals == 1
    # Neutral does not dilute the hit rate (denominator = hit + miss).
    assert reflection.same_stock_hit_rate_pct == 100.0


# --------------------------------------------------------------------------
# Guardrail 2: statistics carry the window they were drawn from.
# --------------------------------------------------------------------------


def test_window_annotation_reflects_outcome_dates(isolated_db) -> None:
    _seed_signal_with_outcome(isolated_db, anchor_date=date(2024, 4, 1))
    _seed_signal_with_outcome(isolated_db, anchor_date=date(2024, 5, 15))

    reflection = _build(isolated_db, min_samples=1)

    assert reflection is not None
    assert reflection.window_start == date(2024, 4, 1)
    assert reflection.window_end == date(2024, 5, 15)
    prompt = format_decision_memory_prompt_section(reflection, report_language="en")
    assert "2024-04-01" in prompt and "2024-05-15" in prompt


# --------------------------------------------------------------------------
# Guardrail 3: reflection never carries or implies a direction override.
# --------------------------------------------------------------------------


def test_reflection_has_no_directional_recommendation_field(isolated_db) -> None:
    reflection = _build_single(isolated_db)
    for forbidden in ("recommended_action", "direction", "suggested_action", "action"):
        assert not hasattr(reflection, forbidden)


def test_prompt_states_calibration_only_and_no_override(isolated_db) -> None:
    reflection = _build_single(isolated_db)

    zh = format_decision_memory_prompt_section(reflection, report_language="zh")
    en = format_decision_memory_prompt_section(reflection, report_language="en")

    assert "不得据此翻转或否决" in zh
    assert "never to flip or override" in en
    # It must not instruct a directional change.
    for directive in ("改为卖出", "change your recommendation", "flip to sell"):
        assert directive not in zh and directive not in en


def _build_single(db) -> DecisionReflection:
    _seed_signal_with_outcome(db, outcome="hit", stock_return_pct=5.0)
    reflection = _build(db, min_samples=1)
    assert reflection is not None
    return reflection


# --------------------------------------------------------------------------
# Pattern-level calibration reuses the authoritative per-action stats.
# --------------------------------------------------------------------------


def test_pattern_calibration_uses_global_action_hit_rate(isolated_db) -> None:
    # 6 global "buy" outcomes: 4 hit / 2 miss = 66.67%.
    for _ in range(4):
        _seed_signal_with_outcome(isolated_db, action="buy", outcome="hit")
    for _ in range(2):
        _seed_signal_with_outcome(isolated_db, action="buy", outcome="miss", stock_return_pct=-5.0)

    reflection = _build(isolated_db, lookback=10, min_samples=5)

    assert reflection is not None
    buckets = {b.action: b for b in reflection.pattern_calibration}
    assert "buy" in buckets
    assert buckets["buy"].sample_size == 6
    assert buckets["buy"].hit_rate_pct == pytest.approx(66.67, abs=0.01)


def test_pattern_calibration_drops_buckets_below_threshold(isolated_db) -> None:
    _seed_signal_with_outcome(isolated_db, action="buy", outcome="hit")
    _seed_signal_with_outcome(isolated_db, action="buy", outcome="miss", stock_return_pct=-5.0)

    reflection = _build(isolated_db, min_samples=5)

    assert reflection is not None
    # Only 2 decided "buy" samples globally: below threshold, so no pattern bucket.
    assert reflection.pattern_calibration == tuple()


# --------------------------------------------------------------------------
# Minimum age: only reflect on signals old enough to have settled outcomes.
# --------------------------------------------------------------------------


def test_min_age_excludes_recent_signals(isolated_db) -> None:
    # Signal created 1 day ago; min_age_days=3 means it is too fresh.
    _seed_signal_with_outcome(isolated_db, age_days=1)
    assert _build(isolated_db, min_age_days=3, min_samples=1) is None
    # Same signal is eligible when the age gate is relaxed.
    assert _build(isolated_db, min_age_days=0, min_samples=1) is not None


# --------------------------------------------------------------------------
# End-to-end: real outcome classification then reflection.
# --------------------------------------------------------------------------


def test_end_to_end_run_outcomes_then_reflection(isolated_db) -> None:
    created = _FIXED_NOW - timedelta(days=30)
    signal_id = _insert_signal(isolated_db, action="buy", created_at=created)
    with isolated_db.session_scope() as session:
        anchor = date(2024, 5, 1)
        session.add(StockDaily(code=_canon("600519"), date=anchor, open=100, high=100, low=100, close=100))
        for index, close in enumerate([103, 104, 105, 106, 107, 108, 109, 110, 111, 112], start=1):
            session.add(
                StockDaily(
                    code=_canon("600519"),
                    date=date(2024, 5, 1 + index),
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                )
            )
    DecisionSignalOutcomeService(db_manager=isolated_db).run_outcomes(
        signal_id=signal_id, horizons=["1d", "3d"]
    )

    reflection = _build(isolated_db, min_samples=1)

    assert reflection is not None
    assert reflection.same_stock_hits >= 1
    assert any(call.outcome == "hit" for call in reflection.recent_calls)


# --------------------------------------------------------------------------
# Rendering.
# --------------------------------------------------------------------------


def test_render_none_is_empty() -> None:
    assert format_decision_memory_prompt_section(None) == ""
    assert render_decision_memory_report_section(None) == ""


def test_render_report_section_is_bilingual(isolated_db) -> None:
    reflection = _build_single(isolated_db)

    zh = render_decision_memory_report_section(reflection, report_language="zh")
    en = render_decision_memory_report_section(reflection, report_language="en")

    assert "历史决策复盘" in zh
    assert "Historical Decision Reflection" in en
    assert "不改变上方结论" in zh
    assert "does not change the call above" in en


