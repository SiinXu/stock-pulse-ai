# -*- coding: utf-8 -*-
"""System configuration service for `.env` based settings."""

from __future__ import annotations

import io
import logging
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse, urlunparse

import requests

from src.config import (
    ANSPIRE_LLM_BASE_URL_DEFAULT,
    ANSPIRE_LLM_MODEL_DEFAULT,
    SUPPORTED_LLM_CHANNEL_PROTOCOLS,
    Config,
    _get_litellm_provider,
    _uses_direct_env_provider,
    canonicalize_llm_channel_protocol,
    channel_allows_empty_api_key,
    get_config as get_runtime_config,
    normalize_agent_litellm_model,
    normalize_news_strategy_profile,
    normalize_llm_channel_model,
    parse_env_bool,
    parse_env_int,
    resolve_news_window_days,
    resolve_llm_channel_protocol,
    setup_env,
)
from src.llm.hermes import (
    HERMES_DEFAULT_BASE_URL,
    HERMES_DEFAULT_MODEL,
    HERMES_DEFAULT_PROTOCOL,
    build_hermes_redaction_values,
    canonicalize_hermes_model_ref,
    canonicalize_hermes_base_url,
    is_masked_secret_placeholder,
    is_reserved_hermes_name,
    open_hermes_no_proxy_client,
    parse_hermes_channel,
)
from src.core.config_manager import ConfigManager, ConfigVersionMismatchError
from src.core.config_registry import (
    LLM_CHANNEL_FIELD_KEY_RE,
    build_schema_response,
    evaluate_config_conditions,
    get_category_definitions,
    get_contract_field_definitions,
    get_field_definition,
    get_registered_field_keys,
)
from src.llm.errors import call_litellm_with_param_recovery
from src.llm.backend_registry import (
    AUTO_AGENT_BACKEND_ID,
    CODEX_CLI_BACKEND_ID,
    GENERATION_ONLY_BACKEND_IDS,
    LOCAL_CLI_GENERATION_BACKEND_IDS,
    LITELLM_BACKEND_ID,
    normalize_backend_id,
)
from src.llm.generation_params import apply_litellm_generation_params
from src.llm.local_cli_backend import resolve_local_cli_preset
from src.llm.response_content import strip_leading_think_wrapper
from src.llm.provider_catalog import (
    build_connection_contract_values,
    get_connection_field_schema,
    get_unknown_connection_contract_fields,
    validate_connection_contract_values,
)
from src.notification_contracts import (
    FEISHU_APP_BOT_ENV_GROUP,
    FEISHU_WEBHOOK_ENV_GROUP,
    is_feishu_app_bot_env_configured,
    is_feishu_static_env_configured,
)
from src.notification_noise import validate_notification_timezone
from src.notification_sender.gotify_sender import resolve_gotify_message_endpoint
from src.notification_sender.ntfy_sender import resolve_ntfy_endpoint
from src.services.stock_list_parser import split_stock_list
from src.services.generation_backend_status_service import GenerationBackendStatusService
from src.services.config import (
    ConfigConflictService,
    EffectiveConfigResolver,
    ModelAssignmentValidator,
)
# Re-exported for api.v1.endpoints.system_config and tests.
from src.services.config import ConfigConflictError  # noqa: F401
from src.services.config import llm_channel_map
from src.utils.sanitize import (
    log_safe_exception,
    sanitize_diagnostic_text,
    sanitize_exception_chain,
)

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Raised when one or more submitted fields fail validation."""

    def __init__(self, issues: List[Dict[str, Any]]):
        super().__init__("Configuration validation failed")
        self.issues = issues


class ConfigImportError(Exception):
    """Raised when an imported `.env` payload is invalid."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def known_llm_provider_channel_names() -> frozenset:
    """Provider channel names that ship a built-in default endpoint.

    Derived from the authoritative provider catalog ids (``src.llm.provider_catalog``)
    so provider metadata has a single source of truth — enabled channels whose
    name matches a non-custom catalog provider are not treated as custom
    endpoints and are exempt from the explicit Base URL requirement. Uses the
    pure ``get_provider_ids()`` (static ids only, no ``src.config`` coupling) so
    it stays deterministic regardless of surrounding config/import state.
    """
    from src.llm.provider_catalog import get_provider_ids

    return frozenset(pid.lower() for pid in get_provider_ids() if pid.lower() != "custom")


@dataclass(frozen=True)
class _LLMDiagnostic:
    """Internal structured diagnosis for LLM test and discovery failures."""

    error_code: str
    retryable: bool
    message: str
    reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class SystemConfigService:
    """Service layer for reading, validating, and updating runtime configuration."""

    _ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    _GENERATION_BACKEND_STATUS_EXACT_KEYS = {
        "GENERATION_BACKEND",
        "GENERATION_FALLBACK_BACKEND",
        "GENERATION_BACKEND_TIMEOUT_SECONDS",
        "GENERATION_BACKEND_MAX_OUTPUT_BYTES",
        "GENERATION_BACKEND_MAX_CONCURRENCY",
        "LOCAL_CLI_BACKEND_MAX_CONCURRENCY",
        "OPENCODE_CLI_MODEL",
        "LITELLM_CONFIG",
        "LITELLM_MODEL",
        "LITELLM_FALLBACK_MODELS",
        "GEMINI_API_KEY",
        "GEMINI_API_KEYS",
        "GEMINI_MODEL",
        "GEMINI_MODEL_FALLBACK",
        "GEMINI_TEMPERATURE",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_KEYS",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_TEMPERATURE",
        "ANTHROPIC_MAX_TOKENS",
        "OPENAI_API_KEY",
        "OPENAI_API_KEYS",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_VISION_MODEL",
        "OPENAI_TEMPERATURE",
        "OLLAMA_API_BASE",
        "OLLAMA_MODEL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_KEYS",
        "AIHUBMIX_KEY",
        "ANSPIRE_LLM_ENABLED",
        "ANSPIRE_LLM_BASE_URL",
        "ANSPIRE_LLM_MODEL",
        "ANSPIRE_API_KEYS",
    }
    _GENERATION_BACKEND_STATUS_LLM_CHANNEL_RE = LLM_CHANNEL_FIELD_KEY_RE

    _LLM_CAPABILITY_ORDER: Tuple[str, ...] = ("json", "tools", "stream", "vision")
    _LLM_STREAM_CHUNK_LIMIT = 8
    _LLM_EMPTY_API_KEY_ADAPTER_SENTINEL = "dsa-local-no-key"
    _WEB_SETTINGS_LLM_CHANNEL_SUPPORT_KEY_RE = LLM_CHANNEL_FIELD_KEY_RE
    _CONNECTION_SECRET_SCOPE_SUFFIXES: Tuple[str, ...] = (
        "API_KEY",
        "API_KEYS",
        "EXTRA_HEADERS",
    )
    _LLM_CAPABILITY_PROBE_IMAGE = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )

    _NOTIFICATION_TEST_CHANNELS: Tuple[str, ...] = (
        "wechat",
        "dingtalk",
        "feishu",
        "telegram",
        "email",
        "pushover",
        "ntfy",
        "gotify",
        "pushplus",
        "serverchan3",
        "custom",
        "discord",
        "slack",
        "astrbot",
    )
    _NOTIFICATION_TEST_KEY_MAP: Dict[str, Tuple[str, str]] = {
        "WECHAT_WEBHOOK_URL": ("wechat_webhook_url", "string"),
        "WECHAT_MSG_TYPE": ("wechat_msg_type", "string"),
        "WECHAT_MAX_BYTES": ("wechat_max_bytes", "int"),
        "FEISHU_WEBHOOK_URL": ("feishu_webhook_url", "string"),
        "FEISHU_WEBHOOK_SECRET": ("feishu_webhook_secret", "string"),
        "FEISHU_WEBHOOK_KEYWORD": ("feishu_webhook_keyword", "string"),
        "FEISHU_MAX_BYTES": ("feishu_max_bytes", "int"),
        "FEISHU_SEND_AS_FILE": ("feishu_send_as_file", "bool"),
        "DINGTALK_WEBHOOK_URL": ("dingtalk_webhook_url", "string"),
        "DINGTALK_SECRET": ("dingtalk_secret", "string"),
        "FEISHU_APP_ID": ("feishu_app_id", "string"),
        "FEISHU_APP_SECRET": ("feishu_app_secret", "string"),
        "FEISHU_CHAT_ID": ("feishu_chat_id", "string"),
        "FEISHU_RECEIVE_ID_TYPE": ("feishu_receive_id_type", "string"),
        "FEISHU_DOMAIN": ("feishu_domain", "string"),
        "TELEGRAM_BOT_TOKEN": ("telegram_bot_token", "string"),
        "TELEGRAM_CHAT_ID": ("telegram_chat_id", "string"),
        "TELEGRAM_MESSAGE_THREAD_ID": ("telegram_message_thread_id", "string"),
        "EMAIL_SENDER": ("email_sender", "string"),
        "EMAIL_SENDER_NAME": ("email_sender_name", "string"),
        "EMAIL_PASSWORD": ("email_password", "string"),
        "EMAIL_RECEIVERS": ("email_receivers", "csv"),
        "PUSHOVER_USER_KEY": ("pushover_user_key", "string"),
        "PUSHOVER_API_TOKEN": ("pushover_api_token", "string"),
        "NTFY_URL": ("ntfy_url", "string"),
        "NTFY_TOKEN": ("ntfy_token", "string"),
        "GOTIFY_URL": ("gotify_url", "string"),
        "GOTIFY_TOKEN": ("gotify_token", "string"),
        "PUSHPLUS_TOKEN": ("pushplus_token", "string"),
        "PUSHPLUS_TOPIC": ("pushplus_topic", "string"),
        "SERVERCHAN3_SENDKEY": ("serverchan3_sendkey", "string"),
        "CUSTOM_WEBHOOK_URLS": ("custom_webhook_urls", "csv"),
        "CUSTOM_WEBHOOK_BEARER_TOKEN": ("custom_webhook_bearer_token", "string"),
        "CUSTOM_WEBHOOK_BODY_TEMPLATE": ("custom_webhook_body_template", "string"),
        "WEBHOOK_VERIFY_SSL": ("webhook_verify_ssl", "bool"),
        "DISCORD_WEBHOOK_URL": ("discord_webhook_url", "string"),
        "DISCORD_BOT_TOKEN": ("discord_bot_token", "string"),
        "DISCORD_MAIN_CHANNEL_ID": ("discord_main_channel_id", "string"),
        "DISCORD_CHANNEL_ID": ("discord_main_channel_id", "string"),
        "DISCORD_MAX_WORDS": ("discord_max_words", "int"),
        "SLACK_WEBHOOK_URL": ("slack_webhook_url", "string"),
        "SLACK_BOT_TOKEN": ("slack_bot_token", "string"),
        "SLACK_CHANNEL_ID": ("slack_channel_id", "string"),
        "ASTRBOT_URL": ("astrbot_url", "string"),
        "ASTRBOT_TOKEN": ("astrbot_token", "string"),
    }
    _NOTIFICATION_REQUIRED_KEY_GROUPS: Dict[str, Tuple[Tuple[str, ...], ...]] = {
        "wechat": (("WECHAT_WEBHOOK_URL",),),
        "dingtalk": (("DINGTALK_WEBHOOK_URL",),),
        "feishu": (FEISHU_WEBHOOK_ENV_GROUP, FEISHU_APP_BOT_ENV_GROUP),
        "telegram": (("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),),
        "email": (("EMAIL_SENDER", "EMAIL_PASSWORD"),),
        "pushover": (("PUSHOVER_USER_KEY", "PUSHOVER_API_TOKEN"),),
        "ntfy": (("NTFY_URL",),),
        "gotify": (("GOTIFY_URL", "GOTIFY_TOKEN"),),
        "pushplus": (("PUSHPLUS_TOKEN",),),
        "serverchan3": (("SERVERCHAN3_SENDKEY",),),
        "custom": (("CUSTOM_WEBHOOK_URLS",),),
        "discord": (("DISCORD_WEBHOOK_URL",), ("DISCORD_BOT_TOKEN", "DISCORD_MAIN_CHANNEL_ID"), ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID")),
        "slack": (("SLACK_WEBHOOK_URL",), ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID")),
        "astrbot": (("ASTRBOT_URL",),),
    }
    _NOTIFICATION_TEST_TARGET_KEYS: Dict[str, Tuple[str, ...]] = {
        "wechat": ("WECHAT_WEBHOOK_URL",),
        "dingtalk": ("DINGTALK_WEBHOOK_URL",),
        "feishu": FEISHU_WEBHOOK_ENV_GROUP + FEISHU_APP_BOT_ENV_GROUP,
        "telegram": ("TELEGRAM_BOT_TOKEN",),
        "email": ("EMAIL_RECEIVERS", "EMAIL_SENDER"),
        "pushover": ("PUSHOVER_USER_KEY",),
        "ntfy": ("NTFY_URL",),
        "gotify": ("GOTIFY_URL",),
        "pushplus": ("PUSHPLUS_TOPIC",),
        "serverchan3": ("SERVERCHAN3_SENDKEY",),
        "custom": ("CUSTOM_WEBHOOK_URLS",),
        "discord": ("DISCORD_WEBHOOK_URL", "DISCORD_MAIN_CHANNEL_ID", "DISCORD_CHANNEL_ID"),
        "slack": ("SLACK_WEBHOOK_URL", "SLACK_CHANNEL_ID"),
        "astrbot": ("ASTRBOT_URL",),
    }



_service_part_modules = __import__("sys").modules
_service_binding_module_name = "src.services.system_config_service_parts.binding"
if _service_binding_module_name in _service_part_modules:
    _service_binding_module = __import__("importlib").reload(
        _service_part_modules[_service_binding_module_name]
    )
else:
    _service_binding_module = __import__(
        _service_binding_module_name,
        fromlist=("clone_member",),
    )

for _service_part_module_name, _service_part_class_name in (
    ("src.services.system_config_service_parts.core", "_SystemConfigCoreMethods"),
    ("src.services.system_config_service_parts.llm_operations", "_SystemConfigLLMOperationsMethods"),
    ("src.services.system_config_service_parts.updates_validation", "_SystemConfigUpdateMethods"),
    ("src.services.system_config_service_parts.notifications", "_SystemConfigNotificationMethods"),
    ("src.services.system_config_service_parts.setup", "_SystemConfigSetupMethods"),
    ("src.services.system_config_service_parts.llm_validation", "_SystemConfigLLMValidationMethods"),
):
    if _service_part_module_name in _service_part_modules:
        _service_part_module = __import__("importlib").reload(
            _service_part_modules[_service_part_module_name]
        )
    else:
        _service_part_module = __import__(
            _service_part_module_name,
            fromlist=(_service_part_class_name,),
        )
    _service_part_class = getattr(_service_part_module, _service_part_class_name)
    for _service_member_name, _service_member in vars(_service_part_class).items():
        if _service_member_name in {
            "__module__",
            "__qualname__",
            "__doc__",
            "__dict__",
            "__weakref__",
        }:
            continue
        if _service_member_name == "__annotations__":
            SystemConfigService.__annotations__.update(_service_member)
            continue
        _service_member = _service_binding_module.clone_member(
            _service_member,
            globals(),
            module_name=__name__,
            owner_name="SystemConfigService",
            member_name=_service_member_name,
        )
        setattr(SystemConfigService, _service_member_name, _service_member)

del (
    _service_binding_module,
    _service_binding_module_name,
    _service_member,
    _service_member_name,
    _service_part_class,
    _service_part_class_name,
    _service_part_module,
    _service_part_module_name,
    _service_part_modules,
)
