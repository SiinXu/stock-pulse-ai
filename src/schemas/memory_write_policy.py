# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Library-only memory WRITE admission policy (#1119 Slice 1).

Classifies persist attempts over existing episode / prediction / decision-signal
stores and fails closed. Reuses #1124 ``memory_fact_opinion``,
``memory_write_guard``, and ``memory_provenance``; it does not fork or weaken
those contracts.

This module lives next to those write contracts so repositories and services
can import it without an upward ``src.repositories`` / ``src.services`` →
``src.agent`` edge.

This module is not Decision Memory inject admission. ``admit_decision_memory``
in ``src.services.decision_memory_service`` remains a separate READ-path
renderer filter and must not be routed through this write policy.

Out of slice: consolidation, forgetting, TTL / per-symbol caps, score decay,
the #1118 layered store, #1113 EvolutionEvent, auto-promotion, new env keys,
migrations, and public API / Web / Desktop changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from src.schemas.agent_episode import reject_episode_free_text
from src.schemas.approvals import LOCAL_ADMIN_OWNER
from src.schemas.memory_fact_opinion import (
    FactOpinionMixError,
    lock_opinion_payload,
    lock_prediction_outcome_actuals,
)
from src.schemas.memory_provenance import (
    FEEDBACK_ACTOR_ID,
    MemoryProvenanceError,
    PROVENANCE_SOURCE_OPERATOR,
    PROVENANCE_SOURCE_SYSTEM_RESOLVE,
    PROVENANCE_SOURCE_USER_FEEDBACK,
    reject_client_provenance_keys,
    stamp_memory_provenance,
)
from src.schemas.memory_write_guard import (
    MemoryWriteRejectedError,
    reject_feedback_write_fields,
)

WRITE_CLASS_EPISODIC = "episodic"
WRITE_CLASS_MARKET_ACTUALS = "market_actuals"
WRITE_CLASS_OPINION = "opinion"
WRITE_CLASS_SEMANTIC_FACT = "semantic_fact"
WRITE_CLASS_PROCEDURAL_FLAG = "procedural_flag"

WRITE_CLASSES = frozenset(
    {
        WRITE_CLASS_EPISODIC,
        WRITE_CLASS_MARKET_ACTUALS,
        WRITE_CLASS_OPINION,
        WRITE_CLASS_SEMANTIC_FACT,
        WRITE_CLASS_PROCEDURAL_FLAG,
    }
)

# Repeated independently verified evidence. Tests pin this to
# ``MIN_OUTCOME_PATTERN_EVIDENCE``; this module must not import ``src.agent``.
SEMANTIC_FACT_MIN_INDEPENDENT_EVIDENCE = 3

ERROR_UNKNOWN_CLASS = "memory_write_unknown_class"
ERROR_FACT_OPINION_MIX = "memory_write_fact_opinion_mix"
ERROR_SOUL_OR_OVERSIZE = "memory_write_soul_or_oversize"
ERROR_FORGED_PROVENANCE = "memory_write_forged_provenance"
ERROR_INVALID_PROVENANCE = "memory_write_invalid_provenance"
ERROR_SEMANTIC_UNVERIFIED = "memory_write_semantic_unverified"
ERROR_PROCEDURAL_EVAL_GATE_UNMET = "memory_write_procedural_eval_gate_unmet"
ERROR_PROCEDURAL_SAMPLE_THRESHOLD_UNMET = (
    "memory_write_procedural_sample_threshold_unmet"
)
ERROR_PROCEDURAL_MIN_SAMPLES_INVALID = (
    "memory_write_procedural_min_samples_invalid"
)
ERROR_PERSIST_FORBIDDEN = "memory_write_persist_forbidden"
ERROR_INVALID_EPISODE = "memory_write_invalid_episode"

_OPINION_PROVENANCE = frozenset(
    {PROVENANCE_SOURCE_USER_FEEDBACK, PROVENANCE_SOURCE_OPERATOR}
)


class MemoryWriteAdmissionError(ValueError):
    """Typed rejection for policy-only write classes (semantic / procedural)."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        write_class: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.write_class = write_class


@dataclass(frozen=True)
class MemoryWriteDecision:
    """Typed admit/reject result. Never replaced with ``None`` or bare ``False``."""

    admitted: bool
    persist: bool
    write_class: str
    error_code: Optional[str] = None
    reason: Optional[str] = None
    provenance_source: Optional[str] = None
    actor_id: Optional[str] = None
    auto_promote: bool = False
    cause: Optional[BaseException] = None

    def stamp_mapping(self) -> Dict[str, Optional[str]]:
        return {
            "provenance_source": self.provenance_source,
            "actor_id": self.actor_id,
        }

    def stamped_payload(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        out = dict(payload)
        out.update(self.stamp_mapping())
        return out


def _code_for_cause(exc: BaseException) -> str:
    if isinstance(exc, FactOpinionMixError):
        return ERROR_FACT_OPINION_MIX
    if isinstance(exc, MemoryWriteRejectedError):
        return ERROR_SOUL_OR_OVERSIZE
    if isinstance(exc, MemoryProvenanceError):
        return ERROR_FORGED_PROVENANCE
    return ERROR_UNKNOWN_CLASS


def _rejected(
    write_class: str,
    *,
    error_code: str,
    reason: str,
    cause: Optional[BaseException] = None,
) -> MemoryWriteDecision:
    return MemoryWriteDecision(
        admitted=False,
        persist=False,
        write_class=write_class,
        error_code=error_code,
        reason=reason,
        auto_promote=False,
        cause=cause,
    )


def _guarded_cause(write_class: str, exc: BaseException) -> MemoryWriteDecision:
    return _rejected(
        write_class,
        error_code=_code_for_cause(exc),
        reason=str(exc),
        cause=exc,
    )


def _strict_int(value: Any) -> Optional[int]:
    if type(value) is not int or value < 0:
        return None
    return value


def _opinion_actor(
    provenance_source: str,
    actor_id: Optional[str],
) -> str:
    if actor_id is not None:
        return actor_id
    if provenance_source == PROVENANCE_SOURCE_OPERATOR:
        return LOCAL_ADMIN_OWNER
    return FEEDBACK_ACTOR_ID


def _episode_mapping(episode: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(episode, Mapping):
        return episode
    dump = getattr(episode, "model_dump", None)
    if callable(dump):
        data = dump(mode="python")
        if isinstance(data, Mapping):
            return data
    return None


def _episode_extra(episode: Any) -> Optional[Mapping[str, Any]]:
    labels = getattr(episode, "outcome_labels", None)
    if labels is None and isinstance(episode, Mapping):
        labels = episode.get("outcome_labels")
    extra = getattr(labels, "extra", None) if labels is not None else None
    if extra is None and isinstance(labels, Mapping):
        extra = labels.get("extra")
    if isinstance(extra, Mapping):
        return extra
    return None


def _admit_episodic(episode: Any) -> MemoryWriteDecision:
    write_class = WRITE_CLASS_EPISODIC
    if episode is None:
        return _rejected(
            write_class,
            error_code=ERROR_INVALID_EPISODE,
            reason="episodic write requires an episode payload",
        )
    try:
        mapping = _episode_mapping(episode)
        if mapping is not None:
            reject_client_provenance_keys(mapping)
        extra = _episode_extra(episode)
        if extra is not None:
            lock_opinion_payload(extra)
        reject_episode_free_text(episode)
        stamp = stamp_memory_provenance(
            provenance_source=PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            actor_id=None,
        )
    except (
        FactOpinionMixError,
        MemoryWriteRejectedError,
        MemoryProvenanceError,
        TypeError,
    ) as exc:
        return _guarded_cause(write_class, exc)
    return MemoryWriteDecision(
        admitted=True,
        persist=True,
        write_class=write_class,
        provenance_source=stamp["provenance_source"],
        actor_id=stamp["actor_id"],
        auto_promote=False,
    )


def _admit_market_actuals(payload: Optional[Mapping[str, Any]]) -> MemoryWriteDecision:
    write_class = WRITE_CLASS_MARKET_ACTUALS
    if not isinstance(payload, Mapping):
        return _rejected(
            write_class,
            error_code=ERROR_UNKNOWN_CLASS,
            reason="market actuals write requires a mapping payload",
        )
    try:
        lock_prediction_outcome_actuals(payload)
        reject_client_provenance_keys(payload)
        stamp = stamp_memory_provenance(
            provenance_source=PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            actor_id=None,
        )
    except (FactOpinionMixError, MemoryProvenanceError, TypeError) as exc:
        return _guarded_cause(write_class, exc)
    return MemoryWriteDecision(
        admitted=True,
        persist=True,
        write_class=write_class,
        provenance_source=stamp["provenance_source"],
        actor_id=stamp["actor_id"],
        auto_promote=False,
    )


def _admit_opinion(
    payload: Optional[Mapping[str, Any]],
    *,
    provenance_source: Optional[str],
    actor_id: Optional[str],
) -> MemoryWriteDecision:
    write_class = WRITE_CLASS_OPINION
    if not isinstance(payload, Mapping):
        return _rejected(
            write_class,
            error_code=ERROR_UNKNOWN_CLASS,
            reason="opinion write requires a mapping payload",
        )
    source = provenance_source or PROVENANCE_SOURCE_USER_FEEDBACK
    if source not in _OPINION_PROVENANCE:
        return _rejected(
            write_class,
            error_code=ERROR_INVALID_PROVENANCE,
            reason="opinion writes must stamp user_feedback or operator",
        )
    stamped_actor = _opinion_actor(source, actor_id)
    try:
        lock_opinion_payload(payload)
        reject_feedback_write_fields(payload)
        reject_client_provenance_keys(payload)
        stamp = stamp_memory_provenance(
            provenance_source=source,
            actor_id=stamped_actor,
        )
    except (
        FactOpinionMixError,
        MemoryWriteRejectedError,
        MemoryProvenanceError,
        TypeError,
    ) as exc:
        return _guarded_cause(write_class, exc)
    return MemoryWriteDecision(
        admitted=True,
        persist=True,
        write_class=write_class,
        provenance_source=stamp["provenance_source"],
        actor_id=stamp["actor_id"],
        auto_promote=False,
    )


def _admit_semantic_fact(
    payload: Optional[Mapping[str, Any]],
    *,
    independent_evidence_count: Any,
    independently_verified: Any,
    operator_promote: Any,
) -> MemoryWriteDecision:
    write_class = WRITE_CLASS_SEMANTIC_FACT
    mapping: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
    try:
        if payload is not None and not isinstance(payload, Mapping):
            raise TypeError("semantic-fact payload must be a mapping")
        if mapping:
            lock_opinion_payload(mapping)
            reject_feedback_write_fields(mapping)
            reject_client_provenance_keys(mapping)
    except (
        FactOpinionMixError,
        MemoryWriteRejectedError,
        MemoryProvenanceError,
        TypeError,
    ) as exc:
        return _guarded_cause(write_class, exc)

    if operator_promote is True:
        stamp = stamp_memory_provenance(
            provenance_source=PROVENANCE_SOURCE_OPERATOR,
            actor_id=LOCAL_ADMIN_OWNER,
        )
        return MemoryWriteDecision(
            admitted=True,
            persist=False,
            write_class=write_class,
            provenance_source=stamp["provenance_source"],
            actor_id=stamp["actor_id"],
            auto_promote=False,
        )

    evidence = _strict_int(independent_evidence_count)
    if (
        independently_verified is True
        and evidence is not None
        and evidence >= SEMANTIC_FACT_MIN_INDEPENDENT_EVIDENCE
    ):
        stamp = stamp_memory_provenance(
            provenance_source=PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            actor_id=None,
        )
        return MemoryWriteDecision(
            admitted=True,
            persist=False,
            write_class=write_class,
            provenance_source=stamp["provenance_source"],
            actor_id=stamp["actor_id"],
            auto_promote=False,
        )

    return _rejected(
        write_class,
        error_code=ERROR_SEMANTIC_UNVERIFIED,
        reason=(
            "semantic facts reject a single unverified user note; "
            "require repeated independently verified evidence or operator promote"
        ),
    )


def _admit_procedural_flag(
    *,
    sample_count: Any,
    eval_gate_passed: Any,
    min_samples: Any,
) -> MemoryWriteDecision:
    write_class = WRITE_CLASS_PROCEDURAL_FLAG
    floor = _strict_int(min_samples)
    if floor is None or floor < 1:
        return _rejected(
            write_class,
            error_code=ERROR_PROCEDURAL_MIN_SAMPLES_INVALID,
            reason="procedural auto-flag requires an explicit positive min_samples",
        )
    if eval_gate_passed is not True:
        return _rejected(
            write_class,
            error_code=ERROR_PROCEDURAL_EVAL_GATE_UNMET,
            reason="procedural auto-flag requires an explicit passed eval gate",
        )
    samples = _strict_int(sample_count)
    if samples is None or samples < floor:
        return _rejected(
            write_class,
            error_code=ERROR_PROCEDURAL_SAMPLE_THRESHOLD_UNMET,
            reason=(
                "procedural auto-flag requires sample_count "
                f">= {floor}"
            ),
        )
    return MemoryWriteDecision(
        admitted=True,
        persist=False,
        write_class=write_class,
        provenance_source=PROVENANCE_SOURCE_SYSTEM_RESOLVE,
        actor_id=None,
        auto_promote=False,
    )


def admit_memory_write(
    *,
    write_class: str,
    payload: Optional[Mapping[str, Any]] = None,
    episode: Any = None,
    provenance_source: Optional[str] = None,
    actor_id: Optional[str] = None,
    independent_evidence_count: int = 0,
    independently_verified: bool = False,
    operator_promote: bool = False,
    sample_count: int = 0,
    eval_gate_passed: Optional[bool] = None,
    min_samples: Optional[int] = None,
) -> MemoryWriteDecision:
    """Evaluate a write. Always returns a decision; never ``None``."""
    if write_class not in WRITE_CLASSES:
        return _rejected(
            str(write_class),
            error_code=ERROR_UNKNOWN_CLASS,
            reason=f"unknown memory write class: {write_class}",
        )
    if write_class == WRITE_CLASS_EPISODIC:
        return _admit_episodic(episode)
    if write_class == WRITE_CLASS_MARKET_ACTUALS:
        return _admit_market_actuals(payload)
    if write_class == WRITE_CLASS_OPINION:
        return _admit_opinion(
            payload,
            provenance_source=provenance_source,
            actor_id=actor_id,
        )
    if write_class == WRITE_CLASS_SEMANTIC_FACT:
        return _admit_semantic_fact(
            payload,
            independent_evidence_count=independent_evidence_count,
            independently_verified=independently_verified,
            operator_promote=operator_promote,
        )
    return _admit_procedural_flag(
        sample_count=sample_count,
        eval_gate_passed=eval_gate_passed,
        min_samples=min_samples,
    )


def require_memory_write(
    *,
    persist_required: bool = True,
    **kwargs: Any,
) -> MemoryWriteDecision:
    """Return an admitted decision or raise. Re-raises unchanged #1124 errors."""
    decision = admit_memory_write(**kwargs)
    if not decision.admitted:
        if decision.cause is not None:
            raise decision.cause
        raise MemoryWriteAdmissionError(
            decision.reason or "memory write rejected",
            error_code=decision.error_code or ERROR_UNKNOWN_CLASS,
            write_class=decision.write_class,
        )
    if persist_required and not decision.persist:
        raise MemoryWriteAdmissionError(
            "admitted candidate cannot persist; no store exists for this class",
            error_code=ERROR_PERSIST_FORBIDDEN,
            write_class=decision.write_class,
        )
    return decision


def require_episodic_write(episode: Any) -> MemoryWriteDecision:
    return require_memory_write(
        write_class=WRITE_CLASS_EPISODIC,
        episode=episode,
        persist_required=True,
    )


def require_market_actuals_write(payload: Mapping[str, Any]) -> MemoryWriteDecision:
    return require_memory_write(
        write_class=WRITE_CLASS_MARKET_ACTUALS,
        payload=payload,
        persist_required=True,
    )


def require_opinion_write(
    payload: Mapping[str, Any],
    *,
    provenance_source: str = PROVENANCE_SOURCE_USER_FEEDBACK,
    actor_id: Optional[str] = None,
) -> Tuple[MemoryWriteDecision, Dict[str, Any]]:
    decision = require_memory_write(
        write_class=WRITE_CLASS_OPINION,
        payload=payload,
        provenance_source=provenance_source,
        actor_id=actor_id,
        persist_required=True,
    )
    return decision, decision.stamped_payload(payload)


__all__ = [
    "ERROR_FACT_OPINION_MIX",
    "ERROR_FORGED_PROVENANCE",
    "ERROR_INVALID_EPISODE",
    "ERROR_INVALID_PROVENANCE",
    "ERROR_PERSIST_FORBIDDEN",
    "ERROR_PROCEDURAL_EVAL_GATE_UNMET",
    "ERROR_PROCEDURAL_MIN_SAMPLES_INVALID",
    "ERROR_PROCEDURAL_SAMPLE_THRESHOLD_UNMET",
    "ERROR_SEMANTIC_UNVERIFIED",
    "ERROR_SOUL_OR_OVERSIZE",
    "ERROR_UNKNOWN_CLASS",
    "MemoryWriteAdmissionError",
    "MemoryWriteDecision",
    "SEMANTIC_FACT_MIN_INDEPENDENT_EVIDENCE",
    "WRITE_CLASSES",
    "WRITE_CLASS_EPISODIC",
    "WRITE_CLASS_MARKET_ACTUALS",
    "WRITE_CLASS_OPINION",
    "WRITE_CLASS_PROCEDURAL_FLAG",
    "WRITE_CLASS_SEMANTIC_FACT",
    "admit_memory_write",
    "require_episodic_write",
    "require_market_actuals_write",
    "require_memory_write",
    "require_opinion_write",
]
