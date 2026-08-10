"""System configuration field definitions."""

from typing import Any, Dict

SYSTEM_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "REPORT_EXPORT_PDF_FONT_PATH": {
        "title": "Report Export PDF Font Path",
        "description": (
            "Optional absolute path to one parseable TTF/OTF face used by PDF report export. "
            "An explicitly configured invalid path fails closed; it never falls back to another system font."
        ),
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"maxLength": 1024},
        "display_order": 9,
        "help_key": "settings.system.REPORT_EXPORT_PDF_FONT_PATH",
        "examples": [
            "REPORT_EXPORT_PDF_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
        ],
        "docs": [
            {
                "label": "Report export configuration and font readiness",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/report-export.md",
            },
        ],
        "warning_codes": ["restart_required", "path_must_exist"],
    },
    "SCHEDULE_TIME": {
        "title": "Schedule Time",
        "description": (
            "Deprecated legacy day-batch daily time (HH:MM). Prefer versioned scheduled tasks. Still supported for compatibility."
        ),
        "category": "system",
        "data_type": "time",
        "ui_control": "time",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "18:00",
        "options": [],
        "validation": {"pattern": r"^([01]\d|2[0-3]):[0-5]\d$"},
        "display_order": 10,
        "help_key": "settings.system.schedule",
        "examples": [
            "SCHEDULE_TIME=18:00",
            "SCHEDULE_ENABLED=true",
            "SCHEDULE_RUN_IMMEDIATELY=false",
        ],
        "docs": [
            {
                "label": "Scheduled tasks: legacy SCHEDULE day-batch deprecation",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/scheduled-tasks.md#legacy-schedule-day-batch-deprecation",
            },
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": ["local_timezone"],
        "deprecated": True,
        "replacement": (
            "versioned scheduled tasks (POST /api/v1/scheduled-tasks; Web Settings → Saved schedule definitions)"
        ),
    },
    "SCHEDULE_TIMES": {
        "title": "Schedule Times",
        "description": (
            "Deprecated legacy day-batch multi-time list (comma-separated HH:MM). Falls back to SCHEDULE_TIME when empty. Prefer versioned scheduled tasks."
        ),
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"pattern": r"^\s*(?:(?:[01]\d|2[0-3]):[0-5]\d\s*(?:,\s*(?:[01]\d|2[0-3]):[0-5]\d\s*)*)?$"},
        "display_order": 11,
        "help_key": "settings.system.schedule",
        "examples": [
            "SCHEDULE_TIMES=09:20,12:30,15:10,18:00",
            "SCHEDULE_TIME=18:00",
            "SCHEDULE_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Scheduled tasks: legacy SCHEDULE day-batch deprecation",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/scheduled-tasks.md#legacy-schedule-day-batch-deprecation",
            },
            {
                "label": "Full guide: configuration",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": ["local_timezone"],
        "deprecated": True,
        "replacement": (
            "versioned scheduled tasks (POST /api/v1/scheduled-tasks; Web Settings → Saved schedule definitions)"
        ),
    },
    "USE_PROXY": {
        "title": "Enable Local Proxy",
        "description": (
            "Mainland-friendly toggle that maps PROXY_HOST and PROXY_PORT onto "
            "process http_proxy/https_proxy at env bootstrap and config reload. "
            "GitHub Actions always skips this regardless of the value. "
            "A process restart is required for a full, reliable effect "
            "(including disabling a previously applied proxy and any long-lived "
            "HTTP clients that cached proxy settings)."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 17,
        "help_key": "settings.system.USE_PROXY",
        "examples": [
            "USE_PROXY=false",
            "USE_PROXY=true",
            "PROXY_HOST=127.0.0.1",
            "PROXY_PORT=10809",
        ],
        "docs": [
            {
                "label": "FAQ: configure proxy for Gemini/OpenAI",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/FAQ_EN.md#q7-how-to-configure-proxy-to-access-geminiopenai-api",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["restart_required", "network_scope"],
    },
    "PROXY_HOST": {
        "title": "Proxy Host",
        "description": (
            "Host (or user:pass@host) used when USE_PROXY=true to build "
            "http://{PROXY_HOST}:{PROXY_PORT}. May embed credentials; values are "
            "masked in Settings and redacted in diagnostics. Prefer host-only "
            "values when credentials are not required. Inside containers, "
            "127.0.0.1 points at the container, not the host machine. "
            "Requires process restart for full effect with USE_PROXY."
        ),
        "category": "system",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": "127.0.0.1",
        "options": [],
        "validation": {},
        "display_order": 18,
        "help_key": "settings.system.PROXY_HOST",
        "examples": [
            "PROXY_HOST=127.0.0.1",
            "PROXY_HOST=host.docker.internal",
        ],
        "docs": [
            {
                "label": "FAQ: configure proxy for Gemini/OpenAI",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/FAQ_EN.md#q7-how-to-configure-proxy-to-access-geminiopenai-api",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["restart_required", "secret_value", "network_scope"],
    },
    "PROXY_PORT": {
        "title": "Proxy Port",
        "description": (
            "Port used when USE_PROXY=true to build "
            "http://{PROXY_HOST}:{PROXY_PORT} (default 10809). "
            "Requires process restart for full effect with USE_PROXY."
        ),
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "10809",
        "options": [],
        "validation": {"min": 1, "max": 65535},
        "display_order": 19,
        "help_key": "settings.system.PROXY_PORT",
        "examples": [
            "PROXY_PORT=10809",
            "PROXY_PORT=7890",
        ],
        "docs": [
            {
                "label": "FAQ: configure proxy for Gemini/OpenAI",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/FAQ_EN.md#q7-how-to-configure-proxy-to-access-geminiopenai-api",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["restart_required", "network_scope"],
    },
    "HTTP_PROXY": {
        "title": "HTTP Proxy",
        "description": (
            "Optional standard HTTP proxy URL for outbound requests "
            "(data sources, LLM, search, notifications). Prefer this over "
            "USE_PROXY/PROXY_HOST/PROXY_PORT when libraries honor HTTP_PROXY. "
            "URL userinfo credentials are redacted in diagnostics; do not share "
            "export dumps that include them."
        ),
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 20,
        "help_key": "settings.system.HTTP_PROXY",
        "examples": [
            "HTTP_PROXY=http://127.0.0.1:7890",
            "HTTPS_PROXY=http://127.0.0.1:7890",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["network_scope"],
    },
    "LOG_LEVEL": {
        "title": "Log Level",
        "description": "Application log level.",
        "category": "system",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "INFO",
        "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        "validation": {"enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
        "display_order": 30,
        "help_key": "settings.system.LOG_LEVEL",
        "examples": [
            "LOG_LEVEL=INFO",
            "LOG_LEVEL=DEBUG",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "LOG_DIR": {
        "title": "Log Directory",
        "description": "Directory for application logs. The runtime user or container must be able to write to this path.",
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "./logs",
        "options": [],
        "validation": {},
        "display_order": 31,
        "help_key": "settings.system.LOG_DIR",
        "examples": [
            "LOG_DIR=./logs",
            "LOG_DIR=/app/logs",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["restart_required", "path_must_be_writable"],
    },
    "WEBUI_ENABLED": {
        "title": "Web UI Enabled",
        "description": "Startup-time compatibility flag for default WebUI/API service mode. Saving this setting does not start or stop the current process.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 37,
        "help_key": "settings.system.WEBUI_ENABLED",
        "examples": [
            "WEBUI_ENABLED=false",
            "WEBUI_ENABLED=true",
        ],
        "docs": [
            {
                "label": "完整指南：WebUI 与 API",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#webui-与-api-服务",
            },
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/deploy-webui-cloud.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "WEBUI_AUTO_BUILD": {
        "title": "Web UI Auto Build",
        "description": "Build or verify the Web frontend assets before backend WebUI startup. Disable only when assets are prebuilt.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 38,
        "help_key": "settings.system.WEBUI_AUTO_BUILD",
        "examples": [
            "WEBUI_AUTO_BUILD=true",
            "WEBUI_AUTO_BUILD=false",
        ],
        "docs": [
            {
                "label": "完整指南：WebUI 与 API",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#webui-与-api-服务",
            },
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/deploy-webui-cloud.md",
            },
        ],
        "warning_codes": ["restart_required", "requires_built_web_assets"],
    },
    "WEBUI_HOST": {
        "title": "Web UI Host",
        "description": "Host address for Web UI service binding.",
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "127.0.0.1",
        "options": [],
        "validation": {},
        "display_order": 39,
        "help_key": "settings.system.WEBUI_HOST",
        "examples": [
            "WEBUI_HOST=127.0.0.1",
            "WEBUI_HOST=0.0.0.0",
        ],
        "docs": [
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/deploy-webui-cloud.md",
            },
            {
                "label": "完整指南：WebUI 与 API",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#webui-与-api-服务",
            },
        ],
        "warning_codes": ["public_bind_requires_auth", "restart_required"],
    },
    "WEBUI_PORT": {
        "title": "Web UI Port",
        "description": "Port for Web UI service.",
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "8000",
        "options": [],
        "validation": {"min": 1, "max": 65535},
        "display_order": 40,
        "help_key": "settings.system.WEBUI_PORT",
        "examples": [
            "WEBUI_PORT=8000",
            "WEBUI_PORT=18000",
        ],
        "docs": [
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/deploy-webui-cloud.md",
            },
            {
                "label": "完整指南：WebUI 与 API",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#webui-与-api-服务",
            },
        ],
        "warning_codes": ["port_mapping_required", "restart_required"],
    },
    "RUN_IMMEDIATELY": {
        "title": "Run Immediately",
        "description": "Whether to run analysis immediately on startup (non-schedule mode).",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 45,
        "help_key": "settings.system.RUN_IMMEDIATELY",
        "examples": [
            "RUN_IMMEDIATELY=true",
            "RUN_IMMEDIATELY=false",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "SCHEDULE_ENABLED": {
        "title": "Schedule Enabled",
        "description": (
            "Deprecated legacy day-batch switch for whole-watchlist daily analysis. Prefer versioned scheduled tasks. Still supported for compatibility."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 8,
        "help_key": "settings.system.schedule",
        "examples": [
            "SCHEDULE_ENABLED=true",
            "SCHEDULE_TIME=18:00",
            "SCHEDULE_RUN_IMMEDIATELY=false",
        ],
        "docs": [
            {
                "label": "Scheduled tasks: legacy SCHEDULE day-batch deprecation",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/scheduled-tasks.md#legacy-schedule-day-batch-deprecation",
            },
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": ["restart_required"],
        "deprecated": True,
        "replacement": (
            "versioned scheduled tasks (POST /api/v1/scheduled-tasks; Web Settings → Saved schedule definitions)"
        ),
    },
    "LOCAL_ONLY_MODE": {
        "title": "Local Only Mode",
        "description": (
            "When enabled, the outbound HTTP policy fails closed for every non-loopback "
            "destination (public cloud APIs, private LAN hosts, and allowlisted remote "
            "services). Only pure loopback targets remain reachable. Blocked calls raise "
            "coded errors that name LOCAL_ONLY_MODE; they never silently fall through."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 40,
        "help_key": "settings.system.LOCAL_ONLY_MODE",
        "examples": ["LOCAL_ONLY_MODE=false", "LOCAL_ONLY_MODE=true"],
        "docs": [
            {"label": "Local Only mode (EN)", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/local-only-mode_EN.md"},
            {"label": "本地专用模式", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/local-only-mode.md"},
            {"label": "Outbound HTTP security policy", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/security-outbound-policy.md"},
        ],
        "warning_codes": ["restart_required", "network_scope", "local_only_blocks_cloud"],
    },
    "ADMIN_AUTH_ENABLED": {
        "title": "Admin Auth Enabled",
        "description": "Enable password protection for Web UI. The first visit initializes the admin password.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": False,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 41,
        "help_key": "settings.system.ADMIN_AUTH_ENABLED",
        "examples": [
            "ADMIN_AUTH_ENABLED=true",
            "python -m src.auth reset_password",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/deploy-webui-cloud.md",
            },
        ],
        "warning_codes": ["public_webui_requires_auth", "auth_settings_endpoint_required"],
    },
    "TRUST_X_FORWARDED_FOR": {
        "title": "Trust X-Forwarded-For",
        "description": "Use X-Forwarded-For as the client IP behind one trusted reverse proxy.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 42,
        "help_key": "settings.system.TRUST_X_FORWARDED_FOR",
        "examples": [
            "TRUST_X_FORWARDED_FOR=false",
            "TRUST_X_FORWARDED_FOR=true",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/deploy-webui-cloud.md",
            },
        ],
        "warning_codes": ["trusted_proxy_only"],
    },
    "SCHEDULE_RUN_IMMEDIATELY": {
        "title": "Schedule Run Immediately",
        "description": (
            "Deprecated legacy schedule-mode startup flag: run one analysis immediately when schedule mode starts. Prefer versioned scheduled tasks. Still supported."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 11,
        "help_key": "settings.system.schedule",
        "examples": [
            "SCHEDULE_RUN_IMMEDIATELY=true",
            "SCHEDULE_RUN_IMMEDIATELY=false",
        ],
        "docs": [
            {
                "label": "Scheduled tasks: legacy SCHEDULE day-batch deprecation",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/scheduled-tasks.md#legacy-schedule-day-batch-deprecation",
            },
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": ["restart_required"],
        "deprecated": True,
        "replacement": (
            "versioned scheduled tasks (POST /api/v1/scheduled-tasks; Web Settings → Saved schedule definitions)"
        ),
    },
    "TRADING_DAY_CHECK_ENABLED": {
        "title": "Trading Day Check",
        "description": "Skip analysis on non-trading days. Set to false or use --force-run to override.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 12,
        "help_key": "settings.system.TRADING_DAY_CHECK_ENABLED",
        "examples": [
            "TRADING_DAY_CHECK_ENABLED=true",
            "TRADING_DAY_CHECK_ENABLED=false",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": ["force_run_override"],
    },
    "MARKET_REVIEW_ENABLED": {
        "title": "Market Review Enabled",
        "description": "Enable market overview/review in analysis reports.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 46,
        "help_key": "settings.system.market_review",
        "examples": [
            "MARKET_REVIEW_ENABLED=true",
            "MARKET_REVIEW_REGION=cn",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "DAILY_MARKET_CONTEXT_ENABLED": {
        "title": "Daily Market Context Enabled",
        "description": "Inject daily market context into stock-analysis prompts and apply conservative decision guardrails.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 47,
        "help_key": "settings.system.market_review",
        "examples": [
            "DAILY_MARKET_CONTEXT_ENABLED=true",
            "DAILY_MARKET_CONTEXT_ENABLED=false",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "MARKET_REVIEW_REGION": {
        "title": "Market Review Region",
        "description": "Market region for review: cn (A-shares), hk (Hong Kong), us (US stocks), jp (Japan), kr (Korea), or both (all markets).",
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "cn",
        "options": ["cn", "hk", "us", "jp", "kr", "both"],
        "validation": {"allowed_values": ["cn", "hk", "us", "jp", "kr", "both"], "multi_value": True, "delimiter": ","},
        "display_order": 48,
        "help_key": "settings.system.market_review",
        "examples": [
            "MARKET_REVIEW_REGION=cn",
            "MARKET_REVIEW_REGION=jp",
            "MARKET_REVIEW_REGION=both",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "MARKET_REVIEW_COLOR_SCHEME": {
        "title": "Market Review Color Scheme",
        "description": "Index change color style in market-review tables: green_up (green for gains, red for losses) or red_up (red for gains, green for losses).",
        "category": "system",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "green_up",
        "options": [
            {"label": "Green Up / Red Down", "value": "green_up"},
            {"label": "Red Up / Green Down", "value": "red_up"},
        ],
        "validation": {"enum": ["green_up", "red_up"]},
        "display_order": 49,
        "help_key": "settings.system.market_review",
        "examples": [
            "MARKET_REVIEW_COLOR_SCHEME=green_up",
            "MARKET_REVIEW_COLOR_SCHEME=red_up",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "MAX_WORKERS": {
        "title": "Max Workers",
        "description": "Maximum concurrent analysis threads. Keep low to avoid API rate limits.",
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "3",
        "options": [],
        "validation": {"min": 1, "max": 20},
        "display_order": 50,
        "help_key": "settings.system.MAX_WORKERS",
        "examples": [
            "MAX_WORKERS=3",
            "MAX_WORKERS=5",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "ANALYSIS_DELAY": {
        "title": "Analysis Delay",
        "description": "Delay in seconds between individual stock analyses (for API rate limiting).",
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "options": [],
        "validation": {"min": 0, "max": 60},
        "display_order": 51,
        "help_key": "settings.system.ANALYSIS_DELAY",
        "examples": [
            "ANALYSIS_DELAY=0",
            "ANALYSIS_DELAY=5",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "SAVE_CONTEXT_SNAPSHOT": {
        "title": "Save Context Snapshot",
        "description": "Persist the full analysis_history.context_snapshot for history/API/Web transparency. Disable only to stop storing snapshots; it does not disable AnalysisContextPack prompt summaries during the current run.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 52,
        "help_key": "settings.system.SAVE_CONTEXT_SNAPSHOT",
        "examples": [
            "SAVE_CONTEXT_SNAPSHOT=true",
            "SAVE_CONTEXT_SNAPSHOT=false",
            "python main.py --no-context-snapshot",
        ],
        "docs": [
            {
                "label": "AnalysisContextPack P6 文档、迁移与回滚",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/analysis-context-pack.md#p6-文档迁移与回滚",
            },
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "DEBUG": {
        "title": "Debug Mode",
        "description": "Enable debug mode with verbose logging.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 55,
        "help_key": "settings.system.DEBUG",
        "examples": [
            "DEBUG=true",
            "DEBUG=false",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "SIGNAL_SCORECARD_PUBLIC_ENABLED": {
        "title": "Public Signal Scorecard",
        "description": (
            "Opt-in unauthenticated exposure of the aggregated signal scorecard at "
            "GET /api/v1/scorecard. Off by default so self-hosted deployments stay private; "
            "when enabled, only aggregate non-sensitive stats are returned (no per-symbol identity)."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 56,
        "help_key": "settings.system.scorecard",
        "examples": [
            "SIGNAL_SCORECARD_PUBLIC_ENABLED=false",
            "SIGNAL_SCORECARD_PUBLIC_ENABLED=true",
            "SIGNAL_SCORECARD_MIN_SAMPLES=10",
        ],
        "docs": [
            {
                "label": "Full guide: environment variables",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "SIGNAL_SCORECARD_MIN_SAMPLES": {
        "title": "Scorecard Min Samples",
        "description": (
            "Minimum decided samples (hit + miss) before a scorecard bucket shows a hit rate. "
            "Buckets below this threshold render as insufficient_data."
        ),
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "10",
        "options": [],
        "validation": {"min": 1, "max": 10000},
        "display_order": 57,
        "help_key": "settings.system.scorecard",
        "examples": [
            "SIGNAL_SCORECARD_MIN_SAMPLES=10",
            "SIGNAL_SCORECARD_MIN_SAMPLES=20",
        ],
        "docs": [
            {
                "label": "Full guide: environment variables",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "LOCAL_RUNTIME_AUTO_DETECT": {
        "title": "Local Runtime Auto-Detect",
        "description": (
            "When enabled (default), setup readiness performs a fast loopback-only probe for a "
            "running local generation runtime such as Ollama (127.0.0.0/8, ::1, localhost). "
            "Probe failures are log-only and never block startup. Disable to skip the probe."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 58,
        "help_key": "settings.system.LOCAL_RUNTIME_AUTO_DETECT",
        "examples": [
            "LOCAL_RUNTIME_AUTO_DETECT=true",
            "LOCAL_RUNTIME_AUTO_DETECT=false",
        ],
        "docs": [
            {
                "label": "Beginner client setup",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/beginner-client-setup_EN.md",
            },
            {
                "label": "LLM configuration guide",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/LLM_CONFIG_GUIDE_EN.md",
            },
        ],
        "warning_codes": [],
    },
    "LOCAL_RUNTIME_DETECT_TIMEOUT_SECONDS": {
        "title": "Local Runtime Detect Timeout",
        "description": (
            "Per-request timeout in seconds for the loopback local-runtime detect probe. "
            "Clamped to 0.05–2.0; keep low so setup status stays fast when Ollama is down."
        ),
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0.35",
        "options": [],
        "validation": {"min": 0.05, "max": 2.0},
        "display_order": 59,
        "help_key": "settings.system.LOCAL_RUNTIME_DETECT_TIMEOUT_SECONDS",
        "examples": [
            "LOCAL_RUNTIME_DETECT_TIMEOUT_SECONDS=0.35",
            "LOCAL_RUNTIME_DETECT_TIMEOUT_SECONDS=0.5",
        ],
        "docs": [
            {
                "label": "Beginner client setup",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/beginner-client-setup_EN.md",
            },
        ],
        "warning_codes": [],
    },

    "DAILY_BRIEF_ENABLED": {
        "title": "Daily Brief Enabled",
        "description": (
            "Opt-in daily brief that reviews historical prediction accuracy "
            "(decision-signal outcomes, backtest summary, skill-opinion performance) "
            "before summarizing yesterday's analyses and today's watchlist. "
            "Default off. Does not invent hit rates when history is insufficient."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 58,
        "help_key": "settings.system.daily_brief",
        "examples": [
            "DAILY_BRIEF_ENABLED=false",
            "DAILY_BRIEF_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Daily brief",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/daily-brief.md",
            },
        ],
        "warning_codes": [],
    },
    "DAILY_BRIEF_SCHEDULE_TIME": {
        "title": "Daily Brief Schedule Time",
        "description": (
            "Local wall-clock time (24-hour HH:MM) when the enabled daily brief may fire. "
            "The scheduler polls periodically and runs at most once per local calendar day "
            "after this time."
        ),
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "08:30",
        "options": [],
        "validation": {"pattern": r"^(?:[01]\d|2[0-3]):[0-5]\d$"},
        "display_order": 59,
        "help_key": "settings.system.daily_brief",
        "examples": [
            "DAILY_BRIEF_SCHEDULE_TIME=08:30",
            "DAILY_BRIEF_SCHEDULE_TIME=09:00",
        ],
        "docs": [
            {
                "label": "Daily brief",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/daily-brief.md",
            },
        ],
        "warning_codes": [],
    },
    "DAILY_BRIEF_TIMEZONE": {
        "title": "Daily Brief Timezone",
        "description": (
            "IANA timezone used for the daily brief schedule and for mapping "
            "analysis timestamps onto 'yesterday'. Defaults to Asia/Shanghai when unset "
            "or invalid."
        ),
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "Asia/Shanghai",
        "options": [],
        "validation": {},
        "display_order": 60,
        "help_key": "settings.system.daily_brief",
        "examples": [
            "DAILY_BRIEF_TIMEZONE=Asia/Shanghai",
            "DAILY_BRIEF_TIMEZONE=America/New_York",
        ],
        "docs": [
            {
                "label": "Daily brief",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/daily-brief.md",
            },
        ],
        "warning_codes": [],
    },
    "DAILY_BRIEF_MIN_SAMPLES": {
        "title": "Daily Brief Min Samples",
        "description": (
            "Minimum completed (hit+miss or backtest completed) samples before the brief "
            "publishes a percentage for a given accuracy source. Below this threshold the "
            "brief states insufficient history explicitly."
        ),
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "10",
        "options": [],
        "validation": {"min": 1, "max": 10000},
        "display_order": 61,
        "help_key": "settings.system.daily_brief",
        "examples": [
            "DAILY_BRIEF_MIN_SAMPLES=10",
            "DAILY_BRIEF_MIN_SAMPLES=20",
        ],
        "docs": [
            {
                "label": "Daily brief",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/daily-brief.md",
            },
        ],
        "warning_codes": [],
    },
    "PORTFOLIO_STRESS_SCENARIOS_PATH": {
        "title": "Portfolio Stress Scenario Catalog",
        "description": (
            "Optional local YAML file that adds or overrides bounded deterministic "
            "portfolio stress scenarios. The last validated catalog remains active "
            "when a later reload is invalid."
        ),
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"max_length": 1024},
        "display_order": 62,
        "help_key": "settings.system.PORTFOLIO_STRESS_SCENARIOS_PATH",
        "examples": ["PORTFOLIO_STRESS_SCENARIOS_PATH=./config/stress-scenarios.yaml"],
        "docs": [
            {
                "label": "Portfolio stress testing",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/portfolio-stress-test_EN.md",
            },
        ],
        "warning_codes": ["restart_required", "local_path"],
    },

    "DAILY_BRIEF_NOTIFY": {
        "title": "Daily Brief Notify",
        "description": (
            "When true, a completed daily brief may be pushed through the configured "
            "notification channels. Does not enable the brief itself."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 63,
        "help_key": "settings.system.daily_brief",
        "examples": ["DAILY_BRIEF_NOTIFY=true", "DAILY_BRIEF_NOTIFY=false"],
        "docs": [
            {
                "label": "Daily brief",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/daily-brief.md",
            },
        ],
        "warning_codes": [],
    },
    "DAILY_BRIEF_PERSIST_HISTORY": {
        "title": "Daily Brief Persist History",
        "description": (
            "When true, each daily brief is stored for later accuracy review and history panels."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 64,
        "help_key": "settings.system.daily_brief",
        "examples": [
            "DAILY_BRIEF_PERSIST_HISTORY=true",
            "DAILY_BRIEF_PERSIST_HISTORY=false",
        ],
        "docs": [
            {
                "label": "Daily brief",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/daily-brief.md",
            },
        ],
        "warning_codes": [],
    },
    "DAILY_BRIEF_SAVE_REPORT_FILE": {
        "title": "Daily Brief Save Report File",
        "description": (
            "When true, the brief also writes a report file under the configured report directory."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 65,
        "help_key": "settings.system.daily_brief",
        "examples": [
            "DAILY_BRIEF_SAVE_REPORT_FILE=true",
            "DAILY_BRIEF_SAVE_REPORT_FILE=false",
        ],
        "docs": [
            {
                "label": "Daily brief",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/daily-brief.md",
            },
        ],
        "warning_codes": [],
    },
    "ADMIN_SESSION_MAX_AGE_HOURS": {
        "title": "Admin Session Max Age (Hours)",
        "description": (
            "Maximum lifetime of an authenticated admin web session in hours. "
            "Range 1–720; default 24."
        ),
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "24",
        "options": [],
        "validation": {"min": 1, "max": 720},
        "display_order": 66,
        "help_key": "settings.system.ADMIN_SESSION_MAX_AGE_HOURS",
        "examples": ["ADMIN_SESSION_MAX_AGE_HOURS=24", "ADMIN_SESSION_MAX_AGE_HOURS=72"],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "OUTBOUND_HTTP_ALLOWLIST": {
        "title": "Outbound HTTP Allowlist",
        "description": (
            "Comma-separated host:port entries that may be reached by fail-closed outbound "
            "HTTP when the target is private or loopback. Public hosts do not need entries. "
            "Misconfiguration can block local Ollama, SearXNG, Hermes, or private plugins."
        ),
        "category": "system",
        "data_type": "string",
        "ui_control": "textarea",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"max_length": 4096},
        "display_order": 67,
        "help_key": "settings.system.OUTBOUND_HTTP_ALLOWLIST",
        "examples": [
            "OUTBOUND_HTTP_ALLOWLIST=127.0.0.1:8642,searxng.internal:8080",
            "OUTBOUND_HTTP_ALLOWLIST=192.168.1.100:11434",
        ],
        "docs": [
            {
                "label": "Outbound HTTP security policy",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/security-outbound-policy.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "PLUGIN_DATA_PROVIDER_AUTO_BIND": {
        "title": "Plugin Data Provider Auto-Bind",
        "description": (
            "When true, ApplicationServices fail-closed binds one complete plugin data-provider "
            "registry into the process data manager used by stock services and the primary "
            "analysis pipeline. Default false."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 68,
        "help_key": "settings.system.PLUGIN_DATA_PROVIDER_AUTO_BIND",
        "examples": [
            "PLUGIN_DATA_PROVIDER_AUTO_BIND=false",
            "PLUGIN_DATA_PROVIDER_AUTO_BIND=true",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "SMARTMONEY_ENABLED": {
        "title": "SmartMoney Money-Flow Enabled",
        "description": (
            "Default-off gate for SmartMoney money-flow tracking and optional analysis-context "
            "injection. When false, no extra SmartMoney network calls are made."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 69,
        "help_key": "settings.system.SMARTMONEY_ENABLED",
        "examples": ["SMARTMONEY_ENABLED=false", "SMARTMONEY_ENABLED=true"],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "ENABLE_FUNDAMENTAL_PIPELINE": {
        "title": "Enable Fundamental Pipeline",
        "description": (
            "Master switch for the fundamental-data stage of analysis. When false, fundamental "
            "fetch and enrichment are skipped without failing the rest of the pipeline."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 70,
        "help_key": "settings.system.fundamental_pipeline",
        "examples": [
            "ENABLE_FUNDAMENTAL_PIPELINE=true",
            "ENABLE_FUNDAMENTAL_PIPELINE=false",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "FUNDAMENTAL_STAGE_TIMEOUT_SECONDS": {
        "title": "Fundamental Stage Timeout (Seconds)",
        "description": (
            "Wall-clock budget for the fundamental pipeline stage. 0 disables the stage timeout. "
            "Default 8.0."
        ),
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "8.0",
        "options": [],
        "validation": {"min": 0.0, "max": 600.0},
        "display_order": 71,
        "help_key": "settings.system.fundamental_pipeline",
        "examples": [
            "FUNDAMENTAL_STAGE_TIMEOUT_SECONDS=8.0",
            "FUNDAMENTAL_STAGE_TIMEOUT_SECONDS=15",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "FUNDAMENTAL_FETCH_TIMEOUT_SECONDS": {
        "title": "Fundamental Fetch Timeout (Seconds)",
        "description": (
            "Per-fetch timeout for fundamental provider calls inside the stage. Default 8.0."
        ),
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "8.0",
        "options": [],
        "validation": {"min": 0.0, "max": 600.0},
        "display_order": 72,
        "help_key": "settings.system.fundamental_pipeline",
        "examples": [
            "FUNDAMENTAL_FETCH_TIMEOUT_SECONDS=8.0",
            "FUNDAMENTAL_FETCH_TIMEOUT_SECONDS=12",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "FUNDAMENTAL_RETRY_MAX": {
        "title": "Fundamental Retry Max",
        "description": "Maximum additional retries after a failed fundamental fetch. Default 1.",
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "1",
        "options": [],
        "validation": {"min": 0, "max": 10},
        "display_order": 73,
        "help_key": "settings.system.fundamental_pipeline",
        "examples": ["FUNDAMENTAL_RETRY_MAX=1", "FUNDAMENTAL_RETRY_MAX=0"],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "FUNDAMENTAL_CACHE_TTL_SECONDS": {
        "title": "Fundamental Cache TTL (Seconds)",
        "description": "In-process fundamental cache time-to-live in seconds. Default 120.",
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "120",
        "options": [],
        "validation": {"min": 0, "max": 86400},
        "display_order": 74,
        "help_key": "settings.system.fundamental_pipeline",
        "examples": [
            "FUNDAMENTAL_CACHE_TTL_SECONDS=120",
            "FUNDAMENTAL_CACHE_TTL_SECONDS=300",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "FUNDAMENTAL_CACHE_MAX_ENTRIES": {
        "title": "Fundamental Cache Max Entries",
        "description": "Maximum in-process fundamental cache entries. Default 256.",
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "256",
        "options": [],
        "validation": {"min": 1, "max": 10000},
        "display_order": 75,
        "help_key": "settings.system.fundamental_pipeline",
        "examples": [
            "FUNDAMENTAL_CACHE_MAX_ENTRIES=256",
            "FUNDAMENTAL_CACHE_MAX_ENTRIES=512",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS": {
        "title": "Portfolio Idempotency Replay Window (Days)",
        "description": (
            "How many days a portfolio mutation idempotency key remains eligible for safe replay. "
            "Range 1–3650; default 7."
        ),
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "7",
        "options": [],
        "validation": {"min": 1, "max": 3650},
        "display_order": 76,
        "help_key": "settings.system.PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS",
        "examples": [
            "PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS=7",
            "PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS=30",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT": {
        "title": "Portfolio Risk Concentration Alert (%)",
        "description": (
            "Single-position concentration percentage that raises a portfolio risk alert. "
            "Default 35.0."
        ),
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "35.0",
        "options": [],
        "validation": {"min": 0.0, "max": 100.0},
        "display_order": 77,
        "help_key": "settings.system.portfolio_risk",
        "examples": [
            "PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT=35.0",
            "PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT=25",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT": {
        "title": "Portfolio Risk Drawdown Alert (%)",
        "description": "Portfolio drawdown percentage that raises a risk alert. Default 15.0.",
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "15.0",
        "options": [],
        "validation": {"min": 0.0, "max": 100.0},
        "display_order": 78,
        "help_key": "settings.system.portfolio_risk",
        "examples": [
            "PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT=15.0",
            "PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT=20",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT": {
        "title": "Portfolio Risk Stop-Loss Alert (%)",
        "description": (
            "Per-position loss percentage that raises a stop-loss risk alert. Default 10.0."
        ),
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "10.0",
        "options": [],
        "validation": {"min": 0.0, "max": 100.0},
        "display_order": 79,
        "help_key": "settings.system.portfolio_risk",
        "examples": [
            "PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT=10.0",
            "PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT=8",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO": {
        "title": "Portfolio Risk Stop-Loss Near Ratio",
        "description": (
            "Fraction of the stop-loss threshold that counts as 'near stop-loss' for early "
            "warnings. Range [0, 1]; default 0.8."
        ),
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0.8",
        "options": [],
        "validation": {"min": 0.0, "max": 1.0},
        "display_order": 80,
        "help_key": "settings.system.portfolio_risk",
        "examples": [
            "PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO=0.8",
            "PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO=0.9",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "PORTFOLIO_RISK_LOOKBACK_DAYS": {
        "title": "Portfolio Risk Lookback Days",
        "description": (
            "Trading-day lookback window used by portfolio risk metrics such as drawdown. "
            "Default 180."
        ),
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "180",
        "options": [],
        "validation": {"min": 1, "max": 3650},
        "display_order": 81,
        "help_key": "settings.system.portfolio_risk",
        "examples": [
            "PORTFOLIO_RISK_LOOKBACK_DAYS=180",
            "PORTFOLIO_RISK_LOOKBACK_DAYS=90",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "PORTFOLIO_FX_UPDATE_ENABLED": {
        "title": "Portfolio FX Update Enabled",
        "description": (
            "When true, portfolio valuation may refresh FX rates for multi-currency holdings. "
            "Default true."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 82,
        "help_key": "settings.system.PORTFOLIO_FX_UPDATE_ENABLED",
        "examples": [
            "PORTFOLIO_FX_UPDATE_ENABLED=true",
            "PORTFOLIO_FX_UPDATE_ENABLED=false",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "NEWS_INTEL_RETENTION_DAYS": {
        "title": "News Intel Retention Days",
        "description": (
            "How many days local intelligence-pool items are retained. Range 1–365; default 30."
        ),
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "30",
        "options": [],
        "validation": {"min": 1, "max": 365},
        "display_order": 83,
        "help_key": "settings.system.news_intel",
        "examples": ["NEWS_INTEL_RETENTION_DAYS=30", "NEWS_INTEL_RETENTION_DAYS=14"],
        "docs": [
            {
                "label": "Intelligence sources",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/intelligence-sources.md",
            },
        ],
        "warning_codes": [],
    },
    "NEWS_INTEL_FETCH_TIMEOUT_SEC": {
        "title": "News Intel Fetch Timeout (Seconds)",
        "description": (
            "Per-source pull timeout for the local intelligence pool. Range 1–30; default 8."
        ),
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "8",
        "options": [],
        "validation": {"min": 1.0, "max": 30.0},
        "display_order": 84,
        "help_key": "settings.system.news_intel",
        "examples": ["NEWS_INTEL_FETCH_TIMEOUT_SEC=8", "NEWS_INTEL_FETCH_TIMEOUT_SEC=12"],
        "docs": [
            {
                "label": "Intelligence sources",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/intelligence-sources.md",
            },
        ],
        "warning_codes": [],
    },
    "NEWS_INTEL_MAX_ITEMS_PER_SOURCE": {
        "title": "News Intel Max Items Per Source",
        "description": (
            "Maximum items retained per intelligence source per fetch. Range 1–200; default 50."
        ),
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "50",
        "options": [],
        "validation": {"min": 1, "max": 200},
        "display_order": 85,
        "help_key": "settings.system.news_intel",
        "examples": [
            "NEWS_INTEL_MAX_ITEMS_PER_SOURCE=50",
            "NEWS_INTEL_MAX_ITEMS_PER_SOURCE=100",
        ],
        "docs": [
            {
                "label": "Intelligence sources",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/intelligence-sources.md",
            },
        ],
        "warning_codes": [],
    },
    "NEWS_INTEL_AUTO_FETCH_ENABLED": {
        "title": "News Intel Auto Fetch Enabled",
        "description": (
            "When true, the local intelligence pool may auto-fetch on schedule. Default false "
            "(opt-in). Workflow env-allowlists may still need an explicit mapping."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 86,
        "help_key": "settings.system.news_intel",
        "examples": [
            "NEWS_INTEL_AUTO_FETCH_ENABLED=false",
            "NEWS_INTEL_AUTO_FETCH_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Intelligence sources",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/intelligence-sources.md",
            },
        ],
        "warning_codes": [],
    },
    "NEWSNOW_BASE_URL": {
        "title": "NewsNow Base URL",
        "description": (
            "Base URL for the NewsNow-compatible intelligence feed adapter. Default "
            "https://newsnow.busiyi.world. Private hosts also need OUTBOUND_HTTP_ALLOWLIST."
        ),
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "https://newsnow.busiyi.world",
        "options": [],
        "validation": {"max_length": 1024},
        "display_order": 87,
        "help_key": "settings.system.news_intel",
        "examples": [
            "NEWSNOW_BASE_URL=https://newsnow.busiyi.world",
            "NEWSNOW_BASE_URL=http://127.0.0.1:3000",
        ],
        "docs": [
            {
                "label": "Intelligence sources",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/intelligence-sources.md",
            },
        ],
        "warning_codes": [],
    },
    "REASONING_TRACE_EXPORT_ENABLED": {
        "title": "Reasoning Trace Export Enabled",
        "description": (
            "Opt-in export of reasoning-trace artifacts for diagnostics. Default false; "
            "exports can be large and may contain analysis content."
        ),
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 88,
        "help_key": "settings.system.reasoning_trace_export",
        "examples": [
            "REASONING_TRACE_EXPORT_ENABLED=false",
            "REASONING_TRACE_EXPORT_ENABLED=true",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },
    "REASONING_TRACE_EXPORT_MAX_CHARS": {
        "title": "Reasoning Trace Export Max Chars",
        "description": (
            "Maximum characters retained when reasoning-trace export is enabled. "
            "Clamped to 10000–2000000; default 500000."
        ),
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "500000",
        "options": [],
        "validation": {"min": 10000, "max": 2000000},
        "display_order": 89,
        "help_key": "settings.system.reasoning_trace_export",
        "examples": [
            "REASONING_TRACE_EXPORT_MAX_CHARS=500000",
            "REASONING_TRACE_EXPORT_MAX_CHARS=100000",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": [],
    },

}


_PORTFOLIO_HEALTH_NUMBER_FIELDS = {
    "PORTFOLIO_HEALTH_WEIGHT_CONCENTRATION": (
        "Portfolio Health Concentration Weight", "0.25", 0.0, 1.0
    ),
    "PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE": (
        "Portfolio Health Risk Exposure Weight", "0.25", 0.0, 1.0
    ),
    "PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION": (
        "Portfolio Health Diversification Weight", "0.20", 0.0, 1.0
    ),
    "PORTFOLIO_HEALTH_WEIGHT_PNL": (
        "Portfolio Health PnL Weight", "0.15", 0.0, 1.0
    ),
    "PORTFOLIO_HEALTH_WEIGHT_CASH_RATIO": (
        "Portfolio Health Cash Ratio Weight", "0.15", 0.0, 1.0
    ),
    "PORTFOLIO_HEALTH_CONCENTRATION_ALERT_PCT": (
        "Portfolio Health Concentration Alert (%)", "35.0", 0.0, 100.0
    ),
    "PORTFOLIO_HEALTH_VAR_ALERT_PCT": (
        "Portfolio Health VaR Alert (%)", "5.0", 0.0, 100.0
    ),
    "PORTFOLIO_HEALTH_DIVERSIFICATION_ALERT": (
        "Portfolio Health Diversification Alert", "0.35", 0.0, 1.0
    ),
    "PORTFOLIO_HEALTH_CASH_LOW_ALERT_PCT": (
        "Portfolio Health Low Cash Alert (%)", "2.0", 0.0, 100.0
    ),
    "PORTFOLIO_HEALTH_CASH_HIGH_ALERT_PCT": (
        "Portfolio Health High Cash Alert (%)", "50.0", 0.0, 100.0
    ),
    "PORTFOLIO_HEALTH_PNL_LOSS_ALERT_PCT": (
        "Portfolio Health PnL Loss Alert (%)", "-15.0", -100.0, 0.0
    ),
}

for _offset, (_key, (_title, _default, _minimum, _maximum)) in enumerate(
    _PORTFOLIO_HEALTH_NUMBER_FIELDS.items(),
    start=0,
):
    SYSTEM_FIELD_DEFINITIONS[_key] = {
        "title": _title,
        "description": (
            "Finite portfolio-health formula configuration. Invalid, non-finite, "
            "or out-of-range values are rejected instead of clamped."
        ),
        "category": "system",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": _default,
        "options": [],
        "validation": {"min": _minimum, "max": _maximum},
        "display_order": 170 + _offset,
        "help_key": "settings.system.portfolio_health",
        "examples": [f"{_key}={_default}"],
        "docs": [
            {
                "label": "Portfolio health score",
                "href": (
                    "https://github.com/SiinXu/stock-pulse-ai/blob/main/"
                    "docs/portfolio-health-score_EN.md"
                ),
            }
        ],
        "warning_codes": [],
    }

del _offset, _key, _title, _default, _minimum, _maximum
