# -*- coding: utf-8 -*-
"""Registry facade for the single config resolve package.

Registration metadata remains owned by :mod:`src.core.config_registry` and its
partitioned parts. This module is a stable import path for resolve-side callers
so they do not open a second key catalog or bypass the unregistered-key guard.
"""

from __future__ import annotations

from src.core.config_registry import (
    LLM_CHANNEL_FIELD_KEY_RE,
    SCHEMA_VERSION,
    build_schema_response,
    evaluate_config_conditions,
    get_category_definitions,
    get_contract_field_definitions,
    get_field_definition,
    get_registered_field_keys,
)

__all__ = [
    "LLM_CHANNEL_FIELD_KEY_RE",
    "SCHEMA_VERSION",
    "build_schema_response",
    "evaluate_config_conditions",
    "get_category_definitions",
    "get_contract_field_definitions",
    "get_field_definition",
    "get_registered_field_keys",
]
