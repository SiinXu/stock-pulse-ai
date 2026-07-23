# -*- coding: utf-8 -*-
"""Canonical presentation fields for persisted DecisionSignal assets."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Optional, TypedDict

from src.report_language import (
    SUPPORTED_REPORT_LANGUAGES,
    is_supported_report_language_value,
    normalize_report_language,
)
from src.schemas.decision_action import (
    DecisionAction,
    localize_action_label,
    normalize_decision_action,
)


DECISION_SIGNAL_PRESENTATION_SCHEMA_VERSION = "decision-signal-presentation-v1"


class DecisionSignalPresentation(TypedDict):
    """Renderer-ready fields whose action mirrors the top-level signal action."""

    schema_version: str
    action: DecisionAction
    label: str
    confidence: Optional[float]
    summary: Optional[str]
    risk: Optional[str]
    timestamp: Optional[str]


def build_decision_signal_presentation(
    item: Any,
    *,
    report_language: Optional[str] = None,
) -> Optional[DecisionSignalPresentation]:
    """Build a presentation model with direction derived only from top-level action."""

    if not isinstance(item, Mapping):
        return None
    nested = item.get("presentation")
    presentation = nested if isinstance(nested, Mapping) else {}
    action = normalize_decision_action(item.get("action"))
    if action is None:
        return None
    language = _presentation_language(
        item,
        presentation=presentation,
        action=action,
        requested=report_language,
    )
    label = localize_action_label(action, language)
    if label is None:
        return None
    return {
        "schema_version": DECISION_SIGNAL_PRESENTATION_SCHEMA_VERSION,
        "action": action,
        "label": label,
        "confidence": _optional_confidence(
            _presentation_value(presentation, "confidence", item.get("confidence"))
        ),
        "summary": _optional_display_text(
            _presentation_value(presentation, "summary", item.get("reason"))
        ),
        "risk": _optional_display_text(
            _presentation_value(presentation, "risk", item.get("risk_summary"))
        ),
        "timestamp": _optional_scalar_text(
            _presentation_value(presentation, "timestamp", item.get("created_at"))
        ),
    }


def _presentation_value(
    presentation: Mapping[str, Any],
    key: str,
    fallback: Any,
) -> Any:
    """Return a nested non-direction field when the presentation supplies it."""

    return presentation[key] if key in presentation else fallback


def _presentation_language(
    item: Mapping[str, Any],
    *,
    presentation: Mapping[str, Any],
    action: DecisionAction,
    requested: Optional[str],
) -> str:
    """Resolve presentation language from provenance or a matching stored label."""

    metadata = item.get("metadata")
    metadata_language = metadata.get("report_language") if isinstance(metadata, Mapping) else None
    for candidate in (requested, item.get("report_language"), metadata_language):
        if is_supported_report_language_value(candidate):
            return normalize_report_language(candidate)

    for stored_label in (
        _optional_scalar_text(presentation.get("label")),
        _optional_scalar_text(item.get("action_label")),
    ):
        if not stored_label:
            continue
        for language in SUPPORTED_REPORT_LANGUAGES:
            if stored_label == localize_action_label(action, language):
                return language
    return "zh"


def _optional_confidence(value: Any) -> Optional[float]:
    """Normalize a finite unit-interval confidence value or return none."""

    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        return None
    return parsed


def _optional_display_text(value: Any) -> Optional[str]:
    """Normalize optional scalar or structured display content into text."""

    if value in (None, "", [], {}):
        return None
    if isinstance(value, (list, tuple)):
        text = "；".join(str(item).strip() for item in value if str(item or "").strip())
    elif isinstance(value, Mapping):
        text = "；".join(
            f"{key}: {item}"
            for key, item in value.items()
            if str(key or "").strip() and str(item or "").strip()
        )
    else:
        text = str(value).strip()
    return text or None


def _optional_scalar_text(value: Any) -> Optional[str]:
    """Normalize an optional scalar presentation value into stripped text."""

    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None
