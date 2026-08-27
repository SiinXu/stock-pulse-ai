# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persist-path counterexamples for #1119 Slice 2 per-symbol episode forgetting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from src.config import Config
from src.repositories.agent_episode_repo import (
    AgentEpisodeRepository,
    forget_id_in_chunk_size,
)
from src.repositories.agent_episode_tables import agent_episodes_table
from src.repositories.agent_evolution_event_repo import AgentEvolutionEventRepository
from src.repositories.base import RepositoryError
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.memory_forget_policy import (
    EPISODE_FORGET_EVENT_TYPE,
    ERROR_FORGET_UNSCOPED,
    MemoryForgetError,
    require_episode_forget_policy,
    resolve_episode_forget_policy,
)
from src.services.agent_episode_service import AgentEpisodeService
from src.storage import DatabaseManager

NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=90)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-episode-forgetting.db"
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
        "started_at": datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 8, 12, 10, 1, 0, tzinfo=timezone.utc),
        "success": True,
        "trajectory_summary": [{"tool": "get_quote", "success": True, "duration_ms": 12}],
        "lessons": [{"kind": "evidence_gap", "severity": "low", "remedy": "add source"}],
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


def _forget_events(db) -> list:
    events = AgentEvolutionEventRepository(db).list_events(
        occurred_from=NOW - timedelta(days=1),
        occurred_to=NOW + timedelta(days=1),
        event_type=EPISODE_FORGET_EVENT_TYPE,
    )
    return events


def test_no_policy_preserves_all_rows_and_reports_remaining(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old", "AAPL")
    _append_at(isolated_db, NOW, "ep-new", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    result = repo.apply_forget(resolve_episode_forget_policy(symbol="AAPL"))
    assert result.applied is False
    assert result.deleted_count == 0
    assert result.remaining_count == 2
    assert result.audit_event_id is None
    assert _ids(repo) == {"ep-old", "ep-new"}
    assert _forget_events(isolated_db) == []


def test_empty_store_is_idempotent_zero(isolated_db) -> None:
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    decision = require_episode_forget_policy(symbol="AAPL", cutoff=CUTOFF, max_rows=2)
    first = repo.apply_forget(decision)
    second = repo.apply_forget(decision)
    assert first.applied is True
    assert first.deleted_count == 0
    assert first.remaining_count == 0
    assert second.deleted_count == 0
    assert second.remaining_count == 0
    assert _ids(repo) == set()


def test_exact_cutoff_deletes_older_and_keeps_equal(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(microseconds=1), "ep-older", "AAPL")
    _append_at(isolated_db, CUTOFF, "ep-exact", "AAPL")
    _append_at(isolated_db, CUTOFF + timedelta(microseconds=1), "ep-newer", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    result = repo.apply_forget(require_episode_forget_policy(symbol="AAPL", cutoff=CUTOFF))
    assert result.deleted_count == 1
    assert result.remaining_count == 2
    assert _ids(repo) == {"ep-exact", "ep-newer"}
    again = repo.apply_forget(require_episode_forget_policy(symbol="AAPL", cutoff=CUTOFF))
    assert again.deleted_count == 0
    assert again.remaining_count == 2
    assert _ids(repo) == {"ep-exact", "ep-newer"}


def test_cross_symbol_isolation_for_ttl_and_cap(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-aapl-old", "AAPL")
    _append_at(isolated_db, NOW - timedelta(days=3), "ep-aapl-keep-1", "AAPL")
    _append_at(isolated_db, NOW - timedelta(days=2), "ep-aapl-keep-2", "AAPL")
    _append_at(isolated_db, NOW - timedelta(days=1), "ep-aapl-keep-3", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-tsla-old", "TSLA")
    _append_at(isolated_db, NOW - timedelta(days=3), "ep-tsla-1", "TSLA")
    _append_at(isolated_db, NOW, "ep-tsla-2", "TSLA")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    result = repo.apply_forget(
        require_episode_forget_policy(symbol="AAPL", cutoff=CUTOFF, max_rows=2)
    )
    assert result.symbol == "AAPL"
    assert result.deleted_count == 2
    assert result.remaining_count == 2
    assert _ids(repo) == {
        "ep-aapl-keep-2",
        "ep-aapl-keep-3",
        "ep-tsla-old",
        "ep-tsla-1",
        "ep-tsla-2",
    }


def test_exact_count_boundary_keeps_newest_on_timestamp_tie(isolated_db) -> None:
    tied = NOW - timedelta(days=1)
    first = _append_at(isolated_db, tied, "ep-tie-1", "AAPL")
    second = _append_at(isolated_db, tied, "ep-tie-2", "AAPL")
    third = _append_at(isolated_db, tied, "ep-tie-3", "AAPL")
    assert first.id < second.id < third.id
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    exact = repo.apply_forget(require_episode_forget_policy(symbol="AAPL", max_rows=3))
    assert exact.deleted_count == 0
    overflow = repo.apply_forget(require_episode_forget_policy(symbol="AAPL", max_rows=2))
    assert overflow.deleted_count == 1
    assert _ids(repo) == {"ep-tie-2", "ep-tie-3"}


def test_dry_run_does_not_delete(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old", "AAPL")
    _append_at(isolated_db, NOW, "ep-new", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    preview = repo.apply_forget(
        require_episode_forget_policy(symbol="AAPL", cutoff=CUTOFF, dry_run=True)
    )
    assert preview.dry_run is True
    assert preview.deleted_count == 1
    assert preview.remaining_count == 1
    assert preview.audit_event_id is None
    assert _ids(repo) == {"ep-old", "ep-new"}
    assert _forget_events(isolated_db) == []


def test_transaction_failure_rolls_back_rows(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old", "AAPL")
    _append_at(isolated_db, NOW, "ep-new", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    decision = require_episode_forget_policy(symbol="AAPL", cutoff=CUTOFF)

    def fail_commit(self):
        raise RuntimeError("commit failed")

    original = Session.commit
    Session.commit = fail_commit
    try:
        with pytest.raises(RepositoryError) as raised:
            repo.apply_forget(decision)
        assert raised.value.error_code == "agent_episode_forget_failed"
    finally:
        Session.commit = original

    assert _ids(repo) == {"ep-old", "ep-new"}
    assert _forget_events(isolated_db) == []


def test_unscoped_policy_never_deletes(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    with pytest.raises(MemoryForgetError) as raised:
        repo.apply_forget(resolve_episode_forget_policy(cutoff=CUTOFF))
    assert raised.value.error_code == ERROR_FORGET_UNSCOPED
    assert _ids(repo) == {"ep-old"}


def test_append_path_forgets_only_the_written_symbol(isolated_db) -> None:
    clock = {"now": CUTOFF - timedelta(days=1)}
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: clock["now"])
    repo.append(AgentEpisodeCreate.model_validate(_payload("ep-aapl-old", "AAPL")))
    repo.append(AgentEpisodeCreate.model_validate(_payload("ep-tsla-old", "TSLA")))
    clock["now"] = NOW
    service = AgentEpisodeService(
        repository=repo,
        config=SimpleNamespace(
            agent_episode_log_enabled=True,
            agent_episode_retention_days=90,
            agent_episode_max_rows=50000,
        ),
    )
    stored = service.record_episode(_payload("ep-aapl-new", "AAPL"))
    assert stored is not None
    assert stored.episode_id == "ep-aapl-new"
    assert _ids(repo) == {"ep-aapl-new", "ep-tsla-old"}
    events = _forget_events(isolated_db)
    assert len(events) == 1
    assert events[0].after["symbol"] == "AAPL"


def test_append_without_symbol_does_not_purge(isolated_db) -> None:
    clock = {"now": CUTOFF - timedelta(days=1)}
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: clock["now"])
    repo.append(AgentEpisodeCreate.model_validate(_payload("ep-aapl-old", "AAPL")))
    clock["now"] = NOW
    service = AgentEpisodeService(
        repository=repo,
        config=SimpleNamespace(
            agent_episode_log_enabled=True,
            agent_episode_retention_days=90,
            agent_episode_max_rows=2,
        ),
    )
    payload = _payload("ep-none", "AAPL")
    payload["symbol"] = None
    payload["market"] = None
    stored = service.record_episode(payload)
    assert stored is not None
    assert stored.symbol is None
    assert _ids(repo) == {"ep-aapl-old", "ep-none"}


def test_service_forget_is_observable_and_idempotent(isolated_db) -> None:
    clock = {"now": CUTOFF - timedelta(days=1)}
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: clock["now"])
    repo.append(AgentEpisodeCreate.model_validate(_payload("ep-old", "AAPL")))
    clock["now"] = NOW
    service = AgentEpisodeService(repository=repo)
    first = service.forget_symbol("AAPL", cutoff=CUTOFF)
    second = service.forget_symbol("AAPL", cutoff=CUTOFF)
    assert first.deleted_count == 1
    assert first.remaining_count == 0
    assert second.deleted_count == 0
    assert _ids(repo) == set()


def test_append_forget_failure_does_not_mask_append(isolated_db, monkeypatch) -> None:
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    stored = repo.append(AgentEpisodeCreate.model_validate(_payload("ep-new", "AAPL")))
    service = AgentEpisodeService(
        repository=repo,
        config=SimpleNamespace(
            agent_episode_log_enabled=True,
            agent_episode_retention_days=90,
            agent_episode_max_rows=50000,
        ),
    )

    def boom(_decision):
        raise RuntimeError("forget unavailable")

    monkeypatch.setattr(repo, "apply_forget", boom)
    recorded = service.record_episode(_payload("ep-later", "AAPL"))
    assert recorded is not None
    assert recorded.episode_id == "ep-later"
    assert repo.get_by_episode_id(stored.episode_id) is not None


def test_forget_writes_metadata_only_evolution_event(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old", "AAPL")
    _append_at(isolated_db, NOW, "ep-new", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    result = repo.apply_forget(require_episode_forget_policy(symbol="AAPL", cutoff=CUTOFF))
    assert result.deleted_count == 1
    assert result.audit_event_id
    events = _forget_events(isolated_db)
    assert len(events) == 1
    event = events[0]
    assert event.event_id == result.audit_event_id
    assert event.actor == "system"
    assert event.before == {"count": 2, "symbol": "AAPL"}
    assert event.after["count"] == 1
    assert event.after["deleted_count"] == 1
    assert event.after["symbol"] == "AAPL"
    assert "deleted_id_sha256" in event.after
    assert "trajectory" not in event.before
    assert "lessons" not in event.before
    assert "trajectory" not in event.after
    assert "lessons" not in event.after
    assert "outcome_labels" not in event.after


def test_audit_failure_rolls_back_delete(isolated_db, monkeypatch) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-old", "AAPL")
    _append_at(isolated_db, NOW, "ep-new", "AAPL")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(
        "src.repositories.agent_episode_repo.insert_evolution_event_on_session",
        boom,
    )
    with pytest.raises(RepositoryError) as raised:
        repo.apply_forget(require_episode_forget_policy(symbol="AAPL", cutoff=CUTOFF))
    assert raised.value.error_code == "agent_episode_forget_failed"
    assert _ids(repo) == {"ep-old", "ep-new"}
    assert _forget_events(isolated_db) == []


def test_legacy_unscoped_retention_and_capacity_fail_closed(isolated_db) -> None:
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-aapl", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-tsla", "TSLA")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    with pytest.raises(MemoryForgetError) as retention_error:
        repo.apply_retention(cutoff=CUTOFF)
    assert retention_error.value.error_code == ERROR_FORGET_UNSCOPED
    with pytest.raises(MemoryForgetError) as capacity_error:
        repo.apply_capacity(max_rows=1)
    assert capacity_error.value.error_code == ERROR_FORGET_UNSCOPED
    assert _ids(repo) == {"ep-aapl", "ep-tsla"}
    scoped = repo.apply_retention(cutoff=CUTOFF, symbol="AAPL")
    assert scoped == 1
    assert _ids(repo) == {"ep-tsla"}


def test_inactive_no_policy_counts_table_without_deleting(isolated_db) -> None:
    _append_at(isolated_db, NOW, "ep-aapl", "AAPL")
    _append_at(isolated_db, NOW, "ep-tsla", "TSLA")
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    result = repo.apply_forget(resolve_episode_forget_policy())
    assert result.applied is False
    assert result.deleted_count == 0
    assert result.remaining_count == 2
    assert _ids(repo) == {"ep-aapl", "ep-tsla"}


def test_forget_chunks_id_in_lists_in_one_transaction(isolated_db) -> None:
    repo = AgentEpisodeRepository(
        isolated_db, clock=lambda: NOW, forget_id_chunk_size=2
    )
    for index in range(5):
        _append_at(
            isolated_db,
            CUTOFF - timedelta(days=1),
            f"ep-chunk-{index}",
            "AAPL",
        )
    _append_at(isolated_db, CUTOFF, "ep-chunk-exact", "AAPL")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-chunk-other", "TSLA")
    result = repo.apply_forget(require_episode_forget_policy(symbol="AAPL", cutoff=CUTOFF))
    assert result.deleted_count == 5
    assert result.remaining_count == 1
    assert result.audit_event_id
    events = _forget_events(isolated_db)
    assert len(events) == 1
    assert events[0].after["deleted_count"] == 5
    assert events[0].before["count"] == 6
    assert _ids(repo) == {"ep-chunk-exact", "ep-chunk-other"}


def test_forget_deletes_more_ids_than_sqlite_in_bind_limit(isolated_db) -> None:
    repo = AgentEpisodeRepository(isolated_db, clock=lambda: NOW)
    with isolated_db.get_session() as session:
        chunk = forget_id_in_chunk_size(session)
    expired_count = chunk + 2
    created = _as_naive(CUTOFF - timedelta(days=1))
    rows = [
        {
            "schema_version": "agent-episode-v1",
            "episode_id": f"ep-bulk-{index}",
            "run_id": f"run-bulk-{index}",
            "mode": "single",
            "symbol": "BULK",
            "trajectory_summary_json": "[]",
            "lessons_json": "[]",
            "created_at": created,
        }
        for index in range(expired_count)
    ]
    with isolated_db.get_session() as session:
        session.execute(agent_episodes_table.insert(), rows)
        session.commit()
    _append_at(isolated_db, CUTOFF, "ep-bulk-exact", "BULK")
    _append_at(isolated_db, CUTOFF - timedelta(days=1), "ep-other-old", "OTHER")
    result = repo.apply_forget(require_episode_forget_policy(symbol="BULK", cutoff=CUTOFF))
    assert result.deleted_count == expired_count
    assert result.remaining_count == 1
    assert result.audit_event_id
    events = _forget_events(isolated_db)
    assert len(events) == 1
    assert events[0].after["deleted_count"] == expired_count
    assert events[0].before["count"] == expired_count + 1
    assert repo.get_by_episode_id("ep-bulk-exact") is not None
    assert repo.get_by_episode_id("ep-other-old") is not None
    assert repo.query(symbol="BULK", limit=10).total == 1
    assert repo.query(symbol="OTHER", limit=10).total == 1


def _as_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
