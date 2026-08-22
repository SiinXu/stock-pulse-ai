# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic contract tests for #1124 DAG-3 memory provenance stamps."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.v1.schemas.decision_signals import DecisionSignalFeedbackRequest
from src.schemas.approvals import LOCAL_ADMIN_OWNER
from src.schemas.memory_provenance import (
    CLIENT_PROVENANCE_KEYS,
    FEEDBACK_ACTOR_ID,
    MemoryProvenanceError,
    PROVENANCE_SOURCE_OPERATOR,
    PROVENANCE_SOURCE_SYSTEM_RESOLVE,
    PROVENANCE_SOURCE_USER_FEEDBACK,
    PROVENANCE_SOURCE_VALUES,
    apply_server_provenance,
    reject_client_provenance_keys,
    require_persisted_provenance,
    stamp_memory_provenance,
)


def test_vocabulary_and_feedback_actor_are_server_owned() -> None:
    assert PROVENANCE_SOURCE_VALUES == frozenset(
        {
            PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            PROVENANCE_SOURCE_USER_FEEDBACK,
            PROVENANCE_SOURCE_OPERATOR,
        }
    )
    assert FEEDBACK_ACTOR_ID == LOCAL_ADMIN_OWNER
    assert "source" not in CLIENT_PROVENANCE_KEYS


def test_stamp_memory_provenance_rejects_unknown_and_invalid_actor() -> None:
    stamp = stamp_memory_provenance(
        provenance_source=PROVENANCE_SOURCE_USER_FEEDBACK,
        actor_id=LOCAL_ADMIN_OWNER,
    )
    assert stamp == {
        "provenance_source": PROVENANCE_SOURCE_USER_FEEDBACK,
        "actor_id": LOCAL_ADMIN_OWNER,
    }
    system_stamp = stamp_memory_provenance(
        provenance_source=PROVENANCE_SOURCE_SYSTEM_RESOLVE,
        actor_id=None,
    )
    assert system_stamp == {
        "provenance_source": PROVENANCE_SOURCE_SYSTEM_RESOLVE,
        "actor_id": None,
    }
    with pytest.raises(MemoryProvenanceError, match="unknown provenance_source"):
        stamp_memory_provenance(provenance_source="web")
    with pytest.raises(MemoryProvenanceError, match="non-empty string"):
        stamp_memory_provenance(
            provenance_source=PROVENANCE_SOURCE_OPERATOR,
            actor_id="  ",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"provenance_source": PROVENANCE_SOURCE_SYSTEM_RESOLVE},
        {"actor_id": "root"},
        {"memory_source": "system_resolve"},
        {"provenance": {"source": "operator"}},
        {"source": PROVENANCE_SOURCE_SYSTEM_RESOLVE},
        {"source": PROVENANCE_SOURCE_OPERATOR},
    ],
)
def test_reject_client_provenance_keys(payload: dict) -> None:
    with pytest.raises(MemoryProvenanceError, match="provenance"):
        reject_client_provenance_keys(
            {"feedback_value": "useful", "source": "web", **payload}
            if "source" not in payload
            else {"feedback_value": "useful", **payload}
        )


def test_apply_and_require_server_stamp() -> None:
    legal = {
        "signal_id": 1,
        "feedback_value": "useful",
        "source": "web",
    }
    stamped = apply_server_provenance(
        legal,
        provenance_source=PROVENANCE_SOURCE_USER_FEEDBACK,
        actor_id=FEEDBACK_ACTOR_ID,
    )
    assert stamped["source"] == "web"
    assert stamped["provenance_source"] == PROVENANCE_SOURCE_USER_FEEDBACK
    assert stamped["actor_id"] == FEEDBACK_ACTOR_ID
    require_persisted_provenance(
        stamped,
        expected_source=PROVENANCE_SOURCE_USER_FEEDBACK,
        expected_actor_id=FEEDBACK_ACTOR_ID,
    )
    with pytest.raises(MemoryProvenanceError, match="persist requires"):
        require_persisted_provenance(
            legal,
            expected_source=PROVENANCE_SOURCE_USER_FEEDBACK,
            expected_actor_id=FEEDBACK_ACTOR_ID,
        )
    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        apply_server_provenance(
            {**legal, "provenance_source": PROVENANCE_SOURCE_SYSTEM_RESOLVE},
            provenance_source=PROVENANCE_SOURCE_USER_FEEDBACK,
            actor_id=FEEDBACK_ACTOR_ID,
        )


def test_feedback_request_rejects_client_provenance_and_extra_keys() -> None:
    with pytest.raises((ValidationError, MemoryProvenanceError)):
        DecisionSignalFeedbackRequest.model_validate(
            {
                "feedback_value": "useful",
                "source": "web",
                "provenance_source": PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            }
        )
    with pytest.raises((ValidationError, MemoryProvenanceError)):
        DecisionSignalFeedbackRequest.model_validate(
            {
                "feedback_value": "useful",
                "source": "api",
                "actor_id": "root",
            }
        )
    with pytest.raises((ValidationError, MemoryProvenanceError)):
        DecisionSignalFeedbackRequest.model_validate(
            {
                "feedback_value": "useful",
                "source": "web",
                "provenance_source": PROVENANCE_SOURCE_OPERATOR,
            }
        )
    with pytest.raises(ValidationError):
        DecisionSignalFeedbackRequest.model_validate(
            {
                "feedback_value": "useful",
                "source": PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            }
        )
    request = DecisionSignalFeedbackRequest.model_validate(
        {
            "feedback_value": "useful",
            "reason_code": "matched_plan",
            "note": "agrees with the call",
            "source": "web",
        }
    )
    assert request.source == "web"
    assert not hasattr(request, "provenance_source") or "provenance_source" not in request.model_fields_set
