# -*- coding: utf-8 -*-
"""Single configuration resolution path (value + source).

New code that needs a raw config string should call :func:`resolve` instead of
reaching ``os.getenv`` / dotenv / registry defaults through ad-hoc paths.

Registry metadata continues to live in :mod:`src.core.config_registry`; this
package re-exports the registration helpers used together with resolution so
callers do not invent a parallel key catalog.
"""

from __future__ import annotations

from src.core.config.resolve import (
    ResolvedConfigValue,
    dump_resolved,
    dump_resolved_as_dicts,
    resolve,
    resolve_config_value,
    resolve_registered,
)
from src.core.config.sources import (
    WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS,
    ConfigSource,
    get_env_file_value,
    get_process_env_value,
    read_persisted_config_map,
    resolve_env_path,
)

__all__ = [
    "ConfigSource",
    "ResolvedConfigValue",
    "WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS",
    "dump_resolved",
    "dump_resolved_as_dicts",
    "get_env_file_value",
    "get_process_env_value",
    "read_persisted_config_map",
    "resolve",
    "resolve_config_value",
    "resolve_env_path",
    "resolve_registered",
]
