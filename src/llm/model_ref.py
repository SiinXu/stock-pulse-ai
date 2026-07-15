# -*- coding: utf-8 -*-
"""Stable references to one runtime model on one LLM Connection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, unquote


MODEL_REF_PREFIX = "modelref:v1:"


@dataclass(frozen=True)
class ModelRef:
    """Connection-aware identity kept separate from the runtime route."""

    connection_id: str
    runtime_route: str


def canonicalize_connection_id(value: str) -> str:
    """Return the runtime identity used for one LLM Connection."""
    return str(value or "").strip().lower()


def is_model_ref(value: str) -> bool:
    """Return whether a value declares the versioned ModelRef namespace."""
    return str(value or "").strip().startswith(MODEL_REF_PREFIX)


def encode_model_ref(connection_id: str, runtime_route: str) -> str:
    """Encode a Connection and runtime route into a CSV-safe opaque value."""
    normalized_connection = canonicalize_connection_id(connection_id)
    normalized_route = str(runtime_route or "").strip()
    if not normalized_connection or not normalized_route:
        raise ValueError("connection_id and runtime_route are required")
    return (
        f"{MODEL_REF_PREFIX}"
        f"{quote(normalized_connection, safe='')}:"
        f"{quote(normalized_route, safe='')}"
    )


def decode_model_ref(value: str) -> Optional[ModelRef]:
    """Decode a ModelRef, or return ``None`` for a legacy runtime route."""
    normalized = str(value or "").strip()
    if not is_model_ref(normalized):
        return None
    payload = normalized[len(MODEL_REF_PREFIX):]
    encoded_connection, separator, encoded_route = payload.partition(":")
    if not separator:
        raise ValueError("invalid model_ref")
    connection_id = canonicalize_connection_id(unquote(encoded_connection))
    runtime_route = unquote(encoded_route).strip()
    if not connection_id or not runtime_route:
        raise ValueError("invalid model_ref")
    return ModelRef(connection_id=connection_id, runtime_route=runtime_route)


def normalize_model_ref(value: str) -> str:
    """Canonicalize a valid ModelRef while preserving legacy routes and invalid input."""
    normalized = str(value or "").strip()
    try:
        decoded = decode_model_ref(normalized)
    except ValueError:
        return normalized
    if decoded is None:
        return normalized
    return encode_model_ref(decoded.connection_id, decoded.runtime_route)
