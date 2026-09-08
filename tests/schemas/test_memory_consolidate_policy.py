# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Counterexample tests for the #1119 Slice 3 episode consolidate policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import inspect

import pytest

from src.agent.soul import AGENT_SOUL_MARKER
from src.schemas.agent_episode import AgentEpisodeCreate, EpisodeLesson
from src.schemas.memory_consolidate_policy import (
    EPISODE_CONSOLIDATE_MODE,
    ERROR_CONSOLIDATE_AMBIGUOUS_CUTOFF,
    ERROR_CONSOLIDATE_INVALID_CUTOFF,
    ERROR_CONSOLIDATE_INVALID_DRY_RUN,
    ERROR_CONSOLIDATE_INVALID_MAX_ROWS,
    ERROR_CONSOLIDATE_INVALID_NOW,
    ERROR_CONSOLIDATE_INVALID_RETENTION_DAYS,
    ERROR_CONSOLIDATE_INVALID_SOURCES,
    ERROR_CONSOLIDATE_INVALID_SYMBOL,
    ERROR_CONSOLIDATE_UNSCOPED,
    MemoryConsolidateError,
    build_episode_consolidate_summary,
    require_episode_consolidate_policy,
    require_episode_consolidate_summary,
    resolve_episode_consolidate_policy,
)
from src.schemas.memory_write_guard import MemoryWriteRejectedError
from src.schemas.memory_write_policy import require_episodic_write


NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)


def test_no_policy_does_not_apply() -> None:
    empty = resolve_episode_consolidate_policy()
    assert empty.apply is False
    assert empty.error_code is None
    symbol_only = resolve_episode_consolidate_policy(symbol="AAPL")
    assert symbol_only.apply is False
    assert symbol_only.symbol == "AAPL"
    assert symbol_only.error_code is None


def test_cutoff_without_symbol_is_unscoped() -> None:
    decision = resolve_episode_consolidate_policy(cutoff=NOW)
    assert decision.apply is False
    assert decision.error_code == ERROR_CONSOLIDATE_UNSCOPED
    with pytest.raises(MemoryConsolidateError) as raised:
        require_episode_consolidate_policy(symbol="  ", cutoff=NOW, max_rows=2)
    assert raised.value.error_code == ERROR_CONSOLIDATE_UNSCOPED


def test_valid_symbol_cutoff_and_count_apply() -> None:
    decision = require_episode_consolidate_policy(
        symbol=" AAPL ",
        cutoff=NOW,
        max_rows=2,
        dry_run=True,
    )
    assert decision.apply is True
    assert decision.symbol == "AAPL"
    assert decision.cutoff == datetime(2026, 8, 26, 12, 0, 0)
    assert decision.max_rows == 2
    assert decision.dry_run is True
    assert decision.error_code is None


def test_retention_days_uses_injected_clock() -> None:
    decision = require_episode_consolidate_policy(
        symbol="600519",
        retention_days=90,
        now=NOW,
    )
    assert decision.apply is True
    assert decision.cutoff == datetime(2026, 5, 28, 12, 0, 0)
    assert decision.cutoff == (NOW - timedelta(days=90)).astimezone(timezone.utc).replace(
        tzinfo=None
    )


def test_invalid_inputs_fail_closed() -> None:
    cases = [
        ({"symbol": 600519, "cutoff": NOW}, ERROR_CONSOLIDATE_INVALID_SYMBOL),
        ({"symbol": "AAPL", "cutoff": True}, ERROR_CONSOLIDATE_INVALID_CUTOFF),
        ({"symbol": "AAPL", "retention_days": 90}, ERROR_CONSOLIDATE_INVALID_NOW),
        (
            {"symbol": "AAPL", "retention_days": True, "now": NOW},
            ERROR_CONSOLIDATE_INVALID_RETENTION_DAYS,
        ),
        ({"symbol": "AAPL", "max_rows": True}, ERROR_CONSOLIDATE_INVALID_MAX_ROWS),
        ({"symbol": "AAPL", "max_rows": 0}, ERROR_CONSOLIDATE_INVALID_MAX_ROWS),
        (
            {"symbol": "AAPL", "cutoff": NOW, "retention_days": 90, "now": NOW},
            ERROR_CONSOLIDATE_AMBIGUOUS_CUTOFF,
        ),
        (
            {"symbol": "AAPL", "cutoff": NOW, "dry_run": "true"},
            ERROR_CONSOLIDATE_INVALID_DRY_RUN,
        ),
    ]
    for kwargs, code in cases:
        decision = resolve_episode_consolidate_policy(**kwargs)
        assert decision.apply is False, kwargs
        assert decision.error_code == code, kwargs


def _source(**overrides: object) -> SimpleNamespace:
    payload = {
        "started_at": datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 5, 1, 10, 1, 0, tzinfo=timezone.utc),
        "created_at": datetime(2026, 5, 1, 10, 2, 0, tzinfo=timezone.utc),
        "success": True,
        "market": "us",
        "soul_version": "v1",
        "soul_hash": "abcdef0123456789",
        "trajectory_summary": [{"tool": "get_quote", "success": True}],
        "lessons": [
            EpisodeLesson.model_validate(
                {"kind": "evidence_gap", "severity": "low", "remedy": "add source"}
            )
        ],
        "outcome_labels": SimpleNamespace(
            user_feedback="disagree_score",
            extra={"comment": "review later", "outcome": "miss"},
        ),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_summary_is_counts_and_lessons_only_and_is_admitted() -> None:
    first = _source()
    second = _source(
        success=False,
        started_at=datetime(2026, 5, 2, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 2, 10, 1, 0, tzinfo=timezone.utc),
        lessons=[
            EpisodeLesson.model_validate(
                {"kind": "timeout", "severity": "medium", "remedy": "retry later"}
            )
        ],
    )
    summary = require_episode_consolidate_summary(
        [first, second],
        symbol="AAPL",
        episode_id="epc-test-summary",
        run_id="cns-test-summary",
    )
    assert isinstance(summary, AgentEpisodeCreate)
    assert summary.mode == EPISODE_CONSOLIDATE_MODE
    assert summary.symbol == "AAPL"
    assert summary.market == "us"
    assert summary.soul_version is None
    assert summary.soul_hash is None
    assert summary.soul_charter is None
    assert summary.trajectory_summary == []
    assert summary.outcome_labels is not None
    assert summary.outcome_labels.user_feedback is None
    assert summary.outcome_labels.extra == {
        "source_count": "2",
        "success_count": "1",
        "failure_count": "1",
    }
    assert [lesson.kind for lesson in summary.lessons] == ["evidence_gap", "timeout"]
    admitted = require_episodic_write(summary)
    assert admitted.admitted is True
    assert admitted.persist is True


def test_summary_builder_rejects_blank_symbol_and_single_source() -> None:
    with pytest.raises(MemoryConsolidateError) as unscoped:
        build_episode_consolidate_summary([_source(), _source()], symbol="  ")
    assert unscoped.value.error_code == ERROR_CONSOLIDATE_UNSCOPED
    with pytest.raises(MemoryConsolidateError) as too_few:
        build_episode_consolidate_summary([_source()], symbol="AAPL")
    assert too_few.value.error_code == ERROR_CONSOLIDATE_INVALID_SOURCES


def test_forged_soul_summary_is_not_admitted() -> None:
    summary = build_episode_consolidate_summary(
        [_source(), _source(success=False)],
        symbol="AAPL",
        episode_id="epc-soul",
        run_id="cns-soul",
    )
    assert summary.outcome_labels is not None
    summary.outcome_labels.user_feedback = AGENT_SOUL_MARKER
    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        require_episodic_write(summary)


def test_resolver_stays_library_only() -> None:
    import src.schemas.memory_consolidate_policy as module

    source = inspect.getsource(module)
    assert "src.repositories" not in source
    assert "src.services" not in source
    assert "src.agent" not in source
    assert "def resolve_episode_consolidate_policy" in source
    assert "def build_episode_consolidate_summary" in source
