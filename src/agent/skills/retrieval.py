# -*- coding: utf-8 -*-
"""Catalog-description skill retrieval (Issue #1123 Slice A).

``retrieve_skills`` returns ranked catalog IDs. SkillRouter owns selection
(including empty-match fallback to the default router set). SkillManager
renders those IDs. This module is not a second instruction path, not the
#1118 procedural store, and not #1091 tool scoring.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.agent.memory_vector import HashingVectorIndex, VectorDocument
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

SKILL_RETRIEVAL_K_DEFAULT = 0
SKILL_RETRIEVAL_K_HARD_CAP = 8
RETRIEVED_SKILLS_META_KEY = "retrieved_skill_ids"

_POSITIVE_SCORE_EPS = 1e-12
_PRIOR_WEIGHT_MAX = 2.0


def resolve_skill_retrieval_k(config: Any = None) -> int:
    """Return the configured retrieval K from the typed int contract.

    0 disables retrieval. ``bool``, ``float``, strings, and other non-ints are
    rejected (disabled) rather than coerced. Values above the hard cap clamp.
    Env loading uses ``parse_env_int``; this guard is the runtime contract.
    """
    if config is None:
        return SKILL_RETRIEVAL_K_DEFAULT
    raw = getattr(config, "agent_skill_retrieval_k", SKILL_RETRIEVAL_K_DEFAULT)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return SKILL_RETRIEVAL_K_DEFAULT
    if raw <= 0:
        return 0
    if raw > SKILL_RETRIEVAL_K_HARD_CAP:
        return SKILL_RETRIEVAL_K_HARD_CAP
    return raw


def skill_catalog_text(skill: Any) -> str:
    """Build the coarse-match document for one catalog Skill."""
    parts: List[str] = []
    for value in (
        getattr(skill, "description", "") or "",
        getattr(skill, "display_name", "") or "",
    ):
        text = str(value).strip()
        if text:
            parts.append(text)
    aliases = getattr(skill, "aliases", None) or []
    if isinstance(aliases, str):
        aliases = [aliases]
    for alias in aliases:
        text = str(alias).strip()
        if text:
            parts.append(text)
    regimes = getattr(skill, "market_regimes", None) or []
    if isinstance(regimes, str):
        regimes = [regimes]
    for regime in regimes:
        text = str(regime).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def build_skill_retrieval_query(ctx: Any, regime: Optional[str] = None) -> str:
    """Assemble a secret-free retrieval query from the shared AgentContext."""
    parts: List[str] = []
    for value in (
        getattr(ctx, "query", "") or "",
        getattr(ctx, "stock_name", "") or "",
        regime or "",
    ):
        text = str(value).strip()
        if text:
            parts.append(text)
    meta = getattr(ctx, "meta", None) or {}
    if isinstance(meta, Mapping):
        for key in ("user_query", "analysis_query"):
            extra = meta.get(key)
            if isinstance(extra, str) and extra.strip():
                parts.append(extra.strip())
    return " ".join(parts)


def _bound_k(k: Any) -> int:
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        return 0
    return min(k, SKILL_RETRIEVAL_K_HARD_CAP)


def _valid_prior_weight(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    weight = float(value)
    if not math.isfinite(weight) or weight <= 0.0 or weight > _PRIOR_WEIGHT_MAX:
        return None
    return weight


def retrieve_skills(
    query: str,
    catalog: Optional[Iterable[Any]],
    *,
    k: int,
    performance_prior: Optional[Mapping[str, float]] = None,
) -> List[str]:
    """Return top-K skill IDs by description match plus an optional prior.

    Empty catalog, empty/whitespace query, invalid/non-positive k, or all-zero
    cosine scores return an empty list. SkillRouter falls back to the default
    router set; this function never returns the full catalog as a fallback.
    """
    bound_k = _bound_k(k)
    if bound_k <= 0:
        return []

    documents: List[VectorDocument] = []
    seen: set[str] = set()
    for skill in catalog or []:
        skill_id = str(getattr(skill, "name", "") or "").strip()
        if not skill_id or skill_id in seen:
            continue
        text = skill_catalog_text(skill)
        if not text:
            continue
        seen.add(skill_id)
        documents.append(VectorDocument(doc_id=skill_id, text=text, meta={}))

    if not documents:
        return []

    query_text = str(query or "").strip()
    if not query_text:
        return []

    index = HashingVectorIndex()
    index.add_many(documents)
    ranked = index.query(query_text, top_k=len(documents))
    scored: List[Tuple[str, float]] = []
    for doc, cosine in ranked:
        try:
            score = float(cosine)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(score):
            continue
        if performance_prior:
            weight = _valid_prior_weight(performance_prior.get(doc.doc_id))
            if weight is not None:
                score *= weight
        if score > _POSITIVE_SCORE_EPS:
            scored.append((doc.doc_id, score))
    if not scored:
        return []
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [skill_id for skill_id, _score in scored[:bound_k]]


def load_optional_skill_performance_prior(
    catalog: Optional[Iterable[Any]],
    *,
    memory: Any = None,
) -> Dict[str, float]:
    """Return finite bounded priors from an already-injected AgentMemory.

    Does not construct AgentMemory or open BacktestService. Missing, disabled,
    or insufficiently sampled entries stay omitted (neutral). Invalid win-rate
    values are dropped rather than coerced.
    """
    if memory is None or not getattr(memory, "enabled", False):
        return {}
    prior: Dict[str, float] = {}
    try:
        for skill in catalog or []:
            skill_id = str(getattr(skill, "name", "") or "").strip()
            if not skill_id:
                continue
            perf = memory.get_skill_performance(skill_id)
            if not isinstance(perf, Mapping) or not perf.get("sufficient_samples"):
                continue
            win_rate = perf.get("win_rate")
            if isinstance(win_rate, bool) or not isinstance(win_rate, (int, float)):
                continue
            rate = float(win_rate)
            if not math.isfinite(rate) or rate < 0.0 or rate > 1.0:
                continue
            weight = _valid_prior_weight(0.5 + rate)
            if weight is None:
                continue
            prior[skill_id] = weight
    except Exception as exc:  # broad-exception: fallback_recorded - prior is optional.
        log_safe_exception(
            logger,
            "Optional skill performance prior unavailable; using description match only",
            exc,
            error_code="agent_skill_retrieval_prior_failed",
            level=logging.DEBUG,
        )
        return {}
    return prior


def record_retrieved_skill_ids(ctx: Any, skill_ids: Sequence[str]) -> None:
    """Store a bounded, secret-free ID list on the shared run-local ctx.meta.

    Only the SkillRouter retrieval path should call this. Explicit
    ``skills_requested`` and manual ``AGENT_SKILLS`` are not retrieved.
    """
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return
    bounded: List[str] = []
    for skill_id in skill_ids:
        cleaned = str(skill_id).strip() if isinstance(skill_id, str) else ""
        if not cleaned or cleaned in bounded:
            continue
        bounded.append(cleaned)
        if len(bounded) >= SKILL_RETRIEVAL_K_HARD_CAP:
            break
    meta[RETRIEVED_SKILLS_META_KEY] = bounded
