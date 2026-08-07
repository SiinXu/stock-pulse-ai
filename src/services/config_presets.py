# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Official recommended configuration presets (data only).

Presets are pure data: each entry maps to non-secret system-config keys that are
applied through SystemConfigService. No secrets, tokens, or executable content.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple


PROFILE_API_VERSION = "stockpulse/v1"
PROFILE_KIND = "Profile"
MAX_PROFILE_YAML_BYTES = 256 * 1024

_SECRET_KEY_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
_SECRET_KEY_SUFFIXES = ("_EXTRA_HEADERS",)
_SECRET_KEY_EXACT = frozenset({"LITELLM_CONFIG"})

PROFILE_EXPORT_KEY_ALLOWLIST = frozenset(
    {
        "GENERATION_BACKEND",
        "GENERATION_FALLBACK_BACKEND",
        "GENERATION_BACKEND_TIMEOUT_SECONDS",
        "GENERATION_BACKEND_MAX_OUTPUT_BYTES",
        "GENERATION_BACKEND_MAX_CONCURRENCY",
        "LOCAL_CLI_BACKEND_MAX_CONCURRENCY",
        "OPENCODE_CLI_MODEL",
        "LLM_CONFIG_MODE",
        "LITELLM_MODEL",
        "LITELLM_FALLBACK_MODELS",
        "AGENT_LITELLM_MODEL",
        "AGENT_GENERATION_BACKEND",
        "AGENT_FEATURES_ACKNOWLEDGED_OFF",
        "AGENT_SKILLS",
        "AGENT_SKILL_DIR",
        "AGENT_SKILL_ROUTING",
        "AGENT_SKILL_AUTOWEIGHT",
        "VISION_MODEL",
        "REPORT_LANGUAGE",
        "NEWS_STRATEGY_PROFILE",
        "LLM_CHANNELS",
        "LLM_OLLAMA_PROVIDER",
        "LLM_OLLAMA_PROTOCOL",
        "LLM_OLLAMA_BASE_URL",
        "LLM_OLLAMA_MODELS",
        "LLM_OLLAMA_ENABLED",
        "LLM_OLLAMA_DISPLAY_NAME",
    }
)


def is_secret_config_key(key: str) -> bool:
    """Return True when a config key must never enter a profile YAML."""
    normalized = str(key or "").strip().upper()
    if not normalized:
        return True
    if normalized in _SECRET_KEY_EXACT:
        return True
    if any(normalized.endswith(suffix) for suffix in _SECRET_KEY_SUFFIXES):
        return True
    if any(marker in normalized for marker in _SECRET_KEY_MARKERS):
        return True
    return False


def is_exportable_config_key(key: str) -> bool:
    """Return True when a non-secret key is allowed in profile export."""
    normalized = str(key or "").strip().upper()
    if not normalized or is_secret_config_key(normalized):
        return False
    if normalized in PROFILE_EXPORT_KEY_ALLOWLIST:
        return True
    if normalized.startswith("LLM_") and not is_secret_config_key(normalized):
        if normalized.endswith(
            (
                "_PROTOCOL",
                "_MODELS",
                "_ENABLED",
                "_DISPLAY_NAME",
                "_PROVIDER",
                "_BASE_URL",
            )
        ):
            return True
    return False


def _preset(
    *,
    preset_id: str,
    display_name: str,
    description: str,
    tags: List[str],
    preference_order: List[str],
    config_values: Mapping[str, str],
    strategies_enabled: List[str],
    beginner_mode: bool,
    requirements: Mapping[str, Any],
) -> Dict[str, Any]:
    safe_config = {
        str(key).upper(): str(value)
        for key, value in config_values.items()
        if not is_secret_config_key(str(key))
    }
    return {
        "id": preset_id,
        "display_name": display_name,
        "description": description,
        "tags": list(tags),
        "preference_order": list(preference_order),
        "config_values": safe_config,
        "strategies": {"enabled": list(strategies_enabled)},
        "features": {"beginner_mode": bool(beginner_mode)},
        "requirements": dict(requirements),
    }


OFFICIAL_PRESETS: Tuple[Dict[str, Any], ...] = (
    _preset(
        preset_id="local-first",
        display_name="Local-first (Ollama / Model Pack)",
        description=(
            "Prefer local Ollama or Model Pack models for analysis. "
            "Uses LiteLLM channels mode with an Ollama connection scaffold; "
            "does not invent API keys."
        ),
        tags=["local", "privacy", "offline-capable"],
        preference_order=["ollama", "model_pack", "cli", "cloud"],
        config_values={
            "GENERATION_BACKEND": "litellm",
            "GENERATION_FALLBACK_BACKEND": "litellm",
            "LLM_CONFIG_MODE": "channels",
            "LLM_OLLAMA_PROVIDER": "ollama",
            "LLM_OLLAMA_PROTOCOL": "ollama",
            "LLM_OLLAMA_ENABLED": "true",
            "LLM_OLLAMA_DISPLAY_NAME": "Ollama (local)",
            "AGENT_GENERATION_BACKEND": "auto",
        },
        strategies_enabled=["bull_trend"],
        beginner_mode=True,
        requirements={"needs_ollama": True, "min_ram_gb": 8},
    ),
    _preset(
        preset_id="cli-backends",
        display_name="CLI backends (Codex / Claude Code / OpenCode)",
        description=(
            "Prefer a local generation CLI for analysis text. "
            "Agent features stay optional; acknowledge CLI generation-only limits."
        ),
        tags=["local", "cli", "experimental"],
        preference_order=["cli", "ollama", "model_pack", "cloud"],
        config_values={
            "GENERATION_BACKEND": "codex_cli",
            "GENERATION_FALLBACK_BACKEND": "litellm",
            "AGENT_FEATURES_ACKNOWLEDGED_OFF": "true",
            "AGENT_GENERATION_BACKEND": "auto",
        },
        strategies_enabled=["bull_trend"],
        beginner_mode=True,
        requirements={"needs_cli": True, "min_ram_gb": 4},
    ),
    _preset(
        preset_id="cloud-balanced",
        display_name="Cloud balanced",
        description=(
            "Balanced cloud-oriented defaults: LiteLLM channels mode with "
            "backend fallback enabled. Add your own provider credentials separately."
        ),
        tags=["cloud", "balanced"],
        preference_order=["cloud", "cli", "ollama", "model_pack"],
        config_values={
            "GENERATION_BACKEND": "litellm",
            "GENERATION_FALLBACK_BACKEND": "litellm",
            "LLM_CONFIG_MODE": "channels",
            "AGENT_GENERATION_BACKEND": "auto",
            "NEWS_STRATEGY_PROFILE": "short",
        },
        strategies_enabled=["bull_trend", "growth_quality"],
        beginner_mode=True,
        requirements={"needs_cloud_key": True, "min_ram_gb": 2},
    ),
    _preset(
        preset_id="power-user",
        display_name="Custom / advanced",
        description=(
            "Minimal touch preset that keeps full Settings available. "
            "Does not force a generation backend; disables beginner-mode bias."
        ),
        tags=["advanced", "custom"],
        preference_order=["cloud", "cli", "ollama", "model_pack"],
        config_values={"LLM_CONFIG_MODE": "auto"},
        strategies_enabled=[],
        beginner_mode=False,
        requirements={},
    ),
)

PRESET_BY_ID: Dict[str, Dict[str, Any]] = {str(item["id"]): item for item in OFFICIAL_PRESETS}


def list_official_presets() -> List[Dict[str, Any]]:
    return [dict(item) for item in OFFICIAL_PRESETS]


def get_official_preset(preset_id: str) -> Dict[str, Any] | None:
    item = PRESET_BY_ID.get(str(preset_id or "").strip())
    return dict(item) if item is not None else None


__all__ = [
    "MAX_PROFILE_YAML_BYTES",
    "OFFICIAL_PRESETS",
    "PRESET_BY_ID",
    "PROFILE_API_VERSION",
    "PROFILE_EXPORT_KEY_ALLOWLIST",
    "PROFILE_KIND",
    "get_official_preset",
    "is_exportable_config_key",
    "is_secret_config_key",
    "list_official_presets",
]
