"""Validation methods for :class:`src.config.Config`."""

import os
from typing import Dict, List, Optional
from urllib.parse import urlparse

from src.config_parts.defaults import ConfigIssue, _has_gotify_base_url, _has_ntfy_topic_endpoint
from src.config_parts.parsers import (
    _get_litellm_provider,
    _matches_exact_route,
    _uses_direct_env_provider,
    get_configured_llm_models,
    get_effective_agent_primary_model,
)
from src.llm.backend_registry import (
    AUTO_AGENT_BACKEND_ID,
    GENERATION_ONLY_BACKEND_IDS,
    LITELLM_BACKEND_ID,
    LOCAL_CLI_GENERATION_BACKEND_IDS,
    OPENCODE_CLI_BACKEND_ID,
    SUPPORTED_AGENT_GENERATION_BACKENDS,
    SUPPORTED_AGENT_UI_BACKENDS,
    SUPPORTED_GENERATION_BACKENDS,
)
from src.llm.hermes import route_deployment_origins, route_has_hermes
from src.notification_contracts import (
    is_feishu_app_bot_configured,
    is_feishu_static_configured,
)
from src.notification_noise import (
    NOTIFICATION_SEVERITIES,
    is_supported_notification_severity,
    parse_notification_quiet_hours,
    validate_notification_timezone,
)


class _ConfigValidationMethods:

    def validate_structured(self) -> List[ConfigIssue]:
        """Return structured validation issues with severity levels.

        Covers all three LLM configuration tiers introduced by PR #494:
        - LITELLM_CONFIG (YAML)
        - LLM_CHANNELS (env)
        - Legacy per-provider keys

        Returns:
            List of ConfigIssue objects, each carrying a severity
            ("error" | "warning" | "info"), a human-readable message, and the
            primary environment variable / field name it relates to.
        """
        issues: List[ConfigIssue] = []

        # --- Stock list ---
        if not self.stock_list:
            issues.append(ConfigIssue(
                severity="error",
                message="未配置 STOCK_LIST。请设置至少一个股票代码，例如：600519,hk00700,AAPL。",
                field="STOCK_LIST",
            ))
        elif self.stock_email_groups:
            from data_provider.base import normalize_stock_code
            configured_stock_set = {
                normalize_stock_code(code)
                for code in self.stock_list
                if (code or "").strip()
            }
            missing_group_stocks_dict: Dict[str, None] = {}
            for stocks, _emails in self.stock_email_groups:
                for stock in stocks:
                    raw = (stock or "").strip()
                    if not raw:
                        continue
                    normalized_stock = normalize_stock_code(stock)
                    if normalized_stock in configured_stock_set:
                        continue
                    if normalized_stock in missing_group_stocks_dict:
                        continue
                    missing_group_stocks_dict[normalized_stock] = None
            missing_group_stocks = list(missing_group_stocks_dict.keys())
            if missing_group_stocks:
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "检测到 STOCK_GROUP_N 中存在未包含在 STOCK_LIST 内的股票："
                        f"{', '.join(missing_group_stocks[:6])}。"
                        "STOCK_GROUP_N 仅用于邮件路由，不会扩大分析范围；"
                        "请先将这些股票加入 STOCK_LIST。"
                    ),
                    field="STOCK_GROUP_N",
                ))

        # --- Data sources (informational only) ---
        if not self.tushare_token:
            issues.append(ConfigIssue(
                severity="info",
                message="未配置 Tushare Token，将使用其他数据源",
                field="TUSHARE_TOKEN",
            ))

        # --- Generation backend selection ---
        generation_backend = (self.generation_backend or LITELLM_BACKEND_ID).strip().lower()
        generation_fallback_backend = str(self.generation_fallback_backend or "").strip().lower()
        agent_generation_backend = (
            self.agent_generation_backend or AUTO_AGENT_BACKEND_ID
        ).strip().lower()
        if generation_backend not in SUPPORTED_GENERATION_BACKENDS:
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "GENERATION_BACKEND 当前支持 "
                    f"{'、'.join(sorted(SUPPORTED_GENERATION_BACKENDS))}。"
                    f"已配置的值为：{generation_backend}。"
                ),
                field="GENERATION_BACKEND",
            ))
        if generation_fallback_backend and generation_fallback_backend == generation_backend:
            generation_fallback_backend = ""
        if generation_fallback_backend and generation_fallback_backend != LITELLM_BACKEND_ID:
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "GENERATION_FALLBACK_BACKEND 当前支持 litellm、与 primary 相同的 no-op 值，或空字符串。"
                    f"已配置的值为：{generation_fallback_backend}。"
                ),
                field="GENERATION_FALLBACK_BACKEND",
            ))
        if agent_generation_backend not in SUPPORTED_AGENT_GENERATION_BACKENDS:
            agent_ui_backends = "、".join(sorted(SUPPORTED_AGENT_UI_BACKENDS))
            local_toolless_backends = "、".join(sorted(GENERATION_ONLY_BACKEND_IDS))
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    f"AGENT_GENERATION_BACKEND 当前支持 {agent_ui_backends}；"
                    f"local CLI backend（{local_toolless_backends}）仅作为显式 unsupported diagnostic 保留，"
                    "不支持 Agent 工具调用。"
                    f"已配置的值为：{agent_generation_backend}。"
                ),
                field="AGENT_GENERATION_BACKEND",
            ))
        litellm_model_lower = (self.litellm_model or "").strip().lower()
        local_model_prefix = next(
            (
                backend_id
                for backend_id in GENERATION_ONLY_BACKEND_IDS
                if litellm_model_lower.startswith(f"{backend_id}/")
            ),
            "",
        )
        if local_model_prefix:
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    f"{local_model_prefix} 是 GENERATION_BACKEND，不是 LiteLLM provider。"
                    f"请不要使用 LITELLM_MODEL={local_model_prefix}/...。"
                ),
                field="LITELLM_MODEL",
            ))
        if generation_backend == OPENCODE_CLI_BACKEND_ID:
            opencode_model = (self.opencode_cli_model or "").strip()
            unsafe_model = bool(opencode_model) and (
                any(ch.isspace() for ch in opencode_model)
                or any(
                    marker in opencode_model
                    for marker in ("|", ">", "<", ";", "`", "&&", "||", "$")
                )
            )
            if unsafe_model:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "OPENCODE_CLI_MODEL 是可选的 OpenCode 模型覆盖值。"
                        "配置时会作为单个 --model 参数传给 OpenCode，不能包含空白或 shell 元字符；"
                        "不配置时 StockPulse 将使用 OpenCode 自身默认模型。"
                    ),
                    field="OPENCODE_CLI_MODEL",
                ))

        # --- LLM availability ---
        for raw_issue in self.llm_channel_config_issues or []:
            issues.append(ConfigIssue(
                severity=raw_issue.get("severity", "error"),  # type: ignore[arg-type]
                message=raw_issue.get("message", "LLM channel configuration is invalid"),
                field=raw_issue.get("field", "LLM_CHANNELS"),
                code=raw_issue.get("code", "invalid_channel_config"),
            ))

        # llm_model_list is populated for YAML / channels / managed legacy keys.
        # Other LiteLLM-native providers (for example cohere/*) run through the
        # direct litellm env path and therefore do not populate llm_model_list.
        has_direct_env_model = bool(self.litellm_model) and _uses_direct_env_provider(self.litellm_model)
        local_generation_backend = generation_backend in LOCAL_CLI_GENERATION_BACKEND_IDS
        if not local_generation_backend and not self.llm_model_list and not has_direct_env_model:
            if self.litellm_config_path:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "已配置 LITELLM_CONFIG，但未解析出可用模型。"
                        "请检查 YAML 中的 model_list、litellm_params 和环境变量引用。"
                    ),
                    field="LITELLM_CONFIG",
                ))
            elif self.llm_channel_names:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "已配置 LLM_CHANNELS，但未解析出可用模型渠道。"
                        "请检查对应 LLM_<CHANNEL>_API_KEY(S)、"
                        "LLM_<CHANNEL>_MODELS、LLM_<CHANNEL>_PROTOCOL 或 Base URL。"
                    ),
                    field="LLM_CHANNELS",
                ))
            else:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "未配置任何可用的 AI 模型接入。请至少配置 ANSPIRE_API_KEYS、"
                        "AIHUBMIX_KEY、GEMINI_API_KEY、ANTHROPIC_API_KEY、"
                        "OPENAI_API_KEY 或 DEEPSEEK_API_KEY 中的一个，或配置 "
                        "LITELLM_CONFIG / LLM_CHANNELS 可用模型渠道。"
                    ),
                    field="LITELLM_CONFIG",
                ))
        elif not local_generation_backend and not self.litellm_model:
            issues.append(ConfigIssue(
                severity="info",
                message=(
                    "尚未明确指定主模型，系统将自动从可用 API Key 推断。"
                    "建议尽早配置主模型（格式如 gemini/gemini-3.1-pro-preview）"
                ),
                field="LITELLM_MODEL",
            ))

        available_router_models = get_configured_llm_models(self.llm_model_list)
        available_router_model_set = set(available_router_models)

        def _has_runtime_source_for_model(model: str) -> bool:
            if not model or _uses_direct_env_provider(model):
                return True
            provider = _get_litellm_provider(model)
            if provider in {"gemini", "vertex_ai"}:
                return any(k and len(k) >= 8 for k in (self.gemini_api_keys or []))
            if provider == "anthropic":
                return any(k and len(k) >= 8 for k in (self.anthropic_api_keys or []))
            if provider == "deepseek":
                return any(k and len(k) >= 8 for k in (self.deepseek_api_keys or []))
            if provider == "openai":
                return any(k and len(k) >= 8 for k in (self.openai_api_keys or []))
            return False

        configured_agent_primary_model = bool((self.agent_litellm_model or "").strip())
        effective_agent_primary_model = get_effective_agent_primary_model(self)

        if available_router_model_set:
            if self.litellm_model:
                origins = route_deployment_origins(self.llm_model_list, self.litellm_model)
                if origins.is_mixed:
                    issues.append(ConfigIssue(
                        severity="error",
                        message=(
                            "Hermes/non-Hermes mixed generation routes are not supported in Phase 3. "
                            "请选择纯 Hermes 或纯非 Hermes 主模型。"
                        ),
                        field="LITELLM_MODEL",
                        code="mixed_hermes_route_unsupported",
                    ))
            if (
                self.litellm_model
                and not _uses_direct_env_provider(self.litellm_model)
                and not _matches_exact_route(self.litellm_model, available_router_model_set)
            ):
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "已配置的主模型未出现在当前渠道或高级模型路由配置中。"
                        f" 当前可用模型：{', '.join(available_router_models[:6])}"
                    ),
                    field="LITELLM_MODEL",
                ))

            if configured_agent_primary_model and effective_agent_primary_model:
                origins = route_deployment_origins(self.llm_model_list, effective_agent_primary_model)
                if origins.is_hermes_only:
                    issues.append(ConfigIssue(
                        severity="error",
                        message=(
                            "Hermes-only route 不能作为 Agent 主模型。"
                            "请选择包含非 Hermes deployment 的 Agent-safe route。"
                        ),
                        field="AGENT_LITELLM_MODEL",
                        code="explicit_agent_model_no_safe_deployment",
                    ))

            if (
                configured_agent_primary_model
                and effective_agent_primary_model
                and not _uses_direct_env_provider(effective_agent_primary_model)
                and not _matches_exact_route(effective_agent_primary_model, available_router_model_set)
            ):
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "已配置的 Agent 主模型未出现在当前渠道或高级模型路由配置中。"
                        f" 当前可用模型：{', '.join(available_router_models[:6])}"
                    ),
                    field="AGENT_LITELLM_MODEL",
                ))

            mixed_fallbacks = [
                model for model in (self.litellm_fallback_models or [])
                if route_deployment_origins(self.llm_model_list, model).is_mixed
            ]
            if mixed_fallbacks:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "Hermes/non-Hermes mixed generation routes are not supported as fallback models in Phase 3: "
                        f"{', '.join(mixed_fallbacks[:3])}"
                    ),
                    field="LITELLM_FALLBACK_MODELS",
                    code="mixed_hermes_route_unsupported",
                ))

            invalid_fallbacks = [
                model for model in (self.litellm_fallback_models or [])
                if model and not _matches_exact_route(model, available_router_model_set)
                and not _uses_direct_env_provider(model)
            ]
            if invalid_fallbacks:
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "备选模型中包含未在当前渠道或高级模型路由配置中声明的模型："
                        f"{', '.join(invalid_fallbacks[:3])}"
                    ),
                    field="LITELLM_FALLBACK_MODELS",
                ))

            if (
                self.vision_model
                and not _uses_direct_env_provider(self.vision_model)
                and not _matches_exact_route(self.vision_model, available_router_model_set)
            ):
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "VISION_MODEL 未出现在当前渠道声明中。"
                        f" 当前可用模型：{', '.join(available_router_models[:6])}"
                    ),
                    field="VISION_MODEL",
                ))
            if self.vision_model and route_has_hermes(self.llm_model_list, self.vision_model):
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "Hermes Phase 3 未验证 Vision 能力，VISION_MODEL 不能选择包含 Hermes deployment 的 route。"
                    ),
                    field="VISION_MODEL",
                    code="hermes_vision_unsupported",
                ))
        elif (
            configured_agent_primary_model
            and effective_agent_primary_model
            and not _has_runtime_source_for_model(effective_agent_primary_model)
        ):
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "已配置 Agent 主模型，但未找到可用的运行时来源"
                    "（启用渠道或匹配的 API Key）。"
                ),
                field="AGENT_LITELLM_MODEL",
            ))

        # --- Search engine (informational only) ---
        if not self.has_search_capability_enabled():
            issues.append(ConfigIssue(
                severity="info",
                message="未配置搜索引擎能力 (Bocha/MiniMax/Tavily/Brave/SerpAPI/SearXNG)，新闻搜索功能将不可用",
                field="BOCHA_API_KEYS",
            ))

        # --- Notification channels ---
        has_notification = bool(
            self.wechat_webhook_url
            or self.feishu_webhook_url
            or (
                (self.feishu_app_id or "")
                and (self.feishu_app_secret or "")
                and (self.feishu_chat_id or "")
            )
            or (self.telegram_bot_token and self.telegram_chat_id)
            or (self.email_sender and self.email_password)
            or (self.pushover_user_key and self.pushover_api_token)
            or _has_ntfy_topic_endpoint(self.ntfy_url)
            or (
                self.gotify_url
                and (self.gotify_token or "").strip()
                and _has_gotify_base_url(self.gotify_url)
            )
            or self.pushplus_token
            or self.serverchan3_sendkey
            or self.custom_webhook_urls
            or self.astrbot_url
            or (self.discord_bot_token and self.discord_main_channel_id)
            or self.discord_webhook_url
            or self.slack_webhook_url
            or (self.slack_bot_token and self.slack_channel_id)
        )

        if not has_notification:
            issues.append(ConfigIssue(
                severity="warning",
                message="未配置通知渠道，将不发送推送通知",
                field="WECHAT_WEBHOOK_URL",
            ))

        has_telegram_token = bool((self.telegram_bot_token or "").strip())
        has_telegram_chat_id = bool((self.telegram_chat_id or "").strip())
        if has_telegram_token != has_telegram_chat_id:
            issues.append(ConfigIssue(
                severity="error",
                message="Telegram 通知配置不完整：TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID 必须同时配置。",
                field="TELEGRAM_CHAT_ID" if has_telegram_token else "TELEGRAM_BOT_TOKEN",
            ))

        has_email_sender = bool((self.email_sender or "").strip())
        has_email_password = bool((self.email_password or "").strip())
        if has_email_sender != has_email_password:
            issues.append(ConfigIssue(
                severity="error",
                message="邮件通知配置不完整：EMAIL_SENDER 和 EMAIL_PASSWORD 必须同时配置。",
                field="EMAIL_PASSWORD" if has_email_sender else "EMAIL_SENDER",
            ))

        def _warn_if_webhook_url_invalid(field: str, value: Optional[str]) -> None:
            raw_url = (value or "").strip()
            if not raw_url:
                return
            parsed = urlparse(raw_url)
            if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
                return
            issues.append(ConfigIssue(
                severity="warning",
                message=f"{field} 看起来不是有效 URL，请确认是否以 http:// 或 https:// 开头。",
                field=field,
            ))

        for field, value in (
            ("WECHAT_WEBHOOK_URL", self.wechat_webhook_url),
            ("FEISHU_WEBHOOK_URL", self.feishu_webhook_url),
            ("DINGTALK_WEBHOOK_URL", self.dingtalk_webhook_url),
            ("DISCORD_WEBHOOK_URL", self.discord_webhook_url),
            ("SLACK_WEBHOOK_URL", self.slack_webhook_url),
            ("ASTRBOT_URL", self.astrbot_url),
        ):
            _warn_if_webhook_url_invalid(field, value)

        for custom_url in self.custom_webhook_urls:
            _warn_if_webhook_url_invalid("CUSTOM_WEBHOOK_URLS", custom_url)

        if self.ntfy_url and not _has_ntfy_topic_endpoint(self.ntfy_url):
            issues.append(ConfigIssue(
                severity="error",
                message="NTFY_URL 必须包含 topic path，例如 https://ntfy.sh/my-topic",
                field="NTFY_URL",
            ))

        if self.gotify_url and not _has_gotify_base_url(self.gotify_url):
            issues.append(ConfigIssue(
                severity="error",
                message="GOTIFY_URL 必须是 Gotify server base URL，不包含 /message，例如 https://gotify.example",
                field="GOTIFY_URL",
            ))

        if (
            self.gotify_url
            and _has_gotify_base_url(self.gotify_url)
            and not (self.gotify_token or "").strip()
        ):
            issues.append(ConfigIssue(
                severity="warning",
                message="已配置 GOTIFY_URL，但缺少 GOTIFY_TOKEN，Gotify 渠道不会启用",
                field="GOTIFY_TOKEN",
            ))

        if self.notification_quiet_hours:
            try:
                parse_notification_quiet_hours(self.notification_quiet_hours)
            except ValueError as exc:
                issues.append(ConfigIssue(
                    severity="error",
                    message=f"通知静默时段配置无效：{exc}",
                    field="NOTIFICATION_QUIET_HOURS",
                ))

        if self.notification_timezone:
            try:
                validate_notification_timezone(self.notification_timezone)
            except ValueError as exc:
                issues.append(ConfigIssue(
                    severity="error",
                    message=f"通知时区配置无效：{exc}",
                    field="NOTIFICATION_TIMEZONE",
                ))

        if self.notification_min_severity and not is_supported_notification_severity(self.notification_min_severity):
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "通知最低级别配置无效，允许值："
                    f"{', '.join(NOTIFICATION_SEVERITIES)}"
                ),
                field="NOTIFICATION_MIN_SEVERITY",
            ))

        if self.notification_daily_digest_enabled:
            issues.append(ConfigIssue(
                severity="warning",
                message=(
                    "NOTIFICATION_DAILY_DIGEST_ENABLED 当前为预留配置；"
                    "P4 不会发送每日摘要或持久化摘要内容。"
                ),
                field="NOTIFICATION_DAILY_DIGEST_ENABLED",
            ))

        has_feishu_app_id = bool((self.feishu_app_id or "").strip())
        has_feishu_app_secret = bool((self.feishu_app_secret or "").strip())
        has_feishu_app_credentials_complete = has_feishu_app_id and has_feishu_app_secret
        has_feishu_app_credentials = has_feishu_app_id or has_feishu_app_secret
        has_feishu_doc_token = bool((self.feishu_folder_token or "").strip())
        has_feishu_full_cloud_doc_credentials = (
            has_feishu_app_credentials_complete
            and has_feishu_doc_token
        )
        has_feishu_stream_route = bool(self.feishu_stream_enabled and has_feishu_app_credentials_complete)
        has_feishu_app_notification_route = is_feishu_app_bot_configured(self)
        if (
            has_feishu_app_credentials
            and not has_feishu_full_cloud_doc_credentials
            and not is_feishu_static_configured(self)
            and not has_feishu_stream_route
            and not has_feishu_app_notification_route
        ):
            suggestions = []
            if has_feishu_app_credentials_complete:
                suggestions.append("配置 FEISHU_CHAT_ID 开启 App Bot 主动推送")
                suggestions.append("开启 FEISHU_STREAM_ENABLED 使用应用机器人事件订阅")
            else:
                suggestions.append("补齐 FEISHU_APP_ID / FEISHU_APP_SECRET 后配置 FEISHU_CHAT_ID 开启 App Bot 主动推送")
            suggestions.append("配置 FEISHU_WEBHOOK_URL 使用自定义机器人 Webhook 推送")
            issues.append(ConfigIssue(
                severity="warning",
                message="仅配置 FEISHU_APP_ID / FEISHU_APP_SECRET 不会开启飞书静态通知。"
                        + " 请选择以下方式之一："
                        + "；".join(suggestions) + "。",
                field="FEISHU_CHAT_ID",
            ))

        # --- Deprecated field migration hints ---
        if os.getenv("OPENAI_VISION_MODEL"):
            issues.append(ConfigIssue(
                severity="info",
                message=(
                    "OPENAI_VISION_MODEL 已废弃，请改用 VISION_MODEL。"
                    "当前值已自动迁移，建议更新配置文件以消除此提示。"
                ),
                field="OPENAI_VISION_MODEL",
            ))

        # --- Vision key availability ---
        # Only warn when user explicitly set VISION_MODEL (or OPENAI_VISION_MODEL alias).
        # Skipped when vision_model is empty (Vision not intentionally configured).
        if self.vision_model:
            # Maps provider prefix → the corresponding key list tracked by Config.
            # vertex_ai shares gemini keys; other LiteLLM-native providers are not
            # in this map (their keys come from env vars, which we cannot inspect here).
            _VISION_KEY_MAP = {
                "gemini": self.gemini_api_keys,
                "vertex_ai": self.gemini_api_keys,
                "anthropic": self.anthropic_api_keys,
                "openai": self.openai_api_keys,
                "deepseek": self.deepseek_api_keys,
            }
            # Derive the primary model's provider prefix so that its key is also
            # checked even when the provider is absent from VISION_PROVIDER_PRIORITY.
            _primary_prefix = (
                self.vision_model.split("/")[0]
                if "/" in self.vision_model
                else "openai"
            )
            _priority_providers = [
                p.strip().lower()
                for p in self.vision_provider_priority.split(",")
                if p.strip()
            ]
            # Union: fallback providers + primary model's own provider
            _all_providers = {_primary_prefix} | set(_priority_providers)

            # Align with get_api_keys_for_model: keys must be non-empty and len >= 8
            _has_any_key = any(
                any(k and len(k) >= 8 for k in (_VISION_KEY_MAP.get(p) or []))
                for p in _all_providers
                if p in _VISION_KEY_MAP
            )
            if not _has_any_key:
                _checked = sorted(_all_providers & _VISION_KEY_MAP.keys())
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "VISION_MODEL 已配置，但未找到可用的 Vision API Key "
                        f"（已检查：{', '.join(_checked)}）。"
                        "图片股票代码提取功能将不可用，请配置对应的 API Key。"
                    ),
                    field="VISION_MODEL",
                ))

        return issues

    def validate(self) -> List[str]:
        """Return validation messages as plain strings (backward-compatible).

        Internally delegates to validate_structured().  Callers that only need
        the human-readable strings can continue to use this method unchanged.

        Returns:
            List of message strings, one per ConfigIssue.
        """
        return [issue.message for issue in self.validate_structured()]
