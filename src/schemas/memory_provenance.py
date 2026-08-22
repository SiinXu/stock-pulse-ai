# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Server-stamped provenance for governed memory writes (#1124 DAG-3).

The server, not the client, stamps ``provenance_source`` and optional
``actor_id`` on persisted memory rows. Transport ``source`` (``web`` / ``api``)
is a channel field and is not provenance. Client-supplied provenance keys are
rejected, not ignored or stripped.

This module does not add product feedback APIs (#1105), layered store/UX
(#1118), forgetting (#1119), or multi-tenant identity (#230).
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Mapping, Optional

from src.schemas.approvals import LOCAL_ADMIN_OWNER

PROVENANCE_SOURCE_SYSTEM_RESOLVE = "system_resolve"
PROVENANCE_SOURCE_USER_FEEDBACK = "user_feedback"
PROVENANCE_SOURCE_OPERATOR = "operator"

PROVENANCE_SOURCE_VALUES: FrozenSet[str] = frozenset(
    {
        PROVENANCE_SOURCE_SYSTEM_RESOLVE,
        PROVENANCE_SOURCE_USER_FEEDBACK,
        PROVENANCE_SOURCE_OPERATOR,
    }
)

CLIENT_PROVENANCE_KEYS: FrozenSet[str] = frozenset(
    {
        "provenance_source",
        "actor_id",
        "memory_source",
        "provenance",
    }
)

FEEDBACK_ACTOR_ID = LOCAL_ADMIN_OWNER
PROVENANCE_SOURCE_MAX_LENGTH = 32
ACTOR_ID_MAX_LENGTH = 128


class MemoryProvenanceError(ValueError):
    """Raised when a memory write is missing a stamp or carries a client spoof."""


def reject_client_provenance_keys(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Reject client-supplied provenance stamps and spoofed transport values."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    hits = tuple(sorted(str(key) for key in payload if str(key) in CLIENT_PROVENANCE_KEYS))
    if hits:
        raise MemoryProvenanceError(
            "client-supplied provenance is rejected: " + ", ".join(hits)
        )
    source = payload.get("source")
    if isinstance(source, str) and source in PROVENANCE_SOURCE_VALUES:
        raise MemoryProvenanceError(
            "transport source cannot carry provenance values"
        )
    return payload


def stamp_memory_provenance(
    *,
    provenance_source: str,
    actor_id: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Return the server-only provenance pair. Never read these from a request body."""
    if provenance_source not in PROVENANCE_SOURCE_VALUES:
        raise MemoryProvenanceError(
            f"unknown provenance_source: {provenance_source}"
        )
    if len(provenance_source) > PROVENANCE_SOURCE_MAX_LENGTH:
        raise MemoryProvenanceError("provenance_source exceeds column width")
    stamped_actor: Optional[str] = None
    if actor_id is not None:
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise MemoryProvenanceError("actor_id must be a non-empty string")
        if len(actor_id) > ACTOR_ID_MAX_LENGTH:
            raise MemoryProvenanceError(
                f"actor_id must be at most {ACTOR_ID_MAX_LENGTH} characters"
            )
        stamped_actor = actor_id
    return {
        "provenance_source": provenance_source,
        "actor_id": stamped_actor,
    }


def require_persisted_provenance(
    fields: Mapping[str, Any],
    *,
    expected_source: str,
    expected_actor_id: Optional[str] = None,
) -> Mapping[str, Any]:
    """Fail closed when a persist mapping is missing or spoofing the server stamp."""
    if not isinstance(fields, Mapping):
        raise TypeError("fields must be a mapping")
    if expected_source not in PROVENANCE_SOURCE_VALUES:
        raise MemoryProvenanceError(
            f"unknown provenance_source: {expected_source}"
        )
    source = fields.get("provenance_source")
    if source is None:
        raise MemoryProvenanceError("persist requires provenance_source")
    if source != expected_source:
        raise MemoryProvenanceError(
            f"provenance_source must be {expected_source}"
        )
    actor_id = fields.get("actor_id")
    if actor_id != expected_actor_id:
        raise MemoryProvenanceError("actor_id is not the server stamp")
    return fields


def apply_server_provenance(
    fields: Mapping[str, Any],
    *,
    provenance_source: str,
    actor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Reject client stamps, then attach the server stamp for this write path."""
    reject_client_provenance_keys(fields)
    out = dict(fields)
    out.update(
        stamp_memory_provenance(
            provenance_source=provenance_source,
            actor_id=actor_id,
        )
    )
    return out


__all__ = [
    "ACTOR_ID_MAX_LENGTH",
    "CLIENT_PROVENANCE_KEYS",
    "FEEDBACK_ACTOR_ID",
    "MemoryProvenanceError",
    "PROVENANCE_SOURCE_MAX_LENGTH",
    "PROVENANCE_SOURCE_OPERATOR",
    "PROVENANCE_SOURCE_SYSTEM_RESOLVE",
    "PROVENANCE_SOURCE_USER_FEEDBACK",
    "PROVENANCE_SOURCE_VALUES",
    "apply_server_provenance",
    "reject_client_provenance_keys",
    "require_persisted_provenance",
    "stamp_memory_provenance",
]
