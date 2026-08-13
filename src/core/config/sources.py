# -*- coding: utf-8 -*-
"""Config value sources: process environment and persisted ``.env``.

This module owns the *raw* source adapters used by the single resolve path.
It does not invent keys: registration and UI metadata stay in
``src.core.config_registry`` (and the unregistered-key debt guard).

Bootstrap override capture for WebUI-priority keys remains on
``Config`` (tests and runtime reliability patch those class attributes).
Adapters here only read process env and the persisted file.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Dict, Mapping, Optional, Union

from dotenv import dotenv_values

from src.core.config_manager import unescape_compose_sensitive_env_value
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

# Keys the WebUI can rewrite at runtime. When a value is present in the
# persisted ``.env`` file, that copy is preferred over the post-dotenv process
# environment — unless bootstrap capture proves the process env was an explicit
# host/container override. Keep this set identical to the historical
# ``Config._WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS`` contract.
WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS = frozenset(
    {
        "STOCK_LIST",
        "RUN_IMMEDIATELY",
        "SCHEDULE_ENABLED",
        "SCHEDULE_TIME",
        "SCHEDULE_TIMES",
        "SCHEDULE_RUN_IMMEDIATELY",
    }
)


class ConfigSource(str, Enum):
    """Where a resolved raw config string came from.

    Values are stable strings for diagnostics dumps and API payloads.
    """

    DEFAULT = "default"
    ENV = "env"
    PERSISTED = "persisted"


def resolve_env_path(env_file: Optional[Union[str, Path]] = None) -> Path:
    """Return the active ``.env`` path (``ENV_FILE`` or repository-root default).

    Matches ``setup_env`` in :mod:`src.config` so diagnostics and the public
    :func:`src.core.config.resolve` entry agree with process bootstrap.
    """
    if env_file is not None:
        return Path(env_file)
    configured = os.getenv("ENV_FILE")
    if configured:
        return Path(configured)
    # src/core/config/sources.py -> config -> core -> src -> repository root
    return Path(__file__).resolve().parents[3] / ".env"


def read_persisted_config_map(
    env_path: Optional[Path] = None,
    *,
    normalize_compose_sensitive: bool = True,
) -> Dict[str, str]:
    """Read the full persisted ``.env`` map (missing file → empty dict)."""
    path = env_path if env_path is not None else resolve_env_path()
    if not path.exists():
        return {}
    try:
        content = path.read_bytes()
    except Exception as exc:  # broad-exception: fallback_recorded - missing map
        log_safe_exception(
            logger,
            "Environment file read failed",
            exc,
            error_code="environment_file_read_failed",
            level=logging.WARNING,
            context={"env_path": str(path)},
        )
        return {}

    text = content.decode("utf-8")
    raw_values = dotenv_values(stream=StringIO(text), interpolate=False)
    values = dotenv_values(stream=StringIO(text)) if normalize_compose_sensitive else raw_values
    if normalize_compose_sensitive:
        for raw_key, raw_value in raw_values.items():
            if raw_key is not None and str(raw_key).upper() == "CUSTOM_WEBHOOK_BODY_TEMPLATE":
                values[raw_key] = raw_value
    else:
        values = raw_values

    config_map: Dict[str, str] = {}
    for key, value in values.items():
        if key is None:
            continue
        normalized_key = str(key)
        normalized_value = "" if value is None else str(value)
        if normalize_compose_sensitive:
            normalized_value = unescape_compose_sensitive_env_value(
                normalized_key,
                normalized_value,
            )
        config_map[normalized_key] = normalized_value
    return config_map


def get_env_file_value(
    key: str,
    *,
    env_path: Optional[Path] = None,
    file_values: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Read one key from the persisted ``.env`` (None when absent)."""
    if file_values is not None:
        if key not in file_values:
            return None
        value = file_values[key]
        return unescape_compose_sensitive_env_value(key, str(value))

    path = env_path if env_path is not None else resolve_env_path()
    if not path.exists():
        return None

    try:
        env_values = dotenv_values(path)
    except Exception as exc:  # broad-exception: fallback_recorded - treat as missing
        log_safe_exception(
            logger,
            "Environment file read failed",
            exc,
            error_code="environment_file_read_failed",
            level=logging.WARNING,
            context={"config_key": key},
        )
        return None

    value = env_values.get(key)
    if value is None:
        return None
    return unescape_compose_sensitive_env_value(key, str(value))


def get_process_env_value(
    key: str,
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Read one key from the process environment (None when absent)."""
    source = os.environ if environ is None else environ
    if key not in source:
        return None
    value = source[key]
    return None if value is None else str(value)
