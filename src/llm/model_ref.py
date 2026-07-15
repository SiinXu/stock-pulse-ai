# -*- coding: utf-8 -*-
"""Stable, opaque references to one model on one LLM connection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, unquote


MODEL_REF_PREFIX = "modelref:v1:"


@dataclass(frozen=True)
class ModelRef:
    """Connection-aware model identity kept separate from its runtime route."""

    connection_id: str
    runtime_route: str


def is_model_ref(value: str) -> bool:
    """Return whether a value declares the versioned ModelRef wire format."""
    return str(value or "").strip().startswith(MODEL_REF_PREFIX)


def encode_model_ref(connection_id: str, runtime_route: str) -> str:
    """Encode a connection and route into a versioned, CSV-safe opaque value."""
    normalized_connection = str(connection_id or "").strip()
    normalized_route = str(runtime_route or "").strip()
    if not normalized_connection or not normalized_route:
        raise ValueError("connection_id and runtime_route are required")
    return (
        f"{MODEL_REF_PREFIX}"
        f"{quote(normalized_connection, safe='')}:"
        f"{quote(normalized_route, safe='')}"
    )


def decode_model_ref(value: str) -> Optional[ModelRef]:
    """Decode a ModelRef, returning ``None`` for a legacy runtime route."""
    normalized = str(value or "").strip()
    if not is_model_ref(normalized):
        return None
    payload = normalized[len(MODEL_REF_PREFIX):]
    encoded_connection, separator, encoded_route = payload.partition(":")
    if not separator:
        raise ValueError("invalid model_ref")
    connection_id = unquote(encoded_connection).strip()
    runtime_route = unquote(encoded_route).strip()
    if not connection_id or not runtime_route:
        raise ValueError("invalid model_ref")
    return ModelRef(connection_id=connection_id, runtime_route=runtime_route)
