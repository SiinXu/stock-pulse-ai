"""Environment loading methods for :class:`src.config.Config`."""

import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from dotenv import dotenv_values

from src.config_parts.defaults import (
    AGENT_MAX_STEPS_DEFAULT,
    ANSPIRE_LLM_BASE_URL_DEFAULT,
    ANSPIRE_LLM_MODEL_DEFAULT,
    DEFAULT_ALPHASIFT_INSTALL_SPEC,
    FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
    KRONOS_MODEL_SIZE_DEFAULT as _KRONOS_MODEL_SIZE_DEFAULT,
    PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT,
    logger,
    normalize_tickflow_kline_adjust,
    parse_prompt_cache_diagnostics_level,
)
from src.config_parts.parsers import (
    get_agent_context_compression_preset,
    get_configured_llm_models,
    normalize_agent_context_compression_profile,
    normalize_agent_litellm_model,
    normalize_news_strategy_profile,
    parse_agent_context_compression_int,
    parse_env_bool,
    parse_env_float,
    parse_env_int,
    resolve_news_window_days,
    resolve_unified_llm_temperature,
)
from src.core.config_manager import unescape_compose_sensitive_env_value
from src.llm.backend_registry import AUTO_AGENT_BACKEND_ID, LITELLM_BACKEND_ID
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
from src.notification_routing import parse_notification_route_channels
from src.report_language import (
    is_supported_report_language_value,
    normalize_report_language,
)
from src.scheduler import normalize_schedule_times
from src.services.stock_list_parser import split_stock_list
from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from src.config_parts.model import Config


def setup_env() -> None:
    from src import config as config_module

    config_module.setup_env()


class _ConfigLoadingMethods:
    @classmethod
    def _load_from_env(cls) -> 'Config':
        """
        从 .env 文件加载配置
\x20\x20\x20\x20\x20\x20\x20\x20
        加载优先级：
        1. 大多数配置保持系统环境变量优先
        2. WebUI 可写的运行期关键键优先复用持久化 `.env`，但保留启动时显式进程环境变量的 override
        3. 代码中的默认值
        """
        cls._capture_bootstrap_runtime_env_overrides()
        preexisting_report_language = os.environ.get("REPORT_LANGUAGE")

        # Ensure environment variables have been loaded
        setup_env()

        # Smart Agent Configuration (Critical Fix)
        # If a proxy is configured, Automatically set NO_PROXY To exclude domestic data sources, Avoid failed market data acquisition
        http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
        if http_proxy:
            # Domestic financial data source domain list
            domestic_domains = [
                'eastmoney.com',   # Eastmoney (efinance/AkShare)
                'sina.com.cn',     # Sina Finance (Akshare)
                '163.com',         # NetEase Finance (Akshare)
                'tushare.pro',     # Tushare
                'baostock.com',    # Baostock
                'sse.com.cn',      # Shanghai Stock Exchange
                'szse.cn',         # Shenzhen Stock Exchange
                'csindex.com.cn',  # Shanghai Composite Index
                'cninfo.com.cn',   # JiuDaoXinZhiYun
                'localhost',
                '127.0.0.1'
            ]

            # Get existing no_proxy
            current_no_proxy = os.getenv('NO_PROXY') or os.getenv('no_proxy') or ''
            existing_domains = current_no_proxy.split(',') if current_no_proxy else []

            # Merge and deduplicate
            final_domains = list(set(existing_domains + domestic_domains))
            final_no_proxy = ','.join(filter(None, final_domains))

            # Set environment variables (requests/urllib3/aiohttp will comply with this setting)
            os.environ['NO_PROXY'] = final_no_proxy
            os.environ['no_proxy'] = final_no_proxy

            # Ensure HTTP_PROXY is also correctly set (to prevent only defined in .env but not exported)
            os.environ['HTTP_PROXY'] = http_proxy
            os.environ['http_proxy'] = http_proxy

            # HTTPS_PROXY similarly
            https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
            if https_proxy:
                os.environ['HTTPS_PROXY'] = https_proxy
                os.environ['https_proxy'] = https_proxy


        # Parse watchlist stocks (comma-separated, convert to uppercase - Issue #355)
        stock_list_str = cls._resolve_env_value(
            'STOCK_LIST',
            default='',
            prefer_env_file=True,
        )
        stock_list = [
            (c or "").strip().upper()
            for c in split_stock_list(stock_list_str)
            if (c or "").strip()
        ]

        # === LiteLLM multi-key parsing ===
        # GEMINI_API_KEYS (comma-separated) > GEMINI_API_KEY (single)
        _gemini_keys_raw = os.getenv('GEMINI_API_KEYS', '')
        gemini_api_keys = [k.strip() for k in _gemini_keys_raw.split(',') if k.strip()]
        _single_gemini = os.getenv('GEMINI_API_KEY', '').strip()
        if not gemini_api_keys and _single_gemini:
            gemini_api_keys = [_single_gemini]

        # ANTHROPIC_API_KEYS > ANTHROPIC_API_KEY
        _anthropic_keys_raw = os.getenv('ANTHROPIC_API_KEYS', '')
        anthropic_api_keys = [k.strip() for k in _anthropic_keys_raw.split(',') if k.strip()]
        _single_anthropic = os.getenv('ANTHROPIC_API_KEY', '').strip()
        if not anthropic_api_keys and _single_anthropic:
            anthropic_api_keys = [_single_anthropic]

        # OPENAI_API_KEYS > AIHUBMIX_KEY > OPENAI_API_KEY
        _aihubmix = os.getenv('AIHUBMIX_KEY', '').strip()
        _openai_keys_raw = os.getenv('OPENAI_API_KEYS', '')
        openai_api_keys = [k.strip() for k in _openai_keys_raw.split(',') if k.strip()]
        if not openai_api_keys:
            _single_openai = os.getenv('OPENAI_API_KEY', '').strip()
            _fallback_key = _aihubmix or _single_openai
            if _fallback_key:
                openai_api_keys = [_fallback_key]
        openai_base_url = os.getenv('OPENAI_BASE_URL') or (
            'https://aihubmix.com/v1' if _aihubmix else None
        )

        # DEEPSEEK_API_KEYS > DEEPSEEK_API_KEY (independent from OpenAI-compatible layer)
        _deepseek_keys_raw = os.getenv('DEEPSEEK_API_KEYS', '')
        deepseek_api_keys = [k.strip() for k in _deepseek_keys_raw.split(',') if k.strip()]
        if not deepseek_api_keys:
            _single_deepseek = os.getenv('DEEPSEEK_API_KEY', '').strip()
            if _single_deepseek:
                deepseek_api_keys = [_single_deepseek]

        # Anspire Open shares the same key as Anspire Search and exposes an
        # OpenAI-compatible LLM gateway.  When no other OpenAI-compatible key is
        # configured, use ANSPIRE_API_KEYS as the legacy openai-compatible
        # provider so "one key" setups work without LLM_CHANNELS.
        anspire_keys_str = os.getenv('ANSPIRE_API_KEYS', '')
        anspire_api_keys = [k.strip() for k in anspire_keys_str.split(',') if k.strip()]
        anspire_llm_enabled = parse_env_bool(os.getenv('ANSPIRE_LLM_ENABLED'), default=True)
        anspire_llm_base_url = (
            os.getenv('ANSPIRE_LLM_BASE_URL') or ANSPIRE_LLM_BASE_URL_DEFAULT
        ).strip()
        _anspire_llm_model_env = os.getenv('ANSPIRE_LLM_MODEL', '').strip()
        anspire_channel_disabled = False
        for _raw_channel in os.getenv('LLM_CHANNELS', '').split(','):
            if _raw_channel.strip().lower() != "anspire":
                continue
            _channel_enabled_raw = os.getenv('LLM_ANSPIRE_ENABLED')
            if _channel_enabled_raw is not None and _channel_enabled_raw.strip():
                anspire_channel_disabled = not parse_env_bool(_channel_enabled_raw, default=True)
            else:
                anspire_channel_disabled = not anspire_llm_enabled
            break
        using_anspire_llm_legacy = bool(
            anspire_llm_enabled
            and not anspire_channel_disabled
            and anspire_api_keys
            and not openai_api_keys
        )
        if using_anspire_llm_legacy:
            openai_api_keys = list(anspire_api_keys)
            openai_base_url = anspire_llm_base_url

        # LITELLM_MODEL / LITELLM_FALLBACK_MODELS explicit values are recorded
        # before YAML/channels are parsed, but legacy inference is delayed until
        # the higher-priority sources and Hermes blocking issues are known.
        from src.llm.model_ref import normalize_model_ref

        litellm_model_explicit = normalize_model_ref(os.getenv('LITELLM_MODEL', ''))
        litellm_model = litellm_model_explicit
        inferred_legacy_deepseek_model = False
        _openai_model_env = os.getenv('OPENAI_MODEL', '').strip()
        if using_anspire_llm_legacy:
            _openai_model_name = _anspire_llm_model_env or _openai_model_env or ANSPIRE_LLM_MODEL_DEFAULT
        else:
            _openai_model_name = _openai_model_env or 'gpt-5.5'

        # LITELLM_FALLBACK_MODELS: comma-separated list of fallback models
        _fallback_str = os.getenv('LITELLM_FALLBACK_MODELS', '')
        litellm_fallback_models_explicit = bool(_fallback_str.strip())
        if _fallback_str.strip():
            litellm_fallback_models = [
                normalize_model_ref(model)
                for model in _fallback_str.split(',')
                if model.strip()
            ]
        else:
            litellm_fallback_models = []

        # === LLM Channels + YAML config ===
        litellm_config_path = os.getenv('LITELLM_CONFIG', '').strip() or None
        # Explicit config mode makes the source of LiteLLM models unambiguous.
        # "auto" preserves the historical YAML > Channels > legacy precedence.
        llm_config_mode = (os.getenv('LLM_CONFIG_MODE', '') or '').strip().lower() or 'auto'
        if llm_config_mode not in ('auto', 'channels', 'yaml', 'legacy'):
            llm_config_mode = 'auto'
        llm_models_source = "legacy_env"
        llm_channels: List[Dict[str, Any]] = []
        llm_channel_names: List[str] = []
        llm_channel_config_issues: List[Dict[str, str]] = []
        llm_blocks_legacy_fallback = False
        llm_blocked_hermes_routes: List[str] = []
        llm_model_list: List[Dict[str, Any]] = []

        # Priority 1: LITELLM_CONFIG (standard LiteLLM YAML config file)
        if litellm_config_path and llm_config_mode in ('auto', 'yaml'):
            llm_model_list = cls._parse_litellm_yaml(litellm_config_path)
            if llm_model_list:
                llm_models_source = "litellm_config"

        # Priority 2: LLM_CHANNELS (env var based channel config)
        if not llm_model_list and llm_config_mode in ('auto', 'channels'):
            _channels_str = os.getenv('LLM_CHANNELS', '').strip()
            if _channels_str:
                from src.llm.model_ref import canonicalize_connection_id

                llm_channel_names = [
                    canonicalize_connection_id(ch)
                    for ch in _channels_str.split(',')
                    if ch.strip()
                ]
                (
                    llm_channels,
                    hermes_issues,
                    llm_blocks_legacy_fallback,
                    llm_blocked_hermes_routes,
                ) = cls._parse_llm_channels_with_issues(_channels_str)
                llm_channel_config_issues = [issue.as_dict() for issue in hermes_issues]
                llm_model_list = cls._channels_to_model_list(llm_channels)
                if llm_model_list:
                    llm_models_source = "llm_channels"

        route_models = get_configured_llm_models(llm_model_list)
        from src.llm.model_ref import is_model_ref

        # Connection-aware aliases coexist with legacy routes in Router config.
        # Existing installations without explicit task refs must keep the same
        # route defaults instead of receiving duplicate ModelRef fallbacks.
        default_route_models = [
            model for model in route_models if not is_model_ref(model)
        ]
        if route_models:
            if not litellm_model and default_route_models:
                litellm_model = default_route_models[0]
            if (
                default_route_models
                and not litellm_fallback_models
                and not litellm_fallback_models_explicit
                and litellm_model
            ):
                from src.llm.model_ref import decode_model_ref

                try:
                    selected_ref = decode_model_ref(litellm_model)
                except ValueError:
                    selected_ref = None
                _seen = {
                    litellm_model,
                    selected_ref.runtime_route if selected_ref else litellm_model,
                }
                litellm_fallback_models = [
                    model for model in default_route_models
                    if model not in _seen and not _seen.add(model)  # type: ignore[func-returns-value]
                ]

        # Priority 3: Legacy env vars → auto-build model_list (backward compatible).
        # This is skipped when an explicit invalid Hermes channel blocks legacy fallback.
        if (
            not llm_model_list
            and not llm_blocks_legacy_fallback
            and llm_config_mode in ('auto', 'legacy')
        ):
            llm_model_list = cls._legacy_keys_to_model_list(
                gemini_api_keys, anthropic_api_keys, openai_api_keys,
                openai_base_url,
                deepseek_api_keys,
            )
            if llm_model_list:
                llm_models_source = "legacy_env"

            if not litellm_model:
                _gemini_model_name = os.getenv('GEMINI_MODEL', 'gemini-3.1-pro-preview').strip()
                _anthropic_model_name = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6').strip()
                if gemini_api_keys:
                    litellm_model = f'gemini/{_gemini_model_name}'
                elif anthropic_api_keys:
                    litellm_model = f'anthropic/{_anthropic_model_name}'
                elif deepseek_api_keys:
                    litellm_model = 'deepseek/deepseek-chat'
                    inferred_legacy_deepseek_model = True
                elif openai_api_keys:
                    # For openai-compatible models, add prefix only if not already prefixed
                    if '/' not in _openai_model_name:
                        litellm_model = f'openai/{_openai_model_name}'
                    else:
                        litellm_model = _openai_model_name

            if not litellm_fallback_models and not litellm_fallback_models_explicit:
                # Backward compat: use gemini_model_fallback when primary is gemini
                _gemini_fallback = os.getenv('GEMINI_MODEL_FALLBACK', 'gemini-3-flash-preview').strip()
                if litellm_model.startswith('gemini/') and _gemini_fallback:
                    _fb = f'gemini/{_gemini_fallback}' if '/' not in _gemini_fallback else _gemini_fallback
                    litellm_fallback_models = [_fb]

        if (
            inferred_legacy_deepseek_model
            and llm_models_source == "legacy_env"
            and litellm_model == 'deepseek/deepseek-chat'
        ):
            logger.warning(
                "Deprecation warning:\n"
                "deepseek-chat will be deprecated on 2026-07-24,\n"
                "please migrate to deepseek-v4-flash."
            )

        generation_backend = (
            os.getenv('GENERATION_BACKEND', LITELLM_BACKEND_ID).strip().lower()
            or LITELLM_BACKEND_ID
        )
        _generation_fallback_raw = os.getenv('GENERATION_FALLBACK_BACKEND')
        if _generation_fallback_raw is None:
            generation_fallback_backend = LITELLM_BACKEND_ID
        else:
            generation_fallback_backend = _generation_fallback_raw.strip().lower()
        agent_generation_backend = (
            os.getenv('AGENT_GENERATION_BACKEND', AUTO_AGENT_BACKEND_ID).strip().lower()
            or AUTO_AGENT_BACKEND_ID
        )
        generation_backend_timeout_seconds = parse_env_int(
            os.getenv('GENERATION_BACKEND_TIMEOUT_SECONDS'),
            DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS,
            field_name='GENERATION_BACKEND_TIMEOUT_SECONDS',
            minimum=1,
            maximum=MAX_LOCAL_CLI_TIMEOUT_SECONDS,
        )
        generation_backend_max_output_bytes = parse_env_int(
            os.getenv('GENERATION_BACKEND_MAX_OUTPUT_BYTES'),
            DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES,
            field_name='GENERATION_BACKEND_MAX_OUTPUT_BYTES',
            minimum=1,
            maximum=MAX_LOCAL_CLI_OUTPUT_BYTES,
        )
        generation_backend_max_concurrency = parse_env_int(
            os.getenv('GENERATION_BACKEND_MAX_CONCURRENCY'),
            DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY,
            field_name='GENERATION_BACKEND_MAX_CONCURRENCY',
            minimum=1,
            maximum=MAX_GENERATION_BACKEND_MAX_CONCURRENCY,
        )
        local_cli_backend_max_concurrency = parse_env_int(
            os.getenv('LOCAL_CLI_BACKEND_MAX_CONCURRENCY'),
            DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
            field_name='LOCAL_CLI_BACKEND_MAX_CONCURRENCY',
            minimum=1,
            maximum=MAX_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
        )
        opencode_cli_model = (os.getenv('OPENCODE_CLI_MODEL', '') or '').strip()

        agent_litellm_model = normalize_agent_litellm_model(
            os.getenv('AGENT_LITELLM_MODEL', ''),
            configured_models=set(get_configured_llm_models(llm_model_list)),
        )
        agent_context_compression_profile = normalize_agent_context_compression_profile(
            os.getenv('AGENT_CONTEXT_COMPRESSION_PROFILE')
        )
        agent_context_compression_preset = get_agent_context_compression_preset(
            agent_context_compression_profile
        )
        agent_context_compression_trigger_tokens = parse_agent_context_compression_int(
            os.getenv('AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS'),
            agent_context_compression_preset.trigger_tokens,
            field_name='AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
            minimum=1000,
            maximum=200000,
        )
        agent_context_protected_turns = parse_agent_context_compression_int(
            os.getenv('AGENT_CONTEXT_PROTECTED_TURNS'),
            agent_context_compression_preset.protected_turns,
            field_name='AGENT_CONTEXT_PROTECTED_TURNS',
            minimum=1,
            maximum=20,
        )

        # Parse search engine API Keys (supports multiple keys, comma-separated)
        bocha_keys_str = os.getenv('BOCHA_API_KEYS', '')
        bocha_api_keys = [k.strip() for k in bocha_keys_str.split(',') if k.strip()]

        minimax_keys_str = os.getenv('MINIMAX_API_KEYS', '')
        minimax_api_keys = [k.strip() for k in minimax_keys_str.split(',') if k.strip()]

        tavily_keys_str = os.getenv('TAVILY_API_KEYS', '')
        tavily_api_keys = [k.strip() for k in tavily_keys_str.split(',') if k.strip()]

        serpapi_keys_str = os.getenv('SERPAPI_API_KEYS', '')
        serpapi_keys = [k.strip() for k in serpapi_keys_str.split(',') if k.strip()]

        brave_keys_str = os.getenv('BRAVE_API_KEYS', '')
        brave_api_keys = [k.strip() for k in brave_keys_str.split(',') if k.strip()]

        _raw_urls = [u.strip() for u in os.getenv('SEARXNG_BASE_URLS', '').split(',') if u.strip()]
        searxng_base_urls = []
        invalid_searxng_urls = []
        for u in _raw_urls:
            p = urlparse(u)
            if p.scheme in ('http', 'https') and p.netloc:
                searxng_base_urls.append(u)
            else:
                invalid_searxng_urls.append(u)
        if invalid_searxng_urls:
            logger.warning(
                "SEARXNG_BASE_URLS 中存在无效 URL，已忽略: %s",
                ", ".join(invalid_searxng_urls[:3]),
            )
        searxng_public_instances_enabled = parse_env_bool(
            os.getenv('SEARXNG_PUBLIC_INSTANCES_ENABLED'),
            default=True,
        )

        # WeCom Message Type and Maximum Byte Count Logic
        wechat_msg_type = os.getenv('WECHAT_MSG_TYPE', 'markdown')
        wechat_msg_type_lower = wechat_msg_type.lower()
        wechat_max_bytes_env = os.getenv('WECHAT_MAX_BYTES')
        if wechat_max_bytes_env not in (None, ''):
            wechat_max_bytes = parse_env_int(
                wechat_max_bytes_env,
                2048 if wechat_msg_type_lower == 'text' else 4000,
                field_name='WECHAT_MAX_BYTES',
                minimum=1,
            )
        else:
            # Select default byte size based on message type when no explicit configuration is provided.
            wechat_max_bytes = 2048 if wechat_msg_type_lower == 'text' else 4000

        # Preserve historical semantics for startup flags: only an explicit
        # literal "true" enables immediate execution; empty strings stay False.
        legacy_run_immediately_env = cls._resolve_env_value(
            'RUN_IMMEDIATELY',
            prefer_env_file=True,
        )
        legacy_run_immediately = (
            legacy_run_immediately_env.lower() == 'true'
            if legacy_run_immediately_env is not None
            else True
        )

        schedule_run_immediately_env = cls._resolve_env_value(
            'SCHEDULE_RUN_IMMEDIATELY',
            prefer_env_file=True,
        )
        # Keep backward compatibility for container/process overrides:
        # when RUN_IMMEDIATELY is explicitly provided by the runtime but the
        # schedule-specific alias is absent, schedule mode should inherit the
        # legacy process value instead of being pulled back to the persisted
        # `.env` copy of SCHEDULE_RUN_IMMEDIATELY.
        if (
            not cls._had_bootstrap_runtime_env_key('SCHEDULE_RUN_IMMEDIATELY')
            and cls._has_bootstrap_runtime_env_override('RUN_IMMEDIATELY')
        ):
            schedule_run_immediately = legacy_run_immediately
        else:
            schedule_run_immediately = (
                schedule_run_immediately_env.lower() == 'true'
                if schedule_run_immediately_env is not None
                else legacy_run_immediately
            )
        schedule_time_value = cls._resolve_env_value(
            'SCHEDULE_TIME',
            default='18:00',
            prefer_env_file=True,
        )
        schedule_times_value = cls._resolve_env_value(
            'SCHEDULE_TIMES',
            default='',
            prefer_env_file=True,
        )

        report_language_raw = cls._resolve_report_language_env_value(
            preexisting_report_language
        )
        report_show_llm_model_raw = os.getenv('REPORT_SHOW_LLM_MODEL')
        report_show_llm_model = parse_env_bool(report_show_llm_model_raw, default=True)
        if report_show_llm_model_raw is not None and not report_show_llm_model_raw.strip():
            report_show_llm_model = False

        return cls(
            stock_list=stock_list,
            feishu_app_id=os.getenv('FEISHU_APP_ID'),
            feishu_app_secret=os.getenv('FEISHU_APP_SECRET'),
            feishu_folder_token=os.getenv('FEISHU_FOLDER_TOKEN'),
            tushare_token=os.getenv('TUSHARE_TOKEN'),
            tickflow_api_key=os.getenv('TICKFLOW_API_KEY'),
            tickflow_kline_adjust=normalize_tickflow_kline_adjust(os.getenv('TICKFLOW_KLINE_ADJUST')),
            tickflow_priority=parse_env_int(os.getenv('TICKFLOW_PRIORITY'), 2, field_name='TICKFLOW_PRIORITY', minimum=0),
            tickflow_batch_daily_enabled=parse_env_bool(os.getenv('TICKFLOW_BATCH_DAILY_ENABLED'), default=True),
            tickflow_batch_size=parse_env_int(os.getenv('TICKFLOW_BATCH_SIZE'), 100, field_name='TICKFLOW_BATCH_SIZE', minimum=1),
            finnhub_api_key=os.getenv('FINNHUB_API_KEY') or None,
            alphavantage_api_key=os.getenv('ALPHAVANTAGE_API_KEY') or None,
            longbridge_app_key=os.getenv('LONGBRIDGE_APP_KEY') or None,
            longbridge_app_secret=os.getenv('LONGBRIDGE_APP_SECRET') or None,
            longbridge_access_token=os.getenv('LONGBRIDGE_ACCESS_TOKEN') or None,
            longbridge_oauth_client_id=os.getenv('LONGBRIDGE_OAUTH_CLIENT_ID') or None,
            stock_index_remote_update_enabled=parse_env_bool(
                os.getenv('STOCK_INDEX_REMOTE_UPDATE_ENABLED'),
                default=True,
            ),
            generation_backend=generation_backend,
            generation_fallback_backend=generation_fallback_backend,
            generation_backend_timeout_seconds=generation_backend_timeout_seconds,
            generation_backend_max_output_bytes=generation_backend_max_output_bytes,
            generation_backend_max_concurrency=generation_backend_max_concurrency,
            local_cli_backend_max_concurrency=local_cli_backend_max_concurrency,
            opencode_cli_model=opencode_cli_model,
            litellm_model=litellm_model,
            litellm_fallback_models=litellm_fallback_models,
            llm_temperature=resolve_unified_llm_temperature(litellm_model),
            litellm_config_path=litellm_config_path,
            llm_config_mode=llm_config_mode,
            llm_models_source=llm_models_source,
            llm_channels=llm_channels,
            llm_channel_names=llm_channel_names,
            llm_channel_config_issues=llm_channel_config_issues,
            llm_blocks_legacy_fallback=llm_blocks_legacy_fallback,
            llm_blocked_hermes_routes=llm_blocked_hermes_routes,
            llm_model_list=llm_model_list,
            llm_prompt_cache_telemetry_enabled=parse_env_bool(
                os.getenv("LLM_PROMPT_CACHE_TELEMETRY_ENABLED"),
                default=True,
            ),
            llm_prompt_cache_hints_enabled=parse_env_bool(
                os.getenv("LLM_PROMPT_CACHE_HINTS_ENABLED"),
                default=False,
            ),
            llm_prompt_cache_diagnostics_level=parse_prompt_cache_diagnostics_level(
                os.getenv("LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL")
            ),
            gemini_api_keys=gemini_api_keys,
            anthropic_api_keys=anthropic_api_keys,
            openai_api_keys=openai_api_keys,
            deepseek_api_keys=deepseek_api_keys,
            gemini_api_key=os.getenv('GEMINI_API_KEY'),
            gemini_model=os.getenv('GEMINI_MODEL', 'gemini-3.1-pro-preview'),
            gemini_model_fallback=os.getenv('GEMINI_MODEL_FALLBACK', 'gemini-3-flash-preview'),
            gemini_temperature=parse_env_float(os.getenv('GEMINI_TEMPERATURE'), 0.7, field_name='GEMINI_TEMPERATURE'),
            gemini_request_delay=parse_env_float(os.getenv('GEMINI_REQUEST_DELAY'), 2.0, field_name='GEMINI_REQUEST_DELAY', minimum=0.0),
            gemini_max_retries=parse_env_int(os.getenv('GEMINI_MAX_RETRIES'), 5, field_name='GEMINI_MAX_RETRIES', minimum=0),
            gemini_retry_delay=parse_env_float(os.getenv('GEMINI_RETRY_DELAY'), 5.0, field_name='GEMINI_RETRY_DELAY', minimum=0.0),
            anthropic_api_key=os.getenv('ANTHROPIC_API_KEY'),
            anthropic_model=os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
            anthropic_temperature=parse_env_float(os.getenv('ANTHROPIC_TEMPERATURE'), 0.7, field_name='ANTHROPIC_TEMPERATURE'),
            anthropic_max_tokens=parse_env_int(os.getenv('ANTHROPIC_MAX_TOKENS'), 8192, field_name='ANTHROPIC_MAX_TOKENS', minimum=1),
            # AIHubmix is the preferred OpenAI-compatible provider (one key, all models, no VPN required).
            # Within the OpenAI-compatible layer: AIHUBMIX_KEY takes priority over OPENAI_API_KEY.
            # Overall provider fallback order: Gemini > Anthropic > OpenAI-compatible (incl. AIHubmix).
            # base_url is auto-set to aihubmix.com/v1 when AIHUBMIX_KEY is used and no explicit
            # OPENAI_BASE_URL override is provided.
            # Model names match upstream (e.g. gemini-3.1-pro-preview, gpt-5.5, deepseek-v4-flash).
            openai_api_key=openai_api_keys[0] if openai_api_keys else None,
            openai_base_url=openai_base_url,
            openai_model=_openai_model_name,
            openai_vision_model=os.getenv('OPENAI_VISION_MODEL') or None,
            openai_temperature=parse_env_float(os.getenv('OPENAI_TEMPERATURE'), 0.7, field_name='OPENAI_TEMPERATURE'),
            # Vision model: VISION_MODEL > OPENAI_VISION_MODEL (alias) > default
            vision_model=(
                normalize_model_ref(
                    os.getenv('VISION_MODEL')
                    or os.getenv('OPENAI_VISION_MODEL')
                    or ""
                )
            ),
            vision_provider_priority=os.getenv('VISION_PROVIDER_PRIORITY', 'gemini,anthropic,openai'),
            anspire_api_keys=anspire_api_keys,
            bocha_api_keys=bocha_api_keys,
            minimax_api_keys=minimax_api_keys,
            tavily_api_keys=tavily_api_keys,
            brave_api_keys=brave_api_keys,
            serpapi_keys=serpapi_keys,
            searxng_base_urls=searxng_base_urls,
            searxng_public_instances_enabled=searxng_public_instances_enabled,
            social_sentiment_api_key=os.getenv('SOCIAL_SENTIMENT_API_KEY') or None,
            social_sentiment_api_url=os.getenv('SOCIAL_SENTIMENT_API_URL', 'https://api.adanos.org').rstrip('/'),
            news_max_age_days=parse_env_int(os.getenv('NEWS_MAX_AGE_DAYS'), 3, field_name='NEWS_MAX_AGE_DAYS', minimum=1),
            news_strategy_profile=cls._parse_news_strategy_profile(
                os.getenv('NEWS_STRATEGY_PROFILE', 'short')
            ),
            news_intel_retention_days=parse_env_int(
                os.getenv('NEWS_INTEL_RETENTION_DAYS'),
                30,
                field_name='NEWS_INTEL_RETENTION_DAYS',
                minimum=1,
                maximum=365,
            ),
            news_intel_fetch_timeout_sec=parse_env_float(
                os.getenv('NEWS_INTEL_FETCH_TIMEOUT_SEC'),
                8.0,
                field_name='NEWS_INTEL_FETCH_TIMEOUT_SEC',
                minimum=1.0,
                maximum=30.0,
            ),
            news_intel_max_items_per_source=parse_env_int(
                os.getenv('NEWS_INTEL_MAX_ITEMS_PER_SOURCE'),
                50,
                field_name='NEWS_INTEL_MAX_ITEMS_PER_SOURCE',
                minimum=1,
                maximum=200,
            ),
            news_intel_auto_fetch_enabled=parse_env_bool(
                os.getenv('NEWS_INTEL_AUTO_FETCH_ENABLED'),
                False,
            ),
            newsnow_base_url=((os.getenv('NEWSNOW_BASE_URL') or '').strip().rstrip('/') or 'https://newsnow.busiyi.world'),
            bias_threshold=parse_env_float(os.getenv('BIAS_THRESHOLD'), 5.0, field_name='BIAS_THRESHOLD', minimum=1.0),
            agent_generation_backend=agent_generation_backend,
            agent_litellm_model=agent_litellm_model,
            agent_mode=os.getenv('AGENT_MODE', 'false').lower() == 'true',
            _agent_mode_explicit=os.getenv('AGENT_MODE') is not None,
            agent_max_steps=parse_env_int(
                os.getenv('AGENT_MAX_STEPS'),
                AGENT_MAX_STEPS_DEFAULT,
                field_name='AGENT_MAX_STEPS',
                minimum=1,
            ),
            agent_skills=[s.strip() for s in os.getenv('AGENT_SKILLS', '').split(',') if s.strip()],
            agent_skill_dir=os.getenv('AGENT_SKILL_DIR') or os.getenv('AGENT_STRATEGY_DIR'),
            agent_nl_routing=os.getenv('AGENT_NL_ROUTING', 'false').lower() == 'true',
            agent_arch=os.getenv('AGENT_ARCH', 'single').lower(),
            agent_orchestrator_mode=os.getenv('AGENT_ORCHESTRATOR_MODE', 'standard').lower(),
            agent_orchestrator_timeout_s=parse_env_int(
                os.getenv('AGENT_ORCHESTRATOR_TIMEOUT_S'),
                600,
                field_name='AGENT_ORCHESTRATOR_TIMEOUT_S',
                minimum=0,
            ),
            agent_technical_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_TECHNICAL_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_TECHNICAL_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_intel_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_INTEL_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_INTEL_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_risk_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_RISK_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_RISK_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_decision_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_DECISION_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_DECISION_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_portfolio_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_PORTFOLIO_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_PORTFOLIO_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_skill_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_SKILL_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_SKILL_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_risk_override=os.getenv('AGENT_RISK_OVERRIDE', 'true').lower() == 'true',
            agent_deep_research_budget=parse_env_int(
                os.getenv('AGENT_DEEP_RESEARCH_BUDGET'),
                30000,
                field_name='AGENT_DEEP_RESEARCH_BUDGET',
                minimum=5000,
            ),
            agent_deep_research_timeout=parse_env_int(
                os.getenv('AGENT_DEEP_RESEARCH_TIMEOUT'),
                180,
                field_name='AGENT_DEEP_RESEARCH_TIMEOUT',
                minimum=30,
            ),
            agent_memory_enabled=os.getenv('AGENT_MEMORY_ENABLED', 'false').lower() == 'true',
            agent_skill_autoweight=(
                os.getenv('AGENT_SKILL_AUTOWEIGHT')
                or os.getenv('AGENT_STRATEGY_AUTOWEIGHT', 'true')
            ).lower() == 'true',
            agent_skill_routing=(
                os.getenv('AGENT_SKILL_ROUTING')
                or os.getenv('AGENT_STRATEGY_ROUTING', 'auto')
            ).lower(),
            agent_context_compression_enabled=parse_env_bool(
                os.getenv('AGENT_CONTEXT_COMPRESSION_ENABLED'),
                default=False,
            ),
            agent_context_compression_profile=agent_context_compression_profile,
            agent_context_compression_trigger_tokens=agent_context_compression_trigger_tokens,
            agent_context_protected_turns=agent_context_protected_turns,
            agent_event_monitor_enabled=os.getenv('AGENT_EVENT_MONITOR_ENABLED', 'false').lower() == 'true',
            agent_event_monitor_interval_minutes=parse_env_int(
                os.getenv('AGENT_EVENT_MONITOR_INTERVAL_MINUTES'),
                5,
                field_name='AGENT_EVENT_MONITOR_INTERVAL_MINUTES',
                minimum=1,
            ),
            agent_event_alert_rules_json=os.getenv('AGENT_EVENT_ALERT_RULES_JSON', ''),
            wechat_webhook_url=os.getenv('WECHAT_WEBHOOK_URL'),
            feishu_webhook_url=os.getenv('FEISHU_WEBHOOK_URL'),
            feishu_webhook_secret=os.getenv('FEISHU_WEBHOOK_SECRET'),
            feishu_webhook_keyword=os.getenv('FEISHU_WEBHOOK_KEYWORD'),
            dingtalk_webhook_url=os.getenv('DINGTALK_WEBHOOK_URL'),
            dingtalk_secret=os.getenv('DINGTALK_SECRET'),


            feishu_chat_id=os.getenv('FEISHU_CHAT_ID'),
            feishu_receive_id_type=os.getenv('FEISHU_RECEIVE_ID_TYPE', 'chat_id'),
            feishu_domain=os.getenv('FEISHU_DOMAIN', 'feishu'),
            telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
            telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID'),
            telegram_message_thread_id=os.getenv('TELEGRAM_MESSAGE_THREAD_ID'),
            email_sender=os.getenv('EMAIL_SENDER'),
            email_sender_name=os.getenv('EMAIL_SENDER_NAME', 'StockPulse'),
            email_password=os.getenv('EMAIL_PASSWORD'),
            email_receivers=[r.strip() for r in os.getenv('EMAIL_RECEIVERS', '').split(',') if r.strip()],
            stock_email_groups=cls._parse_stock_email_groups(),
            pushover_user_key=os.getenv('PUSHOVER_USER_KEY'),
            pushover_api_token=os.getenv('PUSHOVER_API_TOKEN'),
            ntfy_url=os.getenv('NTFY_URL'),
            ntfy_token=os.getenv('NTFY_TOKEN'),
            gotify_url=os.getenv('GOTIFY_URL'),
            gotify_token=os.getenv('GOTIFY_TOKEN'),
            pushplus_token=os.getenv('PUSHPLUS_TOKEN'),
            pushplus_topic=os.getenv('PUSHPLUS_TOPIC'),
            serverchan3_sendkey=os.getenv('SERVERCHAN3_SENDKEY'),
            custom_webhook_urls=[u.strip() for u in os.getenv('CUSTOM_WEBHOOK_URLS', '').split(',') if u.strip()],
            custom_webhook_bearer_token=os.getenv('CUSTOM_WEBHOOK_BEARER_TOKEN'),
            custom_webhook_body_template=unescape_compose_sensitive_env_value(
                'CUSTOM_WEBHOOK_BODY_TEMPLATE',
                os.getenv('CUSTOM_WEBHOOK_BODY_TEMPLATE') or '',
            ) or None,
            webhook_verify_ssl=os.getenv('WEBHOOK_VERIFY_SSL', 'true').lower() == 'true',
            discord_bot_token=os.getenv('DISCORD_BOT_TOKEN'),
            discord_main_channel_id=(
                os.getenv('DISCORD_MAIN_CHANNEL_ID')
                or os.getenv('DISCORD_CHANNEL_ID')
            ),
            discord_webhook_url=os.getenv('DISCORD_WEBHOOK_URL'),
            discord_interactions_public_key=os.getenv('DISCORD_INTERACTIONS_PUBLIC_KEY'),
            slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL'),
            slack_bot_token=os.getenv('SLACK_BOT_TOKEN'),
            slack_channel_id=os.getenv('SLACK_CHANNEL_ID'),
            astrbot_url=os.getenv('ASTRBOT_URL'),
            astrbot_token=os.getenv('ASTRBOT_TOKEN'),
            notification_report_channels=parse_notification_route_channels(
                os.getenv('NOTIFICATION_REPORT_CHANNELS')
            ),
            notification_alert_channels=parse_notification_route_channels(
                os.getenv('NOTIFICATION_ALERT_CHANNELS')
            ),
            notification_system_error_channels=parse_notification_route_channels(
                os.getenv('NOTIFICATION_SYSTEM_ERROR_CHANNELS')
            ),
            notification_dedup_ttl_seconds=parse_env_int(
                os.getenv('NOTIFICATION_DEDUP_TTL_SECONDS'),
                0,
                field_name='NOTIFICATION_DEDUP_TTL_SECONDS',
                minimum=0,
            ),
            notification_cooldown_seconds=parse_env_int(
                os.getenv('NOTIFICATION_COOLDOWN_SECONDS'),
                0,
                field_name='NOTIFICATION_COOLDOWN_SECONDS',
                minimum=0,
            ),
            notification_quiet_hours=(os.getenv('NOTIFICATION_QUIET_HOURS') or '').strip(),
            notification_timezone=(os.getenv('NOTIFICATION_TIMEZONE') or '').strip(),
            notification_min_severity=(os.getenv('NOTIFICATION_MIN_SEVERITY') or '').strip().lower(),
            notification_daily_digest_enabled=parse_env_bool(
                os.getenv('NOTIFICATION_DAILY_DIGEST_ENABLED'),
                default=False,
            ),
            single_stock_notify=os.getenv('SINGLE_STOCK_NOTIFY', 'false').lower() == 'true',
            report_type=cls._parse_report_type(os.getenv('REPORT_TYPE', 'simple')),
            report_language=cls._parse_report_language(report_language_raw),
            report_summary_only=os.getenv('REPORT_SUMMARY_ONLY', 'false').lower() == 'true',
            report_show_llm_model=report_show_llm_model,
            report_templates_dir=os.getenv('REPORT_TEMPLATES_DIR', 'templates'),
            report_renderer_enabled=os.getenv('REPORT_RENDERER_ENABLED', 'false').lower() == 'true',
            report_integrity_enabled=os.getenv('REPORT_INTEGRITY_ENABLED', 'true').lower() == 'true',
            report_integrity_retry=parse_env_int(os.getenv('REPORT_INTEGRITY_RETRY'), 1, field_name='REPORT_INTEGRITY_RETRY', minimum=0),
            report_history_compare_n=parse_env_int(os.getenv('REPORT_HISTORY_COMPARE_N'), 0, field_name='REPORT_HISTORY_COMPARE_N', minimum=0),
            analysis_delay=parse_env_float(os.getenv('ANALYSIS_DELAY'), 0.0, field_name='ANALYSIS_DELAY', minimum=0.0),
            merge_email_notification=os.getenv('MERGE_EMAIL_NOTIFICATION', 'false').lower() == 'true',
            feishu_max_bytes=parse_env_int(os.getenv('FEISHU_MAX_BYTES'), 20000, field_name='FEISHU_MAX_BYTES', minimum=1),
            feishu_send_as_file=os.getenv('FEISHU_SEND_AS_FILE', '').lower() in ('true', '1', 'yes'),
            wechat_max_bytes=wechat_max_bytes,
            wechat_msg_type=wechat_msg_type_lower,
            discord_max_words=parse_env_int(os.getenv('DISCORD_MAX_WORDS'), 2000, field_name='DISCORD_MAX_WORDS', minimum=1),
            markdown_to_image_channels=[
                c.strip().lower()
                for c in os.getenv('MARKDOWN_TO_IMAGE_CHANNELS', '').split(',')
                if c.strip()
            ],
            markdown_to_image_max_chars=parse_env_int(
                os.getenv('MARKDOWN_TO_IMAGE_MAX_CHARS'),
                15000,
                field_name='MARKDOWN_TO_IMAGE_MAX_CHARS',
                minimum=1,
            ),
            md2img_engine=cls._parse_md2img_engine(os.getenv('MD2IMG_ENGINE', 'wkhtmltoimage')),
            prefetch_realtime_quotes=os.getenv('PREFETCH_REALTIME_QUOTES', 'true').lower() == 'true',
            database_path=os.getenv('DATABASE_PATH', './data/stock_analysis.db'),
            sqlite_wal_enabled=os.getenv('SQLITE_WAL_ENABLED', 'true').lower() == 'true',
            sqlite_busy_timeout_ms=parse_env_int(
                os.getenv('SQLITE_BUSY_TIMEOUT_MS'),
                5000,
                field_name='SQLITE_BUSY_TIMEOUT_MS',
                minimum=0,
            ),
            sqlite_write_retry_max=parse_env_int(
                os.getenv('SQLITE_WRITE_RETRY_MAX'),
                3,
                field_name='SQLITE_WRITE_RETRY_MAX',
                minimum=0,
            ),
            sqlite_write_retry_base_delay=parse_env_float(
                os.getenv('SQLITE_WRITE_RETRY_BASE_DELAY'),
                0.1,
                field_name='SQLITE_WRITE_RETRY_BASE_DELAY',
                minimum=0.0,
            ),
            save_context_snapshot=os.getenv('SAVE_CONTEXT_SNAPSHOT', 'true').lower() == 'true',
            backtest_enabled=os.getenv('BACKTEST_ENABLED', 'true').lower() == 'true',
            backtest_eval_window_days=parse_env_int(os.getenv('BACKTEST_EVAL_WINDOW_DAYS'), 10, field_name='BACKTEST_EVAL_WINDOW_DAYS', minimum=1),
            backtest_min_age_days=parse_env_int(os.getenv('BACKTEST_MIN_AGE_DAYS'), 14, field_name='BACKTEST_MIN_AGE_DAYS', minimum=1),
            backtest_engine_version=os.getenv('BACKTEST_ENGINE_VERSION', 'v1'),
            backtest_neutral_band_pct=parse_env_float(
                os.getenv('BACKTEST_NEUTRAL_BAND_PCT'),
                2.0,
                field_name='BACKTEST_NEUTRAL_BAND_PCT',
                minimum=0.0,
            ),
            log_dir=os.getenv('LOG_DIR', './logs'),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            max_workers=parse_env_int(os.getenv('MAX_WORKERS'), 3, field_name='MAX_WORKERS', minimum=1),
            debug=os.getenv('DEBUG', 'false').lower() == 'true',
            config_validate_mode=os.getenv('CONFIG_VALIDATE_MODE', 'warn').lower(),
            http_proxy=os.getenv('HTTP_PROXY'),
            https_proxy=os.getenv('HTTPS_PROXY'),
            schedule_enabled=cls._resolve_env_value(
                'SCHEDULE_ENABLED',
                default='false',
                prefer_env_file=True,
            ).lower() == 'true',
            schedule_time=(schedule_time_value or '18:00').strip() or '18:00',
            schedule_times=normalize_schedule_times(
                schedule_times_value,
                fallback_time=(schedule_time_value or '18:00').strip() or '18:00',
            ),
            schedule_run_immediately=schedule_run_immediately,
            run_immediately=legacy_run_immediately,
            market_review_enabled=os.getenv('MARKET_REVIEW_ENABLED', 'true').lower() == 'true',
            daily_market_context_enabled=os.getenv('DAILY_MARKET_CONTEXT_ENABLED', 'true').lower() == 'true',
            market_review_region=cls._parse_market_review_region(
                os.getenv('MARKET_REVIEW_REGION', 'cn')
            ),
            market_review_color_scheme=cls._parse_market_review_color_scheme(
                os.getenv('MARKET_REVIEW_COLOR_SCHEME', 'green_up')
            ),
            trading_day_check_enabled=os.getenv('TRADING_DAY_CHECK_ENABLED', 'true').lower() != 'false',
            webui_enabled=os.getenv('WEBUI_ENABLED', 'false').lower() == 'true',
            webui_host=os.getenv('WEBUI_HOST', '127.0.0.1'),
            webui_port=parse_env_int(os.getenv('WEBUI_PORT'), 8000, field_name='WEBUI_PORT', minimum=1, maximum=65535),
            # Robot configuration
            bot_enabled=os.getenv('BOT_ENABLED', 'true').lower() == 'true',
            bot_command_prefix=os.getenv('BOT_COMMAND_PREFIX', '/'),
            bot_rate_limit_requests=parse_env_int(os.getenv('BOT_RATE_LIMIT_REQUESTS'), 10, field_name='BOT_RATE_LIMIT_REQUESTS', minimum=1),
            bot_rate_limit_window=parse_env_int(os.getenv('BOT_RATE_LIMIT_WINDOW'), 60, field_name='BOT_RATE_LIMIT_WINDOW', minimum=1),
            bot_admin_users=[u.strip() for u in os.getenv('BOT_ADMIN_USERS', '').split(',') if u.strip()],
            # Feishu robot
            feishu_verification_token=os.getenv('FEISHU_VERIFICATION_TOKEN'),
            feishu_encrypt_key=os.getenv('FEISHU_ENCRYPT_KEY'),
            feishu_stream_enabled=os.getenv('FEISHU_STREAM_ENABLED', 'false').lower() == 'true',
            # DingTalk robot
            dingtalk_app_key=os.getenv('DINGTALK_APP_KEY'),
            dingtalk_app_secret=os.getenv('DINGTALK_APP_SECRET'),
            dingtalk_stream_enabled=os.getenv('DINGTALK_STREAM_ENABLED', 'false').lower() == 'true',
            # WeCom bot
            wecom_corpid=os.getenv('WECOM_CORPID'),
            wecom_token=os.getenv('WECOM_TOKEN'),
            wecom_encoding_aes_key=os.getenv('WECOM_ENCODING_AES_KEY'),
            wecom_agent_id=os.getenv('WECOM_AGENT_ID'),
            # Telegram
            telegram_webhook_secret=os.getenv('TELEGRAM_WEBHOOK_SECRET'),
            # Discord Bot extension configuration
            discord_bot_status=os.getenv('DISCORD_BOT_STATUS', 'A股智能分析 | /help'),
            # Enhanced real-time quote configuration.
            enable_realtime_quote=os.getenv('ENABLE_REALTIME_QUOTE', 'true').lower() == 'true',
            enable_realtime_technical_indicators=os.getenv(
                'ENABLE_REALTIME_TECHNICAL_INDICATORS', 'true'
            ).lower() == 'true',
            enable_chip_distribution=os.getenv('ENABLE_CHIP_DISTRIBUTION', 'true').lower() == 'true',
            # Eastmoney API patch switch
            enable_eastmoney_patch=os.getenv('ENABLE_EASTMONEY_PATCH', 'false').lower() == 'true',
            # Real-time quote data source priority:
            # - tencent: Tencent Finance; provides volume ratio, turnover rate, P/E, and P/B (recommended)
            # - akshare_sina: Sina Finance; stable basic quotes without volume ratio
            # - efinance/akshare_em: Eastmoney full-data APIs; most complete, but prone to blocking
            # - tushare: Tushare Pro; requires 2,000 points and provides comprehensive data
            realtime_source_priority=cls._resolve_realtime_source_priority(),
            realtime_cache_ttl=parse_env_int(os.getenv('REALTIME_CACHE_TTL'), 600, field_name='REALTIME_CACHE_TTL', minimum=0),
            circuit_breaker_cooldown=parse_env_int(os.getenv('CIRCUIT_BREAKER_COOLDOWN'), 300, field_name='CIRCUIT_BREAKER_COOLDOWN', minimum=0),
            enable_fundamental_pipeline=os.getenv('ENABLE_FUNDAMENTAL_PIPELINE', 'true').lower() == 'true',
            fundamental_stage_timeout_seconds=parse_env_float(
                os.getenv('FUNDAMENTAL_STAGE_TIMEOUT_SECONDS'),
                FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
                field_name='FUNDAMENTAL_STAGE_TIMEOUT_SECONDS',
                minimum=0.0,
            ),
            fundamental_fetch_timeout_seconds=parse_env_float(
                os.getenv('FUNDAMENTAL_FETCH_TIMEOUT_SECONDS'),
                8.0,
                field_name='FUNDAMENTAL_FETCH_TIMEOUT_SECONDS',
                minimum=0.0,
            ),
            fundamental_retry_max=parse_env_int(os.getenv('FUNDAMENTAL_RETRY_MAX'), 1, field_name='FUNDAMENTAL_RETRY_MAX', minimum=0),
            fundamental_cache_ttl_seconds=parse_env_int(
                os.getenv('FUNDAMENTAL_CACHE_TTL_SECONDS'),
                120,
                field_name='FUNDAMENTAL_CACHE_TTL_SECONDS',
                minimum=0,
            ),
            fundamental_cache_max_entries=parse_env_int(
                os.getenv('FUNDAMENTAL_CACHE_MAX_ENTRIES'),
                256,
                field_name='FUNDAMENTAL_CACHE_MAX_ENTRIES',
                minimum=1,
            ),
            portfolio_idempotency_replay_window_days=parse_env_int(
                os.getenv('PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS'),
                PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT,
                field_name='PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS',
                minimum=1,
                maximum=3650,
            ),
            portfolio_risk_concentration_alert_pct=parse_env_float(
                os.getenv('PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT'),
                35.0,
                field_name='PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT',
                minimum=0.0,
            ),
            portfolio_risk_drawdown_alert_pct=parse_env_float(
                os.getenv('PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT'),
                15.0,
                field_name='PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT',
                minimum=0.0,
            ),
            portfolio_risk_stop_loss_alert_pct=parse_env_float(
                os.getenv('PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT'),
                10.0,
                field_name='PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT',
                minimum=0.0,
            ),
            portfolio_risk_stop_loss_near_ratio=parse_env_float(
                os.getenv('PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO'),
                0.8,
                field_name='PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO',
                minimum=0.0,
            ),
            portfolio_risk_lookback_days=parse_env_int(
                os.getenv('PORTFOLIO_RISK_LOOKBACK_DAYS'),
                180,
                field_name='PORTFOLIO_RISK_LOOKBACK_DAYS',
                minimum=1,
            ),
            portfolio_fx_update_enabled=os.getenv('PORTFOLIO_FX_UPDATE_ENABLED', 'true').lower() == 'true',
            alphasift_enabled=parse_env_bool(os.getenv('ALPHASIFT_ENABLED'), default=False),
            alphasift_install_spec=(
                DEFAULT_ALPHASIFT_INSTALL_SPEC
                if os.getenv('ALPHASIFT_INSTALL_SPEC') is None
                else os.getenv('ALPHASIFT_INSTALL_SPEC', '').strip()
            ),
            kronos_enabled=parse_env_bool(os.getenv('KRONOS_ENABLED'), default=False),
            kronos_model_size=(
                os.getenv('KRONOS_MODEL_SIZE', _KRONOS_MODEL_SIZE_DEFAULT).strip().lower()
                or _KRONOS_MODEL_SIZE_DEFAULT
            ),
            kronos_weights_dir=os.getenv('KRONOS_WEIGHTS_DIR', '').strip() or None,
            decision_memory_enabled=parse_env_bool(os.getenv('DECISION_MEMORY_ENABLED'), default=True),
            decision_memory_lookback=parse_env_int(
                os.getenv('DECISION_MEMORY_LOOKBACK'), 5, field_name='DECISION_MEMORY_LOOKBACK', minimum=0
            ),
            decision_memory_min_age_days=parse_env_int(
                os.getenv('DECISION_MEMORY_MIN_AGE_DAYS'), 3, field_name='DECISION_MEMORY_MIN_AGE_DAYS', minimum=0
            ),
            decision_memory_min_samples=parse_env_int(
                os.getenv('DECISION_MEMORY_MIN_SAMPLES'), 5, field_name='DECISION_MEMORY_MIN_SAMPLES', minimum=1
            ),
            signal_scorecard_public_enabled=parse_env_bool(
                os.getenv('SIGNAL_SCORECARD_PUBLIC_ENABLED'), default=False
            ),
            signal_scorecard_min_samples=parse_env_int(
                os.getenv('SIGNAL_SCORECARD_MIN_SAMPLES'), 10, field_name='SIGNAL_SCORECARD_MIN_SAMPLES', minimum=1
            ),
            paper_portfolio_initial_cash=parse_env_float(
                os.getenv('PAPER_PORTFOLIO_INITIAL_CASH'), 1_000_000.0, field_name='PAPER_PORTFOLIO_INITIAL_CASH', minimum=0.0
            ),
        )


    @classmethod
    def _parse_stock_email_groups(cls) -> List[Tuple[List[str], List[str]]]:
        """
        Parse STOCK_GROUP_N and EMAIL_GROUP_N from environment.
        Returns [(stocks, emails), ...] ordered by group index.
        Stock codes are canonicalized via normalize_stock_code so that
        runtime routing matches the same equivalence used in validation.
        """
        from data_provider.base import normalize_stock_code

        groups: dict = {}
        stock_re = re.compile(r'^STOCK_GROUP_(\d+)$', re.IGNORECASE)
        email_re = re.compile(r'^EMAIL_GROUP_(\d+)$', re.IGNORECASE)
        for key in os.environ:
            m = stock_re.match(key)
            if m:
                idx = int(m.group(1))
                val = os.environ[key].strip()
                groups.setdefault(idx, {})['stocks'] = [
                    normalize_stock_code(c.strip())
                    for c in val.split(',') if c.strip()
                ]
            m = email_re.match(key)
            if m:
                idx = int(m.group(1))
                val = os.environ[key].strip()
                groups.setdefault(idx, {})['emails'] = [e.strip() for e in val.split(',') if e.strip()]
        result = []
        for idx in sorted(groups.keys()):
            g = groups[idx]
            if 'stocks' in g and 'emails' in g and g['stocks'] and g['emails']:
                result.append((g['stocks'], g['emails']))
        return result

    @classmethod
    def _parse_report_type(cls, value: str) -> str:
        """Parse REPORT_TYPE, fallback to simple for invalid values (supports brief)."""
        v = (value or 'simple').strip().lower()
        if v in ('simple', 'full', 'brief'):
            return v
        import logging
        logging.getLogger(__name__).warning(
            f"REPORT_TYPE '{value}' invalid, fallback to 'simple' (valid: simple/full/brief)"
        )
        return 'simple'

    @classmethod
    def _get_env_file_value(cls, key: str) -> Optional[str]:
        """Read one config key directly from the active `.env` file."""
        env_file = os.getenv("ENV_FILE")
        env_path = Path(env_file) if env_file else (Path(__file__).parent.parent / ".env")
        if not env_path.exists():
            return None

        try:
            env_values = dotenv_values(env_path)
        except Exception as exc:  # pragma: no cover - defensive branch
            # broad-exception: fallback_recorded - Read failure is logged as missing.
            log_safe_exception(
                logging.getLogger(__name__),
                "Environment file read failed",
                exc,
                error_code="environment_file_read_failed",
                level=logging.WARNING,
                context={"config_key": key},
            )
            return None

        value = env_values.get(key)
        if value is None:
            return None
        return unescape_compose_sensitive_env_value(key, str(value))

    @classmethod
    def _resolve_env_value(
        cls,
        key: str,
        *,
        default: Optional[str] = None,
        prefer_env_file: bool = False,
    ) -> Optional[str]:
        """Resolve one env value, optionally preferring the persisted `.env` copy."""
        env_value = os.getenv(key)
        file_value = cls._get_env_file_value(key)

        should_prefer_file = prefer_env_file or key in cls._WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS
        if should_prefer_file and file_value is not None:
            if env_value is not None and cls._has_bootstrap_runtime_env_override(key):
                return env_value
            return file_value
        if env_value is not None:
            return env_value
        if file_value is not None:
            return file_value
        return default

    @classmethod
    def _capture_bootstrap_runtime_env_overrides(cls) -> None:
        """Remember process-provided runtime env overrides before dotenv mutates os.environ.

        Called by ``setup_env()`` **before** ``load_dotenv()``, so ``os.environ``
        only contains genuine process-level values (Docker ``environment:``,
        Dockerfile ``ENV``, shell exports, etc.).

        A key is treated as an explicit override when it is present in
        ``os.environ`` and either:
        * absent from the persisted ``.env`` file, **or**
        * present with a **different** value.

        When both values are identical, the distinction is irrelevant and we
        do **not** flag the key, so that a later ``.env`` update by WebUI can
        take effect on config reload without requiring a container restart.
        """
        if cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED:
            return

        explicit_overrides = set()
        present_keys = set()
        for key in cls._WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS:
            env_value = os.environ.get(key)
            if env_value is None:
                continue

            present_keys.add(key)
            file_value = cls._get_env_file_value(key)
            if file_value is None or env_value != file_value:
                explicit_overrides.add(key)

        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES = frozenset(explicit_overrides)
        cls._BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS = frozenset(present_keys)
        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED = True

    @classmethod
    def _has_bootstrap_runtime_env_override(cls, key: str) -> bool:
        cls._capture_bootstrap_runtime_env_overrides()
        return key in cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES

    @classmethod
    def _had_bootstrap_runtime_env_key(cls, key: str) -> bool:
        cls._capture_bootstrap_runtime_env_overrides()
        return key in cls._BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS

    @classmethod
    def _resolve_report_language_env_value(
        cls,
        preexisting_env_value: Optional[str],
    ) -> str:
        """Resolve REPORT_LANGUAGE while preserving real process env overrides."""
        file_value = cls._get_env_file_value("REPORT_LANGUAGE")
        env_value = os.getenv("REPORT_LANGUAGE")

        if preexisting_env_value is not None:
            env_text = preexisting_env_value.strip()
            file_text = (file_value or "").strip()
            if file_text and env_text and env_text.lower() != file_text.lower():
                env_file = os.getenv("ENV_FILE") or str(Path(__file__).parent.parent / ".env")
                logging.getLogger(__name__).warning(
                    "REPORT_LANGUAGE environment value '%s' overrides %s ('%s')",
                    preexisting_env_value,
                    env_file,
                    file_value,
                )
            return preexisting_env_value

        if file_value is not None:
            return file_value

        return env_value or "zh"

    @classmethod
    def _parse_report_language(cls, value: Optional[str]) -> str:
        """Parse REPORT_LANGUAGE, fallback to zh for invalid values."""
        normalized = normalize_report_language(value, default="zh")
        raw = (value or "").strip()
        if raw and not is_supported_report_language_value(raw):
            logging.getLogger(__name__).warning(
                "REPORT_LANGUAGE '%s' invalid, fallback to 'zh' (valid: zh/en)",
                value,
            )
        return normalized

    @classmethod
    def _parse_news_strategy_profile(cls, value: Optional[str]) -> str:
        """Parse NEWS_STRATEGY_PROFILE, fallback to short for invalid values."""
        normalized = normalize_news_strategy_profile(value)
        raw = (value or "short").strip().lower()
        if raw != normalized:
            logging.getLogger(__name__).warning(
                "NEWS_STRATEGY_PROFILE '%s' invalid, fallback to 'short' "
                "(valid: ultra_short/short/medium/long)",
                value,
            )
        return normalized

    def get_effective_news_window_days(self) -> int:
        """Return effective news window days after profile + max-age merge."""
        return resolve_news_window_days(
            news_max_age_days=self.news_max_age_days,
            news_strategy_profile=self.news_strategy_profile,
        )

    @classmethod
    def _parse_market_review_region(cls, value: str) -> str:
        """解析大盘复盘市场区域，非法值记录警告后回退为 cn"""
        import logging
        v = (value or 'cn').strip().lower()
        supported_regions = ('cn', 'hk', 'us', 'jp', 'kr', 'both')
        ordered_regions = ('cn', 'hk', 'us', 'jp', 'kr')

        if v in supported_regions:
            if v == 'both':
                return ','.join(ordered_regions)
            return v

        if ',' in v:
            requested = {item.strip() for item in v.split(',') if item.strip()}
            normalized = [region for region in ordered_regions if region in requested]
            if 'both' in requested:
                normalized = list(ordered_regions)
            if normalized:
                return ','.join(normalized)

        logging.getLogger(__name__).warning(
            f"MARKET_REVIEW_REGION 配置值 '{value}' 无效，已回退为默认值 'cn'（合法值：cn / hk / us / jp / kr / both；支持逗号分隔有效值）"
        )
        return 'cn'

    @classmethod
    def _parse_market_review_color_scheme(cls, value: str) -> str:
        """Parse market-review index change color scheme."""
        import logging
        v = (value or 'green_up').strip().lower().replace('-', '_')
        if v in ('green_up', 'red_up'):
            return v
        logging.getLogger(__name__).warning(
            "MARKET_REVIEW_COLOR_SCHEME 配置值 '%s' 无效，已回退为默认值 'green_up'（合法值：green_up / red_up）",
            value,
        )
        return 'green_up'

    @classmethod
    def _parse_md2img_engine(cls, value: str) -> str:
        """Parse MD2IMG_ENGINE, fallback to wkhtmltoimage for invalid values (Issue #455)."""
        v = (value or 'wkhtmltoimage').strip().lower()
        if v in ('wkhtmltoimage', 'markdown-to-file'):
            return v
        if v:
            import logging
            logging.getLogger(__name__).warning(
                f"MD2IMG_ENGINE '{value}' invalid, fallback to 'wkhtmltoimage' "
                "(valid: wkhtmltoimage | markdown-to-file)"
            )
        return 'wkhtmltoimage'

    @classmethod
    def _resolve_realtime_source_priority(cls) -> str:
        """
        Resolve realtime source priority with automatic tushare injection.

        When TUSHARE_TOKEN is configured but REALTIME_SOURCE_PRIORITY is not
        explicitly set, automatically prepend 'tushare' to the default priority
        so that the paid data source is utilized for realtime quotes as well.
        """
        explicit = os.getenv('REALTIME_SOURCE_PRIORITY')
        default_priority = 'tencent,akshare_sina,efinance,akshare_em'

        if explicit:
            # User explicitly set priority, respect it
            return explicit

        tushare_token = os.getenv('TUSHARE_TOKEN', '').strip()
        if tushare_token:
            # Token configured but no explicit priority override
            # Prepend tushare so the paid source is tried first
            import logging
            logger = logging.getLogger(__name__)
            resolved = f'tushare,{default_priority}'
            logger.info(
                f"TUSHARE_TOKEN detected, auto-injecting tushare into realtime priority: {resolved}"
            )
            return resolved

        return default_priority
