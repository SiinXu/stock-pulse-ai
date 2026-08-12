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
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

DEFAULT_HIGH_DISAGREEMENT_THRESHOLD = 0.6
_MAX_ALERT_POINTS = 5
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
    candidates: List[Any] = []

    if isinstance(source, Mapping):
        candidates.append(source.get("disagreement_handling"))
        dashboard = source.get("dashboard")
        if isinstance(dashboard, Mapping):
            candidates.append(dashboard.get("disagreement_handling"))
            synthesis = dashboard.get("strategy_synthesis")
            if isinstance(synthesis, Mapping):
                candidates.append(synthesis.get("disagreement_handling"))
        synthesis = source.get("strategy_synthesis")
        if isinstance(synthesis, Mapping):
            candidates.append(synthesis.get("disagreement_handling"))
        raw_result = source.get("raw_result")
        if isinstance(raw_result, Mapping):
            nested = extract_disagreement_handling_record(raw_result)
            if nested is not None:
                return nested
    else:
        dashboard = getattr(source, "dashboard", None)
        if isinstance(dashboard, Mapping):
            candidates.append(dashboard.get("disagreement_handling"))
            synthesis = dashboard.get("strategy_synthesis")
            if isinstance(synthesis, Mapping):
                candidates.append(synthesis.get("disagreement_handling"))
        # Optional runtime attachment used by some pipeline paths.
        meta_handling = getattr(source, "disagreement_handling", None)
        candidates.append(meta_handling)

    for candidate in candidates:
        normalized = _normalize_record(candidate)
        if normalized is not None:
            return normalized
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
    if record.get("enabled") is False:
        return False

    threshold_value = _clamp_unit(threshold, DEFAULT_HIGH_DISAGREEMENT_THRESHOLD)
    score = _safe_float(record.get("disagreement_score"))
    if score is not None:
        return score >= threshold_value
    return bool(record.get("high_disagreement"))


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
    code = (stock_code or "").strip() or "unknown"
    name = (stock_name or "").strip() or code
    score = _safe_float(record.get("disagreement_score"))
    score_text = f"{score * 100:.0f}%" if score is not None else "n/a"
    verdict = str(record.get("verdict_mode") or "").strip() or "unknown"
    escalation = str(record.get("escalation") or "").strip() or "unknown"
    resolution = str(record.get("resolution_status") or "").strip() or "unknown"

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
    config: Any = None,
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
        if not bool(outbound_notifications_enabled):
            return False

        if config is None:
            from src.config import get_config

            config = get_config()

        if not bool(getattr(config, "high_disagreement_alerts_enabled", True)):
            return False

        record = extract_disagreement_handling_record(result)
        if record is None:
            return False

        threshold = getattr(
            config,
            "high_disagreement_threshold",
            DEFAULT_HIGH_DISAGREEMENT_THRESHOLD,
        )
        if not should_emit_high_disagreement_alert(record, threshold=float(threshold)):
            return False

        stock_code = str(getattr(result, "code", None) or "").strip() or "unknown"
        stock_name = getattr(result, "name", None)
        report_language = getattr(result, "report_language", None) or getattr(
            config, "report_language", "zh"
        )
        query_id = getattr(result, "query_id", None)
        alert_text = build_high_disagreement_alert_text(
            stock_code=stock_code,
            stock_name=str(stock_name) if stock_name else None,
            record=record,
            history_id=history_id,
            report_language=str(report_language or "zh"),
            config=config,
        )

        if notifier is None:
            from src.notification import NotificationService

            notification_service: Any = NotificationService()
        else:
            notification_service = notifier
        dedup_key = (
            f"high_disagreement:{stock_code}:"
            f"{history_id or query_id or 'unknown'}"
        )
        send_kwargs = {
            "route_type": "alert",
            "severity": "warning",
            "dedup_key": dedup_key,
            "cooldown_key": f"high_disagreement:{stock_code}",
        }

        send_with_results = getattr(notification_service, "send_with_results", None)
        if callable(send_with_results):
            dispatch_result = send_with_results(alert_text, **send_kwargs)
            success = bool(getattr(dispatch_result, "success", False))
            status = str(getattr(dispatch_result, "status", "") or "")
            logger.info(
                "High-disagreement alert dispatch finished",
                extra={
                    "stock_code": stock_code,
                    "history_id": history_id,
                    "success": success,
                    "status": status,
                    "disagreement_score": record.get("disagreement_score"),
                },
            )
            return success

        sent = bool(notification_service.send(alert_text, **send_kwargs))
        logger.info(
            "High-disagreement alert send finished",
            extra={
                "stock_code": stock_code,
                "history_id": history_id,
                "success": sent,
                "disagreement_score": record.get("disagreement_score"),
            },
        )
        return sent
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
    # Authoritative product record from #1205 always sets enabled=True when active.
    if value.get("enabled") is False:
        return None
    has_score = _safe_float(value.get("disagreement_score")) is not None
    has_flag = "high_disagreement" in value
    has_points = isinstance(value.get("points"), list)
    if not (has_score or has_flag or has_points):
        return None
    return dict(value)


def _public_points(raw_points: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_points, Sequence) or isinstance(raw_points, (str, bytes)):
        return []
    points: List[Dict[str, Any]] = []
    for item in list(raw_points)[:_MAX_ALERT_POINTS]:
        if not isinstance(item, Mapping):
            continue
        participants_raw = item.get("participants")
        participants: List[str] = []
        if isinstance(participants_raw, Sequence) and not isinstance(
            participants_raw, (str, bytes)
        ):
            participants = [
                str(p).strip()
                for p in participants_raw
                if str(p).strip()
            ][:12]
        points.append(
            {
                "source": str(item.get("source") or "unknown"),
                "kind": str(item.get("kind") or "unknown"),
                "severity": str(item.get("severity") or "medium"),
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
    if number != number:  # NaN
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
    host = str(getattr(config, "webui_host", "") or "").strip()
    if not host or host in {"0.0.0.0", "::", "[::]"}:
        return None
    port_raw = getattr(config, "webui_port", None)
    try:
        port = int(port_raw) if port_raw is not None else 8000
    except (TypeError, ValueError):
        port = 8000
    if port <= 0:
        return None
    # Local WebUI is HTTP-only; do not invent TLS settings.
    return f"http://{host}:{port}"


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
    "build_high_disagreement_alert_text",
    "build_history_entry_href",
    "extract_disagreement_handling_record",
    "maybe_send_high_disagreement_alert",
    "should_emit_high_disagreement_alert",
]
