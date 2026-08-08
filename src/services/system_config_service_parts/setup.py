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
    @staticmethod
    def _setup_model_runtime_route(model: str) -> str:
        """Return the runtime route for a ModelRef while preserving legacy routes."""
        from src.llm.model_ref import decode_model_ref

        normalized = (model or "").strip()
        try:
            decoded = decode_model_ref(normalized)
        except ValueError:
            return normalized
        return decoded.runtime_route if decoded else normalized

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

            protocol, base_url = llm_channel_map.resolve_connection_transport(
                effective_map,
                name,
            )
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
        from src.llm.model_ref import is_model_ref, normalize_model_ref

        explicit_model = (effective_map.get("LITELLM_MODEL") or "").strip()
        yaml_models = self._collect_yaml_models_from_map(effective_map)
        channel_models = self._collect_setup_channel_models(effective_map)
        channel_model_refs = set(self._collect_llm_channel_model_refs_from_map(effective_map))

        if explicit_model:
            if is_model_ref(explicit_model):
                normalized_ref = normalize_model_ref(explicit_model)
                if yaml_models:
                    return "", "主要模型未出现在当前 LiteLLM YAML model_list 中"
                if normalized_ref in channel_model_refs:
                    return normalized_ref, "explicit"
                return "", "主要模型缺少可用连接或匹配的 API 密钥"
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

    def _build_setup_primary_llm_check(
        self,
        effective_map: Dict[str, str],
        local_detect: Any = None,
    ) -> Dict[str, Any]:
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
        # Zero-config first success (#796): keep needs_action for full AI smoke,
        # but guide beginners to data-only dry-run and/or detected local Ollama.
        if local_detect is None:
            local_detect = self._detect_local_runtime_for_setup(effective_map)
        if getattr(local_detect, "available", False):
            models = list(getattr(local_detect, "models", None) or [])
            base_url = getattr(local_detect, "base_url", None) or "http://127.0.0.1:11434"
            models_hint = (
                f"已发现模型：{', '.join(models[:3])}。"
                if models
                else "尚未列出本地模型，可在 Local Models 拉取后再应用。"
            )
            return self._setup_check(
                "llm_primary",
                "主要模型",
                "ai_model",
                True,
                "needs_action",
                (
                    f"{source}。已在本机检测到 Ollama（{base_url}），"
                    f"可作为零 Key 本地生成路径。{models_hint}"
                ),
                (
                    "推荐：在「本地模型」应用检测到的 Ollama 配置（无需云端 API Key），"
                    "或先运行 data-only：`python main.py --dry-run` 获取行情数据报告。"
                ),
            )
        return self._setup_check(
            "llm_primary",
            "主要模型",
            "ai_model",
            True,
            "needs_action",
            (
                f"{source}。"
                "在配置模型前，仍可用 data-only 路径完成首次成功："
                "`python main.py --dry-run`（仅行情数据，无 AI 分析）。"
            ),
            (
                "请在「模型接入」添加云端 Key，或启动本机 Ollama 后走本地零成本路径；"
                "也可先 dry-run 体验数据报告。"
            ),
        )

    def _build_setup_agent_llm_check(
        self,
        effective_map: Dict[str, str],
        primary_check: Dict[str, Any],
    ) -> Dict[str, Any]:
        check = self._resolve_setup_agent_llm_check(effective_map, primary_check)
        if (
            check["status"] == "needs_action"
            and parse_env_bool(
                effective_map.get("AGENT_FEATURES_ACKNOWLEDGED_OFF"),
                default=False,
            )
        ):
            return self._setup_check(
                "llm_agent",
                "Agent 模型",
                "agent",
                True,
                "optional",
                "已确认暂不使用问股 Agent。CLI 后端仅覆盖报告生成；问股 Agent 需要支持工具调用的 API 模型。",
                "需要启用 Agent 时，请关闭「确认暂不使用 Agent 功能」，并配置 API 模型连接。",
            )
        return check

    def _resolve_setup_agent_llm_check(
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
                primary_runtime_route = self._setup_model_runtime_route(primary_model)
                if primary_runtime_route in hermes_routes and primary_runtime_route not in non_hermes_routes:
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

        yaml_models = self._collect_yaml_models_from_map(effective_map)
        configured_models = set(yaml_models or self._collect_setup_channel_models(effective_map))
        if not yaml_models:
            configured_models.update(self._collect_llm_channel_model_refs_from_map(effective_map))
        agent_model = normalize_agent_litellm_model(agent_model_raw, configured_models=configured_models)
        agent_runtime_route = self._setup_model_runtime_route(agent_model)
        if agent_runtime_route in hermes_routes and agent_runtime_route not in non_hermes_routes:
            return self._setup_check(
                "llm_agent",
                "Agent 模型",
                "agent",
                True,
                "needs_action",
                f"Agent 主要模型 {agent_runtime_route} 只有 Hermes deployment，Phase 3 不支持 Agent 工具调用。",
                "请选择非 Hermes Agent 模型，或配置 mixed route 中的非 Hermes deployment。",
            )
        configured_agent_message = f"已配置 Agent 主要模型: {agent_runtime_route}"
        if generation_backend in LOCAL_CLI_GENERATION_BACKEND_IDS:
            local_cli_display = resolve_local_cli_preset(generation_backend).display_name
            configured_agent_message = (
                f"普通分析使用 {local_cli_display}；Agent 工具调用仍使用主要模型: {agent_runtime_route}"
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
            f"Agent 主要模型 {agent_runtime_route} 缺少可用连接或匹配的 API 密钥。",
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

    def _detect_local_runtime_for_setup(self, effective_map: Dict[str, str]):
        """Run the fast loopback local-runtime probe used by setup readiness."""
        from src.services.local_runtime_detect import detect_local_runtime_from_config_map

        return detect_local_runtime_from_config_map(effective_map)

    def _build_setup_local_runtime_check(
        self,
        effective_map: Dict[str, str],
        local_detect: Any = None,
    ) -> Dict[str, Any]:
        """Surface local Ollama detect as a stable, non-blocking setup check."""
        detect = (
            local_detect
            if local_detect is not None
            else self._detect_local_runtime_for_setup(effective_map)
        )
        if not getattr(detect, "detect_enabled", True):
            return self._setup_check(
                "local_runtime",
                "本地运行时检测",
                "system",
                False,
                "optional",
                "已关闭 LOCAL_RUNTIME_AUTO_DETECT，跳过本机 Ollama 探测。",
                "需要自动发现时，将 LOCAL_RUNTIME_AUTO_DETECT 设为 true。",
            )
        if getattr(detect, "available", False):
            models = list(getattr(detect, "models", None) or [])
            model_text = (
                f"已发现 {len(models)} 个本地模型"
                + (f"（例如 {', '.join(models[:3])}）" if models else "（列表为空，可先拉取模型）")
            )
            profile_hint = ""
            suggested = getattr(detect, "suggested_profile", None) or {}
            litellm_model = str(suggested.get("LITELLM_MODEL") or "").strip()
            if litellm_model:
                profile_hint = (
                    f" 建议非密钥字段：LLM_CHANNELS=ollama，LITELLM_MODEL={litellm_model}。"
                )
            base_url = getattr(detect, "base_url", None) or "http://127.0.0.1:11434"
            return self._setup_check(
                "local_runtime",
                "本地运行时检测",
                "system",
                False,
                "configured",
                f"已检测到本机 Ollama：{base_url}。{model_text}。{profile_hint}".strip(),
                "可在设置中应用本地零成本路径，无需云端 API Key。",
            )
        return self._setup_check(
            "local_runtime",
            "本地运行时检测",
            "system",
            False,
            "optional",
            (
                "未在回环地址检测到可用的 Ollama（默认 http://127.0.0.1:11434）。"
                "探测失败仅记录日志，不影响启动。"
            ),
            (
                "可选：启动 Ollama 后刷新就绪检查以使用本地零成本路径；"
                "或先 `python main.py --dry-run` 获取 data-only 报告。"
            ),
        )

    def _build_setup_data_only_check(self, effective_map: Dict[str, str]) -> Dict[str, Any]:
        """Explain the zero-key data-only first-success path (dry-run equivalent)."""
        stocks = split_stock_list(effective_map.get("STOCK_LIST") or "")
        if stocks:
            return self._setup_check(
                "data_only_path",
                "零配置 data-only 路径",
                "base",
                False,
                "configured",
                (
                    f"自选股已配置 {len(stocks)} 只；无 LLM Key 时仍可运行 "
                    "`python main.py --dry-run` 获取行情数据报告（与 dry-run 产物一致）。"
                ),
                "配置主要模型或本地 Ollama 后即可升级为完整 AI 分析。",
            )
        return self._setup_check(
            "data_only_path",
            "零配置 data-only 路径",
            "base",
            False,
            "optional",
            (
                "无 LLM Key 时，正常分析会给出明确引导，并可使用 "
                "`python main.py --dry-run` 完成 data-only 首次成功。"
            ),
            "请先在 STOCK_LIST 添加至少 1 只股票，再运行 dry-run。",
        )
