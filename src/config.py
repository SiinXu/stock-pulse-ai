# -*- coding: utf-8 -*-
"""
===================================
StockPulse configuration management.
===================================

Responsibilities:
1. Manage global configuration through a singleton.
2. Load sensitive settings from the configured environment file.
3. Provide typed access to resolved configuration values.
"""

import json
import importlib as _importlib
import logging
import os
import re
import sys as _sys
import types as _types
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import unquote, urlparse
from dotenv import load_dotenv, dotenv_values
from dataclasses import dataclass, field

from src.core.config_manager import unescape_compose_sensitive_env_value
from src.report_language import (
    is_supported_report_language_value,
    normalize_report_language,
)
from src.notification_routing import parse_notification_route_channels
from src.notification_noise import (
    NOTIFICATION_SEVERITIES,
    is_supported_notification_severity,
    parse_notification_quiet_hours,
    validate_notification_timezone,
)
from src.notification_contracts import (
    is_feishu_app_bot_configured,
    is_feishu_static_configured,
)
from src.services.stock_list_parser import split_stock_list
from src.utils.sanitize import log_safe_exception
from src.llm.backend_registry import (
    AUTO_AGENT_BACKEND_ID,
    GENERATION_ONLY_BACKEND_IDS,
    LOCAL_CLI_GENERATION_BACKEND_IDS,
    LITELLM_BACKEND_ID,
    OPENCODE_CLI_BACKEND_ID,
    SUPPORTED_AGENT_GENERATION_BACKENDS,
    SUPPORTED_AGENT_UI_BACKENDS,
    SUPPORTED_GENERATION_BACKENDS,
)
from src.llm.local_cli_backend import (
    DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY,
    DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
    DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES,
    DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS,
    MAX_GENERATION_BACKEND_MAX_CONCURRENCY,
    MAX_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
    MAX_LOCAL_CLI_OUTPUT_BYTES,
    MAX_LOCAL_CLI_TIMEOUT_SECONDS,
)
from src.llm import generation_params as llm_generation_params
from src.llm.provider_catalog_data import get_provider_ids, get_static_provider
from src.llm.hermes import (
    HERMES_DEFAULT_BASE_URL,
    HERMES_DEFAULT_MODEL,
    HERMES_DEFAULT_PROTOCOL,
    HermesConfigIssue,
    hermes_model_info,
    is_reserved_hermes_name,
    parse_hermes_channel,
    route_identity_candidates,
    route_deployment_origins,
    route_has_hermes,
)
from src.scheduler import normalize_schedule_times
from src.config_parts.binding import clone_function as _clone_config_function


def _load_or_reload_config_part(module_name: str):
    module = _sys.modules.get(module_name)
    if module is None:
        return _importlib.import_module(module_name)
    return _importlib.reload(module)


_config_defaults_module = _load_or_reload_config_part("src.config_parts.defaults")
_config_parsers_module = _load_or_reload_config_part("src.config_parts.parsers")

from src.config_parts.defaults import (
    AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE,
    AGENT_CONTEXT_COMPRESSION_PROFILES,
    AGENT_MAX_STEPS_DEFAULT,
    ANSPIRE_LLM_BASE_URL_DEFAULT,
    ANSPIRE_LLM_MODEL_DEFAULT,
    FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
    NEWS_STRATEGY_WINDOWS,
    PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT,
    PROMPT_CACHE_DIAGNOSTICS_LEVELS,
    SUPPORTED_LLM_CHANNEL_PROTOCOLS,
    TICKFLOW_KLINE_ADJUST_VALUES,
    AgentContextCompressionPreset,
    ConfigIssue,
    DEFAULT_ALPHASIFT_INSTALL_SPEC,
    _FALSEY_ENV_VALUES,
    _MANAGED_LITELLM_KEY_PROVIDERS,
    KRONOS_MODEL_SIZE_DEFAULT as _KRONOS_MODEL_SIZE_DEFAULT,
    KRONOS_MODEL_SIZES as _KRONOS_MODEL_SIZES,
    _has_gotify_base_url,
    _has_ntfy_topic_endpoint,
    normalize_tickflow_kline_adjust,
    parse_prompt_cache_diagnostics_level,
)
from src.config_parts.parsers import (
    LLM_EMPTY_API_KEY_HOSTNAMES,
    _get_litellm_provider,
    _matches_exact_route,
    _matches_route_set,
    _uses_direct_env_provider,
    canonicalize_llm_channel_protocol,
    channel_allows_empty_api_key,
    get_agent_context_compression_preset,
    get_configured_llm_models,
    get_effective_agent_models_to_try,
    get_effective_agent_primary_model,
    get_fixed_litellm_temperature,
    normalize_agent_context_compression_profile,
    normalize_agent_litellm_model,
    normalize_litellm_temperature,
    normalize_llm_channel_model,
    normalize_news_strategy_profile,
    parse_agent_context_compression_int,
    parse_env_bool,
    parse_env_float,
    parse_env_int,
    resolve_litellm_thinking_enabled,
    resolve_litellm_wire_model,
    resolve_llm_channel_protocol,
    resolve_news_window_days,
    resolve_unified_llm_temperature,
)

for _compat_name, _compat_value in tuple(globals().items()):
    if (
        isinstance(_compat_value, _types.FunctionType)
        and _compat_value.__module__ == __name__
        and _compat_value.__globals__ is not globals()
    ):
        globals()[_compat_name] = _clone_config_function(_compat_value, globals())

del _compat_name, _compat_value
_config_defaults_module._bind_config_facade(globals())

logger = logging.getLogger(__name__)


def setup_env(override: bool = False):
    """
    Initialize environment variables from .env file.

    Args:
        override: If True, overwrite existing environment variables with values
                  from .env file. Set to True when reloading config after updates.
                  Default is False to preserve behavior on initial load where
                  system environment variables take precedence.
    """
    Config._capture_bootstrap_runtime_env_overrides()
    # src/config.py -> src/ -> root
    env_file = os.getenv("ENV_FILE")
    if env_file:
        env_path = Path(env_file)
    else:
        env_path = Path(__file__).parent.parent / '.env'
    compose_sensitive_keys = ("CUSTOM_WEBHOOK_BODY_TEMPLATE",)
    preexisting_compose_sensitive_keys = {
        key for key in compose_sensitive_keys if key in os.environ
    }
    load_dotenv(dotenv_path=env_path, override=override)
    try:
        raw_env_values = dotenv_values(env_path, interpolate=False)
    except Exception as exc:  # pragma: no cover - defensive branch
        log_safe_exception(
            logger,
            "Raw environment file read failed",
            exc,
            error_code="raw_environment_file_read_failed",
            level=logging.WARNING,
        )
        return

    key = "CUSTOM_WEBHOOK_BODY_TEMPLATE"
    if key in raw_env_values and (
        override or key not in preexisting_compose_sensitive_keys
    ):
        raw_value = raw_env_values.get(key)
        os.environ[key] = unescape_compose_sensitive_env_value(
            key,
            "" if raw_value is None else str(raw_value),
        )


for _config_part_name in (
    "src.config_parts.loading",
    "src.config_parts.llm",
    "src.config_parts.runtime",
    "src.config_parts.validation",
):
    _load_or_reload_config_part(_config_part_name)

_config_model_module = _load_or_reload_config_part("src.config_parts.model")
Config = _config_model_module.Config
_config_model_module._bind_config_facade(globals())


# === Convenient Configuration Access Function ===
def get_config() -> Config:
    """获取全局配置实例的快捷方式"""
    return Config.get_instance()


# ============================================================
# Shared LLM helpers (used by both analyzer and agent/llm_adapter)
# ============================================================

def get_api_keys_for_model(model: str, config: Config) -> List[str]:
    """Return explicitly managed API keys for a litellm model (legacy path only).

    When llm_model_list is populated (channels / YAML), the Router handles key
    selection, so this function is not needed.  Kept for backward compat when
    no Router is built and a direct litellm.completion() call is needed.
    """
    provider = _get_litellm_provider(model)
    if provider in {"gemini", "vertex_ai"}:
        return [k for k in config.gemini_api_keys if k and len(k) >= 8]
    if provider == "anthropic":
        return [k for k in config.anthropic_api_keys if k and len(k) >= 8]
    if provider == "deepseek":
        return [k for k in config.deepseek_api_keys if k and len(k) >= 8]
    if provider == "openai":
        return [k for k in config.openai_api_keys if k and len(k) >= 8]
    # Other LiteLLM-native providers – API key resolved from env vars
    return []


def extra_litellm_params(model: str, config: Config) -> Dict[str, Any]:
    """Build extra litellm params for a model (legacy path only).

    When llm_model_list is populated, the Router already carries api_base
    and headers per-deployment, so this is not called.
    """
    params: Dict[str, Any] = {}
    # deepseek/ provider: litellm auto-resolves api_base, no manual override needed
    if model.startswith("deepseek/"):
        return params
    if model.startswith("openai/") or "/" not in model:
        if config.openai_base_url:
            params["api_base"] = config.openai_base_url
    return params


if __name__ == "__main__":
    # Print a minimal configuration-loading diagnostic.
    config = get_config()
    print("=== Configuration loading check ===")
    print(f"Watchlist: {config.stock_list}")
    print(f"Database path: {config.database_path}")
    print(f"Maximum workers: {config.max_workers}")
    print(f"Debug mode: {config.debug}")
    
    # Validate the resolved configuration.
    warnings = config.validate()
    if warnings:
        print("\nConfiguration warnings:")
        for w in warnings:
            print(f"  - {w}")
