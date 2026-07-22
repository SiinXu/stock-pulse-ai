# -*- coding: utf-8 -*-
"""Configuration field metadata registry.

This module is the single source of truth for configuration UI metadata,
validation hints, and category grouping.
"""

from __future__ import annotations

import importlib as _importlib
import re
import sys as _sys
from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.config import (
    AGENT_CONTEXT_COMPRESSION_PROFILES,
    AGENT_MAX_STEPS_DEFAULT,
    DEFAULT_ALPHASIFT_INSTALL_SPEC,
)
from src.notification_noise import NOTIFICATION_SEVERITIES
from src.notification_routing import ROUTABLE_NOTIFICATION_CHANNELS

SCHEMA_VERSION = "2026-07-16-config-contract"

_REGISTRY_PART_MODULES = (
    "src.core.config_registry_parts.catalog",
    "src.core.config_registry_parts.base",
    "src.core.config_registry_parts.ai_model",
    "src.core.config_registry_parts.data_source",
    "src.core.config_registry_parts.notification",
    "src.core.config_registry_parts.system",
    "src.core.config_registry_parts.backtest",
    "src.core.config_registry_parts.agent",
    "src.core.config_registry_parts.help_metadata",
)
for _registry_part_name in _REGISTRY_PART_MODULES:
    _registry_part_module = _sys.modules.get(_registry_part_name)
    if _registry_part_module is None:
        _importlib.import_module(_registry_part_name)
    else:
        _importlib.reload(_registry_part_module)
del _registry_part_name
del _registry_part_module

from src.core.config_registry_parts.catalog import (
    WEB_SETTINGS_HIDDEN_FROM_UI,
    _CATEGORY_DEFINITIONS,
)
_CATEGORY_DEFINITIONS: List[Dict[str, Any]]

from src.core.config_registry_parts.base import (
    BASE_FIELD_DEFINITIONS as _BASE_FIELD_DEFINITIONS,
)
from src.core.config_registry_parts.ai_model import (
    AI_MODEL_FIELD_DEFINITIONS as _AI_MODEL_FIELD_DEFINITIONS,
    AI_MODEL_LEGACY_FIELD_DEFINITIONS as _AI_MODEL_LEGACY_FIELD_DEFINITIONS,
)
from src.core.config_registry_parts.data_source import (
    DATA_SOURCE_FIELD_DEFINITIONS as _DATA_SOURCE_FIELD_DEFINITIONS,
)
from src.core.config_registry_parts.notification import (
    NOTIFICATION_FIELD_DEFINITIONS as _NOTIFICATION_FIELD_DEFINITIONS,
)
from src.core.config_registry_parts.system import (
    SYSTEM_FIELD_DEFINITIONS as _SYSTEM_FIELD_DEFINITIONS,
)
from src.core.config_registry_parts.backtest import (
    BACKTEST_FIELD_DEFINITIONS as _BACKTEST_FIELD_DEFINITIONS,
)
from src.core.config_registry_parts.agent import (
    AGENT_FIELD_DEFINITIONS as _AGENT_FIELD_DEFINITIONS,
)
from src.core.config_registry_parts.help_metadata import (
    _DOC_CUSTOM_WEBHOOK,
    _DOC_FULL_GUIDE_DATA_SOURCE,
    _DOC_FULL_GUIDE_ENV,
    _DOC_FULL_GUIDE_NOTIFICATION,
    _DOC_FULL_GUIDE_SEARCH,
    _DOC_LLM_CONFIG,
    _FIELD_HELP_METADATA,
)

_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    **_BASE_FIELD_DEFINITIONS,
    **_AI_MODEL_FIELD_DEFINITIONS,
    **_DATA_SOURCE_FIELD_DEFINITIONS,
    **_AI_MODEL_LEGACY_FIELD_DEFINITIONS,
    **_NOTIFICATION_FIELD_DEFINITIONS,
    **_SYSTEM_FIELD_DEFINITIONS,
    **_BACKTEST_FIELD_DEFINITIONS,
    **_AGENT_FIELD_DEFINITIONS,
}
_FIELD_HELP_METADATA: Dict[str, Dict[str, Any]]

del _BASE_FIELD_DEFINITIONS
del _AI_MODEL_FIELD_DEFINITIONS
del _DATA_SOURCE_FIELD_DEFINITIONS
del _AI_MODEL_LEGACY_FIELD_DEFINITIONS
del _NOTIFICATION_FIELD_DEFINITIONS
del _SYSTEM_FIELD_DEFINITIONS
del _BACKTEST_FIELD_DEFINITIONS
del _AGENT_FIELD_DEFINITIONS
del _REGISTRY_PART_MODULES
del _importlib
del _sys


def get_category_definitions() -> List[Dict[str, Any]]:
    """Return deep-copied category metadata."""
    return deepcopy(_CATEGORY_DEFINITIONS)


def get_registered_field_keys() -> List[str]:
    """Return all explicitly registered keys."""
    return list(_FIELD_DEFINITIONS.keys())


def _extract_option_values(options: List[Any]) -> List[str]:
    """Extract canonical option values from string/object style select options."""
    values: List[str] = []
    for option in options:
        if isinstance(option, str):
            values.append(option)
            continue
        if isinstance(option, dict):
            value = option.get("value")
            if isinstance(value, str) and value:
                values.append(value)
    return values


# UI ownership/placement for AI-model related fields. The Web renders each
# field only in the surface its placement declares, instead of maintaining its
# own provider/field lists:
#   - model_access: edited exclusively by the model-access connection manager
#   - task_routing: task model selectors (report / agent / vision) and routing
#   - developer_diagnostics: advanced diagnostics, collapsed by default
#   - hidden_legacy: legacy provider keys kept for back-compat; readable through
#     the API but never rendered as a generic editable settings field
#   - None: regular field, rendered by its category page as usual
_UI_PLACEMENT_TASK_ROUTING_KEYS = frozenset({
    "LITELLM_MODEL",
    "AGENT_LITELLM_MODEL",
    "VISION_MODEL",
    "LITELLM_FALLBACK_MODELS",
    "LLM_TEMPERATURE",
})

_UI_PLACEMENT_DIAGNOSTICS_KEYS = frozenset({
    "LLM_CONFIG_MODE",
    "LITELLM_CONFIG",
    "GENERATION_BACKEND",
    "GENERATION_FALLBACK_BACKEND",
    "GENERATION_BACKEND_MAX_CONCURRENCY",
    "GENERATION_BACKEND_MAX_OUTPUT_BYTES",
    "GENERATION_BACKEND_TIMEOUT_SECONDS",
    "LOCAL_CLI_BACKEND_MAX_CONCURRENCY",
    "OPENCODE_CLI_MODEL",
})
_UI_PLACEMENT_DIAGNOSTICS_PREFIXES = ("LLM_PROMPT_CACHE_", "LLM_USAGE_HMAC_")

_UI_PLACEMENT_HIDDEN_LEGACY_KEYS = frozenset({
    "AIHUBMIX_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEYS",
    "OLLAMA_API_BASE",
    "OLLAMA_MODEL",
})
_UI_PLACEMENT_HIDDEN_LEGACY_PREFIXES = ("OPENAI_", "ANTHROPIC_", "GEMINI_", "ANSPIRE_LLM_")

# Canonical shape of dynamic per-channel config keys (LLM_<NAME>_API_KEY, ...).
# group(1) captures the channel name. Shared with the service layer so "what is
# a channel field key" has a single definition.
LLM_CHANNEL_FIELD_KEY_RE = re.compile(
    r"^LLM_([A-Z0-9_]+)_(DISPLAY_NAME|PROVIDER|PROTOCOL|BASE_URL|API_KEY|API_KEYS|MODELS|EXTRA_HEADERS|ENABLED)$"
)


def derive_ui_placement(key: str) -> Optional[str]:
    """Return the UI placement for a config key (None = regular field)."""
    key_upper = key.upper()
    if key_upper == "LLM_CHANNELS":
        return "model_access"
    if key_upper in _UI_PLACEMENT_TASK_ROUTING_KEYS:
        return "task_routing"
    if key_upper in _UI_PLACEMENT_DIAGNOSTICS_KEYS or key_upper.startswith(
        _UI_PLACEMENT_DIAGNOSTICS_PREFIXES
    ):
        return "developer_diagnostics"
    if key_upper in _UI_PLACEMENT_HIDDEN_LEGACY_KEYS or key_upper.startswith(
        _UI_PLACEMENT_HIDDEN_LEGACY_PREFIXES
    ):
        return "hidden_legacy"
    if LLM_CHANNEL_FIELD_KEY_RE.match(key_upper):
        return "model_access"
    return None


def get_field_definition(key: str, value_hint: Optional[str] = None) -> Dict[str, Any]:
    """Return field definition for key, including inferred fallback metadata."""
    key_upper = key.upper()
    if key_upper in _FIELD_DEFINITIONS:
        field = deepcopy(_FIELD_DEFINITIONS[key_upper])
        if key_upper in _FIELD_HELP_METADATA:
            field.update(deepcopy(_FIELD_HELP_METADATA[key_upper]))
        field["key"] = key_upper
        validation = deepcopy(field.get("validation") or {})
        option_values = _extract_option_values(field.get("options", []))
        if field.get("ui_control") == "select" and option_values and "enum" not in validation:
            validation["enum"] = option_values
        field["validation"] = validation
        field["ui_placement"] = derive_ui_placement(key_upper)
        return field

    category = _infer_category(key_upper)
    data_type = _infer_data_type(key_upper, value_hint)
    field = {
        "key": key_upper,
        "title": key_upper.replace("_", " ").title(),
        "description": "Auto-inferred field metadata.",
        "category": category,
        "data_type": data_type,
        "ui_control": _infer_ui_control(data_type, key_upper),
        "is_sensitive": _is_sensitive_key(key_upper),
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 9000,
        "ui_placement": derive_ui_placement(key_upper),
    }
    return field


def get_contract_field_definitions() -> Dict[str, Dict[str, Any]]:
    """Return {KEY: contract} for registered fields that declare a schema contract."""
    return {
        key: deepcopy(field["contract"])
        for key, field in _FIELD_DEFINITIONS.items()
        if field.get("contract")
    }


def evaluate_config_conditions(
    conditions: Optional[List[Dict[str, Any]]],
    config_map: Dict[str, str],
) -> str:
    """Evaluate an AND-list of field conditions against a config map.

    Returns 'met', 'not_met', or 'unknown'. An unknown operator yields 'unknown'
    so callers can fail-safe (keep the field visible and still validated).
    """
    if conditions is None:
        return "met"
    if not isinstance(conditions, list):
        return "unknown"
    if not conditions:
        return "met"
    all_met = True
    for condition in conditions:
        if not isinstance(condition, dict):
            return "unknown"
        key = str(condition.get("key", "")).strip().upper()
        if not key:
            return "unknown"
        operator = condition.get("operator")
        expected = condition.get("value")
        actual = str(config_map.get(key, "") or "")
        if operator == "equals":
            if isinstance(expected, list):
                return "unknown"
            expected_scalar = "" if expected is None else str(expected)
            met = actual == expected_scalar
        elif operator == "notEquals":
            if isinstance(expected, list):
                return "unknown"
            expected_scalar = "" if expected is None else str(expected)
            met = actual != expected_scalar
        elif operator == "in":
            if not isinstance(expected, list):
                return "unknown"
            met = actual in [str(value) for value in expected]
        elif operator == "notEmpty":
            met = bool(actual.strip())
        else:
            return "unknown"
        all_met = all_met and met
    return "met" if all_met else "not_met"


def build_schema_response() -> Dict[str, Any]:
    """Build schema payload grouped by category."""
    category_map: Dict[str, Dict[str, Any]] = {}
    for category in get_category_definitions():
        category_map[category["category"]] = {**category, "fields": []}

    for key in sorted(_FIELD_DEFINITIONS.keys()):
        field = get_field_definition(key)
        category_map[field["category"]]["fields"].append(field)

    categories = sorted(category_map.values(), key=lambda item: item["display_order"])
    for category in categories:
        category["fields"] = sorted(
            category["fields"],
            key=lambda item: (item.get("display_order", 9999), item["key"]),
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "categories": categories,
    }


def _is_sensitive_key(key: str) -> bool:
    markers = ("KEY", "TOKEN", "SECRET", "PASSWORD")
    return key.endswith("_EXTRA_HEADERS") or any(marker in key for marker in markers)


def _infer_category(key: str) -> str:
    if key == "STOCK_LIST":
        return "base"
    if key.startswith("BACKTEST_"):
        return "backtest"
    if key.startswith(("GEMINI_", "OPENAI_", "ANTHROPIC_", "LITELLM_", "AIHUBMIX_", "DEEPSEEK_", "LLM_")):
        return "ai_model"
    if key.endswith("_PRIORITY") or key.startswith(
        (
            "TUSHARE",
            "TICKFLOW",
            "AKSHARE",
            "EFINANCE",
            "PYTDX",
            "BAOSTOCK",
            "YFINANCE",
            "TAVILY",
            "SERPAPI",
            "BRAVE",
            "BOCHA",
            "ANSPIRE",
            "SEARXNG",
            "NEWS_",
            "BIAS_",
        )
    ) or key in ("ENABLE_REALTIME_QUOTE", "ENABLE_CHIP_DISTRIBUTION"):
        return "data_source"
    if key.startswith((
        "WECHAT",
        "FEISHU",
        "TELEGRAM",
        "EMAIL",
        "PUSHOVER",
        "NTFY",
        "GOTIFY",
        "PUSHPLUS",
        "SERVERCHAN",
        "DINGTALK",
        "DISCORD",
        "SLACK",
        "CUSTOM_WEBHOOK",
        "WECOM",
        "ASTRBOT",
    )) or "WEBHOOK" in key:
        return "notification"
    if key.startswith(("LOG_", "SCHEDULE_", "WEBUI_", "HTTP_", "HTTPS_", "MAX_", "DEBUG", "MARKET_REVIEW_", "TRADING_DAY_", "ANALYSIS_DELAY")):
        return "system"
    return "uncategorized"


def _infer_data_type(key: str, value_hint: Optional[str]) -> str:
    if key.endswith("_TIME"):
        return "time"
    if key.endswith("_EXTRA_HEADERS"):
        return "json"
    if value_hint is None:
        return "string"

    lowered = value_hint.strip().lower()
    if lowered in {"true", "false"}:
        return "boolean"

    try:
        int(value_hint)
        return "integer"
    except (TypeError, ValueError):
        pass

    try:
        float(value_hint)
        return "number"
    except (TypeError, ValueError):
        pass

    if key in {"STOCK_LIST", "EMAIL_RECEIVERS", "CUSTOM_WEBHOOK_URLS"}:
        return "array"
    return "string"


def _infer_ui_control(data_type: str, key: str) -> str:
    if data_type == "json":
        return "textarea"
    if _is_sensitive_key(key):
        return "password"
    if data_type == "boolean":
        return "switch"
    if data_type in {"integer", "number"}:
        return "number"
    if data_type == "time":
        return "time"
    if data_type == "array":
        return "textarea"
    return "text"
