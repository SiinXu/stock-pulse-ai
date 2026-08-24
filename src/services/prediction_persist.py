# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persist verifiable PredictionRecord drafts after analysis finalize (Issue #1101).

A3 under Epic #1107. Extraction stays pure in ``prediction_extractor``; this
module is the only production writer of pending ``agent_predictions`` rows.

Idempotency relies on the store primary key: the same run/symbol is projected
to a stable ``prediction_id``, and ``insert_pending`` does not overwrite on
conflict. Failures are logged and never raised to analysis callers.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from typing import Any, Dict, Mapping, Optional, Tuple

from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_prediction import AgentPredictionInsert, AgentPredictionRecord
from src.services.prediction_extractor import PredictionExtractionResult
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

PREDICTION_PERSIST_ERROR_CODE = "prediction_persist_failed"
_PREDICTION_ID_MAX_LEN = 128


def prediction_id_for_run(run_id: str, symbol: str = "") -> str:
    """Return a stable prediction_id so re-finalize hits the store PK."""
    token = str(run_id or "").strip()
    code = str(symbol or "").strip()
    parts = [part for part in (token, code) if part]
    candidate = "pred-" + "-".join(parts) if parts else ""
    if (
        candidate
        and len(candidate) <= _PREDICTION_ID_MAX_LEN
        and not any(char.isspace() for char in candidate)
    ):
        return candidate
    digest = hashlib.sha256(f"{token}\n{code}".encode("utf-8")).hexdigest()[:32]
    return f"pred-{digest}"


def persist_verifiable_prediction_draft(
    extraction: Optional[PredictionExtractionResult],
    *,
    repo: Optional[AgentPredictionRepository] = None,
    error_code: str = PREDICTION_PERSIST_ERROR_CODE,
    context: Optional[Mapping[str, Any]] = None,
) -> Optional[Tuple[bool, AgentPredictionRecord]]:
    """Insert one pending row for a verifiable draft. Never raises."""
    safe_context: Dict[str, Any] = dict(context or {})
    try:
        if extraction is None or not extraction.verifiable or extraction.record is None:
            return None
        record = extraction.record
        if record.status != "pending":
            return None
        fields = AgentPredictionInsert.from_prediction_record(record)
        stable_id = prediction_id_for_run(record.run_id, record.symbol)
        if stable_id != fields.prediction_id:
            fields = replace(fields, prediction_id=stable_id)
        safe_context.setdefault("prediction_id", fields.prediction_id)
        safe_context.setdefault("run_id", fields.run_id)
        writer = repo if repo is not None else AgentPredictionRepository()
        created, stored = writer.insert_pending(fields)
        return created, stored
    except Exception as exc:  # broad-exception: fallback_recorded - persist must not abort analysis
        log_safe_exception(
            logger,
            "Prediction draft persist failed",
            exc,
            error_code=error_code or PREDICTION_PERSIST_ERROR_CODE,
            level=logging.WARNING,
            context=safe_context,
        )
        return None


__all__ = [
    "PREDICTION_PERSIST_ERROR_CODE",
    "persist_verifiable_prediction_draft",
    "prediction_id_for_run",
]
