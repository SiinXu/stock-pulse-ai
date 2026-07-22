"""Dataclass model for the public :mod:`src.config` facade."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.config_parts import loading as _loading_module
from src.config_parts import parsers as _parsers_module
from src.config_parts.binding import (
    bind_wrapped_function,
    clone_descriptor,
    clone_function,
    replace_closure_reference,
)
from src.config_parts.defaults import (
    AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE,
    AGENT_MAX_STEPS_DEFAULT,
    DEFAULT_ALPHASIFT_INSTALL_SPEC,
    FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
    PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT,
)
from src.config_parts.llm import _ConfigLLMMethods
from src.config_parts.loading import _ConfigLoadingMethods
from src.config_parts.parsers import normalize_agent_context_compression_profile
from src.config_parts.runtime import _ConfigRuntimeMethods
from src.config_parts.validation import _ConfigValidationMethods
from src.llm.backend_registry import AUTO_AGENT_BACKEND_ID, LITELLM_BACKEND_ID
from src.llm.local_cli_backend import (
    DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY,
    DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
    DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES,
    DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS,
)


@dataclass
class Config:
    """
    系统配置类 - 单例模式
\x20\x20\x20\x20
    设计说明：
    - 使用 dataclass 简化配置属性定义
    - 所有配置项从环境变量读取，支持默认值
    - 类方法 get_instance() 实现单例访问
    """

    # Watchlist Stocks Configuration
    stock_list: List[str] = field(default_factory=list)

    # === Feishu Cloud Document Configuration ===
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    feishu_folder_token: Optional[str] = None  # Target folder Token

    # === Data source API Token ===
    tushare_token: Optional[str] = None
    tickflow_api_key: Optional[str] = None
    tickflow_kline_adjust: str = "none"
    tickflow_priority: int = 2
    tickflow_batch_daily_enabled: bool = True
    tickflow_batch_size: int = 100
    finnhub_api_key: Optional[str] = None
    alphavantage_api_key: Optional[str] = None
    longbridge_app_key: Optional[str] = None
    longbridge_app_secret: Optional[str] = None
    longbridge_access_token: Optional[str] = None
    longbridge_oauth_client_id: Optional[str] = None
    stock_index_remote_update_enabled: bool = True

    # === AlphaSift optional stock screening integration ===
    alphasift_enabled: bool = False
    alphasift_install_spec: str = DEFAULT_ALPHASIFT_INSTALL_SPEC

    # == AI Analysis Configuration ===
    generation_backend: str = LITELLM_BACKEND_ID
    generation_fallback_backend: str = LITELLM_BACKEND_ID
    generation_backend_timeout_seconds: int = DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS
    generation_backend_max_output_bytes: int = DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES
    generation_backend_max_concurrency: int = DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY
    local_cli_backend_max_concurrency: int = DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY
    opencode_cli_model: str = ""
    # LiteLLM unified model config (provider/model format, e.g. gemini/gemini-3.1-pro-preview)
    litellm_model: str = ""  # Primary model; must include provider prefix when set explicitly
    litellm_fallback_models: List[str] = field(default_factory=list)  # Cross-model fallback list

    # Unified temperature for all LLM calls (LLM_TEMPERATURE); legacy per-provider temps are fallback only
    llm_temperature: float = 0.7

    # Provider prompt-cache controls. These do not control provider implicit cache.
    llm_prompt_cache_telemetry_enabled: bool = True
    llm_prompt_cache_hints_enabled: bool = False
    llm_prompt_cache_diagnostics_level: str = "off"

    # --- Multi-channel LLM config (new) ---
    # LITELLM_CONFIG: path to a standard litellm_config.yaml file (most powerful)
    litellm_config_path: Optional[str] = None
    # LLM_CONFIG_MODE: auto|channels|yaml|legacy. "auto" keeps the historical
    # YAML > Channels > legacy precedence; the others force a single source.
    llm_config_mode: str = "auto"
    # Internal metadata: which config layer actually produced llm_model_list
    llm_models_source: str = "legacy_env"
    # LLM_CHANNELS: list of channel dicts, each with name/base_url/api_keys/models
    llm_channels: List[Dict[str, Any]] = field(default_factory=list)
    # Raw channel names requested through LLM_CHANNELS, including channels that
    # were skipped during parsing because required channel fields were missing.
    llm_channel_names: List[str] = field(default_factory=list)
    # Structured parse issues raised while turning LLM_CHANNELS into deployments.
    llm_channel_config_issues: List[Dict[str, str]] = field(default_factory=list)
    # True when invalid explicit channel config must prevent legacy key inference.
    llm_blocks_legacy_fallback: bool = False
    # Canonical Hermes route names that were requested but blocked by atomic parse issues.
    llm_blocked_hermes_routes: List[str] = field(default_factory=list)
    # Pre-built LiteLLM Router model_list (populated from channels, YAML, or legacy keys)
    llm_model_list: List[Dict[str, Any]] = field(default_factory=list)

    # Multi-key support: each list is parsed from *_API_KEYS (comma-separated) with single-key fallback
    gemini_api_keys: List[str] = field(default_factory=list)
    anthropic_api_keys: List[str] = field(default_factory=list)
    openai_api_keys: List[str] = field(default_factory=list)
    deepseek_api_keys: List[str] = field(default_factory=list)

    # Legacy single-key fields (kept for backward compatibility; gemini_api_keys[0] when set)
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.1-pro-preview"  # Main Model
    gemini_model_fallback: str = "gemini-3-flash-preview"  # Alternative model
    gemini_temperature: float = 0.7  # Temperature parameter (0.0-2.0, controls output randomness, default 0.7)

    # Gemini API Request Configuration (to prevent 429 rate limiting)
    gemini_request_delay: float = 2.0  # Request interval (seconds)
    gemini_max_retries: int = 5  # Maximum retry attempts
    gemini_retry_delay: float = 5.0  # Retry base delay (seconds)

    # Anthropic Claude API (backup, use when Gemini is unavailable)
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"  # Claude model name
    anthropic_temperature: float = 0.7  # Anthropic temperature (0.0-1.0, default 0.7)
    anthropic_max_tokens: int = 8192  # Max tokens for Anthropic responses

    # OpenAI compatible API (fallback when Gemini/Anthropic are unavailable)
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None  # e.g., https://api.openai.com/v1
    openai_model: str = "gpt-5.5"  # OpenAI compatible model name
    openai_vision_model: Optional[str] = None  # Deprecated: use VISION_MODEL instead
    openai_temperature: float = 0.7  # OpenAI temperature parameter (0.0-2.0, default 0.7)

    # === Vision Configuration ===
    # VISION_MODEL: litellm model string used for image understanding calls.
    # Fallback chain: VISION_MODEL → OPENAI_VISION_MODEL → gemini/gemini-2.0-flash
    vision_model: str = ""
    # VISION_PROVIDER_PRIORITY: comma-separated provider order for Vision fallback.
    vision_provider_priority: str = "gemini,anthropic,openai"

    # === Search Engine Configuration (Supports multi-Key Load Balancing) ===
    anspire_api_keys: List[str] = field(default_factory=list)  # Anspire Search API Keys
    bocha_api_keys: List[str] = field(default_factory=list)  # Bocha API Keys
    minimax_api_keys: List[str] = field(default_factory=list)  # MiniMax API Keys
    tavily_api_keys: List[str] = field(default_factory=list)  # Tavily API Keys
    brave_api_keys: List[str] = field(default_factory=list)  # Brave Search API Keys
    serpapi_keys: List[str] = field(default_factory=list)  # SerpAPI Keys
    searxng_base_urls: List[str] = field(default_factory=list)  # SearXNG instance URLs (self-hosted, no quota)
    searxng_public_instances_enabled: bool = True  # Auto-discover public SearXNG instances when base URLs are absent

    # === Social Sentiment (US stocks only, api.adanos.org) ===
    social_sentiment_api_key: Optional[str] = None
    social_sentiment_api_url: str = "https://api.adanos.org"

    # News and Analysis Filtering Configuration
    news_max_age_days: int = 3   # Maximum news timeliness (days)
    news_strategy_profile: str = "short"  # News window strategy positions: ultra_short/short/medium/long
    news_intel_retention_days: int = 30  # Local news pool retention period
    news_intel_fetch_timeout_sec: float = 8.0  # Single feed source pull timeout
    news_intel_max_items_per_source: int = 50  # Maximum number of items collected from each information source per request
    news_intel_auto_fetch_enabled: bool = False  # Automatically initialize and pull local news sources before analysis
    newsnow_base_url: str = "https://newsnow.busiyi.world"  # NewsNow HTTP API base URL (Source side data, Does Not Affect LLM/provider base URL)
    bias_threshold: float = 5.0  # Standard deviation threshold (%), prompts not to chase highs if exceeded.

    # == Agent Mode Configuration ===
    agent_generation_backend: str = AUTO_AGENT_BACKEND_ID
    agent_litellm_model: str = ""  # Optional Agent-only primary model; empty inherits LITELLM_MODEL
    agent_mode: bool = False
    _agent_mode_explicit: bool = False  # True when AGENT_MODE was explicitly set in env
    agent_max_steps: int = AGENT_MAX_STEPS_DEFAULT
    agent_skills: List[str] = field(default_factory=list)
    agent_skill_dir: Optional[str] = None
    agent_nl_routing: bool = False  # Enable natural language routing in bot dispatcher
    agent_arch: str = "single"     # Agent architecture: 'single' (legacy) or 'multi' (orchestrator)
    agent_orchestrator_mode: str = "standard"  # Orchestrator mode: quick/standard/full/specialist
    agent_orchestrator_timeout_s: int = 600  # Cooperative timeout budget for the whole multi-agent pipeline
    agent_technical_agent_timeout_s: float = 0
    agent_intel_agent_timeout_s: float = 0
    agent_risk_agent_timeout_s: float = 0
    agent_decision_agent_timeout_s: float = 0
    agent_portfolio_agent_timeout_s: float = 0
    agent_skill_agent_timeout_s: float = 0
    agent_risk_override: bool = True  # Allow risk agent to veto buy signals
    agent_deep_research_budget: int = 30000  # Max token budget for deep research
    agent_deep_research_timeout: int = 180  # Max seconds for /research command before returning timeout
    agent_memory_enabled: bool = False  # Enable memory & calibration system
    agent_skill_autoweight: bool = True  # Auto-weight skills by backtest performance
    agent_skill_routing: str = "auto"  # Skill routing: 'auto' (regime-based) or 'manual'
    agent_context_compression_enabled: bool = False  # Compress visible chat history before Agent calls
    agent_context_compression_profile: str = AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE
    agent_context_compression_trigger_tokens: int = 12000
    agent_context_protected_turns: int = 4
    agent_event_monitor_enabled: bool = False  # Enable periodic event-driven alert checks in schedule mode
    agent_event_monitor_interval_minutes: int = 5  # Polling interval for event monitor background checks
    agent_event_alert_rules_json: str = ""  # JSON array of serialized EventMonitor rules

    # === Notification Configuration (Can configure multiple, all push) ===

    # WeCom Webhook
    wechat_webhook_url: Optional[str] = None

    # Feishu Webhook
    feishu_webhook_url: Optional[str] = None
    feishu_webhook_secret: Optional[str] = None  # Custom robot signature key (optional)
    feishu_webhook_keyword: Optional[str] = None  # Custom robot keywords (optional)
    dingtalk_webhook_url: Optional[str] = None
    dingtalk_secret: Optional[str] = None

    # Feishu App Bot notification
    feishu_chat_id: Optional[str] = None  # Target group conversation chat_id (group mode) or user open_id (P2P mode)
    feishu_receive_id_type: str = "chat_id"  # Receiver ID type: "chat_id" (group chat) / "open_id" (private chat)
    feishu_domain: str = "feishu"  # Feishu domain: "feishu"(feishu.cn) / "lark"(larksuite.com)

    # Telegram configuration (requires simultaneous configuration of Bot Token and Chat ID)
    telegram_bot_token: Optional[str] = None  # Bot Token(@BotFather get)
    telegram_chat_id: Optional[str] = None  # Chat ID
    telegram_message_thread_id: Optional[str] = None  # Topic ID (Message Thread ID) for groups

    # Email configuration (requires only email and authorization code, SMTP automatically identifies)
    email_sender: Optional[str] = None  # Sender email
    email_sender_name: str = "StockPulse"  # Display name used in the email From header.
    email_password: Optional[str] = None  # Email password/authorization code
    email_receivers: List[str] = field(default_factory=list)  # Recipient list (leave blank to send to yourself)

    # Stock-to-email group routing (Issue #268): STOCK_GROUP_N + EMAIL_GROUP_N
    # When configured, each group's report is sent to that group's emails only.
    stock_email_groups: List[Tuple[List[str], List[str]]] = field(default_factory=list)

    # Pushover Configuration (mobile/desktop push notifications)
    pushover_user_key: Optional[str] = None  # User Key (obtained from https://pushover.net)
    pushover_api_token: Optional[str] = None  # Application API Token

    # ntfy configuration (full topic endpoint, e.g., https://ntfy.sh/my-topic)
    ntfy_url: Optional[str] = None
    ntfy_token: Optional[str] = None

    # Gotify Configuration(server base URL; sender Concatenate /message)
    gotify_url: Optional[str] = None
    gotify_token: Optional[str] = None

    # Custom Webhook (supports multiple, comma-separated)
    # Suitable for: DingTalk, Discord, Slack, Bark, and any service that supports POST JSON Webhooks.
    custom_webhook_urls: List[str] = field(default_factory=list)
    custom_webhook_bearer_token: Optional[str] = None  # Bearer Token(For authentication required Webhook)
    custom_webhook_body_template: Optional[str] = None  # Custom Webhook JSON body template
    webhook_verify_ssl: bool = True  # Webhook HTTPS certificate validation, false can support self-signed certificates (with MITM risk)

    # Discord notification configuration
    discord_bot_token: Optional[str] = None  # Discord Bot Token
    discord_main_channel_id: Optional[str] = None  # Discord Main Channel ID
    discord_webhook_url: Optional[str] = None  # Discord Webhook URL
    discord_interactions_public_key: Optional[str] = None  # Discord Interaction onboarding signing key

    # Slack notification configuration
    slack_webhook_url: Optional[str] = None  # Slack Incoming Webhook URL
    slack_bot_token: Optional[str] = None  # Slack Bot Token (xoxb-...)
    slack_channel_id: Optional[str] = None  # Slack channel ID (required for Bot mode)

    # AstrBot notification configuration
    astrbot_token: Optional[str] = None
    astrbot_url: Optional[str] = None

    # Notification routing strategy (Issue #1200 P3): Leaving empty indicates that this type uses all configured channels.
    notification_report_channels: List[str] = field(default_factory=list)
    notification_alert_channels: List[str] = field(default_factory=list)
    notification_system_error_channels: List[str] = field(default_factory=list)

    # Notification noise reduction mechanism (Issue #1200 P4): Defaults to all disabled, only effective for static notification channels.
    notification_dedup_ttl_seconds: int = 0
    notification_cooldown_seconds: int = 0
    notification_quiet_hours: str = ""
    notification_timezone: str = ""
    notification_min_severity: str = ""
    notification_daily_digest_enabled: bool = False

    # Single stock push mode: Pushes immediately after analyzing each stock, instead of pushing after aggregation
    single_stock_notify: bool = False

    # Report type: simple (concise) or full (complete)
    report_type: str = "simple"
    report_language: str = "zh"

    # Only analyze the result summary: true only pushes summaries, without individual stock details (Issue #262)
    report_summary_only: bool = False
    report_show_llm_model: bool = True

    # Report Engine P0: Jinja2 renderer and integrity checks
    report_templates_dir: str = "templates"  # Template directory (relative to project root)
    report_renderer_enabled: bool = False  # Enable Jinja2 rendering (default off for zero regression)
    report_integrity_enabled: bool = True  # Content integrity validation after LLM output
    report_integrity_retry: int = 1  # Retry count when mandatory fields missing (0 = placeholder only)
    report_history_compare_n: int = 0  # History comparison count (0 = disabled)

    # PushPlus Push Configuration
    pushplus_token: Optional[str] = None  # PushPlus Token
    pushplus_topic: Optional[str] = None  # PushPlus Group Encoding (one-to-many push)

    # ServerSoy3 Push configuration
    serverchan3_sendkey: Optional[str] = None  # Server Soy sauce 3 SendKey

    # Analyze interval time (seconds) - to avoid API rate limiting
    analysis_delay: float = 0.0  # Delay between individual stock analysis and major index analysis

    # Merge stock + market report into one notification (Issue #190)
    merge_email_notification: bool = False

    # Message length limit (bytes) - Automatically split long messages for sending
    feishu_max_bytes: int = 20000  # Feishu limits to approximately 20KB, default 20000 bytes
    feishu_send_as_file: bool = False  # Does Feishu send reports in file format (default: text message)?
    wechat_max_bytes: int = 4000   # WeCom limit is 4096 bytes; default 4000 bytes
    discord_max_words: int = 2000  # Discord limits 2000 words, defaults to 2000 words
    wechat_msg_type: str = "markdown"  # WeCom message type; defaults to markdown

    # Markdown to image (Issue #289): Send unsupported Markdown channels as images
    markdown_to_image_channels: List[str] = field(default_factory=list)  # Comma-separated: telegram,wechat,custom,email
    markdown_to_image_max_chars: int = 15000  # Do not convert if exceeding this length to avoid oversized images
    md2img_engine: str = "wkhtmltoimage"  # wkhtmltoimage | markdown-to-file (Issue #455, better emoji support)

    # Real-time quote prefetch (Issue #455): Set to false to disable, avoid full market pull from efinance/akshare_em
    prefetch_realtime_quotes: bool = True

    # === Database Configuration ===
    database_path: str = "./data/stock_analysis.db"
    sqlite_wal_enabled: bool = True
    sqlite_busy_timeout_ms: int = 5000
    sqlite_write_retry_max: int = 3
    sqlite_write_retry_base_delay: float = 0.1

    # Whether to save analysis context snapshots (for historical backtracking)
    save_context_snapshot: bool = True

    # === Backtesting Configuration ===
    backtest_enabled: bool = True
    backtest_eval_window_days: int = 10
    backtest_min_age_days: int = 14
    backtest_engine_version: str = "v1"
    backtest_neutral_band_pct: float = 2.0

    # Log Configuration
    log_dir: str = "./logs"  # Log file directory
    log_level: str = "INFO"  # Log level

    # System Configuration
    max_workers: int = 3  # Low concurrency anti-ban
    debug: bool = False
    http_proxy: Optional[str] = None  # HTTP Proxy (e.g., http://127.0.0.1:10809)
    https_proxy: Optional[str] = None # HTTPS Proxy

    # === Scheduled Task Configuration ===
    schedule_enabled: bool = False            # Enable scheduled tasks
    schedule_time: str = "18:00"              # Push notification time (HH:MM format)
    schedule_times: List[str] = field(default_factory=lambda: ["18:00"])
    schedule_run_immediately: bool = True     # Execute immediately upon startup
    run_immediately: bool = True              # Execute immediately upon startup (non-scheduled mode)
    market_review_enabled: bool = True        # Enable market review
    daily_market_context_enabled: bool = True   # Should the market summary be used for individual stock analysis prompts and conservative barriers?
    # Main Market Review Market Region: cn(A-shares), hk(Hong Kong stocks), us(U.S. stocks), jp(Japanese stocks), kr(Korean stocks), both(all markets)
    market_review_region: str = "cn"
    market_review_color_scheme: str = "green_up"
    # Trading check: Enabled by default, skips execution on non-trading days; set to false or --force-run to force execution (Issue #373)
    trading_day_check_enabled: bool = True

    # === Real-Time Quote Enhanced Data Configuration ===
    # Real-time quote switch; when disabled, analysis uses historical closing prices.
    enable_realtime_quote: bool = True
    # Intraday technical analysis uses real-time prices for moving averages and bullish MA alignment (Issue #234); otherwise it uses the previous close.
    enable_realtime_technical_indicators: bool = True
    # Chip distribution switch (the upstream API is unstable; disabling it is recommended for cloud deployments)
    enable_chip_distribution: bool = True
    # Eastmoney API patch switch
    enable_eastmoney_patch: bool = False
    # Real-time quote data source priority (comma separated)
    # Recommendation order:tencent > akshare_sina > efinance > akshare_em > tushare
    # - tencent: Tencent Finance, including volume ratio, turnover rate, and P/E ratio; stable single-stock query (recommended)
    # - akshare_sina: Sina Finance, stable basic data but no volume ratio
    # - efinance/akshare_em: Eastmoney full-data APIs; most complete, but prone to blocking
    # - tushare: Tushare Pro, requires 2000 points, comprehensive data (paid users have priority)
    realtime_source_priority: str = "tencent,akshare_sina,efinance,akshare_em"
    # Real-time quote cache time (seconds)
    realtime_cache_ttl: int = 600
    # Circuit Breaker cooling time (seconds)
    circuit_breaker_cooldown: int = 300

    # === Fundamental Data Aggregation Switch and Degradation Protection ===
    # Global master switch; returns not_supported when closed and maintains the main flow without changes
    enable_fundamental_pipeline: bool = True
    # Total budget for fundamentals phase (seconds)
    fundamental_stage_timeout_seconds: float = FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT
    # Single source call timeout (seconds)
    fundamental_fetch_timeout_seconds: float = 8.0
    # (Included in the first retry) Number of failed ability retries
    fundamental_retry_max: int = 1
    # Fundamentals context short TTL (seconds)
    fundamental_cache_ttl_seconds: int = 120
    # Maximum number of fundamentals cache entries (to avoid long-running memory growth)
    fundamental_cache_max_entries: int = 256

    # === Portfolio import, risk, FX, and idempotency settings ===
    portfolio_idempotency_replay_window_days: int = PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT
    portfolio_risk_concentration_alert_pct: float = 35.0
    portfolio_risk_drawdown_alert_pct: float = 15.0
    portfolio_risk_stop_loss_alert_pct: float = 10.0
    portfolio_risk_stop_loss_near_ratio: float = 0.8
    portfolio_risk_lookback_days: int = 180
    portfolio_fx_update_enabled: bool = True

    # Discord Bot status
    discord_bot_status: str = "A股智能分析 | /help"

    # Rate Limiting Configuration (Key Anti-Ban Parameters)
    # Akshare request interval range (seconds)
    akshare_sleep_min: float = 2.0
    akshare_sleep_max: float = 5.0

    # Maximum requests per minute from Tushare (free quota)
    tushare_rate_limit_per_minute: int = 80

    # Retry configuration
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0

    # === WebUI Configuration ===
    webui_enabled: bool = False
    webui_host: str = "127.0.0.1"
    webui_port: int = 8000

    # Robot Configuration
    bot_enabled: bool = True              # Enable robot functionality
    bot_command_prefix: str = "/"         # Command prefix
    bot_rate_limit_requests: int = 10     # Rate limit: maximum number of requests within the window
    bot_rate_limit_window: int = 60       # Rate limit: window time (seconds)
    bot_admin_users: List[str] = field(default_factory=list)  # Admin user ID list

    # Feishu robot (event subscription) - has feishu_app_id, feishu_app_secret
    feishu_verification_token: Optional[str] = None  # Event subscription verification Token
    feishu_encrypt_key: Optional[str] = None         # Message encryption key (optional)
    feishu_stream_enabled: bool = False              # Whether long connection Stream mode is enabled (no public IP required)

    # DingTalk robot
    dingtalk_app_key: Optional[str] = None      # Application AppKey
    dingtalk_app_secret: Optional[str] = None   # Application AppSecret
    dingtalk_stream_enabled: bool = False       # Whether Stream mode is enabled (no public IP required)

    # WeCom bot (callback mode)
    wecom_corpid: Optional[str] = None              # Company ID
    wecom_token: Optional[str] = None               # Callback Token
    wecom_encoding_aes_key: Optional[str] = None    # Message encryption and decryption key
    wecom_agent_id: Optional[str] = None            # Application AgentId

    # Telegram Robot? - existing telegram_bot_token, telegram_chat_id
    telegram_webhook_secret: Optional[str] = None   # Webhook Key

    # === Configuration Validation Mode ===
    # CONFIG_VALIDATE_MODE=warn (default): log all issues but always continue startup
    # CONFIG_VALIDATE_MODE=strict: exit(1) when any "error" severity issue is found
    config_validate_mode: str = "warn"

    # --- Post-init validation ---------------------------------------------------
    _VALID_AGENT_ARCH = {"single", "multi"}
    _VALID_ORCHESTRATOR_MODES = {"quick", "standard", "full", "specialist"}
    _VALID_SKILL_ROUTING = {"auto", "manual"}
    _WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS = frozenset(
        {
            "STOCK_LIST",
            "RUN_IMMEDIATELY",
            "SCHEDULE_ENABLED",
            "SCHEDULE_TIME",
            "SCHEDULE_TIMES",
            "SCHEDULE_RUN_IMMEDIATELY",
        }
    )
    _BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED = False
    _BOOTSTRAP_RUNTIME_ENV_OVERRIDES = frozenset()
    _BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS = frozenset()

    def __post_init__(self) -> None:
        _log = logging.getLogger(__name__)
        if self.agent_arch not in self._VALID_AGENT_ARCH:
            _log.warning(
                "Invalid AGENT_ARCH=%r, falling back to 'single'. Valid: %s",
                self.agent_arch, self._VALID_AGENT_ARCH,
            )
            object.__setattr__(self, "agent_arch", "single")
        if self.agent_orchestrator_mode in {"strategy", "skill"}:
            _log.info(
                "AGENT_ORCHESTRATOR_MODE=%s is deprecated; normalizing to 'specialist'",
                self.agent_orchestrator_mode,
            )
            object.__setattr__(self, "agent_orchestrator_mode", "specialist")
        if self.agent_orchestrator_mode not in self._VALID_ORCHESTRATOR_MODES:
            _log.warning(
                "Invalid AGENT_ORCHESTRATOR_MODE=%r, falling back to 'standard'. Valid: %s",
                self.agent_orchestrator_mode, self._VALID_ORCHESTRATOR_MODES,
            )
            object.__setattr__(self, "agent_orchestrator_mode", "standard")
        if self.agent_skill_routing not in self._VALID_SKILL_ROUTING:
            _log.warning(
                "Invalid AGENT_SKILL_ROUTING=%r, falling back to 'auto'. Valid: %s",
                self.agent_skill_routing, self._VALID_SKILL_ROUTING,
            )
            object.__setattr__(self, "agent_skill_routing", "auto")
        normalized_profile = normalize_agent_context_compression_profile(
            self.agent_context_compression_profile
        )
        if normalized_profile != self.agent_context_compression_profile:
            object.__setattr__(self, "agent_context_compression_profile", normalized_profile)

    # Singleton instance storage
    _instance: Optional['Config'] = None

    @classmethod
    def get_instance(cls) -> 'Config':
        """
        获取配置单例实例
\x20\x20\x20\x20\x20\x20\x20\x20
        单例模式确保：
        1. 全局只有一个配置实例
        2. 配置只从环境变量加载一次
        3. 所有模块共享相同配置
        """
        if cls._instance is None:
            cls._instance = cls._load_from_env()
        return cls._instance



_CONFIG_METHOD_GROUPS = (
    (_ConfigLoadingMethods, ("_load_from_env",)),
    (
        _ConfigLLMMethods,
        (
            "_parse_litellm_yaml",
            "_parse_llm_channels",
            "_parse_llm_channels_with_issues",
            "_channels_to_model_list",
            "_legacy_keys_to_model_list",
        ),
    ),
    (
        _ConfigLoadingMethods,
        (
            "_parse_stock_email_groups",
            "_parse_report_type",
            "_get_env_file_value",
            "_resolve_env_value",
            "_capture_bootstrap_runtime_env_overrides",
            "_has_bootstrap_runtime_env_override",
            "_had_bootstrap_runtime_env_key",
            "_resolve_report_language_env_value",
            "_parse_report_language",
            "_parse_news_strategy_profile",
            "get_effective_news_window_days",
            "_parse_market_review_region",
            "_parse_market_review_color_scheme",
            "_parse_md2img_engine",
            "_resolve_realtime_source_priority",
        ),
    ),
    (
        _ConfigRuntimeMethods,
        (
            "reset_instance",
            "has_searxng_enabled",
            "has_search_capability_enabled",
            "is_agent_available",
            "refresh_stock_list",
        ),
    ),
    (_ConfigValidationMethods, ("validate_structured", "validate")),
    (_ConfigRuntimeMethods, ("get_db_url",)),
)


def _install_config_methods(method_group: type, method_names: Tuple[str, ...]) -> None:
    for method_name in method_names:
        descriptor = vars(method_group)[method_name]
        function = descriptor.__func__ if isinstance(descriptor, classmethod) else descriptor
        function.__module__ = "src.config"
        function.__qualname__ = f"Config.{method_name}"
        setattr(Config, method_name, descriptor)


_loading_module.Config = Config
_parsers_module.Config = Config

for _method_group, _method_names in _CONFIG_METHOD_GROUPS:
    _install_config_methods(_method_group, _method_names)

Config.__module__ = "src.config"
for _method_name in ("__init__", "__repr__", "__eq__", "__post_init__", "get_instance"):
    _descriptor = vars(Config)[_method_name]
    _function = _descriptor.__func__ if isinstance(_descriptor, classmethod) else _descriptor
    _function.__module__ = "src.config"
    _function.__qualname__ = f"Config.{_method_name}"

del _descriptor, _function, _method_name


def _bind_config_facade(facade_globals: Dict[str, Any]) -> None:
    """Bind public Config methods to the original facade global namespace."""
    init_function = vars(Config)["__init__"]
    for config_field in Config.__dataclass_fields__.values():
        default_factory = config_field.default_factory
        if getattr(default_factory, "__globals__", None) is not globals():
            continue
        cloned_factory = clone_function(default_factory, facade_globals)
        replace_closure_reference(init_function, default_factory, cloned_factory)
        config_field.default_factory = cloned_factory

    bind_wrapped_function(vars(Config)["__repr__"], facade_globals)

    for method_group, method_names in _CONFIG_METHOD_GROUPS:
        for method_name in method_names:
            descriptor = clone_descriptor(vars(method_group)[method_name], facade_globals)
            function = descriptor.__func__ if isinstance(descriptor, classmethod) else descriptor
            function.__module__ = "src.config"
            function.__qualname__ = f"Config.{method_name}"
            setattr(Config, method_name, descriptor)

    for method_name in ("__init__", "__eq__", "__post_init__", "get_instance"):
        descriptor = clone_descriptor(vars(Config)[method_name], facade_globals)
        function = descriptor.__func__ if isinstance(descriptor, classmethod) else descriptor
        function.__module__ = "src.config"
        function.__qualname__ = f"Config.{method_name}"
        setattr(Config, method_name, descriptor)
