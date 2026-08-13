# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""One-click research asset package export (Issues #988 / #1140).

PR1: ZIP from persisted history (report, decision card, evidence refs, signals,
claims/outcomes when present, redacted reasoning trace). Full evidence-chain-v1
(#986/#127) is deferred; a later PR can add evidence_chain.json without rename.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from src.services.reasoning_trace_export_service import (
    build_reasoning_trace_package,
    redact_export_payload,
)
from src.services.report_mode import normalize_report_mode
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "research-pack-v1"
DEFAULT_MAX_ZIP_BYTES = 24 * 1024 * 1024
MIN_MAX_ZIP_BYTES = 1 * 1024 * 1024
MAX_MAX_ZIP_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_REPORT_CHARS = 800_000
DEFAULT_MAX_EVIDENCE_ITEMS = 64
DEFAULT_MAX_STRING_CHARS = 2_000
DISCLAIMER_EN = (
    "This research pack is generated from local analysis history for offline "
    "review and sharing. It is not investment advice. Supported credential "
    "shapes and local paths are redacted; treat the package as sensitive data."
)
DISCLAIMER_ZH = (
    "本研报资产包由本地分析历史生成，供离线阅读与分享，不构成投资建议。"
    "已知凭据形态与本地路径已脱敏；请仍按敏感资料保管。"
)
ProgressCallback = Callable[[str, str, Optional[str]], None]


class ResearchPackExportDisabled(RuntimeError):
    code = "research_pack_export_disabled"

    def __init__(self) -> None:
        super().__init__(self.code)


class ResearchPackNotFound(RuntimeError):
    code = "research_pack_not_found"

    def __init__(self, message: str = "research_pack_not_found") -> None:
        super().__init__(message)


class ResearchPackLimitError(RuntimeError):
    code = "research_pack_limit_exceeded"

    def __init__(self, message: str, *, error_code: str = "research_pack_limit_exceeded") -> None:
        super().__init__(message)
        self.code = error_code
        self.message = message


@dataclass
class ProgressStage:
    name: str
    status: str
    detail: Optional[str] = None


@dataclass(frozen=True)
class ResearchPackExportResult:
    """Export result. ``zip_bytes`` is empty when ``include_zip=False`` (JSON meta only)."""

    zip_bytes: bytes
    meta: Dict[str, Any]
    truncated: bool
    schema_version: str = SCHEMA_VERSION
    resolved_record_id: Optional[str] = None
    lookup_mode: Optional[str] = None
    progress: List[Dict[str, Any]] = field(default_factory=list)
    root_dirname: str = "research-pack"
    content_byte_length: int = 0
    zip_included: bool = True

    def to_json_envelope(self) -> Dict[str, Any]:
        # JSON mode reports content size when ZIP was not assembled.
        byte_length = len(self.zip_bytes) if self.zip_included else self.content_byte_length
        return {
            "schema_version": self.schema_version,
            "meta": self.meta,
            "truncated": self.truncated,
            "progress": self.progress,
            "byte_length": byte_length,
            "root_dirname": self.root_dirname,
            "zip_included": self.zip_included,
        }


def _resolve_runtime_config(config: Any = None) -> Any:
    if config is not None:
        return config
    try:
        from src.application_services import get_application_services
        return get_application_services().config
    except Exception as exc:  # broad-exception: fallback_recorded - config lookup falls back to safe defaults without failing export
        log_safe_exception(
            logger, "Research pack export config lookup failed; using safe defaults", exc,
            error_code="research_pack_export_config_lookup_failed", level=logging.DEBUG,
        )
        return None


def is_research_pack_export_enabled(config: Any = None) -> bool:
    resolved = _resolve_runtime_config(config)
    if resolved is None:
        return False
    return bool(getattr(resolved, "research_pack_export_enabled", False))


def get_research_pack_max_zip_bytes(config: Any = None) -> int:
    resolved = _resolve_runtime_config(config)
    if resolved is None:
        return DEFAULT_MAX_ZIP_BYTES
    raw = getattr(resolved, "research_pack_max_zip_bytes", DEFAULT_MAX_ZIP_BYTES)
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_MAX_ZIP_BYTES
    return min(MAX_MAX_ZIP_BYTES, max(MIN_MAX_ZIP_BYTES, value))


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _clip_str(value: Any, max_chars: int = DEFAULT_MAX_STRING_CHARS) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    text = str(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)] + "…"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False, sort_keys=True,
    ).encode("utf-8")


def _safe_dirname_part(value: Any, fallback: str = "unknown") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")[:48]
    return text or fallback


def _parse_record_json(history_service: Any, record: Any, field_name: str) -> Any:
    raw = getattr(record, field_name, None)
    parse = getattr(history_service, "_parse_diagnostic_json_field", None)
    if callable(parse):
        return parse(raw, field_name)
    if isinstance(raw, str):
        return json.loads(raw) if raw.strip() else None
    return raw


class _ProgressTracker:
    def __init__(self, callback: Optional[ProgressCallback] = None) -> None:
        self._callback = callback
        self.stages: List[ProgressStage] = []

    def start(self, name: str, detail: Optional[str] = None) -> None:
        self.stages.append(ProgressStage(name=name, status="running", detail=detail))
        if self._callback:
            self._callback(name, "running", detail)

    def complete(self, name: str, detail: Optional[str] = None) -> None:
        self._finish(name, "completed", detail)

    def skip(self, name: str, detail: Optional[str] = None) -> None:
        self._finish(name, "skipped", detail)

    def fail(self, name: str, detail: Optional[str] = None) -> None:
        self._finish(name, "failed", detail)

    def _finish(self, name: str, status: str, detail: Optional[str]) -> None:
        for stage in reversed(self.stages):
            if stage.name == name and stage.status == "running":
                stage.status = status
                if detail is not None:
                    stage.detail = detail
                break
        else:
            self.stages.append(ProgressStage(name=name, status=status, detail=detail))
        if self._callback:
            self._callback(name, status, detail)

    def as_list(self) -> List[Dict[str, Any]]:
        return [{"name": s.name, "status": s.status, "detail": s.detail} for s in self.stages]


def _slim_mapping(value: Mapping[str, Any], *, max_keys: int = 48) -> Dict[str, Any]:
    slim: Dict[str, Any] = {}
    not_calculable: List[str] = []
    for key, item in list(value.items())[:max_keys]:
        key_text = str(key)[:64]
        if isinstance(item, float) and not math.isfinite(item):
            not_calculable.append(key_text)
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            slim[key_text] = _clip_str(item, 500) if isinstance(item, str) else item
        elif isinstance(item, Mapping):
            nested: Dict[str, Any] = {}
            for nested_key, nested_value in list(item.items())[:16]:
                nested_key_text = str(nested_key)[:64]
                if isinstance(nested_value, float) and not math.isfinite(nested_value):
                    not_calculable.append(f"{key_text}.{nested_key_text}")
                    continue
                if isinstance(nested_value, (str, int, float, bool)) or nested_value is None:
                    nested[nested_key_text] = (
                        _clip_str(nested_value, 200)
                        if isinstance(nested_value, str)
                        else nested_value
                    )
            slim[key_text] = nested
        elif isinstance(item, list):
            entries: List[Any] = []
            for index, entry in enumerate(item[:16]):
                if isinstance(entry, float) and not math.isfinite(entry):
                    not_calculable.append(f"{key_text}[{index}]")
                    continue
                if isinstance(entry, (str, int, float, bool)) or entry is None:
                    entries.append(
                        _clip_str(entry, 200) if isinstance(entry, str) else entry
                    )
            slim[key_text] = entries
    if not_calculable:
        slim["not_calculable_fields"] = not_calculable
    return slim


def _extract_decision_card_markdown(report_markdown: str) -> Optional[str]:
    text = report_markdown or ""
    for pattern in (
        r"(?ms)^###\s*🃏[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)",
        r"(?ms)^###\s*Decision Card[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)",
        r"(?ms)^###\s*决策卡[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)",
    ):
        match = re.search(pattern, text)
        if match and match.group(0).strip():
            return match.group(0).strip()
    return None


def _extract_decision_card(*, record: Any, raw_result: Any, report_markdown: Optional[str], language: str) -> Dict[str, Any]:
    raw = _as_mapping(raw_result)
    dashboard = _as_mapping(raw.get("dashboard"))
    core = _as_mapping(dashboard.get("core_conclusion"))
    battle = _as_mapping(dashboard.get("battle_plan"))
    strategy = _as_mapping(dashboard.get("strategy_synthesis"))
    action = (
        raw.get("action") or raw.get("operation_advice") or getattr(record, "operation_advice", None)
        or core.get("operation_advice") or core.get("decision_type") or strategy.get("final_signal")
    )
    one_sentence = core.get("analysis_summary") or raw.get("analysis_summary") or getattr(record, "analysis_summary", None)
    confidence = core.get("confidence_level") or raw.get("confidence_level")
    key_risks = _as_list(core.get("key_risks") or battle.get("key_risks") or raw.get("key_risks"))
    watch = _as_list(core.get("watch_conditions") or battle.get("watch_conditions") or raw.get("watch_conditions"))
    stop_loss = battle.get("stop_loss") or raw.get("stop_loss") or getattr(record, "stop_loss", None)
    take_profit = battle.get("take_profit") or raw.get("take_profit") or getattr(record, "take_profit", None)
    risk = _as_mapping(
        dashboard.get("risk_manager")
        or raw.get("risk_gate_result")
        or dashboard.get("risk")
        or dashboard.get("risk_assessment")
        or raw.get("risk_assessment")
    )
    risk_conclusion = (
        risk.get("verdict")
        or risk.get("outcome")
        or risk.get("conclusion")
        or risk.get("risk_level")
        or risk.get("assessment")
    )
    clipped_risk_conclusion = _clip_str(risk_conclusion, 200)
    if not str(clipped_risk_conclusion or "").strip():
        clipped_risk_conclusion = None
    sentiment_score = getattr(record, "sentiment_score", None)
    if isinstance(sentiment_score, bool) or not isinstance(sentiment_score, (int, float)):
        sentiment_score = None
    elif isinstance(sentiment_score, float) and not math.isfinite(sentiment_score):
        sentiment_score = None
    card: Dict[str, Any] = {
        "action": _clip_str(action, 120),
        "one_sentence": _clip_str(one_sentence, 500),
        "confidence_level": _clip_str(confidence, 80),
        "trend_prediction": _clip_str(raw.get("trend_prediction") or getattr(record, "trend_prediction", None), 120),
        "sentiment_score": sentiment_score,
        "sentiment_score_status": (
            "available" if sentiment_score is not None else "not_calculable"
        ),
        "risk_conclusion": clipped_risk_conclusion,
        "risk_assessment_status": (
            "evaluated" if clipped_risk_conclusion is not None else "not_evaluated"
        ),
        "key_risks": [_clip_str(i, 200) for i in key_risks[:5] if i is not None],
        "watch_conditions": [_clip_str(i, 200) for i in watch[:5] if i is not None],
        "stop_loss": _clip_str(stop_loss, 80),
        "take_profit": _clip_str(take_profit, 80),
        "source": "history_projection",
        "language": language,
    }
    if report_markdown:
        excerpt = _extract_decision_card_markdown(report_markdown)
        if excerpt:
            card["markdown_excerpt"] = _clip_str(excerpt, 4_000)
            card["source"] = "report_markdown_section"
    return card


def render_brief_card_markdown(card: Mapping[str, Any], *, language: str = "en") -> str:
    zh = str(language).lower().startswith("zh")
    title = "决策卡" if zh else "Decision Card"
    labels = {
        "action": "方向" if zh else "Action",
        "one_sentence": "一句话结论" if zh else "One-sentence thesis",
        "confidence_level": "置信度" if zh else "Confidence",
        "trend_prediction": "趋势" if zh else "Trend",
        "sentiment_score": "情绪分" if zh else "Sentiment score",
        "risk_conclusion": "风险结论" if zh else "Risk conclusion",
        "key_risks": "关键风险" if zh else "Key risks",
        "watch_conditions": "观察/失效条件" if zh else "Watch / invalidation",
        "stop_loss": "止损" if zh else "Stop loss",
        "take_profit": "止盈" if zh else "Take profit",
    }
    lines = [f"# {title}", ""]
    for key in (
        "action",
        "one_sentence",
        "confidence_level",
        "trend_prediction",
        "sentiment_score",
        "risk_conclusion",
        "stop_loss",
        "take_profit",
    ):
        value = card.get(key)
        if value is None or value == "":
            if key == "sentiment_score" and card.get("sentiment_score_status") == "not_calculable":
                lines.append(
                    f"- **{labels[key]}**: {'不可计算' if zh else 'Not calculable'}"
                )
            elif key == "risk_conclusion" and card.get("risk_assessment_status") == "not_evaluated":
                lines.append(
                    f"- **{labels[key]}**: {'未评估' if zh else 'Not evaluated'}"
                )
            continue
        lines.append(f"- **{labels[key]}**: {value}")
    for list_key in ("key_risks", "watch_conditions"):
        items = card.get(list_key) or []
        if not isinstance(items, list) or not items:
            continue
        lines.append(f"- **{labels[list_key]}**:")
        for item in items:
            lines.append(f"  - {item}")
    if len(lines) <= 2:
        lines.append("_" + ("无可用决策字段" if zh else "No decision fields available") + "_")
    lines.extend(["", "---", DISCLAIMER_ZH if zh else DISCLAIMER_EN, ""])
    return "\n".join(lines)


def _extract_signals_snapshot(record: Any, raw_result: Any, context_snapshot: Any) -> Dict[str, Any]:
    raw = _as_mapping(raw_result)
    ctx = _as_mapping(context_snapshot)
    dashboard = _as_mapping(raw.get("dashboard"))
    for candidate in (
        raw.get("decision_signal"), dashboard.get("decision_signal"), ctx.get("decision_signal"),
        raw.get("decision_action"), dashboard.get("decision_action"),
    ):
        if isinstance(candidate, Mapping) and candidate:
            slim = _slim_mapping(candidate, max_keys=48)
            if slim:
                status = (
                    "not_calculable"
                    if set(slim) == {"not_calculable_fields"}
                    else "present"
                )
                return {
                    "status": status,
                    "signal": slim,
                    "projection": "persisted_decision_signal",
                }
    projected: Dict[str, Any] = {}
    for key in ("operation_advice", "action", "action_label", "sentiment_score", "trend_prediction"):
        value = raw.get(key)
        if value is None and hasattr(record, key):
            value = getattr(record, key, None)
        if value is not None:
            projected[key] = value if isinstance(value, (int, float, bool)) else _clip_str(value, 200)
    core = _as_mapping(dashboard.get("core_conclusion"))
    for key in ("decision_type", "operation_advice", "confidence_level", "analysis_summary"):
        if key in core and core[key] is not None:
            projected.setdefault(key, core[key] if isinstance(core[key], (int, float, bool)) else _clip_str(core[key], 200))
    strategy = _as_mapping(dashboard.get("strategy_synthesis"))
    if strategy.get("final_signal") is not None:
        projected.setdefault("final_signal", _clip_str(strategy.get("final_signal"), 80))
    if projected:
        projected["projection"] = "dashboard_fields"
        slim = _slim_mapping(projected, max_keys=48)
        status = (
            "not_calculable"
            if set(slim) == {"not_calculable_fields", "projection"}
            else "present"
        )
        return {"status": status, "signal": slim, "projection": "dashboard_fields"}
    return {"status": "missing", "signal": None, "missing_reason": "decision signal snapshot not present on this history record"}


def _extract_evidence_refs(*, diagnostics: Any, raw_result: Any, context_snapshot: Any, news_items: Sequence[Mapping[str, Any]], max_items: int = DEFAULT_MAX_EVIDENCE_ITEMS) -> Dict[str, Any]:
    refs: List[Dict[str, Any]] = []
    gaps: List[Dict[str, str]] = []
    diag = _as_mapping(diagnostics)
    raw = _as_mapping(raw_result)
    ctx = _as_mapping(context_snapshot)
    dashboard = _as_mapping(raw.get("dashboard"))
    for source_key, kind in (("provider_runs", "provider"), ("llm_runs", "llm"), ("pipeline_stages", "pipeline_stage"), ("data_sources", "data_source")):
        for item in _as_list(diag.get(source_key))[:16]:
            if not isinstance(item, Mapping):
                continue
            name = item.get("provider") or item.get("name") or item.get("source") or item.get("stage") or item.get("model")
            refs.append({
                "id": f"{kind}:{len(refs) + 1}", "kind": kind, "label": _clip_str(name, 120) or kind,
                "status": "present", "as_of": _clip_str(item.get("as_of") or item.get("timestamp"), 64),
                "summary": _clip_str(item.get("summary") or item.get("status") or item.get("message"), 300),
            })
            if len(refs) >= max_items:
                break
        if len(refs) >= max_items:
            break
    signal_attr = _as_mapping(dashboard.get("signal_attribution"))
    for weight in _as_list(signal_attr.get("weights") or signal_attr.get("items"))[:12]:
        if len(refs) >= max_items or not isinstance(weight, Mapping):
            continue
        label = weight.get("name") or weight.get("factor") or weight.get("source")
        refs.append({
            "id": f"signal_attr:{len(refs) + 1}", "kind": "signal_attribution",
            "label": _clip_str(label, 120) or "signal_attribution", "status": "present",
            "summary": _clip_str(weight.get("weight") or weight.get("reason"), 200),
        })
    for event in _as_list(diag.get("agent_events"))[:80]:
        if len(refs) >= max_items or not isinstance(event, Mapping):
            continue
        event_type = str(event.get("event_type") or event.get("type") or "")
        if "tool" not in event_type.lower() and not event.get("tool_name"):
            continue
        tool_name = event.get("tool_name") or event.get("name") or event_type
        refs.append({
            "id": f"tool:{len(refs) + 1}", "kind": "tool_call", "label": _clip_str(tool_name, 120) or "tool",
            "status": "present", "agent_role": _clip_str(event.get("agent_role") or event.get("role"), 64),
            "summary": _clip_str(event.get("summary") or event.get("status"), 200),
        })
    for news in list(news_items)[:12]:
        if len(refs) >= max_items or not isinstance(news, Mapping) or not news.get("title"):
            continue
        refs.append({
            "id": f"news:{len(refs) + 1}", "kind": "news", "label": _clip_str(news.get("title"), 200) or "news",
            "status": "present", "summary": _clip_str(news.get("snippet"), 300),
        })
    overview = _as_mapping(ctx.get("analysis_context_pack_overview") or ctx.get("overview"))
    data_quality = _as_mapping(overview.get("data_quality") or ctx.get("data_quality"))
    for item in _as_list(data_quality.get("validation_evidence"))[:12]:
        if len(refs) >= max_items or not isinstance(item, Mapping):
            continue
        refs.append({
            "id": f"quality:{len(refs) + 1}", "kind": "data_quality",
            "label": _clip_str(item.get("check") or item.get("name"), 120) or "data_quality",
            "status": _clip_str(item.get("status") or "present", 32) or "present",
            "summary": _clip_str(item.get("message") or item.get("detail"), 300),
        })
    if not refs:
        gaps.append({
            "code": "evidence_refs_empty",
            "message": "No provider, tool, news, or data-quality evidence was present on this history record.",
        })
    gaps.append({
        "code": "evidence_chain_v1_deferred",
        "message": "Full evidence-chain-v1 is deferred (#986/#127); this index is lightweight only.",
    })
    return {
        "schema_version": "research-pack-evidence-refs-v1",
        "status": "present" if refs else "empty",
        "count": len(refs),
        "items": refs,
        "gaps": gaps,
    }


def render_evidence_summary_markdown(evidence: Mapping[str, Any], *, language: str = "en") -> str:
    zh = str(language).lower().startswith("zh")
    lines = [f"# {'证据索引' if zh else 'Evidence index'}", ""]
    items = evidence.get("items") if isinstance(evidence.get("items"), list) else []
    if not items:
        lines.append("_No evidence references on this record; full evidence chain lands later._" if not zh else "_（本记录无可用证据引用）_")
    else:
        for item in items:
            if not isinstance(item, Mapping):
                continue
            label = item.get("label") or item.get("id") or "item"
            kind = item.get("kind") or "ref"
            summary = item.get("summary")
            status = item.get("status") or "present"
            line = f"- **[{kind}]** {label} ({status})"
            if summary:
                line += f" — {summary}"
            lines.append(line)
    gaps = evidence.get("gaps") if isinstance(evidence.get("gaps"), list) else []
    if gaps:
        lines.extend(["", f"## {'缺口' if zh else 'Gaps'}"])
        for gap in gaps:
            if isinstance(gap, Mapping):
                lines.append(f"- `{gap.get('code') or 'gap'}`: {gap.get('message') or ''}")
    lines.append("")
    return "\n".join(lines)


def _extract_claims_and_outcomes(raw_result: Any, context_snapshot: Any) -> Dict[str, Any]:
    raw = _as_mapping(raw_result)
    ctx = _as_mapping(context_snapshot)
    claims = None
    for key in ("prediction_claims", "claims", "financial_claims"):
        candidate = raw.get(key) or ctx.get(key)
        if isinstance(candidate, list) and candidate:
            claims = []
            for item in candidate[:32]:
                if isinstance(item, Mapping):
                    claims.append(_slim_mapping(item, max_keys=16))
                elif isinstance(item, str):
                    claims.append({"text": _clip_str(item, 300)})
            break
    outcomes = None
    for key in ("prediction_outcomes", "resolve_results", "outcomes", "claim_outcomes"):
        candidate = raw.get(key) or ctx.get(key)
        if isinstance(candidate, list) and candidate:
            outcomes = [_slim_mapping(item, max_keys=16) for item in candidate[:32] if isinstance(item, Mapping)]
            break
    data_hashes = {}
    for key in ("data_hash", "input_hash", "context_hash", "content_hash"):
        value = raw.get(key) or ctx.get(key)
        if isinstance(value, str) and value:
            data_hashes[key] = _clip_str(value, 128)
    return {
        "claims": claims, "claims_status": "present" if claims else "missing",
        "outcomes": outcomes, "outcomes_status": "present" if outcomes else "missing",
        "data_hashes": data_hashes or None,
    }


def render_pack_readme(*, language: str, root_dirname: str) -> str:
    zh = str(language).lower().startswith("zh")
    if zh:
        return "\n".join([
            f"# 研报资产包 `{root_dirname}`", "",
            "本包由 StockPulse 一键导出，可离线阅读主结论与证据索引。", "",
            "## 内容", "",
            "| 文件 | 说明 |", "| --- | --- |",
            "| `meta.json` | 元数据、进度、脱敏声明 |",
            "| `report.md` | 完整报告（脱敏） |",
            "| `brief-card.md` | 决策卡摘要 |",
            "| `signals.json` | 决策信号快照 |",
            "| `evidence-refs.json` / `evidence-summary.md` | 证据引用索引 |",
            "| `claims-outcomes.json` | 论断与结果（若有） |",
            "| `reasoning-trace.json` | 脱敏推理轨迹 |",
            "| `README.md` | 本说明 |", "",
            "## 隐私", "", DISCLAIMER_ZH, "",
            "## 后续", "", "完整证据链将在 #986 / #127 合入后增量接入。", "",
        ])
    return "\n".join([
        f"# Research pack `{root_dirname}`", "",
        "Generated by StockPulse one-click export for offline review.", "",
        "## Contents", "",
        "| File | Purpose |", "| --- | --- |",
        "| `meta.json` | Metadata, progress, redaction notice |",
        "| `report.md` | Full report (redacted) |",
        "| `brief-card.md` | Decision card summary |",
        "| `signals.json` | Decision signal snapshot |",
        "| `evidence-refs.json` / `evidence-summary.md` | Evidence index |",
        "| `claims-outcomes.json` | Claims and outcomes when present |",
        "| `reasoning-trace.json` | Redacted reasoning trace |",
        "| `README.md` | This file |", "",
        "## Privacy", "", DISCLAIMER_EN, "",
        "## Follow-up", "", "Full evidence-chain-v1 plugs in after #986 / #127 merge.", "",
    ])


class ResearchPackExportService:
    def __init__(self, *, history_service: Any = None, config: Any = None) -> None:
        self._history_service = history_service
        self._config = config

    @property
    def history_service(self) -> Any:
        if self._history_service is None:
            from src.services.history_service import HistoryService
            self._history_service = HistoryService()
        return self._history_service

    @property
    def config(self) -> Any:
        if self._config is None:
            self._config = _resolve_runtime_config(None)
        return self._config

    def ensure_enabled(self) -> None:
        if not is_research_pack_export_enabled(self.config):
            raise ResearchPackExportDisabled()

    def export_for_record(
        self,
        record_id: str,
        *,
        progress_callback: Optional[ProgressCallback] = None,
        language: Optional[str] = None,
        include_zip: bool = True,
    ) -> ResearchPackExportResult:
        """Assemble pack artifacts; set ``include_zip=False`` for metadata-only export."""
        self.ensure_enabled()
        tracker = _ProgressTracker(progress_callback)
        truncated = False
        truncation_notes: List[str] = []
        max_zip = get_research_pack_max_zip_bytes(self.config)

        tracker.start("resolve_record")
        record = self.history_service._resolve_record(record_id)
        if not record:
            tracker.fail("resolve_record", "not_found")
            raise ResearchPackNotFound(f"history record not found: {record_id}")
        context_snapshot = _parse_record_json(self.history_service, record, "context_snapshot")
        raw_result = _parse_record_json(self.history_service, record, "raw_result")
        diagnostics = context_snapshot.get("diagnostics") if isinstance(context_snapshot, Mapping) else None
        raw_meta = _as_mapping(raw_result.get("meta"))
        report_mode = normalize_report_mode(
            _clip_str(
                raw_meta.get("report_mode")
                or raw_meta.get("report_type")
                or getattr(record, "report_type", None),
                32,
            )
        )
        primary_id = getattr(record, "id", None)
        selected_record_id = str(primary_id) if primary_id is not None else str(record_id)
        selected_query_id = getattr(record, "query_id", None)
        stock_code = getattr(record, "code", None) or getattr(record, "stock_code", None)
        stock_name = getattr(record, "name", None) or getattr(record, "stock_name", None)
        created_at = getattr(record, "created_at", None)
        if isinstance(created_at, datetime):
            created_iso = created_at.astimezone(timezone.utc).isoformat()
            date_part = created_at.strftime("%Y%m%d")
        else:
            created_iso = str(created_at) if created_at else None
            date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        requested_pk = None
        try:
            requested_pk = int(record_id)
        except (TypeError, ValueError):
            pass
        resolved_pk = None
        if primary_id is not None:
            try:
                resolved_pk = int(primary_id)
            except (TypeError, ValueError):
                pass
        if requested_pk is not None and resolved_pk is not None and requested_pk == resolved_pk:
            lookup_mode = "by_record_id"
        else:
            lookup_mode = "latest_by_query_id" if selected_query_id else "by_record_id"
        tracker.complete("resolve_record", f"record_id={selected_record_id};lookup_mode={lookup_mode}")
        lang = language or (str(getattr(self.config, "report_language", "en") or "en") if self.config else "en")

        tracker.start("report")
        report_text = None
        report_missing = None
        try:
            report_text = self.history_service.get_markdown_report(record_id)
            if not report_text:
                report_missing = "markdown report empty"
                tracker.skip("report", report_missing)
            else:
                if len(report_text) > DEFAULT_MAX_REPORT_CHARS:
                    report_text = report_text[: DEFAULT_MAX_REPORT_CHARS - 1] + "…"
                    truncated = True
                    truncation_notes.append("report_chars")
                report_text = str(redact_export_payload(report_text))
                tracker.complete("report", f"chars={len(report_text)}")
        except Exception as exc:  # broad-exception: fallback_recorded - report generation failure is recorded and export continues with gaps
            log_safe_exception(logger, "Research pack report generation failed", exc,
                               error_code="research_pack_report_failed", context={"record_id": record_id}, level=logging.WARNING)
            report_missing = "markdown report generation failed"
            tracker.fail("report", report_missing)

        tracker.start("decision_card")
        card = redact_export_payload(_extract_decision_card(record=record, raw_result=raw_result, report_markdown=report_text, language=lang))
        if not isinstance(card, dict):
            card = {}
        brief_md = str(redact_export_payload(render_brief_card_markdown(card, language=lang)))
        tracker.complete("decision_card", f"source={card.get('source')}")

        tracker.start("signals")
        signals = redact_export_payload(_extract_signals_snapshot(record, raw_result, context_snapshot))
        if not isinstance(signals, dict):
            signals = {"status": "missing", "signal": None}
        tracker.complete("signals", str(signals.get("status")))

        tracker.start("evidence_refs")
        news_items: List[Mapping[str, Any]] = []
        try:
            news_raw = self.history_service.resolve_and_get_news(record_id, limit=12)
            if isinstance(news_raw, list):
                news_items = [i for i in news_raw if isinstance(i, Mapping)]
        except Exception as exc:  # broad-exception: fallback_recorded - news lookup failure is recorded and evidence export continues
            log_safe_exception(logger, "Research pack news lookup failed", exc,
                               error_code="research_pack_news_failed", context={"record_id": record_id}, level=logging.DEBUG)
        evidence = redact_export_payload(_extract_evidence_refs(
            diagnostics=diagnostics, raw_result=raw_result, context_snapshot=context_snapshot, news_items=news_items,
        ))
        if not isinstance(evidence, dict):
            evidence = {"status": "empty", "items": [], "gaps": [], "count": 0}
        evidence_md = str(redact_export_payload(render_evidence_summary_markdown(evidence, language=lang)))
        tracker.complete("evidence_refs", f"count={evidence.get('count', 0)}")

        tracker.start("claims_outcomes")
        claims_outcomes = redact_export_payload(_extract_claims_and_outcomes(raw_result, context_snapshot))
        if not isinstance(claims_outcomes, dict):
            claims_outcomes = {"claims_status": "missing", "outcomes_status": "missing", "claims": None, "outcomes": None}
        tracker.complete("claims_outcomes", f"claims={claims_outcomes.get('claims_status')}")

        tracker.start("reasoning_trace")
        trace_payload = None
        trace_missing = None
        try:
            diagnostic_trace_id = diagnostics.get("trace_id") if isinstance(diagnostics, Mapping) else None
            stable_run_id = str(diagnostic_trace_id or selected_query_id or f"history:{selected_record_id}")
            trace_result = build_reasoning_trace_package(
                run_id=stable_run_id, record_id=selected_record_id,
                query_id=str(selected_query_id) if selected_query_id is not None else None,
                lookup_key=str(record_id), lookup_mode=lookup_mode,
                stock_code=str(stock_code) if stock_code is not None else None,
                stock_name=str(stock_name) if stock_name is not None else None,
                diagnostics=diagnostics if isinstance(diagnostics, Mapping) else None,
                raw_result=raw_result if isinstance(raw_result, Mapping) else None,
                context_snapshot=context_snapshot if isinstance(context_snapshot, Mapping) else None,
                config=self.config, include_markdown=False, output_format="json",
            )
            trace_payload = trace_result.package
            if trace_result.truncated:
                truncated = True
                truncation_notes.append("reasoning_trace")
            tracker.complete("reasoning_trace", f"truncated={bool(trace_result.truncated)}")
        except Exception as exc:  # broad-exception: fallback_recorded - reasoning-trace projection failure is recorded and export continues with gaps
            log_safe_exception(logger, "Research pack reasoning-trace projection failed", exc,
                               error_code="research_pack_trace_failed", context={"record_id": record_id}, level=logging.WARNING)
            trace_missing = "reasoning_trace_projection_failed"
            tracker.fail("reasoning_trace", trace_missing)

        tracker.start("assemble_zip")
        root = f"research-pack-{_safe_dirname_part(stock_code, 'record')}-{_safe_dirname_part(date_part, 'date')}"
        artifacts: Dict[str, bytes] = {}
        if report_text is not None:
            artifacts["report.md"] = report_text.encode("utf-8")
        artifacts["brief-card.md"] = brief_md.encode("utf-8")
        artifacts["signals.json"] = _json_bytes(signals)
        artifacts["evidence-refs.json"] = _json_bytes(evidence)
        artifacts["evidence-summary.md"] = evidence_md.encode("utf-8")
        artifacts["claims-outcomes.json"] = _json_bytes(claims_outcomes)
        if trace_payload is not None:
            artifacts["reasoning-trace.json"] = _json_bytes(trace_payload)
        else:
            artifacts["reasoning-trace.json"] = _json_bytes({"status": "missing", "missing_reason": trace_missing or "unavailable"})
        artifacts["README.md"] = str(redact_export_payload(render_pack_readme(language=lang, root_dirname=root))).encode("utf-8")

        artifact_manifest = [
            {"name": n, "byte_length": len(d), "sha256": _sha256_bytes(d), "status": "present"}
            for n, d in sorted(artifacts.items())
        ]
        if report_text is None:
            artifact_manifest.append({
                "name": "report.md", "byte_length": None, "sha256": None, "status": "missing",
                "missing_reason": report_missing or "unavailable",
            })
        content_bytes = sum(len(d) for d in artifacts.values())
        if content_bytes > max_zip:
            tracker.fail("assemble_zip", f"content_bytes={content_bytes}>{max_zip}")
            raise ResearchPackLimitError(
                f"Research pack content exceeds max size ({content_bytes} > {max_zip} bytes).",
            )

        def _build_zip(meta_payload: Mapping[str, Any]) -> bytes:
            # Fixed entry timestamps keep archive output deterministic. Store meta.json
            # without compression so changing zip_byte_length cannot create a DEFLATE
            # size cycle; after the integer width stabilizes, the archive size does too.
            fixed_ts = (1980, 1, 1, 0, 0, 0)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for name, data in sorted(artifacts.items()):
                    info = zipfile.ZipInfo(filename=f"{root}/{name}", date_time=fixed_ts)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    zf.writestr(info, data)
                meta_info = zipfile.ZipInfo(filename=f"{root}/meta.json", date_time=fixed_ts)
                meta_info.compress_type = zipfile.ZIP_STORED
                zf.writestr(meta_info, _json_bytes(meta_payload))
            return buffer.getvalue()

        def _base_meta(*, zip_included_flag: bool, progress: List[Dict[str, Any]]) -> Dict[str, Any]:
            payload: Dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "record_id": selected_record_id,
                "query_id": str(selected_query_id) if selected_query_id is not None else None,
                "lookup_key": str(record_id),
                "lookup_mode": lookup_mode,
                "stock_code": _clip_str(stock_code, 32),
                "stock_name": _clip_str(stock_name, 80),
                "created_at": created_iso,
                "model_used": _clip_str(
                    _as_mapping(raw_result).get("model_used") if isinstance(raw_result, Mapping) else None,
                    80,
                ),
                "report_language": lang,
                "report_mode": report_mode,
                "share_mode": True,
                "redaction": {
                    "always_on": True,
                    "helper": "redact_export_payload",
                    "classes": [
                        "api_keys",
                        "bearer_tokens",
                        "credential_urls",
                        "local_paths",
                        "opaque_tokens",
                    ],
                },
                "disclaimer": DISCLAIMER_ZH if str(lang).lower().startswith("zh") else DISCLAIMER_EN,
                "truncated": truncated,
                "truncation_notes": truncation_notes,
                "limits": {
                    "max_zip_bytes": max_zip,
                    "max_report_chars": DEFAULT_MAX_REPORT_CHARS,
                    "max_evidence_items": DEFAULT_MAX_EVIDENCE_ITEMS,
                },
                "progress": progress,
                "artifacts": artifact_manifest,
                "content_byte_length": content_bytes,
                "zip_included": zip_included_flag,
                "evidence_chain_status": "deferred",
                "evidence_chain_note": "Full evidence-chain-v1 deferred until #986/#127 merge.",
            }
            redacted = redact_export_payload(payload)
            return redacted if isinstance(redacted, dict) else payload

        zip_bytes = b""
        if include_zip:
            tracker.complete("assemble_zip", f"files={len(artifacts)}")
            final_progress = tracker.as_list()
            meta = _base_meta(zip_included_flag=True, progress=final_progress)
            size_guess = 0
            for _ in range(16):
                meta["zip_byte_length"] = size_guess
                zip_bytes = _build_zip(meta)
                if len(zip_bytes) == size_guess:
                    break
                size_guess = len(zip_bytes)
            else:
                raise RuntimeError("research pack ZIP byte length did not converge")
            if len(zip_bytes) > max_zip:
                raise ResearchPackLimitError(
                    f"Research pack ZIP exceeds max size ({len(zip_bytes)} > {max_zip} bytes).",
                )
        else:
            tracker.complete("assemble_zip", f"files={len(artifacts)};zip_skipped=1")
            final_progress = tracker.as_list()
            meta = _base_meta(zip_included_flag=False, progress=final_progress)

        return ResearchPackExportResult(
            zip_bytes=zip_bytes,
            meta=meta,
            truncated=truncated,
            resolved_record_id=selected_record_id,
            lookup_mode=lookup_mode,
            progress=final_progress,
            root_dirname=root,
            content_byte_length=content_bytes,
            zip_included=include_zip,
        )
