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
        "category": "uncategorized",
        "title": "Uncategorized",
        "description": "Keys not mapped in the field registry.",
        "display_order": 99,
    },
]

WEB_SETTINGS_HIDDEN_FROM_UI = {
    "DATABASE_PATH",
    "DINGTALK_WEBHOOK_URL",
    "DINGTALK_SECRET",
    "SQLITE_WAL_ENABLED",
    "SQLITE_BUSY_TIMEOUT_MS",
    "SQLITE_WRITE_RETRY_MAX",
    "SQLITE_WRITE_RETRY_BASE_DELAY",
    "USE_PROXY",
    "PROXY_HOST",
    "PROXY_PORT",
}
