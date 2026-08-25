# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Schema-only validation for the EvolutionEvent store contract."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.evolution_event import (
    EVOLUTION_EVENT_MAX_LIMIT,
    EvolutionEventCreate,
    normalize_optional_event_type,
    validate_query_limit,
    validate_query_window,
)


def _valid(**overrides):
    payload = {
        "event_type": "adapter.confidence_calibration",
        "actor": "system",
        "reason_refs": {
            "prediction_ids": ["pred-1"],
            "run_ids": ["run-1"],
        },
        "before": {"confidence": 0.4},
        "after": {"confidence": 0.5},
    }
    payload.update(overrides)
    return payload


def test_append_payload_serializes_required_fields() -> None:
    event = EvolutionEventCreate.model_validate(_valid())
    dumped = event.model_dump(mode="json")
    assert dumped["event_id"]
    assert dumped["occurred_at"].endswith("+00:00") or dumped["occurred_at"].endswith("Z")
    assert dumped["event_type"] == "adapter.confidence_calibration"
    assert dumped["actor"] == "system"
    assert dumped["reason_refs"]["prediction_ids"] == ["pred-1"]
    assert dumped["reason_refs"]["run_ids"] == ["run-1"]
    assert dumped["before"] == {"confidence": 0.4}
    assert dumped["after"] == {"confidence": 0.5}


@pytest.mark.parametrize("actor", ["system", "user", "operator"])
def test_allowlisted_actors_are_accepted(actor: str) -> None:
    event = EvolutionEventCreate.model_validate(_valid(actor=actor))
    assert event.actor == actor


@pytest.mark.parametrize("actor", ["admin", "SYSTEM", "", "resolver"])
def test_unknown_actor_is_rejected(actor: str) -> None:
    with pytest.raises(ValidationError):
        EvolutionEventCreate.model_validate(_valid(actor=actor))


@pytest.mark.parametrize("event_type", ["", "   ", "bad type", "1starts-digit"])
def test_nonempty_type_is_required(event_type: str) -> None:
    with pytest.raises(ValidationError):
        EvolutionEventCreate.model_validate(_valid(event_type=event_type))


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        EvolutionEventCreate.model_validate(
            _valid(occurred_at=datetime(2026, 8, 25, 12, 0))
        )


@pytest.mark.parametrize(
    "snapshot",
    [
        {"api_key": "secret"},
        {"system_prompt": "You are the agent."},
        {"provider_payload": {"choices": []}},
        {"accessToken": "tok"},
        {"systemPrompt": "You are the agent."},
        {"providerPayload": {"choices": []}},
        {"system-prompt": "You are the agent."},
        {"provider.payload": {"choices": []}},
        {"access.Token": "tok"},
        {"meta": {"accessToken": "nested"}},
        {"meta": {"system.prompt": "nested"}},
    ],
)
def test_forbidden_payload_keys_reject_nested_and_variant_names(snapshot: dict) -> None:
    with pytest.raises(ValidationError, match="must not persist"):
        EvolutionEventCreate.model_validate(_valid(before=snapshot))


def test_empty_reason_refs_are_allowed_without_inventing_ids() -> None:
    event = EvolutionEventCreate.model_validate(
        _valid(reason_refs={"prediction_ids": [], "run_ids": []})
    )
    assert event.reason_refs.prediction_ids == []
    assert event.reason_refs.run_ids == []


@pytest.mark.parametrize(
    "before, after",
    [
        ({}, {}),
        ({"factor": 1.0}, {"factor": 1.0}),
        ({"n": 1}, {"n": 1}),
    ],
)
def test_noop_and_identical_snapshots_are_rejected(before: dict, after: dict) -> None:
    with pytest.raises(ValidationError, match="must describe a mutation"):
        EvolutionEventCreate.model_validate(_valid(before=before, after=after))


def test_non_finite_snapshot_numbers_are_rejected() -> None:
    with pytest.raises(ValidationError):
        EvolutionEventCreate.model_validate(_valid(before={"confidence": float("nan")}))


def test_query_window_and_limit_validation() -> None:
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    end = datetime(2026, 8, 2, tzinfo=timezone.utc)
    assert validate_query_window(start, end) == (start, end)
    with pytest.raises(ValueError, match="timezone-aware"):
        validate_query_window(datetime(2026, 8, 1), end)
    with pytest.raises(ValueError, match="less than or equal"):
        validate_query_window(end, start)
    assert validate_query_limit(None) == 100
    assert validate_query_limit(1) == 1
    with pytest.raises(ValueError, match="between"):
        validate_query_limit(0)
    with pytest.raises(ValueError, match="between"):
        validate_query_limit(EVOLUTION_EVENT_MAX_LIMIT + 1)
    assert normalize_optional_event_type(None) is None
    with pytest.raises(ValueError, match="nonempty"):
        normalize_optional_event_type("  ")
    with pytest.raises(ValueError, match="nonempty"):
        normalize_optional_event_type("")
    assert normalize_optional_event_type("adapter.confidence_calibration") == (
        "adapter.confidence_calibration"
    )
