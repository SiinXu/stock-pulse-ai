# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Default-off, fail-soft layered memory collection tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent.memory_governance import LayeredMemoryPolicy, PrincipalMemoryLifecycle
from src.config import Config
from src.repositories.layered_memory_repo import (
    DurableLayeredMemoryStore,
    LayeredMemoryRepository,
)
from src.services.layered_memory_collection_service import (
    LAYERED_MEMORY_OPERATOR_PRINCIPAL,
    LayeredMemoryCollectionService,
    is_layered_memory_collection_enabled,
    try_collect_layered_memory_observation,
)
from src.storage import DatabaseManager


AS_OF = "2026-08-09T00:00:00Z"


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "layered-collect.db"))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _result(**overrides):
    payload = {
        "code": "600519",
        "decision_type": "buy",
        "sentiment_score": 66,
        "current_price": 1800.0,
        "operation_advice": "do not copy this prose",
        "analysis_summary": "secret-looking summary",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_flag_default_off_is_strict_boolean(isolated_db) -> None:
    config = Config.get_instance()
    assert config.layered_memory_collection_enabled is False
    assert is_layered_memory_collection_enabled(config) is False
    assert is_layered_memory_collection_enabled(
        SimpleNamespace(layered_memory_collection_enabled="true")
    ) is False
    assert is_layered_memory_collection_enabled(
        SimpleNamespace(layered_memory_collection_enabled=True)
    ) is True


def test_disabled_helper_does_not_initialize_repository() -> None:
    with patch(
        "src.services.layered_memory_collection_service.LayeredMemoryRepository",
        side_effect=AssertionError("repository must stay lazy"),
    ):
        assert try_collect_layered_memory_observation(
            result=_result(),
            analysis_history_id=1,
            config=SimpleNamespace(layered_memory_collection_enabled=False),
        ) is None


def test_enabled_without_consent_is_noop(isolated_db) -> None:
    cfg = SimpleNamespace(
        layered_memory_collection_enabled=True,
        layered_memory_retention_days=90,
        layered_memory_vector_enabled=False,
        layered_memory_max_records_per_principal=200,
        layered_memory_audit_enabled=True,
    )
    stored = try_collect_layered_memory_observation(
        result=_result(),
        analysis_history_id=11,
        config=cfg,
        now=AS_OF,
    )
    assert stored is None
    assert LayeredMemoryRepository().list_records("local_admin") == []


def test_enabled_collects_after_consent_and_skips_prose(isolated_db) -> None:
    cfg = SimpleNamespace(
        layered_memory_collection_enabled=True,
        layered_memory_retention_days=90,
        layered_memory_vector_enabled=False,
        layered_memory_max_records_per_principal=200,
        layered_memory_audit_enabled=True,
    )
    repo = LayeredMemoryRepository()
    life = PrincipalMemoryLifecycle(
        policy=LayeredMemoryPolicy.from_config(cfg),
        store=DurableLayeredMemoryStore(repo),
    )
    life.grant_consent(LAYERED_MEMORY_OPERATOR_PRINCIPAL, at=AS_OF)
    stored = LayeredMemoryCollectionService(repository=repo, config=cfg).collect_from_analysis_result(
        result=_result(),
        analysis_history_id=12,
        config=cfg,
        now=AS_OF,
    )
    assert stored is not None
    assert stored.analysis_history_id == 12
    assert stored.signal == "buy"
    assert stored.price_at_analysis == 1800.0
    assert stored.provenance_source == "system_resolve"
    dumped = stored.__dict__
    assert "do not copy this prose" not in str(dumped)
    assert "secret-looking summary" not in str(dumped)


def test_persist_failure_does_not_raise(isolated_db) -> None:
    bad_repo = MagicMock()
    bad_repo.has_consent.side_effect = RuntimeError("db down")
    service = LayeredMemoryCollectionService(
        repository=bad_repo,
        config=SimpleNamespace(
            layered_memory_collection_enabled=True,
            layered_memory_retention_days=90,
            layered_memory_vector_enabled=False,
            layered_memory_max_records_per_principal=200,
            layered_memory_audit_enabled=True,
        ),
    )
    assert service.collect_from_analysis_result(
        result=_result(),
        analysis_history_id=13,
        now=AS_OF,
    ) is None


def test_enabled_repository_initialization_failure_is_fail_soft() -> None:
    with patch(
        "src.services.layered_memory_collection_service.LayeredMemoryRepository",
        side_effect=RuntimeError("database unavailable"),
    ):
        assert try_collect_layered_memory_observation(
            result=_result(),
            analysis_history_id=14,
            config=SimpleNamespace(layered_memory_collection_enabled=True),
            now=AS_OF,
        ) is None


def test_client_provenance_on_collect_is_fail_soft(isolated_db) -> None:
    cfg = SimpleNamespace(
        layered_memory_collection_enabled=True,
        layered_memory_retention_days=90,
        layered_memory_vector_enabled=False,
        layered_memory_max_records_per_principal=200,
        layered_memory_audit_enabled=True,
    )
    repo = LayeredMemoryRepository()
    PrincipalMemoryLifecycle(
        policy=LayeredMemoryPolicy.from_config(cfg),
        store=DurableLayeredMemoryStore(repo),
    ).grant_consent(LAYERED_MEMORY_OPERATOR_PRINCIPAL, at=AS_OF)
    stored = LayeredMemoryCollectionService(repository=repo, config=cfg).collect_observation(
        {
            "principal_id": "local_admin",
            "analysis_history_id": 15,
            "stock_code": "600519",
            "observed_at": AS_OF,
            "expires_at": None,
            "signal": "buy",
            "sentiment_score": 50.0,
            "price_at_analysis": 10.0,
            "provenance_source": "operator",
        },
        config=cfg,
        now=AS_OF,
    )
    assert stored is None
    assert repo.list_records("local_admin") == []
