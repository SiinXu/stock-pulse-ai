# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic contract tests for the #1124 DAG-2 memory write guard."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agent.soul import AGENT_SOUL_END_MARKER, AGENT_SOUL_MARKER
from src.api.v1.schemas.decision_signals import DecisionSignalFeedbackRequest
from src.schemas.agent_episode import EpisodeLesson, EpisodeOutcomeLabels
from src.schemas.memory_write_guard import (
    FEEDBACK_NOTE_MAX_LENGTH,
    FEEDBACK_REASON_CODE_MAX_LENGTH,
    MemoryWriteRejectedError,
    SOUL_BOUNDARY_TOKEN,
    reject_feedback_write_fields,
    reject_memory_write_text,
)


def test_soul_boundary_token_matches_composer_markers() -> None:
    assert SOUL_BOUNDARY_TOKEN in AGENT_SOUL_MARKER.lower()
    assert SOUL_BOUNDARY_TOKEN in AGENT_SOUL_END_MARKER.lower()
    assert AGENT_SOUL_END_MARKER == "<!-- /stockpulse-agent-soul -->"


def test_reject_memory_write_text_allows_legal_and_none() -> None:
    legal = "user disagrees with the hit"
    assert reject_memory_write_text(
        legal, field_name="note", max_length=FEEDBACK_NOTE_MAX_LENGTH
    ) is legal
    assert reject_memory_write_text(
        None, field_name="note", max_length=FEEDBACK_NOTE_MAX_LENGTH
    ) is None
    exact = "a" * FEEDBACK_NOTE_MAX_LENGTH
    assert reject_memory_write_text(
        exact, field_name="note", max_length=FEEDBACK_NOTE_MAX_LENGTH
    ) is exact


@pytest.mark.parametrize(
    "payload",
    [
        AGENT_SOUL_MARKER,
        AGENT_SOUL_END_MARKER,
        "<!-- StockPulse-Agent-Soul -->",
        "stockpulse-agent-soul",
        f"looks fine {AGENT_SOUL_MARKER}",
    ],
)
def test_reject_memory_write_text_rejects_soul_markers(payload: str) -> None:
    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        reject_memory_write_text(
            payload, field_name="note", max_length=FEEDBACK_NOTE_MAX_LENGTH
        )


def test_reject_memory_write_text_rejects_oversize_and_controls() -> None:
    with pytest.raises(MemoryWriteRejectedError, match="at most 1000"):
        reject_memory_write_text(
            "x" * (FEEDBACK_NOTE_MAX_LENGTH + 1),
            field_name="note",
            max_length=FEEDBACK_NOTE_MAX_LENGTH,
        )
    with pytest.raises(MemoryWriteRejectedError, match="control characters"):
        reject_memory_write_text(
            "ok\x00spoof", field_name="note", max_length=FEEDBACK_NOTE_MAX_LENGTH
        )
    with pytest.raises(MemoryWriteRejectedError, match="must be a string"):
        reject_memory_write_text(
            123, field_name="note", max_length=FEEDBACK_NOTE_MAX_LENGTH
        )


def test_reject_feedback_write_fields_covers_note_and_reason_code() -> None:
    legal = {
        "feedback_value": "useful",
        "reason_code": "matched_plan",
        "note": "agrees with the call",
        "source": "web",
    }
    assert reject_feedback_write_fields(legal) is legal
    with pytest.raises(MemoryWriteRejectedError, match="note"):
        reject_feedback_write_fields({**legal, "note": AGENT_SOUL_MARKER})
    with pytest.raises(MemoryWriteRejectedError, match="reason_code"):
        reject_feedback_write_fields(
            {**legal, "reason_code": f"x{AGENT_SOUL_END_MARKER}"}
        )


def test_feedback_request_rejects_marker_and_oversize() -> None:
    with pytest.raises(ValidationError, match="Soul boundary"):
        DecisionSignalFeedbackRequest.model_validate(
            {
                "feedback_value": "useful",
                "source": "api",
                "note": f"ok {AGENT_SOUL_MARKER} spoof",
            }
        )
    with pytest.raises(ValidationError):
        DecisionSignalFeedbackRequest.model_validate(
            {
                "feedback_value": "useful",
                "source": "api",
                "note": "n" * (FEEDBACK_NOTE_MAX_LENGTH + 1),
            }
        )
    request = DecisionSignalFeedbackRequest.model_validate(
        {
            "feedback_value": "useful",
            "reason_code": "matched_plan",
            "note": "n" * FEEDBACK_NOTE_MAX_LENGTH,
            "source": "web",
        }
    )
    assert request.note is not None
    assert len(request.note) == FEEDBACK_NOTE_MAX_LENGTH
    assert request.reason_code == "matched_plan"


def test_episode_free_text_rejects_soul_markers() -> None:
    with pytest.raises(ValidationError, match="Soul boundary"):
        EpisodeOutcomeLabels.model_validate({"user_feedback": AGENT_SOUL_MARKER})
    with pytest.raises(ValidationError, match="Soul boundary"):
        EpisodeOutcomeLabels.model_validate(
            {"extra": {"comment": AGENT_SOUL_END_MARKER}}
        )
    with pytest.raises(ValidationError, match="Soul boundary"):
        EpisodeLesson.model_validate(
            {"kind": "evidence_gap", "remedy": f"fix {SOUL_BOUNDARY_TOKEN}"}
        )
    labels = EpisodeOutcomeLabels.model_validate(
        {"user_feedback": "disagree_score", "extra": {"comment": "review later"}}
    )
    assert labels.user_feedback == "disagree_score"
    assert labels.extra["comment"] == "review later"


def test_reason_code_cap_is_unchanged() -> None:
    assert FEEDBACK_REASON_CODE_MAX_LENGTH == 64
    with pytest.raises(ValidationError):
        DecisionSignalFeedbackRequest.model_validate(
            {
                "feedback_value": "useful",
                "reason_code": "r" * (FEEDBACK_REASON_CODE_MAX_LENGTH + 1),
            }
        )
