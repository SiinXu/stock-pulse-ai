# -*- coding: utf-8 -*-
"""Single resolve path: raw config key → (value, source).

Precedence matches the historical ``Config._resolve_env_value`` contract:

1. For WebUI file-priority keys (or ``prefer_env_file=True``) when the
   persisted ``.env`` has a value:
   - process env wins only when bootstrap capture proves an explicit override;
   - otherwise the persisted file wins.
2. Otherwise process env (post-``setup_env`` / dotenv) wins when present.
3. Otherwise the persisted file value wins when present.
4. Otherwise the caller-provided default (source ``default``).

Registry defaults are **not** auto-applied here. Typed runtime defaults still
live in ``Config._load_from_env`` parsers. Callers that want the registry's
``default_value`` metadata must pass it explicitly (or use
:func:`resolve_registered`) so unregistered keys never invent values and the
env-example registry guard is not bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Set

from src.core.config.sources import (
    WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS,
    ConfigSource,
    get_env_file_value,
    get_process_env_value,
    resolve_env_path,
)


@dataclass(frozen=True)
class ResolvedConfigValue:
    """One resolved raw configuration string and its winning source."""

    key: str
    value: Optional[str]
    source: ConfigSource

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source.value,
        }


def resolve_config_value(
    key: str,
    *,
    env_value: Optional[str],
    file_value: Optional[str],
    default: Optional[str] = None,
    prefer_env_file: bool = False,
    has_bootstrap_override: bool = False,
    webui_file_priority: bool = False,
) -> ResolvedConfigValue:
    """Pure resolution of one key. Inputs are already read from adapters.

    Behavior (value selection) is identical to the pre-#1070
    ``Config._resolve_env_value`` algorithm; *source* is additive metadata.
    """
    normalized_key = str(key)
    should_prefer_file = prefer_env_file or webui_file_priority
    if should_prefer_file and file_value is not None:
        if env_value is not None and has_bootstrap_override:
            return ResolvedConfigValue(
                key=normalized_key,
                value=env_value,
                source=ConfigSource.ENV,
            )
        return ResolvedConfigValue(
            key=normalized_key,
            value=file_value,
            source=ConfigSource.PERSISTED,
        )
    if env_value is not None:
        return ResolvedConfigValue(
            key=normalized_key,
            value=env_value,
            source=ConfigSource.ENV,
        )
    if file_value is not None:
        return ResolvedConfigValue(
            key=normalized_key,
            value=file_value,
            source=ConfigSource.PERSISTED,
        )
    return ResolvedConfigValue(
        key=normalized_key,
        value=default,
        source=ConfigSource.DEFAULT,
    )


def _bootstrap_override_for(key: str) -> bool:
    """Read bootstrap override flag from the Config facade when available."""
    # Lazy import avoids import cycles during src.config bootstrap.
    from src.config import Config

    return Config._has_bootstrap_runtime_env_override(key)


def resolve(
    key: str,
    *,
    default: Optional[str] = None,
    prefer_env_file: bool = False,
    env_path: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
    file_values: Optional[Mapping[str, str]] = None,
    bootstrap_overrides: Optional[Set[str]] = None,
    webui_priority_keys: Optional[Set[str]] = None,
) -> ResolvedConfigValue:
    """Resolve one key through the single path and return value + source.

    When *bootstrap_overrides* is omitted, uses ``Config`` bootstrap capture
    (must have been run via ``setup_env`` /
    ``Config._capture_bootstrap_runtime_env_overrides`` for WebUI-priority keys
    to classify correctly).
    """
    normalized_key = str(key)
    priority = (
        webui_priority_keys
        if webui_priority_keys is not None
        else WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS
    )
    env_value = get_process_env_value(normalized_key, environ=environ)
    file_value = get_env_file_value(
        normalized_key,
        env_path=env_path,
        file_values=file_values,
    )
    if bootstrap_overrides is not None:
        has_override = normalized_key in bootstrap_overrides
    else:
        has_override = _bootstrap_override_for(normalized_key)

    return resolve_config_value(
        normalized_key,
        env_value=env_value,
        file_value=file_value,
        default=default,
        prefer_env_file=prefer_env_file,
        has_bootstrap_override=has_override,
        webui_file_priority=normalized_key in priority,
    )


def resolve_registered(
    key: str,
    *,
    prefer_env_file: bool = False,
    env_path: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
    file_values: Optional[Mapping[str, str]] = None,
    bootstrap_overrides: Optional[Set[str]] = None,
) -> ResolvedConfigValue:
    """Resolve a **registered** key, applying registry ``default_value`` only when set.

    Unregistered keys resolve without inventing a registry default (same as
    :func:`resolve` with ``default=None``). This keeps the unregistered-key
    debt guard honest: resolution never silently registers or fabricates keys.
    """
    default: Optional[str] = None
    # Lazy import: config_registry pulls selected constants from src.config.
    from src.core.config_registry import get_field_definition, get_registered_field_keys

    normalized_key = str(key).upper()
    registered = {item.upper() for item in get_registered_field_keys()}
    if normalized_key in registered:
        field = get_field_definition(normalized_key)
        raw_default = field.get("default_value")
        if isinstance(raw_default, str):
            default = raw_default
        elif raw_default is not None:
            default = str(raw_default)

    return resolve(
        normalized_key,
        default=default,
        prefer_env_file=prefer_env_file,
        env_path=env_path,
        environ=environ,
        file_values=file_values,
        bootstrap_overrides=bootstrap_overrides,
    )


def dump_resolved(
    keys: Optional[Sequence[str]] = None,
    *,
    prefer_env_file_keys: Optional[Set[str]] = None,
    env_path: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
    file_values: Optional[Mapping[str, str]] = None,
    bootstrap_overrides: Optional[Set[str]] = None,
    use_registry_defaults: bool = False,
) -> List[ResolvedConfigValue]:
    """Diagnostics dump: ``key → value → source`` for the requested key set.

    When *keys* is omitted, dumps every **registered** field key (never the
    temporary unregistered debt list — that set is guard-only and must shrink).
    """
    if keys is None:
        from src.core.config_registry import get_registered_field_keys

        keys = list(get_registered_field_keys())

    prefer_keys = prefer_env_file_keys or set()
    prefer_upper = {str(item).upper() for item in prefer_keys}
    results: List[ResolvedConfigValue] = []
    for key in keys:
        prefer = str(key).upper() in prefer_upper
        if use_registry_defaults:
            results.append(
                resolve_registered(
                    key,
                    prefer_env_file=prefer,
                    env_path=env_path,
                    environ=environ,
                    file_values=file_values,
                    bootstrap_overrides=bootstrap_overrides,
                )
            )
        else:
            results.append(
                resolve(
                    key,
                    prefer_env_file=prefer,
                    env_path=env_path,
                    environ=environ,
                    file_values=file_values,
                    bootstrap_overrides=bootstrap_overrides,
                )
            )
    return results


def dump_resolved_as_dicts(
    keys: Optional[Iterable[str]] = None,
    **kwargs,
) -> List[dict]:
    """JSON-friendly form of :func:`dump_resolved`."""
    key_list = list(keys) if keys is not None else None
    return [item.as_dict() for item in dump_resolved(key_list, **kwargs)]


__all__ = [
    "ResolvedConfigValue",
    "dump_resolved",
    "dump_resolved_as_dicts",
    "resolve",
    "resolve_config_value",
    "resolve_env_path",
    "resolve_registered",
]
