"""Explicit metadata for the remaining documented environment inventory.

These fields close the historical ``.env.example`` registry gap.  The helpers
below only remove repetitive dictionary boilerplate; every key, category,
type, control, default, and sensitivity decision is declared in this module.
Web visibility is owned separately by ``catalog.WEB_SETTINGS_HIDDEN_FROM_UI``.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


def _field(
    *,
    title: str,
    description: str,
    category: str,
    data_type: str,
    ui_control: str,
    default_value: str,
    display_order: int,
    is_sensitive: bool = False,
    options: Iterable[Any] = (),
    validation: Mapping[str, Any] | None = None,
    warning_codes: Iterable[str] = (),
) -> Dict[str, Any]:
    """Build one complete registry entry from explicitly declared metadata."""
    return {
        "title": title,
        "description": description,
        "category": category,
        "data_type": data_type,
        "ui_control": ui_control,
        "is_sensitive": is_sensitive,
        "is_required": False,
        "is_editable": True,
        "default_value": default_value,
        "options": list(options),
        "validation": dict(validation or {}),
        "display_order": display_order,
        "warning_codes": list(warning_codes),
    }


def _integer(
    title: str,
    description: str,
    category: str,
    default: str,
    order: int,
    *,
    minimum: int = 0,
    maximum: int | None = None,
    warning_codes: Iterable[str] = (),
) -> Dict[str, Any]:
    validation: Dict[str, Any] = {"min": minimum}
    if maximum is not None:
        validation["max"] = maximum
    return _field(
        title=title,
        description=description,
        category=category,
        data_type="integer",
        ui_control="number",
        default_value=default,
        display_order=order,
        validation=validation,
        warning_codes=warning_codes,
    )


def _number(
    title: str,
    description: str,
    category: str,
    default: str,
    order: int,
    *,
    minimum: float = 0,
    maximum: float | None = None,
    warning_codes: Iterable[str] = (),
) -> Dict[str, Any]:
    validation: Dict[str, Any] = {"min": minimum}
    if maximum is not None:
        validation["max"] = maximum
    return _field(
        title=title,
        description=description,
        category=category,
        data_type="number",
        ui_control="number",
        default_value=default,
        display_order=order,
        validation=validation,
        warning_codes=warning_codes,
    )


def _boolean(
    title: str,
    description: str,
    category: str,
    default: str,
    order: int,
) -> Dict[str, Any]:
    return _field(
        title=title,
        description=description,
        category=category,
        data_type="boolean",
        ui_control="switch",
        default_value=default,
        display_order=order,
    )


def _text(
    title: str,
    description: str,
    category: str,
    default: str,
    order: int,
    *,
    sensitive: bool = False,
    control: str = "text",
    warning_codes: Iterable[str] = (),
) -> Dict[str, Any]:
    return _field(
        title=title,
        description=description,
        category=category,
        data_type="string",
        ui_control="password" if sensitive else control,
        default_value=default,
        display_order=order,
        is_sensitive=sensitive,
        warning_codes=warning_codes,
    )


# Per-channel fields are owned by the Model Access editor.  Registering the
# built-in templates makes the documented inventory complete, while the service
# filters them to channels named by LLM_CHANNELS so dormant templates never
# flood the Settings response.
_LLM_CHANNEL_TEMPLATES: Dict[str, Dict[str, str]] = {
    "AIHUBMIX": {
        "PROVIDER": "aihubmix", "PROTOCOL": "openai",
        "BASE_URL": "https://aihubmix.com/v1", "API_KEY": "sk-xxx",
        "MODELS": "gpt-5.5,claude-sonnet-4-6,gemini-3.1-pro-preview",
    },
    "ANSPIRE": {
        "PROVIDER": "anspire", "PROTOCOL": "openai",
        "BASE_URL": "https://open-gateway.anspire.cn/v6 (example)",
        "API_KEY": "sk-xxx",
        "MODELS": "Doubao-Seed-2.0-lite,Doubao-Seed-2.0-pro (example models)",
    },
    "ANTHROPIC": {
        "PROVIDER": "anthropic", "PROTOCOL": "anthropic",
        "API_KEY": "sk-ant-xxx", "MODELS": "claude-sonnet-4-6,claude-opus-4-7",
    },
    "DASHSCOPE": {
        "PROVIDER": "dashscope", "PROTOCOL": "openai",
        "BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "API_KEY": "sk-xxx", "MODELS": "qwen3.6-plus,qwen3.6-flash",
    },
    "DEEPSEEK": {
        "PROVIDER": "deepseek", "PROTOCOL": "deepseek",
        "BASE_URL": "https://api.deepseek.com", "API_KEY": "sk-xxx",
        "MODELS": "deepseek-v4-flash,deepseek-v4-pro",
    },
    "GEMINI": {
        "PROVIDER": "gemini", "PROTOCOL": "gemini", "API_KEY": "xxx",
        "API_KEYS": "key1,key2",
        "MODELS": "gemini-3.1-pro-preview,gemini-3-flash-preview",
    },
    "HERMES": {
        "PROVIDER": "custom", "PROTOCOL": "openai",
        "BASE_URL": "http://127.0.0.1:8642/v1", "API_KEY": "sk-local-hermes",
        "MODELS": "hermes-agent",
    },
    "MIMO": {
        "PROVIDER": "custom", "PROTOCOL": "openai",
        "BASE_URL": "https://your-mimo-endpoint.example/v1", "API_KEY": "sk-xxx",
        "MODELS": "mimo-xxx",
    },
    "MINIMAX": {
        "PROVIDER": "minimax", "PROTOCOL": "openai",
        "BASE_URL": "https://api.minimax.io/v1", "API_KEY": "xxx",
        "MODELS": "MiniMax-M2.7,MiniMax-M2.7-highspeed",
    },
    "MOONSHOT": {
        "PROVIDER": "moonshot", "PROTOCOL": "openai",
        "BASE_URL": "https://api.moonshot.cn/v1", "API_KEY": "sk-xxx",
        "MODELS": "kimi-k2.6,kimi-k2.5",
    },
    "MY_PROXY": {
        "PROVIDER": "custom", "PROTOCOL": "openai",
        "BASE_URL": "https://your-proxy.example.com/v1", "API_KEY": "sk-xxx",
        "MODELS": "gpt-5.5,claude-sonnet-4-6",
    },
    "OLLAMA": {
        "PROVIDER": "ollama", "BASE_URL": "http://localhost:11434",
        "MODELS": "qwen3:8b,qwen3:4b",
    },
    "OPENAI": {
        "PROVIDER": "openai", "PROTOCOL": "openai",
        "BASE_URL": "https://api.openai.com/v1", "API_KEY": "sk-xxx",
        "MODELS": "gpt-5.5,gpt-5.4-mini",
    },
    "OPENROUTER": {
        "PROVIDER": "openrouter", "PROTOCOL": "openai",
        "BASE_URL": "https://openrouter.ai/api/v1", "API_KEY": "sk-or-xxx",
        "MODELS": "~anthropic/claude-sonnet-latest,~openai/gpt-latest",
    },
    "SILICONFLOW": {
        "PROVIDER": "siliconflow", "PROTOCOL": "openai",
        "BASE_URL": "https://api.siliconflow.cn/v1", "API_KEY": "sk-xxx",
        "MODELS": "deepseek-ai/DeepSeek-V3.2,Qwen/Qwen3-235B-A22B-Thinking-2507",
    },
    "VOLCENGINE": {
        "PROVIDER": "volcengine", "PROTOCOL": "openai",
        "BASE_URL": "https://ark.cn-beijing.volces.com/api/v3", "API_KEY": "xxx",
        "MODELS": "doubao-seed-1-6-251015,doubao-seed-1-6-thinking-251015",
    },
    "ZHIPU": {
        "PROVIDER": "zhipu", "PROTOCOL": "openai",
        "BASE_URL": "https://open.bigmodel.cn/api/paas/v4", "API_KEY": "xxx",
        "MODELS": "glm-5.1,glm-4.7-flash",
    },
}

_LLM_SUFFIX_METADATA = {
    "PROVIDER": ("Provider", "text", False),
    "PROTOCOL": ("Protocol", "text", False),
    "BASE_URL": ("Base URL", "text", False),
    "API_KEY": ("API Key", "password", True),
    "API_KEYS": ("API Keys", "password", True),
    "MODELS": ("Models", "textarea", False),
}

LLM_CHANNEL_INVENTORY_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {}
for _channel, _values in _LLM_CHANNEL_TEMPLATES.items():
    for _suffix, _default in _values.items():
        _label, _control, _sensitive = _LLM_SUFFIX_METADATA[_suffix]
        _key = f"LLM_{_channel}_{_suffix}"
        LLM_CHANNEL_INVENTORY_FIELD_DEFINITIONS[_key] = _field(
            title=f"{_channel.replace('_', ' ').title()} {_label}",
            description=f"Built-in {_channel.lower()} connection template {_label.lower()}.",
            category="ai_model",
            data_type="string",
            ui_control=_control,
            default_value=_default,
            display_order=800,
            is_sensitive=_sensitive,
            warning_codes=["secret_value"] if _sensitive else [],
        )
del _channel, _values, _suffix, _default, _label, _control, _sensitive, _key


INVENTORY_COMPLETION_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Data-source ordering, credentials, and resilience controls.
    "AKSHARE_PRIORITY": _integer("AkShare Priority", "Daily-data provider priority; lower values run earlier.", "data_source", "1", 700, maximum=99, warning_codes=["restart_required"]),
    "ALPHAVANTAGE_API_KEY": _text("AlphaVantage API Key", "Optional AlphaVantage credential for US market data.", "data_source", "", 701, sensitive=True),
    "BAOSTOCK_PRIORITY": _integer("Baostock Priority", "Daily-data provider priority; lower values run earlier.", "data_source", "3", 702, maximum=99, warning_codes=["restart_required"]),
    "EFINANCE_CALL_TIMEOUT": _integer("Efinance Call Timeout", "Maximum seconds allowed for one efinance call.", "data_source", "30", 703, minimum=1, warning_codes=["restart_required"]),
    "EFINANCE_PRIORITY": _integer("Efinance Priority", "Daily-data provider priority; lower values run earlier.", "data_source", "0", 704, maximum=99, warning_codes=["restart_required"]),
    "ENABLE_EASTMONEY_PATCH": _boolean("Enable Eastmoney Patch", "Add compatibility headers when Eastmoney connections are unstable.", "data_source", "false", 705),
    "FINNHUB_API_KEY": _text("Finnhub API Key", "Optional Finnhub credential for US market data.", "data_source", "", 706, sensitive=True),
    "INDUSTRY_PROVIDER": _field(title="Industry Provider", description="Optional industry and concept-board provider used by AlphaSift.", category="data_source", data_type="string", ui_control="select", default_value="none", display_order=707, options=["none", "akshare"], validation={"enum": ["none", "akshare"]}),
    "INDUSTRY_PROVIDER_MAX_BOARDS": _integer("Industry Provider Max Boards", "Maximum industry or concept boards loaded per refresh.", "data_source", "80", 708),
    "PREFETCH_REALTIME_QUOTES": _boolean("Prefetch Realtime Quotes", "Prefetch batch realtime quotes before per-symbol analysis.", "data_source", "true", 709),
    "PROVIDER_ADAPTIVE_PRIORITY_ENABLED": _boolean("Adaptive Provider Priority", "Reorder sufficiently sampled providers within equal static priority.", "data_source", "true", 710),
    "PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES": _integer("Adaptive Priority Min Samples", "Samples required before adaptive provider ordering.", "data_source", "3", 711, minimum=1),
    "PROVIDER_CIRCUIT_BREAKER_ENABLED": _boolean("Provider Circuit Breaker", "Temporarily skip repeatedly failing daily-data providers.", "data_source", "true", 712),
    "PROVIDER_CIRCUIT_COOLDOWN_SECONDS": _number("Provider Circuit Cooldown", "Seconds before a half-open provider probe.", "data_source", "300", 713),
    "PROVIDER_CIRCUIT_FAILURE_THRESHOLD": _integer("Provider Circuit Failure Threshold", "Consecutive failures required to open a provider circuit.", "data_source", "3", 714, minimum=1),
    "PROVIDER_DAILY_CACHE_ENABLED": _boolean("Provider Daily Cache", "Enable layered daily market-data caching.", "data_source", "true", 715),
    "PROVIDER_DAILY_CACHE_MEMORY_MAX_ENTRIES": _integer("Daily Cache Memory Entries", "Maximum in-memory daily-data cache entries.", "data_source", "256", 716, minimum=1),
    "PROVIDER_DAILY_CACHE_MEMORY_TTL_SECONDS": _number("Daily Cache Memory TTL", "Fresh lifetime in seconds for in-memory daily-data entries.", "data_source", "60", 717),
    "PROVIDER_DAILY_CACHE_PERSISTENT_TTL_SECONDS": _number("Daily Cache Persistent TTL", "Fresh lifetime in seconds for persistent daily-data entries.", "data_source", "3600", 718),
    "PROVIDER_DAILY_CACHE_STALE_IF_ERROR_SECONDS": _number("Daily Cache Stale If Error", "Additional seconds a stale entry may be used after provider failure.", "data_source", "86400", 719),
    "PROVIDER_HEALTH_WINDOW_SIZE": _integer("Provider Health Window Size", "Recent outcomes used for provider health scoring.", "data_source", "20", 720, minimum=1),
    "PYTDX_PRIORITY": _integer("Pytdx Priority", "Daily-data provider priority; lower values run earlier.", "data_source", "2", 721, maximum=99, warning_codes=["restart_required"]),
    "SNAPSHOT_SOURCE_PRIORITY": _text("Snapshot Source Priority", "Optional AlphaSift full-market snapshot override. Leave empty to derive the source order from configured credentials.", "data_source", "", 722),
    "SOCIAL_SENTIMENT_API_KEY": _text("Social Sentiment API Key", "Optional credential for US social-sentiment intelligence.", "data_source", "", 723, sensitive=True),
    "SOCIAL_SENTIMENT_API_URL": _text("Social Sentiment API URL", "Endpoint for optional social-sentiment intelligence.", "data_source", "https://api.adanos.org", 724),
    "TUSHARE_PRIORITY": _integer("Tushare Compatibility Priority", "Compatibility value; the runtime promotes an initialized Tushare provider to priority -1 and otherwise uses 2.", "data_source", "2", 725, maximum=99, warning_codes=["restart_required"]),
    "YFINANCE_PRIORITY": _integer("YFinance Priority", "Daily-data provider priority for eligible routes.", "data_source", "4", 726, maximum=99, warning_codes=["restart_required"]),

    # Longbridge user configuration. Endpoint overrides and cache tuning are
    # registered below as operator-only fields and filtered from Web Settings.
    "LONGBRIDGE_ACCESS_TOKEN": _text("Longbridge Access Token", "Legacy Longbridge access token.", "data_source", "", 740, sensitive=True),
    "LONGBRIDGE_APP_KEY": _text("Longbridge App Key", "Longbridge application key or OAuth compatibility client ID.", "data_source", "", 741, sensitive=True),
    "LONGBRIDGE_APP_SECRET": _text("Longbridge App Secret", "Longbridge application secret.", "data_source", "", 742, sensitive=True),
    "LONGBRIDGE_OAUTH_CLIENT_ID": _text("Longbridge OAuth Client ID", "Client ID for Longbridge OAuth authentication.", "data_source", "", 743),
    "LONGBRIDGE_OAUTH_TOKEN_CACHE_B64": _text("Longbridge OAuth Token Cache", "Base64-encoded Longbridge OAuth token cache.", "data_source", "", 744, sensitive=True),
    "LONGBRIDGE_ENABLE_OVERNIGHT": _boolean("Longbridge Overnight Trading", "Include overnight-session quotes when supported.", "data_source", "false", 745),
    "LONGBRIDGE_PRIORITY": _integer("Longbridge Priority", "Longbridge priority for eligible daily-data routes.", "data_source", "5", 746, maximum=99, warning_codes=["restart_required"]),
    "LONGBRIDGE_REGION": _field(title="Longbridge Region", description="Longbridge endpoint region.", category="data_source", data_type="string", ui_control="select", default_value="hk", display_order=747, options=["hk", "cn"], validation={"enum": ["hk", "cn"]}),
    "LONGBRIDGE_PUSH_CANDLESTICK_MODE": _field(title="Longbridge Candlestick Mode", description="Whether pushed candlesticks are realtime or confirmed.", category="data_source", data_type="string", ui_control="select", default_value="realtime", display_order=748, options=["realtime", "confirmed"], validation={"enum": ["realtime", "confirmed"]}),
    "LONGBRIDGE_PRINT_QUOTE_PACKAGES": _boolean("Log Longbridge Quote Packages", "Log detailed Longbridge quote packages for diagnostics.", "data_source", "false", 749),

    # Notification delivery and rendering limits.
    "DISCORD_MAX_WORDS": _integer("Discord Message Limit", "Maximum characters per Discord message before splitting.", "notification", "2000", 700, minimum=1),
    "FEISHU_MAX_BYTES": _integer("Feishu Message Byte Limit", "Maximum Feishu message bytes before splitting.", "notification", "20000", 701, minimum=1),
    "FEISHU_SEND_AS_FILE": _boolean("Send Feishu Reports As Files", "Send reports as files when using Feishu app-bot mode.", "notification", "false", 702),
    "MARKDOWN_TO_IMAGE_CHANNELS": _text("Markdown To Image Channels", "Comma-separated channels that receive image-rendered Markdown. Empty keeps image delivery disabled.", "notification", "", 703, control="textarea"),
    "MARKDOWN_TO_IMAGE_MAX_CHARS": _integer("Markdown To Image Max Characters", "Skip image rendering for reports above this character count.", "notification", "15000", 704, minimum=1),
    "MD2IMG_ENGINE": _field(title="Markdown Image Engine", description="Renderer used for Markdown-to-image delivery.", category="notification", data_type="string", ui_control="select", default_value="wkhtmltoimage", display_order=705, options=["wkhtmltoimage", "markdown-to-file", "playwright"], validation={"enum": ["wkhtmltoimage", "markdown-to-file", "playwright"]}),
    "WECHAT_MAX_BYTES": _integer("WeCom Message Byte Limit", "Maximum WeCom message bytes before splitting.", "notification", "4000", 706, minimum=1),

    # AI diagnostics not owned by a particular connection.
    "LITELLM_LOG_LEVEL": _field(title="LiteLLM Log Level", description="LiteLLM internal diagnostic log level.", category="ai_model", data_type="string", ui_control="select", default_value="WARNING", display_order=850, options=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], validation={"enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]}, warning_codes=["restart_required"]),

    # Explicit operator/bootstrap/path contracts. These are registered so type
    # and sensitivity are never inferred, then filtered by the Web hidden set.
    "ALLOW_INSECURE_PUBLIC_BIND": _boolean("Allow Insecure Public Bind", "Emergency-only unauthenticated public-bind override.", "system", "false", 900),
    "DATABASE_PATH": _text("Database Path", "SQLite database path selected at process startup.", "system", "./data/stock_analysis.db", 901, warning_codes=["restart_required", "path_must_be_writable"]),
    "DSA_WEB_DEV_API_PROXY": _text("Web Development API Proxy", "Vite-only backend proxy target for local frontend development.", "system", "http://127.0.0.1:8000", 902),
    "PLUGINS_DIR": _text("Plugins Directory", "Startup-only directory containing reviewed external plugins.", "system", "/absolute/path/to/reviewed/plugins", 903, warning_codes=["restart_required", "path_must_be_readable"]),
    "PLUGIN_STATE_PATH": _text("Plugin State Path", "Startup-only plugin lifecycle state file.", "system", "./data/plugin_lifecycle_state.json", 904, warning_codes=["restart_required", "path_must_be_writable"]),
    "SQLITE_BUSY_TIMEOUT_MS": _integer("SQLite Busy Timeout", "SQLite lock wait timeout in milliseconds.", "system", "5000", 905),
    "SQLITE_WAL_ENABLED": _boolean("SQLite WAL", "Enable SQLite write-ahead logging for file-backed databases.", "system", "true", 906),
    "SQLITE_WRITE_RETRY_BASE_DELAY": _number("SQLite Retry Base Delay", "Base delay in seconds for SQLite lock retries.", "system", "0.1", 907),
    "SQLITE_WRITE_RETRY_MAX": _integer("SQLite Write Retry Limit", "Maximum retries after SQLite lock errors.", "system", "3", 908),

    "ALPHASIFT_DAILY_CALL_TIMEOUT_SEC": _integer("AlphaSift Daily Call Timeout", "Operator timeout for AlphaSift daily-history calls.", "data_source", "20", 900),
    "SEARXNG_TIMEOUT_SECONDS": _integer(
        "SearXNG Self-Hosted Timeout",
        "Per-search timeout in seconds for self-hosted SearXNG instances. Public instances are unaffected.",
        "data_source",
        "10",
        915,
        minimum=1,
    ),
    "ALPHASIFT_DAILY_HISTORY_CACHE_DIR": _text("AlphaSift Daily History Cache", "Operator path for AlphaSift daily-history cache files.", "data_source", "data/alphasift/daily_history", 901),
    "ALPHASIFT_DATA_DIR": _text("AlphaSift Data Directory", "Operator path for AlphaSift runtime data.", "data_source", "data/alphasift", 902),
    "ALPHASIFT_EASTMONEY_JITTER_SEC": _number("AlphaSift Eastmoney Jitter", "Maximum request jitter in seconds for Eastmoney fallback calls.", "data_source", "0.3", 903),
    "ALPHASIFT_EASTMONEY_MIN_INTERVAL_SEC": _number("AlphaSift Eastmoney Minimum Interval", "Minimum seconds between Eastmoney fallback calls.", "data_source", "1.0", 904),
    "ALPHASIFT_FALLBACK_SNAPSHOT_PATH": _text("AlphaSift Fallback Snapshot", "Operator path for the last-good AlphaSift snapshot.", "data_source", "data/alphasift/snapshot.last_good.json", 905),
    "ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR": _text("AlphaSift Industry Cache", "Operator path for industry-provider cache files.", "data_source", "data/alphasift/industry_provider_cache", 906),
    "ALPHASIFT_SNAPSHOT_CALL_TIMEOUT_SEC": _integer("AlphaSift Snapshot Call Timeout", "Operator timeout for AlphaSift snapshot calls.", "data_source", "60", 907),
    "ALPHASIFT_SOURCE_CALL_TIMEOUT_SEC": _text("AlphaSift Source Call Timeout", "Optional global timeout or off token for wrapped provider calls.", "data_source", "", 908),
    "PROVIDER_DAILY_CACHE_DIR": _text("Provider Daily Cache Directory", "Operator path for persistent daily-data cache files.", "data_source", "data/provider_cache/daily", 909),
    "LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS": _integer("Longbridge Connection Cooldown", "Seconds to skip Longbridge after a connection-close failure.", "data_source", "15", 910),
    "LONGBRIDGE_HTTP_URL": _text("Longbridge HTTP URL", "Operator override for the Longbridge HTTP endpoint.", "data_source", "https://openapi.longbridge.com", 911),
    "LONGBRIDGE_QUOTE_WS_URL": _text("Longbridge Quote WebSocket URL", "Operator override for the Longbridge quote WebSocket endpoint.", "data_source", "wss://openapi-quote.longbridge.com/v2", 912),
    "LONGBRIDGE_STATIC_INFO_TTL_SECONDS": _integer("Longbridge Static Info TTL", "Process cache lifetime for Longbridge static security data.", "data_source", "86400", 913),
    "LONGBRIDGE_TRADE_WS_URL": _text("Longbridge Trade WebSocket URL", "Operator override for the Longbridge trade WebSocket endpoint.", "data_source", "wss://openapi-trade.longbridge.com/v2", 914),

    # Compatibility or indexed-group fields need dedicated workflows rather
    # than generic Settings controls and therefore remain API/env-only.
    "DISCORD_CHANNEL_ID": _text("Legacy Discord Channel ID", "Compatibility alias for DISCORD_MAIN_CHANNEL_ID.", "notification", "", 900),
    "EMAIL_GROUP_1": _text("Email Group 1", "Indexed recipient group paired with STOCK_GROUP_1.", "notification", "user1@example.com", 901, control="textarea"),
    "EMAIL_GROUP_2": _text("Email Group 2", "Indexed recipient group paired with STOCK_GROUP_2.", "notification", "user2@example.com", 902, control="textarea"),
    "OLLAMA_API_BASE": _text("Legacy Ollama API Base", "Compatibility alias for the channel-based Ollama connection.", "ai_model", "http://localhost:11434", 900),
    "SHARE_IMAGE_XIAOHONGSHU_HANDLE": _text("Xiaohongshu Share Handle", "Brand handle rendered into share images.", "notification", "", 910),
    "SHARE_IMAGE_XIAOHONGSHU_ID": _text("Xiaohongshu Share ID", "Brand identifier rendered into share images.", "notification", "", 911),
    "SHARE_IMAGE_XIAOHONGSHU_QR_PATH": _text("Xiaohongshu QR Image Path", "Operator path for the QR image rendered into share images.", "notification", "src/assets/share_image/xiaohongshu_qr.jpg", 912),
    "SHARE_IMAGE_XIAOHONGSHU_URL": _text("Xiaohongshu Share URL", "Profile URL encoded by the share-image QR code.", "notification", "", 913),
    "STOCK_GROUP_1": _text("Stock Group 1", "Indexed stock subset paired with EMAIL_GROUP_1.", "base", "600519,300750", 900, control="textarea"),
    "STOCK_GROUP_2": _text("Stock Group 2", "Indexed stock subset paired with EMAIL_GROUP_2.", "base", "002594,AAPL", 901, control="textarea"),
    **LLM_CHANNEL_INVENTORY_FIELD_DEFINITIONS,
}

_WEB_HELP_KEYS = frozenset({
    "AKSHARE_PRIORITY", "ALPHAVANTAGE_API_KEY", "BAOSTOCK_PRIORITY",
    "DISCORD_MAX_WORDS", "EFINANCE_CALL_TIMEOUT", "EFINANCE_PRIORITY",
    "ENABLE_EASTMONEY_PATCH", "FEISHU_MAX_BYTES", "FEISHU_SEND_AS_FILE",
    "FINNHUB_API_KEY", "INDUSTRY_PROVIDER", "INDUSTRY_PROVIDER_MAX_BOARDS",
    "LITELLM_LOG_LEVEL", "LONGBRIDGE_ACCESS_TOKEN", "LONGBRIDGE_APP_KEY",
    "LONGBRIDGE_APP_SECRET", "LONGBRIDGE_ENABLE_OVERNIGHT",
    "LONGBRIDGE_OAUTH_CLIENT_ID", "LONGBRIDGE_OAUTH_TOKEN_CACHE_B64",
    "LONGBRIDGE_PRINT_QUOTE_PACKAGES", "LONGBRIDGE_PRIORITY",
    "LONGBRIDGE_PUSH_CANDLESTICK_MODE", "LONGBRIDGE_REGION",
    "MARKDOWN_TO_IMAGE_CHANNELS", "MARKDOWN_TO_IMAGE_MAX_CHARS",
    "MD2IMG_ENGINE", "PREFETCH_REALTIME_QUOTES",
    "PROVIDER_ADAPTIVE_PRIORITY_ENABLED", "PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES",
    "PROVIDER_CIRCUIT_BREAKER_ENABLED", "PROVIDER_CIRCUIT_COOLDOWN_SECONDS",
    "PROVIDER_CIRCUIT_FAILURE_THRESHOLD", "PROVIDER_DAILY_CACHE_ENABLED",
    "PROVIDER_DAILY_CACHE_MEMORY_MAX_ENTRIES",
    "PROVIDER_DAILY_CACHE_MEMORY_TTL_SECONDS",
    "PROVIDER_DAILY_CACHE_PERSISTENT_TTL_SECONDS",
    "PROVIDER_DAILY_CACHE_STALE_IF_ERROR_SECONDS", "PROVIDER_HEALTH_WINDOW_SIZE",
    "PYTDX_PRIORITY", "SNAPSHOT_SOURCE_PRIORITY", "SOCIAL_SENTIMENT_API_KEY",
    "SOCIAL_SENTIMENT_API_URL", "TUSHARE_PRIORITY", "WECHAT_MAX_BYTES",
    "YFINANCE_PRIORITY",
})

for _inventory_key in _WEB_HELP_KEYS:
    _inventory_field = INVENTORY_COMPLETION_FIELD_DEFINITIONS[_inventory_key]
    _inventory_field.setdefault(
        "examples",
        [f"{_inventory_key}={_inventory_field.get('default_value', '')}"],
    )
    _inventory_field.setdefault(
        "docs",
        [
            {
                "label": "Environment variable reference",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/environment-variables_EN.md",
            }
        ],
    )
del _inventory_key, _inventory_field
