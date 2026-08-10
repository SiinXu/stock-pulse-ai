# -*- coding: utf-8 -*-
"""Strict types for an explicit, principal-scoped memory projection.

Layers in this foundation (honest naming):

- **Episodic**: recent, point-in-time analysis observations for one stock.
- **Outcome-pattern**: structured aggregates of provenance-linked *correct*
  outcomes, keyed by ``(signal, horizon)``. This is **not** free-text knowledge
  or embedding-store "semantic memory"; the type name and payload key are
  ``outcome_pattern`` / ``outcome_patterns`` so the contract matches the
  implementation.

Every field that can reach a projected payload is structurally constrained
here: identifiers match a fixed alphabet, timestamps are validated bounded UTC
instants, and outcome provenance is strictly typed. Free-form stored prose
therefore cannot be smuggled through a "string" field into a prompt boundary.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

MAX_AUTHORIZED_RECORDS = 200
MAX_EPISODIC_INJECTION = 3
MAX_OUTCOME_PATTERN_INJECTION = 3
MAX_SEMANTIC_INJECTION = MAX_OUTCOME_PATTERN_INJECTION
MIN_OUTCOME_PATTERN_EVIDENCE = 3
MIN_SEMANTIC_EVIDENCE = MIN_OUTCOME_PATTERN_EVIDENCE
SIGNALS = frozenset({"buy", "hold", "sell"})
OUTCOME_HORIZON_DAYS = frozenset({5, 20})
MAX_RECORD_ID = 2 ** 63 - 1

_INSTANT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_PRINCIPAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_MIN_INSTANT = datetime(2000, 1, 1, tzinfo=timezone.utc)
_MAX_INSTANT = datetime(2100, 1, 1, tzinfo=timezone.utc)


def parse_instant(name: str, value: Any) -> datetime:
    """Parse a bounded UTC instant, rejecting malformed or unbounded text."""
    if type(value) is not str or not _INSTANT_RE.match(value):
        raise ValueError(
            f"{name} must be a canonical UTC instant such as 2026-08-09T00:00:00Z"
        )
    try:
        parsed = datetime.strptime(value.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise ValueError(f"{name} is not a valid calendar instant") from exc
    parsed = parsed.replace(tzinfo=timezone.utc)
    if not _MIN_INSTANT <= parsed < _MAX_INSTANT:
        raise ValueError(f"{name} is outside the supported [2000, 2100) window")
    return parsed


def validate_principal_id(value: Any) -> str:
    if type(value) is not str or not _PRINCIPAL_RE.match(value):
        raise ValueError("principal_id must be a bounded identifier")
    return value


def validate_stock_code(value: Any) -> str:
    if type(value) is not str or not _STOCK_CODE_RE.match(value):
        raise ValueError("stock_code must be a bounded symbol identifier")
    return value


def _validate_record_id(name: str, value: Any) -> int:
    if type(value) is not int or not 0 < value <= MAX_RECORD_ID:
        raise ValueError(f"{name} must be a bounded positive integer")
    return value


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
        validate_principal_id(self.principal_id)
        _validate_record_id("analysis_history_id", self.analysis_history_id)
        validate_stock_code(self.stock_code)
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
        observed = parse_instant("observed_at", self.observed_at)
        if self.expires_at is not None:
            if parse_instant("expires_at", self.expires_at) <= observed:
                raise ValueError("expires_at must be after observed_at")
        outcome_fields = (self.outcome_id, self.outcome_horizon_days, self.evaluated_at, self.was_correct)
        if any(value is not None for value in outcome_fields) and any(
            value is None for value in outcome_fields
        ):
            raise ValueError("evaluated outcome provenance must be complete")
        if self.outcome_id is None:
            return
        _validate_record_id("outcome_id", self.outcome_id)
        if type(self.outcome_horizon_days) is not int or self.outcome_horizon_days not in OUTCOME_HORIZON_DAYS:
            raise ValueError("outcome horizon must be 5 or 20 days")
        if type(self.was_correct) is not bool:
            raise ValueError("was_correct must be a boolean")
        if parse_instant("evaluated_at", self.evaluated_at) < observed:
            raise ValueError("evaluated_at must not precede observed_at")


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
    outcome_pending_as_of: bool = False
    source: str = "structured"
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OutcomePatternEntry:
    """Structured outcome-pattern evidence for one (signal, horizon) group."""

    principal_id: str
    pattern_id: str
    stock_code: str
    signal_bias: str
    evidence_count: int
    source_history_ids: List[int]
    source_outcome_ids: List[int]
    horizon_days: int
    evaluated_through: str
    sufficient_evidence: bool
    source: str = "structured"
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


SemanticMemoryEntry = OutcomePatternEntry


@dataclass
class LayeredMemoryBundle:
    principal_id: str
    as_of: str
    episodic: List[EpisodicMemoryEntry] = field(default_factory=list)
    outcome_patterns: List[OutcomePatternEntry] = field(default_factory=list)
    vector_used: bool = False
    truncated: bool = False

    @property
    def semantic(self) -> List[OutcomePatternEntry]:
        return self.outcome_patterns

    @semantic.setter
    def semantic(self, value: List[OutcomePatternEntry]) -> None:
        self.outcome_patterns = value

    @property
    def source_history_ids(self) -> List[int]:
        return sorted({entry.analysis_history_id for entry in self.episodic} | {
            source_id for entry in self.outcome_patterns for source_id in entry.source_history_ids
        })
