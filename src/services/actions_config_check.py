# -*- coding: utf-8 -*-
"""Actions-oriented configuration check without running analysis.

Presence / format / optional connectivity verdicts only. Never prints secret
values — only env key names, status icons, and sanitized remediation text.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Minimum length for API-key style secrets (aligned with config validation).
_MIN_KEY_LENGTH = 8

# Channel-style LLM API key env names: LLM_<CHANNEL>_API_KEY(S)
_LLM_CHANNEL_KEY_RE = re.compile(r"^LLM_[A-Z0-9]+_API_KEYS?$")

# Legacy / fixed-name LLM credential keys (any one is enough for pass).
LEGACY_LLM_KEY_NAMES: Tuple[str, ...] = (
    "GEMINI_API_KEY",
    "GEMINI_API_KEYS",
    "OPENAI_API_KEY",
    "OPENAI_API_KEYS",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_KEYS",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEYS",
    "AIHUBMIX_KEY",
    "ANSPIRE_API_KEYS",
    "LITELLM_API_KEY",
)

# Recommended keys for first-time Actions users (issue #847 / three-line preset).
RECOMMENDED_LLM_KEYS: Tuple[str, ...] = (
    "LLM_ZHIPU_API_KEY",
    "LLM_SILICONFLOW_API_KEY",
    "GEMINI_API_KEY",
    "ANSPIRE_API_KEYS",
    "AIHUBMIX_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
)

# Optional data-source enhancers (never hard-fail).
OPTIONAL_DATA_SOURCE_KEYS: Tuple[Tuple[str, str, str], ...] = (
    ("TUSHARE_TOKEN", "Tushare token", "Tushare Token"),
    ("TICKFLOW_API_KEY", "TickFlow API key", "TickFlow API Key"),
)


@dataclass(frozen=True)
class NotificationChannelCheck:
    """Minimal completeness rules for one notification channel."""

    channel_id: str
    label_en: str
    label_zh: str
    # Any one of these key-groups fully present enables the channel.
    key_groups: Tuple[Tuple[str, ...], ...]


NOTIFICATION_CHANNEL_CHECKS: Tuple[NotificationChannelCheck, ...] = (
    NotificationChannelCheck(
        "wechat",
        "WeCom webhook",
        "企业微信 Webhook",
        (("WECHAT_WEBHOOK_URL",),),
    ),
    NotificationChannelCheck(
        "feishu",
        "Feishu",
        "飞书",
        (
            ("FEISHU_WEBHOOK_URL",),
            ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_CHAT_ID"),
        ),
    ),
    NotificationChannelCheck(
        "dingtalk",
        "DingTalk webhook",
        "钉钉 Webhook",
        (("DINGTALK_WEBHOOK_URL",),),
    ),
    NotificationChannelCheck(
        "telegram",
        "Telegram",
        "Telegram",
        (("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),),
    ),
    NotificationChannelCheck(
        "email",
        "Email",
        "邮件",
        (("EMAIL_SENDER", "EMAIL_PASSWORD"),),
    ),
    NotificationChannelCheck(
        "discord",
        "Discord",
        "Discord",
        (
            ("DISCORD_WEBHOOK_URL",),
            ("DISCORD_BOT_TOKEN", "DISCORD_MAIN_CHANNEL_ID"),
        ),
    ),
    NotificationChannelCheck(
        "slack",
        "Slack",
        "Slack",
        (
            ("SLACK_WEBHOOK_URL",),
            ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID"),
        ),
    ),
    NotificationChannelCheck(
        "pushplus",
        "PushPlus",
        "PushPlus",
        (("PUSHPLUS_TOKEN",),),
    ),
    NotificationChannelCheck(
        "ntfy",
        "ntfy",
        "ntfy",
        (("NTFY_URL",),),
    ),
    NotificationChannelCheck(
        "gotify",
        "Gotify",
        "Gotify",
        (("GOTIFY_URL", "GOTIFY_TOKEN"),),
    ),
    NotificationChannelCheck(
        "serverchan3",
        "ServerChan³",
        "Server酱³",
        (("SERVERCHAN3_SENDKEY",),),
    ),
    NotificationChannelCheck(
        "custom",
        "Custom webhook",
        "自定义 Webhook",
        (("CUSTOM_WEBHOOK_URLS",),),
    ),
    NotificationChannelCheck(
        "astrbot",
        "AstrBot",
        "AstrBot",
        (("ASTRBOT_URL",),),
    ),
    NotificationChannelCheck(
        "pushover",
        "Pushover",
        "Pushover",
        (("PUSHOVER_USER_KEY", "PUSHOVER_API_TOKEN"),),
    ),
)


class CheckSeverity(str, Enum):
    """Severity for a single checklist row."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    INFO = "info"
    SKIP = "skip"


_ICON = {
    CheckSeverity.PASS: "✅",
    CheckSeverity.WARN: "⚠️",
    CheckSeverity.FAIL: "❌",
    CheckSeverity.INFO: "ℹ️",
    CheckSeverity.SKIP: "⚪",
}


@dataclass(frozen=True)
class CheckItem:
    """One bilingual checklist row with a stable message code."""

    code: str
    severity: CheckSeverity
    label_en: str
    label_zh: str
    detail_en: str
    detail_zh: str
    hint_en: str = ""
    hint_zh: str = ""
    field: str = ""

    @property
    def icon(self) -> str:
        return _ICON[self.severity]

    def is_hard_failure(self) -> bool:
        return self.severity is CheckSeverity.FAIL


@dataclass
class ConfigCheckReport:
    """Aggregate verdict for Actions / CLI."""

    items: List[CheckItem] = field(default_factory=list)
    strict_notify: bool = False
    probe_llm: bool = False

    @property
    def hard_failures(self) -> List[CheckItem]:
        return [item for item in self.items if item.is_hard_failure()]

    @property
    def warnings(self) -> List[CheckItem]:
        return [item for item in self.items if item.severity is CheckSeverity.WARN]

    @property
    def ok(self) -> bool:
        return not self.hard_failures

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def _env_get(env: Mapping[str, str], key: str) -> str:
    raw = env.get(key)
    if raw is None:
        return ""
    return str(raw).strip()


def _is_present(env: Mapping[str, str], key: str) -> bool:
    return bool(_env_get(env, key))


def _is_malformed_secret(env: Mapping[str, str], key: str) -> bool:
    value = _env_get(env, key)
    if not value:
        return False
    if len(value) < _MIN_KEY_LENGTH:
        return True
    lowered = value.lower()
    if lowered in {"xxx", "your_key", "changeme", "placeholder", "todo", "none", "null"}:
        return True
    return False


def _group_complete(env: Mapping[str, str], keys: Sequence[str]) -> bool:
    return all(_is_present(env, key) for key in keys)


def _group_partial(env: Mapping[str, str], keys: Sequence[str]) -> bool:
    present = sum(1 for key in keys if _is_present(env, key))
    return 0 < present < len(keys)


def _looks_like_http_url(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def discover_llm_key_names(env: Mapping[str, str]) -> List[str]:
    """Return env key names that look like configured LLM credentials (no values)."""
    found: List[str] = []
    for key in LEGACY_LLM_KEY_NAMES:
        if _is_present(env, key):
            found.append(key)
    for key in sorted(env.keys()):
        if not _LLM_CHANNEL_KEY_RE.match(key):
            continue
        if key in found:
            continue
        if _is_present(env, key):
            found.append(key)
    if _is_present(env, "LITELLM_CONFIG") or _is_present(env, "LITELLM_CONFIG_YAML"):
        if "LITELLM_CONFIG" not in found and "LITELLM_CONFIG_YAML" not in found:
            if _is_present(env, "LITELLM_CONFIG_YAML"):
                found.append("LITELLM_CONFIG_YAML")
            else:
                found.append("LITELLM_CONFIG")
    return found


def _resolve_watchlist_raw(env: Mapping[str, str]) -> Tuple[str, str]:
    """Return (raw_value, source_key). Prefer STOCK_LIST_CONFIG then STOCK_LIST."""
    config_val = _env_get(env, "STOCK_LIST_CONFIG")
    if config_val:
        return config_val, "STOCK_LIST_CONFIG"
    stock_val = _env_get(env, "STOCK_LIST")
    if stock_val:
        return stock_val, "STOCK_LIST"
    return "", ""


def _parse_stock_tokens(raw: str) -> List[str]:
    tokens: List[str] = []
    for part in re.split(r"[,;\s]+", raw.strip()):
        token = part.strip()
        if token:
            tokens.append(token)
    return tokens


def check_watchlist(env: Mapping[str, str]) -> CheckItem:
    raw, source = _resolve_watchlist_raw(env)
    if not raw:
        return CheckItem(
            code="config.watchlist.missing",
            severity=CheckSeverity.FAIL,
            label_en="Watchlist (STOCK_LIST)",
            label_zh="自选股 (STOCK_LIST)",
            detail_en="STOCK_LIST / STOCK_LIST_CONFIG is empty.",
            detail_zh="未配置 STOCK_LIST / STOCK_LIST_CONFIG。",
            hint_en=(
                "Add repository Secret or Variable STOCK_LIST, e.g. "
                "600519,hk00700,AAPL (Settings → Secrets and variables → Actions)."
            ),
            hint_zh=(
                "请到 Settings → Secrets and variables → Actions 添加 STOCK_LIST，"
                "例如：600519,hk00700,AAPL。"
            ),
            field="STOCK_LIST",
        )
    tokens = _parse_stock_tokens(raw)
    if not tokens:
        return CheckItem(
            code="config.watchlist.malformed",
            severity=CheckSeverity.FAIL,
            label_en="Watchlist (STOCK_LIST)",
            label_zh="自选股 (STOCK_LIST)",
            detail_en=f"{source} is set but contains no stock codes.",
            detail_zh=f"{source} 已设置但未解析出任何股票代码。",
            hint_en="Use comma-separated codes, e.g. 600519,hk00700,AAPL.",
            hint_zh="请使用逗号分隔的代码，例如：600519,hk00700,AAPL。",
            field=source or "STOCK_LIST",
        )
    return CheckItem(
        code="config.watchlist.ok",
        severity=CheckSeverity.PASS,
        label_en="Watchlist (STOCK_LIST)",
        label_zh="自选股 (STOCK_LIST)",
        detail_en=f"Configured via {source}: {len(tokens)} symbol(s).",
        detail_zh=f"已通过 {source} 配置：{len(tokens)} 个代码。",
        field=source,
    )


def check_llm_keys(env: Mapping[str, str]) -> List[CheckItem]:
    items: List[CheckItem] = []
    found = discover_llm_key_names(env)
    malformed = [name for name in found if _is_malformed_secret(env, name)]

    if not found:
        recommended = ", ".join(RECOMMENDED_LLM_KEYS[:4])
        items.append(
            CheckItem(
                code="config.llm.missing",
                severity=CheckSeverity.FAIL,
                label_en="LLM API key",
                label_zh="大模型 API Key",
                detail_en="No LLM API key or LiteLLM config was detected.",
                detail_zh="未检测到任何大模型 API Key 或 LiteLLM 配置。",
                hint_en=(
                    f"Add at least one of: {recommended}, "
                    "or LITELLM_CONFIG / LLM_CHANNELS with keys. "
                    "Settings → Secrets and variables → Actions."
                ),
                hint_zh=(
                    f"请至少配置其一：{recommended}，"
                    "或 LITELLM_CONFIG / LLM_CHANNELS 及对应 Key。"
                    "路径：Settings → Secrets and variables → Actions。"
                ),
                field="LLM",
            )
        )
        return items

    if malformed and len(malformed) == len(found):
        items.append(
            CheckItem(
                code="config.llm.malformed",
                severity=CheckSeverity.FAIL,
                label_en="LLM API key",
                label_zh="大模型 API Key",
                detail_en=(
                    "LLM credential env keys are present but look incomplete "
                    f"(too short or placeholder): {', '.join(malformed)}."
                ),
                detail_zh=(
                    "检测到 LLM 相关环境变量，但值过短或像占位符："
                    f"{', '.join(malformed)}。"
                ),
                hint_en="Replace placeholders with a real API key (never paste keys into issues).",
                hint_zh="请将占位符替换为真实 API Key（切勿把 Key 贴到 Issue/日志）。",
                field=malformed[0],
            )
        )
        return items

    if malformed:
        items.append(
            CheckItem(
                code="config.llm.partial_malformed",
                severity=CheckSeverity.WARN,
                label_en="LLM API key format",
                label_zh="大模型 Key 格式",
                detail_en=(
                    "Some LLM keys look incomplete (too short or placeholder): "
                    f"{', '.join(malformed)}. Other keys are present."
                ),
                detail_zh=(
                    "部分 LLM Key 看起来不完整（过短或占位符）："
                    f"{', '.join(malformed)}。仍检测到其他可用 Key。"
                ),
                field=malformed[0],
            )
        )

    items.append(
        CheckItem(
            code="config.llm.ok",
            severity=CheckSeverity.PASS,
            label_en="LLM API key",
            label_zh="大模型 API Key",
            detail_en=f"Detected credential surface(s): {', '.join(found)}.",
            detail_zh=f"已检测到凭据相关项：{', '.join(found)}。",
            field=found[0],
        )
    )
    return items


def check_notifications(
    env: Mapping[str, str],
    *,
    strict_notify: bool = False,
) -> List[CheckItem]:
    items: List[CheckItem] = []
    configured: List[str] = []

    for channel in NOTIFICATION_CHANNEL_CHECKS:
        complete = any(_group_complete(env, group) for group in channel.key_groups)
        if complete:
            for group in channel.key_groups:
                if not _group_complete(env, group):
                    continue
                for key in group:
                    if "URL" in key or key.endswith("_URLS"):
                        raw = _env_get(env, key)
                        first = raw.split(",")[0].strip() if raw else ""
                        if first and not _looks_like_http_url(first):
                            items.append(
                                CheckItem(
                                    code=f"config.notify.{channel.channel_id}.malformed_url",
                                    severity=CheckSeverity.WARN,
                                    label_en=f"Notification · {channel.label_en}",
                                    label_zh=f"通知 · {channel.label_zh}",
                                    detail_en=f"{key} does not look like an http(s) URL.",
                                    detail_zh=f"{key} 不像有效的 http(s) URL。",
                                    hint_en="Use a full webhook URL starting with https://.",
                                    hint_zh="请使用以 https:// 开头的完整 Webhook URL。",
                                    field=key,
                                )
                            )
            configured.append(channel.channel_id)
            continue
        if any(_group_partial(env, group) for group in channel.key_groups):
            missing_bits: List[str] = []
            for group in channel.key_groups:
                if _group_partial(env, group):
                    missing_bits.extend(k for k in group if not _is_present(env, k))
            items.append(
                CheckItem(
                    code=f"config.notify.{channel.channel_id}.incomplete",
                    severity=CheckSeverity.WARN,
                    label_en=f"Notification · {channel.label_en}",
                    label_zh=f"通知 · {channel.label_zh}",
                    detail_en=(
                        "Partial channel config; missing: "
                        f"{', '.join(dict.fromkeys(missing_bits))}."
                    ),
                    detail_zh=(
                        "渠道配置不完整，缺少："
                        f"{', '.join(dict.fromkeys(missing_bits))}。"
                    ),
                    hint_en="Complete the minimal key set for this channel, or remove partial secrets.",
                    hint_zh="请补齐该渠道的最小 Key 组合，或删除不完整的 Secret。",
                    field=missing_bits[0] if missing_bits else channel.channel_id,
                )
            )

    if configured:
        items.append(
            CheckItem(
                code="config.notify.ok",
                severity=CheckSeverity.PASS,
                label_en="Notification channels",
                label_zh="通知渠道",
                detail_en=f"Configured channel(s): {', '.join(configured)}.",
                detail_zh=f"已配置渠道：{', '.join(configured)}。",
                field="NOTIFICATION",
            )
        )
    else:
        severity = CheckSeverity.FAIL if strict_notify else CheckSeverity.WARN
        items.append(
            CheckItem(
                code="config.notify.missing",
                severity=severity,
                label_en="Notification channels",
                label_zh="通知渠道",
                detail_en=(
                    "No notification channel is fully configured. "
                    "Daily analysis can still succeed; download Artifacts or add a webhook later."
                ),
                detail_zh=(
                    "未完整配置任何通知渠道。日推分析仍可成功；"
                    "可下载 Artifact 查看报告，或之后再配置 Webhook。"
                ),
                hint_en=(
                    "Optional: set WECHAT_WEBHOOK_URL, FEISHU_WEBHOOK_URL, "
                    "TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL, etc."
                ),
                hint_zh=(
                    "可选：配置 WECHAT_WEBHOOK_URL、FEISHU_WEBHOOK_URL、"
                    "TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID、DISCORD_WEBHOOK_URL 等。"
                ),
                field="NOTIFICATION",
            )
        )
    return items


def check_optional_data_sources(env: Mapping[str, str]) -> List[CheckItem]:
    items: List[CheckItem] = []
    for key, label_en, label_zh in OPTIONAL_DATA_SOURCE_KEYS:
        if _is_present(env, key):
            if _is_malformed_secret(env, key):
                items.append(
                    CheckItem(
                        code=f"config.datasource.{key.lower()}.malformed",
                        severity=CheckSeverity.WARN,
                        label_en=label_en,
                        label_zh=label_zh,
                        detail_en=f"{key} is set but looks too short or like a placeholder.",
                        detail_zh=f"{key} 已设置但过短或像占位符。",
                        field=key,
                    )
                )
            else:
                items.append(
                    CheckItem(
                        code=f"config.datasource.{key.lower()}.ok",
                        severity=CheckSeverity.PASS,
                        label_en=label_en,
                        label_zh=label_zh,
                        detail_en=f"{key} is configured (optional enhancer).",
                        detail_zh=f"{key} 已配置（可选增强数据源）。",
                        field=key,
                    )
                )
        else:
            items.append(
                CheckItem(
                    code=f"config.datasource.{key.lower()}.absent",
                    severity=CheckSeverity.INFO,
                    label_en=label_en,
                    label_zh=label_zh,
                    detail_en=f"{key} not set; free fallbacks still work.",
                    detail_zh=f"未配置 {key}；将使用免费/其他回退数据源。",
                    field=key,
                )
            )
    return items


def check_data_paths(env: Mapping[str, str], *, repo_root: Optional[Path] = None) -> List[CheckItem]:
    """Sanity-check report/data path configuration (create-ability, not analysis)."""
    root = repo_root or Path.cwd()
    items: List[CheckItem] = []

    database_path = _env_get(env, "DATABASE_PATH") or str(root / "data" / "stock_analysis.db")
    report_dir = _env_get(env, "REPORT_DIR") or str(root / "reports")
    data_dir = _env_get(env, "DATA_DIR") or str(root / "data")
    log_dir = _env_get(env, "LOG_DIR") or str(root / "logs")

    targets = (
        ("DATABASE_PATH parent", Path(database_path).expanduser().parent, "config.path.database"),
        ("REPORT_DIR", Path(report_dir).expanduser(), "config.path.reports"),
        ("DATA_DIR", Path(data_dir).expanduser(), "config.path.data"),
        ("LOG_DIR", Path(log_dir).expanduser(), "config.path.logs"),
    )

    for label, path, code_prefix in targets:
        try:
            resolved = path if path.is_absolute() else (root / path)
            if resolved.exists():
                if not os.access(resolved, os.W_OK):
                    items.append(
                        CheckItem(
                            code=f"{code_prefix}.not_writable",
                            severity=CheckSeverity.FAIL,
                            label_en=f"Path · {label}",
                            label_zh=f"路径 · {label}",
                            detail_en=f"Path exists but is not writable: {resolved}.",
                            detail_zh=f"路径存在但不可写：{resolved}。",
                            field=label,
                        )
                    )
                else:
                    items.append(
                        CheckItem(
                            code=f"{code_prefix}.ok",
                            severity=CheckSeverity.PASS,
                            label_en=f"Path · {label}",
                            label_zh=f"路径 · {label}",
                            detail_en=f"Writable: {resolved}.",
                            detail_zh=f"可写：{resolved}。",
                            field=label,
                        )
                    )
            else:
                parent = resolved if resolved.suffix == "" else resolved.parent
                probe = parent
                while not probe.exists() and probe != probe.parent:
                    probe = probe.parent
                if probe.exists() and os.access(probe, os.W_OK):
                    items.append(
                        CheckItem(
                            code=f"{code_prefix}.creatable",
                            severity=CheckSeverity.PASS,
                            label_en=f"Path · {label}",
                            label_zh=f"路径 · {label}",
                            detail_en=f"Does not exist yet but is creatable under {probe}.",
                            detail_zh=f"尚不存在，但可在 {probe} 下创建。",
                            field=label,
                        )
                    )
                else:
                    items.append(
                        CheckItem(
                            code=f"{code_prefix}.blocked",
                            severity=CheckSeverity.FAIL,
                            label_en=f"Path · {label}",
                            label_zh=f"路径 · {label}",
                            detail_en=f"Cannot create path {resolved} (ancestor not writable).",
                            detail_zh=f"无法创建路径 {resolved}（上级目录不可写）。",
                            field=label,
                        )
                    )
        except OSError as exc:
            items.append(
                CheckItem(
                    code=f"{code_prefix}.error",
                    severity=CheckSeverity.FAIL,
                    label_en=f"Path · {label}",
                    label_zh=f"路径 · {label}",
                    detail_en=f"Path check failed: {type(exc).__name__}.",
                    detail_zh=f"路径检查失败：{type(exc).__name__}。",
                    field=label,
                )
            )
    return items


def _sanitize_probe_error(message: str, env: Mapping[str, str]) -> str:
    """Strip any configured secret values from probe error text."""
    text = str(message or "")
    for key, value in env.items():
        secret = str(value or "").strip()
        if len(secret) >= 4 and secret in text:
            text = text.replace(secret, f"[{key}]")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200]


def probe_llm_connectivity(
    env: Mapping[str, str],
    *,
    timeout_seconds: float = 8.0,
) -> CheckItem:
    """One cheap connectivity call for the first detectable provider (optional).

    Never logs or returns secret values — status / HTTP code only.
    """
    candidates: List[Tuple[str, str, str]] = []
    if _is_present(env, "LLM_SILICONFLOW_API_KEY") and not _is_malformed_secret(
        env, "LLM_SILICONFLOW_API_KEY"
    ):
        base = _env_get(env, "LLM_SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn/v1"
        candidates.append(("siliconflow", base, "LLM_SILICONFLOW_API_KEY"))
    if _is_present(env, "LLM_ZHIPU_API_KEY") and not _is_malformed_secret(env, "LLM_ZHIPU_API_KEY"):
        base = _env_get(env, "LLM_ZHIPU_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4"
        candidates.append(("zhipu", base, "LLM_ZHIPU_API_KEY"))
    if _is_present(env, "OPENAI_API_KEY") and not _is_malformed_secret(env, "OPENAI_API_KEY"):
        base = _env_get(env, "OPENAI_BASE_URL") or "https://api.openai.com/v1"
        candidates.append(("openai", base, "OPENAI_API_KEY"))
    if _is_present(env, "DEEPSEEK_API_KEY") and not _is_malformed_secret(env, "DEEPSEEK_API_KEY"):
        base = _env_get(env, "DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
        candidates.append(("deepseek", base, "DEEPSEEK_API_KEY"))
    # Do not probe Gemini via ?key= URL query: that pattern can leak the secret
    # into exception/proxy logs. Optional probe uses Bearer-style /models only.


    for label, base, key_name in candidates:
        api_key = _env_get(env, key_name)
        base_url = base.rstrip("/")
        url = f"{base_url}/models"
        try:
            req = Request(
                url,
                method="GET",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "stock-pulse-config-check/1",
                },
            )
            with urlopen(req, timeout=timeout_seconds) as resp:  # noqa: S310
                status = getattr(resp, "status", None) or resp.getcode()
            return CheckItem(
                code="config.llm.probe.ok",
                severity=CheckSeverity.PASS,
                label_en="LLM connectivity probe",
                label_zh="大模型连通性探测",
                detail_en=f"{label} models endpoint reachable (HTTP {status}).",
                detail_zh=f"{label} models 接口可达（HTTP {status}）。",
                field=key_name,
            )
        except HTTPError as exc:
            if exc.code in (401, 403):
                return CheckItem(
                    code="config.llm.probe.auth_rejected",
                    severity=CheckSeverity.WARN,
                    label_en="LLM connectivity probe",
                    label_zh="大模型连通性探测",
                    detail_en=(
                        f"{label} endpoint reached but auth rejected (HTTP {exc.code}). "
                        "Key may be invalid or lack permission."
                    ),
                    detail_zh=(
                        f"{label} 接口可达但鉴权失败（HTTP {exc.code}）。"
                        "Key 可能无效或权限不足。"
                    ),
                    field=key_name,
                )
            return CheckItem(
                code="config.llm.probe.http_error",
                severity=CheckSeverity.WARN,
                label_en="LLM connectivity probe",
                label_zh="大模型连通性探测",
                detail_en=f"{label} probe HTTP {exc.code}.",
                detail_zh=f"{label} 探测 HTTP {exc.code}。",
                field=key_name,
            )
        except (URLError, TimeoutError, OSError) as exc:
            return CheckItem(
                code="config.llm.probe.network_error",
                severity=CheckSeverity.WARN,
                label_en="LLM connectivity probe",
                label_zh="大模型连通性探测",
                detail_en=(
                    f"{label} probe network error: "
                    f"{_sanitize_probe_error(type(exc).__name__, env)}."
                ),
                detail_zh=(
                    f"{label} 探测网络错误："
                    f"{_sanitize_probe_error(type(exc).__name__, env)}。"
                ),
                field=key_name,
            )

    return CheckItem(
        code="config.llm.probe.skipped_no_target",
        severity=CheckSeverity.SKIP,
        label_en="LLM connectivity probe",
        label_zh="大模型连通性探测",
        detail_en="No probe-capable provider key found; presence check only.",
        detail_zh="未找到可探测的提供商 Key；仅做存在性检查。",
        field="LLM",
    )


def run_config_check(
    env: Optional[Mapping[str, str]] = None,
    *,
    strict_notify: bool = False,
    probe_llm: bool = False,
    repo_root: Optional[Path] = None,
) -> ConfigCheckReport:
    """Run the full configuration checklist against an env mapping."""
    source: Mapping[str, str] = env if env is not None else os.environ
    report = ConfigCheckReport(strict_notify=strict_notify, probe_llm=probe_llm)

    report.items.append(check_watchlist(source))
    report.items.extend(check_llm_keys(source))
    report.items.extend(check_notifications(source, strict_notify=strict_notify))
    report.items.extend(check_optional_data_sources(source))
    report.items.extend(check_data_paths(source, repo_root=repo_root))

    if probe_llm:
        report.items.append(probe_llm_connectivity(source))
    else:
        report.items.append(
            CheckItem(
                code="config.llm.probe.skipped",
                severity=CheckSeverity.SKIP,
                label_en="LLM connectivity probe",
                label_zh="大模型连通性探测",
                detail_en="Skipped (default). Pass --probe-llm to run one cheap call.",
                detail_zh="已跳过（默认）。传入 --probe-llm 可做一次廉价连通性探测。",
                field="LLM",
            )
        )
    return report


def format_report_text(report: ConfigCheckReport) -> str:
    """Human-readable bilingual table for logs."""
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("Config Check / 配置自检")
    lines.append("=" * 72)
    lines.append(f"{'Icon':<4} {'Code':<36} {'EN / 中文':<28} Status")
    lines.append("-" * 72)
    for item in report.items:
        label = f"{item.label_en} / {item.label_zh}"
        lines.append(
            f"{item.icon:<4} {item.code:<36} {label[:28]:<28} {item.severity.value}"
        )
        lines.append(f"     EN: {item.detail_en}")
        lines.append(f"     中文: {item.detail_zh}")
        if item.hint_en:
            lines.append(f"     → {item.hint_en}")
        if item.hint_zh and item.hint_zh != item.hint_en:
            lines.append(f"     → {item.hint_zh}")
    lines.append("-" * 72)
    if report.ok:
        if report.warnings:
            lines.append(
                f"RESULT: PASS with {len(report.warnings)} warning(s) "
                f"/ 通过（{len(report.warnings)} 条警告）"
            )
        else:
            lines.append("RESULT: PASS / 通过")
    else:
        lines.append(
            f"RESULT: FAIL ({len(report.hard_failures)} hard failure(s)) "
            f"/ 失败（{len(report.hard_failures)} 项硬错误）"
        )
        lines.append(
            "Fix the ❌ items under Settings → Secrets and variables → Actions, "
            "then re-run Config Check."
        )
        lines.append(
            "请到 Settings → Secrets and variables → Actions 修复 ❌ 项后重新运行配置自检。"
        )
    lines.append("=" * 72)
    return "\n".join(lines)


def format_report_markdown(report: ConfigCheckReport) -> str:
    """GitHub Step Summary markdown (bilingual)."""
    lines: List[str] = []
    lines.append("## Config Check / 配置自检")
    lines.append("")
    lines.append(
        "Presence and format only — secret **values are never printed**. "
        "本检查只报告存在性/格式，**绝不输出 Secret 值**。"
    )
    lines.append("")
    lines.append("| Status | Code | Item (EN / 中文) | Detail |")
    lines.append("| --- | --- | --- | --- |")
    for item in report.items:
        detail = f"{item.detail_en}<br>{item.detail_zh}"
        if item.hint_en:
            detail += f"<br>→ {item.hint_en}"
        if item.hint_zh and item.hint_zh != item.hint_en:
            detail += f"<br>→ {item.hint_zh}"
        label = f"{item.label_en} / {item.label_zh}"
        lines.append(
            f"| {item.icon} `{item.severity.value}` | `{item.code}` | {label} | {detail} |"
        )
    lines.append("")
    if report.ok:
        if report.warnings:
            lines.append(
                f"**Result:** ✅ PASS with {len(report.warnings)} warning(s) — "
                f"you can run **StockPulse Daily Analysis**. "
                f"通过（{len(report.warnings)} 条警告）— 可以运行日推分析。"
            )
        else:
            lines.append(
                "**Result:** ✅ PASS — ready for **StockPulse Daily Analysis**. "
                "通过 — 可以运行日推分析。"
            )
    else:
        lines.append(
            f"**Result:** ❌ FAIL ({len(report.hard_failures)} hard failure(s)). "
            "Open **Settings → Secrets and variables → Actions**, add the missing items, "
            "then re-run **Config Check**. "
            f"失败（{len(report.hard_failures)} 项）。请补齐后重新运行配置自检。"
        )
    lines.append("")
    lines.append(
        "Next: Actions → **StockPulse Daily Analysis** → Run workflow. "
        "下一步：Actions → **StockPulse Daily Analysis** → 运行工作流。"
    )
    return "\n".join(lines)


def env_from_mapping(raw: Mapping[str, object]) -> Dict[str, str]:
    """Normalize a mapping into string env values (empty for None)."""
    out: Dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            out[str(key)] = ""
        else:
            out[str(key)] = str(value)
    return out
