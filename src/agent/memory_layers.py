# -*- coding: utf-8 -*-
"""Strict types for an explicit, principal-scoped memory projection."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

MAX_AUTHORIZED_RECORDS = 200
MAX_EPISODIC_INJECTION = 3
MAX_SEMANTIC_INJECTION = 3
MIN_SEMANTIC_EVIDENCE = 3
SIGNALS = frozenset({"buy", "hold", "sell"})


@dataclass(frozen=True)
class MemoryObservation:
    principal_id: str
    analysis_history_id: int
    stock_code: str
    observed_at: str
    expires_at: Optional[str]
    signal: str
    sentiment_score: float
    price_at_analysis: float
    outcome_id: Optional[int] = None
    outcome_horizon_days: Optional[int] = None
    evaluated_at: Optional[str] = None
    was_correct: Optional[bool] = None

    def __post_init__(self) -> None:
        if not self.principal_id or len(self.principal_id) > 128:
            raise ValueError("principal_id is required and bounded")
        if type(self.analysis_history_id) is not int or self.analysis_history_id <= 0:
            raise ValueError("analysis_history_id must be positive")
        if not self.stock_code or len(self.stock_code) > 32:
            raise ValueError("stock_code is required and bounded")
        if self.signal not in SIGNALS:
            raise ValueError("signal must be buy, hold, or sell")
        for name, value, low, high in (
            ("sentiment_score", self.sentiment_score, 0.0, 100.0),
            ("price_at_analysis", self.price_at_analysis, 0.0, 1_000_000_000.0),
        ):
            if type(value) not in (int, float) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
            if not low <= float(value) <= high:
                raise ValueError(f"{name} is out of range")
        outcome_fields = (self.outcome_id, self.outcome_horizon_days, self.evaluated_at, self.was_correct)
        if any(value is not None for value in outcome_fields) and any(
            value is None for value in outcome_fields
        ):
            raise ValueError("evaluated outcome provenance must be complete")
        if self.outcome_horizon_days is not None and self.outcome_horizon_days not in {5, 20}:
            raise ValueError("outcome horizon must be 5 or 20 days")


@dataclass(frozen=True)
class EpisodicMemoryEntry:
    principal_id: str
    analysis_history_id: int
    stock_code: str
    observed_at: str
    expires_at: Optional[str]
    signal: str
    sentiment_score: float
    price_at_analysis: float
    outcome_id: Optional[int]
    outcome_horizon_days: Optional[int]
    evaluated_at: Optional[str]
    was_correct: Optional[bool]
    source: str = "structured"
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticMemoryEntry:
    principal_id: str
    pattern_id: str
    stock_code: str
    signal_bias: str
    evidence_count: int
    source_history_ids: List[int]
    source_outcome_ids: List[int]
    horizon_days: List[int]
    evaluated_through: str
    sufficient_evidence: bool
    source: str = "structured"
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LayeredMemoryBundle:
    principal_id: str
    episodic: List[EpisodicMemoryEntry] = field(default_factory=list)
    semantic: List[SemanticMemoryEntry] = field(default_factory=list)
    vector_used: bool = False
    truncated: bool = False

    @property
    def source_history_ids(self) -> List[int]:
        return sorted({entry.analysis_history_id for entry in self.episodic} | {
            source_id for entry in self.semantic for source_id in entry.source_history_ids
        })
