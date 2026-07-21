# -*- coding: utf-8 -*-
"""Shared sanitization for model-authored Agent dashboard payloads."""

from __future__ import annotations

from typing import Any, Dict


RESERVED_EXPLANATION_FIELD = "agent_disagreement_explanation"


def has_reserved_explanation_field(payload: Any) -> bool:
    """Return whether a parsed dashboard contains a model-owned reserved field."""
    if not isinstance(payload, dict):
        return False
    if RESERVED_EXPLANATION_FIELD in payload:
        return True
    nested = payload.get("dashboard")
    return isinstance(nested, dict) and RESERVED_EXPLANATION_FIELD in nested


def sanitize_agent_dashboard_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove fields reserved for deterministic post-processing.

    Both supported forged locations are removed at the shared LLM dashboard
    boundary. The input mapping and nested dashboard mapping are not mutated.
    """
    sanitized = dict(payload)
    sanitized.pop(RESERVED_EXPLANATION_FIELD, None)

    nested = sanitized.get("dashboard")
    if isinstance(nested, dict):
        nested = dict(nested)
        nested.pop(RESERVED_EXPLANATION_FIELD, None)
        sanitized["dashboard"] = nested
    return sanitized


__all__ = [
    "RESERVED_EXPLANATION_FIELD",
    "has_reserved_explanation_field",
    "sanitize_agent_dashboard_payload",
]
