# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Gate relative-value language unless it cites peer canvas fields (issue #1139).

Relative claims (peer premium/discount, cheaper than peers, peer median, …)
must cite structured canvas cells. Without a canvas — or without citations —
claims are downgraded rather than presented as grounded comparisons.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

POLICY_VERSION = "peer-relative-claim-policy-v1"

_RELATIVE_CLAIM_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bvs\.?\s+peers?\b",
        r"\bpeer\s+median\b",
        r"\bpeer\s+multiples?\b",
        r"\brelative\s+(to|vs\.?|versus)\b",
        r"\bcheaper\s+than\s+(peers?|industry|sector)\b",
        r"\bmore\s+expensive\s+than\s+(peers?|industry|sector)\b",
        r"\bundervalued\s+(vs\.?|versus|relative)\b",
        r"\bovervalued\s+(vs\.?|versus|relative)\b",
        r"\bpremium\s+to\s+(peers?|industry|sector)\b",
        r"\bdiscount\s+to\s+(peers?|industry|sector)\b",
        r"\bindustry\s+(pe|pb|multiple|median)\b",
        r"\bsector\s+(pe|pb|multiple|median)\b",
        r"同业",
        r"相对估值",
        r"相对同业",
        r"同业中位",
        r"较同行",
        r"高于同行",
        r"低于同行",
    )
)

_CITATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bcanvas\.[A-Za-z0-9_\[\]\.\-]+",
        r"\bcite:[A-Za-z0-9_@\.\-]+",
        r"\bcell:[A-Za-z0-9_@\.\-]+",
        r"\bpeer_canvas\b",
        r"\bpeer-valuation-canvas-v1\b",
        r"\bheatmap_cells\b",
        r"\brows\[\d+\]\.metrics\.[A-Za-z0-9_]+",
    )
)


def has_relative_value_language(text: str) -> bool:
    """Return whether free text makes a peer/relative valuation claim."""
    payload = str(text or "")
    if not payload.strip():
        return False
    return any(pattern.search(payload) for pattern in _RELATIVE_CLAIM_PATTERNS)


def extract_canvas_citations(text: str) -> list[str]:
    """Return citation tokens found in free text."""
    payload = str(text or "")
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _CITATION_PATTERNS:
        for match in pattern.finditer(payload):
            token = match.group(0)
            key = token.lower()
            if key not in seen:
                seen.add(key)
                found.append(token)
    return found


def canvas_is_usable(canvas: Optional[Mapping[str, Any]]) -> bool:
    """Return whether a canvas payload can ground relative claims."""
    if not isinstance(canvas, Mapping):
        return False
    schema = str(canvas.get("schema_version") or "")
    if schema and schema != "peer-valuation-canvas-v1":
        if not schema.startswith("peer-valuation-canvas"):
            return False
    rows = canvas.get("rows")
    if not isinstance(rows, Sequence) or not rows:
        return False
    status = str(canvas.get("status") or "")
    if status in {"invalid_request", "insufficient_peers"}:
        return False
    peer_rows = [
        row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("role") or "") == "peer"
    ]
    return bool(peer_rows)


def evaluate_relative_claims(
    *,
    text: str,
    canvas: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Evaluate whether relative-value language is grounded in a peer canvas."""
    relative = has_relative_value_language(text)
    citations = extract_canvas_citations(text)
    usable = canvas_is_usable(canvas)

    if not relative:
        return {
            "policy_version": POLICY_VERSION,
            "status": "ok",
            "relative_language": False,
            "canvas_present": usable,
            "citations": citations,
            "action": "none",
            "reason": "no_relative_claims",
            "confidence_adjustment": 0.0,
            "message": "No relative-value language detected.",
        }

    if not usable:
        return {
            "policy_version": POLICY_VERSION,
            "status": "downgraded",
            "relative_language": True,
            "canvas_present": False,
            "citations": citations,
            "action": "gate_relative_claims",
            "reason": "relative_claims_without_canvas",
            "confidence_adjustment": -0.25,
            "message": (
                "Relative-value claims require a peer valuation canvas; "
                "claims are downgraded without structured comparison fields."
            ),
        }

    if not citations:
        return {
            "policy_version": POLICY_VERSION,
            "status": "downgraded",
            "relative_language": True,
            "canvas_present": True,
            "citations": [],
            "action": "require_canvas_citation",
            "reason": "relative_claims_missing_canvas_citation",
            "confidence_adjustment": -0.15,
            "message": (
                "Relative-value claims must cite canvas cells "
                "(e.g. canvas.rows[0].metrics.pe_ratio or cite:pe_ratio@CODE)."
            ),
        }

    return {
        "policy_version": POLICY_VERSION,
        "status": "ok",
        "relative_language": True,
        "canvas_present": True,
        "citations": citations,
        "action": "allow_with_citations",
        "reason": "relative_claims_cite_canvas",
        "confidence_adjustment": 0.0,
        "message": "Relative-value claims cite peer canvas fields.",
    }
