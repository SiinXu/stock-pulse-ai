# -*- coding: utf-8 -*-
"""Pure projection over caller-authorized, principal-scoped memory records."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from typing import Dict, List, Optional, Sequence

from src.agent.memory_layers import (
    MAX_AUTHORIZED_RECORDS,
    MAX_EPISODIC_INJECTION,
    MAX_SEMANTIC_INJECTION,
    MIN_SEMANTIC_EVIDENCE,
    EpisodicMemoryEntry,
    LayeredMemoryBundle,
    MemoryObservation,
    SemanticMemoryEntry,
)


class AuthorizedMemoryProjector:
    """Project records already authorized by a lifecycle/consent owner.

    This class never reads storage, infers ownership, caches records, persists
    derivatives, or injects a production prompt.
    """

    def __init__(
        self,
        records: Sequence[MemoryObservation],
        *,
        principal_id: str,
        as_of: str,
        vector_enabled: bool = False,
    ) -> None:
        if not principal_id or len(principal_id) > 128:
            raise ValueError("principal_id is required and bounded")
        if not as_of or len(as_of) > 64:
            raise ValueError("as_of is required and bounded")
        if len(records) > MAX_AUTHORIZED_RECORDS:
            raise ValueError("authorized record panel exceeds hard cap")
        if any(record.principal_id != principal_id for record in records):
            raise PermissionError("cross-principal record rejected")
        ids = [record.analysis_history_id for record in records]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate analysis_history_id")
        self.records = tuple(
            record for record in records
            if record.expires_at is None or record.expires_at > as_of
        )
        self.principal_id = principal_id
        self.as_of = as_of
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
        if not stock_code or len(stock_code) > 32 or len(query) > 500:
            raise ValueError("stock_code/query is invalid or unbounded")
        selected = [record for record in self.records if record.stock_code == stock_code]
        selected.sort(key=lambda record: (record.observed_at, record.analysis_history_id), reverse=True)
        episodic = [self._episode(record) for record in selected[:episodic_limit]]
        semantic = self._semantic(selected)[:semantic_limit]
        vector_used = False
        if self.vector_enabled and query:
            episodic, episode_used = _vector_rank_episodes(episodic, query)
            semantic, semantic_used = _vector_rank_semantic(semantic, query)
            vector_used = episode_used or semantic_used
        return LayeredMemoryBundle(
            principal_id=self.principal_id,
            episodic=episodic,
            semantic=semantic,
            vector_used=vector_used,
            truncated=len(selected) > episodic_limit,
        )

    def _episode(self, record: MemoryObservation) -> EpisodicMemoryEntry:
        return EpisodicMemoryEntry(
            principal_id=record.principal_id,
            analysis_history_id=record.analysis_history_id,
            stock_code=record.stock_code,
            observed_at=record.observed_at,
            expires_at=record.expires_at,
            signal=record.signal,
            sentiment_score=record.sentiment_score,
            price_at_analysis=record.price_at_analysis,
            outcome_id=record.outcome_id,
            outcome_horizon_days=record.outcome_horizon_days,
            evaluated_at=record.evaluated_at,
            was_correct=record.was_correct,
        )

    def _semantic(self, records: Sequence[MemoryObservation]) -> List[SemanticMemoryEntry]:
        correct: Dict[str, List[MemoryObservation]] = defaultdict(list)
        for record in records:
            if record.was_correct is True:
                correct[record.signal].append(record)
        patterns: List[SemanticMemoryEntry] = []
        for signal, group in correct.items():
            if not group:
                continue
            history_ids = sorted(record.analysis_history_id for record in group)
            outcome_ids = sorted(int(record.outcome_id) for record in group if record.outcome_id is not None)
            horizons = sorted({int(record.outcome_horizon_days) for record in group if record.outcome_horizon_days is not None})
            evaluated_through = max(record.evaluated_at or "" for record in group)
            patterns.append(SemanticMemoryEntry(
                principal_id=self.principal_id,
                pattern_id=f"evaluated:{signal}:{'-'.join(map(str, history_ids))}",
                stock_code=group[0].stock_code,
                signal_bias=signal,
                evidence_count=len(group),
                source_history_ids=history_ids,
                source_outcome_ids=outcome_ids,
                horizon_days=horizons,
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
