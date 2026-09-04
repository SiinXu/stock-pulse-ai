"""Category and visibility metadata for the configuration registry."""

from typing import Any, Dict, List

_CATEGORY_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "category": "base",
        "title": "Base Settings",
        "description": "Watchlist and foundational application settings.",
        "display_order": 10,
    },
    {
        "category": "ai_model",
        "title": "AI Model",
        "description": "Model providers, model names, and inference parameters.",
        "display_order": 20,
    },
    {
        "category": "data_source",
        "title": "Data Source",
        "description": "Market data provider credentials and priority settings.",
        "display_order": 30,
    },
    {
        "category": "notification",
        "title": "Notification",
        "description": "Bot, webhook, and push channel related settings.",
        "display_order": 40,
    },
    {
        "category": "system",
        "title": "System",
        "description": "Runtime and scheduling controls.",
        "display_order": 50,
    },
    {
        "category": "agent",
        "title": "Agent",
        "description": "Agent mode and strategy-skill settings.",
        "display_order": 55,
    },
    {
        "category": "backtest",
        "title": "Backtest",
        "description": "Backtest engine behavior and evaluation parameters.",
        "display_order": 60,
    },
    {
        "category": "indicators",
        "title": "Technical Indicators",
        "description": "Configurable moving-average, MACD, and RSI periods for trend analysis.",
        "display_order": 65,
    },
    {
        "category": "mcp",
        "title": "MCP Server",
        "description": (
            "Optional Model Context Protocol process settings. Default off; "
            "HTTP transport is a security-sensitive external surface."
        ),
        "display_order": 70,
    },
    {
        "category": "uncategorized",
        "title": "Uncategorized",
        "description": "Keys not mapped in the field registry.",
        "display_order": 99,
    },
]

WEB_SETTINGS_HIDDEN_FROM_UI = {
    "ALLOW_INSECURE_PUBLIC_BIND",
    "DATABASE_PATH",
    "SQLITE_WAL_ENABLED",
    "SQLITE_BUSY_TIMEOUT_MS",
    "SQLITE_WRITE_RETRY_MAX",
    "SQLITE_WRITE_RETRY_BASE_DELAY",
    # Startup, operator path, and development-only configuration is explicit in
    # the registry but intentionally unavailable to the browser settings form.
    "DSA_WEB_DEV_API_PROXY",
    "PLUGINS_DIR",
    "PLUGIN_STATE_PATH",
    "ALPHASIFT_DAILY_CALL_TIMEOUT_SEC",
    "SEARXNG_TIMEOUT_SECONDS",
    "ALPHASIFT_DAILY_HISTORY_CACHE_DIR",
    "ALPHASIFT_DATA_DIR",
    "ALPHASIFT_EASTMONEY_JITTER_SEC",
    "ALPHASIFT_EASTMONEY_MIN_INTERVAL_SEC",
    "ALPHASIFT_FALLBACK_SNAPSHOT_PATH",
    "ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR",
    "ALPHASIFT_SNAPSHOT_CALL_TIMEOUT_SEC",
    "ALPHASIFT_SOURCE_CALL_TIMEOUT_SEC",
    "PROVIDER_DAILY_CACHE_DIR",
    "LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS",
    "LONGBRIDGE_HTTP_URL",
    "LONGBRIDGE_QUOTE_WS_URL",
    "LONGBRIDGE_STATIC_INFO_TTL_SECONDS",
    "LONGBRIDGE_TRADE_WS_URL",
    # Compatibility aliases and indexed workflows require dedicated editors.
    "DISCORD_CHANNEL_ID",
    "EMAIL_GROUP_1",
    "EMAIL_GROUP_2",
    "OLLAMA_API_BASE",
    "SHARE_IMAGE_XIAOHONGSHU_HANDLE",
    "SHARE_IMAGE_XIAOHONGSHU_ID",
    "SHARE_IMAGE_XIAOHONGSHU_QR_PATH",
    "SHARE_IMAGE_XIAOHONGSHU_URL",
    "STOCK_GROUP_1",
    "STOCK_GROUP_2",
    # The instance promotes configured Tushare to -1 and otherwise fixes it at
    # 2, so the documented compatibility value is not an effective Web control.
    "TUSHARE_PRIORITY",
    # Advanced resolver backpressure tuning remains environment-managed. The
    # primary enable/interval/batch/lease/attempt controls stay Web-editable.
    "PREDICTION_RESOLVE_FETCH_CONCURRENCY",
    "PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK",
    "PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_THRESHOLD",
    "PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_COOLDOWN_SECONDS",
    "PREDICTION_RESOLVE_CIRCUIT_OPEN_MAX_PER_TICK",
    "PREDICTION_RESOLVE_RETRY_JITTER_RATIO",
    # USE_PROXY / PROXY_HOST / PROXY_PORT are Web-editable (system network
    # section). Previously hidden as low-frequency ops keys applied only at
    # process bootstrap; remain restart-gated via warning_codes + field help.
}
