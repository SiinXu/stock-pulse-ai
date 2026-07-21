"""LLM channel loading methods for :class:`src.config.Config`."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config_parts.defaults import (
    ANSPIRE_LLM_BASE_URL_DEFAULT,
    ANSPIRE_LLM_MODEL_DEFAULT,
    SUPPORTED_LLM_CHANNEL_PROTOCOLS,
)
from src.config_parts.parsers import (
    canonicalize_llm_channel_protocol,
    channel_allows_empty_api_key,
    normalize_llm_channel_model,
    parse_env_bool,
    resolve_llm_channel_protocol,
)
from src.llm.hermes import (
    HERMES_DEFAULT_BASE_URL,
    HERMES_DEFAULT_MODEL,
    HERMES_DEFAULT_PROTOCOL,
    HermesConfigIssue,
    hermes_model_info,
    is_reserved_hermes_name,
    parse_hermes_channel,
)
from src.llm.provider_catalog_data import get_provider_ids, get_static_provider
from src.utils.sanitize import log_safe_exception


class _ConfigLLMMethods:
    @classmethod
    def _parse_litellm_yaml(cls, config_path: str) -> List[Dict[str, Any]]:
        """Parse a standard LiteLLM config YAML file into Router model_list.

        Supports the ``os.environ/VAR_NAME`` syntax for secret references.
        Returns an empty list on any error (logged, never raises).
        """
        import logging
        _logger = logging.getLogger("src.config")
        try:
            import yaml
        except ImportError:
            _logger.warning("PyYAML not installed; LITELLM_CONFIG ignored. Install with: pip install pyyaml")
            return []

        path = Path(config_path)
        if not path.is_absolute():
            path = Path(__file__).parent.parent.parent / path
        if not path.exists():
            _logger.warning(f"LITELLM_CONFIG file not found: {path}")
            return []

        try:
            with open(path, encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f) or {}
        except Exception as exc:
            # broad-exception: fallback_recorded - Invalid config is logged and ignored.
            log_safe_exception(
                _logger,
                "LiteLLM configuration parsing failed",
                exc,
                error_code="litellm_config_parse_failed",
                level=logging.WARNING,
            )
            return []

        model_list = yaml_config.get('model_list', [])
        if not isinstance(model_list, list):
            _logger.warning("LITELLM_CONFIG: model_list must be a list")
            return []

        # Resolve os.environ/ references in string params
        for entry in model_list:
            params = entry.get('litellm_params', {})
            for key in list(params.keys()):
                val = params.get(key)
                if isinstance(val, str) and val.startswith('os.environ/'):
                    env_name = val.split('/', 1)[1]
                    params[key] = os.getenv(env_name, '')

        _logger.info(f"LITELLM_CONFIG: loaded {len(model_list)} model deployment(s) from {path}")
        return model_list

    @classmethod
    def _parse_llm_channels(cls, channels_str: str) -> List[Dict[str, Any]]:
        """Backward-compatible channel parser returning only valid channels."""
        channels, _issues, _blocks, _blocked_routes = cls._parse_llm_channels_with_issues(channels_str)
        return channels

    @classmethod
    def _parse_llm_channels_with_issues(
        cls,
        channels_str: str,
    ) -> Tuple[List[Dict[str, Any]], List[HermesConfigIssue], bool, List[str]]:
        """Parse LLM_CHANNELS env var and per-channel env vars.

        Format:
            LLM_CHANNELS=aihubmix,deepseek,gemini
            LLM_AIHUBMIX_PROTOCOL=openai
            LLM_AIHUBMIX_BASE_URL=https://aihubmix.com/v1
            LLM_AIHUBMIX_API_KEY=sk-xxx           (or LLM_AIHUBMIX_API_KEYS=k1,k2)
            LLM_AIHUBMIX_MODELS=gpt-5.5,claude-sonnet-4-6
            LLM_AIHUBMIX_ENABLED=true
        """
        import logging
        _logger = logging.getLogger("src.config")

        from src.llm.model_ref import canonicalize_connection_id

        channels: List[Dict[str, Any]] = []
        issues: List[HermesConfigIssue] = []
        blocks_legacy_fallback = False
        blocked_hermes_routes: List[str] = []
        for raw_name in channels_str.split(','):
            ch_name = raw_name.strip()
            if not ch_name:
                continue
            ch_lower = canonicalize_connection_id(ch_name)
            ch_upper = ch_name.upper()

            explicit_provider_id = os.getenv(f'LLM_{ch_upper}_PROVIDER', '').strip().lower()
            provider_id = explicit_provider_id
            provider = None
            if provider_id:
                provider = get_static_provider(provider_id)
            else:
                provider_ids = set(get_provider_ids())
                provider_id = ch_lower if ch_lower in provider_ids and ch_lower != "custom" else "custom"

            base_url = os.getenv(f'LLM_{ch_upper}_BASE_URL', '').strip() or None
            if ch_lower == "anspire" and not base_url:
                base_url = (
                    os.getenv('ANSPIRE_LLM_BASE_URL') or ANSPIRE_LLM_BASE_URL_DEFAULT
                ).strip() or None
            protocol_raw = os.getenv(f'LLM_{ch_upper}_PROTOCOL', '').strip()
            if provider is not None and not provider["is_custom"]:
                protocol_raw = str(provider["protocol"])
                if not base_url:
                    base_url = str(provider["default_base_url"]).strip() or None
            if ch_lower == "anspire" and not protocol_raw:
                protocol_raw = "openai"
            enabled_raw = os.getenv(f'LLM_{ch_upper}_ENABLED')
            if ch_lower == "anspire" and (enabled_raw is None or not enabled_raw.strip()):
                enabled_raw = os.getenv('ANSPIRE_LLM_ENABLED')
            enabled = parse_env_bool(enabled_raw, default=True)

            # API keys: LLM_{NAME}_API_KEYS (multi) > LLM_{NAME}_API_KEY (single)
            api_keys_raw = os.getenv(f'LLM_{ch_upper}_API_KEYS', '')
            api_keys = [k.strip() for k in api_keys_raw.split(',') if k.strip()]
            single_key = os.getenv(f'LLM_{ch_upper}_API_KEY', '').strip()
            if not api_keys:
                if single_key:
                    api_keys = [single_key]
            if not api_keys and ch_lower == "anspire":
                anspire_keys_raw = os.getenv('ANSPIRE_API_KEYS', '')
                api_keys = [k.strip() for k in anspire_keys_raw.split(',') if k.strip()]

            # Models
            models_raw = os.getenv(f'LLM_{ch_upper}_MODELS', '')
            raw_models = [m.strip() for m in models_raw.split(',') if m.strip()]
            if not raw_models and ch_lower == "anspire":
                anspire_model = (
                    os.getenv('ANSPIRE_LLM_MODEL') or ANSPIRE_LLM_MODEL_DEFAULT
                ).strip()
                if anspire_model:
                    raw_models = [anspire_model]

            if is_reserved_hermes_name(ch_name):
                if not raw_models:
                    raw_models = [HERMES_DEFAULT_MODEL]
                result = parse_hermes_channel(
                    enabled=enabled,
                    protocol=protocol_raw or HERMES_DEFAULT_PROTOCOL,
                    base_url=base_url or HERMES_DEFAULT_BASE_URL,
                    api_key=single_key,
                    api_keys_raw=api_keys_raw,
                    extra_headers_raw=os.getenv(f'LLM_{ch_upper}_EXTRA_HEADERS', ''),
                    models=raw_models,
                )
                issues.extend(result.issues)
                blocks_legacy_fallback = blocks_legacy_fallback or result.blocks_legacy_fallback
                for route_name in result.blocked_route_names:
                    if route_name not in blocked_hermes_routes:
                        blocked_hermes_routes.append(route_name)
                if result.channel is None:
                    if not enabled:
                        _logger.info("LLM channel '%s': disabled, skipped", ch_name)
                    else:
                        _logger.warning("LLM channel '%s': invalid reserved Hermes channel, skipped", ch_name)
                    continue
                result.channel["provider_id"] = provider_id
                channels.append(result.channel)
                _logger.info("LLM channel '%s': Hermes preset with %d model(s)", ch_name, len(result.channel["models"]))
                continue

            protocol = resolve_llm_channel_protocol(protocol_raw, base_url=base_url, models=raw_models, channel_name=ch_name)
            models = [normalize_llm_channel_model(m, protocol, base_url) for m in raw_models]

            # Extra headers (JSON string, optional)
            extra_headers_raw = os.getenv(f'LLM_{ch_upper}_EXTRA_HEADERS', '').strip()
            extra_headers = None
            if extra_headers_raw:
                try:
                    extra_headers = json.loads(extra_headers_raw)
                except json.JSONDecodeError:
                    _logger.warning(f"LLM_{ch_upper}_EXTRA_HEADERS: invalid JSON, ignored")

            if not enabled:
                _logger.info(f"LLM channel '{ch_name}': disabled, skipped")
                continue

            if protocol_raw and canonicalize_llm_channel_protocol(protocol_raw) not in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
                _logger.warning(
                    "LLM_%s_PROTOCOL=%s is unsupported; auto-detected protocol=%s",
                    ch_upper,
                    protocol_raw,
                    protocol or "unknown",
                )

            if not api_keys and channel_allows_empty_api_key(protocol, base_url):
                api_keys = [""]

            if not api_keys:
                _logger.warning(f"LLM channel '{ch_name}': no API key configured, skipped")
                continue
            if not models:
                _logger.warning(f"LLM channel '{ch_name}': no models configured, skipped")
                continue

            channels.append({
                'name': ch_name.lower(),
                'provider_id': provider_id,
                'protocol': protocol,
                'enabled': enabled,
                'base_url': base_url,
                'api_keys': api_keys,
                'models': models,
                'extra_headers': extra_headers,
            })
            _logger.info(f"LLM channel '{ch_name}': {len(models)} model(s), {len(api_keys)} key(s)")

        return channels, issues, blocks_legacy_fallback, blocked_hermes_routes

    @classmethod
    def _channels_to_model_list(cls, channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert parsed LLM channels to LiteLLM Router model_list format.

        Mapping follows:
        - LiteLLM providers: https://docs.litellm.ai/docs/providers
        - LiteLLM model_list semantics: https://docs.litellm.ai/docs/proxy/configs#the-model_list-key
        """
        from src.llm.model_ref import canonicalize_connection_id, encode_model_ref

        model_list: List[Dict[str, Any]] = []
        model_ref_entries: List[Dict[str, Any]] = []
        route_owner_ids: Dict[str, set[str]] = {}
        for ch in channels:
            connection_id = canonicalize_connection_id(ch.get("name"))
            if not connection_id:
                continue
            for model_name in ch.get("models") or []:
                route_owner_ids.setdefault(str(model_name), set()).add(connection_id)

        for ch in channels:
            hermes_refs = {
                str(ref.get("route_model") or ""): ref
                for ref in (ch.get("model_refs") or [])
                if isinstance(ref, dict)
            }
            for model_name in ch['models']:
                for api_key in ch['api_keys']:
                    model_ref = hermes_refs.get(str(model_name))
                    wire_model = str((model_ref or {}).get("wire_model") or model_name)
                    litellm_params: Dict[str, Any] = {
                        'model': wire_model,
                    }
                    if api_key:
                        litellm_params['api_key'] = api_key
                    if ch['base_url']:
                        litellm_params['api_base'] = ch['base_url']
                    # Preserve only headers explicitly configured for this connection.
                    headers = dict(ch.get('extra_headers') or {})
                    if headers:
                        litellm_params['extra_headers'] = headers

                    entry: Dict[str, Any] = {
                        'model_name': model_name,
                        'litellm_params': litellm_params,
                    }
                    if ch.get("is_hermes") or is_reserved_hermes_name(str(ch.get("name") or "")):
                        entry["model_info"] = hermes_model_info(
                            str((model_ref or {}).get("display_model") or "")
                        )
                    if len(route_owner_ids.get(str(model_name), set())) == 1:
                        model_list.append(entry)

                    connection_id = canonicalize_connection_id(ch.get("name"))
                    if connection_id:
                        reference_value = encode_model_ref(connection_id, model_name)
                        reference_info = dict(entry.get("model_info") or {})
                        reference_info.update({
                            "dsa_model_ref": reference_value,
                            "dsa_connection_id": connection_id,
                            "dsa_runtime_route": model_name,
                        })
                        model_ref_entries.append({
                            "model_name": reference_value,
                            "litellm_params": dict(litellm_params),
                            "model_info": reference_info,
                        })

        # Keep legacy aliases first for compatibility. The ModelRef aliases are
        # unique per Connection and let new assignments select exact credentials.
        return model_list + model_ref_entries

    @classmethod
    def _legacy_keys_to_model_list(
        cls,
        gemini_keys: List[str],
        anthropic_keys: List[str],
        openai_keys: List[str],
        openai_base_url: Optional[str],
        deepseek_keys: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build Router model_list from legacy per-provider keys (backward compat).

        Returns a model_list where each provider's keys are expanded into
        deployments, keyed by placeholder model_name tokens.  The analyzer
        resolves actual model_names at call time from LITELLM_MODEL /
        LITELLM_FALLBACK_MODELS.

        Compatibility note:
        - LiteLLM OpenAI-compatible 约定: https://docs.litellm.ai/docs/providers/openai_compatible
        - OpenAI 请求与鉴权约定: https://platform.openai.com/docs/api-reference/making-requests
          / https://platform.openai.com/docs/api-reference/authentication
        """
        model_list: List[Dict[str, Any]] = []

        # Gemini keys
        for k in gemini_keys:
            if k and len(k) >= 8:
                model_list.append({
                    'model_name': '__legacy_gemini__',
                    'litellm_params': {'model': '__legacy_gemini__', 'api_key': k},
                })

        # Anthropic keys
        for k in anthropic_keys:
            if k and len(k) >= 8:
                model_list.append({
                    'model_name': '__legacy_anthropic__',
                    'litellm_params': {'model': '__legacy_anthropic__', 'api_key': k},
                })

        # OpenAI-compatible keys
        for k in openai_keys:
            if k and len(k) >= 8:
                params: Dict[str, Any] = {'model': '__legacy_openai__', 'api_key': k}
                if openai_base_url:
                    params['api_base'] = openai_base_url
                model_list.append({
                    'model_name': '__legacy_openai__',
                    'litellm_params': params,
                })

        # DeepSeek keys (native litellm provider — auto-resolves api_base)
        for k in (deepseek_keys or []):
            if k and len(k) >= 8:
                model_list.append({
                    'model_name': '__legacy_deepseek__',
                    'litellm_params': {
                        'model': '__legacy_deepseek__',
                        'api_key': k,
                    },
                })

        return model_list
