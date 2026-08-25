# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Allowlist for #1096 eval-fixture curator-grade ingest.

This module is the ingest/sidecar boundary only. It does not constrain
``EpisodeOutcomeLabels.manual_grade``, which remains an optional free-form
string so historical append-time values such as ``wrong`` still read.
"""

from __future__ import annotations

from typing import FrozenSet, Optional

from src.schemas.memory_write_guard import reject_memory_write_text


CURATOR_GRADE_ALLOWLIST: FrozenSet[str] = frozenset(
    {"fail", "harmful", "partial", "pass"}
)
CURATOR_GRADE_FIXTURE_VERSION = "curator_grade/1.0"


def normalize_curator_grade(value: Optional[str]) -> Optional[str]:
    """Canonicalize a sidecar/CLI curator grade.

    Blank values are absence (``None``), not a fabricated neutral grade.
    Unknown tokens fail closed. Do not use this helper to parse stored
    ``agent_episodes.outcome_labels_json``.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError("manual_grade must be a string")
    text = value.strip()
    if not text:
        return None
    reject_memory_write_text(
        text,
        field_name="manual_grade",
        max_length=64,
    )
    canonical = text.lower()
    if canonical not in CURATOR_GRADE_ALLOWLIST:
        raise ValueError(f"unsupported manual_grade: {value!r}")
    return canonical
