"""Compatibility guards for ``src.services.system_config_service``."""

import hashlib
import inspect
import json
import subprocess
import sys
from typing import get_type_hints

import src.services.system_config_service as service_module


EXPECTED_MODULE_NAMES = ('annotations',
 'io',
 'logging',
 'json',
 'os',
 're',
 'shutil',
 'time',
 'dataclass',
 'field',
 'Path',
 'Any',
 'Callable',
 'Dict',
 'List',
 'Optional',
 'Sequence',
 'Set',
 'Tuple',
 'urlparse',
 'urlunparse',
 'requests',
 'ANSPIRE_LLM_BASE_URL_DEFAULT',
 'ANSPIRE_LLM_MODEL_DEFAULT',
 'SUPPORTED_LLM_CHANNEL_PROTOCOLS',
 'Config',
 '_get_litellm_provider',
 '_uses_direct_env_provider',
 'canonicalize_llm_channel_protocol',
 'channel_allows_empty_api_key',
 'get_runtime_config',
 'normalize_agent_litellm_model',
 'normalize_news_strategy_profile',
 'normalize_llm_channel_model',
 'parse_env_bool',
 'parse_env_int',
 'resolve_news_window_days',
 'resolve_llm_channel_protocol',
 'setup_env',
 'HERMES_DEFAULT_BASE_URL',
 'HERMES_DEFAULT_MODEL',
 'HERMES_DEFAULT_PROTOCOL',
 'build_hermes_redaction_values',
 'canonicalize_hermes_model_ref',
 'canonicalize_hermes_base_url',
 'is_masked_secret_placeholder',
 'is_reserved_hermes_name',
 'open_hermes_no_proxy_client',
 'parse_hermes_channel',
 'ConfigManager',
 'ConfigVersionMismatchError',
 'LLM_CHANNEL_FIELD_KEY_RE',
 'build_schema_response',
 'evaluate_config_conditions',
 'get_category_definitions',
 'get_contract_field_definitions',
 'get_field_definition',
 'get_registered_field_keys',
 'call_litellm_with_param_recovery',
 'AUTO_AGENT_BACKEND_ID',
 'CODEX_CLI_BACKEND_ID',
 'GENERATION_ONLY_BACKEND_IDS',
 'LOCAL_CLI_GENERATION_BACKEND_IDS',
 'LITELLM_BACKEND_ID',
 'normalize_backend_id',
 'apply_litellm_generation_params',
 'resolve_local_cli_preset',
 'strip_leading_think_wrapper',
 'build_connection_contract_values',
 'get_connection_field_schema',
 'get_unknown_connection_contract_fields',
 'validate_connection_contract_values',
 'FEISHU_APP_BOT_ENV_GROUP',
 'FEISHU_WEBHOOK_ENV_GROUP',
 'is_feishu_app_bot_env_configured',
 'is_feishu_static_env_configured',
 'validate_notification_timezone',
 'resolve_gotify_message_endpoint',
 'resolve_ntfy_endpoint',
 'split_stock_list',
 'GenerationBackendStatusService',
 'ConfigConflictService',
 'EffectiveConfigResolver',
 'ModelAssignmentValidator',
 'ConfigConflictError',
 'llm_channel_map',
 'log_safe_exception',
 'sanitize_diagnostic_text',
 'sanitize_exception_chain',
 'logger',
 'ConfigValidationError',
 'ConfigImportError',
 'known_llm_provider_channel_names',
 '_LLMDiagnostic',
 'SystemConfigService')
EXPECTED_PUBLIC_NAMES = ('annotations',
 'io',
 'logging',
 'json',
 'os',
 're',
 'shutil',
 'time',
 'dataclass',
 'field',
 'Path',
 'Any',
 'Callable',
 'Dict',
 'List',
 'Optional',
 'Sequence',
 'Set',
 'Tuple',
 'urlparse',
 'urlunparse',
 'requests',
 'ANSPIRE_LLM_BASE_URL_DEFAULT',
 'ANSPIRE_LLM_MODEL_DEFAULT',
 'SUPPORTED_LLM_CHANNEL_PROTOCOLS',
 'Config',
 'canonicalize_llm_channel_protocol',
 'channel_allows_empty_api_key',
 'get_runtime_config',
 'normalize_agent_litellm_model',
 'normalize_news_strategy_profile',
 'normalize_llm_channel_model',
 'parse_env_bool',
 'parse_env_int',
 'resolve_news_window_days',
 'resolve_llm_channel_protocol',
 'setup_env',
 'HERMES_DEFAULT_BASE_URL',
 'HERMES_DEFAULT_MODEL',
 'HERMES_DEFAULT_PROTOCOL',
 'build_hermes_redaction_values',
 'canonicalize_hermes_model_ref',
 'canonicalize_hermes_base_url',
 'is_masked_secret_placeholder',
 'is_reserved_hermes_name',
 'open_hermes_no_proxy_client',
 'parse_hermes_channel',
 'ConfigManager',
 'ConfigVersionMismatchError',
 'LLM_CHANNEL_FIELD_KEY_RE',
 'build_schema_response',
 'evaluate_config_conditions',
 'get_category_definitions',
 'get_contract_field_definitions',
 'get_field_definition',
 'get_registered_field_keys',
 'call_litellm_with_param_recovery',
 'AUTO_AGENT_BACKEND_ID',
 'CODEX_CLI_BACKEND_ID',
 'GENERATION_ONLY_BACKEND_IDS',
 'LOCAL_CLI_GENERATION_BACKEND_IDS',
 'LITELLM_BACKEND_ID',
 'normalize_backend_id',
 'apply_litellm_generation_params',
 'resolve_local_cli_preset',
 'strip_leading_think_wrapper',
 'build_connection_contract_values',
 'get_connection_field_schema',
 'get_unknown_connection_contract_fields',
 'validate_connection_contract_values',
 'FEISHU_APP_BOT_ENV_GROUP',
 'FEISHU_WEBHOOK_ENV_GROUP',
 'is_feishu_app_bot_env_configured',
 'is_feishu_static_env_configured',
 'validate_notification_timezone',
 'resolve_gotify_message_endpoint',
 'resolve_ntfy_endpoint',
 'split_stock_list',
 'GenerationBackendStatusService',
 'ConfigConflictService',
 'EffectiveConfigResolver',
 'ModelAssignmentValidator',
 'ConfigConflictError',
 'llm_channel_map',
 'log_safe_exception',
 'sanitize_diagnostic_text',
 'sanitize_exception_chain',
 'logger',
 'ConfigValidationError',
 'ConfigImportError',
 'known_llm_provider_channel_names',
 'SystemConfigService')
EXPECTED_MODULE_ANNOTATIONS = {}
EXPECTED_CLASS_SURFACE = ('__annotations__',
 '_ENV_KEY_PATTERN',
 '_GENERATION_BACKEND_STATUS_EXACT_KEYS',
 '_GENERATION_BACKEND_STATUS_LLM_CHANNEL_RE',
 '_LLM_CAPABILITY_ORDER',
 '_LLM_STREAM_CHUNK_LIMIT',
 '_LLM_EMPTY_API_KEY_ADAPTER_SENTINEL',
 '_WEB_SETTINGS_LLM_CHANNEL_SUPPORT_KEY_RE',
 '_CONNECTION_SECRET_SCOPE_SUFFIXES',
 '_LLM_CAPABILITY_PROBE_IMAGE',
 '_NOTIFICATION_TEST_CHANNELS',
 '_NOTIFICATION_TEST_KEY_MAP',
 '_NOTIFICATION_REQUIRED_KEY_GROUPS',
 '_NOTIFICATION_TEST_TARGET_KEYS',
 '__init__',
 'get_schema',
 '_reload_runtime_singletons',
 '_build_display_config_map',
 '_build_runtime_display_config_map',
 'get_config',
 '_detect_configured_notification_channels',
 'validate',
 'test_notification_channel',
 'get_setup_status',
 'get_llm_config_mode_status',
 'get_available_models',
 '_resolve_connection_provider',
 '_resolve_connection_transport',
 '_resolve_request_provider',
 '_LEGACY_LLM_PROVIDER_KEYS',
 '_resolve_llm_config_mode_status',
 '_LEGACY_CHANNEL_SPECS',
 '_build_legacy_channels_migration',
 'preview_legacy_channels_migration',
 'apply_legacy_channels_migration',
 'get_generation_backend_status',
 'preview_generation_backend_status',
 'test_generation_backend',
 'export_env',
 'export_desktop_env',
 'import_env',
 'import_desktop_env',
 '_resolve_hermes_saved_secret',
 '_validate_hermes_submitted_secret',
 'discover_llm_channel_models',
 'test_llm_channel',
 '_normalize_llm_capability_checks',
 '_build_skipped_capability_results',
 '_run_hermes_capability_checks',
 '_run_llm_capability_checks',
 '_run_json_capability_check',
 '_run_tools_capability_check',
 '_run_stream_capability_check',
 '_run_vision_capability_check',
 '_build_llm_capability_completion_kwargs',
 '_build_llm_capability_result',
 '_build_llm_capability_result_from_diagnostic',
 '_extract_llm_tool_call_names',
 '_extract_llm_stream_chunk_content',
 '_classify_llm_capability_exception',
 'update',
 '_build_explainability_warnings',
 '_build_runtime_model_cleanup_warnings',
 '_build_hermes_unsupported_key_cleanup_warnings',
 'apply_simple_updates',
 '_parse_imported_env_content',
 '_collect_issues',
 '_connection_secret_scope_identity',
 '_collect_connection_secret_scope_issues',
 '_generation_backend_uses_litellm',
 '_validate_field_contracts',
 '_is_generation_backend_status_key',
 '_filter_generation_backend_items',
 '_collect_generation_backend_issues',
 '_validate_generation_backend_litellm_runtime_source',
 '_collect_generation_backend_issues_from_map',
 '_validate_value',
 '_normalize_value_for_storage',
 '_validate_numeric_range',
 '_is_valid_url',
 '_canonical_ipv4_numeric_host',
 '_is_noncanonical_ipv4_numeric_host',
 '_normalize_hostname_for_security',
 '_is_valid_llm_base_url',
 '_split_csv',
 '_build_notification_test_effective_map',
 '_get_missing_notification_test_keys',
 '_get_invalid_notification_test_config_message',
 '_build_notification_config',
 '_parse_notification_test_value',
 '_dispatch_notification_test',
 '_build_notification_test_content',
 '_resolve_notification_test_target',
 '_build_notification_test_result',
 '_sanitize_notification_attempt',
 '_sanitize_notification_text',
 '_mask_notification_target',
 '_classify_notification_exception',
 '_setup_check',
 '_is_setup_relevant_env_key',
 '_build_setup_effective_config_map',
 '_build_generation_backend_base_map',
 '_build_generation_backend_effective_map',
 '_has_any_config_value',
 '_has_valid_ntfy_endpoint',
 '_has_valid_gotify_config',
 '_anspire_legacy_llm_enabled',
 '_provider_has_setup_credentials',
 '_has_setup_runtime_source_for_model',
 '_collect_setup_channel_models',
 '_infer_setup_legacy_primary_model',
 '_resolve_setup_primary_model',
 '_build_setup_primary_llm_check',
 '_build_setup_agent_llm_check',
 '_build_setup_stock_list_check',
 '_build_setup_notification_check',
 '_build_setup_storage_check',
 '_is_safe_base_url',
 '_build_llm_models_url',
 '_get_runtime_llm_temperature',
 '_build_llm_channel_result',
 '_merge_llm_diagnostic_details',
 '_build_redaction_values',
 '_comma_flexible_secret_pattern',
 '_sanitize_llm_error_text',
 '_sanitize_llm_details',
 '_sanitize_llm_value',
 '_classify_llm_http_error',
 '_has_model_not_found_signal',
 '_has_model_access_denied_signal',
 '_has_request_blocked_signal',
 '_has_transport_blocked_signal',
 '_has_provider_prefix_mismatch_signal',
 '_classify_llm_exception',
 '_extract_llm_completion_content',
 '_extract_llm_discovery_error',
 '_extract_discovered_llm_models',
 '_validate_cross_field',
 '_validate_llm_channel_map',
 '_collect_llm_channel_models_from_map',
 '_collect_hermes_channel_models_from_map',
 '_collect_non_hermes_channel_models_from_map',
 '_collect_mixed_hermes_routes_from_map',
 '_matches_route_set',
 '_matches_exact_route',
 '_uses_litellm_yaml',
 '_collect_yaml_models_from_map',
 '_has_legacy_key_for_provider',
 '_has_runtime_source_for_model',
 '_collect_llm_route_references',
 '_collect_llm_route_connection_ids',
 '_collect_llm_channel_model_refs_from_map',
 '_collect_model_ref_assignment_issues',
 '_model_removal_issue_key',
 '_collect_removed_model_in_use_issues',
 '_validate_llm_runtime_selection',
 '_unknown_connection_contract_issues',
 '_validate_llm_channel_definition',
 '_validate_llm_channel_connection')
EXPECTED_CLASS_ANNOTATIONS = {'_LLM_CAPABILITY_ORDER': 'Tuple[str, ...]',
 '_CONNECTION_SECRET_SCOPE_SUFFIXES': 'Tuple[str, ...]',
 '_NOTIFICATION_TEST_CHANNELS': 'Tuple[str, ...]',
 '_NOTIFICATION_TEST_KEY_MAP': 'Dict[str, Tuple[str, str]]',
 '_NOTIFICATION_REQUIRED_KEY_GROUPS': 'Dict[str, Tuple[Tuple[str, ...], ...]]',
 '_NOTIFICATION_TEST_TARGET_KEYS': 'Dict[str, Tuple[str, ...]]'}
EXPECTED_CLASS_FIRSTLINENO = 149
EXPECTED_CLASS_STATIC_ATTRIBUTES = (
    "_conflict",
    "_manager",
    "_runtime_config_provider",
    "_runtime_scheduler",
)
EXPECTED_METHOD_METADATA_SHA256 = 'ed19ece76229f722b259bd9c887de114ab1ac857319ca9c45a77a6c5e69941cf'


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if inspect.isfunction(descriptor):
        return descriptor
    return None


def _iter_code_objects(code):
    yield code
    code_type = type(code)
    for constant in code.co_consts:
        if isinstance(constant, code_type):
            yield from _iter_code_objects(constant)


def test_system_config_service_module_surface_is_stable():
    assert tuple(
        name for name in vars(service_module) if not name.startswith("__")
    ) == EXPECTED_MODULE_NAMES
    assert tuple(
        name for name in vars(service_module) if not name.startswith("_")
    ) == EXPECTED_PUBLIC_NAMES
    assert service_module.__annotations__ == EXPECTED_MODULE_ANNOTATIONS


def test_system_config_service_class_surface_and_metadata_are_stable():
    service = service_module.SystemConfigService
    metadata = {
        "__module__",
        "__doc__",
        "__dict__",
        "__weakref__",
        "__firstlineno__",
        "__static_attributes__",
    }

    assert service.__module__ == "src.services.system_config_service"
    assert service.__mro__ == (service, object)
    assert tuple(name for name in vars(service) if name not in metadata) == EXPECTED_CLASS_SURFACE
    assert service.__annotations__ == EXPECTED_CLASS_ANNOTATIONS
    if hasattr(service, "__firstlineno__"):
        assert service.__firstlineno__ == EXPECTED_CLASS_FIRSTLINENO
    if hasattr(service, "__static_attributes__"):
        assert service.__static_attributes__ == EXPECTED_CLASS_STATIC_ATTRIBUTES

    method_metadata = {}
    for name, descriptor in vars(service).items():
        function = _descriptor_function(descriptor)
        if function is None:
            continue
        assert function.__module__ == "src.services.system_config_service"
        assert function.__qualname__ == f"SystemConfigService.{name}"
        assert function.__globals__ is service_module.__dict__
        if hasattr(function.__code__, "co_qualname"):
            code_qualnames = tuple(
                code.co_qualname for code in _iter_code_objects(function.__code__)
            )
            assert code_qualnames[0] == function.__qualname__
            assert all(
                code_qualname == function.__qualname__
                or code_qualname.startswith(f"{function.__qualname__}.")
                for code_qualname in code_qualnames
            )
        get_type_hints(function)
        method_metadata[name] = {
            "kind": type(descriptor).__name__,
            "module": function.__module__,
            "qualname": function.__qualname__,
            "signature": str(inspect.signature(function)),
            "facade_globals": function.__globals__ is service_module.__dict__,
        }

    payload = json.dumps(
        method_metadata,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_METHOD_METADATA_SHA256


def test_system_config_service_auth_guard_remains_facade_bound():
    service = service_module.SystemConfigService
    collect_issues = inspect.getattr_static(service, "_collect_issues")

    assert service._ENV_KEY_PATTERN.pattern == r"^[A-Za-z_][A-Za-z0-9_]*$"
    assert "invalid_key" in collect_issues.__code__.co_consts
    assert "auth_settings_endpoint_required" in collect_issues.__code__.co_consts
    assert collect_issues.__globals__ is service_module.__dict__


def test_system_config_service_reload_recreates_facade_definitions():
    script = r"""
import importlib
import inspect
import src.services.system_config_service as module
import src.services.system_config_service_parts.core as core_part

old_service = module.SystemConfigService
old_error = module.ConfigValidationError
old_diagnostic = module._LLMDiagnostic
old_method = inspect.getattr_static(old_service, "_collect_issues")
expected_legacy_specs = old_service._LEGACY_CHANNEL_SPECS

core_part._SystemConfigCoreMethods._LEGACY_CHANNEL_SPECS = ()
reloaded = importlib.reload(module)

assert reloaded.SystemConfigService is not old_service
assert reloaded.ConfigValidationError is not old_error
assert reloaded._LLMDiagnostic is not old_diagnostic
assert inspect.getattr_static(reloaded.SystemConfigService, "_collect_issues") is not old_method
assert reloaded.SystemConfigService._LEGACY_CHANNEL_SPECS == expected_legacy_specs
"""
    subprocess.run([sys.executable, "-c", script], check=True)
