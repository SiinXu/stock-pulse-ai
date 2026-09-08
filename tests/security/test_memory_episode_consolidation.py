# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persist-path counterexamples for #1119 Slice 3 per-symbol episode consolidation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from src.agent.soul import AGENT_SOUL_MARKER
from src.config import Config
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_evolution_event_repo import AgentEvolutionEventRepository
from src.repositories.base import RepositoryError
from src.schemas.agent_episode import AgentEpisodeCreate, AGENT_EPISODE_MAX_REMEDY
from src.schemas.memory_consolidate_policy import (
    EPISODE_CONSOLIDATE_EVENT_TYPE,
    EPISODE_CONSOLIDATE_MODE,
    ERROR_CONSOLIDATE_UNSCOPED,
    MemoryConsolidateError,
    build_episode_consolidate_summary,
    require_episode_consolidate_policy,
    resolve_episode_consolidate_policy,
)
from src.schemas.memory_forget_policy import EPISODE_FORGET_EVENT_TYPE
from src.schemas.memory_write_guard import MemoryWriteRejectedError
from src.services.agent_episode_service import AgentEpisodeService
from src.storage import DatabaseManager

NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=90)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-episode-consolidation.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _payload(episode_id: str, symbol: str, **overrides: object) -> dict:
    payload = {
        "episode_id": episode_id,
        "run_id": f"run-{episode_id}",
        "mode": "single",
        "symbol": symbol,
        "market": "us",
        "started_at": datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 5, 12, 10, 1, 0, tzinfo=timezone.utc),
        "success": True,
        "trajectory_summary": [{"tool": "get_quote", "success": True, "duration_ms": 12}],
        "lessons": [{"kind": "evidence_gap", "severity": "low", "remedy": "add source"}],
        "outcome_labels": {"user_feedback": "disagree_score"},
    }
    payload.update(overrides)
    return payload


def _append_at(
    db: DatabaseManager, when: datetime, episode_id: str, symbol: str, **overrides: object
):
    repo = AgentEpisodeRepository(db, clock=lambda: when)
    return repo.append(AgentEpisodeCreate.model_validate(_payload(episode_id, symbol, **overrides)))


def _ids(repo: AgentEpisodeRepository) -> set[str]:
    page = repo.query(limit=200)
    return {item.episode_id for item in page.items}


def _events(db, event_type: str) -> list:
    return AgentEvolutionEventRepository(db).list_events(
        occurred_from=NOW - timedelta(days=1),
        occurred_to=NOW + timedelta(days=1),
        event_type=event_type,
    )


def _enabled_service(repo: AgentEpisodeRepository) -> AgentEpisodeService:
    return AgentEpisodeService(
        repository=repo,
        config=SimpleNamespace(
            agent_episode_log_enabled=True,
            agent_episode_retention_days=90,
            agent_episode_max_rows=50000,
        ),
    )


def test_no_policy_preserves_all_rows_and_reports_remaining(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old-1", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old-2", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    result = repo.apply_consolidate(resolve_episode_consolidate_policy(symbol="AAPL"))
    assert result.applied is False
    assert result.deleted_count == 0
    assert result.remaining_count == 2
    assert result.audit_event_id is None
    assert result.summary_episode_id is None
    assert _ids(repo) == {"ep-old-1", "ep-old-2"}
    assert _events(isolated_db, EPISODE_CONSOLIDATE_EVENT_TYPE) == []


def test_batch_summarizes_two_or_more_and_leaves_other_symbols(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=2), "ep-aapl-1", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-aapl-2", "AAPL")
    _append_at(isolated_db, NOW, "ep-aapl-new", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-tsla-1", "TSLA")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-tsla-2", "TSLA")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    result = repo.apply_consolidate(
        require_episode_consolidate_policy(symbol="AAPL", cutoff=CUTOFF)
    )
    assert result.applied is True
    assert result.deleted_count == 2
    assert result.source_count == 2
    assert result.remaining_count == 2
    assert result.summary_episode_id
    assert result.audit_event_id
    remaining = _ids(repo)
    assert "ep-aapl-1" not in remaining
    assert "ep-aapl-2" not in remaining
    assert "ep-aapl-new" in remaining
    assert {"ep-tsla-1", "ep-tsla-2"}.issubset(remaining)
    summary = repo.get_by_episode_id(result.summary_episode_id)
    assert summary is not None
    assert summary.mode == EPISODE_CONSOLIDATE_MODE
    assert summary.symbol == "AAPL"
    assert summary.trajectory_summary == []
    assert summary.soul_version is None
    assert summary.soul_hash is None
    assert summary.outcome_labels is not None
    assert summary.outcome_labels.user_feedback is None
    assert summary.outcome_labels.extra["source_count"] == "2"
    events = _events(isolated_db, EPISODE_CONSOLIDATE_EVENT_TYPE)
    assert len(events) == 1
    event = events[0]
    assert event.event_id == result.audit_event_id
    assert event.actor == "system"
    assert event.before == {"count": 3, "symbol": "AAPL"}
    assert event.after["symbol"] == "AAPL"
    assert event.after["deleted_count"] == 2
    assert event.after["source_count"] == 2
    assert event.after["summary_episode_id"] == result.summary_episode_id
    assert "source_id_sha256" in event.after
    assert "trajectory" not in event.after
    assert "lessons" not in event.after
    assert "soul" not in event.after


def test_existing_summaries_are_excluded_from_source_set(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=3), "ep-old-1", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=2), "ep-old-2", "AAPL")
    _append_at(
        isolated_db,
        CUTOFF - timedelta(days=1),
        "ep-summary-old",
        "AAPL",
        mode=EPISODE_CONSOLIDATE_MODE,
        trajectory_summary=[],
        lessons=[{"kind": "prior_summary", "severity": "low", "remedy": "keep compact"}],
        outcome_labels={"extra": {"source_count": "4"}},
    )
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    result = repo.apply_consolidate(
        require_episode_consolidate_policy(symbol="AAPL", cutoff=CUTOFF)
    )
    assert result.deleted_count == 2
    assert result.source_count == 2
    remaining = _ids(repo)
    assert "ep-old-1" not in remaining
    assert "ep-old-2" not in remaining
    assert "ep-summary-old" in remaining
    assert result.summary_episode_id in remaining
    assert result.summary_episode_id != "ep-summary-old"
    old_summary = repo.get_by_episode_id("ep-summary-old")
    assert old_summary is not None
    assert old_summary.mode == EPISODE_CONSOLIDATE_MODE


def test_single_source_is_noop_then_forget_drops_leftover(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old", "AAPL")
    clock = {"now": NOW}
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: clock["now"])
    preview = repo.apply_consolidate(
        require_episode_consolidate_policy(symbol="AAPL", cutoff=CUTOFF)
    )
    assert preview.deleted_count == 0
    assert preview.summary_episode_id is None
    assert preview.audit_event_id is None
    assert _ids(repo) == {"ep-old"}
    service = _enabled_service(repo)
    stored = service.record_episode(_payload("ep-new", "AAPL"))
    assert stored is not None
    assert _ids(repo) == {"ep-new"}
    assert _events(isolated_db, EPISODE_CONSOLIDATE_EVENT_TYPE) == []
    forget_events = _events(isolated_db, EPISODE_FORGET_EVENT_TYPE)
    assert len(forget_events) == 1
    assert forget_events[0].after["deleted_count"] == 1


def test_dry_run_does_not_insert_delete_or_audit(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=2), "ep-old-1", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old-2", "AAPL")
    _append_at(isolated_db, NOW, "ep-new", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    preview = repo.apply_consolidate(
        require_episode_consolidate_policy(symbol="AAPL", cutoff=CUTOFF, dry_run=True)
    )
    assert preview.dry_run is True
    assert preview.deleted_count == 2
    assert preview.source_count == 2
    assert preview.remaining_count == 2
    assert preview.audit_event_id is None
    assert preview.summary_episode_id is None
    assert _ids(repo) == {"ep-old-1", "ep-old-2", "ep-new"}
    assert _events(isolated_db, EPISODE_CONSOLIDATE_EVENT_TYPE) == []


def test_unscoped_policy_never_writes(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old-1", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old-2", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    with pytest.raises(MemoryConsolidateError) as raised:
        repo.apply_consolidate(resolve_episode_consolidate_policy(cutoff=CUTOFF))
    assert raised.value.error_code == ERROR_CONSOLIDATE_UNSCOPED
    assert _ids(repo) == {"ep-old-1", "ep-old-2"}


def _forged_summary(kind: str):
    def _build(sources, *, symbol, episode_id=None, run_id=None):
        summary = build_episode_consolidate_summary(
            sources, symbol=symbol, episode_id=episode_id, run_id=run_id
        )
        assert summary.outcome_labels is not None
        if kind == "soul":
            summary.outcome_labels.user_feedback = AGENT_SOUL_MARKER
        elif kind == "oversize":
            summary.outcome_labels.user_feedback = "x" * (AGENT_EPISODE_MAX_REMEDY + 1)
        elif kind == "fact":
            summary.outcome_labels.extra["outcome"] = "miss"
        else:
            raise AssertionError(kind)
        return summary

    return _build


@pytest.mark.parametrize("kind", ["soul", "oversize", "fact"])
def test_rejected_summary_leaves_sources(isolated_db, monkeypatch, kind) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=2), "ep-old-1", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old-2", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    monkeypatch.setattr(
        "src.repositories.agent_episode_repo.build_episode_consolidate_summary",
        _forged_summary(kind),
    )
    with pytest.raises((RepositoryError, MemoryWriteRejectedError)):
        repo.apply_consolidate(
            require_episode_consolidate_policy(symbol="AAPL", cutoff=CUTOFF)
        )
    assert _ids(repo) == {"ep-old-1", "ep-old-2"}
    assert _events(isolated_db, EPISODE_CONSOLIDATE_EVENT_TYPE) == []


def test_audit_failure_rolls_back_summary_and_sources(isolated_db, monkeypatch) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=2), "ep-old-1", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old-2", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(
        "src.repositories.agent_episode_repo.insert_evolution_event_on_session",
        boom,
    )
    with pytest.raises(RepositoryError) as raised:
        repo.apply_consolidate(
            require_episode_consolidate_policy(symbol="AAPL", cutoff=CUTOFF)
        )
    assert raised.value.error_code == "agent_episode_consolidate_failed"
    assert _ids(repo) == {"ep-old-1", "ep-old-2"}
    assert _events(isolated_db, EPISODE_CONSOLIDATE_EVENT_TYPE) == []


def test_transaction_failure_rolls_back_rows(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=2), "ep-old-1", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old-2", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    decision = require_episode_consolidate_policy(symbol="AAPL", cutoff=CUTOFF)

    def fail_commit(self):
        raise RuntimeError("commit failed")

    original = Session.commit
    Session.commit = fail_commit
    try:
        with pytest.raises(RepositoryError) as raised:
            repo.apply_consolidate(decision)
        assert raised.value.error_code == "agent_episode_consolidate_failed"
    finally:
        Session.commit = original

    assert _ids(repo) == {"ep-old-1", "ep-old-2"}
    assert _events(isolated_db, EPISODE_CONSOLIDATE_EVENT_TYPE) == []


def test_append_path_consolidates_before_forget_and_is_fail_soft(
    isolated_db, monkeypatch
) -> None:
    clock = {"now": CUTOFF - timedelta(days=2)}
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: clock["now"])
    repo.append(AgentEpisodeCreate.model_validate(_payload("ep-aapl-1", "AAPL")))
    clock["now"] = CUTOFF - timedelta(days=1)
    repo.append(AgentEpisodeCreate.model_validate(_payload("ep-aapl-2", "AAPL")))
    repo.append(AgentEpisodeCreate.model_validate(_payload("ep-tsla-1", "TSLA")))
    clock["now"] = NOW
    service = _enabled_service(repo)
    stored = service.record_episode(_payload("ep-aapl-new", "AAPL"))
    assert stored is not None
    remaining = _ids(repo)
    assert "ep-aapl-1" not in remaining
    assert "ep-aapl-2" not in remaining
    assert "ep-aapl-new" in remaining
    assert "ep-tsla-1" in remaining
    summaries = [item for item in repo.query(symbol="AAPL", limit=20).items if item.mode == EPISODE_CONSOLIDATE_MODE]
    assert len(summaries) == 1
    assert summaries[0].trajectory_summary == []
    assert _events(isolated_db, EPISODE_CONSOLIDATE_EVENT_TYPE)
    assert not _events(isolated_db, EPISODE_FORGET_EVENT_TYPE)

    def boom(_decision):
        raise RuntimeError("consolidate unavailable")

    monkeypatch.setattr(repo, "apply_consolidate", boom)
    clock["now"] = CUTOFF - timedelta(days=1)
    repo.append(AgentEpisodeCreate.model_validate(_payload("ep-later-old-1", "MSFT")))
    repo.append(AgentEpisodeCreate.model_validate(_payload("ep-later-old-2", "MSFT")))
    clock["now"] = NOW
    recorded = service.record_episode(_payload("ep-later-new", "MSFT"))
    assert recorded is not None
    assert recorded.episode_id == "ep-later-new"
    assert "ep-later-new" in _ids(repo)
    assert "ep-later-old-1" not in _ids(repo)
    assert "ep-later-old-2" not in _ids(repo)


def test_explicit_consolidate_is_fail_loud(isolated_db) -> None:
    service = AgentEpisodeService(
        repository=AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    )
    with pytest.raises(MemoryConsolidateError) as raised:
        service.consolidate_symbol("  ", cutoff=CUTOFF)
    assert raised.value.error_code == ERROR_CONSOLIDATE_UNSCOPED
