# -*- coding: utf-8 -*-
"""Extract corporate-event display contexts from alert trigger diagnostics (issue #241 Web)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence


def parse_diagnostics_object(diagnostics: Any) -> Optional[Dict[str, Any]]:
    if isinstance(diagnostics, dict):
        return dict(diagnostics)
    if not isinstance(diagnostics, str):
        return None
    text = diagnostics.strip()
    if not text or not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return dict(parsed) if isinstance(parsed, dict) else None


def extract_event_display_contexts(diagnostics: Any) -> Dict[str, Optional[Dict[str, Any]]]:
    payload = parse_diagnostics_object(diagnostics) or {}
    impact = payload.get("impact_context")
    event = payload.get("event_context")
    return {
        "impact_context": dict(impact) if isinstance(impact, dict) else None,
        "event_context": dict(event) if isinstance(event, dict) else None,
    }


def enrich_trigger_items_with_event_contexts(
    items: Sequence[Mapping[str, Any]],
    *,
    raw_diagnostics_by_id: Mapping[int, Any],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for item in items:
        row = dict(item)
        trigger_id = row.get("id")
        raw = raw_diagnostics_by_id.get(int(trigger_id)) if trigger_id is not None else None
        contexts = extract_event_display_contexts(raw)
        if contexts["impact_context"] is not None:
            row["impact_context"] = contexts["impact_context"]
        if contexts["event_context"] is not None:
            row["event_context"] = contexts["event_context"]
        enriched.append(row)
    return enriched
