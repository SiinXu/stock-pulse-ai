"""Compatibility guards for the public ``src.config`` facade."""

import inspect
import subprocess
import sys
from typing import get_type_hints
from unittest.mock import patch

import src.config as config_module
from src.config import Config


EXPECTED_PUBLIC_EXPORTS = {
    "AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE",
    "AGENT_CONTEXT_COMPRESSION_PROFILES",
    "AGENT_MAX_STEPS_DEFAULT",
    "ANSPIRE_LLM_BASE_URL_DEFAULT",
    "ANSPIRE_LLM_MODEL_DEFAULT",
    "AUTO_AGENT_BACKEND_ID",
    "AgentContextCompressionPreset",
    "Any",
    "Config",
    "ConfigIssue",
    "DEFAULT_ALPHASIFT_INSTALL_SPEC",
    "DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY",
    "DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY",
    "DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES",
    "DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS",
    "Dict",
    "FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT",
    "GENERATION_ONLY_BACKEND_IDS",
    "HERMES_DEFAULT_BASE_URL",
    "HERMES_DEFAULT_MODEL",
    "HERMES_DEFAULT_PROTOCOL",
    "HermesConfigIssue",
    "LITELLM_BACKEND_ID",
    "LLM_EMPTY_API_KEY_HOSTNAMES",
    "LOCAL_CLI_GENERATION_BACKEND_IDS",
    "List",
    "Literal",
    "MAX_GENERATION_BACKEND_MAX_CONCURRENCY",
    "MAX_LOCAL_CLI_BACKEND_MAX_CONCURRENCY",
    "MAX_LOCAL_CLI_OUTPUT_BYTES",
    "MAX_LOCAL_CLI_TIMEOUT_SECONDS",
    "NEWS_STRATEGY_WINDOWS",
    "NOTIFICATION_SEVERITIES",
    "OPENCODE_CLI_BACKEND_ID",
    "Optional",
    "PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT",
    "PROMPT_CACHE_DIAGNOSTICS_LEVELS",
    "Path",
    "SUPPORTED_AGENT_GENERATION_BACKENDS",
    "SUPPORTED_AGENT_UI_BACKENDS",
    "SUPPORTED_GENERATION_BACKENDS",
    "SUPPORTED_LLM_CHANNEL_PROTOCOLS",
    "TICKFLOW_KLINE_ADJUST_VALUES",
    "Tuple",
    "canonicalize_llm_channel_protocol",
    "channel_allows_empty_api_key",
    "dataclass",
    "dotenv_values",
    "extra_litellm_params",
    "field",
    "get_agent_context_compression_preset",
    "get_api_keys_for_model",
    "get_config",
    "get_configured_llm_models",
    "get_effective_agent_models_to_try",
    "get_effective_agent_primary_model",
    "get_fixed_litellm_temperature",
    "get_provider_ids",
    "get_static_provider",
    "hermes_model_info",
    "is_feishu_app_bot_configured",
    "is_feishu_static_configured",
    "is_reserved_hermes_name",
    "is_supported_notification_severity",
    "is_supported_report_language_value",
    "json",
    "llm_generation_params",
    "load_dotenv",
    "log_safe_exception",
    "logger",
    "logging",
    "normalize_agent_context_compression_profile",
    "normalize_agent_litellm_model",
    "normalize_litellm_temperature",
    "normalize_llm_channel_model",
    "normalize_news_strategy_profile",
    "normalize_report_language",
    "normalize_schedule_times",
    "normalize_tickflow_kline_adjust",
    "os",
    "parse_agent_context_compression_int",
    "parse_env_bool",
    "parse_env_float",
    "parse_env_int",
    "parse_hermes_channel",
    "parse_notification_quiet_hours",
    "parse_notification_route_channels",
    "parse_prompt_cache_diagnostics_level",
    "re",
    "resolve_litellm_thinking_enabled",
    "resolve_litellm_wire_model",
    "resolve_llm_channel_protocol",
    "resolve_news_window_days",
    "resolve_unified_llm_temperature",
    "route_deployment_origins",
    "route_has_hermes",
    "route_identity_candidates",
    "setup_env",
    "split_stock_list",
    "unescape_compose_sensitive_env_value",
    "unquote",
    "urlparse",
    "validate_notification_timezone",
}


def test_config_public_export_surface_is_stable():
    public_exports = {name for name in dir(config_module) if not name.startswith("_")}

    assert public_exports == EXPECTED_PUBLIC_EXPORTS


def test_config_class_identity_and_method_ownership_are_stable():
    assert Config.__module__ == "src.config"
    assert Config.__mro__ == (Config, object)

    for method_name in (
        "_load_from_env",
        "_parse_litellm_yaml",
        "refresh_stock_list",
        "validate_structured",
        "get_db_url",
    ):
        method = getattr(Config, method_name)
        assert method.__module__ == "src.config"
        assert method.__qualname__ == f"Config.{method_name}"


def test_moved_callables_resolve_types_and_globals_through_facade():
    assert get_type_hints(config_module.get_effective_agent_primary_model)["config"] is Config
    assert get_type_hints(config_module.get_effective_agent_models_to_try)["config"] is Config
    assert get_type_hints(Config._load_from_env)["return"] is Config
    assert config_module.parse_env_bool.__globals__ is config_module.__dict__
    assert Config.__init__.__globals__ is config_module.__dict__
    assert Config.__eq__.__globals__ is config_module.__dict__
    assert Config._parse_llm_channels_with_issues.__globals__ is config_module.__dict__


def test_config_method_observes_facade_dependency_patches():
    env = {
        "LLM_OPENAI_API_KEY": "test-key-12345678",
        "LLM_OPENAI_MODELS": "gpt-test",
        "LLM_OPENAI_PROTOCOL": "openai",
        "LLM_OPENAI_BASE_URL": "https://example.invalid/v1",
    }
    with patch.dict(config_module.os.environ, env, clear=True):
        with patch.object(
            config_module,
            "get_provider_ids",
            return_value=(),
        ) as get_provider_ids:
            channels, issues, blocks_legacy, blocked_routes = (
                Config._parse_llm_channels_with_issues("openai")
            )

    get_provider_ids.assert_called_once_with()
    assert channels[0]["provider_id"] == "custom"
    assert issues == []
    assert blocks_legacy is False
    assert blocked_routes == []


def test_exported_dataclass_method_metadata_is_stable():
    for value in (config_module.ConfigIssue, config_module.AgentContextCompressionPreset):
        assert value.__module__ == "src.config"
        for method_name in ("__init__", "__repr__", "__eq__"):
            assert getattr(value, method_name).__module__ == "src.config"

    facade_owned_methods = {
        config_module.ConfigIssue: ("__init__", "__eq__", "__str__"),
        config_module.AgentContextCompressionPreset: (
            "__init__",
            "__eq__",
            "__hash__",
            "__setattr__",
            "__delattr__",
        ),
    }
    for value, method_names in facade_owned_methods.items():
        for method_name in method_names:
            assert getattr(value, method_name).__globals__ is config_module.__dict__

    for value in (
        Config,
        config_module.ConfigIssue,
        config_module.AgentContextCompressionPreset,
    ):
        repr_function = inspect.unwrap(value.__repr__)
        assert repr_function.__module__ == "src.config"
        assert repr_function.__globals__ is config_module.__dict__


def test_config_default_factory_metadata_is_stable():
    schedule_factory = Config.__dataclass_fields__["schedule_times"].default_factory

    assert schedule_factory.__module__ == "src.config"
    assert schedule_factory.__qualname__ == "Config.<lambda>"
    assert schedule_factory.__globals__ is config_module.__dict__
    assert schedule_factory in tuple(
        cell.cell_contents for cell in Config.__init__.__closure__ or ()
    )
    assert schedule_factory() == ["18:00"]


def test_config_reload_recreates_public_definitions_and_singleton():
    script = """
import importlib
import src.config as config

old_config = config.Config
old_issue = config.ConfigIssue
old_preset = config.AgentContextCompressionPreset
old_parser = config.parse_env_bool
config.Config._instance = config.Config()

reloaded = importlib.reload(config)
assert reloaded.Config is not old_config
assert reloaded.ConfigIssue is not old_issue
assert reloaded.AgentContextCompressionPreset is not old_preset
assert reloaded.parse_env_bool is not old_parser
assert reloaded.Config._instance is None
"""
    subprocess.run([sys.executable, "-c", script], check=True)
