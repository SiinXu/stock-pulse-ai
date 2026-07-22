# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Configurable, low-sensitivity guards for Agent runtime execution."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.utils.sanitize import sanitize_diagnostic_text


DEFAULT_TOOL_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_IDENTICAL_TOOL_CALLS = 3
DEFAULT_MAX_STAGE_ENTRIES = 1


class StageFailurePolicy(str, Enum):
    """Control whether eligible stage failures degrade or stop the pipeline."""

    ISOLATE = "isolate"
    FAIL_FAST = "fail_fast"


@dataclass(frozen=True)
class RuntimeGuardPolicy:
    """Resolved runtime-guard thresholds for one Agent execution."""

    tool_timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS
    max_identical_tool_calls: int = DEFAULT_MAX_IDENTICAL_TOOL_CALLS
    max_stage_entries: int = DEFAULT_MAX_STAGE_ENTRIES
    stage_failure_policy: StageFailurePolicy = StageFailurePolicy.ISOLATE

    @classmethod
    def from_sources(cls, config: Any = None) -> "RuntimeGuardPolicy":
        """Resolve config attributes first, then environment, then defaults."""
        tool_timeout = _read_non_negative_float(
            config,
            attr_name="agent_tool_timeout_s",
            env_name="AGENT_TOOL_TIMEOUT_S",
            default=DEFAULT_TOOL_TIMEOUT_SECONDS,
        )
        identical_limit = _read_non_negative_int(
            config,
            attr_name="agent_max_identical_tool_calls",
            env_name="AGENT_MAX_IDENTICAL_TOOL_CALLS",
            default=DEFAULT_MAX_IDENTICAL_TOOL_CALLS,
        )
        stage_entry_limit = _read_non_negative_int(
            config,
            attr_name="agent_max_stage_entries",
            env_name="AGENT_MAX_STAGE_ENTRIES",
            default=DEFAULT_MAX_STAGE_ENTRIES,
        )
        failure_policy = _read_stage_failure_policy(config)
        return cls(
            tool_timeout_seconds=tool_timeout,
            max_identical_tool_calls=identical_limit,
            max_stage_entries=stage_entry_limit,
            stage_failure_policy=failure_policy,
        )


def runtime_guard_fingerprint(value: str) -> str:
    """Return a stable short digest without exposing the source value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def log_runtime_guard_event(
    target_logger: logging.Logger,
    event: str,
    *,
    level: int = logging.WARNING,
    **fields: Any,
) -> None:
    """Write one machine-readable guard event containing controlled scalars."""
    payload = {"event": _safe_log_value(str(event))}
    payload.update(
        {
            str(key): _safe_log_value(value)
            for key, value in fields.items()
            if value is not None
        }
    )
    target_logger.log(
        level,
        "agent_runtime_guard %s",
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
    )


def _read_source(config: Any, attr_name: str, env_name: str) -> Any:
    """Read one non-empty value from config, then the process environment."""
    if config is not None:
        value = getattr(config, attr_name, None)
        if value is not None and value != "":
            return value
    value = os.getenv(env_name)
    return value if value is not None and value != "" else None


def _read_non_negative_float(
    config: Any,
    *,
    attr_name: str,
    env_name: str,
    default: float,
) -> float:
    """Read a finite non-negative float or return the documented default."""
    raw_value = _read_source(config, attr_name, env_name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        _log_config_fallback(env_name, default, "invalid_number")
        return default
    if not math.isfinite(value) or value < 0:
        _log_config_fallback(env_name, default, "out_of_range")
        return default
    return value


def _read_non_negative_int(
    config: Any,
    *,
    attr_name: str,
    env_name: str,
    default: int,
) -> int:
    """Read a non-negative integer or return the documented default."""
    raw_value = _read_source(config, attr_name, env_name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        _log_config_fallback(env_name, default, "invalid_integer")
        return default
    if value < 0:
        _log_config_fallback(env_name, default, "out_of_range")
        return default
    return value


def _read_stage_failure_policy(config: Any) -> StageFailurePolicy:
    """Resolve the supported stage failure policy without silent fallback."""
    env_name = "AGENT_STAGE_FAILURE_POLICY"
    raw_value = _read_source(config, "agent_stage_failure_policy", env_name)
    if raw_value is None:
        return StageFailurePolicy.ISOLATE
    if isinstance(raw_value, StageFailurePolicy):
        return raw_value
    try:
        return StageFailurePolicy(str(raw_value).strip().lower())
    except ValueError:
        _log_config_fallback(env_name, StageFailurePolicy.ISOLATE.value, "invalid_enum")
        return StageFailurePolicy.ISOLATE


def _log_config_fallback(setting: str, default: Any, reason: str) -> None:
    """Record why one invalid guard setting fell back to its default."""
    log_runtime_guard_event(
        logging.getLogger(__name__),
        "guard_config_fallback",
        setting=setting,
        default=default,
        reason=reason,
    )


def _safe_log_value(value: Any) -> Any:
    """Return a bounded scalar that cannot expose credential-like strings."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, str):
        return sanitize_diagnostic_text(value, max_length=120)
    return type(value).__name__


__all__ = [
    "DEFAULT_MAX_IDENTICAL_TOOL_CALLS",
    "DEFAULT_MAX_STAGE_ENTRIES",
    "DEFAULT_TOOL_TIMEOUT_SECONDS",
    "RuntimeGuardPolicy",
    "StageFailurePolicy",
    "log_runtime_guard_event",
    "runtime_guard_fingerprint",
]
