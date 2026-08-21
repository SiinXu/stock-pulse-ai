# -*- coding: utf-8 -*-
"""High-disagreement alert emission for multi-agent analyses (Issue #134).

Consumes the structured ``disagreement_handling`` record produced by structured
disagreement handling (#1205). This module never recomputes disagreement scores
or re-classifies points; it only thresholds an existing record and routes an
alert through the existing notification pipeline (``route_type=alert``).

Ownership boundaries:
- Channel configuration / routing: existing NOTIFICATION_ALERT_CHANNELS (#931).
- In-app inbox projection of durable occurrences: #953 / related inbox coverage.
- Single channel or dispatch failure must never interrupt analysis persistence.
"""

from __future__ import annotations

import logging
import inspect
import ipaddress
import math
import re
from typing import Any, Dict, List, Mapping, Optional

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

logger = logging.getLogger(__name__)

DEFAULT_HIGH_DISAGREEMENT_THRESHOLD = 0.6
DISAGREEMENT_HANDLING_SCHEMA_VERSION = "disagreement-handling-v1"
_MAX_ALERT_POINTS = 5
_MAX_PARTICIPANTS = 12
_MAX_LABEL_LENGTH = 96
_MAX_STOCK_NAME_LENGTH = 128
_MAX_STOCK_CODE_LENGTH = 32
_MAX_QUERY_ID_LENGTH = 128
_MAX_RAW_RESULT_DEPTH = 4
_HISTORY_ENTRY_HREF_TEMPLATE = (
    "/research/analysis?segment=history&recordId={record_id}"
)


def extract_disagreement_handling_record(source: Any) -> Optional[Dict[str, Any]]:
    """Return a structured disagreement_handling record if present on *source*.

    Accepted locations (first match wins):
    - ``dashboard.disagreement_handling``
    - ``dashboard.strategy_synthesis.disagreement_handling``
    - ``strategy_synthesis.disagreement_handling`` (dict source)
    - ``raw_result.dashboard...`` when *source* is a mapping

    Returns ``None`` when no authoritative record is available. Does not invent
    disagreement from raw agent opinions or conflict_severity alone.
    """
    current = source
    visited: set[int] = set()
    for _ in range(_MAX_RAW_RESULT_DEPTH + 1):
        if id(current) in visited:
            return None
        visited.add(id(current))
        candidates: List[Any] = []
        if isinstance(current, Mapping):
            candidates.append(current.get("disagreement_handling"))
            dashboard = current.get("dashboard")
            if isinstance(dashboard, Mapping):
                candidates.append(dashboard.get("disagreement_handling"))
                synthesis = dashboard.get("strategy_synthesis")
                if isinstance(synthesis, Mapping):
                    candidates.append(synthesis.get("disagreement_handling"))
            synthesis = current.get("strategy_synthesis")
            if isinstance(synthesis, Mapping):
                candidates.append(synthesis.get("disagreement_handling"))
        else:
            dashboard = getattr(current, "dashboard", None)
            if isinstance(dashboard, Mapping):
                candidates.append(dashboard.get("disagreement_handling"))
                synthesis = dashboard.get("strategy_synthesis")
                if isinstance(synthesis, Mapping):
                    candidates.append(synthesis.get("disagreement_handling"))
            candidates.append(getattr(current, "disagreement_handling", None))

        for candidate in candidates:
            normalized = _normalize_record(candidate)
            if normalized is not None:
                return normalized

        if not isinstance(current, Mapping):
            break
        raw_result = current.get("raw_result")
        if not isinstance(raw_result, Mapping):
            break
        current = raw_result
    return None


def should_emit_high_disagreement_alert(
    record: Optional[Mapping[str, Any]],
    *,
    threshold: float = DEFAULT_HIGH_DISAGREEMENT_THRESHOLD,
) -> bool:
    """True when an existing record meets the alert threshold policy.

    Policy (score-primary so ``HIGH_DISAGREEMENT_THRESHOLD`` is effective):
    - When ``disagreement_score`` is present: alert only if ``score >= threshold``.
    - When score is absent: fall back to the record's ``high_disagreement`` flag
      so #1205 classifications without a numeric score are still consumable.
    """
    if not isinstance(record, Mapping) or not record:
        return False
    if record.get("schema_version") != DISAGREEMENT_HANDLING_SCHEMA_VERSION:
        return False
    if record.get("enabled") is not True:
        return False

    threshold_value = _clamp_unit(threshold, DEFAULT_HIGH_DISAGREEMENT_THRESHOLD)
    score = _safe_float(record.get("disagreement_score"))
    if score is not None:
        return score >= threshold_value
    return record.get("high_disagreement") is True


def build_history_entry_href(
    history_id: Optional[int],
    *,
    config: Any = None,
) -> Optional[str]:
    """Build history entry path, preferring absolute URL when WebUI host is usable."""
    if not isinstance(history_id, int) or isinstance(history_id, bool) or history_id <= 0:
        return None
    path = _HISTORY_ENTRY_HREF_TEMPLATE.format(record_id=history_id)
    base = _public_web_base(config)
    if base:
        return f"{base}{path}"
    return path


def build_high_disagreement_alert_text(
    *,
    stock_code: str,
    stock_name: Optional[str],
    record: Mapping[str, Any],
    history_id: Optional[int] = None,
    report_language: str = "zh",
    config: Any = None,
) -> str:
    """Build outbound alert Markdown from an existing disagreement record.

    Formats locally (same shape as ``NotificationBuilder.build_simple_alert``)
    to avoid importing the full notification facade for pure text construction.
    """
    labels = _alert_labels(report_language)
    code = _safe_text(stock_code, _MAX_STOCK_CODE_LENGTH, "unknown")
    name = _safe_text(stock_name, _MAX_STOCK_NAME_LENGTH, code)
    score = _safe_float(record.get("disagreement_score"))
    score_text = f"{score * 100:.0f}%" if score is not None else "n/a"
    verdict = _safe_text(record.get("verdict_mode"), _MAX_LABEL_LENGTH, "unknown")
    escalation = _safe_text(record.get("escalation"), _MAX_LABEL_LENGTH, "unknown")
    resolution = _safe_text(
        record.get("resolution_status"), _MAX_LABEL_LENGTH, "unknown"
    )

    lines: List[str] = [
        f"{labels['stock']}: {name} ({code})",
        f"{labels['score']}: {score_text}",
        f"{labels['verdict']}: {verdict}",
        f"{labels['escalation']}: {escalation}",
        f"{labels['resolution']}: {resolution}",
    ]

    points = _public_points(record.get("points"))
    if points:
        lines.append(f"{labels['points']}:")
        for point in points:
            source = point.get("source") or "unknown"
            kind = point.get("kind") or "unknown"
            severity = point.get("severity") or "medium"
            participants = point.get("participants") or []
            participant_text = (
                ", ".join(participants) if participants else "n/a"
            )
            lines.append(
                f"- [{source}] {severity}/{kind} · {labels['participants']}: {participant_text}"
            )
    else:
        lines.append(f"{labels['points']}: {labels['points_none']}")

    entry_href = build_history_entry_href(history_id, config=config)
    if entry_href:
        lines.append(f"{labels['entry']}: {entry_href}")
    else:
        lines.append(f"{labels['entry']}: {labels['entry_unavailable']}")

    title = f"{labels['title']} | {name} ({code})"
    # Match NotificationBuilder.build_simple_alert(warning) without importing it.
    return f"⚠️ **{title}**\n\n" + "\n".join(lines)


def maybe_send_high_disagreement_alert(
    result: Any,
    *,
    history_id: Optional[int] = None,
    config: Any,
    notifier: Any = None,
    outbound_notifications_enabled: bool = True,
) -> bool:
    """Emit a high-disagreement alert when an existing record exceeds threshold.

    Always fail-open: any extraction, formatting, or channel failure is logged
    and returns ``False`` without raising into the analysis pipeline.

    Respects the same outbound delivery intent as report notifications: when
    ``outbound_notifications_enabled`` is false (``--no-notify`` /
    ``send_notification=false`` / dry-run delivery skip), no alert is sent.
    """
    try:
        if outbound_notifications_enabled is not True:
            return False

        if config is None:
            return False

        if _static_config_value(
            config, "high_disagreement_alerts_enabled", True
        ) is not True:
            return False

        record = extract_disagreement_handling_record(result)
        if record is None:
            return False

        threshold = _static_config_value(
            config,
            "high_disagreement_threshold",
            DEFAULT_HIGH_DISAGREEMENT_THRESHOLD,
        )
        if not should_emit_high_disagreement_alert(record, threshold=threshold):
            return False

        stock_code = _safe_text(
            getattr(result, "code", None), _MAX_STOCK_CODE_LENGTH, "unknown"
        )
        stock_name = getattr(result, "name", None)
        report_language = getattr(result, "report_language", None) or getattr(
            config, "report_language", "zh"
        )
        query_id = getattr(result, "query_id", None)
        alert_text = build_high_disagreement_alert_text(
            stock_code=stock_code,
            stock_name=stock_name,
            record=record,
            history_id=history_id,
            report_language=_safe_text(report_language, 16, "zh"),
            config=config,
        )

        if notifier is None:
            from src.notification import NotificationService

            notification_service: Any = NotificationService()
        else:
            notification_service = notifier
        dedup_key = (
            f"high_disagreement:{stock_code}:"
            f"{history_id or _safe_text(query_id, _MAX_QUERY_ID_LENGTH, 'unknown')}"
        )
        send_kwargs = {
            "route_type": "alert",
            "severity": "warning",
            "dedup_key": dedup_key,
            "cooldown_key": f"high_disagreement:{stock_code}",
        }

        from src.notification_parts.dispatch import (
            dispatch_channel_summaries,
            invoke_notifier_dispatch,
        )

        dispatch_result = invoke_notifier_dispatch(
            notification_service,
            alert_text,
            **send_kwargs,
        )
        success = bool(getattr(dispatch_result, "success", False))
        status = str(getattr(dispatch_result, "status", "") or "")
        if status == "partial_failed":
            logger.warning(
                "High-disagreement alert dispatch finished status=%s channels=%s",
                sanitize_diagnostic_text(
                    getattr(dispatch_result, "status", None)
                ),
                sanitize_diagnostic_text(
                    dispatch_channel_summaries(dispatch_result)
                ),
            )
        else:
            logger.info("High-disagreement alert dispatch finished")
        return success
    except Exception as exc:  # broad-exception: fallback_recorded - alert must not interrupt analysis
        log_safe_exception(
            logger,
            "High-disagreement alert emission failed",
            exc,
            error_code="high_disagreement_alert_failed",
            level=logging.WARNING,
            context={
                "stock_code": getattr(result, "code", None),
                "history_id": history_id,
            },
        )
        return False


def _normalize_record(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping) or not value:
        return None
    # Only consume the versioned public contract from #1205. A same-named legacy
    # mapping must not trigger outbound delivery.
    if value.get("schema_version") != DISAGREEMENT_HANDLING_SCHEMA_VERSION:
        return None
    if value.get("enabled") is not True:
        return None
    has_score = _safe_float(value.get("disagreement_score")) is not None
    has_flag = "high_disagreement" in value
    has_points = isinstance(value.get("points"), list)
    if not (has_score or has_flag or has_points):
        return None
    return dict(value)


def _public_points(raw_points: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_points, list):
        return []
    points: List[Dict[str, Any]] = []
    for item in raw_points[:_MAX_ALERT_POINTS]:
        if not isinstance(item, Mapping):
            continue
        participants_raw = item.get("participants")
        participants: List[str] = []
        if isinstance(participants_raw, list):
            participants = [
                _safe_text(p, _MAX_LABEL_LENGTH, "")
                for p in participants_raw
                if _safe_text(p, _MAX_LABEL_LENGTH, "")
            ][:_MAX_PARTICIPANTS]
        points.append(
            {
                "source": _safe_text(
                    item.get("source"), _MAX_LABEL_LENGTH, "unknown"
                ),
                "kind": _safe_text(item.get("kind"), _MAX_LABEL_LENGTH, "unknown"),
                "severity": _safe_text(
                    item.get("severity"), _MAX_LABEL_LENGTH, "medium"
                ),
                "participants": participants,
            }
        )
    return points


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _clamp_unit(value: Any, default: float) -> float:
    number = _safe_float(value)
    if number is None:
        return float(default)
    return max(0.0, min(1.0, number))


def _public_web_base(config: Any) -> Optional[str]:
    """Return an absolute origin when WEBUI_HOST is a usable non-bind-all host."""
    if config is None:
        return None
    host = _safe_text(_static_config_value(config, "webui_host", ""), 253, "")
    if not host or host in {"0.0.0.0", "::", "[::]"}:
        return None
    formatted_host = _validated_web_host(host)
    if formatted_host is None:
        return None
    port_raw = _static_config_value(config, "webui_port", None)
    if isinstance(port_raw, bool):
        return None
    try:
        port = int(port_raw) if port_raw is not None else 8000
    except (TypeError, ValueError):
        return None
    if not 1 <= port <= 65535:
        return None
    # Local WebUI is HTTP-only; do not invent TLS settings.
    return f"http://{formatted_host}:{port}"


def _static_config_value(config: Any, name: str, default: Any) -> Any:
    """Read declared config only, without accepting dynamic mock attributes."""
    if config is None:
        return default
    try:
        declared = inspect.getattr_static(config, name)
    except AttributeError:
        return default
    if isinstance(declared, property):
        try:
            return declared.__get__(config, type(config))
        except (AttributeError, TypeError):
            return default
    return declared


def _safe_text(value: Any, max_length: int, default: str) -> str:
    """Return bounded, single-line text without invoking arbitrary containers."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return default
    if isinstance(value, float) and not math.isfinite(value):
        return default
    text = " ".join(str(value).split()).strip()
    if not text:
        return default
    return text[:max_length]


def _validated_web_host(host: str) -> Optional[str]:
    """Return an origin-safe host, bracketing IPv6 addresses when needed."""
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        if len(candidate) > 253 or not re.fullmatch(
            r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*",
            candidate,
        ):
            return None
        return candidate
    if address.is_unspecified:
        return None
    return f"[{candidate}]" if address.version == 6 else candidate


def _alert_labels(report_language: str) -> Dict[str, str]:
    language = str(report_language or "zh").strip().lower()
    if language.startswith("zh"):
        return {
            "title": "高分歧告警",
            "stock": "标的",
            "score": "分歧分数",
            "verdict": "裁决模式",
            "escalation": "升级",
            "resolution": "解决状态",
            "points": "分歧要点",
            "points_none": "（无记录）",
            "participants": "参与方",
            "entry": "入口",
            "entry_unavailable": "历史记录不可用",
        }
    return {
        "title": "High Disagreement Alert",
        "stock": "Stock",
        "score": "Disagreement score",
        "verdict": "Verdict mode",
        "escalation": "Escalation",
        "resolution": "Resolution",
        "points": "Disagreement points",
        "points_none": "(none recorded)",
        "participants": "participants",
        "entry": "Entry",
        "entry_unavailable": "history record unavailable",
    }


__all__ = [
    "DEFAULT_HIGH_DISAGREEMENT_THRESHOLD",
    "DISAGREEMENT_HANDLING_SCHEMA_VERSION",
    "build_high_disagreement_alert_text",
    "build_history_entry_href",
    "extract_disagreement_handling_record",
    "maybe_send_high_disagreement_alert",
    "should_emit_high_disagreement_alert",
]
