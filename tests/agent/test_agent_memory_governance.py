"""Lifecycle tests: consent, retention, delete/clear, access audit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.agent.memory_governance import LayeredMemoryPolicy, PrincipalMemoryLifecycle
from src.agent.memory_layers import MemoryObservation

_BASE = datetime(2026, 8, 1, tzinfo=timezone.utc)
AS_OF = "2026-08-09T00:00:00Z"


def _instant(offset_minutes: int) -> str:
    return (_BASE + timedelta(minutes=offset_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _obs(index: int, *, principal: str = "alice", correct=None,
         expires_at=None, signal: str = "buy") -> MemoryObservation:
    evaluated = correct is not None
    return MemoryObservation(
        principal_id=principal,
        analysis_history_id=index,
        stock_code="600519",
        observed_at=_instant(index),
        expires_at=expires_at,
        signal=signal,
        sentiment_score=60,
        price_at_analysis=100.0,
        outcome_id=1000 + index if evaluated else None,
        outcome_horizon_days=5 if evaluated else None,
        evaluated_at="2026-08-08T00:00:00Z" if evaluated else None,
        was_correct=correct,
    )


def _lifecycle(**policy_kwargs) -> PrincipalMemoryLifecycle:
    return PrincipalMemoryLifecycle(policy=LayeredMemoryPolicy(**policy_kwargs))


def test_defaults_minimize_collection() -> None:
    policy = LayeredMemoryPolicy()
    assert policy.collection_enabled is False
    assert policy.vector_enabled is False
    assert policy.retention_days == 90
    assert policy.audit_enabled is True


def test_from_config_reads_shared_config_fields() -> None:
    class _Cfg:
        layered_memory_collection_enabled = True
        layered_memory_retention_days = 30
        layered_memory_vector_enabled = True
        layered_memory_max_records_per_principal = 50
        layered_memory_audit_enabled = False

    policy = LayeredMemoryPolicy.from_config(_Cfg())
    assert policy.collection_enabled is True
    assert policy.retention_days == 30
    assert policy.vector_enabled is True
    assert policy.max_records_per_principal == 50
    assert policy.audit_enabled is False


def test_collect_requires_global_switch_and_consent() -> None:
    life = _lifecycle(collection_enabled=False)
    life.grant_consent("alice", at=AS_OF)
    with pytest.raises(PermissionError, match="disabled"):
        life.put(_obs(1), now=AS_OF)

    life = _lifecycle(collection_enabled=True)
    with pytest.raises(PermissionError, match="consented"):
        life.put(_obs(1), now=AS_OF)

    life.grant_consent("alice", at=AS_OF)
    stored = life.put(_obs(1), now=AS_OF)
    assert stored.expires_at is not None
    assert life.list_records("alice", as_of=AS_OF)[0].analysis_history_id == 1


def test_retention_auto_expires_records() -> None:
    life = _lifecycle(collection_enabled=True, retention_days=3)
    life.grant_consent("alice", at="2026-08-01T00:00:00Z")
    # observed_at for index=1 is 2026-08-01T00:01:00Z; now must not precede it.
    life.put(_obs(1), now="2026-08-01T00:01:05Z")
    assert life.expire_due(now="2026-08-04T00:01:00Z") == 1
    assert life.list_records("alice", as_of="2026-08-04T00:01:00Z") == []
    actions = [e.action for e in life.auditor.list_for_principal("alice")]
    assert "expire" in actions
    assert "collect" in actions


def test_delete_and_clear_are_principal_scoped() -> None:
    life = _lifecycle(collection_enabled=True)
    life.grant_consent("alice", at=AS_OF)
    life.grant_consent("bob", at=AS_OF)
    life.put(_obs(1, principal="alice"), now=AS_OF)
    life.put(_obs(2, principal="bob"), now=AS_OF)
    assert life.delete("alice", 1, at=AS_OF) is True
    assert life.list_records("alice", as_of=AS_OF) == []
    assert len(life.list_records("bob", as_of=AS_OF)) == 1
    assert life.clear("bob", at=AS_OF) == 1
    assert life.list_records("bob", as_of=AS_OF) == []


def test_revoke_consent_clears_data_by_default() -> None:
    life = _lifecycle(collection_enabled=True)
    life.grant_consent("alice", at=AS_OF)
    life.put(_obs(1), now=AS_OF)
    assert life.revoke_consent("alice", at=AS_OF) == 1
    assert life.has_consent("alice") is False
    with pytest.raises(PermissionError):
        life.list_records("alice", as_of=AS_OF)


def test_project_and_export_require_consent_and_are_audited() -> None:
    life = _lifecycle(collection_enabled=True)
    with pytest.raises(PermissionError):
        life.project("alice", stock_code="600519", as_of=AS_OF)
    life.grant_consent("alice", at=AS_OF)
    for index in range(1, 4):
        life.put(_obs(index, correct=True), now=AS_OF)
    bundle = life.project("alice", stock_code="600519", as_of=AS_OF, query="buy")
    assert len(bundle.outcome_patterns) == 1
    rendered = life.export_isolated_prompt_block("alice", stock_code="600519", as_of=AS_OF)
    assert "BEGIN_UNTRUSTED_MEMORY_DATA" in rendered
    actions = [e.action for e in life.auditor.list_for_principal("alice")]
    assert "project" in actions and "export" in actions


def test_cross_principal_put_is_impossible_via_observation_owner() -> None:
    life = _lifecycle(collection_enabled=True)
    life.grant_consent("alice", at=AS_OF)
    life.grant_consent("bob", at=AS_OF)
    life.put(_obs(1, principal="bob"), now=AS_OF)
    assert life.list_records("alice", as_of=AS_OF) == []
    assert len(life.list_records("bob", as_of=AS_OF)) == 1
