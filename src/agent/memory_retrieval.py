# -*- coding: utf-8 -*-
"""Pure projection over caller-authorized, principal-scoped memory records."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Dict, List, Sequence, Tuple

from src.agent.memory_layers import (
    MAX_AUTHORIZED_RECORDS,
    MAX_EPISODIC_INJECTION,
    MAX_SEMANTIC_INJECTION,
    MIN_SEMANTIC_EVIDENCE,
    EpisodicMemoryEntry,
    LayeredMemoryBundle,
    MemoryObservation,
    SemanticMemoryEntry,
    parse_instant,
    validate_principal_id,
    validate_stock_code,
)


@dataclass(frozen=True)
class _Evidence:
    """One fully-provenanced correct outcome eligible for semantic grouping."""

    analysis_history_id: int
    outcome_id: int
    evaluated_at: str
    stock_code: str


class AuthorizedMemoryProjector:
    """Project records already authorized by a lifecycle/consent owner.

    This class never reads storage, infers ownership, caches records, persists
    derivatives, or injects a production prompt.

    The projection is point-in-time with respect to ``as_of``: records observed
    after ``as_of`` did not exist yet and are excluded, records already expired
    at ``as_of`` are excluded, and an evaluation dated after ``as_of`` has not
    happened yet, so it is withheld and cannot become semantic evidence.
    """

    def __init__(
        self,
        records: Sequence[MemoryObservation],
        *,
        principal_id: str,
        as_of: str,
        vector_enabled: bool = False,
    ) -> None:
        validate_principal_id(principal_id)
        as_of_instant = parse_instant("as_of", as_of)
        if len(records) > MAX_AUTHORIZED_RECORDS:
            raise ValueError("authorized record panel exceeds hard cap")
        if any(record.principal_id != principal_id for record in records):
            raise PermissionError("cross-principal record rejected")
        ids = [record.analysis_history_id for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate analysis_history_id")
        self.records = tuple(
            record for record in records
            if _is_visible_at(record, as_of_instant)
        )
        self.principal_id = principal_id
        self.as_of = as_of
        self.as_of_instant = as_of_instant
        self.vector_enabled = vector_enabled

    def retrieve_layered(
        self,
        *,
        stock_code: str,
        query: str = "",
        episodic_limit: int = MAX_EPISODIC_INJECTION,
        semantic_limit: int = MAX_SEMANTIC_INJECTION,
    ) -> LayeredMemoryBundle:
        _bounded_limit("episodic_limit", episodic_limit, MAX_EPISODIC_INJECTION)
        _bounded_limit("semantic_limit", semantic_limit, MAX_SEMANTIC_INJECTION)
        validate_stock_code(stock_code)
        if type(query) is not str or len(query) > 500:
            raise ValueError("query is invalid or unbounded")
        selected = [record for record in self.records if record.stock_code == stock_code]
        selected.sort(
            key=lambda record: (parse_instant("observed_at", record.observed_at), record.analysis_history_id),
            reverse=True,
        )
        episodic = [self._episode(record) for record in selected[:episodic_limit]]
        semantic = self._semantic(selected)[:semantic_limit]
        vector_used = False
        if self.vector_enabled and query:
            episodic, episode_used = _vector_rank_episodes(episodic, query)
            semantic, semantic_used = _vector_rank_semantic(semantic, query)
            vector_used = episode_used or semantic_used
        return LayeredMemoryBundle(
            principal_id=self.principal_id,
            as_of=self.as_of,
            episodic=episodic,
            semantic=semantic,
            vector_used=vector_used,
            truncated=len(selected) > episodic_limit,
        )

    def _outcome_pending(self, record: MemoryObservation) -> bool:
        """True when the record's evaluation postdates ``as_of``."""
        if record.evaluated_at is None:
            return False
        return parse_instant("evaluated_at", record.evaluated_at) > self.as_of_instant

    def _episode(self, record: MemoryObservation) -> EpisodicMemoryEntry:
        pending = self._outcome_pending(record)
        return EpisodicMemoryEntry(
            principal_id=record.principal_id,
            analysis_history_id=record.analysis_history_id,
            stock_code=record.stock_code,
            observed_at=record.observed_at,
            expires_at=record.expires_at,
            signal=record.signal,
            sentiment_score=record.sentiment_score,
            price_at_analysis=record.price_at_analysis,
            outcome_id=None if pending else record.outcome_id,
            outcome_horizon_days=None if pending else record.outcome_horizon_days,
            evaluated_at=None if pending else record.evaluated_at,
            was_correct=None if pending else record.was_correct,
            outcome_pending_as_of=pending,
        )

    def _semantic(self, records: Sequence[MemoryObservation]) -> List[SemanticMemoryEntry]:
        # Group key is (signal, horizon): a pattern owns exactly one horizon, so
        # results measured over different horizons can never pool into one count.
        correct: Dict[Tuple[str, int], List[_Evidence]] = defaultdict(list)
        for record in records:
            outcome_id, horizon, evaluated_at = record.outcome_id, record.outcome_horizon_days, record.evaluated_at
            if record.was_correct is not True or self._outcome_pending(record):
                continue
            if outcome_id is None or horizon is None or evaluated_at is None:
                # Unreachable: MemoryObservation enforces all-or-none provenance.
                raise ValueError("evaluated outcome provenance must be complete")
            correct[(record.signal, horizon)].append(
                _Evidence(record.analysis_history_id, outcome_id, evaluated_at, record.stock_code)
            )
        patterns: List[SemanticMemoryEntry] = []
        for (signal, horizon), group in correct.items():
            history_ids = sorted(item.analysis_history_id for item in group)
            outcome_ids = sorted(item.outcome_id for item in group)
            evaluated_through = max(
                (item.evaluated_at for item in group),
                key=lambda value: parse_instant("evaluated_at", value),
            )
            patterns.append(SemanticMemoryEntry(
                principal_id=self.principal_id,
                pattern_id=f"evaluated:{signal}:{horizon}d:{'-'.join(map(str, history_ids))}",
                stock_code=group[0].stock_code,
                signal_bias=signal,
                evidence_count=len(group),
                source_history_ids=history_ids,
                source_outcome_ids=outcome_ids,
                horizon_days=horizon,
                evaluated_through=evaluated_through,
                sufficient_evidence=len(group) >= MIN_SEMANTIC_EVIDENCE,
                score=float(len(group)),
            ))
        patterns.sort(key=lambda entry: (entry.score, entry.pattern_id), reverse=True)
        return patterns


def format_layered_data(bundle: LayeredMemoryBundle) -> str:
    """Render typed records as bounded non-authoritative JSON data."""
    payload = {
        "principal_id": bundle.principal_id,
        "as_of": bundle.as_of,
        "source_history_ids": bundle.source_history_ids,
        "vector_used": bundle.vector_used,
        "truncated": bundle.truncated,
        "episodic": [entry.to_dict() for entry in bundle.episodic],
        "semantic": [entry.to_dict() for entry in bundle.semantic],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if len(encoded) > 20_000:
        raise ValueError("memory projection exceeds prompt-data cap")
    return (
        "[NON_AUTHORITATIVE_MEMORY_DATA]\n" + encoded +
        "\n[/NON_AUTHORITATIVE_MEMORY_DATA]"
    )


def _is_visible_at(record: MemoryObservation, as_of_instant: datetime) -> bool:
    if parse_instant("observed_at", record.observed_at) > as_of_instant:
        return False
    if record.expires_at is not None:
        if parse_instant("expires_at", record.expires_at) <= as_of_instant:
            return False
    return True


def _bounded_limit(name: str, value: int, maximum: int) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be within [1, {maximum}]")


def _vector_rank_episodes(entries: List[EpisodicMemoryEntry], query: str):
    from src.agent.memory_vector import HashingVectorIndex, VectorDocument
    index = HashingVectorIndex()
    for position, entry in enumerate(entries):
        index.add(VectorDocument(str(entry.analysis_history_id), f"{entry.stock_code} {entry.signal}", {"position": position}))
    ranked = index.query(query, top_k=len(entries))
    if not ranked:
        return entries, False
    return [replace(entries[int(doc.meta["position"])], source="vector", score=score) for doc, score in ranked], True


def _vector_rank_semantic(entries: List[SemanticMemoryEntry], query: str):
    from src.agent.memory_vector import HashingVectorIndex, VectorDocument
    index = HashingVectorIndex()
    for position, entry in enumerate(entries):
        index.add(VectorDocument(entry.pattern_id, f"{entry.stock_code} {entry.signal_bias}", {"position": position}))
    ranked = index.query(query, top_k=len(entries))
    if not ranked:
        return entries, False
    return [replace(entries[int(doc.meta["position"])], source="vector", score=score) for doc, score in ranked], True
