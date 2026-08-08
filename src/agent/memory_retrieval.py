# -*- coding: utf-8 -*-
"""Structured (and optional vector) retrieval for layered agent memory.

Default path uses SQL / keyword ranking over ``AnalysisHistory``. Vector
ranking is opt-in and silently falls back to structured results when the
vector index is empty or disabled.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

from src.agent.memory_layers import (
    MAX_SEMANTIC_INJECTION,
    MAX_STOCK_CODES_IN_SEMANTIC,
    MAX_SUMMARY_CHARS,
    MIN_SEMANTIC_EVIDENCE,
    EpisodicMemoryEntry,
    LayeredMemoryBundle,
    SemanticMemoryEntry,
)
from src.utils.sanitize import log_safe_exception, redact_sensitive_text

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]{2,}")
_PATH_RE = re.compile(r"(?:[A-Za-z]:)?(?:/|\\)[^\s]{3,}")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")


def sanitize_memory_text(text: str, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    """Produce a low-sensitivity summary fragment for prompt injection.

    Strips secrets via shared redaction, drops filesystem-like paths and
    emails, and hard-caps length.
    """
    if not text:
        return ""
    cleaned = redact_sensitive_text(str(text))
    cleaned = _PATH_RE.sub("[path]", cleaned)
    cleaned = _EMAIL_RE.sub("[email]", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 3].rstrip() + "..."
    return cleaned


def _tokens(text: str) -> set:
    if not text:
        return set()
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}


def _keyword_score(query: str, *parts: str) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    doc = set()
    for part in parts:
        doc |= _tokens(part or "")
    if not doc:
        return 0.0
    overlap = len(q & doc)
    return overlap / max(len(q), 1)


def _parse_raw_result(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            return {}
    return {}


def _record_to_episodic(record: Any, stock_code: str, source: str = "structured", score: float = 0.0) -> EpisodicMemoryEntry:
    raw_result = _parse_raw_result(getattr(record, "raw_result", None))
    signal = (
        raw_result.get("decision_type")
        or getattr(record, "operation_advice", None)
        or "hold"
    )
    price = raw_result.get("current_price")
    if price is None:
        price = 0.0
    created = getattr(record, "created_at", None)
    date_str = ""
    if created is not None and hasattr(created, "date"):
        try:
            date_str = created.date().isoformat()
        except Exception:  # broad-exception: optional_metadata - Unparseable timestamps become empty date strings.
            date_str = str(created)[:10]
    summary = sanitize_memory_text(
        getattr(record, "analysis_summary", None)
        or raw_result.get("summary")
        or ""
    )
    history_id = getattr(record, "id", None)
    return EpisodicMemoryEntry(
        stock_code=stock_code or getattr(record, "code", "") or "",
        date=date_str,
        signal=str(signal or "hold"),
        sentiment_score=int(getattr(record, "sentiment_score", 50) or 50),
        price_at_analysis=float(price or 0.0),
        was_correct=None,
        summary=summary,
        analysis_history_id=int(history_id) if history_id is not None else None,
        source=source,
        score=score,
    )


class StructuredMemoryRetriever:
    """Retrieve episodic and semantic memory from analysis history."""

    def __init__(self, vector_enabled: bool = False):
        self.vector_enabled = vector_enabled

    def fetch_history_records(
        self,
        stock_code: Optional[str] = None,
        limit: int = 20,
    ) -> List[Any]:
        """Load recent AnalysisHistory rows (optionally filtered by code)."""
        try:
            from src.storage import get_db

            db = get_db()
            if stock_code:
                return list(db.get_analysis_history(code=stock_code, limit=limit) or [])
            # Broad fetch for semantic distillation — prefer code-less API when present
            getter = getattr(db, "get_analysis_history", None)
            if getter is None:
                return []
            # Many implementations require code; try empty / None then give up
            try:
                return list(getter(code=None, limit=limit) or [])
            except TypeError:
                return list(getter(limit=limit) or [])
            except Exception:  # broad-exception: optional_metadata - Broad history APIs fail closed to empty.
                return []
        except Exception as exc:  # broad-exception: fallback_recorded - Storage failures yield no memory rows.
            log_safe_exception(
                logger,
                "Structured memory history fetch failed",
                exc,
                error_code="agent_memory_structured_fetch_failed",
                level=logging.DEBUG,
                context={"stock_code": stock_code},
            )
            return []

    def retrieve_episodic(
        self,
        stock_code: str,
        limit: int = 5,
        query: Optional[str] = None,
    ) -> List[EpisodicMemoryEntry]:
        """Return ranked episodic entries for a stock."""
        if not stock_code:
            return []
        records = self.fetch_history_records(stock_code=stock_code, limit=max(limit * 4, 20))
        if not records:
            return []

        entries = [_record_to_episodic(r, stock_code) for r in records]

        if query:
            for entry in entries:
                entry.score = _keyword_score(
                    query,
                    entry.signal,
                    entry.summary,
                    entry.stock_code,
                    entry.date,
                )
            # Prefer keyword hits, then recency (original order is newest-first typically)
            entries.sort(key=lambda e: (e.score, e.date or ""), reverse=True)
        else:
            for i, entry in enumerate(entries):
                entry.score = float(len(entries) - i)

        if self.vector_enabled and query:
            entries = self._rerank_episodic_with_vector(entries, query=query, limit=limit)
        return entries[:limit]

    def retrieve_semantic(
        self,
        query: Optional[str] = None,
        stock_code: Optional[str] = None,
        limit: int = MAX_SEMANTIC_INJECTION,
    ) -> List[SemanticMemoryEntry]:
        """Distill semantic patterns from recent history (cross-episode)."""
        # Prefer stock-scoped history; fall back to same-stock only to avoid
        # accidental cross-user leakage when multi-tenant DB is shared later.
        records = self.fetch_history_records(stock_code=stock_code, limit=50)
        if not records:
            return []

        # Pattern key: normalized signal
        buckets: Dict[str, List[Any]] = defaultdict(list)
        for record in records:
            raw = _parse_raw_result(getattr(record, "raw_result", None))
            signal = str(
                raw.get("decision_type")
                or getattr(record, "operation_advice", None)
                or "hold"
            ).strip().lower() or "hold"
            buckets[signal].append(record)

        patterns: List[SemanticMemoryEntry] = []
        for signal, group in buckets.items():
            codes: List[str] = []
            sentiments: List[float] = []
            summary_bits: List[str] = []
            for r in group:
                code = getattr(r, "code", None) or stock_code or ""
                if code and code not in codes:
                    codes.append(str(code))
                sentiments.append(float(getattr(r, "sentiment_score", 50) or 50))
                snippet = sanitize_memory_text(getattr(r, "analysis_summary", None) or "")
                if snippet and snippet not in summary_bits:
                    summary_bits.append(snippet)
            evidence = len(group)
            avg_sent = sum(sentiments) / len(sentiments) if sentiments else 50.0
            sufficient = evidence >= MIN_SEMANTIC_EVIDENCE
            # Neutral wording when sample size is low — do not overclaim
            if sufficient:
                summary = (
                    f"Across {evidence} past analyses, signal bias is '{signal}' "
                    f"(avg sentiment {avg_sent:.0f})."
                )
            else:
                summary = (
                    f"Limited evidence ({evidence} analyses) for signal '{signal}'; "
                    f"treat as neutral context only."
                )
            if summary_bits:
                summary = sanitize_memory_text(summary + " Example: " + summary_bits[0])
            else:
                summary = sanitize_memory_text(summary)

            score = float(evidence)
            if query:
                score += _keyword_score(query, signal, summary, " ".join(codes))

            patterns.append(
                SemanticMemoryEntry(
                    pattern_id=f"signal:{signal}",
                    summary=summary,
                    evidence_count=evidence,
                    stock_codes=codes[:MAX_STOCK_CODES_IN_SEMANTIC],
                    signal_bias=signal,
                    avg_sentiment=avg_sent,
                    source="structured",
                    score=score,
                    sufficient_evidence=sufficient,
                )
            )

        if self.vector_enabled and query:
            patterns = self._rerank_semantic_with_vector(patterns, query=query)

        patterns.sort(key=lambda p: p.score, reverse=True)
        return patterns[:limit]

    def retrieve_layered(
        self,
        stock_code: str,
        query: Optional[str] = None,
        episodic_limit: int = 3,
        semantic_limit: int = MAX_SEMANTIC_INJECTION,
    ) -> LayeredMemoryBundle:
        """Fetch both layers for prompt injection."""
        episodic = self.retrieve_episodic(stock_code, limit=episodic_limit, query=query)
        semantic = self.retrieve_semantic(
            query=query, stock_code=stock_code, limit=semantic_limit
        )
        vector_used = bool(self.vector_enabled) and any(
            e.source == "vector" for e in episodic
        )
        return LayeredMemoryBundle(
            episodic=episodic,
            semantic=semantic,
            vector_used=vector_used,
        )

    def _rerank_episodic_with_vector(
        self,
        entries: Sequence[EpisodicMemoryEntry],
        query: str,
        limit: int,
    ) -> List[EpisodicMemoryEntry]:
        try:
            from src.agent.memory_vector import HashingVectorIndex, VectorDocument

            index = HashingVectorIndex()
            for i, entry in enumerate(entries):
                text = " ".join(
                    [
                        entry.stock_code,
                        entry.signal,
                        entry.summary,
                        entry.date,
                    ]
                )
                index.add(
                    VectorDocument(
                        doc_id=str(entry.analysis_history_id or i),
                        text=text,
                        meta={"index": i},
                    )
                )
            ranked = index.query(query, top_k=max(limit, len(entries)))
            if not ranked:
                return list(entries)
            out: List[EpisodicMemoryEntry] = []
            seen = set()
            for doc, score in ranked:
                idx = int(doc.meta.get("index", -1))
                if idx < 0 or idx in seen or idx >= len(entries):
                    continue
                seen.add(idx)
                item = entries[idx]
                item.score = float(score)
                item.source = "vector"
                out.append(item)
            # Append any leftover in original order
            for i, entry in enumerate(entries):
                if i not in seen:
                    out.append(entry)
            return out
        except Exception as exc:  # broad-exception: fallback_recorded - Vector rerank fails open to structured order.
            log_safe_exception(
                logger,
                "Vector episodic rerank failed; using structured ranking",
                exc,
                error_code="agent_memory_vector_episodic_failed",
                level=logging.DEBUG,
            )
            return list(entries)

    def _rerank_semantic_with_vector(
        self,
        patterns: Sequence[SemanticMemoryEntry],
        query: str,
    ) -> List[SemanticMemoryEntry]:
        try:
            from src.agent.memory_vector import HashingVectorIndex, VectorDocument

            index = HashingVectorIndex()
            for i, pattern in enumerate(patterns):
                index.add(
                    VectorDocument(
                        doc_id=pattern.pattern_id or str(i),
                        text=f"{pattern.signal_bias} {pattern.summary}",
                        meta={"index": i},
                    )
                )
            ranked = index.query(query, top_k=len(patterns))
            if not ranked:
                return list(patterns)
            out: List[SemanticMemoryEntry] = []
            seen = set()
            for doc, score in ranked:
                idx = int(doc.meta.get("index", -1))
                if idx < 0 or idx in seen or idx >= len(patterns):
                    continue
                seen.add(idx)
                item = patterns[idx]
                item.score = float(score) + item.evidence_count * 0.01
                item.source = "vector"
                out.append(item)
            for i, pattern in enumerate(patterns):
                if i not in seen:
                    out.append(pattern)
            return out
        except Exception as exc:  # broad-exception: fallback_recorded - Vector semantic rerank fails open to structured order.
            log_safe_exception(
                logger,
                "Vector semantic rerank failed; using structured ranking",
                exc,
                error_code="agent_memory_vector_semantic_failed",
                level=logging.DEBUG,
            )
            return list(patterns)


def format_layered_prompt_context(bundle: LayeredMemoryBundle) -> str:
    """Render a layered memory bundle into a prompt-safe block."""
    if not bundle.episodic and not bundle.semantic:
        return ""

    lines: List[str] = []
    if bundle.episodic:
        lines.append("[Memory: recent analysis history]")
        for entry in bundle.episodic:
            parts = [
                entry.date or "unknown_date",
                f"signal={entry.signal or 'unknown'}",
                f"sentiment={entry.sentiment_score}",
            ]
            if entry.price_at_analysis:
                parts.append(f"price={entry.price_at_analysis}")
            if entry.outcome_5d is not None:
                parts.append(f"outcome_5d={entry.outcome_5d}")
            if entry.outcome_20d is not None:
                parts.append(f"outcome_20d={entry.outcome_20d}")
            if entry.was_correct is not None:
                parts.append(f"was_correct={entry.was_correct}")
            if entry.summary:
                parts.append(f"note={entry.summary}")
            lines.append("- " + ", ".join(parts))

    if bundle.semantic:
        lines.append("[Memory: semantic patterns]")
        for pattern in bundle.semantic:
            evidence_tag = (
                "sufficient_evidence"
                if pattern.sufficient_evidence
                else "insufficient_evidence_neutral"
            )
            lines.append(
                f"- {pattern.summary} ({evidence_tag}, source={pattern.source})"
            )

    lines.append(
        "Use this memory as context only; do not copy it verbatim into the final answer."
    )
    return "\n".join(lines)
