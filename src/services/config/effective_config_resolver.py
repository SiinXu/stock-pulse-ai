# -*- coding: utf-8 -*-
"""Single authority for turning stored `.env` values into display/effective config.

``SystemConfigService.get_config`` and the setup/status readers all need the same
notion of the *effective* value a user should see for a key: alias resolution,
switch defaults, process-environment fallbacks and the LLM channel support keys.
Centralizing that here keeps one authority for "what value is in effect" instead
of letting each caller re-derive it.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Set, Tuple

from src.core.config_registry import (
    LLM_CHANNEL_FIELD_KEY_RE,
    get_registered_field_keys,
)


class EffectiveConfigResolver:
    """Resolve stored config maps into the display map surfaced to clients."""

    _DISPLAY_KEY_ALIASES: Dict[str, Tuple[str, ...]] = {
        "AGENT_SKILL_DIR": ("AGENT_SKILL_DIR", "AGENT_STRATEGY_DIR"),
        "AGENT_SKILL_AUTOWEIGHT": ("AGENT_SKILL_AUTOWEIGHT", "AGENT_STRATEGY_AUTOWEIGHT"),
        "AGENT_SKILL_ROUTING": ("AGENT_SKILL_ROUTING", "AGENT_STRATEGY_ROUTING"),
    }
    _DISPLAY_VALUE_ALIASES: Dict[str, Dict[str, str]] = {
        "AGENT_ORCHESTRATOR_MODE": {
            "strategy": "specialist",
            "skill": "specialist",
        }
    }

    @classmethod
    def _normalize_display_value(cls, key: str, value: str) -> str:
        alias_map = cls._DISPLAY_VALUE_ALIASES.get(key.upper())
        if not alias_map:
            return value
        return alias_map.get(value.strip().lower(), value)

    @classmethod
    def build_display_config_map(cls, raw_config_map: Dict[str, str]) -> Dict[str, str]:
        raw_upper = {key.upper(): value for key, value in raw_config_map.items()}
        aliased_keys = {
            alias
            for candidates in cls._DISPLAY_KEY_ALIASES.values()
            for alias in candidates
        }
        display_map: Dict[str, str] = {}

        for key, value in raw_upper.items():
            if key in aliased_keys:
                continue
            display_map[key] = cls._normalize_display_value(key, value)

        for canonical_key, candidates in cls._DISPLAY_KEY_ALIASES.items():
            canonical_env_key = candidates[0]
            if canonical_env_key in raw_upper:
                display_map[canonical_key] = cls._normalize_display_value(
                    canonical_key,
                    raw_upper[canonical_env_key],
                )
                continue

            selected_value: Optional[str] = None
            candidate_seen = False
            for candidate_key in candidates[1:]:
                if candidate_key not in raw_upper:
                    continue
                candidate_seen = True
                candidate_value = raw_upper[candidate_key]
                if candidate_value:
                    selected_value = candidate_value
                    break
            if candidate_seen:
                if selected_value is None:
                    for candidate_key in candidates[1:]:
                        if candidate_key in raw_upper:
                            selected_value = raw_upper[candidate_key]
                            break
                if selected_value is None:
                    selected_value = ""
                display_map[canonical_key] = cls._normalize_display_value(
                    canonical_key,
                    selected_value,
                )

        return display_map

    @staticmethod
    def resolve_display_value(
        raw_value: str,
        field_schema: Dict[str, Any],
        raw_value_exists: bool,
    ) -> str:
        if raw_value_exists:
            return raw_value

        if field_schema.get("ui_control") == "switch" and raw_value:
            return raw_value

        if field_schema.get("ui_control") == "switch":
            default_value = field_schema.get("default_value")
            if isinstance(default_value, str) and default_value:
                return default_value

        return raw_value

    @staticmethod
    def get_schema_config_keys(
        config_map: Dict[str, str],
        registered_keys: Set[str],
    ) -> Set[str]:
        """Return keys needed by the Web schema payload.

        Ordinary settings must be registry-backed. LLM channel detail keys are
        kept only as editor support data for channels declared in LLM_CHANNELS.
        """
        keys = set(registered_keys)
        channel_names = {
            segment.strip().upper()
            for segment in config_map.get("LLM_CHANNELS", "").split(",")
            if segment.strip()
        }
        if not channel_names:
            return keys

        for key in config_map:
            match = LLM_CHANNEL_FIELD_KEY_RE.match(key)
            if match and match.group(1) in channel_names:
                keys.add(key)

        return keys

    @classmethod
    def build_runtime_display_config_map(
        cls,
        saved_config_map: Dict[str, str],
    ) -> Dict[str, str]:
        """Return Web settings values injected through the process environment.

        Docker ``env_file`` / ``--env-file`` only populate process environment
        variables; they do not create an active ``.env`` file inside the
        container. Use these values as display fallbacks so Settings can show
        startup-injected config without letting it override later WebUI saves.
        """
        registered_keys = {key.upper() for key in get_registered_field_keys()}
        channel_names = {
            segment.strip().upper()
            for raw_channels in (
                saved_config_map.get("LLM_CHANNELS", ""),
                os.environ.get("LLM_CHANNELS", ""),
            )
            for segment in raw_channels.split(",")
            if segment.strip()
        }
        runtime_map: Dict[str, str] = {}

        for raw_key, raw_value in os.environ.items():
            key = str(raw_key).upper()
            llm_channel_match = LLM_CHANNEL_FIELD_KEY_RE.match(key)
            if (
                key in registered_keys
                or (llm_channel_match and llm_channel_match.group(1) in channel_names)
            ):
                runtime_map[key] = "" if raw_value is None else str(raw_value)

        return cls.build_display_config_map(runtime_map)
