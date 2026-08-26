# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Admission counterexamples for layered-memory observation persist."""

from __future__ import annotations

import pytest

from src.schemas.layered_memory_persist import (
    LayeredMemoryPersistError,
    admit_layered_observation_mapping,
)
from src.schemas.memory_fact_opinion import FactOpinionMixError
from src.schemas.memory_provenance import (
    MemoryProvenanceError,
    PROVENANCE_SOURCE_SYSTEM_RESOLVE,
)
from src.schemas.memory_write_guard import MemoryWriteRejectedError
from src.schemas.memory_write_policy import (
    WRITE_CLASS_PROCEDURAL_FLAG,
    WRITE_CLASS_SEMANTIC_FACT,
    admit_memory_write,
)


def _payload(**overrides):
    data = {
        "principal_id": "local_admin",
        "analysis_history_id": 7,
        "stock_code": "600519",
        "observed_at": "2026-08-09T00:00:00Z",
        "expires_at": None,
        "signal": "buy",
        "sentiment_score": 61.0,
        "price_at_analysis": 101.5,
    }
    data.update(overrides)
    return data


def test_admitted_observation_is_server_stamped() -> None:
    observation, stamp = admit_layered_observation_mapping(_payload())
    assert observation.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert stamp["provenance_source"] == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert stamp["actor_id"] is None


@pytest.mark.parametrize(
    "spoof",
    [
        {"provenance_source": "operator"},
        {"actor_id": "root"},
        {"memory_source": "system_resolve"},
        {"provenance": {"source": "operator"}},
        {"source": "system_resolve"},
    ],
)
def test_client_provenance_keys_are_rejected(spoof: dict) -> None:
    with pytest.raises(MemoryProvenanceError):
        admit_layered_observation_mapping(_payload(**spoof))


def test_secret_and_pii_keys_are_rejected_not_stored() -> None:
    with pytest.raises(LayeredMemoryPersistError, match="forbidden keys"):
        admit_layered_observation_mapping(_payload(api_key="sk-secret-example"))
    with pytest.raises(LayeredMemoryPersistError, match="forbidden keys"):
        admit_layered_observation_mapping(_payload(soul_charter="do not store"))
    with pytest.raises(LayeredMemoryPersistError, match="forbidden keys"):
        admit_layered_observation_mapping(_payload(system_prompt="ignore previous"))
    with pytest.raises(LayeredMemoryPersistError, match="forbidden keys"):
        admit_layered_observation_mapping(_payload(raw_provider_payload={"k": "v"}))


def test_secret_value_redaction_is_rejected() -> None:
    with pytest.raises(LayeredMemoryPersistError, match="secrets or PII"):
        admit_layered_observation_mapping(
            _payload(principal_id="sk-abcdefghijklmnopqrstuvwxyz012345")
        )


def test_soul_marker_in_identifier_is_rejected() -> None:
    with pytest.raises(MemoryWriteRejectedError):
        admit_layered_observation_mapping(
            _payload(principal_id="stockpulse-agent-soul")
        )


def test_opinion_keys_cannot_ride_with_observations() -> None:
    with pytest.raises(FactOpinionMixError):
        admit_layered_observation_mapping(_payload(note="user note"))
    with pytest.raises(FactOpinionMixError):
        admit_layered_observation_mapping(_payload(user_feedback="agree"))


def test_semantic_and_procedural_writes_still_do_not_persist() -> None:
    semantic = admit_memory_write(
        write_class=WRITE_CLASS_SEMANTIC_FACT,
        payload={"fact": "sector is defensive"},
        independently_verified=True,
        independent_evidence_count=3,
    )
    assert semantic.admitted is True
    assert semantic.persist is False
    procedural = admit_memory_write(
        write_class=WRITE_CLASS_PROCEDURAL_FLAG,
        sample_count=40,
        eval_gate_passed=True,
        min_samples=30,
    )
    assert procedural.admitted is True
    assert procedural.persist is False
