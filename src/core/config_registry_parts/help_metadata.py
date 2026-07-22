"""Help links, examples, and warnings for registered fields."""

from typing import Any, Dict

_DOC_FULL_GUIDE_ENV = [
    {
        "label": "完整指南：环境变量完整列表",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
    },
]

_DOC_FULL_GUIDE_SEARCH = [
    {
        "label": "完整指南：搜索服务配置",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#搜索服务配置",
    },
]

_DOC_FULL_GUIDE_DATA_SOURCE = [
    {
        "label": "完整指南：数据源配置",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#数据源配置",
    },
]

_DOC_FULL_GUIDE_NOTIFICATION = [
    {
        "label": "完整指南：通知渠道配置",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#通知渠道详细配置",
    },
]

_DOC_LLM_CONFIG = [
    {
        "label": "LLM 配置指南",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/LLM_CONFIG_GUIDE.md",
    },
    {
        "label": "LLM 服务商配置速查",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/llm-providers.md",
    },
]

_DOC_CUSTOM_WEBHOOK = [
    {
        "label": "完整指南：自定义 Webhook",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#自定义-webhook",
    },
]

_FIELD_HELP_METADATA: Dict[str, Dict[str, Any]] = {
    "ANSPIRE_LLM_ENABLED": {
        "help_key": "settings.ai_model.anspire_llm",
        "examples": [
            "ANSPIRE_LLM_ENABLED=true",
            "ANSPIRE_API_KEYS=your_anspire_key",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": [],
    },
    "ANSPIRE_LLM_BASE_URL": {
        "help_key": "settings.ai_model.anspire_llm",
        "examples": [
            "ANSPIRE_LLM_BASE_URL=https://open-gateway.anspire.cn/v6",
            "ANSPIRE_LLM_BASE_URL=https://open-gateway.anspire.ai/v6",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["base_url_must_match_provider"],
    },
    "ANSPIRE_LLM_MODEL": {
        "help_key": "settings.ai_model.anspire_llm",
        "examples": [
            "ANSPIRE_LLM_MODEL=Doubao-Seed-2.0-lite",
            "LITELLM_MODEL=openai/Doubao-Seed-2.0-lite",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": [],
    },
    "DEEPSEEK_API_KEYS": {
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "DEEPSEEK_API_KEYS=sk-xxxx,sk-yyyy",
            "LITELLM_MODEL=deepseek/deepseek-v4-flash",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "GEMINI_API_KEYS": {
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "GEMINI_API_KEYS=your_gemini_key_1,your_gemini_key_2",
            "LITELLM_MODEL=gemini/gemini-3.1-pro-preview",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "GEMINI_MODEL": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "GEMINI_MODEL=gemini-3.1-pro-preview",
            "LITELLM_MODEL=gemini/gemini-3.1-pro-preview",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "GEMINI_MODEL_FALLBACK": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "GEMINI_MODEL_FALLBACK=gemini-3-flash-preview",
            "LITELLM_FALLBACK_MODELS=gemini/gemini-3-flash-preview",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "GEMINI_TEMPERATURE": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "GEMINI_TEMPERATURE=0.7",
            "LLM_TEMPERATURE=0.7",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "OPENAI_API_KEYS": {
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "OPENAI_API_KEYS=sk-xxxx,sk-yyyy",
            "OPENAI_BASE_URL=https://api.example.com/v1",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "OPENAI_MODEL": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "OPENAI_MODEL=gpt-5.5",
            "LITELLM_MODEL=openai/gpt-5.5",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "OPENAI_VISION_MODEL": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "OPENAI_VISION_MODEL=gpt-5.5",
            "VISION_MODEL=openai/gpt-5.5",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "OPENAI_TEMPERATURE": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "OPENAI_TEMPERATURE=0.7",
            "LLM_TEMPERATURE=0.7",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "ANTHROPIC_API_KEYS": {
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "ANTHROPIC_API_KEYS=sk-ant-xxxx,sk-ant-yyyy",
            "LITELLM_MODEL=anthropic/claude-sonnet-4-6",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "ANTHROPIC_MODEL": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "ANTHROPIC_MODEL=claude-sonnet-4-6",
            "LITELLM_MODEL=anthropic/claude-sonnet-4-6",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "ANTHROPIC_TEMPERATURE": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "ANTHROPIC_TEMPERATURE=0.7",
            "LLM_TEMPERATURE=0.7",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "ANTHROPIC_MAX_TOKENS": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "ANTHROPIC_MAX_TOKENS=8192",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "TICKFLOW_API_KEY": {
        "help_key": "settings.data_source.TICKFLOW_API_KEY",
        "examples": [
            "TICKFLOW_API_KEY=your_tickflow_key",
        ],
        "docs": _DOC_FULL_GUIDE_DATA_SOURCE,
        "warning_codes": ["secret_value"],
    },
    "TICKFLOW_PRIORITY": {
        "help_key": "settings.data_source.TICKFLOW_PRIORITY",
        "examples": ["TICKFLOW_PRIORITY=2"],
        "docs": _DOC_FULL_GUIDE_DATA_SOURCE,
    },
    "TICKFLOW_KLINE_ADJUST": {
        "help_key": "settings.data_source.TICKFLOW_KLINE_ADJUST",
        "examples": ["TICKFLOW_KLINE_ADJUST=none"],
        "docs": _DOC_FULL_GUIDE_DATA_SOURCE,
    },
    "TICKFLOW_BATCH_DAILY_ENABLED": {
        "help_key": "settings.data_source.TICKFLOW_BATCH_DAILY_ENABLED",
        "examples": ["TICKFLOW_BATCH_DAILY_ENABLED=true"],
        "docs": _DOC_FULL_GUIDE_DATA_SOURCE,
    },
    "TICKFLOW_BATCH_SIZE": {
        "help_key": "settings.data_source.TICKFLOW_BATCH_SIZE",
        "examples": ["TICKFLOW_BATCH_SIZE=100"],
        "docs": _DOC_FULL_GUIDE_DATA_SOURCE,
    },
    "SERPAPI_API_KEYS": {
        "help_key": "settings.data_source.search_api_keys",
        "examples": [
            "SERPAPI_API_KEYS=serpapi_key_1,serpapi_key_2",
        ],
        "docs": _DOC_FULL_GUIDE_SEARCH,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "BRAVE_API_KEYS": {
        "help_key": "settings.data_source.search_api_keys",
        "examples": [
            "BRAVE_API_KEYS=brave_key_1,brave_key_2",
        ],
        "docs": _DOC_FULL_GUIDE_SEARCH,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "BOCHA_API_KEYS": {
        "help_key": "settings.data_source.search_api_keys",
        "examples": [
            "BOCHA_API_KEYS=bocha_key_1,bocha_key_2",
        ],
        "docs": _DOC_FULL_GUIDE_SEARCH,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "MINIMAX_API_KEYS": {
        "help_key": "settings.data_source.search_api_keys",
        "examples": [
            "MINIMAX_API_KEYS=minimax_key_1,minimax_key_2",
        ],
        "docs": _DOC_FULL_GUIDE_SEARCH,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "SEARXNG_PUBLIC_INSTANCES_ENABLED": {
        "help_key": "settings.data_source.SEARXNG_BASE_URLS",
        "examples": [
            "SEARXNG_PUBLIC_INSTANCES_ENABLED=true",
            "SEARXNG_PUBLIC_INSTANCES_ENABLED=false",
        ],
        "docs": _DOC_FULL_GUIDE_SEARCH,
        "warning_codes": ["public_instance_stability"],
    },
    "BIAS_THRESHOLD": {
        "help_key": "settings.data_source.BIAS_THRESHOLD",
        "examples": [
            "BIAS_THRESHOLD=5.0",
            "BIAS_THRESHOLD=8.0",
        ],
        "docs": _DOC_FULL_GUIDE_DATA_SOURCE,
        "warning_codes": [],
    },
    "PYTDX_HOST": {
        "help_key": "settings.data_source.pytdx",
        "examples": [
            "PYTDX_HOST=119.147.212.81",
            "PYTDX_PORT=7709",
        ],
        "docs": _DOC_FULL_GUIDE_DATA_SOURCE,
        "warning_codes": [],
    },
    "PYTDX_PORT": {
        "help_key": "settings.data_source.pytdx",
        "examples": [
            "PYTDX_PORT=7709",
            "PYTDX_HOST=119.147.212.81",
        ],
        "docs": _DOC_FULL_GUIDE_DATA_SOURCE,
        "warning_codes": [],
    },
    "PYTDX_SERVERS": {
        "help_key": "settings.data_source.pytdx",
        "examples": [
            "PYTDX_SERVERS=119.147.212.81:7709,119.147.212.81:7711",
        ],
        "docs": _DOC_FULL_GUIDE_DATA_SOURCE,
        "warning_codes": ["overrides_pytdx_host_port"],
    },
    "DINGTALK_APP_KEY": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "DINGTALK_APP_KEY=your_dingtalk_app_key",
            "DINGTALK_APP_SECRET=your_dingtalk_app_secret",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value"],
    },
    "DINGTALK_APP_SECRET": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "DINGTALK_APP_SECRET=your_dingtalk_app_secret",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value"],
    },
    "PUSHPLUS_TOKEN": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "PUSHPLUS_TOKEN=your_pushplus_token",
            "PUSHPLUS_TOPIC=your_pushplus_topic",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value"],
    },
    "CUSTOM_WEBHOOK_BEARER_TOKEN": {
        "help_key": "settings.notification.CUSTOM_WEBHOOK_URLS",
        "examples": [
            "CUSTOM_WEBHOOK_BEARER_TOKEN=your_bearer_token",
        ],
        "docs": _DOC_CUSTOM_WEBHOOK,
        "warning_codes": ["secret_value"],
    },
    "CUSTOM_WEBHOOK_BODY_TEMPLATE": {
        "help_key": "settings.notification.CUSTOM_WEBHOOK_URLS",
        "examples": [
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"msg_type":"text","content":$content_json}',
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$title_json,"text":$content_json}',
        ],
        "docs": _DOC_CUSTOM_WEBHOOK,
        "warning_codes": ["json_template_must_render_object"],
    },
    "FEISHU_WEBHOOK_SECRET": {
        "help_key": "settings.notification.FEISHU_WEBHOOK_URL",
        "examples": [
            "FEISHU_WEBHOOK_SECRET=your_feishu_webhook_secret",
        ],
        "docs": [
            *_DOC_FULL_GUIDE_NOTIFICATION,
            {
                "label": "飞书机器人配置专题",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/bot/feishu-bot-config.md",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "FEISHU_WEBHOOK_KEYWORD": {
        "help_key": "settings.notification.FEISHU_WEBHOOK_URL",
        "examples": [
            "FEISHU_WEBHOOK_KEYWORD=股票日报",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": [],
    },
    "FEISHU_APP_ID": {
        "help_key": "settings.notification.FEISHU_WEBHOOK_URL",
        "examples": [
            "FEISHU_APP_ID=cli_xxxxx",
            "FEISHU_APP_SECRET=your_feishu_app_secret",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["not_webhook_delivery"],
    },
    "FEISHU_APP_SECRET": {
        "help_key": "settings.notification.FEISHU_WEBHOOK_URL",
        "examples": [
            "FEISHU_APP_SECRET=your_feishu_app_secret",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value", "not_webhook_delivery"],
    },
    "TELEGRAM_MESSAGE_THREAD_ID": {
        "help_key": "settings.notification.telegram",
        "examples": [
            "TELEGRAM_MESSAGE_THREAD_ID=123",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": [],
    },
    "DISCORD_MAIN_CHANNEL_ID": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "DISCORD_MAIN_CHANNEL_ID=123456789012345678",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": [],
    },
    "DISCORD_INTERACTIONS_PUBLIC_KEY": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "DISCORD_INTERACTIONS_PUBLIC_KEY=your_discord_public_key",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": [],
    },
    "SLACK_CHANNEL_ID": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "SLACK_CHANNEL_ID=C0123456789",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": [],
    },
    "SLACK_WEBHOOK_URL": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["webhook_secret_value"],
    },
    "PUSHOVER_USER_KEY": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "PUSHOVER_USER_KEY=your_pushover_user_key",
            "PUSHOVER_API_TOKEN=your_pushover_api_token",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value"],
    },
    "PUSHOVER_API_TOKEN": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "PUSHOVER_API_TOKEN=your_pushover_api_token",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value"],
    },
    "NTFY_URL": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "NTFY_URL=https://ntfy.sh/your_topic",
            "NTFY_TOKEN=your_ntfy_token",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["webhook_secret_value"],
    },
    "NTFY_TOKEN": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "NTFY_TOKEN=your_ntfy_token",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value"],
    },
    "GOTIFY_URL": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "GOTIFY_URL=https://gotify.example.com",
            "GOTIFY_TOKEN=your_gotify_token",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["webhook_secret_value"],
    },
    "GOTIFY_TOKEN": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "GOTIFY_TOKEN=your_gotify_token",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value"],
    },
    "PUSHPLUS_TOPIC": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "PUSHPLUS_TOPIC=your_pushplus_topic",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": [],
    },
    "SERVERCHAN3_SENDKEY": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "SERVERCHAN3_SENDKEY=your_serverchan3_sendkey",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value"],
    },
    "ASTRBOT_URL": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "ASTRBOT_URL=https://astrbot.example.com/webhook",
            "ASTRBOT_TOKEN=your_astrbot_token",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["webhook_secret_value"],
    },
    "ASTRBOT_TOKEN": {
        "help_key": "settings.notification.chat_bots",
        "examples": [
            "ASTRBOT_TOKEN=your_astrbot_token",
        ],
        "docs": _DOC_FULL_GUIDE_NOTIFICATION,
        "warning_codes": ["secret_value"],
    },
}
