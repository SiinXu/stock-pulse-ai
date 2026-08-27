# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Admit structured layered-memory observations for durable persist (#1118).

Reuses #1119 ``require_memory_write`` and #1124 provenance / fact-opinion /
Soul-oversize contracts. This is not a semantic-fact or procedural store, not
a production prompt hook, and not user CRUD.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

from src.schemas.memory_fact_opinion import FactOpinionMixError, lock_fact_payload
from src.schemas.memory_provenance import (
    MemoryProvenanceError,
    PROVENANCE_SOURCE_SYSTEM_RESOLVE,
    reject_client_provenance_keys,
    stamp_memory_provenance,
)
from src.schemas.memory_write_guard import (
    MemoryWriteRejectedError,
    reject_memory_write_text,
)
from src.schemas.memory_write_policy import (
    WRITE_CLASS_MARKET_ACTUALS,
    require_memory_write,
)
from src.utils.sanitize import redact_sensitive_data

LAYERED_OBSERVATION_ALLOWED_KEYS = frozenset(
    {
        "principal_id",
        "analysis_history_id",
        "stock_code",
        "observed_at",
        "expires_at",
        "signal",
        "sentiment_score",
        "price_at_analysis",
        "outcome_id",
        "outcome_horizon_days",
        "evaluated_at",
        "was_correct",
    }
)

_STRING_FIELD_MAX_LENGTH = {
    "principal_id": 128,
    "stock_code": 32,
    "observed_at": 32,
    "expires_at": 32,
    "signal": 8,
    "evaluated_at": 32,
}

_REDACTED = "[REDACTED]"


class LayeredMemoryPersistError(ValueError):
    """Raised when a layered observation mapping cannot be persisted."""


def _reject_secret_or_pii_values(payload: Mapping[str, Any]) -> None:
    redacted = redact_sensitive_data(dict(payload))
    if not isinstance(redacted, dict):
        raise LayeredMemoryPersistError("layered observation payload cannot be redacted safely")
    for key, value in payload.items():
        if redacted.get(key) == _REDACTED:
            raise LayeredMemoryPersistError(
                f"layered observation field {key} contains secrets or PII"
            )
        if isinstance(value, str) and isinstance(redacted.get(key), str):
            if redacted[key] != value:
                raise LayeredMemoryPersistError(
                    f"layered observation field {key} contains secrets or PII"
                )


def _reject_soul_or_oversize_strings(payload: Mapping[str, Any]) -> None:
    for key, value in payload.items():
        if value is None or not isinstance(value, str):
            continue
        reject_memory_write_text(
            value,
            field_name=str(key),
            max_length=_STRING_FIELD_MAX_LENGTH.get(str(key), 200),
        )


def admit_layered_observation_mapping(
    payload: Mapping[str, Any],
    *,
    provenance_source: str = PROVENANCE_SOURCE_SYSTEM_RESOLVE,
    actor_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Optional[str]]]:
    """Reject spoofed provenance, secrets, and mixed opinion keys, then stamp.

    Returns a server-stamped mapping. Callers in ``src.agent`` / ``src.services``
    construct ``MemoryObservation``; this schema module must not import
    ``src.agent``.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("layered observation payload must be a mapping")
    try:
        reject_client_provenance_keys(payload)
        lock_fact_payload(payload)
        extra = tuple(
            sorted(str(key) for key in payload if str(key) not in LAYERED_OBSERVATION_ALLOWED_KEYS)
        )
        if extra:
            raise LayeredMemoryPersistError(
                "layered observation payload has forbidden keys: " + ", ".join(extra)
            )
        _reject_soul_or_oversize_strings(payload)
        _reject_secret_or_pii_values(payload)
        decision = require_memory_write(
            write_class=WRITE_CLASS_MARKET_ACTUALS,
            payload=payload,
            persist_required=True,
        )
    except (
        FactOpinionMixError,
        MemoryProvenanceError,
        MemoryWriteRejectedError,
        TypeError,
        LayeredMemoryPersistError,
    ):
        raise
    stamp = stamp_memory_provenance(
        provenance_source=provenance_source or decision.provenance_source or PROVENANCE_SOURCE_SYSTEM_RESOLVE,
        actor_id=actor_id if actor_id is not None else decision.actor_id,
    )
    admitted = {
        "principal_id": payload["principal_id"],
        "analysis_history_id": payload["analysis_history_id"],
        "stock_code": payload["stock_code"],
        "observed_at": payload["observed_at"],
        "expires_at": payload.get("expires_at"),
        "signal": payload["signal"],
        "sentiment_score": payload["sentiment_score"],
        "price_at_analysis": payload["price_at_analysis"],
        "outcome_id": payload.get("outcome_id"),
        "outcome_horizon_days": payload.get("outcome_horizon_days"),
        "evaluated_at": payload.get("evaluated_at"),
        "was_correct": payload.get("was_correct"),
        "provenance_source": stamp["provenance_source"],
        "actor_id": stamp["actor_id"],
    }
    return admitted, stamp


def observation_to_persist_mapping(observation: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the admitted persist fields without client provenance keys."""
    if not isinstance(observation, Mapping):
        raise TypeError("layered observation payload must be a mapping")
    payload = dict(observation)
    payload.pop("provenance_source", None)
    payload.pop("actor_id", None)
    return payload


__all__ = [
    "LAYERED_OBSERVATION_ALLOWED_KEYS",
    "LayeredMemoryPersistError",
    "admit_layered_observation_mapping",
    "observation_to_persist_mapping",
]
