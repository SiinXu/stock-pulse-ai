"""Data-source configuration field definitions."""

from typing import Any, Dict

from src.config import DEFAULT_ALPHASIFT_INSTALL_SPEC

DATA_SOURCE_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "TUSHARE_TOKEN": {
        "title": "Tushare Token",
        "description": "Token for Tushare Pro API.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 10,
        "help_key": "settings.data_source.TUSHARE_TOKEN",
        "examples": [
            "TUSHARE_TOKEN=your_tushare_token",
        ],
        "docs": [
            {
                "label": "Tushare 股票列表指南",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/TUSHARE_STOCK_LIST_GUIDE.md",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "TUSHARE_HTTP_URL": {
        "title": "Tushare Pro API URL",
        "description": (
            "Optional Tushare Pro endpoint for self-hosted nodes, proxies, or "
            "internal mirrors. Leave empty to use http://api.tushare.pro. "
            "Private hosts must also be allowed by OUTBOUND_HTTP_ALLOWLIST."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {
            "item_type": "url",
            "allowed_schemes": ["http", "https"],
        },
        "display_order": 11,
        "help_key": "settings.data_source.TUSHARE_HTTP_URL",
        "examples": [
            "TUSHARE_HTTP_URL=https://tushare.example.com",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
            {
                "label": "出站 HTTP 安全策略",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/security-outbound-policy.md",
            },
        ],
    },
    "TICKFLOW_API_KEY": {
        "title": "TickFlow API Key",
        "description": "API key for optional TickFlow A-share daily K-lines, realtime quotes, stock list/name lookup, and market review enhancement. Permission failures fail open to existing providers.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 15,
    },
    "TICKFLOW_PRIORITY": {
        "title": "TickFlow Daily K-line Priority",
        "description": "Priority for TickFlow daily K-line fetcher. Lower numbers are tried earlier; realtime quote order is controlled separately by REALTIME_SOURCE_PRIORITY.",
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "2",
        "options": [],
        "validation": {"min": 0, "max": 99},
        "display_order": 16,
    },
    "TENCENT_PRIORITY": {
        "title": "Tencent Daily K-line Priority",
        "description": (
            "Priority for Tencent direct daily K-line fetcher. Lower numbers are "
            "tried earlier; default 5 keeps Tencent as the final built-in A-share "
            "fallback. Realtime quote order is controlled separately by "
            "REALTIME_SOURCE_PRIORITY."
        ),
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "5",
        "options": [],
        "validation": {"min": 0, "max": 99},
        "display_order": 16,
    },
    "TICKFLOW_KLINE_ADJUST": {
        "title": "TickFlow K-line Adjust",
        "description": "Adjustment mode for TickFlow daily K-lines. Default none preserves the existing unadjusted technical-indicator baseline.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "none",
        "options": ["none", "forward", "backward", "forward_additive", "backward_additive"],
        "validation": {},
        "display_order": 17,
    },
    "TICKFLOW_BATCH_DAILY_ENABLED": {
        "title": "TickFlow Batch Daily Enabled",
        "description": "Enable TickFlow batch daily K-line prefetch when the current plan allows it. Permission failures fail open and fall back to per-stock providers.",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 18,
    },
    "TICKFLOW_BATCH_SIZE": {
        "title": "TickFlow Batch Size",
        "description": "Maximum symbols per TickFlow batch request for daily K-lines and realtime quotes.",
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "100",
        "options": [],
        "validation": {"min": 1, "max": 500},
        "display_order": 19,
    },
    "STOCK_INDEX_REMOTE_UPDATE_ENABLED": {
        "title": "Remote Stock Index Updates",
        "description": "Automatically refresh the local stock autocomplete index from the built-in GitHub main source.",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 16,
        "help_key": "settings.data_source.stock_index_remote",
        "examples": [
            "STOCK_INDEX_REMOTE_UPDATE_ENABLED=true",
            "STOCK_INDEX_REMOTE_UPDATE_ENABLED=false",
        ],
        "docs": [
            {
                "label": "Tushare 股票列表指南",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/TUSHARE_STOCK_LIST_GUIDE.md",
            },
        ],
        "warning_codes": [],
    },
    "ALPHASIFT_ENABLED": {
        "title": "AlphaSift Screening",
        "description": "Enable the built-in AlphaSift stock screening tab. Disabled by default. This switch only affects the AlphaSift screening path; it does not migrate, sanitize, or clear existing LLM/runtime fields in `.env`.",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 17,
        "help_key": "settings.data_source.ALPHASIFT_ENABLED",
        "examples": [
            "ALPHASIFT_ENABLED=false",
            "ALPHASIFT_ENABLED=true",
        ],
        "docs": [
            {
                "label": "LiteLLM Providers（官方）",
                "href": "https://docs.litellm.ai/docs/providers",
            },
            {
                "label": "LiteLLM OpenAI-compatible（官方）",
                "href": "https://docs.litellm.ai/docs/providers/openai_compatible",
            },
            {
                "label": "OpenAI 请求与鉴权（官方）",
                "href": "https://platform.openai.com/docs/api-reference/authentication",
            },
            {
                "label": "AlphaSift 集成说明",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/alphasift-integration.md",
            },
        ],
    },
    "ALPHASIFT_INSTALL_SPEC": {
        "title": "AlphaSift Install Spec",
        "description": "Pinned AlphaSift pip source used for explicit repair installs and source verification. It is not used for normal runtime calls after startup dependency installation; runtime compatibility is built from StockPulse's resolved LLM/runtime context.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": DEFAULT_ALPHASIFT_INSTALL_SPEC,
        "options": [],
        "validation": {},
        "display_order": 18,
        "help_key": "settings.data_source.ALPHASIFT_INSTALL_SPEC",
        "examples": [
            f"ALPHASIFT_INSTALL_SPEC={DEFAULT_ALPHASIFT_INSTALL_SPEC}",
        ],
        "docs": [
            {
                "label": "requirements.txt（版本与依赖边界）",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/requirements.txt",
            },
            {
                "label": "AlphaSift 集成说明",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/alphasift-integration.md",
            },
        ],
    },
    "REALTIME_SOURCE_PRIORITY": {
        "title": "Realtime Source Priority",
        "description": "Ordered priority for realtime quote providers; earlier entries are tried first.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "tencent,akshare_sina,efinance,akshare_em",
        # No allowed_values on purpose: stored aliases (e.g. akshare_qq) and
        # custom sources must keep validating; the UI only offers the catalog.
        "options": [
            {"label": "tencent", "value": "tencent"},
            {"label": "akshare_sina", "value": "akshare_sina"},
            {"label": "efinance", "value": "efinance"},
            {"label": "akshare_em", "value": "akshare_em"},
            {"label": "tushare", "value": "tushare"},
            {"label": "tickflow", "value": "tickflow"},
        ],
        "validation": {"multi_value": True, "delimiter": ",", "ordered": True},
        "display_order": 20,
        "help_key": "settings.data_source.REALTIME_SOURCE_PRIORITY",
        "examples": [
            "REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em",
        ],
        "docs": [
            {
                "label": "完整指南：数据源配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#数据源配置",
            },
        ],
        "warning_codes": ["provider_priority_order"],
    },
    "ENABLE_REALTIME_TECHNICAL_INDICATORS": {
        "title": "Realtime Technical Indicators",
        "description": "Use intraday realtime price for MA5/MA10/MA20 and trend analysis (Issue #234). Disable to use yesterday close.",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 21,
        "help_key": "settings.data_source.realtime_quotes",
        "examples": [
            "ENABLE_REALTIME_TECHNICAL_INDICATORS=true",
            "ENABLE_REALTIME_TECHNICAL_INDICATORS=false",
        ],
        "docs": [
            {
                "label": "完整指南：数据源配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#数据源配置",
            },
        ],
        "warning_codes": [],
    },
    "ANSPIRE_API_KEYS": {
        "title": "Anspire API Keys",
        "description": "Comma-separated Anspire Open API keys. Used by Anspire Search and, by default, the Anspire OpenAI-compatible LLM gateway.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 22,
        "help_key": "settings.data_source.search_api_keys",
        "examples": [
            "ANSPIRE_API_KEYS=key1,key2",
        ],
        "docs": [
            {
                "label": "完整指南：搜索服务配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#搜索服务配置",
            },
        ],
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "TAVILY_API_KEYS": {
        "title": "Tavily API Keys",
        "description": "Comma-separated Tavily API keys.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 30,
        "help_key": "settings.data_source.search_api_keys",
        "examples": [
            "TAVILY_API_KEYS=tvly-xxxx",
            "TAVILY_API_KEYS=tvly-key-1,tvly-key-2",
        ],
        "docs": [
            {
                "label": "完整指南：搜索服务配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#搜索服务配置",
            },
        ],
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "SERPAPI_API_KEYS": {
        "title": "SerpAPI Keys",
        "description": "Comma-separated SerpAPI keys.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 40,
    },
    "BRAVE_API_KEYS": {
        "title": "Brave API Keys",
        "description": "Comma-separated Brave Search API keys.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 50,
    },
    "BOCHA_API_KEYS": {
        "title": "Bocha API Keys",
        "description": "Comma-separated Bocha Search API keys.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 51,
    },
    "MINIMAX_API_KEYS": {
        "title": "MiniMax API Key",
        "description": "MiniMax API key (search priority: Bocha > Tavily > Brave > SerpAPI > MiniMax > SearXNG).",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 53,
    },
    "SEARXNG_BASE_URLS": {
        "title": "SearXNG Base URLs",
        "description": "Comma-separated SearXNG instance URLs (self-hosted, no quota). Enable format: json in settings.yml.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {
            "multi_value": True,
            "delimiter": ",",
            "item_type": "url",
            "allowed_schemes": ["http", "https"],
        },
        "display_order": 52,
        "help_key": "settings.data_source.SEARXNG_BASE_URLS",
        "examples": [
            "SEARXNG_BASE_URLS=https://search.example.com",
            "SEARXNG_PUBLIC_INSTANCES_ENABLED=false",
        ],
        "docs": [
            {
                "label": "完整指南：搜索服务配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#搜索服务配置",
            },
        ],
        "warning_codes": ["requires_json_format"],
    },
    "SEARXNG_PUBLIC_INSTANCES_ENABLED": {
        "title": "SearXNG Public Instances",
        "description": "Auto-discover public SearXNG instances from searx.space when SEARXNG_BASE_URLS is empty. Default: true; set false to disable.",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 53,
    },
    "RSS_NEWS_FEED_URLS": {
        "title": "RSS/Atom News Feed URLs",
        "description": (
            "Optional comma-separated RSS or Atom feed URLs used as a free "
            "supplement in the on-demand news search pipeline (not a replacement "
            "for SearXNG or paid search). Empty keeps the feature inert. Feed "
            "fetching uses the fail-closed outbound policy; private/loopback hosts "
            "require an exact OUTBOUND_HTTP_ALLOWLIST entry."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {
            "multi_value": True,
            "delimiter": ",",
            "item_type": "url",
            "allowed_schemes": ["http", "https"],
        },
        "display_order": 54,
        "help_key": "settings.data_source.RSS_NEWS_FEED_URLS",
        "examples": [
            "RSS_NEWS_FEED_URLS=https://www.sec.gov/news/pressreleases.rss",
        ],
        "docs": [
            {
                "label": "完整指南：搜索服务配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#搜索服务配置",
            },
            {
                "label": "出站 HTTP 安全策略",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/security-outbound-policy.md",
            },
        ],
    },
    "RSS_NEWS_FETCH_TIMEOUT_SEC": {
        "title": "RSS/Atom Feed Fetch Timeout",
        "description": (
            "Per-feed timeout in seconds for on-demand RSS/Atom news search "
            "(1-30). Default 8. Independent of NEWS_INTEL_FETCH_TIMEOUT_SEC."
        ),
        "category": "data_source",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "8",
        "options": [],
        "validation": {"min": 1, "max": 30},
        "display_order": 55,
        "help_key": "settings.data_source.RSS_NEWS_FEED_URLS",
        "examples": [
            "RSS_NEWS_FETCH_TIMEOUT_SEC=8",
        ],
        "docs": [
            {
                "label": "完整指南：搜索服务配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#搜索服务配置",
            },
        ],
    },
    "ENABLE_REALTIME_QUOTE": {
        "title": "Enable Realtime Quote",
        "description": "Enable realtime market quotes. Disable to only use historical close prices.",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 22,
        "help_key": "settings.data_source.realtime_quotes",
        "examples": [
            "ENABLE_REALTIME_QUOTE=true",
            "ENABLE_REALTIME_QUOTE=false",
        ],
        "docs": [
            {
                "label": "完整指南：数据源配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#数据源配置",
            },
        ],
        "warning_codes": [],
    },
    "ENABLE_CHIP_DISTRIBUTION": {
        "title": "Enable Chip Distribution",
        "description": "Enable chip distribution analysis. May be unstable; recommended to disable on cloud deployments.",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 23,
        "help_key": "settings.data_source.ENABLE_CHIP_DISTRIBUTION",
        "examples": [
            "ENABLE_CHIP_DISTRIBUTION=true",
            "ENABLE_CHIP_DISTRIBUTION=false",
        ],
        "docs": [
            {
                "label": "完整指南：数据源配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#数据源配置",
            },
        ],
        "warning_codes": ["cloud_deployments_may_disable"],
    },
    "NEWS_MAX_AGE_DAYS": {
        "title": "News Max Age (Days)",
        "description": "Maximum age of news in days. Older articles are excluded from analysis context.",
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "3",
        "options": [],
        "validation": {"min": 1, "max": 30},
        "display_order": 60,
        "help_key": "settings.data_source.news_window",
        "examples": [
            "NEWS_MAX_AGE_DAYS=3",
            "NEWS_STRATEGY_PROFILE=short",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "NEWS_STRATEGY_PROFILE": {
        "title": "News Strategy Profile",
        "description": "News window profile: ultra_short(1d), short(3d), medium(7d), long(30d). Effective window = min(profile, NEWS_MAX_AGE_DAYS).",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "short",
        "options": ["ultra_short", "short", "medium", "long"],
        "validation": {"enum": ["ultra_short", "short", "medium", "long"]},
        "display_order": 61,
        "help_key": "settings.data_source.news_window",
        "examples": [
            "NEWS_STRATEGY_PROFILE=short",
            "NEWS_MAX_AGE_DAYS=3",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "BIAS_THRESHOLD": {
        "title": "Bias Threshold (%)",
        "description": "Deviation threshold from MA5 (%). Exceeding this triggers 'do not chase' warning. Strong trend stocks auto-widen to 1.5x.",
        "category": "data_source",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "5.0",
        "options": [],
        "validation": {"min": 0.0, "max": 50.0},
        "display_order": 62,
    },
    "PYTDX_HOST": {
        "title": "Pytdx Host",
        "description": "Tongdaxin data server IP. Used with PYTDX_PORT. Overrides built-in defaults.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 55,
    },
    "PYTDX_PORT": {
        "title": "Pytdx Port",
        "description": "Tongdaxin data server port (e.g. 7709). Used with PYTDX_HOST.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 56,
    },
    "PYTDX_SERVERS": {
        "title": "Pytdx Servers",
        "description": "Comma-separated ip:port (e.g. 192.168.1.1:7709,10.0.0.1:7709). Overrides PYTDX_HOST+PYTDX_PORT.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 57,
    },

    "FUTU_OPEND_HOST": {
        "title": "Futu OpenD Host",
        "description": (
            "IPv4 host for the local Futu OpenD gateway used by --portfolio futu and "
            "portfolio Futu position import. Default 127.0.0.1. OpenD uses a local TCP "
            "protocol (not HTTP); loopback or a trusted LAN address is expected, "
            "matching other local-runtime gateways such as Pytdx."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "127.0.0.1",
        "options": [],
        "validation": {},
        "display_order": 70,
        "help_key": "settings.data_source.FUTU_OPEND_HOST",
        "examples": [
            "FUTU_OPEND_HOST=127.0.0.1",
            "FUTU_OPEND_HOST=192.168.1.20",
        ],
        "docs": [
            {
                "label": "Futu OpenD portfolio import",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/futu-opend-portfolio-import_EN.md",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
    },
    "FUTU_OPEND_PORT": {
        "title": "Futu OpenD Port",
        "description": "TCP port for the Futu OpenD gateway. Default 11111.",
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "11111",
        "options": [],
        "validation": {"min": 1, "max": 65535},
        "display_order": 71,
        "help_key": "settings.data_source.FUTU_OPEND_PORT",
        "examples": [
            "FUTU_OPEND_PORT=11111",
        ],
        "docs": [
            {
                "label": "Futu OpenD portfolio import",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/futu-opend-portfolio-import_EN.md",
            },
        ],
    },
    "FUTU_ACC_ID": {
        "title": "Futu Account ID",
        "description": (
            "Optional live securities account ID. Leave empty to merge eligible "
            "ACTIVE REAL NORMAL/MASTER accounts."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 72,
        "help_key": "settings.data_source.FUTU_ACC_ID",
        "examples": [
            "FUTU_ACC_ID=",
            "FUTU_ACC_ID=1001",
        ],
        "docs": [
            {
                "label": "Futu OpenD portfolio import",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/futu-opend-portfolio-import_EN.md",
            },
        ],
    },
    "FUTU_SECURITY_FIRM": {
        "title": "Futu Security Firm",
        "description": (
            "Futu SecurityFirm enum name. NONE uses SDK auto-detection. "
            "Common values include FUTUSECURITIES and FUTUSG."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "NONE",
        "options": [],
        "validation": {},
        "display_order": 73,
        "help_key": "settings.data_source.FUTU_SECURITY_FIRM",
        "examples": [
            "FUTU_SECURITY_FIRM=NONE",
            "FUTU_SECURITY_FIRM=FUTUSECURITIES",
        ],
        "docs": [
            {
                "label": "Futu OpenD portfolio import",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/futu-opend-portfolio-import_EN.md",
            },
        ],
    },

    # --- Cryptocurrency market data (CoinGecko; default off) ---
    "CRYPTO_PROVIDER_ENABLED": {
        "title": "Enable Crypto Provider",
        "description": (
            "When true, newly created production data managers register the "
            "CoinGecko crypto provider for crypto:TICKER identities. Default "
            "false leaves equity paths unchanged. See docs/crypto-market-support.md."
        ),
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 80,
        "help_key": "settings.data_source.CRYPTO_PROVIDER_ENABLED",
        "examples": [
            "CRYPTO_PROVIDER_ENABLED=false",
            "CRYPTO_PROVIDER_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Cryptocurrency market support",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/crypto-market-support.md",
            },
        ],
    },
    "COINGECKO_API_PLAN": {
        "title": "CoinGecko API Plan",
        "description": (
            "Authentication mode for CoinGecko: keyless (public, no key), demo "
            "(demo key + official public origin), or pro (pro key + pro origin). "
            "Invalid values fall back to keyless at load time."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "keyless",
        "options": ["keyless", "demo", "pro"],
        "validation": {"enum": ["keyless", "demo", "pro"]},
        "display_order": 81,
        "help_key": "settings.data_source.COINGECKO_API_PLAN",
        "examples": [
            "COINGECKO_API_PLAN=keyless",
            "COINGECKO_API_PLAN=demo",
            "COINGECKO_API_PLAN=pro",
        ],
        "docs": [
            {
                "label": "Cryptocurrency market support",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/crypto-market-support.md",
            },
        ],
    },
    "COINGECKO_API_KEY": {
        "title": "CoinGecko API Key",
        "description": (
            "Optional CoinGecko Demo or Pro API key. Leave empty in keyless mode. "
            "Credentials are never sent to custom COINGECKO_API_BASE origins."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 82,
        "help_key": "settings.data_source.COINGECKO_API_KEY",
        "examples": [
            "COINGECKO_API_KEY=",
            "COINGECKO_API_KEY=CG-xxxxxxxx",
        ],
        "docs": [
            {
                "label": "Cryptocurrency market support",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/crypto-market-support.md",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "COINGECKO_API_BASE": {
        "title": "CoinGecko API Base URL",
        "description": (
            "Optional custom HTTPS base for CoinGecko in keyless mode only. "
            "Demo and Pro always use official origins; credentials are never "
            "sent to a custom base."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {
            "item_type": "url",
            "allowed_schemes": ["https"],
        },
        "display_order": 83,
        "help_key": "settings.data_source.COINGECKO_API_BASE",
        "examples": [
            "COINGECKO_API_BASE=",
            "COINGECKO_API_BASE=https://api.coingecko.com/api/v3",
        ],
        "docs": [
            {
                "label": "Cryptocurrency market support",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/crypto-market-support.md",
            },
            {
                "label": "出站 HTTP 安全策略",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/security-outbound-policy.md",
            },
        ],
    },
    "CRYPTO_COINGECKO_PRIORITY": {
        "title": "CoinGecko Crypto Provider Priority",
        "description": (
            "Priority for the CoinGecko crypto market-data provider among "
            "crypto-market sources. Lower numbers are tried earlier. Default 10. "
            "Does not reorder equity daily or realtime providers."
        ),
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "10",
        "options": [],
        "validation": {"min": 0, "max": 99},
        "display_order": 84,
        "help_key": "settings.data_source.CRYPTO_COINGECKO_PRIORITY",
        "examples": [
            "CRYPTO_COINGECKO_PRIORITY=10",
        ],
        "docs": [
            {
                "label": "Cryptocurrency market support",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/crypto-market-support.md",
            },
        ],
    },
    "PROVIDER_MARKET_DATA_MODE": {
        "title": "Provider Market Data Mode",
        "description": (
            "Manager-level daily-data policy: auto (fresh local, then provider "
            "chain, then eligible stale), local_only (complete local range only; "
            "never enters provider/socket paths), or refresh (skip local read, "
            "run provider chain once). Empty or unset defaults to auto. Invalid "
            "values fail closed at configuration load. Independent of "
            "LOCAL_ONLY_MODE (process-wide outbound HTTP gate)."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "auto",
        "options": ["auto", "local_only", "refresh"],
        "validation": {"enum": ["auto", "local_only", "refresh"]},
        "display_order": 85,
        "help_key": "settings.data_source.PROVIDER_MARKET_DATA_MODE",
        "examples": [
            "PROVIDER_MARKET_DATA_MODE=auto",
            "PROVIDER_MARKET_DATA_MODE=local_only",
            "PROVIDER_MARKET_DATA_MODE=refresh",
        ],
        "docs": [
            {
                "label": "Local-first market data",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/local-first-market-data_EN.md",
            },
        ],
    },
    "PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS": {
        "title": "Local-Only Cache Max Age",
        "description": (
            "Maximum age in seconds of a complete local daily-cache entry that "
            "local_only mode may still serve. Older complete entries are treated "
            "as structured offline misses. Default 2592000 (30 days). Must be "
            "greater than zero."
        ),
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "2592000",
        "unit": "s",
        "options": [],
        "validation": {"min": 1, "max": 315360000},
        "display_order": 86,
        "help_key": "settings.data_source.PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS",
        "examples": [
            "PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS=2592000",
        ],
        "docs": [
            {
                "label": "Local-first market data",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/local-first-market-data_EN.md",
            },
        ],
    },
    "PROVIDER_DAILY_CACHE_PERSISTENT_MAX_AGE_SECONDS": {
        "title": "Persistent Daily Cache Max Age",
        "description": (
            "Delete persistent daily-cache files older than this age in seconds "
            "on read and write. Default 7776000 (90 days). Set 0 to disable "
            "age-based deletion."
        ),
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "7776000",
        "unit": "s",
        "options": [],
        "validation": {"min": 0, "max": 315360000},
        "display_order": 87,
        "help_key": "settings.data_source.PROVIDER_DAILY_CACHE_PERSISTENT_MAX_AGE_SECONDS",
        "examples": [
            "PROVIDER_DAILY_CACHE_PERSISTENT_MAX_AGE_SECONDS=7776000",
        ],
        "docs": [
            {
                "label": "Local-first market data",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/local-first-market-data_EN.md",
            },
        ],
    },
    "PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES": {
        "title": "Persistent Daily Cache Max Entries",
        "description": (
            "Maximum number of persistent daily-cache entries retained. Oldest "
            "entries are removed first; equal timestamps break ties by filename. "
            "Default 512."
        ),
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "512",
        "options": [],
        "validation": {"min": 1, "max": 100000},
        "display_order": 88,
        "help_key": "settings.data_source.PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES",
        "examples": [
            "PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES=512",
        ],
        "docs": [
            {
                "label": "Local-first market data",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/local-first-market-data_EN.md",
            },
        ],
    },
    "PROVIDER_DAILY_CACHE_ROLLOVER_GRACE_DAYS": {
        "title": "Daily Cache Rollover Grace Days",
        "description": (
            "Allow reuse of a covered local daily range across this many "
            "calendar-day default-end-date rollovers. Default 1. Must be at "
            "least 1."
        ),
        "category": "data_source",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "1",
        "unit": "d",
        "options": [],
        "validation": {"min": 1, "max": 30},
        "display_order": 89,
        "help_key": "settings.data_source.PROVIDER_DAILY_CACHE_ROLLOVER_GRACE_DAYS",
        "examples": [
            "PROVIDER_DAILY_CACHE_ROLLOVER_GRACE_DAYS=1",
        ],
        "docs": [
            {
                "label": "Local-first market data",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/local-first-market-data_EN.md",
            },
        ],
    },
    "DATA_VALIDATION_ENABLED": {
        "title": "Enable Data Validation",
        "description": (
            "Run the unified numeric contract for daily, realtime, fundamental, "
            "and selected technical fields, and emit versioned diagnostic "
            "evidence. Default true (warn-oriented). Set false to disable the "
            "validation layer."
        ),
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 90,
        "help_key": "settings.data_source.DATA_VALIDATION_ENABLED",
        "examples": [
            "DATA_VALIDATION_ENABLED=true",
            "DATA_VALIDATION_ENABLED=false",
        ],
        "docs": [
            {
                "label": "Data validation layer",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/data-validation-layer.md",
            },
        ],
    },
    "DATA_VALIDATION_STRICT": {
        "title": "Data Validation Strict Mode",
        "description": (
            "When true, reject provider candidates with reject-severity findings "
            "before acceptance or cache so the existing bounded fallback loop "
            "can try the next source. Default false."
        ),
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 91,
        "help_key": "settings.data_source.DATA_VALIDATION_STRICT",
        "examples": [
            "DATA_VALIDATION_STRICT=false",
            "DATA_VALIDATION_STRICT=true",
        ],
        "docs": [
            {
                "label": "Data validation layer",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/data-validation-layer.md",
            },
        ],
    },
    "DATA_VALIDATION_STRICT_SCOPES": {
        "title": "Data Validation Strict Scopes",
        "description": (
            "Comma-separated market/instrument selectors that apply strict mode, "
            "for example cn/equity,hk/etf,us/index. Supported instruments include "
            "equity, etf, and index. * is a wildcard. Default */*."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "*/*",
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 92,
        "help_key": "settings.data_source.DATA_VALIDATION_STRICT_SCOPES",
        "examples": [
            "DATA_VALIDATION_STRICT_SCOPES=*/*",
            "DATA_VALIDATION_STRICT_SCOPES=cn/equity,hk/etf,us/index",
        ],
        "docs": [
            {
                "label": "Data validation layer",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/data-validation-layer.md",
            },
        ],
    },
    "DATA_VALIDATION_INSTRUMENT_OVERRIDES": {
        "title": "Data Validation Instrument Overrides",
        "description": (
            "Comma-separated authoritative SYMBOL=instrument identities for "
            "offshore symbols whose ETF/index type cannot be inferred safely "
            "from the market code alone, for example SPY=etf,HK02800=etf,1306.T=etf. "
            "Empty leaves classification to built-in rules."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "textarea",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 93,
        "help_key": "settings.data_source.DATA_VALIDATION_INSTRUMENT_OVERRIDES",
        "examples": [
            "DATA_VALIDATION_INSTRUMENT_OVERRIDES=",
            "DATA_VALIDATION_INSTRUMENT_OVERRIDES=SPY=etf,HK02800=etf,1306.T=etf",
        ],
        "docs": [
            {
                "label": "Data validation layer",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/data-validation-layer.md",
            },
        ],
    },
    "DATA_VALIDATION_UPPER_LAYER_MODE": {
        "title": "Data Validation Upper-Layer Mode",
        "description": (
            "Final aggregated-fundamental policy: warn keeps the result and "
            "records evidence; reject raises explicitly at that upper boundary. "
            "This is not provider failover. Default warn. Other values normalize "
            "to warn at load time."
        ),
        "category": "data_source",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "warn",
        "options": ["warn", "reject"],
        "validation": {"enum": ["warn", "reject"]},
        "display_order": 94,
        "help_key": "settings.data_source.DATA_VALIDATION_UPPER_LAYER_MODE",
        "examples": [
            "DATA_VALIDATION_UPPER_LAYER_MODE=warn",
            "DATA_VALIDATION_UPPER_LAYER_MODE=reject",
        ],
        "docs": [
            {
                "label": "Data validation layer",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/data-validation-layer.md",
            },
        ],
    },

}
