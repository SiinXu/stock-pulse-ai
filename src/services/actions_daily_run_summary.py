# -*- coding: utf-8 -*-
"""Human-readable Daily Analysis run summary for GitHub Actions (#850).

Responsibilities:
1. Aggregate structured ``data/run_status.json`` (preferred) plus exit/job
   signals into a plain-language outcome.
2. Render bilingual (zh primary) GitHub Step Summary markdown.
3. Optionally push a short ``system_error`` notification (config-gated).
4. Fail open: summary/notify must never raise into the analysis process, and
   the post-run CLI always exits 0.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.services.actions_outcome_codes import (
    CODE_DATA_SOURCE,
    CODE_MISSING_LLM,
    CODE_MISSING_WATCHLIST,
    CODE_NON_TRADING_DAY,
    CODE_PARTIAL,
    CODE_PROVIDER_DOWN,
    CODE_QUOTA,
    CODE_SUCCESS,
    CODE_TIMEOUT,
    CODE_UNKNOWN,
    OUTCOME_FAILED,
    OUTCOME_PARTIAL,
    OUTCOME_SKIPPED,
    OUTCOME_SUCCESS,
    format_bilingual_cause_block,
    format_cause_action,
    format_cause_headline,
    has_any_llm_secret,
    has_watchlist_configured,
)
from src.utils.sanitize import log_safe_exception, redact_sensitive_text

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_STATUS_PATH = Path("data/run_status.json")

_LOG_HINTS: Sequence[tuple[str, re.Pattern[str]]] = (
    (
        CODE_NON_TRADING_DAY,
        re.compile(
            r"markets are closed today|non.?trading|非交易日|all relevant markets are closed",
            re.I,
        ),
    ),
    (CODE_TIMEOUT, re.compile(r"\btimeout\b|timed out|截止时间|超时", re.I)),
    (
        CODE_QUOTA,
        re.compile(
            r"\bquota\b|rate.?limit|429|resource.?exhausted|insufficient.?quota|配额|限流",
            re.I,
        ),
    ),
    (
        CODE_MISSING_LLM,
        re.compile(
            r"no usable llm|no available.*model|api key.*(missing|not configured)|未检测到可用.?llm|缺少.*api.?key",
            re.I,
        ),
    ),
    (
        CODE_DATA_SOURCE,
        re.compile(
            r"data.?source|provider.*(fail|down|unavailable)|行情源|数据源.*不可用|all providers failed",
            re.I,
        ),
    ),
    (
        CODE_PROVIDER_DOWN,
        re.compile(r"connection.*(reset|refused)|503|502|upstream.*(down|unavailable)", re.I),
    ),
)


@dataclass
class StockOutcome:
    code: str
    status: str
    cause_code: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "code": self.code,
            "status": self.status,
            "cause_code": self.cause_code,
            "detail": self.detail,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class StepOutcome:
    name: str
    status: str
    cause_code: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "name": self.name,
            "status": self.status,
            "cause_code": self.cause_code,
            "detail": self.detail,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class RunStatusDocument:
    schema_version: int = SCHEMA_VERSION
    outcome: str = OUTCOME_SUCCESS
    primary_code: str = CODE_SUCCESS
    ok_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    stocks: List[StockOutcome] = field(default_factory=list)
    steps: List[StepOutcome] = field(default_factory=list)
    no_llm: bool = False
    dry_run: bool = False
    mode: Optional[str] = None
    force_run: bool = False
    messages: Dict[str, str] = field(default_factory=dict)
    written_at: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "outcome": self.outcome,
            "primary_code": self.primary_code,
            "ok_count": self.ok_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "stocks": [item.to_dict() for item in self.stocks],
            "steps": [item.to_dict() for item in self.steps],
            "no_llm": self.no_llm,
            "dry_run": self.dry_run,
            "mode": self.mode,
            "force_run": self.force_run,
            "messages": dict(self.messages),
            "written_at": self.written_at,
        }
        if self.extra:
            payload["extra"] = dict(self.extra)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class DailyRunSummary:
    outcome: str
    primary_code: str
    ok_count: int
    failed_count: int
    skipped_count: int
    headline_zh: str
    headline_en: str
    action_zh: str
    action_en: str
    notify: bool
    source: str
    details: List[str] = field(default_factory=list)

    def short_notify_text(self) -> str:
        text = (
            f"[StockPulse Daily] {self.headline_zh} / {self.headline_en} "
            f"→ {self.action_zh}"
        )
        return sanitize_summary_text(text, max_length=480)


def sanitize_summary_text(value: Any, *, max_length: int = 500) -> str:
    raw = "" if value is None else str(value)
    redacted = redact_sensitive_text(raw, preserve_http_credential_hosts=True)
    text = " ".join(str(redacted).split())
    if len(text) > max_length:
        return f"{text[: max_length - 3].rstrip()}..."
    return text


def default_status_path() -> Path:
    return DEFAULT_STATUS_PATH


def write_run_status(
    document: RunStatusDocument,
    path: Optional[Path] = None,
) -> Optional[Path]:
    target = Path(path) if path is not None else default_status_path()
    try:
        if not document.written_at:
            document.written_at = datetime.now(timezone.utc).isoformat()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = document.to_dict()
        safe_payload = _sanitize_payload_strings(payload)
        target.write_text(
            json.dumps(safe_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target
    except Exception as exc:  # broad-exception: fallback_recorded - status write must not fail analysis
        log_safe_exception(
            logger,
            "Failed to write Actions run status",
            exc,
            error_code="actions_run_status_write_failed",
            level=logging.WARNING,
            context={"path": str(target)},
        )
        return None


def load_run_status(path: Optional[Path] = None) -> Optional[RunStatusDocument]:
    target = Path(path) if path is not None else default_status_path()
    try:
        if not target.is_file():
            return None
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        stocks = [
            StockOutcome(
                code=str(item.get("code") or ""),
                status=str(item.get("status") or "unknown"),
                cause_code=item.get("cause_code"),
                detail=item.get("detail"),
            )
            for item in (raw.get("stocks") or [])
            if isinstance(item, dict) and item.get("code")
        ]
        steps = [
            StepOutcome(
                name=str(item.get("name") or ""),
                status=str(item.get("status") or "unknown"),
                cause_code=item.get("cause_code"),
                detail=item.get("detail"),
            )
            for item in (raw.get("steps") or [])
            if isinstance(item, dict) and item.get("name")
        ]
        messages = raw.get("messages") if isinstance(raw.get("messages"), dict) else {}
        extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
        return RunStatusDocument(
            schema_version=int(raw.get("schema_version") or SCHEMA_VERSION),
            outcome=str(raw.get("outcome") or OUTCOME_SUCCESS),
            primary_code=str(raw.get("primary_code") or CODE_SUCCESS),
            ok_count=int(raw.get("ok_count") or 0),
            failed_count=int(raw.get("failed_count") or 0),
            skipped_count=int(raw.get("skipped_count") or 0),
            stocks=stocks,
            steps=steps,
            no_llm=bool(raw.get("no_llm")),
            dry_run=bool(raw.get("dry_run")),
            mode=raw.get("mode"),
            force_run=bool(raw.get("force_run")),
            messages={str(k): str(v) for k, v in messages.items()},
            written_at=raw.get("written_at"),
            extra=dict(extra),
        )
    except Exception as exc:  # broad-exception: fallback_recorded - corrupt status falls back to heuristics
        log_safe_exception(
            logger,
            "Failed to load Actions run status",
            exc,
            error_code="actions_run_status_load_failed",
            level=logging.WARNING,
            context={"path": str(target)},
        )
        return None


def build_status_for_non_trading_day(
    *,
    mode: Optional[str] = None,
    force_run: bool = False,
    stock_codes: Optional[Sequence[str]] = None,
) -> RunStatusDocument:
    codes = [str(code).strip() for code in (stock_codes or []) if str(code).strip()]
    stocks = [
        StockOutcome(code=code, status="skipped", cause_code=CODE_NON_TRADING_DAY)
        for code in codes
    ]
    return RunStatusDocument(
        outcome=OUTCOME_SKIPPED,
        primary_code=CODE_NON_TRADING_DAY,
        ok_count=0,
        failed_count=0,
        skipped_count=len(stocks) or 1,
        stocks=stocks,
        steps=[
            StepOutcome(
                name="trading_day_check",
                status="skipped",
                cause_code=CODE_NON_TRADING_DAY,
                detail="All relevant markets closed; use force_run to override",
            )
        ],
        mode=mode,
        force_run=force_run,
        messages={
            "zh": format_cause_headline(CODE_NON_TRADING_DAY, language="zh"),
            "en": format_cause_headline(CODE_NON_TRADING_DAY, language="en"),
        },
    )


def build_status_from_counts(
    *,
    ok_count: int,
    failed_count: int,
    skipped_count: int = 0,
    no_llm: bool = False,
    dry_run: bool = False,
    mode: Optional[str] = None,
    force_run: bool = False,
    attempted_codes: Optional[Sequence[str]] = None,
    successful_codes: Optional[Sequence[str]] = None,
) -> RunStatusDocument:
    attempted = [str(c).strip() for c in (attempted_codes or []) if str(c).strip()]
    succeeded = {str(c).strip() for c in (successful_codes or []) if str(c).strip()}
    stocks: List[StockOutcome] = []
    if attempted:
        for code in attempted:
            if code in succeeded:
                stocks.append(StockOutcome(code=code, status="ok"))
            else:
                cause = CODE_MISSING_LLM if no_llm else CODE_UNKNOWN
                stocks.append(StockOutcome(code=code, status="failed", cause_code=cause))

    if no_llm and (ok_count + failed_count + skipped_count) == 0:
        primary = CODE_MISSING_LLM
        outcome = OUTCOME_FAILED
    elif no_llm and failed_count >= ok_count and ok_count == 0:
        primary = CODE_MISSING_LLM
        outcome = OUTCOME_FAILED
    elif failed_count <= 0 and skipped_count <= 0:
        primary = CODE_SUCCESS
        outcome = OUTCOME_SUCCESS
    elif ok_count > 0 and failed_count > 0:
        primary = CODE_PARTIAL if not no_llm else CODE_MISSING_LLM
        outcome = OUTCOME_PARTIAL
    elif ok_count > 0 and skipped_count > 0 and failed_count <= 0:
        primary = CODE_PARTIAL
        outcome = OUTCOME_PARTIAL
    elif ok_count <= 0 and failed_count > 0:
        primary = CODE_MISSING_LLM if no_llm else CODE_UNKNOWN
        outcome = OUTCOME_FAILED
    else:
        primary = CODE_SUCCESS
        outcome = OUTCOME_SUCCESS

    if ok_count > 0 and failed_count <= 0:
        step_status = "ok"
    elif ok_count <= 0 and failed_count > 0:
        step_status = "failed"
    elif ok_count > 0 and failed_count > 0:
        step_status = "partial"
    else:
        step_status = "skipped"

    steps = [
        StepOutcome(
            name="stock_analysis",
            status=step_status,
            cause_code=primary if outcome != OUTCOME_SUCCESS else None,
        )
    ]

    return RunStatusDocument(
        outcome=outcome,
        primary_code=primary,
        ok_count=int(ok_count),
        failed_count=int(failed_count),
        skipped_count=int(skipped_count),
        stocks=stocks,
        steps=steps,
        no_llm=no_llm,
        dry_run=dry_run,
        mode=mode,
        force_run=force_run,
        messages={
            "zh": format_cause_headline(primary, language="zh"),
            "en": format_cause_headline(primary, language="en"),
        },
    )


def build_status_for_failure(
    *,
    primary_code: str = CODE_UNKNOWN,
    detail: Optional[str] = None,
    mode: Optional[str] = None,
) -> RunStatusDocument:
    safe_detail = sanitize_summary_text(detail, max_length=200) if detail else None
    return RunStatusDocument(
        outcome=OUTCOME_FAILED,
        primary_code=primary_code or CODE_UNKNOWN,
        ok_count=0,
        failed_count=1,
        skipped_count=0,
        steps=[
            StepOutcome(
                name="analysis",
                status="failed",
                cause_code=primary_code or CODE_UNKNOWN,
                detail=safe_detail,
            )
        ],
        mode=mode,
        messages={
            "zh": format_cause_headline(primary_code or CODE_UNKNOWN, language="zh"),
            "en": format_cause_headline(primary_code or CODE_UNKNOWN, language="en"),
        },
        extra={"detail": safe_detail} if safe_detail else {},
    )


def classify_log_hints(log_text: str) -> Optional[str]:
    if not log_text:
        return None
    sanitized = sanitize_summary_text(log_text, max_length=50_000)
    for code, pattern in _LOG_HINTS:
        if pattern.search(sanitized):
            return code
    return None


def resolve_summary(
    *,
    status: Optional[RunStatusDocument] = None,
    exit_code: Optional[int] = None,
    job_status: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
    log_text: str = "",
) -> DailyRunSummary:
    env = environ if environ is not None else os.environ
    job = (job_status or "").strip().lower()
    source = "run_status"

    if status is not None:
        outcome = status.outcome
        primary = status.primary_code
        ok_count = status.ok_count
        failed_count = status.failed_count
        skipped_count = status.skipped_count
        details = _status_detail_lines(status)
        if status.no_llm and primary in {CODE_SUCCESS, CODE_PARTIAL, CODE_UNKNOWN}:
            primary = CODE_MISSING_LLM
            if outcome == OUTCOME_SUCCESS:
                outcome = OUTCOME_FAILED
    else:
        source = "fallback"
        ok_count = 0
        failed_count = 0
        skipped_count = 0
        details = []
        outcome, primary = _fallback_classify(
            exit_code=exit_code,
            job_status=job,
            environ=env,
            log_text=log_text,
        )

    if job in {"cancelled", "timed_out"} and (
        status is None or status.outcome != OUTCOME_SKIPPED
    ):
        if primary not in {CODE_NON_TRADING_DAY}:
            primary = CODE_TIMEOUT
            outcome = OUTCOME_FAILED
            source = f"{source}+job_status"

    if outcome == OUTCOME_FAILED and primary == CODE_UNKNOWN:
        if not has_any_llm_secret(env):
            primary = CODE_MISSING_LLM
            source = f"{source}+env_llm"
        elif not has_watchlist_configured(env):
            primary = CODE_MISSING_WATCHLIST
            source = f"{source}+env_watchlist"
        else:
            hint = classify_log_hints(log_text)
            if hint:
                primary = hint
                source = f"{source}+logs"

    if exit_code not in (None, 0) and outcome == OUTCOME_SUCCESS and (
        status is None or status.outcome == OUTCOME_SUCCESS
    ):
        outcome = OUTCOME_FAILED
        if primary == CODE_SUCCESS:
            primary = CODE_UNKNOWN
        source = f"{source}+exit_code"

    notify = outcome == OUTCOME_FAILED

    return DailyRunSummary(
        outcome=outcome,
        primary_code=primary,
        ok_count=ok_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        headline_zh=format_cause_headline(primary, language="zh"),
        headline_en=format_cause_headline(primary, language="en"),
        action_zh=format_cause_action(primary, language="zh"),
        action_en=format_cause_action(primary, language="en"),
        notify=notify,
        source=source,
        details=details,
    )


def format_step_summary_markdown(summary: DailyRunSummary) -> str:
    emoji = {
        OUTCOME_SUCCESS: "✅",
        OUTCOME_SKIPPED: "⏭️",
        OUTCOME_PARTIAL: "⚠️",
        OUTCOME_FAILED: "❌",
    }.get(summary.outcome, "ℹ️")

    outcome_labels = {
        OUTCOME_SUCCESS: "成功 / Success",
        OUTCOME_SKIPPED: "已跳过 / Skipped",
        OUTCOME_PARTIAL: "部分成功 / Partial",
        OUTCOME_FAILED: "失败 / Failed",
    }
    label = outcome_labels.get(summary.outcome, summary.outcome)

    lines = [
        f"## {emoji} Daily Analysis 运行摘要 / Run summary",
        "",
        f"**结果 / Outcome:** {label}",
        f"**代码 / Code:** `{summary.primary_code}`",
        "",
        format_bilingual_cause_block(summary.primary_code),
        "",
        "### 计数 / Counts",
        f"- OK: **{summary.ok_count}**",
        f"- Failed / 失败: **{summary.failed_count}**",
        f"- Skipped / 跳过: **{summary.skipped_count}**",
        "",
    ]

    if summary.details:
        lines.append("### 明细 / Details")
        for item in summary.details[:40]:
            lines.append(f"- {sanitize_summary_text(item, max_length=240)}")
        lines.append("")

    lines.extend(
        [
            "### 说明 / Notes",
            "- 成功路径的报告推送逻辑未改变；本摘要仅解释运行结果。",
            "- Report push on the success path is unchanged; this summary only explains run outcome.",
            "- 失败短通知不会包含 Secret 明文；完整 traceback 请下载 logs Artifact。",
            "- Failure notifications never include secret values; download the logs artifact for full tracebacks.",
            f"- Classification source: `{sanitize_summary_text(summary.source, max_length=80)}`",
            "",
        ]
    )
    return "\n".join(lines)


def append_github_step_summary(markdown: str, *, summary_path: Optional[Path] = None) -> bool:
    try:
        path_raw = str(summary_path) if summary_path is not None else os.environ.get(
            "GITHUB_STEP_SUMMARY", ""
        )
        if not path_raw.strip():
            logger.info("GITHUB_STEP_SUMMARY not set; printing summary to stdout only")
            print(markdown)
            return False
        path = Path(path_raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(markdown)
            if not markdown.endswith("\n"):
                handle.write("\n")
        return True
    except Exception as exc:  # broad-exception: fallback_recorded - step summary must not fail the job
        log_safe_exception(
            logger,
            "Failed to write GitHub Step Summary",
            exc,
            error_code="actions_step_summary_write_failed",
            level=logging.WARNING,
        )
        try:
            print(markdown)
        except Exception:  # broad-exception: cleanup - best-effort stdout fallback after summary write failure
            pass
        return False


def failure_notify_enabled(
    environ: Optional[Mapping[str, str]] = None,
    *,
    system_error_channels_configured: Optional[bool] = None,
) -> bool:
    env = environ if environ is not None else os.environ
    explicit = (env.get("FAILURE_NOTIFY_ENABLED") or "").strip().lower()
    if explicit in {"0", "false", "no", "off"}:
        return False
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if system_error_channels_configured is not None:
        return bool(system_error_channels_configured)
    return bool((env.get("NOTIFICATION_SYSTEM_ERROR_CHANNELS") or "").strip())


def maybe_send_failure_notification(
    summary: DailyRunSummary,
    *,
    environ: Optional[Mapping[str, str]] = None,
    sender: Any = None,
) -> Dict[str, Any]:
    env = environ if environ is not None else os.environ
    if not summary.notify:
        return {"attempted": False, "sent": False, "reason": "outcome_not_failed"}
    if not failure_notify_enabled(env):
        return {
            "attempted": False,
            "sent": False,
            "reason": "notify_disabled_or_no_system_error_channels",
        }

    content = summary.short_notify_text()
    try:
        if sender is None:
            from src.notification import NotificationService

            sender = NotificationService()
        ok = bool(
            sender.send(
                content,
                route_type="system_error",
                severity="error",
            )
        )
        return {
            "attempted": True,
            "sent": ok,
            "reason": "sent" if ok else "dispatch_failed",
        }
    except Exception as exc:  # broad-exception: fallback_recorded - notify must never fail the run
        log_safe_exception(
            logger,
            "Failure notification degraded",
            exc,
            error_code="actions_failure_notify_degraded",
            level=logging.WARNING,
        )
        return {
            "attempted": True,
            "sent": False,
            "reason": "exception",
        }


def build_and_emit_summary(
    *,
    status_path: Optional[Path] = None,
    exit_code: Optional[int] = None,
    job_status: Optional[str] = None,
    log_path: Optional[Path] = None,
    write_step_summary: bool = True,
    notify_on_failure: bool = True,
    environ: Optional[Mapping[str, str]] = None,
    sender: Any = None,
) -> DailyRunSummary:
    env = environ if environ is not None else os.environ
    status = load_run_status(status_path)
    log_text = ""
    if log_path is not None and Path(log_path).is_file():
        try:
            log_text = Path(log_path).read_text(encoding="utf-8", errors="replace")[-40_000:]
        except Exception:  # broad-exception: cleanup - optional log read is fallback classification only
            log_text = ""
    else:
        log_text = _read_latest_log_tail()

    summary = resolve_summary(
        status=status,
        exit_code=exit_code,
        job_status=job_status,
        environ=env,
        log_text=log_text,
    )
    markdown = format_step_summary_markdown(summary)
    if write_step_summary:
        append_github_step_summary(markdown)
    else:
        print(markdown)

    if notify_on_failure:
        result = maybe_send_failure_notification(summary, environ=env, sender=sender)
        logger.info(
            "Failure notification result: attempted=%s sent=%s reason=%s",
            result.get("attempted"),
            result.get("sent"),
            result.get("reason"),
        )
    return summary


def _fallback_classify(
    *,
    exit_code: Optional[int],
    job_status: str,
    environ: Mapping[str, str],
    log_text: str,
) -> tuple[str, str]:
    if job_status in {"cancelled", "timed_out"}:
        return OUTCOME_FAILED, CODE_TIMEOUT

    hint = classify_log_hints(log_text)
    if hint == CODE_NON_TRADING_DAY:
        return OUTCOME_SKIPPED, CODE_NON_TRADING_DAY

    if not has_any_llm_secret(environ):
        if exit_code not in (None, 0) or job_status == "failure" or hint == CODE_MISSING_LLM:
            return OUTCOME_FAILED, CODE_MISSING_LLM

    if not has_watchlist_configured(environ) and (
        exit_code not in (None, 0) or job_status == "failure"
    ):
        return OUTCOME_FAILED, CODE_MISSING_WATCHLIST

    if hint:
        if hint == CODE_NON_TRADING_DAY:
            return OUTCOME_SKIPPED, hint
        return OUTCOME_FAILED, hint

    if exit_code not in (None, 0) or job_status == "failure":
        return OUTCOME_FAILED, CODE_UNKNOWN

    return OUTCOME_SUCCESS, CODE_SUCCESS


def _status_detail_lines(status: RunStatusDocument) -> List[str]:
    lines: List[str] = []
    for step in status.steps[:20]:
        cause = f" ({step.cause_code})" if step.cause_code else ""
        detail = f": {step.detail}" if step.detail else ""
        lines.append(
            sanitize_summary_text(
                f"step {step.name}: {step.status}{cause}{detail}",
                max_length=240,
            )
        )
    for stock in status.stocks[:30]:
        cause = f" ({stock.cause_code})" if stock.cause_code else ""
        lines.append(
            sanitize_summary_text(
                f"stock {stock.code}: {stock.status}{cause}",
                max_length=200,
            )
        )
    if status.messages:
        zh = status.messages.get("zh")
        en = status.messages.get("en")
        if zh:
            lines.append(sanitize_summary_text(f"msg_zh: {zh}", max_length=240))
        if en:
            lines.append(sanitize_summary_text(f"msg_en: {en}", max_length=240))
    return lines


def _sanitize_payload_strings(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize_payload_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload_strings(item) for item in value]
    if isinstance(value, str):
        return sanitize_summary_text(value, max_length=2000)
    return value


def _read_latest_log_tail() -> str:
    logs_dir = Path("logs")
    try:
        if not logs_dir.is_dir():
            return ""
        candidates = sorted(
            logs_dir.glob("stock_analysis_*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return ""
        return candidates[0].read_text(encoding="utf-8", errors="replace")[-40_000:]
    except Exception:  # broad-exception: cleanup - optional latest-log tail only
        return ""


def run_status_to_dict(document: RunStatusDocument) -> Dict[str, Any]:
    return document.to_dict()


def summary_to_dict(summary: DailyRunSummary) -> Dict[str, Any]:
    return asdict(summary)
