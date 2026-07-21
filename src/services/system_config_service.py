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

    def __init__(
        self,
        manager: Optional[ConfigManager] = None,
        runtime_scheduler: Optional[Any] = None,
        runtime_config_provider: Optional[Callable[[], Config]] = None,
    ):
        self._manager = manager or ConfigManager()
        self._conflict = ConfigConflictService(self._manager)
        self._runtime_scheduler = runtime_scheduler
        # Keep the provider rather than a Config object so Config.reset_instance()
        # is reflected on the next read.
        self._runtime_config_provider = runtime_config_provider or get_runtime_config

    def get_schema(self) -> Dict[str, Any]:
        """Return grouped schema metadata for UI rendering."""
        return build_schema_response()

    @staticmethod
    def _reload_runtime_singletons() -> None:
        """Reset runtime singleton services after config reload."""
        from src.agent.tools.data_tools import reset_fetcher_manager
        from src.search_service import reset_search_service

        reset_fetcher_manager()
        reset_search_service()

    @classmethod
    def _build_display_config_map(cls, raw_config_map: Dict[str, str]) -> Dict[str, str]:
        return EffectiveConfigResolver.build_display_config_map(raw_config_map)

    @classmethod
    def _build_runtime_display_config_map(cls, saved_config_map: Dict[str, str]) -> Dict[str, str]:
        return EffectiveConfigResolver.build_runtime_display_config_map(saved_config_map)

    def get_config(self, include_schema: bool = True, mask_token: str = "******") -> Dict[str, Any]:
        """Return display config values with mask metadata for server-masked fields."""
        saved_config_map = self._build_display_config_map(self._manager.read_config_map())
        runtime_config_map = self._build_runtime_display_config_map(saved_config_map)
        config_map = {
            **runtime_config_map,
            **saved_config_map,
        }
        configured_notification_channels = self._detect_configured_notification_channels()
        registered_keys = set(get_registered_field_keys())
        all_keys = set(config_map.keys()) | registered_keys
        if include_schema:
            all_keys = EffectiveConfigResolver.get_schema_config_keys(config_map, registered_keys)

        category_orders = {
            item["category"]: item["display_order"]
            for item in get_category_definitions()
        }

        schema_by_key: Dict[str, Dict[str, Any]] = {
            key: get_field_definition(key, config_map.get(key, ""))
            for key in all_keys
        }

        items: List[Dict[str, Any]] = []
        for key in all_keys:
            raw_value_exists = key in saved_config_map
            raw_value = config_map.get(key, "")
            field_schema = schema_by_key[key]
            display_value = EffectiveConfigResolver.resolve_display_value(
                raw_value, field_schema, raw_value_exists
            )
            is_masked = False
            if field_schema.get("is_sensitive", False) and display_value:
                display_value = mask_token
                is_masked = True
            item: Dict[str, Any] = {
                "key": key,
                "value": display_value,
                "raw_value_exists": raw_value_exists,
                "is_masked": is_masked,
            }
            if include_schema:
                item["schema"] = field_schema
            items.append(item)

        items.sort(
            key=lambda item: (
                category_orders.get(schema_by_key[item["key"]].get("category", "uncategorized"), 999),
                schema_by_key[item["key"]].get("display_order", 9999),
                item["key"],
            )
        )

        return {
            "config_version": self._manager.get_config_version(),
            "mask_token": mask_token,
            "items": items,
            "configured_notification_channels": configured_notification_channels,
            "updated_at": self._manager.get_updated_at(),
        }

    def _detect_configured_notification_channels(self) -> List[str]:
        """Return channels from the live runtime Config without exposing credentials."""
        from src.notification import NotificationService

        config = self._runtime_config_provider()
        return [
            channel.value
            for channel in NotificationService.detect_configured_channels(config)
        ]

    def validate(self, items: Sequence[Dict[str, str]], mask_token: str = "******") -> Dict[str, Any]:
        """Validate submitted items without writing to `.env`."""
        issues = self._collect_issues(items=items, mask_token=mask_token)
        valid = not any(issue["severity"] == "error" for issue in issues)
        return {
            "valid": valid,
            "issues": issues,
        }

    def test_notification_channel(
        self,
        *,
        channel: str,
        items: Sequence[Dict[str, str]],
        mask_token: str = "******",
        title: str = "StockPulse 通知测试",
        content: str = "这是一条来自 StockPulse Web 设置页的通知测试消息。",
        timeout_seconds: float = 20.0,
    ) -> Dict[str, Any]:
        """Send one real notification test without persisting submitted values."""
        normalized_channel = (channel or "").strip().lower()
        if normalized_channel not in self._NOTIFICATION_TEST_CHANNELS:
            raise ValueError(f"Unsupported notification channel: {channel}")

        effective_map = self._build_notification_test_effective_map(
            items=items,
            mask_token=mask_token,
        )
        missing = self._get_missing_notification_test_keys(normalized_channel, effective_map)
        if missing:
            return self._build_notification_test_result(
                success=False,
                message=f"通知渠道配置不完整，缺少: {', '.join(missing)}",
                error_code="config_missing",
                stage="config_validation",
                retryable=False,
                latency_ms=None,
                attempts=[],
            )
        invalid_message = self._get_invalid_notification_test_config_message(
            normalized_channel,
            effective_map,
        )
        if invalid_message:
            return self._build_notification_test_result(
                success=False,
                message=invalid_message,
                error_code="config_invalid",
                stage="config_validation",
                retryable=False,
                latency_ms=None,
                attempts=[],
            )

        config = self._build_notification_config(effective_map)
        try:
            return self._dispatch_notification_test(
                channel=normalized_channel,
                config=config,
                effective_map=effective_map,
                title=title.strip(),
                content=content.strip(),
                timeout_seconds=float(timeout_seconds),
            )
        except Exception as exc:
            redaction_values = [
                value
                for key, value in effective_map.items()
                if get_field_definition(key, value_hint=str(value)).get("is_sensitive")
            ]
            safe_error = sanitize_exception_chain(
                exc,
                redaction_values=redaction_values,
            )
            log_safe_exception(
                logger,
                "Notification channel test failed",
                exc,
                error_code="notification_channel_test_failed",
                level=logging.WARNING,
                context={"channel": normalized_channel},
                redaction_values=redaction_values,
            )
            error_code, retryable = self._classify_notification_exception(exc)
            return self._build_notification_test_result(
                success=False,
                message=safe_error,
                error_code=error_code,
                stage="notification_send",
                retryable=retryable,
                latency_ms=None,
                attempts=[
                    {
                        "channel": normalized_channel,
                        "success": False,
                        "message": safe_error,
                        "target": self._resolve_notification_test_target(normalized_channel, effective_map),
                        "error_code": error_code,
                        "stage": "notification_send",
                        "retryable": retryable,
                        "latency_ms": None,
                    }
                ],
            )

    def get_setup_status(self) -> Dict[str, Any]:
        """Return read-only first-run setup status without mutating runtime state."""
        effective_map = self._build_setup_effective_config_map()
        llm_check = self._build_setup_primary_llm_check(effective_map)
        agent_check = self._build_setup_agent_llm_check(effective_map, llm_check)
        checks = [
            llm_check,
            agent_check,
            self._build_setup_stock_list_check(effective_map),
            self._build_setup_notification_check(effective_map),
            self._build_setup_storage_check(effective_map),
        ]

        required_missing = [
            check["key"]
            for check in checks
            if check["required"] and check["status"] == "needs_action"
        ]
        smoke_blocking_missing = [
            check["key"]
            for check in checks
            if check["key"] in {"llm_primary", "stock_list"}
            and check["status"] == "needs_action"
        ]
        return {
            "is_complete": not required_missing,
            "ready_for_smoke": not smoke_blocking_missing,
            "required_missing_keys": required_missing,
            "next_step_key": required_missing[0] if required_missing else None,
            "checks": checks,
        }

    def get_llm_config_mode_status(self) -> Dict[str, Any]:
        """Return which model config source is requested vs effective."""
        saved_config_map = self._build_display_config_map(self._manager.read_config_map())
        runtime_config_map = self._build_runtime_display_config_map(saved_config_map)
        effective_map = {**runtime_config_map, **saved_config_map}
        return self._resolve_llm_config_mode_status(effective_map)

    def get_available_models(
        self, items: Optional[Sequence[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Return the model routes declared by currently-enabled sources.

        Each entry pairs the canonical backend route (what LITELLM_MODEL etc.
        must store) with a display name and its owning connection/provider, so
        Web model selectors let users pick a display name while the system keeps
        the exact route. The route set is authoritative (matches validation);
        connection/provider are best-effort grouping metadata.
        """
        saved_config_map = self._build_display_config_map(self._manager.read_config_map())
        runtime_config_map = self._build_runtime_display_config_map(saved_config_map)
        effective_map = {**runtime_config_map, **saved_config_map}
        if items:
            for item in items:
                key = str(item.get("key", "")).strip().upper()
                if key:
                    effective_map[key] = str(item.get("value", ""))

        yaml_routes = SystemConfigService._collect_yaml_models_from_map(effective_map)

        # Resolve a connection to its authoritative catalog provider so selectors
        # can group models by provider without a second frontend list.
        from src.llm.model_ref import canonicalize_connection_id, encode_model_ref
        from src.llm.provider_catalog import get_provider_catalog

        provider_label_by_id = {
            str(entry["id"]).lower(): str(entry["label"]) for entry in get_provider_catalog()
        }

        def _resolve_provider(connection_name: str) -> Tuple[str, str]:
            _provider, pid, _explicit = self._resolve_connection_provider(
                effective_map,
                connection_name,
            )
            if pid not in provider_label_by_id:
                pid = "custom"
            return pid, provider_label_by_id.get(pid, pid)

        # YAML aliases do not expose a Connection identity. Preserve their route
        # contract and mark the route itself as the legacy-compatible model_ref.
        if yaml_routes:
            return {
                "models": [
                    {
                        "model_ref": route,
                        "route": route,
                        "display": route,
                        "connection": None,
                        "connection_id": None,
                        "connection_name": None,
                        "provider": None,
                        "provider_id": None,
                        "provider_label": None,
                        "available": True,
                    }
                    for route in dict.fromkeys(yaml_routes)
                ]
            }

        models: List[Dict[str, Any]] = []
        for raw_name in (effective_map.get("LLM_CHANNELS") or "").split(","):
            name = raw_name.strip()
            if not name:
                continue
            connection_id = canonicalize_connection_id(name)
            prefix = f"LLM_{name.upper()}"
            enabled_raw = effective_map.get(f"{prefix}_ENABLED")
            if name.lower() == "anspire" and not (enabled_raw or "").strip():
                enabled_raw = effective_map.get("ANSPIRE_LLM_ENABLED")
            if not parse_env_bool(enabled_raw, default=True):
                continue
            protocol, base_url = self._resolve_connection_transport(
                effective_map,
                name,
            )
            protocol = protocol or "openai"
            provider_id, provider_label = _resolve_provider(name)
            connection_name = (
                effective_map.get(f"{prefix}_DISPLAY_NAME") or name
            ).strip()
            seen_routes: Set[str] = set()
            for raw_model in (effective_map.get(f"{prefix}_MODELS") or "").split(","):
                model = raw_model.strip()
                if not model:
                    continue
                route = normalize_llm_channel_model(model, protocol, base_url)
                if not route or route in seen_routes:
                    continue
                seen_routes.add(route)
                models.append({
                    "model_ref": encode_model_ref(connection_id, route),
                    "route": route,
                    "display": model,
                    "connection": connection_id,
                    "connection_id": connection_id,
                    "connection_name": connection_name,
                    # `provider` stays the protocol for back-compat; provider_id/label
                    # are the authoritative Catalog Provider for display/grouping.
                    "provider": protocol,
                    "provider_id": provider_id,
                    "provider_label": provider_label,
                    "available": True,
                })
        return {"models": models}

    @staticmethod
    def _resolve_connection_provider(
        effective_map: Dict[str, str],
        connection_name: str,
    ) -> Tuple[Optional[Dict[str, Any]], str, bool]:
        return llm_channel_map.resolve_connection_provider(effective_map, connection_name)

    @staticmethod
    def _resolve_connection_transport(
        effective_map: Dict[str, str],
        connection_name: str,
    ) -> Tuple[str, str]:
        return llm_channel_map.resolve_connection_transport(effective_map, connection_name)

    @staticmethod
    def _resolve_request_provider(
        *,
        provider_id: Optional[str],
        protocol: str,
        base_url: str,
    ) -> Tuple[Optional[Dict[str, Any]], str, str, Optional[Dict[str, Any]]]:
        """Apply explicit Catalog identity to an unsaved Connection request."""
        normalized_provider_id = str(provider_id or "").strip().lower()
        if not normalized_provider_id:
            return None, protocol, base_url, None

        from src.llm.provider_catalog import get_provider

        provider = get_provider(normalized_provider_id)
        if provider is None:
            return None, protocol, base_url, {
                "key": "provider_id",
                "code": "invalid_provider",
                "message": "The model connection references an unknown Provider",
                "severity": "error",
                "expected": "provider id from the model provider catalog",
                "actual": normalized_provider_id,
            }

        if not provider["is_custom"]:
            protocol = str(provider["protocol"])
            if not base_url.strip():
                base_url = str(provider["default_base_url"])
        return provider, protocol, base_url, None

    _LEGACY_LLM_PROVIDER_KEYS = (
        "OPENAI_API_KEY", "OPENAI_API_KEYS", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS",
        "GEMINI_API_KEY", "GEMINI_API_KEYS", "DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS",
        "AIHUBMIX_KEY",
    )

    @classmethod
    def _resolve_llm_config_mode_status(cls, effective_map: Dict[str, str]) -> Dict[str, Any]:
        requested = (effective_map.get("LLM_CONFIG_MODE") or "").strip().lower() or "auto"
        if requested not in ("auto", "channels", "yaml", "legacy"):
            requested = "auto"
        has_yaml = bool((effective_map.get("LITELLM_CONFIG") or "").strip())
        has_channels = bool((effective_map.get("LLM_CHANNELS") or "").strip())
        has_legacy = any((effective_map.get(k) or "").strip() for k in cls._LEGACY_LLM_PROVIDER_KEYS)
        detected = [
            name for name, present in (("yaml", has_yaml), ("channels", has_channels), ("legacy", has_legacy))
            if present
        ]

        issues: List[Dict[str, Any]] = []
        if requested == "auto":
            effective = next((cand for cand in ("yaml", "channels", "legacy") if cand in detected), None)
        else:
            effective = requested
            if requested not in detected:
                issues.append({
                    "key": "LLM_CONFIG_MODE",
                    "code": "forced_mode_no_config",
                    "severity": "warning",
                    "message": f"LLM_CONFIG_MODE={requested} is active but no {requested} configuration was found.",
                    "expected": f"configured {requested} source",
                    "actual": ",".join(detected) or "none",
                })

        overridden = [source for source in detected if source != effective]
        return {
            "requested_mode": requested,
            "effective_mode": effective,
            "detected_sources": detected,
            "overridden_sources": overridden,
            "issues": issues,
        }

    # (channel, protocol, base_url_key, api_key_fields, model_field, default_base_url, default_model)
    _LEGACY_CHANNEL_SPECS = (
        ("openai", "openai", "OPENAI_BASE_URL", ("OPENAI_API_KEYS", "OPENAI_API_KEY"), "OPENAI_MODEL", "", "gpt-5.5"),
        ("anthropic", "anthropic", None, ("ANTHROPIC_API_KEYS", "ANTHROPIC_API_KEY"), "ANTHROPIC_MODEL", "", "claude-sonnet-4-6"),
        ("gemini", "gemini", None, ("GEMINI_API_KEYS", "GEMINI_API_KEY"), "GEMINI_MODEL", "", "gemini-3.1-pro-preview"),
        ("deepseek", "deepseek", None, ("DEEPSEEK_API_KEYS", "DEEPSEEK_API_KEY"), None, "", "deepseek-chat"),
        ("aihubmix", "openai", None, ("AIHUBMIX_KEY",), None, "https://aihubmix.com/v1", "gpt-5.5"),
    )

    @classmethod
    def _build_legacy_channels_migration(
        cls, raw_map: Dict[str, str]
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """Turn detected legacy provider keys into channel update items."""
        items: List[Dict[str, str]] = []
        channels: List[Dict[str, str]] = []
        for name, protocol, base_url_key, api_key_fields, model_field, default_base_url, default_model in cls._LEGACY_CHANNEL_SPECS:
            api_key = ""
            for field_name in api_key_fields:
                api_key = (raw_map.get(field_name) or "").strip()
                if api_key:
                    break
            if not api_key:
                continue
            prefix = f"LLM_{name.upper()}"
            base_url = ((raw_map.get(base_url_key) if base_url_key else "") or "").strip() or default_base_url
            model = ((raw_map.get(model_field) if model_field else "") or "").strip() or default_model
            items.append({"key": f"{prefix}_PROVIDER", "value": name})
            items.append({"key": f"{prefix}_PROTOCOL", "value": protocol})
            if base_url:
                items.append({"key": f"{prefix}_BASE_URL", "value": base_url})
            items.append({"key": f"{prefix}_API_KEY", "value": api_key})
            items.append({"key": f"{prefix}_MODELS", "value": model})
            items.append({"key": f"{prefix}_ENABLED", "value": "true"})
            channels.append({"name": name, "protocol": protocol, "base_url": base_url, "model": model})
        if channels:
            items.insert(0, {"key": "LLM_CHANNELS", "value": ",".join(entry["name"] for entry in channels)})
            items.append({"key": "LLM_CONFIG_MODE", "value": "channels"})
        return items, channels

    def preview_legacy_channels_migration(self) -> Dict[str, Any]:
        """Return a redacted preview of the Legacy -> Channels migration."""
        raw_map = {str(key).upper(): value for key, value in self._manager.read_config_map().items()}
        _items, channels = self._build_legacy_channels_migration(raw_map)
        return {"channels": channels}

    def apply_legacy_channels_migration(
        self, config_version: str, mask_token: str = "******"
    ) -> Dict[str, Any]:
        """Copy detected legacy provider config into channels and switch mode."""
        raw_map = {str(key).upper(): value for key, value in self._manager.read_config_map().items()}
        items, channels = self._build_legacy_channels_migration(raw_map)
        if not channels:
            raise ConfigValidationError(issues=[{
                "key": "LLM_CHANNELS",
                "code": "no_legacy_config",
                "severity": "error",
                "message": "No legacy provider configuration was found to migrate.",
                "expected": "at least one legacy provider key",
                "actual": "none",
            }])
        return self.update(config_version=config_version, items=items, mask_token=mask_token)

    def get_generation_backend_status(self) -> Dict[str, Any]:
        """Return cheap generation backend status for saved/runtime config only."""
        effective_map = self._build_generation_backend_base_map()
        service = GenerationBackendStatusService(
            effective_map=effective_map,
            validation_issues=self._collect_generation_backend_issues_from_map(effective_map),
        )
        return service.get_status()

    def preview_generation_backend_status(
        self,
        *,
        items: Sequence[Dict[str, str]],
        mask_token: str = "******",
    ) -> Dict[str, Any]:
        """Return cheap generation backend status for unsaved settings draft."""
        issues = self._collect_generation_backend_issues(items=items, mask_token=mask_token)
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            raise ConfigValidationError(issues=errors)
        effective_map = self._build_generation_backend_effective_map(
            items=items,
            mask_token=mask_token,
        )
        service = GenerationBackendStatusService(
            effective_map=effective_map,
            validation_issues=issues,
        )
        return service.get_status()

    def test_generation_backend(
        self,
        *,
        backend_id: Optional[str] = None,
        mode: str = "json",
        items: Sequence[Dict[str, str]] = (),
        mask_token: str = "******",
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run an explicit generation backend smoke test without persisting config."""
        issues = self._collect_generation_backend_issues(items=items, mask_token=mask_token)
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            raise ConfigValidationError(issues=errors)
        effective_map = self._build_generation_backend_effective_map(
            items=items,
            mask_token=mask_token,
        )
        service = GenerationBackendStatusService(
            effective_map=effective_map,
            validation_issues=issues,
        )
        return service.smoke_test(
            backend_id=backend_id,
            mode=mode,
            timeout_seconds=timeout_seconds,
        )

    def export_env(self) -> Dict[str, Any]:
        """Return the raw active `.env` content for backup."""
        if self._manager.env_path.exists():
            content = self._manager.env_path.read_text(encoding="utf-8")
        else:
            content = ""

        return {
            "content": content,
            "config_version": self._manager.get_config_version(),
            "updated_at": self._manager.get_updated_at(),
        }

    def export_desktop_env(self) -> Dict[str, Any]:
        """Return the raw active `.env` content for desktop backup compatibility."""
        return self.export_env()

    def import_env(
        self,
        *,
        config_version: str,
        content: str,
        reload_now: bool = True,
    ) -> Dict[str, Any]:
        """Merge imported `.env` assignments into the active config."""
        self._conflict.guard_version(config_version)

        updates = self._parse_imported_env_content(content)
        return self.update(
            config_version=config_version,
            items=updates,
            mask_token="__DSA_IMPORT_LITERAL_MASK__",
            reload_now=reload_now,
        )

    def import_desktop_env(
        self,
        *,
        config_version: str,
        content: str,
        reload_now: bool = True,
    ) -> Dict[str, Any]:
        """Merge imported `.env` assignments for desktop backup compatibility."""
        return self.import_env(
            config_version=config_version,
            content=content,
            reload_now=reload_now,
        )

    def _resolve_hermes_saved_secret(
        self,
        *,
        channel_name: str,
        protocol: str,
        base_url: str,
        submitted_api_key: str,
        use_saved_secret: bool,
        stage: str,
    ) -> Tuple[Optional[str], Dict[str, Any], Set[str]]:
        """Resolve a saved Hermes key only when the submitted endpoint is unchanged."""

        redaction_values = self._build_redaction_values(submitted_api_key)
        if not use_saved_secret:
            return submitted_api_key, {}, redaction_values

        if not is_reserved_hermes_name(channel_name):
            return None, self._build_llm_channel_result(
                success=False,
                message="Saved secret scope mismatch",
                error="Saved Hermes secret can only be used with the reserved hermes channel",
                stage=stage,
                error_code="saved_secret_scope_mismatch",
                retryable=False,
                details={"reason": "channel_identity_mismatch"},
                resolved_protocol=None,
                models=[] if stage == "model_discovery" else None,
                latency_ms=None,
                redaction_values=redaction_values,
            ), redaction_values

        saved_map = self._manager.read_config_map()
        saved_key = (saved_map.get("LLM_HERMES_API_KEY") or "").strip()
        if not saved_key or is_masked_secret_placeholder(saved_key):
            error_code = (
                "runtime_secret_not_reusable"
                if is_masked_secret_placeholder(saved_key) or (os.environ.get("LLM_HERMES_API_KEY") or "").strip()
                else "missing_saved_secret"
            )
            return None, self._build_llm_channel_result(
                success=False,
                message=(
                    "Runtime Hermes secret is not reusable"
                    if error_code == "runtime_secret_not_reusable"
                    else "Missing saved Hermes secret"
                ),
                error=(
                    "Runtime-injected LLM_HERMES_API_KEY cannot be reused from the settings test flow"
                    if error_code == "runtime_secret_not_reusable"
                    else "No saved LLM_HERMES_API_KEY is available for this endpoint"
                ),
                stage=stage,
                error_code=error_code,
                retryable=False,
                details={"reason": error_code},
                resolved_protocol=None,
                models=[] if stage == "model_discovery" else None,
                latency_ms=None,
                redaction_values=redaction_values,
            ), redaction_values

        redaction_values.update(self._build_redaction_values(saved_key))
        saved_protocol = (saved_map.get("LLM_HERMES_PROTOCOL") or "openai").strip()
        saved_base_url = (saved_map.get("LLM_HERMES_BASE_URL") or "").strip()
        try:
            submitted_protocol = (protocol or "openai").strip().lower() or "openai"
            saved_protocol_canonical = (saved_protocol or "openai").strip().lower() or "openai"
            submitted_base = canonicalize_hermes_base_url(base_url)
            saved_base = canonicalize_hermes_base_url(saved_base_url)
        except ValueError as exc:
            return None, self._build_llm_channel_result(
                success=False,
                message="Saved secret scope mismatch",
                error=str(exc),
                stage=stage,
                error_code="saved_secret_scope_mismatch",
                retryable=False,
                details={"reason": "invalid_hermes_endpoint"},
                resolved_protocol=None,
                models=[] if stage == "model_discovery" else None,
                latency_ms=None,
                redaction_values=redaction_values,
            ), redaction_values

        if submitted_protocol != saved_protocol_canonical or submitted_base != saved_base:
            return None, self._build_llm_channel_result(
                success=False,
                message="Saved secret scope mismatch",
                error="Hermes endpoint changed; re-enter LLM_HERMES_API_KEY before testing",
                stage=stage,
                error_code="saved_secret_scope_mismatch",
                retryable=False,
                details={
                    "reason": "endpoint_mismatch",
                    "submitted_base_url": submitted_base,
                    "saved_base_url": saved_base,
                },
                resolved_protocol=submitted_protocol,
                models=[] if stage == "model_discovery" else None,
                latency_ms=None,
                redaction_values=redaction_values,
            ), redaction_values

        return saved_key, {}, redaction_values

    def _validate_hermes_submitted_secret(
        self,
        *,
        api_key: str,
        use_saved_secret: bool,
        stage: str,
        models: Optional[List[str]] = None,
        capability_checks: Sequence[str] = (),
        redaction_values: Optional[Set[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Reject Hermes secret shapes that must not reach an outbound request."""

        secret = (api_key or "").strip()
        redactions = set(redaction_values or set())
        redactions.update(self._build_redaction_values(secret))
        if is_masked_secret_placeholder(secret):
            return self._build_llm_channel_result(
                success=False,
                message="Runtime Hermes secret is not reusable",
                error=(
                    "Runtime-injected Hermes secret is masked and cannot be reused by "
                    "test/discovery. Re-enter the key or save it to .env."
                ),
                stage=stage,
                error_code="runtime_secret_not_reusable",
                retryable=False,
                details={"reason": "runtime_secret_not_reusable"},
                resolved_protocol=None,
                models=models if stage == "model_discovery" else None,
                latency_ms=None,
                capability_results=(
                    self._build_skipped_capability_results(
                        capability_checks,
                        "base_test_failed",
                        "Skipped because the base channel test did not pass",
                        redaction_values=redactions,
                    )
                    if capability_checks
                    else None
                ),
                redaction_values=redactions,
            )
        if "," in secret:
            return self._build_llm_channel_result(
                success=False,
                message="Hermes API key is invalid",
                error="Hermes Phase 3 only supports a single LLM_HERMES_API_KEY",
                stage=stage,
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": "LLM_HERMES_API_KEY",
                    "issue_code": "multiple_api_keys",
                    "reason": "multiple_api_keys",
                },
                resolved_protocol=None,
                models=models if stage == "model_discovery" else None,
                latency_ms=None,
                capability_results=(
                    self._build_skipped_capability_results(
                        capability_checks,
                        "base_test_failed",
                        "Skipped because the base channel test did not pass",
                        redaction_values=redactions,
                    )
                    if capability_checks
                    else None
                ),
                redaction_values=redactions,
            )
        return None

    def discover_llm_channel_models(
        self,
        *,
        name: str,
        provider_id: Optional[str] = None,
        protocol: str,
        base_url: str,
        api_key: str,
        models: Sequence[str] = (),
        timeout_seconds: float = 20.0,
        use_saved_secret: bool = False,
    ) -> Dict[str, Any]:
        """Discover available models through the Provider's Catalog contract."""
        channel_name = name.strip() or "channel"
        provider, protocol, base_url, provider_issue = self._resolve_request_provider(
            provider_id=provider_id,
            protocol=protocol,
            base_url=base_url,
        )
        if provider_issue is not None:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=provider_issue["message"],
                stage="model_discovery",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": provider_issue["key"],
                    "issue_code": provider_issue["code"],
                    "reason": provider_issue["code"],
                },
                resolved_protocol=None,
                models=[],
                latency_ms=None,
            )
        resolved_secret, secret_error, redaction_values = self._resolve_hermes_saved_secret(
            channel_name=channel_name,
            protocol=protocol,
            base_url=base_url,
            submitted_api_key=api_key,
            use_saved_secret=use_saved_secret,
            stage="model_discovery",
        )
        if resolved_secret is None:
            return secret_error
        api_key = resolved_secret
        redaction_values.update(self._build_redaction_values(api_key))
        if is_reserved_hermes_name(channel_name):
            secret_error = self._validate_hermes_submitted_secret(
                api_key=api_key,
                use_saved_secret=use_saved_secret,
                stage="model_discovery",
                models=[],
                redaction_values=redaction_values,
            )
            if secret_error is not None:
                return secret_error
            try:
                base_url = canonicalize_hermes_base_url(base_url)
            except ValueError as exc:
                return self._build_llm_channel_result(
                    success=False,
                    message="Hermes Base URL is invalid",
                    error=str(exc),
                    stage="model_discovery",
                    error_code="invalid_config",
                    retryable=False,
                    details={
                        "issue_key": "discover_channel_BASE_URL",
                        "issue_code": "invalid_hermes_url",
                        "reason": "invalid_hermes_url",
                    },
                    resolved_protocol=None,
                    models=[],
                    latency_ms=None,
                    redaction_values=redaction_values,
                )
        existing_models = [str(m).strip() for m in models if str(m).strip()]
        validation_issues, resolved_protocol = self._validate_llm_channel_connection(
            channel_name=channel_name,
            provider=provider,
            provider_id=str(provider_id or ""),
            protocol_value=protocol,
            base_url_value=base_url,
            api_key_value=api_key,
            model_values=existing_models,
            field_prefix="discover_channel",
        )
        if not resolved_protocol and existing_models:
            resolved_protocol = resolve_llm_channel_protocol(
                protocol,
                base_url=base_url,
                models=existing_models,
                channel_name=channel_name,
            )
        errors = [issue for issue in validation_issues if issue["severity"] == "error"]
        if errors:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=errors[0]["message"],
                stage="model_discovery",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": errors[0]["key"],
                    "issue_code": errors[0]["code"],
                    "reason": errors[0]["code"],
                },
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=None,
                redaction_values=redaction_values,
            )

        from src.llm.provider_catalog import supports_model_discovery

        if not supports_model_discovery(
            provider_id=str(provider_id or ""),
            protocol=resolved_protocol,
        ):
            return self._build_llm_channel_result(
                success=False,
                message="Model discovery is not supported for this protocol",
                error=(
                    f"LLM channel '{channel_name}' protocol '{resolved_protocol}' "
                    "does not support /models discovery yet"
                ),
                stage="model_discovery",
                error_code="unsupported_protocol",
                retryable=False,
                details={"protocol": resolved_protocol or None},
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=None,
                redaction_values=redaction_values,
            )

        api_keys = [segment.strip() for segment in api_key.split(",") if segment.strip()]
        selected_api_key = api_keys[0] if api_keys else ""
        redaction_values.update(self._build_redaction_values(selected_api_key))
        request_headers = {"Accept": "application/json"}
        if selected_api_key:
            request_headers["Authorization"] = f"Bearer {selected_api_key}"

        try:
            models_url = self._build_llm_models_url(
                base_url,
                protocol=resolved_protocol,
            )
        except ValueError as exc:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=str(exc),
                stage="model_discovery",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": "discover_channel_BASE_URL",
                    "issue_code": "invalid_url",
                    "reason": "invalid_url",
                },
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=None,
                redaction_values=redaction_values,
            )

        try:
            started_at = time.perf_counter()
            if is_reserved_hermes_name(channel_name):
                session = requests.Session()
                session.trust_env = False
                try:
                    response = session.get(
                        models_url,
                        headers=request_headers,
                        timeout=max(5.0, float(timeout_seconds)),
                        allow_redirects=False,
                    )
                finally:
                    session.close()
            else:
                response = requests.get(
                    models_url,
                    headers=request_headers,
                    timeout=max(5.0, float(timeout_seconds)),
                    allow_redirects=False,
                )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
        except requests.RequestException as exc:
            log_safe_exception(
                logger,
                "LLM channel model discovery failed",
                exc,
                error_code="llm_channel_model_discovery_failed",
                level=logging.WARNING,
                context={"channel": channel_name},
                redaction_values=redaction_values,
            )
            diagnostic = self._classify_llm_exception(exc)
            return self._build_llm_channel_result(
                success=False,
                message=diagnostic.message,
                error=sanitize_exception_chain(exc, redaction_values=redaction_values),
                stage="model_discovery",
                error_code=diagnostic.error_code,
                retryable=diagnostic.retryable,
                details=self._merge_llm_diagnostic_details({"endpoint": models_url}, diagnostic),
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=None,
                redaction_values=redaction_values,
            )

        if 300 <= response.status_code < 400:
            return self._build_llm_channel_result(
                success=False,
                message="Model discovery request was redirected",
                error="Redirect responses are not allowed for model discovery",
                stage="model_discovery",
                error_code="network_error",
                retryable=False,
                details={"endpoint": models_url, "http_status": response.status_code},
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=latency_ms,
                redaction_values=redaction_values,
            )

        if not response.ok:
            error_text = self._extract_llm_discovery_error(response)
            diagnostic = self._classify_llm_http_error(
                status_code=response.status_code,
                error_text=error_text,
            )
            return self._build_llm_channel_result(
                success=False,
                message=diagnostic.message,
                error=error_text,
                stage="model_discovery",
                error_code=diagnostic.error_code,
                retryable=diagnostic.retryable,
                details=self._merge_llm_diagnostic_details(
                    {"endpoint": models_url, "http_status": response.status_code},
                    diagnostic,
                ),
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=latency_ms,
                redaction_values=redaction_values,
            )

        try:
            payload = response.json()
        except ValueError:
            return self._build_llm_channel_result(
                success=False,
                message="Model discovery returned invalid JSON",
                error="The /models endpoint did not return valid JSON",
                stage="response_parse",
                error_code="format_error",
                retryable=False,
                details={"endpoint": models_url, "http_status": response.status_code, "reason": "non_json"},
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=latency_ms,
                redaction_values=redaction_values,
            )

        models = self._extract_discovered_llm_models(payload)
        if not models:
            return self._build_llm_channel_result(
                success=False,
                message="Model discovery returned no models",
                error="The /models endpoint did not return any model IDs",
                stage="response_parse",
                error_code="empty_response",
                retryable=False,
                details={"endpoint": models_url, "http_status": response.status_code, "reason": "empty_models"},
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=latency_ms,
                redaction_values=redaction_values,
            )

        return self._build_llm_channel_result(
            success=True,
            message="LLM channel model discovery succeeded",
            error=None,
            stage="model_discovery",
            error_code=None,
            retryable=False,
            details={"endpoint": models_url, "model_count": len(models)},
            resolved_protocol=resolved_protocol or None,
            models=models,
            latency_ms=latency_ms,
            redaction_values=redaction_values,
        )

    def test_llm_channel(
        self,
        *,
        name: str,
        provider_id: Optional[str] = None,
        protocol: str,
        base_url: str,
        api_key: str,
        models: Sequence[str],
        enabled: bool = True,
        timeout_seconds: float = 20.0,
        capability_checks: Sequence[str] = (),
        use_saved_secret: bool = False,
    ) -> Dict[str, Any]:
        """Run a minimal completion call against one channel definition."""
        requested_capabilities = self._normalize_llm_capability_checks(capability_checks)
        raw_models = [str(model).strip() for model in models if str(model).strip()]
        channel_name = name.strip() or "channel"
        provider, protocol, base_url, provider_issue = self._resolve_request_provider(
            provider_id=provider_id,
            protocol=protocol,
            base_url=base_url,
        )
        if provider_issue is not None:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=provider_issue["message"],
                stage="chat_completion",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": provider_issue["key"],
                    "issue_code": provider_issue["code"],
                    "reason": provider_issue["code"],
                },
                resolved_protocol=None,
                resolved_model=None,
                latency_ms=None,
                capability_results=self._build_skipped_capability_results(
                    requested_capabilities,
                    "base_test_failed",
                    "Skipped because the base channel test did not pass",
                ),
            )
        resolved_secret, secret_error, redaction_values = self._resolve_hermes_saved_secret(
            channel_name=channel_name,
            protocol=protocol,
            base_url=base_url,
            submitted_api_key=api_key,
            use_saved_secret=use_saved_secret,
            stage="chat_completion",
        )
        if resolved_secret is None:
            result = secret_error
            if requested_capabilities and "capability_results" not in result:
                result["capability_results"] = self._build_skipped_capability_results(
                    requested_capabilities,
                    "base_test_failed",
                    "Skipped because the base channel test did not pass",
                    redaction_values=redaction_values,
                )
            return result
        api_key = resolved_secret
        redaction_values.update(self._build_redaction_values(api_key))
        if is_reserved_hermes_name(channel_name):
            secret_error = self._validate_hermes_submitted_secret(
                api_key=api_key,
                use_saved_secret=use_saved_secret,
                stage="chat_completion",
                capability_checks=requested_capabilities,
                redaction_values=redaction_values,
            )
            if secret_error is not None:
                return secret_error
            try:
                base_url = canonicalize_hermes_base_url(base_url)
            except ValueError as exc:
                return self._build_llm_channel_result(
                    success=False,
                    message="Hermes Base URL is invalid",
                    error=str(exc),
                    stage="chat_completion",
                    error_code="invalid_config",
                    retryable=False,
                    details={
                        "issue_key": "test_channel_BASE_URL",
                        "issue_code": "invalid_hermes_url",
                        "reason": "invalid_hermes_url",
                    },
                    resolved_protocol=None,
                    resolved_model=None,
                    latency_ms=None,
                    capability_results=self._build_skipped_capability_results(
                        requested_capabilities,
                        "base_test_failed",
                        "Skipped because the base channel test did not pass",
                        redaction_values=redaction_values,
                    ),
                    redaction_values=redaction_values,
                )
        validation_issues = self._validate_llm_channel_definition(
            channel_name=channel_name,
            display_name=channel_name,
            provider=provider,
            provider_id=str(provider_id or ""),
            protocol_value=protocol,
            base_url_value=base_url,
            api_key_value=api_key,
            model_values=raw_models,
            enabled=enabled,
            field_prefix="test_channel",
            require_complete=True,
        )
        errors = [issue for issue in validation_issues if issue["severity"] == "error"]
        if errors:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=errors[0]["message"],
                stage="chat_completion",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": errors[0]["key"],
                    "issue_code": errors[0]["code"],
                    "reason": errors[0]["code"],
                },
                resolved_protocol=None,
                resolved_model=None,
                latency_ms=None,
                capability_results=self._build_skipped_capability_results(
                    requested_capabilities,
                    "base_test_failed",
                    "Skipped because the base channel test did not pass",
                    redaction_values=redaction_values,
                ),
                redaction_values=redaction_values,
            )

        resolved_protocol = resolve_llm_channel_protocol(protocol, base_url=base_url, models=raw_models, channel_name=name)
        resolved_models = [normalize_llm_channel_model(model, resolved_protocol, base_url) for model in raw_models]
        resolved_model = resolved_models[0]
        if is_reserved_hermes_name(channel_name):
            resolved_model = canonicalize_hermes_model_ref(raw_models[0]).wire_model
        api_keys = [segment.strip() for segment in api_key.split(",") if segment.strip()]
        selected_api_key = api_keys[0] if api_keys else ""
        redaction_values.update(self._build_redaction_values(selected_api_key))

        call_kwargs: Dict[str, Any] = {
            "model": resolved_model,
            "messages": [{"role": "user", "content": "Reply with OK"}],
            "max_tokens": 256,  # Increased to allow MiniMax-M3 thinking process + response
            "timeout": max(5.0, float(timeout_seconds)),
        }
        adapter_api_key = selected_api_key
        if (
            not adapter_api_key
            and resolved_protocol == "openai"
            and channel_allows_empty_api_key(resolved_protocol, base_url)
        ):
            # The OpenAI SDK requires a non-empty constructor value even when a
            # trusted local endpoint does not authenticate requests.
            adapter_api_key = self._LLM_EMPTY_API_KEY_ADAPTER_SENTINEL
        if adapter_api_key:
            call_kwargs["api_key"] = adapter_api_key
        if base_url.strip():
            call_kwargs["api_base"] = base_url.strip()
        call_kwargs = apply_litellm_generation_params(
            call_kwargs,
            resolved_model,
            self._get_runtime_llm_temperature(),
        )

        try:
            import litellm
            from src.agent.llm_adapter import (
                resolve_fallback_litellm_wire_models,
                register_fallback_model_pricing,
            )

            # Register fallback pricing for OpenAI-compatible models to prevent cost calculation errors
            config_model_list = None
            if getattr(self, "_config", None) is not None:
                config_model_list = getattr(self._config, "llm_model_list", None)
            register_fallback_model_pricing(
                resolve_fallback_litellm_wire_models(
                    resolved_model,
                    config_model_list,
                )
            )

            started_at = time.perf_counter()
            if is_reserved_hermes_name(channel_name):
                with open_hermes_no_proxy_client(
                    api_key=selected_api_key,
                    base_url=base_url,
                    timeout=max(5.0, float(timeout_seconds)),
                ) as client:
                    hermes_call_kwargs = dict(call_kwargs)
                    hermes_call_kwargs["stream"] = False
                    hermes_call_kwargs["client"] = client
                    hermes_call_kwargs.pop("api_key", None)
                    hermes_call_kwargs.pop("api_base", None)
                    response = call_litellm_with_param_recovery(
                        lambda kwargs: litellm.completion(**kwargs),
                        model=resolved_model,
                        call_kwargs=hermes_call_kwargs,
                        logger=logger,
                        log_label="[Hermes channel test]",
                    )
            else:
                response = call_litellm_with_param_recovery(
                    lambda kwargs: litellm.completion(**kwargs),
                    model=resolved_model,
                    call_kwargs=call_kwargs,
                    logger=logger,
                    log_label="[LLM channel test]",
                )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            content, parse_error_code, parse_error, parse_reason = self._extract_llm_completion_content(response)
            if parse_error_code:
                message = (
                    "LLM channel returned an empty response"
                    if parse_error_code == "empty_response"
                    else "LLM channel returned an unexpected response format"
                )
                return self._build_llm_channel_result(
                    success=False,
                    message=message,
                    error=parse_error,
                    stage="response_parse",
                    error_code=parse_error_code,
                    retryable=False,
                    details={"response_error": parse_error, "reason": parse_reason},
                    resolved_protocol=resolved_protocol or None,
                    resolved_model=resolved_model,
                    latency_ms=latency_ms,
                    capability_results=self._build_skipped_capability_results(
                        requested_capabilities,
                        "base_test_failed",
                        "Skipped because the base channel test did not pass",
                        redaction_values=redaction_values,
                    ),
                    redaction_values=redaction_values,
                )

            capability_results: Dict[str, Any] = {}
            if requested_capabilities and is_reserved_hermes_name(channel_name):
                capability_results = self._run_hermes_capability_checks(
                    litellm_module=litellm,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    capability_checks=requested_capabilities,
                    redaction_values=redaction_values,
                )
            elif requested_capabilities:
                capability_results = self._run_llm_capability_checks(
                    litellm_module=litellm,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    capability_checks=requested_capabilities,
                    redaction_values=redaction_values,
                )
            return self._build_llm_channel_result(
                success=True,
                message="LLM channel test succeeded",
                error=None,
                stage="chat_completion",
                error_code=None,
                retryable=False,
                details={"response_preview": content[:80]},
                resolved_protocol=resolved_protocol or None,
                resolved_model=resolved_model,
                latency_ms=latency_ms,
                capability_results=capability_results,
                redaction_values=redaction_values,
            )
        except Exception as exc:
            log_safe_exception(
                logger,
                "LLM channel test failed",
                exc,
                error_code="llm_channel_test_failed",
                level=logging.WARNING,
                context={"channel": channel_name},
                redaction_values=redaction_values,
            )
            diagnostic = self._classify_llm_exception(exc)
            return self._build_llm_channel_result(
                success=False,
                message=diagnostic.message,
                error=sanitize_exception_chain(exc, redaction_values=redaction_values),
                stage="chat_completion",
                error_code=diagnostic.error_code,
                retryable=diagnostic.retryable,
                details=self._merge_llm_diagnostic_details({"model": resolved_model}, diagnostic),
                resolved_protocol=resolved_protocol or None,
                resolved_model=resolved_model,
                latency_ms=None,
                redaction_values=redaction_values,
                capability_results=self._build_skipped_capability_results(
                    requested_capabilities,
                    "base_test_failed",
                    "Skipped because the base channel test did not pass",
                    redaction_values=redaction_values,
                ),
            )

    @classmethod
    def _normalize_llm_capability_checks(cls, capability_checks: Sequence[str]) -> List[str]:
        requested = {str(check).strip().lower() for check in capability_checks if str(check).strip()}
        return [check for check in cls._LLM_CAPABILITY_ORDER if check in requested]

    @classmethod
    def _build_skipped_capability_results(
        cls,
        capability_checks: Sequence[str],
        reason: str,
        message: str,
        *,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        return {
            capability: cls._build_llm_capability_result(
                capability=capability,
                status="skipped",
                message=message,
                error_code="skipped",
                retryable=False,
                details={"reason": reason},
                redaction_values=redaction_values,
            )
            for capability in capability_checks
        }

    @classmethod
    def _run_hermes_capability_checks(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
        capability_checks: Sequence[str],
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        for capability in capability_checks:
            if capability != "json":
                results[capability] = cls._build_llm_capability_result(
                    capability=capability,
                    status="skipped",
                    message="Hermes Phase 3 does not probe this capability",
                    error_code="not_probed",
                    retryable=False,
                    details={"reason": "not_probed"},
                    redaction_values=redaction_values,
                )
                continue
            try:
                started_at = time.perf_counter()
                with open_hermes_no_proxy_client(
                    api_key=selected_api_key,
                    base_url=base_url,
                    timeout=max(5.0, float(timeout_seconds)),
                ) as client:
                    call_kwargs = cls._build_llm_capability_completion_kwargs(
                        resolved_model=resolved_model,
                        selected_api_key=selected_api_key,
                        base_url=base_url,
                        timeout_seconds=timeout_seconds,
                        messages=[{"role": "user", "content": 'Return exactly this JSON object: {"status":"ok"}'}],
                        max_tokens=64,
                        extra={"response_format": {"type": "json_object"}, "client": client},
                    )
                    call_kwargs.pop("api_key", None)
                    call_kwargs.pop("api_base", None)
                    response = litellm_module.completion(**call_kwargs)
                    content, parse_error_code, parse_error, parse_reason = cls._extract_llm_completion_content(response)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                if parse_error_code:
                    results[capability] = cls._build_llm_capability_result(
                        capability="json",
                        status="failed",
                        message="JSON capability check returned no parseable content",
                        error_code=parse_error_code,
                        retryable=False,
                        latency_ms=latency_ms,
                        details={"reason": parse_reason, "response_error": parse_error},
                        redaction_values=redaction_values,
                    )
                    continue
                try:
                    payload = json.loads(content)
                except ValueError:
                    payload = None
                if not isinstance(payload, dict) or payload.get("status") != "ok":
                    results[capability] = cls._build_llm_capability_result(
                        capability="json",
                        status="failed",
                        message="JSON capability check returned non-JSON content",
                        error_code="format_error",
                        retryable=False,
                        latency_ms=latency_ms,
                        details={"reason": "non_json", "response_preview": content[:80]},
                        redaction_values=redaction_values,
                    )
                    continue
                results[capability] = cls._build_llm_capability_result(
                    capability="json",
                    status="passed",
                    message="JSON output capability check passed",
                    latency_ms=latency_ms,
                    details={"reason": "json_valid"},
                    redaction_values=redaction_values,
                )
            except Exception as exc:
                diagnostic = cls._classify_llm_capability_exception(exc, "json")
                results[capability] = cls._build_llm_capability_result_from_diagnostic(
                    "json",
                    diagnostic,
                    cls._sanitize_llm_error_text(exc, redaction_values=redaction_values),
                    redaction_values=redaction_values,
                )
        return results

    @classmethod
    def _run_llm_capability_checks(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
        capability_checks: Sequence[str],
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        for capability in capability_checks:
            if capability == "json":
                results[capability] = cls._run_json_capability_check(
                    litellm_module=litellm_module,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                )
            elif capability == "tools":
                results[capability] = cls._run_tools_capability_check(
                    litellm_module=litellm_module,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                )
            elif capability == "stream":
                results[capability] = cls._run_stream_capability_check(
                    litellm_module=litellm_module,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    redaction_values=redaction_values,
                )
            elif capability == "vision":
                results[capability] = cls._run_vision_capability_check(
                    litellm_module=litellm_module,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                )
        return results

    @classmethod
    def _run_json_capability_check(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        try:
            started_at = time.perf_counter()
            response = litellm_module.completion(
                **cls._build_llm_capability_completion_kwargs(
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    messages=[{"role": "user", "content": 'Return exactly this JSON object: {"status":"ok"}'}],
                    max_tokens=64,
                    extra={"response_format": {"type": "json_object"}},
                )
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            content, parse_error_code, parse_error, parse_reason = cls._extract_llm_completion_content(response)
            if parse_error_code:
                return cls._build_llm_capability_result(
                    capability="json",
                    status="failed",
                    message="JSON capability check returned no parseable content",
                    error_code=parse_error_code,
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": parse_reason, "response_error": parse_error},
                )
            try:
                payload = json.loads(content)
            except ValueError:
                return cls._build_llm_capability_result(
                    capability="json",
                    status="failed",
                    message="JSON capability check returned non-JSON content",
                    error_code="format_error",
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": "non_json", "response_preview": content[:80]},
                )
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                return cls._build_llm_capability_result(
                    capability="json",
                    status="failed",
                    message="JSON capability check returned unexpected JSON",
                    error_code="format_error",
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": "non_json", "response_preview": content[:80]},
                )
            return cls._build_llm_capability_result(
                capability="json",
                status="passed",
                message="JSON output capability check passed",
                latency_ms=latency_ms,
                details={"reason": "json_valid"},
            )
        except Exception as exc:
            diagnostic = cls._classify_llm_capability_exception(exc, "json")
            return cls._build_llm_capability_result_from_diagnostic("json", diagnostic, str(exc))

    @classmethod
    def _run_tools_capability_check(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "dsa_probe_echo",
                    "description": "Return the provided text.",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                },
            }
        ]
        try:
            started_at = time.perf_counter()
            response = litellm_module.completion(
                **cls._build_llm_capability_completion_kwargs(
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    messages=[{"role": "user", "content": "Call the dsa_probe_echo tool with text set to ok."}],
                    max_tokens=64,
                    extra={
                        "tools": tools,
                        "tool_choice": {"type": "function", "function": {"name": "dsa_probe_echo"}},
                    },
                )
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            tool_names = cls._extract_llm_tool_call_names(response)
            if "dsa_probe_echo" not in tool_names:
                return cls._build_llm_capability_result(
                    capability="tools",
                    status="failed",
                    message="Tool calling capability check did not return the probe tool call",
                    error_code="capability_unsupported",
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": "tool_calls_missing", "tool_calls": tool_names},
                )
            return cls._build_llm_capability_result(
                capability="tools",
                status="passed",
                message="Tool calling capability check passed",
                latency_ms=latency_ms,
                details={"reason": "tool_call_returned"},
            )
        except Exception as exc:
            diagnostic = cls._classify_llm_capability_exception(exc, "tools")
            return cls._build_llm_capability_result_from_diagnostic("tools", diagnostic, str(exc))

    @classmethod
    def _run_stream_capability_check(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        stream = None
        started_at = time.perf_counter()
        try:
            stream = litellm_module.completion(
                **cls._build_llm_capability_completion_kwargs(
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    messages=[{"role": "user", "content": "Reply with OK"}],
                    max_tokens=32,
                    extra={"stream": True},
                )
            )
            for index, chunk in enumerate(stream):
                content = cls._extract_llm_stream_chunk_content(chunk)
                if content:
                    latency_ms = int((time.perf_counter() - started_at) * 1000)
                    return cls._build_llm_capability_result(
                        capability="stream",
                        status="passed",
                        message="Streaming capability check passed",
                        latency_ms=latency_ms,
                        details={"reason": "stream_chunk_received"},
                    )
                if index + 1 >= cls._LLM_STREAM_CHUNK_LIMIT:
                    break
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            return cls._build_llm_capability_result(
                capability="stream",
                status="failed",
                message="Streaming capability check returned no content chunks",
                error_code="empty_response",
                retryable=False,
                latency_ms=latency_ms,
                details={"reason": "stream_no_content"},
            )
        except Exception as exc:
            diagnostic = cls._classify_llm_capability_exception(exc, "stream")
            return cls._build_llm_capability_result_from_diagnostic(
                "stream",
                diagnostic,
                sanitize_exception_chain(exc, redaction_values=redaction_values),
                redaction_values=redaction_values,
            )
        finally:
            close_stream = getattr(stream, "close", None)
            if callable(close_stream):
                try:
                    close_stream()
                except Exception as exc:
                    log_safe_exception(
                        logger,
                        "LLM stream capability probe close failed",
                        exc,
                        error_code="llm_stream_capability_probe_close_failed",
                        level=logging.DEBUG,
                        redaction_values=redaction_values,
                    )

    @classmethod
    def _run_vision_capability_check(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        try:
            started_at = time.perf_counter()
            response = litellm_module.completion(
                **cls._build_llm_capability_completion_kwargs(
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Reply with OK if this image is visible."},
                                {"type": "image_url", "image_url": {"url": cls._LLM_CAPABILITY_PROBE_IMAGE}},
                            ],
                        }
                    ],
                    max_tokens=32,
                )
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            content, parse_error_code, parse_error, parse_reason = cls._extract_llm_completion_content(response)
            if parse_error_code:
                return cls._build_llm_capability_result(
                    capability="vision",
                    status="failed",
                    message="Vision capability check returned no parseable content",
                    error_code=parse_error_code,
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": parse_reason, "response_error": parse_error},
                )
            return cls._build_llm_capability_result(
                capability="vision",
                status="passed",
                message="Vision capability check passed",
                latency_ms=latency_ms,
                details={"reason": "vision_response_received", "response_preview": content[:80]},
            )
        except Exception as exc:
            diagnostic = cls._classify_llm_capability_exception(exc, "vision")
            return cls._build_llm_capability_result_from_diagnostic("vision", diagnostic, str(exc))

    @classmethod
    def _build_llm_capability_completion_kwargs(
        cls,
        *,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            timeout = 10.0
        call_kwargs: Dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "timeout": min(max(5.0, timeout), 10.0),
        }
        if selected_api_key:
            call_kwargs["api_key"] = selected_api_key
        if base_url.strip():
            call_kwargs["api_base"] = base_url.strip()
        if extra:
            call_kwargs.update(extra)
        call_kwargs = apply_litellm_generation_params(
            call_kwargs,
            resolved_model,
            0.0,
        )
        return call_kwargs

    @classmethod
    def _build_llm_capability_result(
        cls,
        *,
        capability: str,
        status: str,
        message: str,
        error_code: Optional[str] = None,
        retryable: bool = False,
        latency_ms: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "message": cls._sanitize_llm_error_text(message, redaction_values=redaction_values),
            "error_code": error_code,
            "stage": f"capability_{capability}",
            "retryable": retryable,
            "latency_ms": latency_ms,
            "details": cls._sanitize_llm_details(
                {"capability": capability, **(details or {})},
                redaction_values=redaction_values,
            ),
        }

    @classmethod
    def _build_llm_capability_result_from_diagnostic(
        cls,
        capability: str,
        diagnostic: _LLMDiagnostic,
        error: str,
        *,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        details = cls._merge_llm_diagnostic_details({"error": error}, diagnostic)
        return cls._build_llm_capability_result(
            capability=capability,
            status="failed",
            message=diagnostic.message,
            error_code=diagnostic.error_code,
            retryable=diagnostic.retryable,
            details=details,
            redaction_values=redaction_values,
        )

    @staticmethod
    def _extract_llm_tool_call_names(response: Any) -> List[str]:
        choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
        if not choices:
            return []
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls")
        else:
            tool_calls = getattr(message, "tool_calls", None) if message is not None else None
        names: List[str] = []
        for call in tool_calls or []:
            function = call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
            if isinstance(function, dict):
                name = str(function.get("name") or "").strip()
            else:
                name = str(getattr(function, "name", "") or "").strip()
            if name:
                names.append(name)
        return names

    @staticmethod
    def _extract_llm_stream_chunk_content(chunk: Any) -> str:
        choices = chunk.get("choices") if isinstance(chunk, dict) else getattr(chunk, "choices", None)
        if not choices:
            return ""
        choice = choices[0]
        delta = choice.get("delta") if isinstance(choice, dict) else getattr(choice, "delta", None)
        message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
        for container in (delta, message):
            if not container:
                continue
            content = container.get("content") if isinstance(container, dict) else getattr(container, "content", None)
            if content:
                return str(content)
        content = choice.get("text") if isinstance(choice, dict) else getattr(choice, "text", None)
        return str(content or "")

    @classmethod
    def _classify_llm_capability_exception(cls, exc: Exception, capability: str) -> _LLMDiagnostic:
        text = str(exc).lower()
        capability_tokens = {
            "json": ("response_format", "json_object", "json mode"),
            "tools": ("tool_choice", "tools", "function calling", "tool call"),
            "stream": ("stream", "streaming"),
            "vision": ("image", "image_url", "vision", "multimodal", "multi-modal"),
        }
        unsupported_markers = (
            "unsupported",
            "not support",
            "not supported",
            "unknown parameter",
            "unrecognized parameter",
            "invalid parameter",
            "unexpected keyword",
            "not allowed",
        )
        has_unsupported_marker = any(marker in text for marker in unsupported_markers)
        has_capability_token = any(token in text for token in capability_tokens.get(capability, ()))
        if has_unsupported_marker and (has_capability_token or capability in text):
            return _LLMDiagnostic(
                "capability_unsupported",
                False,
                f"LLM channel does not support {capability} capability",
                "capability_unsupported",
                {"capability": capability},
            )
        return cls._classify_llm_exception(exc)

    def update(
        self,
        config_version: str,
        items: Sequence[Dict[str, str]],
        mask_token: str = "******",
        reload_now: bool = True,
    ) -> Dict[str, Any]:
        """Validate and persist updates into `.env`, then reload runtime config."""
        self._conflict.guard_version(config_version)

        issues = self._collect_issues(items=items, mask_token=mask_token)
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            raise ConfigValidationError(issues=errors)

        previous_map = self._manager.read_config_map()
        submitted_keys: Set[str] = set()
        updates: List[Tuple[str, str]] = []
        sensitive_keys: Set[str] = set()
        for item in items:
            key = item["key"].upper()
            value = item["value"]
            field_schema = get_field_definition(key, value)
            normalized_value = self._normalize_value_for_storage(value, field_schema)
            submitted_keys.add(key)
            updates.append((key, normalized_value))
            if bool(field_schema.get("is_sensitive", False)):
                sensitive_keys.add(key)

        try:
            updated_keys, skipped_masked_keys, new_version = self._manager.apply_updates(
                updates=updates,
                sensitive_keys=sensitive_keys,
                mask_token=mask_token,
                expected_version=config_version,
            )
        except ConfigVersionMismatchError as exc:
            raise self._conflict.as_conflict(exc) from exc

        warnings: List[str] = []
        reload_triggered = False
        if reload_now:
            try:
                Config.reset_instance()
                self._reload_runtime_singletons()
                setup_env(override=True)
                config = Config.get_instance()
                warnings.extend(config.validate())
                reload_triggered = True
            except Exception as exc:  # pragma: no cover - defensive branch
                log_safe_exception(
                    logger,
                    "Configuration reload failed",
                    exc,
                    error_code="configuration_reload_failed",
                    redaction_values=(updates[key] for key in sensitive_keys),
                )
                warnings.append("Configuration updated but reload failed")

        warnings.extend(
            self._build_explainability_warnings(
                submitted_keys=submitted_keys,
                reload_now=reload_now,
            )
        )
        update_map = dict(updates)
        warnings.extend(
            self._build_runtime_model_cleanup_warnings(
                previous_map=previous_map,
                updates=update_map,
            )
        )
        warnings.extend(
            self._build_hermes_unsupported_key_cleanup_warnings(
                previous_map=previous_map,
                updates=update_map,
            )
        )
        if self._runtime_scheduler is not None and submitted_keys & {
            "SCHEDULE_ENABLED",
            "SCHEDULE_TIME",
            "SCHEDULE_TIMES",
        }:
            try:
                self._runtime_scheduler.reconcile_from_config(
                    clear_enabled_override="SCHEDULE_ENABLED" in submitted_keys,
                )
            except Exception as exc:  # pragma: no cover - defensive branch
                log_safe_exception(
                    logger,
                    "Runtime scheduler reconciliation failed",
                    exc,
                    error_code="runtime_scheduler_reconcile_failed",
                    redaction_values=(updates[key] for key in sensitive_keys),
                )
                warnings.append("Configuration updated but runtime scheduler reconcile failed")

        return {
            "success": True,
            "config_version": new_version,
            "applied_count": len(updated_keys),
            "skipped_masked_count": len(skipped_masked_keys),
            "reload_triggered": reload_triggered,
            "updated_keys": updated_keys,
            "warnings": warnings,
        }

    def _build_explainability_warnings(
        self,
        *,
        submitted_keys: Set[str],
        reload_now: bool,
    ) -> List[str]:
        """Append user-facing runtime explainability warnings for key settings."""
        warnings: List[str] = []
        if not submitted_keys:
            return warnings

        current_map = self._manager.read_config_map()

        if submitted_keys & {"NEWS_MAX_AGE_DAYS", "NEWS_STRATEGY_PROFILE"}:
            raw_profile = current_map.get("NEWS_STRATEGY_PROFILE", "short")
            profile = normalize_news_strategy_profile(raw_profile)
            try:
                max_age = max(1, int(current_map.get("NEWS_MAX_AGE_DAYS", "3") or "3"))
            except (TypeError, ValueError):
                max_age = 3
            effective_days = resolve_news_window_days(
                news_max_age_days=max_age,
                news_strategy_profile=profile,
            )
            warnings.append(
                (
                    "新闻窗口已按策略计算："
                    f"NEWS_STRATEGY_PROFILE={profile}, "
                    f"NEWS_MAX_AGE_DAYS={max_age}, "
                    f"effective_days={effective_days} "
                    "(effective_days=min(profile_days, NEWS_MAX_AGE_DAYS))."
                )
            )

        if "MAX_WORKERS" in submitted_keys:
            try:
                max_workers = max(1, int(current_map.get("MAX_WORKERS", "3") or "3"))
            except (TypeError, ValueError):
                max_workers = 3
            if reload_now:
                warnings.append(
                    (
                        f"MAX_WORKERS={max_workers} 已保存。任务队列空闲时会自动应用；"
                        "若当前存在运行中任务，将在队列空闲后生效。"
                    )
                )
            else:
                warnings.append(
                    (
                        f"MAX_WORKERS={max_workers} 已写入 .env，但本次未触发运行时重载"
                        "（reload_now=false）；重载后才会应用。"
                    )
                )

        startup_only_run_keys = submitted_keys & {
            "RUN_IMMEDIATELY",
        }
        if startup_only_run_keys:
            warnings.append(
                (
                    f"{', '.join(sorted(startup_only_run_keys))} 已写入 .env。"
                    "它属于启动期单次运行配置：当前已运行的 WebUI/API 进程不会因为本次保存立即触发分析；"
                    "请重启当前进程后，在非 schedule 模式下按新值生效。"
                )
            )

        startup_only_schedule_keys = submitted_keys & {
            "SCHEDULE_RUN_IMMEDIATELY",
        }
        if startup_only_schedule_keys:
            warnings.append(
                (
                    f"{', '.join(sorted(startup_only_schedule_keys))} 已写入 .env。"
                    "这些属于启动期调度模式配置：当前已运行的 WebUI/API 进程不会因为本次保存启动、"
                    "停止或重建 scheduler；请重启当前进程，并以 schedule 模式重新启动后生效。"
                )
            )

        if "SCHEDULE_ENABLED" in submitted_keys:
            schedule_enabled = (current_map.get("SCHEDULE_ENABLED", "false") or "false").strip().lower()
            warnings.append(
                (
                    f"SCHEDULE_ENABLED={schedule_enabled} 已写入 .env。"
                    "如果当前进程是 WebUI/API/Desktop 长运行进程，runtime scheduler 会按新配置启停；"
                    "CLI schedule 模式仍按启动参数和配置运行。"
                )
            )

        if "SCHEDULE_TIMES" in submitted_keys:
            schedule_times = (current_map.get("SCHEDULE_TIMES", "") or "").strip()
            schedule_time = (current_map.get("SCHEDULE_TIME", "") or "").strip() or "18:00"
            effective = schedule_times or schedule_time
            warnings.append(
                (
                    f"SCHEDULE_TIMES={effective} 已写入 .env。"
                    "有效时间点会去重、排序；为空时继续使用 SCHEDULE_TIME。"
                    "如果当前进程存在 runtime scheduler，会按新时间重建 daily jobs。"
                )
            )

        if "SCHEDULE_TIME" in submitted_keys:
            schedule_time = (current_map.get("SCHEDULE_TIME", "") or "").strip() or "18:00"
            warnings.append(
                (
                    f"SCHEDULE_TIME={schedule_time} 已写入 .env。"
                    "如果当前进程已经以 schedule 模式运行，scheduler 会在下一轮检查中自动重建 daily job；"
                    "如果当前进程未以 schedule 模式运行，本次保存不会启动 scheduler。"
                )
            )

        startup_only_bind_keys = submitted_keys & {
            "WEBUI_HOST",
            "WEBUI_PORT",
        }
        if startup_only_bind_keys:
            warnings.append(
                (
                    f"{', '.join(sorted(startup_only_bind_keys))} 已写入 .env。"
                    "这些属于启动期监听配置：当前已运行的 WebUI/API 进程不会因为本次保存重新绑定监听地址或端口；"
                    "请重启当前进程、Docker 容器或服务管理器后生效。"
                )
            )

        return warnings

    @staticmethod
    def _build_runtime_model_cleanup_warnings(
        *,
        previous_map: Dict[str, str],
        updates: Dict[str, str],
    ) -> List[str]:
        """Explain when save payload clears stale runtime model references."""
        runtime_labels = {
            "LITELLM_MODEL": "主要模型",
            "AGENT_LITELLM_MODEL": "Agent 主要模型",
            "VISION_MODEL": "Vision 模型",
        }
        cleared_labels: List[str] = []
        for key, label in runtime_labels.items():
            if previous_map.get(key, "").strip() and key in updates and not updates[key].strip():
                cleared_labels.append(label)

        removed_fallbacks: List[str] = []
        if "LITELLM_FALLBACK_MODELS" in updates:
            previous_fallbacks = [
                item.strip()
                for item in previous_map.get("LITELLM_FALLBACK_MODELS", "").split(",")
                if item.strip()
            ]
            next_fallbacks = {
                item.strip()
                for item in updates["LITELLM_FALLBACK_MODELS"].split(",")
                if item.strip()
            }
            removed_fallbacks = [item for item in previous_fallbacks if item not in next_fallbacks]

        if not cleared_labels and not removed_fallbacks:
            return []

        cleaned_targets = list(cleared_labels)
        if removed_fallbacks:
            cleaned_targets.append("备用模型中的失效项")

        cleaned_text = " / ".join(cleaned_targets)
        warning = (
            f"检测到已同步清理失效的运行时模型引用：{cleaned_text}。"
            "如需恢复，请先补回对应连接的模型列表后重新选择；"
            "也可用桌面端导出备份或手动 .env 还原之前的 LLM_* / "
            "LITELLM_MODEL / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE。"
        )
        return [warning]

    @staticmethod
    def _build_hermes_unsupported_key_cleanup_warnings(
        *,
        previous_map: Dict[str, str],
        updates: Dict[str, str],
    ) -> List[str]:
        """Explain when Hermes save clears unsupported Phase 3 key/header fields."""
        unsupported_labels = {
            "LLM_HERMES_API_KEYS": "LLM_HERMES_API_KEYS",
            "LLM_HERMES_EXTRA_HEADERS": "LLM_HERMES_EXTRA_HEADERS",
        }
        cleared = [
            label
            for key, label in unsupported_labels.items()
            if previous_map.get(key, "").strip() and key in updates and not updates[key].strip()
        ]
        if not cleared:
            return []

        return [
            (
                "检测到已清理 Hermes Phase 3 不支持的配置项："
                f"{', '.join(cleared)}。"
                "Hermes reserved channel 只支持单个 LLM_HERMES_API_KEY，不支持多 Key 或额外 Header；"
                "如需恢复旧值，请从 .env 备份、Git 历史或桌面端导出备份手动还原，"
                "但非空 LLM_HERMES_API_KEYS / LLM_HERMES_EXTRA_HEADERS 仍会被后端校验拒绝。"
            )
        ]

    def apply_simple_updates(
        self,
        updates: Sequence[Tuple[str, str]],
        mask_token: str = "******",
    ) -> None:
        """Apply raw key updates without validation (internal service use only)."""
        self._manager.apply_updates(
            updates=updates,
            sensitive_keys=set(),
            mask_token=mask_token,
        )

    @staticmethod
    def _parse_imported_env_content(content: str) -> List[Dict[str, str]]:
        """Parse raw `.env` text into update items without expanding app templates."""
        normalized_content = content.replace("\ufeff", "")
        if not normalized_content.strip():
            raise ConfigImportError("未识别到有效 .env 配置")

        from dotenv import dotenv_values

        parsed = dotenv_values(stream=io.StringIO(normalized_content), interpolate=False)
        updates: List[Dict[str, str]] = []
        for key, value in parsed.items():
            if key is None:
                continue
            updates.append(
                {
                    "key": str(key).upper(),
                    "value": "" if value is None else str(value),
                }
            )

        if not updates:
            raise ConfigImportError("未识别到有效 .env 配置")

        return updates

    def _collect_issues(
        self,
        items: Sequence[Dict[str, str]],
        mask_token: str,
        *,
        require_explicit_runtime_secrets: bool = False,
    ) -> List[Dict[str, Any]]:
        """Collect field-level and cross-field validation issues."""
        saved_config_map = self._manager.read_config_map()
        display_config_map = self._build_display_config_map(saved_config_map)
        runtime_config_map = self._build_runtime_display_config_map(display_config_map)
        effective_map = {
            **runtime_config_map,
            **display_config_map,
        }
        previous_effective_map = dict(effective_map)
        issues: List[Dict[str, Any]] = []
        updated_map: Dict[str, str] = {}
        submitted_map: Dict[str, str] = {}

        for item in items:
            key = item["key"].upper()
            value = item["value"]
            submitted_map[key] = value
            field_schema = get_field_definition(key, value)
            is_sensitive = bool(field_schema.get("is_sensitive", False))
            submitted_is_masked = is_sensitive and (
                value == mask_token or is_masked_secret_placeholder(value)
            )
            if submitted_is_masked:
                saved_secret = (saved_config_map.get(key) or "").strip()
                dynamic_match = self._WEB_SETTINGS_LLM_CHANNEL_SUPPORT_KEY_RE.fullmatch(key)
                is_connection_scoped = bool(
                    dynamic_match
                    and dynamic_match.group(2) in self._CONNECTION_SECRET_SCOPE_SUFFIXES
                )
                if saved_secret:
                    if not is_connection_scoped and is_masked_secret_placeholder(saved_secret):
                        issues.append(
                            {
                                "key": key,
                                "code": "saved_secret_scope_mismatch",
                                "severity": "error",
                                "message": f"{key} contains a saved mask placeholder and must be replaced.",
                                "expected": "fresh literal secret or explicit clear",
                                "actual": "masked",
                                "details": {"reason": "invalid_saved_secret_placeholder"},
                            }
                        )
                    # Keep the effective saved value. Connection-scoped identity
                    # changes are checked after all draft fields are applied.
                    continue

                runtime_secret = (runtime_config_map.get(key) or "").strip()
                if runtime_secret:
                    code = "runtime_secret_not_reusable"
                    detail_reason = code
                elif dynamic_match:
                    code = "saved_secret_scope_mismatch"
                    detail_reason = "missing_scoped_saved_secret"
                else:
                    code = "missing_saved_secret"
                    detail_reason = code
                details: Dict[str, Any] = {"reason": detail_reason}
                if dynamic_match:
                    details["connection"] = dynamic_match.group(1).lower()
                issues.append(
                    {
                        "key": key,
                        "code": code,
                        "severity": "error",
                        "message": (
                            f"{key} is injected at runtime and cannot be reused by a Settings draft."
                            if runtime_secret
                            else f"{key} has no saved value for this mask token."
                        ),
                        "expected": "fresh literal secret or explicit clear",
                        "actual": "masked",
                        "details": details,
                    }
                )
                continue

            updated_map[key] = value
            effective_map[key] = value
            issues.extend(self._validate_value(key=key, value=value, field_schema=field_schema))

        issues.extend(
            self._collect_connection_secret_scope_issues(
                saved_map=display_config_map,
                runtime_map=runtime_config_map,
                effective_map=effective_map,
                submitted_map=submitted_map,
                mask_token=mask_token,
                require_explicit_runtime_secrets=(
                    require_explicit_runtime_secrets
                    and self._generation_backend_uses_litellm(effective_map)
                ),
            )
        )
        issues.extend(
            self._validate_cross_field(
                effective_map=effective_map,
                updated_keys=set(updated_map.keys()),
                previous_effective_map=previous_effective_map,
            )
        )
        issues.extend(self._validate_field_contracts(effective_map))
        return issues

    @classmethod
    def _connection_secret_scope_identity(
        cls,
        config_map: Dict[str, str],
        connection_name: str,
    ) -> Dict[str, str]:
        """Return the endpoint identity to which a Connection secret is bound."""
        _provider, provider_id, _is_explicit = cls._resolve_connection_provider(
            config_map,
            connection_name,
        )
        protocol, base_url = cls._resolve_connection_transport(
            config_map,
            connection_name,
        )
        return {
            "provider": provider_id.strip().lower(),
            "protocol": canonicalize_llm_channel_protocol(protocol),
            "base_url": base_url.strip().rstrip("/"),
        }

    @classmethod
    def _collect_connection_secret_scope_issues(
        cls,
        *,
        saved_map: Dict[str, str],
        runtime_map: Dict[str, str],
        effective_map: Dict[str, str],
        submitted_map: Dict[str, str],
        mask_token: str,
        require_explicit_runtime_secrets: bool = False,
    ) -> List[Dict[str, Any]]:
        """Reject secrets whose saved/runtime scope cannot authorize a draft."""
        saved_connections: Set[str] = set()
        for key, value in saved_map.items():
            match = cls._WEB_SETTINGS_LLM_CHANNEL_SUPPORT_KEY_RE.fullmatch(key)
            if (
                match
                and match.group(2) in cls._CONNECTION_SECRET_SCOPE_SUFFIXES
                and str(value or "").strip()
            ):
                saved_connections.add(match.group(1))
        effective_connections = {
            name.strip().upper()
            for name in cls._split_csv(effective_map.get("LLM_CHANNELS") or "")
        }
        issues: List[Dict[str, Any]] = []
        for connection_name in sorted(saved_connections):
            saved_identity = cls._connection_secret_scope_identity(
                saved_map,
                connection_name,
            )
            effective_identity = cls._connection_secret_scope_identity(
                effective_map,
                connection_name,
            )
            changed_fields = [
                field
                for field in ("provider", "protocol", "base_url")
                if saved_identity[field] != effective_identity[field]
            ]
            prefix = f"LLM_{connection_name}"
            for suffix in cls._CONNECTION_SECRET_SCOPE_SUFFIXES:
                key = f"{prefix}_{suffix}"
                saved_secret = (saved_map.get(key) or "").strip()
                if not saved_secret:
                    continue
                submitted = submitted_map.get(key)
                submitted_is_masked = submitted is not None and (
                    submitted == mask_token or is_masked_secret_placeholder(submitted)
                )
                if submitted is not None and not submitted_is_masked:
                    continue
                saved_is_masked = is_masked_secret_placeholder(saved_secret)
                if not saved_is_masked and not changed_fields:
                    continue
                issues.append(
                    {
                        "key": key,
                        "code": "saved_secret_scope_mismatch",
                        "severity": "error",
                        "message": (
                            f"{key} contains a saved mask placeholder and must be replaced."
                            if saved_is_masked
                            else (
                                f"{key} is bound to the saved Connection endpoint. "
                                "Re-enter or clear it before changing Provider, protocol, or Base URL."
                            )
                        ),
                        "expected": "fresh literal secret or explicit clear",
                        "actual": "masked" if submitted_is_masked else "omitted",
                        "details": {
                            "reason": (
                                "invalid_saved_secret_placeholder"
                                if saved_is_masked
                                else "connection_identity_changed"
                            ),
                            "connection": connection_name.lower(),
                            "changed_fields": changed_fields,
                        },
                    }
                )

        for connection_name in sorted(effective_connections):
            prefix = f"LLM_{connection_name}"
            connection_touched = "LLM_CHANNELS" in submitted_map or any(
                key.startswith(f"{prefix}_") for key in submitted_map
            )
            if not connection_touched and not require_explicit_runtime_secrets:
                continue
            for suffix in cls._CONNECTION_SECRET_SCOPE_SUFFIXES:
                key = f"{prefix}_{suffix}"
                if (saved_map.get(key) or "").strip():
                    continue
                submitted = submitted_map.get(key)
                submitted_is_masked = submitted is not None and (
                    submitted == mask_token or is_masked_secret_placeholder(submitted)
                )
                # Explicit mask submissions are handled once in the generic
                # sensitive-field pass above. This loop owns omitted secrets.
                if submitted_is_masked:
                    continue
                runtime_secret = (runtime_map.get(key) or "").strip()
                if not runtime_secret:
                    continue
                if submitted is not None:
                    continue
                issues.append(
                    {
                        "key": key,
                        "code": "runtime_secret_not_reusable",
                        "severity": "error",
                        "message": (
                            f"{key} is injected at runtime and cannot be reused by a Settings draft. "
                            "Enter a fresh value before previewing, testing, or changing this Connection."
                        ),
                        "expected": "fresh literal secret",
                        "actual": "masked" if submitted_is_masked else "omitted",
                        "details": {
                            "reason": "runtime_secret_not_reusable",
                            "connection": connection_name.lower(),
                        },
                    }
                )
        return issues

    @staticmethod
    def _generation_backend_uses_litellm(effective_map: Dict[str, str]) -> bool:
        primary = normalize_backend_id(
            effective_map.get("GENERATION_BACKEND"),
            default=LITELLM_BACKEND_ID,
        )
        fallback = (
            LITELLM_BACKEND_ID
            if "GENERATION_FALLBACK_BACKEND" not in effective_map
            else (effective_map.get("GENERATION_FALLBACK_BACKEND") or "").strip().lower()
        )
        return LITELLM_BACKEND_ID in {primary, fallback}

    @staticmethod
    def _validate_field_contracts(effective_map: Dict[str, str]) -> List[Dict[str, Any]]:
        """Authoritative required/conditionally-required schema contract checks.

        Hidden fields (visibleWhen not met) are excluded; a field is required when
        requirement=required or its requiredWhen conditions are met.
        """
        issues: List[Dict[str, Any]] = []
        for key, contract in get_contract_field_definitions().items():
            if evaluate_config_conditions(contract.get("visible_when"), effective_map) == "not_met":
                continue
            required = contract.get("requirement") == "required"
            required_when = contract.get("required_when")
            if required_when and evaluate_config_conditions(required_when, effective_map) == "met":
                required = True
            if required and not str(effective_map.get(key, "") or "").strip():
                issues.append({
                    "key": key,
                    "code": "field_required",
                    "severity": "error",
                    "message": f"{key} is required by the current configuration.",
                    "expected": "non-empty value",
                    "actual": "",
                })
        return issues

    @classmethod
    def _is_generation_backend_status_key(cls, key: str) -> bool:
        normalized = str(key or "").strip().upper()
        return (
            normalized in cls._GENERATION_BACKEND_STATUS_EXACT_KEYS
            or normalized == "LLM_CHANNELS"
            or bool(cls._GENERATION_BACKEND_STATUS_LLM_CHANNEL_RE.fullmatch(normalized))
        )

    @classmethod
    def _filter_generation_backend_items(
        cls,
        items: Sequence[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        filtered: List[Dict[str, str]] = []
        for item in items:
            key = str(item.get("key", "")).strip().upper()
            if not key or not cls._is_generation_backend_status_key(key):
                continue
            filtered.append({"key": key, "value": "" if item.get("value") is None else str(item.get("value"))})
        return filtered

    def _collect_generation_backend_issues(
        self,
        *,
        items: Sequence[Dict[str, str]],
        mask_token: str,
    ) -> List[Dict[str, Any]]:
        """Collect only config issues that affect generation backend status/smoke."""
        issues = self._collect_issues(
            items=self._filter_generation_backend_items(items),
            mask_token=mask_token,
            require_explicit_runtime_secrets=True,
        )
        effective_map = self._build_generation_backend_effective_map(
            items=items,
            mask_token=mask_token,
        )
        issues.extend(self._validate_generation_backend_litellm_runtime_source(effective_map))
        return [
            issue for issue in issues
            if self._is_generation_backend_status_key(str(issue.get("key", "")))
        ]

    @staticmethod
    def _validate_generation_backend_litellm_runtime_source(effective_map: Dict[str, str]) -> List[Dict[str, Any]]:
        """Validate explicit LiteLLM models when no route list can back them."""
        primary_backend = normalize_backend_id(
            effective_map.get("GENERATION_BACKEND"),
            default=LITELLM_BACKEND_ID,
        )
        fallback_backend = (
            LITELLM_BACKEND_ID
            if "GENERATION_FALLBACK_BACKEND" not in effective_map
            else (effective_map.get("GENERATION_FALLBACK_BACKEND") or "").strip().lower()
        )
        litellm_selected = (
            primary_backend == LITELLM_BACKEND_ID
            or (fallback_backend == LITELLM_BACKEND_ID and primary_backend != LITELLM_BACKEND_ID)
        )
        if not litellm_selected:
            return []
        if SystemConfigService._uses_litellm_yaml(effective_map):
            return []
        if SystemConfigService._collect_llm_channel_models_from_map(effective_map):
            return []
        if (effective_map.get("LLM_CHANNELS") or "").strip():
            return []

        issues: List[Dict[str, Any]] = []
        primary_model = (effective_map.get("LITELLM_MODEL") or "").strip()
        if primary_model and not SystemConfigService._has_runtime_source_for_model(primary_model, effective_map):
            issues.append(
                {
                    "key": "LITELLM_MODEL",
                    "code": "missing_runtime_source",
                    "message": (
                        "A primary model is selected, but no usable runtime source was found. "
                        "Configure a matching provider API key, LLM channel, or LiteLLM YAML route."
                    ),
                    "severity": "error",
                    "expected": "matching provider API key, enabled channel model, or YAML model",
                    "actual": primary_model,
                }
            )

        fallback_models = [
            model.strip()
            for model in (effective_map.get("LITELLM_FALLBACK_MODELS") or "").split(",")
            if model.strip()
        ]
        invalid_fallbacks = [
            model for model in fallback_models
            if not SystemConfigService._has_runtime_source_for_model(model, effective_map)
        ]
        if invalid_fallbacks:
            issues.append(
                {
                    "key": "LITELLM_FALLBACK_MODELS",
                    "code": "missing_runtime_source",
                    "message": (
                        "Some fallback models do not have a matching provider API key, "
                        "enabled channel, or LiteLLM YAML route."
                    ),
                    "severity": "error",
                    "expected": "matching provider API key, enabled channel model, or YAML model",
                    "actual": ", ".join(invalid_fallbacks[:3]),
                }
            )
        return issues

    def _collect_generation_backend_issues_from_map(
        self,
        effective_map: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        items = [
            {"key": key, "value": value}
            for key, value in effective_map.items()
            if self._is_generation_backend_status_key(key)
        ]
        return self._collect_generation_backend_issues(items=items, mask_token="******")

    @staticmethod
    def _validate_value(key: str, value: str, field_schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Validate a single field value against schema metadata."""
        issues: List[Dict[str, Any]] = []
        data_type = field_schema.get("data_type", "string")
        validation = field_schema.get("validation", {}) or {}
        is_required = field_schema.get("is_required", False)

        # Empty values are valid for non-required fields (skip type validation)
        if not value.strip() and not is_required:
            return issues

        if ("\n" in value or "\r" in value) and data_type != "json":
            issues.append(
                {
                    "key": key,
                    "code": "invalid_value",
                    "message": "Value cannot contain newline characters",
                    "severity": "error",
                    "expected": "single-line value",
                    "actual": "contains newline",
                }
            )
            return issues

        if data_type == "integer":
            try:
                numeric = int(value)
            except ValueError:
                return [
                    {
                        "key": key,
                        "code": "invalid_type",
                        "message": "Value must be an integer",
                        "severity": "error",
                        "expected": "integer",
                        "actual": value,
                    }
                ]
            issues.extend(SystemConfigService._validate_numeric_range(key, numeric, validation))

        elif data_type == "number":
            try:
                numeric = float(value)
            except ValueError:
                return [
                    {
                        "key": key,
                        "code": "invalid_type",
                        "message": "Value must be a number",
                        "severity": "error",
                        "expected": "number",
                        "actual": value,
                    }
                ]
            issues.extend(SystemConfigService._validate_numeric_range(key, numeric, validation))

        elif data_type == "boolean":
            if value.strip().lower() not in {"true", "false"}:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_type",
                        "message": "Value must be true or false",
                        "severity": "error",
                        "expected": "true|false",
                        "actual": value,
                    }
                )

        elif data_type == "time":
            pattern = validation.get("pattern") or r"^([01]\d|2[0-3]):[0-5]\d$"
            if not re.match(pattern, value.strip()):
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_format",
                        "message": "Value must be in HH:MM format",
                        "severity": "error",
                        "expected": "HH:MM",
                        "actual": value,
                    }
                )

        elif data_type == "json":
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_json",
                        "message": "Value must be valid JSON",
                        "severity": "error",
                        "expected": "valid JSON",
                        "actual": (
                            "[REDACTED]"
                            if field_schema.get("is_sensitive", False)
                            else value[:120]
                        ),
                    }
                )
            else:
                if key.endswith("_EXTRA_HEADERS") and not isinstance(parsed, dict):
                    issues.append(
                        {
                            "key": key,
                            "code": "invalid_json_object",
                            "message": "Value must be a JSON object",
                            "severity": "error",
                            "expected": "JSON object",
                            "actual": "[REDACTED]",
                        }
                    )
                elif key == "AGENT_EVENT_ALERT_RULES_JSON":
                    try:
                        from src.agent.events import parse_event_alert_rules, validate_event_alert_rule

                        rule_index = 0
                        for rule_index, rule in enumerate(parse_event_alert_rules(parsed), start=1):
                            validate_event_alert_rule(rule)
                    except ValueError as exc:
                        issues.append(
                            {
                                "key": key,
                                "code": "invalid_event_rule",
                                "message": f"Rule validation failed: {exc}",
                                "severity": "error",
                                "expected": "supported EventMonitor rule fields and enum values",
                                "actual": f"rule #{rule_index or 1}",
                            }
                        )

        elif validation.get("pattern"):
            pattern = validation["pattern"]
            if not re.match(pattern, value.strip()):
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_format",
                        "message": "Value does not match the required format",
                        "severity": "error",
                        "expected": pattern,
                        "actual": value,
                    }
                )

        if validation.get("timezone") and value:
            try:
                validate_notification_timezone(value)
            except ValueError as exc:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_timezone",
                        "message": str(exc),
                        "severity": "error",
                        "expected": "valid IANA timezone or empty",
                        "actual": value,
                    }
                )

        if "enum" in validation and value and value not in validation["enum"]:
            issues.append(
                {
                    "key": key,
                    "code": "invalid_enum",
                    "message": "Value is not in allowed options",
                    "severity": "error",
                    "expected": ",".join(validation["enum"]),
                    "actual": value,
                }
            )

        if "allowed_values" in validation and value:
            delimiter = validation.get("delimiter")
            raw_values = value.split(delimiter) if delimiter else [value]
            allowed_values = {str(item).strip().lower() for item in validation["allowed_values"]}
            invalid_values = []
            seen_invalid = set()
            for raw_item in raw_values:
                item = raw_item.strip().lower()
                if not item:
                    continue
                if item not in allowed_values and item not in seen_invalid:
                    invalid_values.append(item)
                    seen_invalid.add(item)
            if invalid_values:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_allowed_value",
                        "message": "Value contains unsupported item(s)",
                        "severity": "error",
                        "expected": ",".join(str(item) for item in validation["allowed_values"]),
                        "actual": ", ".join(invalid_values),
                    }
                )

        if validation.get("item_type") == "url":
            delimiter = validation.get("delimiter", ",")
            values = [item.strip() for item in value.split(delimiter)] if validation.get("multi_value") else [value.strip()]
            allowed_schemes = tuple(validation.get("allowed_schemes", ["http", "https"]))
            invalid_values = [
                item for item in values
                if item and not SystemConfigService._is_valid_url(item, allowed_schemes=allowed_schemes)
            ]
            if invalid_values:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_url",
                        "message": "Value must contain valid URLs with scheme and host",
                        "severity": "error",
                        "expected": ",".join(allowed_schemes) + " URL(s)",
                        "actual": ", ".join(invalid_values[:3]),
                    }
                )

        if key == "NTFY_URL" and value.strip():
            allowed_schemes = tuple(validation.get("allowed_schemes", ["http", "https"]))
            if SystemConfigService._is_valid_url(value.strip(), allowed_schemes=allowed_schemes):
                ntfy_server_url, ntfy_topic = resolve_ntfy_endpoint(value)
                if not ntfy_server_url or not ntfy_topic:
                    issues.append(
                        {
                            "key": key,
                            "code": "invalid_ntfy_url",
                            "message": "NTFY_URL must include a topic path, e.g. https://ntfy.sh/my-topic",
                            "severity": "error",
                            "expected": "ntfy publish endpoint with topic path",
                            "actual": value,
                        }
                    )

        if key == "GOTIFY_URL" and value.strip():
            allowed_schemes = tuple(validation.get("allowed_schemes", ["http", "https"]))
            if SystemConfigService._is_valid_url(value.strip(), allowed_schemes=allowed_schemes):
                gotify_endpoint = resolve_gotify_message_endpoint(value)
                if not gotify_endpoint:
                    issues.append(
                        {
                            "key": key,
                            "code": "invalid_gotify_url",
                            "message": "GOTIFY_URL must be a Gotify server base URL and must not include /message",
                            "severity": "error",
                            "expected": "Gotify server base URL, e.g. https://gotify.example",
                            "actual": value,
                        }
                    )

        return issues

    @staticmethod
    def _normalize_value_for_storage(value: str, field_schema: Dict[str, Any]) -> str:
        """Normalize submitted values before persisting to the single-line .env file."""
        if field_schema.get("data_type", "string") != "json":
            return value

        if not value.strip():
            return value

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value

        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _validate_numeric_range(key: str, numeric_value: float, validation: Dict[str, Any]) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        min_value = validation.get("min")
        max_value = validation.get("max")

        if min_value is not None and numeric_value < min_value:
            issues.append(
                {
                    "key": key,
                    "code": "out_of_range",
                    "message": "Value is lower than minimum",
                    "severity": "error",
                    "expected": f">={min_value}",
                    "actual": str(numeric_value),
                }
            )
        if max_value is not None and numeric_value > max_value:
            issues.append(
                {
                    "key": key,
                    "code": "out_of_range",
                    "message": "Value is greater than maximum",
                    "severity": "error",
                    "expected": f"<={max_value}",
                    "actual": str(numeric_value),
                }
            )
        return issues

    @staticmethod
    def _is_valid_url(value: str, allowed_schemes: Tuple[str, ...]) -> bool:
        """Return True when *value* looks like a valid absolute URL."""
        parsed = urlparse(value)
        return parsed.scheme in allowed_schemes and bool(parsed.netloc)

    @staticmethod
    def _canonical_ipv4_numeric_host(host: str) -> Optional[str]:
        """Return canonical IPv4 for libc-style numeric host aliases."""
        import socket

        candidate = (host or "").lower()
        if not candidate or ":" in candidate:
            return None

        try:
            return socket.inet_ntoa(socket.inet_aton(candidate))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _is_noncanonical_ipv4_numeric_host(host: str) -> bool:
        canonical = SystemConfigService._canonical_ipv4_numeric_host(host)
        return canonical is not None and host.lower() != canonical

    @staticmethod
    def _normalize_hostname_for_security(host: str) -> Optional[str]:
        """Return a normalized ASCII host for URL safety checks."""
        import unicodedata

        candidate = (host or "").strip().lower().rstrip(".")
        if not candidate:
            return None
        if ":" in candidate:
            return candidate
        try:
            normalized = unicodedata.normalize("NFKC", candidate)
            ascii_host = normalized.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError:
            return None
        return ascii_host or None

    @staticmethod
    def _is_valid_llm_base_url(value: str, allowed_schemes: Tuple[str, ...] = ("http", "https")) -> bool:
        """Return True when an LLM base URL is safe to parse consistently."""
        if not value:
            return False
        if any(char == "\\" or char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
            return False

        try:
            parsed = urlparse(value)
            host = parsed.hostname
            _ = parsed.port
        except ValueError:
            return False

        if parsed.scheme not in allowed_schemes or not parsed.netloc or not host:
            return False
        if "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
            return False
        if SystemConfigService._is_noncanonical_ipv4_numeric_host(host):
            return False

        return True

    @staticmethod
    def _split_csv(value: str) -> List[str]:
        return [item.strip() for item in (value or "").split(",") if item.strip()]

    def _build_notification_test_effective_map(
        self,
        *,
        items: Sequence[Dict[str, str]],
        mask_token: str,
    ) -> Dict[str, str]:
        """Merge saved/runtime config with unsaved notification test items."""
        allowed_keys = set(self._NOTIFICATION_TEST_KEY_MAP)
        effective = {
            key: value
            for key, value in self._build_display_config_map(self._manager.read_config_map()).items()
            if key in allowed_keys
        }

        for raw_key, raw_value in os.environ.items():
            key = str(raw_key).upper()
            if key in allowed_keys:
                effective[key] = "" if raw_value is None else str(raw_value)

        for item in items:
            key = str(item.get("key", "")).strip().upper()
            if key not in allowed_keys:
                continue
            value = "" if item.get("value") is None else str(item.get("value"))
            if value == mask_token:
                continue
            effective[key] = value

        return effective

    def _get_missing_notification_test_keys(
        self,
        channel: str,
        effective_map: Dict[str, str],
    ) -> List[str]:
        """Return missing keys for a channel, honoring alternative key groups."""
        groups = self._NOTIFICATION_REQUIRED_KEY_GROUPS.get(channel, ())
        if not groups:
            return []

        missing_by_group: List[List[str]] = []
        for group in groups:
            missing = [key for key in group if not (effective_map.get(key) or "").strip()]
            if not missing:
                return []
            missing_by_group.append(missing)

        if not missing_by_group:
            return []
        ranked_groups = []
        for group, missing in zip(groups, missing_by_group):
            present_count = len(group) - len(missing)
            ranked_groups.append((len(missing), -present_count, missing))
        ranked_groups.sort(key=lambda item: (item[0], item[1]))
        return ranked_groups[0][2]

    @staticmethod
    def _get_invalid_notification_test_config_message(
        channel: str,
        effective_map: Dict[str, str],
    ) -> Optional[str]:
        if channel == "ntfy":
            ntfy_url = (effective_map.get("NTFY_URL") or "").strip()
            if not ntfy_url:
                return None
            ntfy_server_url, ntfy_topic = resolve_ntfy_endpoint(ntfy_url)
            if ntfy_server_url and ntfy_topic:
                return None
            return "NTFY_URL 必须包含 topic path，例如 https://ntfy.sh/my-topic。"
        if channel == "gotify":
            gotify_url = (effective_map.get("GOTIFY_URL") or "").strip()
            if not gotify_url:
                return None
            if resolve_gotify_message_endpoint(gotify_url):
                return None
            return "GOTIFY_URL 必须是 Gotify server base URL，不包含 /message。"
        return None

    def _build_notification_config(self, effective_map: Dict[str, str]) -> Config:
        """Build an isolated Config instance from notification values."""
        kwargs: Dict[str, Any] = {"stock_list": []}
        for key, (attr, value_type) in self._NOTIFICATION_TEST_KEY_MAP.items():
            if key not in effective_map:
                continue
            if key == "DISCORD_CHANNEL_ID" and (effective_map.get("DISCORD_MAIN_CHANNEL_ID") or "").strip():
                continue
            raw_value = effective_map.get(key, "")
            kwargs[attr] = self._parse_notification_test_value(key, raw_value, value_type)
        return Config(**kwargs)

    def _parse_notification_test_value(self, key: str, value: str, value_type: str) -> Any:
        if value_type == "csv":
            return self._split_csv(value)
        if value_type == "bool":
            return parse_env_bool(value, default=True)
        if value_type == "int":
            defaults = {
                "WECHAT_MAX_BYTES": 4000,
                "FEISHU_MAX_BYTES": 20000,
                "DISCORD_MAX_WORDS": 2000,
            }
            return parse_env_int(value, defaults.get(key, 0), field_name=key, minimum=1)
        stripped = (value or "").strip()
        return stripped or None

    def _dispatch_notification_test(
        self,
        *,
        channel: str,
        config: Config,
        effective_map: Dict[str, str],
        title: str,
        content: str,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        from src.notification_sender import (
            AstrbotSender,
            CustomWebhookSender,
            DiscordSender,
            EmailSender,
            FeishuSender,
            GotifySender,
            NtfySender,
            PushoverSender,
            PushplusSender,
            Serverchan3Sender,
            SlackSender,
            TelegramSender,
            WechatSender,
            DingtalkSender,
        )

        started_at = time.perf_counter()
        target = self._resolve_notification_test_target(channel, effective_map)
        titled_content = self._build_notification_test_content(title, content)

        if channel == "custom":
            attempts = CustomWebhookSender(config).test_custom_webhooks(
                titled_content,
                timeout_seconds=timeout_seconds,
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            success_count = sum(1 for attempt in attempts if bool(attempt.get("success")))
            total_count = len(attempts)
            success = success_count > 0
            if success_count == total_count and total_count > 0:
                message = f"自定义 Webhook 通知测试成功（{success_count}/{total_count}）"
            elif success_count > 0:
                message = f"自定义 Webhook 通知测试部分成功（{success_count}/{total_count}）"
            else:
                message = f"自定义 Webhook 通知测试失败（{success_count}/{total_count}）"
            return self._build_notification_test_result(
                success=success,
                message=message,
                error_code=None if success else "send_failed",
                stage="notification_send",
                retryable=any(bool(attempt.get("retryable")) for attempt in attempts),
                latency_ms=latency_ms,
                attempts=attempts,
            )

        dispatch = {
            "wechat": lambda: WechatSender(config).send_to_wechat(titled_content, timeout_seconds=timeout_seconds),
            "dingtalk": lambda: DingtalkSender(config).send_to_dingtalk(titled_content, title="Test Message", timeout_seconds=timeout_seconds),
            "feishu": lambda: FeishuSender(config).send_to_feishu(titled_content, timeout_seconds=timeout_seconds),
            "telegram": lambda: TelegramSender(config).send_to_telegram(titled_content, timeout_seconds=timeout_seconds),
            "email": lambda: EmailSender(config).send_to_email(content, subject=title, timeout_seconds=timeout_seconds),
            "pushover": lambda: PushoverSender(config).send_to_pushover(content, title=title, timeout_seconds=timeout_seconds),
            "ntfy": lambda: NtfySender(config).send_to_ntfy(content, title=title, timeout_seconds=timeout_seconds),
            "gotify": lambda: GotifySender(config).send_to_gotify(content, title=title, timeout_seconds=timeout_seconds),
            "pushplus": lambda: PushplusSender(config).send_to_pushplus(content, title=title, timeout_seconds=timeout_seconds),
            "serverchan3": lambda: Serverchan3Sender(config).send_to_serverchan3(content, title=title, timeout_seconds=timeout_seconds),
            "discord": lambda: DiscordSender(config).send_to_discord(titled_content, timeout_seconds=timeout_seconds),
            "slack": lambda: SlackSender(config).send_to_slack(titled_content, timeout_seconds=timeout_seconds),
            "astrbot": lambda: AstrbotSender(config).send_to_astrbot(titled_content, timeout_seconds=timeout_seconds),
        }

        ok = bool(dispatch[channel]())
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        attempt = {
            "channel": channel,
            "success": ok,
            "message": "通知测试发送成功" if ok else "通知测试发送失败",
            "target": target,
            "error_code": None if ok else "send_failed",
            "stage": "notification_send",
            "retryable": False,
            "latency_ms": latency_ms,
        }
        return self._build_notification_test_result(
            success=ok,
            message=f"{channel} 通知测试成功" if ok else f"{channel} 通知测试失败",
            error_code=None if ok else "send_failed",
            stage="notification_send",
            retryable=False,
            latency_ms=latency_ms,
            attempts=[attempt],
        )

    @staticmethod
    def _build_notification_test_content(title: str, content: str) -> str:
        title = title.strip()
        content = content.strip()
        return f"{title}\n\n{content}" if title else content

    def _resolve_notification_test_target(self, channel: str, effective_map: Dict[str, str]) -> str:
        for key in self._NOTIFICATION_TEST_TARGET_KEYS.get(channel, ()):
            raw_value = (effective_map.get(key) or "").strip()
            if not raw_value:
                continue
            if key == "CUSTOM_WEBHOOK_URLS":
                first_url = self._split_csv(raw_value)[0] if self._split_csv(raw_value) else ""
                return self._mask_notification_target(first_url, source_key=key)
            return self._mask_notification_target(raw_value, source_key=key)
        return channel

    @classmethod
    def _build_notification_test_result(
        cls,
        *,
        success: bool,
        message: str,
        error_code: Optional[str],
        stage: Optional[str],
        retryable: bool,
        latency_ms: Optional[int],
        attempts: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        sanitized_attempts = [cls._sanitize_notification_attempt(attempt) for attempt in attempts]
        return {
            "success": success,
            "message": cls._sanitize_notification_text(message),
            "error_code": error_code,
            "stage": stage,
            "retryable": retryable,
            "latency_ms": latency_ms,
            "attempts": sanitized_attempts,
        }

    @classmethod
    def _sanitize_notification_attempt(cls, attempt: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = dict(attempt)
        if "message" in sanitized:
            sanitized["message"] = cls._sanitize_notification_text(sanitized["message"])
        if "target" in sanitized:
            sanitized["target"] = cls._mask_notification_target(str(sanitized.get("target") or ""))
        return sanitized

    @classmethod
    def _sanitize_notification_text(cls, text: Any) -> str:
        sanitized = cls._sanitize_llm_error_text(text)
        if not sanitized:
            return ""
        sanitized = re.sub(r"(?i)(bearer\s+)[a-z0-9._\-:]+", r"\1[REDACTED]", sanitized)
        sanitized = re.sub(r"(?i)(token|secret|password|sendkey)([=:]\s*)[^\s,;&]+", r"\1\2[REDACTED]", sanitized)
        sanitized = re.sub(
            r"https?://[^\s]+",
            lambda match: cls._mask_notification_target(match.group(0)),
            sanitized,
        )
        return sanitized[:300]

    @staticmethod
    def _mask_notification_target(target: str, *, source_key: Optional[str] = None) -> str:
        value = (target or "").strip()
        if not value:
            return ""
        source_key_upper = (source_key or "").upper()
        sensitive_source = any(
            marker in source_key_upper
            for marker in ("TOKEN", "PASSWORD", "SECRET", "SENDKEY", "USER_KEY", "API_KEY")
        )
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            if sensitive_source:
                return "***"
            if len(value) > 10:
                return f"{value[:3]}***{value[-2:]}"
            return value

        safe_netloc = parsed.netloc.rsplit("@", 1)[-1]
        safe_segments: List[str] = []
        path_segments = parsed.path.split("/")
        last_non_empty_index = next(
            (index for index in range(len(path_segments) - 1, -1, -1) if path_segments[index]),
            -1,
        )
        for index, segment in enumerate(path_segments):
            if not segment:
                safe_segments.append(segment)
                continue
            lower = segment.lower()
            looks_secret = (
                (source_key_upper == "NTFY_URL" and index == last_non_empty_index)
                or
                len(segment) >= 16
                or lower.startswith("bot")
                or "token" in lower
                or "sendkey" in lower
                or "secret" in lower
                or re.search(r"[a-zA-Z].*\d|\d.*[a-zA-Z]", segment) is not None and len(segment) >= 10
            )
            if looks_secret:
                safe_segments.append("***")
            else:
                safe_segments.append(segment)

        query = ""
        if parsed.query:
            query = "&".join(
                f"{part.split('=', 1)[0]}=***" if "=" in part else "***"
                for part in parsed.query.split("&")
                if part
            )
        return urlunparse(parsed._replace(netloc=safe_netloc, path="/".join(safe_segments), query=query, fragment=""))

    @staticmethod
    def _classify_notification_exception(exc: Exception) -> Tuple[str, bool]:
        if isinstance(exc, requests.exceptions.Timeout):
            return "timeout", True
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "network_error", True
        if isinstance(exc, requests.exceptions.RequestException):
            return "network_error", True
        return "unexpected_error", False

    @staticmethod
    def _setup_check(
        key: str,
        title: str,
        category: str,
        required: bool,
        status: str,
        message: str,
        next_step: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "key": key,
            "title": title,
            "category": category,
            "required": required,
            "status": status,
            "message": message,
            "next_step": next_step,
        }

    @staticmethod
    def _is_setup_relevant_env_key(key: str) -> bool:
        if key in {
            "STOCK_LIST",
            "DATABASE_PATH",
            "LITELLM_CONFIG",
            "LITELLM_MODEL",
            "LITELLM_FALLBACK_MODELS",
            "AGENT_LITELLM_MODEL",
            "VISION_MODEL",
            "OPENAI_BASE_URL",
            "OLLAMA_API_BASE",
            "FEISHU_STREAM_ENABLED",
        }:
            return True
        prefixes = (
            "LLM_",
            "GEMINI_",
            "OPENAI_",
            "ANTHROPIC_",
            "DEEPSEEK_",
            "OLLAMA_",
            "FEISHU_",
            "TELEGRAM_",
            "EMAIL_",
            "DISCORD_",
            "SLACK_",
            "DINGTALK_",
            "WECHAT_",
            "PUSHOVER_",
            "NTFY_",
            "GOTIFY_",
            "PUSHPLUS_",
            "SERVERCHAN",
            "CUSTOM_WEBHOOK",
            "WECOM_",
            "ASTRBOT_",
        )
        return key.startswith(prefixes) or key.endswith("_API_KEY") or key.endswith("_API_KEYS")

    def _build_setup_effective_config_map(self) -> Dict[str, str]:
        """Combine saved `.env` values with injected runtime env values for status checks."""
        saved_map = self._build_display_config_map(self._manager.read_config_map())
        effective_map = dict(saved_map)
        registered_keys = {key.upper() for key in get_registered_field_keys()}

        for raw_key, raw_value in os.environ.items():
            key = str(raw_key).upper()
            value = "" if raw_value is None else str(raw_value)
            if key in registered_keys or self._is_setup_relevant_env_key(key):
                effective_map[key] = value

        return self._build_display_config_map(effective_map)

    def _build_generation_backend_base_map(self) -> Dict[str, str]:
        """Build generation backend status config with saved values taking precedence."""
        saved_map = self._build_display_config_map(self._manager.read_config_map())
        effective_map = dict(saved_map)
        registered_keys = {key.upper() for key in get_registered_field_keys()}

        for raw_key, raw_value in os.environ.items():
            key = str(raw_key).upper()
            if key in effective_map:
                continue
            value = "" if raw_value is None else str(raw_value)
            if key in registered_keys or self._is_setup_relevant_env_key(key):
                effective_map[key] = value

        return self._build_display_config_map(effective_map)

    def _build_generation_backend_effective_map(
        self,
        *,
        items: Sequence[Dict[str, str]],
        mask_token: str,
    ) -> Dict[str, str]:
        """Merge saved/runtime config with unsaved status/smoke preview items."""
        effective_map = self._build_generation_backend_base_map()
        saved_map = self._build_display_config_map(self._manager.read_config_map())

        for item in self._filter_generation_backend_items(items):
            key = str(item.get("key", "")).strip().upper()
            if not key:
                continue
            value = "" if item.get("value") is None else str(item.get("value"))
            field_schema = get_field_definition(key, value)
            if bool(field_schema.get("is_sensitive", False)) and value == mask_token:
                if key in saved_map:
                    continue
            effective_map[key] = value

        return self._build_display_config_map(effective_map)

    @staticmethod
    def _has_any_config_value(effective_map: Dict[str, str], keys: Sequence[str]) -> bool:
        return any((effective_map.get(key) or "").strip() for key in keys)

    @staticmethod
    def _has_valid_ntfy_endpoint(effective_map: Dict[str, str]) -> bool:
        ntfy_server_url, ntfy_topic = resolve_ntfy_endpoint(effective_map.get("NTFY_URL"))
        return bool(ntfy_server_url and ntfy_topic)

    @staticmethod
    def _has_valid_gotify_config(effective_map: Dict[str, str]) -> bool:
        return bool(
            resolve_gotify_message_endpoint(effective_map.get("GOTIFY_URL"))
            and (effective_map.get("GOTIFY_TOKEN") or "").strip()
        )

    @classmethod
    def _anspire_legacy_llm_enabled(cls, effective_map: Dict[str, str]) -> bool:
        return llm_channel_map.anspire_legacy_llm_enabled(effective_map)

    @classmethod
    def _provider_has_setup_credentials(cls, provider: str, effective_map: Dict[str, str]) -> bool:
        normalized = canonicalize_llm_channel_protocol(provider)
        if normalized == "ollama":
            return True
        if normalized == "gemini" or normalized == "vertex_ai":
            return cls._has_any_config_value(effective_map, ("GEMINI_API_KEYS", "GEMINI_API_KEY"))
        if normalized == "anthropic":
            return cls._has_any_config_value(effective_map, ("ANTHROPIC_API_KEYS", "ANTHROPIC_API_KEY"))
        if normalized == "deepseek":
            return cls._has_any_config_value(effective_map, ("DEEPSEEK_API_KEYS", "DEEPSEEK_API_KEY"))
        if normalized == "openai":
            if cls._has_any_config_value(effective_map, ("OPENAI_API_KEYS", "OPENAI_API_KEY", "AIHUBMIX_KEY")):
                return True
            if (
                cls._anspire_legacy_llm_enabled(effective_map)
                and cls._has_any_config_value(effective_map, ("ANSPIRE_API_KEYS",))
            ):
                return True
            base_url = (effective_map.get("OPENAI_BASE_URL") or "").strip()
            return channel_allows_empty_api_key("openai", base_url)

        env_prefix = normalized.upper().replace("-", "_")
        return cls._has_any_config_value(
            effective_map,
            (f"{env_prefix}_API_KEYS", f"{env_prefix}_API_KEY"),
        )

    @classmethod
    def _has_setup_runtime_source_for_model(cls, model: str, effective_map: Dict[str, str]) -> bool:
        normalized_model = (model or "").strip()
        if not normalized_model:
            return False
        provider = _get_litellm_provider(normalized_model)
        return cls._provider_has_setup_credentials(provider, effective_map)

    @classmethod
    def _collect_setup_channel_models(cls, effective_map: Dict[str, str]) -> List[str]:
        models: List[str] = []
        seen: Set[str] = set()
        for raw_name in cls._split_csv(effective_map.get("LLM_CHANNELS") or ""):
            name = raw_name.strip()
            if not name:
                continue
            prefix = f"LLM_{name.upper()}"
            enabled_raw = effective_map.get(f"{prefix}_ENABLED")
            if name.lower() == "anspire" and not (enabled_raw or "").strip():
                enabled_raw = effective_map.get("ANSPIRE_LLM_ENABLED")
            enabled = parse_env_bool(enabled_raw, default=True)
            if not enabled:
                continue

            base_url = (effective_map.get(f"{prefix}_BASE_URL") or "").strip()
            if name.lower() == "anspire" and not base_url:
                base_url = (
                    effective_map.get("ANSPIRE_LLM_BASE_URL")
                    or ANSPIRE_LLM_BASE_URL_DEFAULT
                ).strip()
            protocol = (effective_map.get(f"{prefix}_PROTOCOL") or "").strip()
            if name.lower() == "anspire" and not protocol:
                protocol = "openai"
            api_key = (
                (effective_map.get(f"{prefix}_API_KEYS") or "").strip()
                or (effective_map.get(f"{prefix}_API_KEY") or "").strip()
            )
            if name.lower() == "anspire" and not api_key:
                api_key = (effective_map.get("ANSPIRE_API_KEYS") or "").strip()
            raw_models = cls._split_csv(effective_map.get(f"{prefix}_MODELS") or "")
            if name.lower() == "anspire" and not raw_models:
                raw_models = [
                    (
                        effective_map.get("ANSPIRE_LLM_MODEL")
                        or ANSPIRE_LLM_MODEL_DEFAULT
                    ).strip()
                ]
            if is_reserved_hermes_name(name):
                result = parse_hermes_channel(
                    enabled=True,
                    protocol=protocol or HERMES_DEFAULT_PROTOCOL,
                    base_url=base_url or HERMES_DEFAULT_BASE_URL,
                    api_key=(effective_map.get(f"{prefix}_API_KEY") or "").strip(),
                    api_keys_raw=(effective_map.get(f"{prefix}_API_KEYS") or "").strip(),
                    extra_headers_raw=(effective_map.get(f"{prefix}_EXTRA_HEADERS") or "").strip(),
                    models=raw_models or [HERMES_DEFAULT_MODEL],
                )
                channel = result.channel or {}
                for raw_model in channel.get("models") or []:
                    if raw_model and raw_model not in seen:
                        seen.add(raw_model)
                        models.append(raw_model)
                continue
            resolved_protocol = resolve_llm_channel_protocol(
                protocol,
                base_url=base_url,
                models=raw_models,
                channel_name=name,
            )
            if not raw_models or not resolved_protocol:
                continue
            if not api_key and not channel_allows_empty_api_key(resolved_protocol, base_url):
                continue

            for raw_model in raw_models:
                normalized_model = normalize_llm_channel_model(raw_model, resolved_protocol, base_url)
                if normalized_model and normalized_model not in seen:
                    seen.add(normalized_model)
                    models.append(normalized_model)
        return models

    @classmethod
    def _infer_setup_legacy_primary_model(cls, effective_map: Dict[str, str]) -> str:
        if cls._has_any_config_value(effective_map, ("GEMINI_API_KEYS", "GEMINI_API_KEY")):
            model = (effective_map.get("GEMINI_MODEL") or "gemini-3.1-pro-preview").strip()
            return model if "/" in model else f"gemini/{model}"
        if cls._has_any_config_value(effective_map, ("ANTHROPIC_API_KEYS", "ANTHROPIC_API_KEY")):
            model = (effective_map.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()
            return model if "/" in model else f"anthropic/{model}"
        if cls._has_any_config_value(effective_map, ("DEEPSEEK_API_KEYS", "DEEPSEEK_API_KEY")):
            return "deepseek/deepseek-chat"
        if cls._has_any_config_value(effective_map, ("OPENAI_API_KEYS", "OPENAI_API_KEY", "AIHUBMIX_KEY")):
            model = (effective_map.get("OPENAI_MODEL") or "gpt-5.5").strip()
            return model if "/" in model else f"openai/{model}"
        if (
            cls._anspire_legacy_llm_enabled(effective_map)
            and cls._has_any_config_value(effective_map, ("ANSPIRE_API_KEYS",))
        ):
            model = (
                effective_map.get("ANSPIRE_LLM_MODEL")
                or effective_map.get("OPENAI_MODEL")
                or ANSPIRE_LLM_MODEL_DEFAULT
            ).strip()
            return model if "/" in model else f"openai/{model}"
        if (effective_map.get("OLLAMA_API_BASE") or "").strip():
            model = (effective_map.get("OLLAMA_MODEL") or "").strip()
            return model if model.startswith("ollama/") else (f"ollama/{model}" if model else "ollama/local")
        return ""

    def _resolve_setup_primary_model(self, effective_map: Dict[str, str]) -> Tuple[str, str]:
        explicit_model = (effective_map.get("LITELLM_MODEL") or "").strip()
        yaml_models = self._collect_yaml_models_from_map(effective_map)
        channel_models = self._collect_setup_channel_models(effective_map)

        if explicit_model:
            if _uses_direct_env_provider(explicit_model):
                return explicit_model, "explicit"
            has_direct_source = self._has_setup_runtime_source_for_model(explicit_model, effective_map)
            if yaml_models and explicit_model not in set(yaml_models):
                return "", "主要模型未出现在当前 LiteLLM YAML model_list 中"
            if channel_models and explicit_model not in set(channel_models):
                return "", "主要模型未出现在已启用连接的模型列表中"
            if yaml_models or channel_models or has_direct_source:
                return explicit_model, "explicit"
            return "", "主要模型缺少可用连接或匹配的 API 密钥"

        if yaml_models:
            return yaml_models[0], "yaml"
        if channel_models:
            return channel_models[0], "channel"

        legacy_model = self._infer_setup_legacy_primary_model(effective_map)
        if legacy_model:
            return legacy_model, "legacy"

        return "", "尚未检测到主要模型配置"

    def _build_setup_primary_llm_check(self, effective_map: Dict[str, str]) -> Dict[str, Any]:
        generation_backend = normalize_backend_id(
            effective_map.get("GENERATION_BACKEND"),
            default=LITELLM_BACKEND_ID,
        )
        if generation_backend in LOCAL_CLI_GENERATION_BACKEND_IDS:
            preset = resolve_local_cli_preset(generation_backend)
            if shutil.which(preset.executable):
                return self._setup_check(
                    "llm_primary",
                    "主要模型",
                    "ai_model",
                    True,
                    "configured",
                    f"已启用 {preset.display_name} 本地生成 Backend（experimental/limited）。",
                )
            return self._setup_check(
                "llm_primary",
                "主要模型",
                "ai_model",
                True,
                "needs_action",
                (
                    "已选择 codex_cli，但 StockPulse 后端进程当前 PATH 中找不到 codex 可执行文件。"
                    if generation_backend == CODEX_CLI_BACKEND_ID
                    else f"已选择 {generation_backend}，但未找到 {preset.executable} 可执行文件。"
                ),
                (
                    "请确认 Codex CLI 已安装到后端 PATH 可见目录；桌面端请完全退出并重开。"
                    "打开 Codex CLI 交互窗口不会改变已运行后端的 PATH；若找到后仍失败，再检查 Codex CLI 登录态，"
                    "或将分析生成方式设回默认模型配置。"
                    if generation_backend == CODEX_CLI_BACKEND_ID
                    else "请先安装并登录对应 CLI，或将分析生成方式设回默认模型配置。"
                ),
            )

        model, source = self._resolve_setup_primary_model(effective_map)
        if model:
            source_label = {
                "explicit": "显式主要模型",
                "yaml": "LiteLLM YAML",
                "channel": "模型连接",
                "legacy": "legacy provider",
            }.get(source, source)
            return self._setup_check(
                "llm_primary",
                "主要模型",
                "ai_model",
                True,
                "configured",
                f"已检测到 {source_label}: {model}",
            )
        return self._setup_check(
            "llm_primary",
            "主要模型",
            "ai_model",
            True,
            "needs_action",
            source,
            "请在“模型接入”中添加模型服务，或在任务路由中选择主要模型。",
        )

    def _build_setup_agent_llm_check(
        self,
        effective_map: Dict[str, str],
        primary_check: Dict[str, Any],
    ) -> Dict[str, Any]:
        generation_backend = normalize_backend_id(
            effective_map.get("GENERATION_BACKEND"),
            default=LITELLM_BACKEND_ID,
        )
        agent_backend = normalize_backend_id(
            effective_map.get("AGENT_GENERATION_BACKEND"),
            default=AUTO_AGENT_BACKEND_ID,
        )
        if agent_backend in GENERATION_ONLY_BACKEND_IDS:
            return self._setup_check(
                "llm_agent",
                "Agent 模型",
                "agent",
                True,
                "needs_action",
                f"Agent 工具调用暂不支持 {agent_backend} text-only backend。",
                "请将 Agent 生成方式设为自动或默认模型配置，并配置支持工具调用的模型连接。",
            )

        agent_model_raw = (effective_map.get("AGENT_LITELLM_MODEL") or "").strip()
        hermes_routes = set(self._collect_hermes_channel_models_from_map(effective_map))
        non_hermes_routes = set(self._collect_non_hermes_channel_models_from_map(effective_map))
        if not agent_model_raw:
            if generation_backend in LOCAL_CLI_GENERATION_BACKEND_IDS:
                local_cli_display = resolve_local_cli_preset(generation_backend).display_name
                litellm_model, _source = self._resolve_setup_primary_model(effective_map)
                if litellm_model:
                    if litellm_model in hermes_routes and litellm_model not in non_hermes_routes:
                        return self._setup_check(
                            "llm_agent",
                            "Agent 模型",
                            "agent",
                            True,
                            "needs_action",
                            f"普通分析使用 {local_cli_display}；但当前 LiteLLM Agent 路径继承的是 Hermes-only 模型，"
                            "Hermes Phase 3 不支持 Agent 工具调用。",
                            "如需使用问股 Agent，请为 Agent 选择非 Hermes 的主要模型，"
                            "或配置包含非 Hermes deployment 的混合 Agent 路由。",
                        )
                    return self._setup_check(
                        "llm_agent",
                        "Agent 模型",
                        "agent",
                        True,
                        "configured",
                        f"普通分析使用 {local_cli_display}；Agent 工具调用仍使用主要模型: {litellm_model}",
                    )
                if agent_backend == LITELLM_BACKEND_ID:
                    return self._setup_check(
                        "llm_agent",
                        "Agent 模型",
                        "agent",
                        True,
                        "needs_action",
                        "Agent 生成方式已固定为默认模型配置，但未检测到可用模型配置。",
                        "如需使用问股 Agent，请先添加模型连接并选择主要模型或 Agent 主要模型。",
                    )
                return self._setup_check(
                    "llm_agent",
                    "Agent 模型",
                    "agent",
                    True,
                    "needs_action",
                    "Agent 工具调用需要默认模型配置；本机 CLI 生成方式不会被自动继承。",
                    "如需使用问股 Agent，请先配置模型连接，或将 Agent 生成方式固定为默认模型配置后补齐模型。",
                )
            if primary_check["status"] == "configured":
                primary_model, _source = self._resolve_setup_primary_model(effective_map)
                if primary_model in hermes_routes and primary_model not in non_hermes_routes:
                    return self._setup_check(
                        "llm_agent",
                        "Agent 模型",
                        "agent",
                        True,
                        "needs_action",
                        "Hermes Phase 3 不支持 Agent 工具调用，且当前继承的主要模型没有非 Hermes deployment。",
                        "请选择非 Hermes Agent 模型，或配置包含非 Hermes deployment 的混合 Agent 路由。",
                    )
                return self._setup_check(
                    "llm_agent",
                    "Agent 模型",
                    "agent",
                    True,
                    "inherited",
                    "未单独配置 Agent 主要模型，将继承主要模型。",
                )
            return self._setup_check(
                "llm_agent",
                "Agent 模型",
                "agent",
                True,
                "needs_action",
                "Agent 未配置独立模型，且主要模型尚不可用。",
                "请先补齐主要模型配置。",
            )

        configured_models = set(
            self._collect_yaml_models_from_map(effective_map)
            or self._collect_setup_channel_models(effective_map)
        )
        agent_model = normalize_agent_litellm_model(agent_model_raw, configured_models=configured_models)
        if agent_model in hermes_routes and agent_model not in non_hermes_routes:
            return self._setup_check(
                "llm_agent",
                "Agent 模型",
                "agent",
                True,
                "needs_action",
                f"Agent 主要模型 {agent_model} 只有 Hermes deployment，Phase 3 不支持 Agent 工具调用。",
                "请选择非 Hermes Agent 模型，或配置 mixed route 中的非 Hermes deployment。",
            )
        configured_agent_message = f"已配置 Agent 主要模型: {agent_model}"
        if generation_backend in LOCAL_CLI_GENERATION_BACKEND_IDS:
            local_cli_display = resolve_local_cli_preset(generation_backend).display_name
            configured_agent_message = (
                f"普通分析使用 {local_cli_display}；Agent 工具调用仍使用主要模型: {agent_model}"
            )
        if _uses_direct_env_provider(agent_model):
            return self._setup_check(
                "llm_agent",
                "Agent 模型",
                "agent",
                True,
                "configured",
                configured_agent_message,
            )
        if (
            not configured_models
            and self._has_setup_runtime_source_for_model(agent_model, effective_map)
        ) or agent_model in configured_models:
            return self._setup_check(
                "llm_agent",
                "Agent 模型",
                "agent",
                True,
                "configured",
                configured_agent_message,
            )

        return self._setup_check(
            "llm_agent",
            "Agent 模型",
            "agent",
            True,
            "needs_action",
            f"Agent 主要模型 {agent_model} 缺少可用连接或匹配的 API 密钥。",
            "请重新选择 Agent 主要模型或补齐对应模型连接配置。",
        )

    def _build_setup_stock_list_check(self, effective_map: Dict[str, str]) -> Dict[str, Any]:
        stocks = split_stock_list(effective_map.get("STOCK_LIST") or "")
        if stocks:
            return self._setup_check(
                "stock_list",
                "自选股",
                "base",
                True,
                "configured",
                f"已配置 {len(stocks)} 只股票。",
            )
        return self._setup_check(
            "stock_list",
            "自选股",
            "base",
            True,
            "needs_action",
            "当前 STOCK_LIST 为空。",
            "请至少添加 1 只股票用于首次试跑。",
        )

    def _build_setup_notification_check(self, effective_map: Dict[str, str]) -> Dict[str, Any]:
        configured = (
            self._has_any_config_value(effective_map, ("WECHAT_WEBHOOK_URL", "DISCORD_WEBHOOK_URL", "DINGTALK_WEBHOOK_URL"))
            or is_feishu_static_env_configured(effective_map)
            or (
                self._has_any_config_value(effective_map, ("TELEGRAM_BOT_TOKEN",))
                and self._has_any_config_value(effective_map, ("TELEGRAM_CHAT_ID",))
            )
            or (
                self._has_any_config_value(effective_map, ("EMAIL_SENDER",))
                and self._has_any_config_value(effective_map, ("EMAIL_PASSWORD",))
            )
            or (
                self._has_any_config_value(effective_map, ("DINGTALK_APP_KEY",))
                and self._has_any_config_value(effective_map, ("DINGTALK_APP_SECRET",))
            )
            or (
                self._has_any_config_value(effective_map, ("DISCORD_BOT_TOKEN",))
                and self._has_any_config_value(effective_map, ("DISCORD_MAIN_CHANNEL_ID", "DISCORD_CHANNEL_ID"))
            )
            or (
                self._has_any_config_value(effective_map, ("PUSHOVER_USER_KEY",))
                and self._has_any_config_value(effective_map, ("PUSHOVER_API_TOKEN",))
            )
            or self._has_any_config_value(effective_map, ("SLACK_WEBHOOK_URL",))
            or (
                self._has_any_config_value(effective_map, ("SLACK_BOT_TOKEN",))
                and self._has_any_config_value(effective_map, ("SLACK_CHANNEL_ID",))
            )
            or self._has_any_config_value(
                effective_map,
                (
                    "PUSHPLUS_TOKEN",
                    "SERVERCHAN3_SENDKEY",
                    "CUSTOM_WEBHOOK_URLS",
                    "WECOM_WEBHOOK_URL",
                    "ASTRBOT_URL",
                ),
            )
            or self._has_valid_ntfy_endpoint(effective_map)
            or self._has_valid_gotify_config(effective_map)
        )
        if configured:
            return self._setup_check(
                "notification",
                "通知渠道",
                "notification",
                False,
                "configured",
                "已检测到至少一个通知渠道配置。",
            )
        return self._setup_check(
            "notification",
            "通知渠道",
            "notification",
            False,
            "optional",
            "通知为可选项，未配置也不影响首次跑通。",
            "需要推送时可稍后配置飞书、钉钉、Telegram、邮件或其他通知渠道。",
        )

    def _build_setup_storage_check(self, effective_map: Dict[str, str]) -> Dict[str, Any]:
        db_path = Path((effective_map.get("DATABASE_PATH") or "./data/stock_analysis.db").strip()).expanduser()
        parent = db_path.parent if db_path.parent != Path("") else Path(".")
        probe = parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent

        if not probe.exists() or not probe.is_dir():
            return self._setup_check(
                "storage",
                "数据库 / 本地存储",
                "system",
                True,
                "needs_action",
                f"数据库路径父目录不可用: {parent}",
                "请检查 DATABASE_PATH 或上级目录权限。",
            )

        if os.access(probe, os.W_OK):
            detail = f"数据库路径可用: {db_path}"
            if not parent.exists():
                detail = f"数据库上级目录可创建: {parent}"
            return self._setup_check(
                "storage",
                "数据库 / 本地存储",
                "system",
                True,
                "configured",
                detail,
            )

        return self._setup_check(
            "storage",
            "数据库 / 本地存储",
            "system",
            True,
            "needs_action",
            f"数据库路径上级目录不可写: {probe}",
            "请调整 DATABASE_PATH 或目录权限。",
        )

    @staticmethod
    def _is_safe_base_url(value: str) -> bool:
        """Block link-local and cloud metadata addresses to prevent SSRF.

        Allows localhost / private-LAN addresses (e.g. Ollama on 192.168.x.x)
        but blocks 169.254.x.x (AWS/Azure/GCP/Alibaba instance-metadata service)
        and other known metadata hostnames.
        """
        import ipaddress

        try:
            parsed = urlparse(value)
            raw_host = parsed.hostname or ""
        except ValueError:
            return False
        if not raw_host:
            return True
        host = SystemConfigService._normalize_hostname_for_security(raw_host)
        if not host:
            return False
        # Known cloud metadata hostnames
        _BLOCKED_HOSTS = frozenset({
            "169.254.169.254",
            "metadata.google.internal",
            "100.100.100.200",
        })
        if host in _BLOCKED_HOSTS:
            return False
        if SystemConfigService._is_noncanonical_ipv4_numeric_host(host):
            return False
        # Numeric IPs: block link-local range (169.254.0.0/16), including IPv4-mapped IPv6.
        try:
            addr = ipaddress.ip_address(host)
            candidate_addrs = [addr]
            mapped_addr = getattr(addr, "ipv4_mapped", None)
            if mapped_addr is not None:
                candidate_addrs.append(mapped_addr)
            for candidate_addr in candidate_addrs:
                if str(candidate_addr) in _BLOCKED_HOSTS or candidate_addr.is_link_local:
                    return False
        except ValueError:
            pass  # hostname, not an IP — already checked against blocklist above
        return True

    @staticmethod
    def _build_llm_models_url(base_url: str, protocol: str = "openai") -> str:
        """Convert a Connection base URL into its model discovery endpoint."""
        if not SystemConfigService._is_valid_llm_base_url(base_url):
            raise ValueError("LLM channel base URL must be a valid absolute URL")
        if not SystemConfigService._is_safe_base_url(base_url):
            raise ValueError("LLM channel base URL points to a restricted address")

        parsed = urlparse(base_url)
        normalized = (parsed.path or "").rstrip("/")
        if str(protocol or "").strip().lower() == "ollama":
            if normalized.endswith("/api/tags"):
                models_path = normalized
            else:
                for suffix in (
                    "/v1/chat/completions",
                    "/v1/completions",
                    "/chat/completions",
                    "/completions",
                    "/v1",
                    "/api",
                ):
                    if normalized.endswith(suffix):
                        normalized = normalized[: -len(suffix)]
                        break
                models_path = f"{normalized}/api/tags" if normalized else "/api/tags"
        else:
            for suffix in ("/chat/completions", "/completions"):
                if normalized.endswith(suffix):
                    normalized = normalized[: -len(suffix)]
                    break
            if normalized.endswith("/models"):
                models_path = normalized or "/models"
            else:
                models_path = f"{normalized}/models" if normalized else "/models"
        models_url = urlunparse(parsed._replace(path=models_path, params="", query="", fragment=""))
        if not SystemConfigService._is_valid_llm_base_url(models_url):
            raise ValueError("LLM channel models URL must be a valid absolute URL")
        if not SystemConfigService._is_safe_base_url(models_url):
            raise ValueError("LLM channel models URL points to a restricted address")
        return models_url

    @staticmethod
    def _get_runtime_llm_temperature() -> float:
        """Return the current configured LLM temperature for ad-hoc channel tests."""
        config = Config._load_from_env()
        try:
            return float(getattr(config, "llm_temperature", 0.7))
        except (TypeError, ValueError):
            return 0.7

    @classmethod
    def _build_llm_channel_result(
        cls,
        *,
        success: bool,
        message: str,
        error: Optional[str],
        stage: Optional[str],
        error_code: Optional[str],
        retryable: Optional[bool],
        details: Optional[Dict[str, Any]] = None,
        resolved_protocol: Optional[str] = None,
        resolved_model: Optional[str] = None,
        models: Optional[List[str]] = None,
        latency_ms: Optional[int] = None,
        capability_results: Optional[Dict[str, Any]] = None,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "success": success,
            "message": cls._sanitize_llm_error_text(message, redaction_values=redaction_values),
            "error": cls._sanitize_llm_error_text(error, redaction_values=redaction_values) if error else None,
            "stage": stage,
            "error_code": error_code,
            "retryable": retryable,
            "details": cls._sanitize_llm_details(details, redaction_values=redaction_values),
            "resolved_protocol": cls._sanitize_llm_error_text(
                resolved_protocol,
                redaction_values=redaction_values,
            ) if resolved_protocol is not None else None,
            "latency_ms": latency_ms,
        }
        if resolved_model is not None or models is None:
            payload["resolved_model"] = cls._sanitize_llm_error_text(
                resolved_model,
                redaction_values=redaction_values,
            ) if resolved_model is not None else resolved_model
        if models is not None:
            payload["models"] = cls._sanitize_llm_value(models, redaction_values=redaction_values)
        if capability_results is not None:
            payload["capability_results"] = cls._sanitize_llm_value(capability_results, redaction_values=redaction_values)
        return payload

    @staticmethod
    def _merge_llm_diagnostic_details(
        base_details: Optional[Dict[str, Any]],
        diagnostic: _LLMDiagnostic,
    ) -> Dict[str, Any]:
        details: Dict[str, Any] = dict(base_details or {})
        if diagnostic.reason:
            details.setdefault("reason", diagnostic.reason)
        details.update(diagnostic.details)
        return details

    @staticmethod
    def _build_redaction_values(*values: Any) -> Set[str]:
        return build_hermes_redaction_values(*values)

    @staticmethod
    def _comma_flexible_secret_pattern(secret: str) -> Optional[re.Pattern[str]]:
        normalized = re.sub(r"(?i)^\s*authorization\s*[:=]\s*", "", str(secret or "").strip())
        normalized = re.sub(r"(?i)^\s*bearer\s+", "", normalized)
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if len(parts) <= 1:
            return None
        return re.compile(
            r"(?i)(?:authorization\s*[:=]\s*)?(?:bearer\s+)?"
            + r"\s*,\s*".join(re.escape(part) for part in parts)
        )

    @classmethod
    def _sanitize_llm_error_text(cls, text: Any, *, redaction_values: Optional[Set[str]] = None) -> str:
        if text is None:
            return ""
        sanitized = str(text).strip()
        if not sanitized:
            return ""
        for secret in sorted((redaction_values or set()), key=len, reverse=True):
            pattern = cls._comma_flexible_secret_pattern(secret)
            if pattern is not None:
                sanitized = pattern.sub("[REDACTED]", sanitized)
        for secret in sorted((redaction_values or set()), key=len, reverse=True):
            if secret:
                sanitized = sanitized.replace(secret, "[REDACTED]")

        patterns = [
            (r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)", r"\1[REDACTED]"),
            (r"(?i)(api[_-]?key\s*[:=]\s*)([^\s,;]+)", r"\1[REDACTED]"),
            (r"(?i)(cookie\s*[:=]\s*)([^\s,;]+)", r"\1[REDACTED]"),
            (r"(?i)bearer\s+[a-z0-9._\-]+", "Bearer [REDACTED]"),
            (r"(?i)sk-[a-z0-9_\-]+", "[REDACTED]"),
        ]
        for pattern, replacement in patterns:
            sanitized = re.sub(pattern, replacement, sanitized)
        return sanitize_diagnostic_text(sanitized, max_length=300)

    @classmethod
    def _sanitize_llm_details(
        cls,
        details: Optional[Dict[str, Any]],
        *,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        if not details:
            return {}
        sanitized = cls._sanitize_llm_value(details, redaction_values=redaction_values)
        return sanitized if isinstance(sanitized, dict) else {}

    @classmethod
    def _sanitize_llm_value(cls, value: Any, *, redaction_values: Optional[Set[str]] = None) -> Any:
        if isinstance(value, str):
            return cls._sanitize_llm_error_text(value, redaction_values=redaction_values)
        if isinstance(value, dict):
            return {
                cls._sanitize_llm_error_text(key, redaction_values=redaction_values): cls._sanitize_llm_value(
                    item,
                    redaction_values=redaction_values,
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                cls._sanitize_llm_value(item, redaction_values=redaction_values)
                for item in value
            ]
        if isinstance(value, tuple):
            return [
                cls._sanitize_llm_value(item, redaction_values=redaction_values)
                for item in value
            ]
        return value

    @staticmethod
    def _classify_llm_http_error(status_code: int, error_text: str) -> _LLMDiagnostic:
        lowered = (error_text or "").lower()
        if SystemConfigService._has_model_access_denied_signal(error_text or ""):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model is not available for this channel",
                "model_access_denied",
            )
        if "model" in lowered and any(token in lowered for token in ("not found", "does not exist", "unknown")):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model could not be found on this channel",
                "model_not_found",
            )
        if status_code == 402 or any(token in lowered for token in ("billing", "balance", "insufficient balance")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or billing limits",
                "insufficient_balance",
            )
        if any(token in lowered for token in ("quota", "insufficient_quota", "quota exceeded")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or rate limiting",
                "quota_exceeded",
            )
        if status_code == 429 or any(token in lowered for token in ("rate limit", "too many requests", "rpm", "tpm")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or rate limiting",
                "rate_limit",
            )
        if SystemConfigService._has_transport_blocked_signal(error_text or ""):
            return _LLMDiagnostic(
                "network_error",
                True,
                "LLM request failed before a valid response was returned",
                "network_error",
            )
        if SystemConfigService._has_request_blocked_signal(error_text or ""):
            return _LLMDiagnostic(
                "request_blocked",
                False,
                "LLM request was blocked by provider or gateway policy",
                "provider_blocked",
            )
        if status_code in {401, 403} or any(token in lowered for token in ("unauthorized", "forbidden", "invalid api key", "authentication")):
            return _LLMDiagnostic("auth", False, "LLM authentication failed", "api_key_rejected")
        if status_code == 404:
            return _LLMDiagnostic(
                "network_error",
                False,
                "LLM model discovery endpoint could not be found",
                "endpoint_not_found",
            )
        if any(token in lowered for token in ("timeout", "timed out")):
            return _LLMDiagnostic("timeout", True, "LLM request timed out", "timeout")
        return _LLMDiagnostic(
            "network_error",
            status_code >= 500,
            "LLM request failed before a valid response was returned",
            "http_error",
        )

    @staticmethod
    def _has_model_not_found_signal(text: str) -> bool:
        lowered = text.lower()

        model_candidates = [
            re.search(r"model\s+not\s+found\s*[:：]?\s*[`\"']?\s*([a-z0-9._/-]{2,})", lowered),
            re.search(r"model\s*[`\"']?\s*([a-z0-9._/-]{2,})\s*[`\"']?\s+does\s+not\s+exist", lowered),
            re.search(r"model\s+does\s+not\s+exist\s*[:：]?\s*[`\"']?\s*([a-z0-9._/-]{2,})", lowered),
            re.search(r"unknown\s+model\s*[:：]?\s*[`\"']?\s*([a-z0-9._/-]{2,})", lowered),
            re.search(r"no\s+such\s+model\s*[:：]?\s*[`\"']?\s*([a-z0-9._/-]{2,})", lowered),
        ]

        for match in model_candidates:
            if not match:
                continue
            model_id = match.group(1).strip()
            if model_id and not model_id.startswith("/") and "http" not in model_id:
                return True

        return False

    @staticmethod
    def _has_model_access_denied_signal(text: str) -> bool:
        lowered = text.lower()
        if "model" not in lowered:
            return False

        # Best-effort classifier for observed provider messages. Keep it gated by
        # an explicit "model" mention plus access/disabled/unavailable signals so
        # unrelated provider-specific failures continue to use the fallback path.
        access_denied_tokens = (
            "not authorized",
            "not allowed",
            "access denied",
            "permission denied",
            "model disabled",
            "model is disabled",
            "disabled model",
            "model has been disabled",
            "model not enabled",
            "model not available",
            "model is not available",
        )
        return any(token in lowered for token in access_denied_tokens)

    @staticmethod
    def _has_request_blocked_signal(text: str) -> bool:
        lowered = text.lower()
        if SystemConfigService._has_transport_blocked_signal(lowered):
            return False
        blocked_tokens = (
            "your request was blocked",
            "the request was blocked",
            "request blocked by policy",
            "blocked by policy",
            "blocked due to policy",
            "moderation_blocked",
            "policy_blocked",
            "请求被拦截",
        )
        return any(token in lowered for token in blocked_tokens)

    @staticmethod
    def _has_transport_blocked_signal(text: str) -> bool:
        lowered = text.lower()
        transport_tokens = (
            "connection blocked",
            "connection request was blocked",
            "network blocked",
            "blocked by network policy",
            "blocked by firewall",
            "firewall blocked",
        )
        return any(token in lowered for token in transport_tokens)

    @staticmethod
    def _has_provider_prefix_mismatch_signal(text: str) -> bool:
        lowered = text.lower()
        mismatch_tokens = (
            "provider prefix",
            "llm provider not provided",
            "invalid provider",
            "unknown provider",
            "custom_llm_provider",
            "not a valid llm provider",
        )
        return any(token in lowered for token in mismatch_tokens)

    @staticmethod
    def _classify_llm_exception(exc: Exception) -> _LLMDiagnostic:
        exc_name = type(exc).__name__.lower()
        text = str(exc).lower()
        if isinstance(exc, TimeoutError) or "timeout" in exc_name or "timed out" in text:
            return _LLMDiagnostic("timeout", True, "LLM request timed out", "timeout")
        if any(token in text for token in ("billing", "balance", "insufficient balance")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or billing limits",
                "insufficient_balance",
            )
        if any(token in text for token in ("quota", "insufficient_quota", "quota exceeded")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or rate limiting",
                "quota_exceeded",
            )
        if "ratelimit" in exc_name or any(token in text for token in ("rate limit", "too many requests", "rpm", "tpm")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or rate limiting",
                "rate_limit",
            )
        if SystemConfigService._has_provider_prefix_mismatch_signal(text):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model prefix does not match this channel",
                "provider_prefix_mismatch",
            )
        if SystemConfigService._has_model_access_denied_signal(str(exc)):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model is not available for this channel",
                "model_access_denied",
            )
        if SystemConfigService._has_request_blocked_signal(str(exc)):
            return _LLMDiagnostic(
                "request_blocked",
                False,
                "LLM request was blocked by provider or gateway policy",
                "provider_blocked",
            )
        if any(token in exc_name for token in ("auth", "permission")) or any(token in text for token in ("unauthorized", "forbidden", "invalid api key", "authentication")):
            return _LLMDiagnostic("auth", False, "LLM authentication failed", "api_key_rejected")
        if ("notfound" in exc_name or "model" in text) and (
            "not found" in text or "does not exist" in text or "unknown model" in text
        ) and SystemConfigService._has_model_not_found_signal(text):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model could not be found on this channel",
                "model_not_found",
            )
        if "dns" in text or "name resolution" in text or "temporary failure in name resolution" in text:
            return _LLMDiagnostic("network_error", True, "LLM request failed before a valid response was returned", "dns_error")
        if "refused" in text or "connection refused" in text:
            return _LLMDiagnostic("network_error", True, "LLM request failed before a valid response was returned", "connection_refused")
        if "ssl" in text or "tls" in text or "certificate" in text:
            return _LLMDiagnostic("network_error", True, "LLM request failed before a valid response was returned", "tls_error")
        if any(token in exc_name for token in ("connection", "network")) or any(
            token in text for token in ("connection", "network", "firewall")
        ):
            return _LLMDiagnostic("network_error", True, "LLM request failed before a valid response was returned", "network_error")
        return _LLMDiagnostic("network_error", False, "LLM channel test failed", "unknown_error")

    @staticmethod
    def _extract_llm_completion_content(response: Any) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        def _field(obj: Any, key: str) -> Any:
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        def _text_from_blocks(blocks: Any) -> str:
            if not isinstance(blocks, list):
                return ""
            text_parts: List[str] = []
            for block in blocks:
                if isinstance(block, str):
                    text_parts.append(block)
                    continue
                block_type = str(_field(block, "type") or "").strip().lower()
                if block_type and block_type not in {"text", "output_text"}:
                    continue
                text = _field(block, "text")
                if text is None:
                    text = _field(block, "content")
                if isinstance(text, str) and text:
                    text_parts.append(text)
            return strip_leading_think_wrapper("".join(text_parts))

        if response is None:
            return "", "empty_response", "Completion returned no response object", "null_response"

        choices = _field(response, "choices")
        if not choices:
            return "", "format_error", "Completion response did not include choices", "malformed_choices"

        choice = choices[0]
        message = _field(choice, "message")
        content_blocks = _field(choice, "content_blocks")
        if content_blocks is None and message is not None:
            content_blocks = _field(message, "content_blocks")
        if content_blocks is not None:
            content = _text_from_blocks(content_blocks)
            if content:
                return content, None, None, None

        if message is None:
            return "", "format_error", "Completion response did not include a message object", "malformed_choices"
        if isinstance(message, dict):
            has_content = "content" in message
        else:
            has_content = hasattr(message, "content")
        if not has_content:
            return "", "format_error", "Completion message did not include a content field", "malformed_choices"
        raw_content = _field(message, "content")
        if raw_content is None:
            return "", "empty_response", "Completion returned null message content", "null_content"
        content = (
            _text_from_blocks(raw_content)
            if isinstance(raw_content, list)
            else strip_leading_think_wrapper(str(raw_content))
        )
        if not content:
            return "", "empty_response", "Completion returned an empty message content", "empty_content"
        return content, None, None, None

    @staticmethod
    def _extract_llm_discovery_error(response: requests.Response) -> str:
        """Extract a concise error message from a failed model discovery response."""
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                message = str(
                    error_payload.get("message")
                    or error_payload.get("code")
                    or ""
                ).strip()
                if message:
                    return message

            message = str(payload.get("message") or payload.get("detail") or "").strip()
            if message:
                return message

        text = response.text.strip()
        if text:
            return text[:200]
        return f"HTTP {response.status_code}"

    @staticmethod
    def _extract_discovered_llm_models(payload: Any) -> List[str]:
        """Normalize common `/models` response shapes into a unique model ID list."""
        raw_models: List[Any] = []
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                raw_models = payload["data"]
            elif isinstance(payload.get("models"), list):
                raw_models = payload["models"]
        elif isinstance(payload, list):
            raw_models = payload

        models: List[str] = []
        seen: Set[str] = set()
        for entry in raw_models:
            if isinstance(entry, str):
                model_id = entry.strip()
            elif isinstance(entry, dict):
                model_id = str(
                    entry.get("id") or entry.get("model") or entry.get("name") or ""
                ).strip()
            else:
                model_id = ""

            if not model_id or model_id in seen:
                continue

            seen.add(model_id)
            models.append(model_id)

        return models

    @staticmethod
    def _validate_cross_field(
        effective_map: Dict[str, str],
        updated_keys: Set[str],
        previous_effective_map: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Validate dependencies across multiple keys."""
        issues: List[Dict[str, Any]] = []

        token_value = (effective_map.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id_value = (effective_map.get("TELEGRAM_CHAT_ID") or "").strip()
        if token_value and not chat_id_value and (
            "TELEGRAM_BOT_TOKEN" in updated_keys or "TELEGRAM_CHAT_ID" in updated_keys
        ):
            issues.append(
                {
                    "key": "TELEGRAM_CHAT_ID",
                    "code": "missing_dependency",
                    "message": "TELEGRAM_CHAT_ID is required when TELEGRAM_BOT_TOKEN is set",
                    "severity": "error",
                    "expected": "non-empty TELEGRAM_CHAT_ID",
                    "actual": chat_id_value,
                }
            )

        feishu_relevant_keys = {
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "FEISHU_WEBHOOK_URL",
            "FEISHU_WEBHOOK_SECRET",
            "FEISHU_WEBHOOK_KEYWORD",
            "FEISHU_STREAM_ENABLED",
            "FEISHU_FOLDER_TOKEN",
            "FEISHU_CHAT_ID",
        }
        has_feishu_app_id = bool((effective_map.get("FEISHU_APP_ID") or "").strip())
        has_feishu_app_secret = bool((effective_map.get("FEISHU_APP_SECRET") or "").strip())
        has_feishu_app_credentials_complete = has_feishu_app_id and has_feishu_app_secret
        has_feishu_app_credentials = has_feishu_app_id or has_feishu_app_secret
        has_feishu_folder_token = bool((effective_map.get("FEISHU_FOLDER_TOKEN") or "").strip())
        has_feishu_full_cloud_doc_credentials = (
            has_feishu_app_credentials_complete
            and has_feishu_folder_token
        )
        # Match runtime semantics: Config.from_env only enables stream mode
        # when the value is exactly "true" (case-insensitive).
        feishu_stream_enabled = (
            (effective_map.get("FEISHU_STREAM_ENABLED") or "false")
            .strip()
            .lower()
            == "true"
        )
        has_feishu_stream_route = feishu_stream_enabled and has_feishu_app_credentials_complete
        has_feishu_app_bot_route = is_feishu_app_bot_env_configured(effective_map)
        if (
            has_feishu_app_credentials
            and not has_feishu_full_cloud_doc_credentials
            and not is_feishu_static_env_configured(effective_map)
            and not has_feishu_stream_route
            and not has_feishu_app_bot_route
            and (updated_keys & feishu_relevant_keys)
        ):
            issues.append(
                {
                    "key": "FEISHU_CHAT_ID",
                    "code": "feishu_mode_mismatch",
                    "message": (
                        "仅配置 FEISHU_APP_ID / FEISHU_APP_SECRET 不会开启飞书静态通知；"
                        "App Bot 主动推送需要同时配置 FEISHU_CHAT_ID，"
                        "Webhook 推送请填写 FEISHU_WEBHOOK_URL；"
                        "事件订阅请使用 FEISHU_STREAM_ENABLED=true 并完成应用发布与权限配置。"
                    ),
                    "severity": "warning",
                    "expected": (
                        "static notification: FEISHU_WEBHOOK_URL or "
                        "FEISHU_APP_ID + FEISHU_APP_SECRET + FEISHU_CHAT_ID; "
                        "event subscription: FEISHU_STREAM_ENABLED=true"
                    ),
                    "actual": "app credentials without notification target",
                }
            )

        issues.extend(
            SystemConfigService._validate_llm_channel_map(
                effective_map=effective_map,
                updated_keys=updated_keys,
            )
        )
        issues.extend(
            SystemConfigService._validate_llm_runtime_selection(
                effective_map=effective_map,
                updated_keys=updated_keys,
                previous_effective_map=previous_effective_map,
            )
        )

        if parse_env_bool(effective_map.get("NOTIFICATION_DAILY_DIGEST_ENABLED"), default=False):
            issues.append(
                {
                    "key": "NOTIFICATION_DAILY_DIGEST_ENABLED",
                    "code": "reserved_notification_daily_digest",
                    "message": (
                        "NOTIFICATION_DAILY_DIGEST_ENABLED is reserved; "
                        "the current P4 implementation does not send daily digests."
                    ),
                    "severity": "warning",
                    "expected": "reserved flag only",
                    "actual": effective_map.get("NOTIFICATION_DAILY_DIGEST_ENABLED", ""),
                }
            )

        return issues

    @staticmethod
    def _validate_llm_channel_map(effective_map: Dict[str, str], updated_keys: Set[str]) -> List[Dict[str, Any]]:
        """Validate channel-style LLM configuration stored in `.env`."""
        issues: List[Dict[str, Any]] = []
        if SystemConfigService._uses_litellm_yaml(effective_map):
            return issues

        raw_channels = (effective_map.get("LLM_CHANNELS") or "").strip()
        if not raw_channels:
            return issues

        normalized_names: List[str] = []
        seen_names: Set[str] = set()
        for raw_name in raw_channels.split(","):
            name = raw_name.strip()
            if not name:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_]+", name):
                issues.append(
                    {
                        "key": "LLM_CHANNELS",
                        "code": "invalid_channel_name",
                        "message": f"LLM channel name '{name}' may only contain letters, numbers, and underscores",
                        "severity": "error",
                        "expected": "letters/numbers/underscores",
                        "actual": name,
                    }
                )
                continue

            normalized_upper = name.upper()
            if normalized_upper in seen_names:
                issues.append(
                    {
                        "key": "LLM_CHANNELS",
                        "code": "duplicate_channel_name",
                        "message": f"LLM channel '{name}' is declared more than once",
                        "severity": "error",
                        "expected": "unique channel names",
                        "actual": raw_channels,
                    }
                )
                continue

            seen_names.add(normalized_upper)
            normalized_names.append(name)

        # Strict completeness gating applies only to channels this update
        # actually touches (or a changed channel list); historical incomplete
        # channels must not block saving unrelated settings.
        llm_channels_touched = "LLM_CHANNELS" in updated_keys
        for name in normalized_names:
            prefix = f"LLM_{name.upper()}"
            touched = llm_channels_touched or any(
                updated_key.startswith(f"{prefix}_") for updated_key in updated_keys
            )
            provider, provider_id, provider_is_explicit = (
                SystemConfigService._resolve_connection_provider(effective_map, name)
            )
            if provider_is_explicit and provider is None and touched:
                provider_value = (effective_map.get(f"{prefix}_PROVIDER") or "").strip()
                issues.append(
                    {
                        "key": f"{prefix}_PROVIDER",
                        "code": "invalid_provider",
                        "message": (
                            f"LLM connection '{name}' references an unknown model provider"
                        ),
                        "severity": "error",
                        "expected": "provider id from the model provider catalog",
                        "actual": provider_value,
                    }
                )
            submitted_protocol = (effective_map.get(f"{prefix}_PROTOCOL") or "").strip()
            protocol_value, base_url_value = (
                SystemConfigService._resolve_connection_transport(
                    effective_map,
                    name,
                )
            )
            if (
                touched
                and submitted_protocol
                and provider_is_explicit
                and provider is not None
                and not provider["is_custom"]
                and canonicalize_llm_channel_protocol(submitted_protocol)
                != canonicalize_llm_channel_protocol(str(provider["protocol"]))
            ):
                issues.append(
                    {
                        "key": f"{prefix}_PROTOCOL",
                        "code": "provider_protocol_mismatch",
                        "message": (
                            f"LLM connection '{name}' protocol must match its Provider"
                        ),
                        "severity": "error",
                        "expected": str(provider["protocol"]),
                        "actual": submitted_protocol,
                    }
                )
            api_key_value = (
                (effective_map.get(f"{prefix}_API_KEYS") or "").strip()
                or (effective_map.get(f"{prefix}_API_KEY") or "").strip()
            )
            api_keys_value = (effective_map.get(f"{prefix}_API_KEYS") or "").strip()
            if name.lower() == "anspire" and not api_key_value:
                api_key_value = (effective_map.get("ANSPIRE_API_KEYS") or "").strip()
            models_value = [
                model.strip()
                for model in (effective_map.get(f"{prefix}_MODELS") or "").split(",")
                if model.strip()
            ]
            if name.lower() == "anspire" and not models_value:
                models_value = [
                    (
                        effective_map.get("ANSPIRE_LLM_MODEL")
                        or ANSPIRE_LLM_MODEL_DEFAULT
                    ).strip()
                ]
            enabled_raw = effective_map.get(f"{prefix}_ENABLED")
            if name.lower() == "anspire" and not (enabled_raw or "").strip():
                enabled_raw = effective_map.get("ANSPIRE_LLM_ENABLED")
            enabled = parse_env_bool(enabled_raw, default=True)
            if is_reserved_hermes_name(name):
                if touched:
                    result = parse_hermes_channel(
                        enabled=enabled,
                        protocol=protocol_value or HERMES_DEFAULT_PROTOCOL,
                        base_url=base_url_value or HERMES_DEFAULT_BASE_URL,
                        api_key=(effective_map.get(f"{prefix}_API_KEY") or "").strip(),
                        api_keys_raw=(effective_map.get(f"{prefix}_API_KEYS") or "").strip(),
                        extra_headers_raw=(effective_map.get(f"{prefix}_EXTRA_HEADERS") or "").strip(),
                        models=models_value or [HERMES_DEFAULT_MODEL],
                    )
                    for issue in result.issues:
                        issues.append(
                            {
                                "key": issue.field,
                                "code": issue.code,
                                "message": issue.message,
                                "severity": issue.severity,
                                "expected": "valid reserved Hermes channel",
                                "actual": "",
                            }
                        )
                continue
            validation_provider = provider
            if (
                not provider_is_explicit
                and provider is not None
                and provider.get("is_custom")
            ):
                # Legacy Connections had no Provider identity. Preserve the
                # established model-route inference only when it resolves to a
                # local runtime contract (for example ollama/model); explicit
                # Custom selections still require their own Base URL.
                inferred_protocol = resolve_llm_channel_protocol(
                    protocol_value,
                    base_url=base_url_value,
                    models=models_value or None,
                    channel_name=name,
                )
                from src.llm.provider_catalog import get_provider

                inferred_provider = get_provider(inferred_protocol)
                if inferred_provider is not None and inferred_provider.get("is_local"):
                    validation_provider = inferred_provider
            display_name_key = f"{prefix}_DISPLAY_NAME"
            # Legacy Connection payloads predate DISPLAY_NAME. Preserve their
            # identity label only when the key is absent; an explicit empty
            # value must still reach the authoritative required-field contract.
            display_name = (
                name
                if display_name_key not in effective_map
                else (effective_map.get(display_name_key) or "").strip()
            )
            issues.extend(
                SystemConfigService._validate_llm_channel_definition(
                    channel_name=name,
                    display_name=display_name,
                    provider=validation_provider,
                    provider_id=provider_id,
                    protocol_value=protocol_value,
                    base_url_value=base_url_value,
                    api_key_value=api_key_value,
                    api_keys_value=api_keys_value,
                    model_values=models_value,
                    extra_headers_value=(effective_map.get(f"{prefix}_EXTRA_HEADERS") or "").strip(),
                    enabled=enabled,
                    field_prefix=prefix,
                    require_complete=enabled and touched,
                )
            )

        return issues

    @staticmethod
    def _collect_llm_channel_models_from_map(effective_map: Dict[str, str]) -> List[str]:
        return llm_channel_map.collect_llm_channel_models_from_map(effective_map)

    @staticmethod
    def _collect_hermes_channel_models_from_map(effective_map: Dict[str, str]) -> List[str]:
        return llm_channel_map.collect_hermes_channel_models_from_map(effective_map)

    @staticmethod
    def _collect_non_hermes_channel_models_from_map(effective_map: Dict[str, str]) -> List[str]:
        return llm_channel_map.collect_non_hermes_channel_models_from_map(effective_map)

    @staticmethod
    def _collect_mixed_hermes_routes_from_map(effective_map: Dict[str, str]) -> Set[str]:
        return llm_channel_map.collect_mixed_hermes_routes_from_map(effective_map)

    @staticmethod
    def _matches_route_set(model: str, routes: Set[str]) -> bool:
        return llm_channel_map.matches_route_set(model, routes)

    @staticmethod
    def _matches_exact_route(model: str, routes: Set[str]) -> bool:
        return llm_channel_map.matches_exact_route(model, routes)

    @staticmethod
    def _uses_litellm_yaml(effective_map: Dict[str, str]) -> bool:
        return llm_channel_map.uses_litellm_yaml(effective_map)

    @staticmethod
    def _collect_yaml_models_from_map(effective_map: Dict[str, str]) -> List[str]:
        return llm_channel_map.collect_yaml_models_from_map(effective_map)

    @staticmethod
    def _has_legacy_key_for_provider(provider: str, effective_map: Dict[str, str]) -> bool:
        return llm_channel_map.has_legacy_key_for_provider(provider, effective_map)

    @staticmethod
    def _has_runtime_source_for_model(model: str, effective_map: Dict[str, str]) -> bool:
        return llm_channel_map.has_runtime_source_for_model(model, effective_map)

    @staticmethod
    def _collect_llm_route_references(
        effective_map: Dict[str, str],
        known_routes: Set[str],
    ) -> Dict[str, List[Dict[str, str]]]:
        return ModelAssignmentValidator.collect_llm_route_references(effective_map, known_routes)

    @staticmethod
    def _collect_llm_route_connection_ids(
        effective_map: Dict[str, str],
    ) -> Dict[str, List[str]]:
        return ModelAssignmentValidator.collect_llm_route_connection_ids(effective_map)

    @staticmethod
    def _collect_llm_channel_model_refs_from_map(
        effective_map: Dict[str, str],
    ) -> List[str]:
        return ModelAssignmentValidator.collect_llm_channel_model_refs_from_map(effective_map)

    @staticmethod
    def _collect_model_ref_assignment_issues(
        effective_map: Dict[str, str],
        updated_keys: Set[str],
    ) -> List[Dict[str, Any]]:
        return ModelAssignmentValidator.collect_model_ref_assignment_issues(effective_map, updated_keys)

    @staticmethod
    def _model_removal_issue_key(
        connection_ids: Sequence[str],
        updated_keys: Set[str],
    ) -> str:
        return ModelAssignmentValidator.model_removal_issue_key(connection_ids, updated_keys)

    @staticmethod
    def _collect_removed_model_in_use_issues(
        effective_map: Dict[str, str],
        previous_effective_map: Optional[Dict[str, str]],
        updated_keys: Set[str],
    ) -> List[Dict[str, Any]]:
        return ModelAssignmentValidator.collect_removed_model_in_use_issues(
            effective_map,
            previous_effective_map,
            updated_keys,
        )

    @staticmethod
    def _validate_llm_runtime_selection(
        effective_map: Dict[str, str],
        updated_keys: Optional[Set[str]] = None,
        previous_effective_map: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        return ModelAssignmentValidator.validate_llm_runtime_selection(
            effective_map,
            updated_keys,
            previous_effective_map,
        )

    @staticmethod
    def _unknown_connection_contract_issues(
        *,
        schema: Sequence[Dict[str, Any]],
        values: Dict[str, str],
        field_prefix: str,
        field_keys: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build stable validation issues for unsupported field conditions."""
        fields_by_key = {
            str(field.get("key") or ""): field
            for field in schema
        }
        issues: List[Dict[str, Any]] = []
        for field_key in get_unknown_connection_contract_fields(
            schema,
            values,
            field_keys=field_keys,
        ):
            field = fields_by_key.get(field_key, {})
            env_suffix = str(field.get("env_suffix") or "").strip()
            issue_key = (
                field_key
                if field_prefix == "test_channel"
                else f"{field_prefix}_{env_suffix}" if env_suffix else field_prefix
            )
            issues.append(
                {
                    "key": issue_key,
                    "code": "unknown_contract_condition",
                    "message": (
                        f"LLM channel field '{field_key}' uses an unsupported "
                        "contract condition"
                    ),
                    "severity": "error",
                    "expected": "supported condition operator",
                    "actual": "unknown",
                }
            )
        return issues

    @staticmethod
    def _validate_llm_channel_definition(
        *,
        channel_name: str,
        display_name: str = "",
        provider: Optional[Dict[str, Any]] = None,
        provider_id: str = "",
        protocol_value: str,
        base_url_value: str,
        api_key_value: str,
        api_keys_value: str = "",
        model_values: Sequence[str],
        extra_headers_value: str = "",
        enabled: bool,
        field_prefix: str,
        require_complete: bool,
    ) -> List[Dict[str, Any]]:
        """Validate one normalized LLM channel definition."""
        if require_complete:
            issues, resolved_protocol = SystemConfigService._validate_llm_channel_connection(
                channel_name=channel_name,
                provider=provider,
                provider_id=provider_id,
                protocol_value=protocol_value,
                base_url_value=base_url_value,
                api_key_value=api_key_value,
                api_keys_value=api_keys_value,
                model_values=model_values,
                extra_headers_value=extra_headers_value,
                enabled=enabled,
                field_prefix=field_prefix,
            )
        else:
            issues = []
            resolved_protocol = resolve_llm_channel_protocol(
                protocol_value,
                base_url=base_url_value,
                models=list(model_values) if model_values else None,
                channel_name=channel_name,
            )
        models_key = f"{field_prefix}_MODELS" if field_prefix != "test_channel" else "models"
        contract_values = build_connection_contract_values(
            connection_name=channel_name,
            display_name=display_name,
            provider_id=provider_id,
            provider=provider,
            protocol=resolved_protocol,
            base_url=base_url_value,
            api_key=api_key_value,
            api_keys=api_keys_value,
            models=model_values,
            extra_headers=extra_headers_value,
            enabled=enabled,
        )
        connection_schema = get_connection_field_schema()
        missing_fields = validate_connection_contract_values(
            connection_schema,
            contract_values,
        )
        issues.extend(
            SystemConfigService._unknown_connection_contract_issues(
                schema=connection_schema,
                values=contract_values,
                field_prefix=field_prefix,
                field_keys=(
                    (
                        "connection_name",
                        "display_name",
                        "provider_id",
                        "api_keys",
                        "models",
                        "extra_headers",
                        "enabled",
                    )
                    if require_complete
                    else None
                ),
            )
        )

        if "display_name" in missing_fields:
            display_name_key = (
                f"{field_prefix}_DISPLAY_NAME"
                if field_prefix != "test_channel"
                else "display_name"
            )
            issues.append(
                {
                    "key": display_name_key,
                    "code": "field_required",
                    "message": f"LLM channel '{channel_name}' requires a display name",
                    "severity": "error",
                    "expected": "non-empty value",
                    "actual": "",
                }
            )

        # Disabled drafts may omit fields required only while enabled, but
        # unconditional identity requirements and schema diagnostics still apply.
        if not require_complete:
            return issues

        if "models" in missing_fields:
            issues.append(
                {
                    "key": models_key,
                    "code": "missing_models",
                    "message": f"LLM channel '{channel_name}' requires at least one model",
                    "severity": "error",
                    "expected": "comma-separated model list",
                    "actual": "",
                }
            )
        elif not resolved_protocol:
            unresolved = [model for model in model_values if "/" not in model]
            if unresolved:
                issues.append(
                    {
                        "key": models_key,
                        "code": "missing_protocol",
                        "message": (
                            f"LLM channel '{channel_name}' uses bare model names. "
                            "Set PROTOCOL or add provider/model prefixes."
                        ),
                        "severity": "error",
                        "expected": "protocol or provider/model",
                        "actual": ", ".join(unresolved[:3]),
                    }
                )

        return issues

    @staticmethod
    def _validate_llm_channel_connection(
        *,
        channel_name: str,
        provider: Optional[Dict[str, Any]] = None,
        provider_id: str = "",
        protocol_value: str,
        base_url_value: str,
        api_key_value: str,
        api_keys_value: str = "",
        model_values: Sequence[str] = (),
        extra_headers_value: str = "",
        enabled: bool = True,
        field_prefix: str,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Validate connection-level fields shared by test and discovery flows."""
        issues: List[Dict[str, Any]] = []
        protocol_key = f"{field_prefix}_PROTOCOL" if field_prefix != "test_channel" else "protocol"
        base_url_key = f"{field_prefix}_BASE_URL" if field_prefix != "test_channel" else "base_url"
        api_key_key = f"{field_prefix}_API_KEY" if field_prefix != "test_channel" else "api_key"

        normalized_protocol = canonicalize_llm_channel_protocol(protocol_value)
        if normalized_protocol and normalized_protocol not in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
            issues.append(
                {
                    "key": protocol_key,
                    "code": "invalid_protocol",
                    "message": (
                        f"Unsupported LLM channel protocol '{protocol_value}'. "
                        f"Supported: {', '.join(SUPPORTED_LLM_CHANNEL_PROTOCOLS)}"
                    ),
                    "severity": "error",
                    "expected": ",".join(SUPPORTED_LLM_CHANNEL_PROTOCOLS),
                    "actual": protocol_value,
                }
            )

        if base_url_value and not SystemConfigService._is_valid_llm_base_url(base_url_value):
            issues.append(
                {
                    "key": base_url_key,
                    "code": "invalid_url",
                    "message": "LLM channel base URL must be a valid absolute URL",
                    "severity": "error",
                    "expected": "http(s)://host",
                    "actual": base_url_value,
                }
            )
        elif base_url_value and not SystemConfigService._is_safe_base_url(base_url_value):
            issues.append(
                {
                    "key": base_url_key,
                    "code": "ssrf_blocked",
                    "message": "LLM channel base URL points to a restricted address (cloud metadata services are not allowed)",
                    "severity": "error",
                    "expected": "publicly reachable or local LLM endpoint",
                    "actual": base_url_value,
                }
            )

        resolved_protocol = resolve_llm_channel_protocol(
            protocol_value,
            base_url=base_url_value,
            models=list(model_values) if model_values else None,
            channel_name=channel_name,
        )
        # Parsed segments make comma-only credentials empty before contract
        # evaluation. Requirement decisions themselves stay in the shared schema.
        parsed_api_key = ",".join(
            segment.strip() for segment in api_key_value.split(",") if segment.strip()
        )
        contract_values = build_connection_contract_values(
            connection_name=channel_name,
            display_name=channel_name,
            provider_id=provider_id,
            provider=provider,
            protocol=resolved_protocol,
            base_url=base_url_value,
            api_key=parsed_api_key,
            api_keys=api_keys_value,
            models=model_values,
            extra_headers=extra_headers_value,
            enabled=enabled,
        )
        connection_schema = get_connection_field_schema()
        missing_fields = validate_connection_contract_values(
            connection_schema,
            contract_values,
            field_keys=("protocol", "base_url", "api_key"),
        )
        issues.extend(
            SystemConfigService._unknown_connection_contract_issues(
                schema=connection_schema,
                values=contract_values,
                field_prefix=field_prefix,
                field_keys=("protocol", "base_url", "api_key"),
            )
        )
        if "protocol" in missing_fields:
            issues.append(
                {
                    "key": protocol_key,
                    "code": "missing_protocol",
                    "message": f"LLM channel '{channel_name}' requires a protocol",
                    "severity": "error",
                    "expected": "supported protocol",
                    "actual": "",
                }
            )
        if "base_url" in missing_fields:
            issues.append(
                {
                    "key": base_url_key,
                    "code": "missing_base_url",
                    "message": f"LLM channel '{channel_name}' requires a base URL",
                    "severity": "error",
                    "expected": "http(s)://host/v1",
                    "actual": "",
                }
            )
        if "api_key" in missing_fields:
            issues.append(
                {
                    "key": api_key_key,
                    "code": "missing_api_key",
                    "message": f"LLM channel '{channel_name}' requires an API key",
                    "severity": "error",
                    "expected": "non-empty API key",
                    "actual": api_key_value,
                }
            )
        return issues, resolved_protocol
