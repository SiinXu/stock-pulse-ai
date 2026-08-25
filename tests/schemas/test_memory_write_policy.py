# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Counterexample tests for the #1119 Slice 1 memory write admission policy."""

from __future__ import annotations

from datetime import datetime, timezone
import inspect

import pytest

from src.agent.evolution.adapters import DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES
from src.agent.memory_layers import MIN_OUTCOME_PATTERN_EVIDENCE
from src.agent.sandbox.policy import SANDBOX_ISOLATION_POLICY
from src.agent.sandbox.promotion import PromotionReceipt
from src.agent.soul import AGENT_SOUL_MARKER
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.approvals import LOCAL_ADMIN_OWNER
from src.schemas.memory_fact_opinion import FactOpinionMixError
from src.schemas.memory_provenance import (
    FEEDBACK_ACTOR_ID,
    MemoryProvenanceError,
    PROVENANCE_SOURCE_OPERATOR,
    PROVENANCE_SOURCE_SYSTEM_RESOLVE,
    PROVENANCE_SOURCE_USER_FEEDBACK,
)
from src.schemas.memory_write_guard import MemoryWriteRejectedError
from src.schemas.memory_write_policy import (
    ERROR_PERSIST_FORBIDDEN,
    ERROR_PROCEDURAL_EVAL_GATE_UNMET,
    ERROR_PROCEDURAL_MIN_SAMPLES_INVALID,
    ERROR_PROCEDURAL_SAMPLE_THRESHOLD_UNMET,
    ERROR_SEMANTIC_UNVERIFIED,
    MemoryWriteAdmissionError,
    SEMANTIC_FACT_MIN_INDEPENDENT_EVIDENCE,
    WRITE_CLASS_PROCEDURAL_FLAG,
    WRITE_CLASS_SEMANTIC_FACT,
    _admit_semantic_fact,
    admit_memory_write,
    require_episodic_write,
    require_market_actuals_write,
    require_memory_write,
    require_opinion_write,
)


def _compact_episode(**overrides: object) -> AgentEpisodeCreate:
    payload = {
        "episode_id": "ep-policy-compact",
        "run_id": "run-policy-compact",
        "mode": "single",
        "symbol": "600519",
        "market": "cn",
        "started_at": datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 8, 12, 10, 1, 0, tzinfo=timezone.utc),
        "success": True,
        "trajectory_summary": [
            {"tool": "get_quote", "success": True, "duration_ms": 12}
        ],
        "lessons": [
            {"kind": "evidence_gap", "severity": "low", "remedy": "add source"}
        ],
        "outcome_labels": {
            "user_feedback": "disagree_score",
            "extra": {"comment": "review later"},
        },
    }
    payload.update(overrides)
    return AgentEpisodeCreate.model_validate(payload)


def test_compact_episode_is_admitted_after_structured_validation() -> None:
    decision = require_episodic_write(_compact_episode())
    assert decision.admitted is True
    assert decision.persist is True
    assert decision.write_class == "episodic"
    assert decision.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert decision.actor_id is None
    assert decision.auto_promote is False


def test_oversize_soul_and_control_episode_text_rejected_unchanged() -> None:
    oversize = _compact_episode(episode_id="ep-oversize")
    assert oversize.outcome_labels is not None
    oversize.outcome_labels.user_feedback = "x" * 257
    with pytest.raises(MemoryWriteRejectedError, match="at most 256"):
        require_episodic_write(oversize)

    soul = _compact_episode(episode_id="ep-soul")
    assert soul.outcome_labels is not None
    soul.outcome_labels.user_feedback = AGENT_SOUL_MARKER
    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        require_episodic_write(soul)

    control = _compact_episode(episode_id="ep-control")
    assert control.outcome_labels is not None
    control.outcome_labels.user_feedback = "ok\x00spoof"
    with pytest.raises(MemoryWriteRejectedError, match="control characters"):
        require_episodic_write(control)


def test_system_resolve_market_actuals_are_admitted_and_server_stamped() -> None:
    actuals = {"label": "hit", "score": 1.0, "engine_version": "claim-scorer-v1"}
    decision = require_market_actuals_write(actuals)
    assert decision.admitted is True
    assert decision.persist is True
    assert decision.write_class == "market_actuals"
    assert decision.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert decision.actor_id is None
    assert "provenance_source" not in actuals
    stamped = decision.stamped_payload(actuals)
    assert stamped["label"] == "hit"
    assert stamped["provenance_source"] == PROVENANCE_SOURCE_SYSTEM_RESOLVE


def test_opinion_payloads_cannot_contain_actual_or_outcome_fields() -> None:
    with pytest.raises(FactOpinionMixError, match="outcome"):
        require_opinion_write(
            {
                "feedback_value": "not_useful",
                "note": "user override",
                "source": "api",
                "outcome": "miss",
            }
        )
    with pytest.raises(FactOpinionMixError, match="actuals"):
        require_opinion_write(
            {
                "feedback_value": "useful",
                "source": "web",
                "actuals": {"end_price": 1.0},
            },
            provenance_source=PROVENANCE_SOURCE_OPERATOR,
            actor_id=FEEDBACK_ACTOR_ID,
        )


def test_forged_provenance_is_rejected_before_server_stamp() -> None:
    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        require_market_actuals_write(
            {
                "label": "hit",
                "score": 1.0,
                "provenance_source": PROVENANCE_SOURCE_USER_FEEDBACK,
            }
        )
    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        require_opinion_write(
            {
                "feedback_value": "useful",
                "source": "web",
                "actor_id": "root",
            }
        )
    legal, stamped = require_opinion_write(
        {"feedback_value": "useful", "source": "web", "note": "agrees"}
    )
    assert legal.provenance_source == PROVENANCE_SOURCE_USER_FEEDBACK
    assert legal.actor_id == FEEDBACK_ACTOR_ID
    assert stamped["provenance_source"] == PROVENANCE_SOURCE_USER_FEEDBACK
    assert stamped["actor_id"] == FEEDBACK_ACTOR_ID


def test_single_unverified_semantic_fact_is_rejected() -> None:
    decision = admit_memory_write(
        write_class=WRITE_CLASS_SEMANTIC_FACT,
        payload={"note": "this stock always wins", "source": "web"},
        independent_evidence_count=1,
        independently_verified=False,
        operator_promote=False,
    )
    assert decision.admitted is False
    assert decision.persist is False
    assert decision.error_code == ERROR_SEMANTIC_UNVERIFIED
    with pytest.raises(MemoryWriteAdmissionError) as exc_info:
        require_memory_write(
            write_class=WRITE_CLASS_SEMANTIC_FACT,
            payload={"note": "this stock always wins", "source": "web"},
            independent_evidence_count=1,
            independently_verified=False,
        )
    assert exc_info.value.error_code == ERROR_SEMANTIC_UNVERIFIED


def test_repeated_verified_evidence_and_operator_promote_are_candidates_only() -> None:
    assert SEMANTIC_FACT_MIN_INDEPENDENT_EVIDENCE == MIN_OUTCOME_PATTERN_EVIDENCE
    repeated = admit_memory_write(
        write_class=WRITE_CLASS_SEMANTIC_FACT,
        payload={"note": "repeated verified miss pattern", "source": "api"},
        independent_evidence_count=MIN_OUTCOME_PATTERN_EVIDENCE,
        independently_verified=True,
    )
    assert repeated.admitted is True
    assert repeated.persist is False
    assert repeated.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert repeated.auto_promote is False

    promoted = admit_memory_write(
        write_class=WRITE_CLASS_SEMANTIC_FACT,
        payload={"note": "operator reviewed candidate", "source": "api"},
        independent_evidence_count=1,
        independently_verified=False,
        operator_promote=True,
    )
    assert promoted.admitted is True
    assert promoted.persist is False
    assert promoted.provenance_source == PROVENANCE_SOURCE_OPERATOR
    assert promoted.actor_id == LOCAL_ADMIN_OWNER
    assert promoted.auto_promote is False

    with pytest.raises(MemoryWriteAdmissionError) as exc_info:
        require_memory_write(
            write_class=WRITE_CLASS_SEMANTIC_FACT,
            independent_evidence_count=MIN_OUTCOME_PATTERN_EVIDENCE,
            independently_verified=True,
            persist_required=True,
        )
    assert exc_info.value.error_code == ERROR_PERSIST_FORBIDDEN


def test_procedural_flag_requires_both_threshold_and_eval_gate() -> None:
    floor = DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES
    threshold_only = admit_memory_write(
        write_class=WRITE_CLASS_PROCEDURAL_FLAG,
        sample_count=floor,
        min_samples=floor,
        eval_gate_passed=False,
    )
    assert threshold_only.admitted is False
    assert threshold_only.error_code == ERROR_PROCEDURAL_EVAL_GATE_UNMET

    absent_gate = admit_memory_write(
        write_class=WRITE_CLASS_PROCEDURAL_FLAG,
        sample_count=floor,
        min_samples=floor,
        eval_gate_passed=None,
    )
    assert absent_gate.admitted is False
    assert absent_gate.error_code == ERROR_PROCEDURAL_EVAL_GATE_UNMET

    eval_only = admit_memory_write(
        write_class=WRITE_CLASS_PROCEDURAL_FLAG,
        sample_count=floor - 1,
        min_samples=floor,
        eval_gate_passed=True,
    )
    assert eval_only.admitted is False
    assert eval_only.error_code == ERROR_PROCEDURAL_SAMPLE_THRESHOLD_UNMET

    omitted_floor = admit_memory_write(
        write_class=WRITE_CLASS_PROCEDURAL_FLAG,
        sample_count=floor,
        eval_gate_passed=True,
    )
    assert omitted_floor.admitted is False
    assert omitted_floor.error_code == ERROR_PROCEDURAL_MIN_SAMPLES_INVALID

    invalid_floor = admit_memory_write(
        write_class=WRITE_CLASS_PROCEDURAL_FLAG,
        sample_count=floor,
        min_samples=True,  # type: ignore[arg-type]
        eval_gate_passed=True,
    )
    assert invalid_floor.admitted is False
    assert invalid_floor.error_code == ERROR_PROCEDURAL_MIN_SAMPLES_INVALID

    both = admit_memory_write(
        write_class=WRITE_CLASS_PROCEDURAL_FLAG,
        sample_count=floor,
        min_samples=floor,
        eval_gate_passed=True,
    )
    assert both.admitted is True
    assert both.persist is False
    assert both.auto_promote is False
    assert SANDBOX_ISOLATION_POLICY["auto_promote_to_production"] is False
    receipt = PromotionReceipt.__dataclass_fields__["auto_promote"].default
    assert receipt is False


def test_episode_extra_actuals_keys_are_rejected() -> None:
    episode = _compact_episode()
    assert episode.outcome_labels is not None
    episode.outcome_labels.extra["outcome"] = "miss"
    with pytest.raises(FactOpinionMixError, match="outcome"):
        require_episodic_write(episode)


def test_operator_promote_stamps_canonical_owner_not_feedback_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_source = inspect.getsource(_admit_semantic_fact)
    assert "LOCAL_ADMIN_OWNER" in semantic_source
    assert "FEEDBACK_ACTOR_ID" not in semantic_source

    monkeypatch.setattr(
        "src.schemas.memory_write_policy.FEEDBACK_ACTOR_ID",
        "feedback-only-alias",
    )
    promoted = admit_memory_write(
        write_class=WRITE_CLASS_SEMANTIC_FACT,
        payload={"note": "operator reviewed candidate", "source": "api"},
        operator_promote=True,
    )
    assert promoted.admitted is True
    assert promoted.provenance_source == PROVENANCE_SOURCE_OPERATOR
    assert promoted.actor_id == LOCAL_ADMIN_OWNER
    assert promoted.actor_id != "feedback-only-alias"

    _decision, operator_stamped = require_opinion_write(
        {"feedback_value": "useful", "source": "api"},
        provenance_source=PROVENANCE_SOURCE_OPERATOR,
    )
    assert operator_stamped["provenance_source"] == PROVENANCE_SOURCE_OPERATOR
    assert operator_stamped["actor_id"] == LOCAL_ADMIN_OWNER
    assert operator_stamped["actor_id"] != "feedback-only-alias"

    _feedback, feedback_stamped = require_opinion_write(
        {"feedback_value": "useful", "source": "web"}
    )
    assert feedback_stamped["provenance_source"] == PROVENANCE_SOURCE_USER_FEEDBACK
    assert feedback_stamped["actor_id"] == "feedback-only-alias"


def test_persist_callers_import_schema_policy_not_agent() -> None:
    import src.repositories.agent_episode_repo as episode_repo
    import src.repositories.agent_feedback_repo as feedback_repo
    import src.repositories.agent_prediction_repo as prediction_repo
    import src.repositories.decision_signal_outcome_repo as outcome_repo
    import src.services.agent_feedback_service as feedback_service
    import src.services.prediction_resolver.memory_store as memory_store

    for module in (
        episode_repo,
        feedback_repo,
        prediction_repo,
        outcome_repo,
        feedback_service,
        memory_store,
    ):
        source = inspect.getsource(module)
        assert "src.agent.memory_write_policy" not in source
        assert "src.schemas.memory_write_policy" in source
        assert "require_opinion_write" in source or "require_market_actuals_write" in source or "require_episodic_write" in source
