"""Setup methods for the system-config facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.system_config_service import (
        ANSPIRE_LLM_BASE_URL_DEFAULT,
        ANSPIRE_LLM_MODEL_DEFAULT,
        AUTO_AGENT_BACKEND_ID,
        Any,
        CODEX_CLI_BACKEND_ID,
        Dict,
        GENERATION_ONLY_BACKEND_IDS,
        HERMES_DEFAULT_BASE_URL,
        HERMES_DEFAULT_MODEL,
        HERMES_DEFAULT_PROTOCOL,
        LITELLM_BACKEND_ID,
        LOCAL_CLI_GENERATION_BACKEND_IDS,
        List,
        Path,
        Set,
        Tuple,
        _get_litellm_provider,
        _uses_direct_env_provider,
        canonicalize_llm_channel_protocol,
        channel_allows_empty_api_key,
        is_feishu_static_env_configured,
        is_reserved_hermes_name,
        llm_channel_map,
        normalize_agent_litellm_model,
        normalize_backend_id,
        normalize_llm_channel_model,
        os,
        parse_env_bool,
        parse_hermes_channel,
        resolve_llm_channel_protocol,
        resolve_local_cli_preset,
        shutil,
        split_stock_list,
    )


class _SystemConfigSetupMethods:
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
