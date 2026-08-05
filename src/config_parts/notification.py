"""Notification domain configuration for the public ``src.config`` facade."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class NotificationConfig:
    """Outbound notification channels, routing, noise controls, and IM formatting."""

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

    # PushPlus Push Configuration
    pushplus_token: Optional[str] = None  # PushPlus Token
    pushplus_topic: Optional[str] = None  # PushPlus Group Encoding (one-to-many push)

    # ServerSoy3 Push configuration
    serverchan3_sendkey: Optional[str] = None  # Server Soy sauce 3 SendKey

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
    md2img_engine: str = "wkhtmltoimage"  # wkhtmltoimage | markdown-to-file | playwright
