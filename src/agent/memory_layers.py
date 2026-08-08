# -*- coding: utf-8 -*-
"""Layer contracts for agent long-term memory (episodic + semantic).

Short-term working memory continues to live in ``AgentContext`` / prefetched
data. Long-term user preference profiles are intentionally deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# Minimum evidence count before semantic patterns may influence confidence
# calibration language. Below this threshold summaries stay neutral.
MIN_SEMANTIC_EVIDENCE = 3

# Caps for prompt injection (keep context small and low-sensitivity)
MAX_EPISODIC_INJECTION = 3
MAX_SEMANTIC_INJECTION = 3
MAX_SUMMARY_CHARS = 240
MAX_STOCK_CODES_IN_SEMANTIC = 5


@dataclass
class EpisodicMemoryEntry:
    """One past analysis episode, optionally linked to AnalysisHistory."""

    stock_code: str = ""
    date: str = ""
    signal: str = ""
    sentiment_score: int = 50
    price_at_analysis: float = 0.0
    outcome_5d: Optional[float] = None
    outcome_20d: Optional[float] = None
    was_correct: Optional[bool] = None
    summary: str = ""
    analysis_history_id: Optional[int] = None
    source: str = "structured"  # structured | vector
    score: float = 0.0


@dataclass
class SemanticMemoryEntry:
    """A cross-episode pattern distilled from multiple analyses."""

    pattern_id: str = ""
    summary: str = ""
    evidence_count: int = 0
    stock_codes: List[str] = field(default_factory=list)
    signal_bias: str = ""
    avg_sentiment: float = 50.0
    source: str = "structured"  # structured | vector
    score: float = 0.0
    sufficient_evidence: bool = False


@dataclass
class LayeredMemoryBundle:
    """Combined retrieval result for prompt injection."""

    episodic: List[EpisodicMemoryEntry] = field(default_factory=list)
    semantic: List[SemanticMemoryEntry] = field(default_factory=list)
    vector_used: bool = False
