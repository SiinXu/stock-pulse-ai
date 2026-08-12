# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Evidence-chain builder (Issues #986 / #127).

Read-only projection of persisted analysis history. Missing evidence is always
recorded explicitly. Reuses reasoning-trace redaction.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.schemas.evidence_chain import (
    EVIDENCE_CHAIN_SCHEMA_VERSION,
    ConclusionLink,
    EvidenceChainCoverage,
    EvidenceChainCoverageSource,
    EvidenceChainPackage,
    EvidenceChainRun,
    EvidenceGap,
    EvidenceItem,
    ReasoningStep,
)
from src.services.reasoning_trace_export_service import (
    build_config_fingerprint,
    redact_export_payload,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

SCHEMA_VERSION = EVIDENCE_CHAIN_SCHEMA_VERSION
NOT_RECORDED = (
    "full_agent_prompts_and_system_messages",
    "tool_arguments_without_deep_payload",
    "chat_provider_protocol_thinking_blocks",
    "ephemeral_sse_stream_events",
    "raw_provider_api_responses",
)
MISSING_AS_OF = "missing"
DEFAULT_MAX_STRING = 800
DEFAULT_MAX_CONCLUSIONS = 120
DEFAULT_MAX_EVIDENCE = 300
DEFAULT_MAX_STEPS = 120
_MISSING_NOTE_NO_EVIDENCE = (
    "No linked evidence was recorded for this conclusion; status is missing."
)
_MISSING_NOTE_NO_AS_OF = "as-of timestamp was not recorded"
_MISSING_NOTE_NO_SOURCE = "source_id was not recorded"


class EvidenceChainDisabled(RuntimeError):
    code = "evidence_chain_disabled"

    def __init__(self) -> None:
        super().__init__(self.code)


class EvidenceChainNotFound(RuntimeError):
    code = "evidence_chain_not_found"

    def __init__(self, message: str = "evidence_chain_not_found") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class EvidenceChainBuildResult:
    package: Dict[str, Any]
    schema_version: str = SCHEMA_VERSION

    def to_json_dict(self) -> Dict[str, Any]:
        return dict(self.package)

    def to_json_text(self) -> str:
        return json.dumps(self.package, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _resolve_runtime_config(config: Any = None) -> Any:
    if config is not None:
        return config
    try:
        from src.application_services import get_application_services
        return get_application_services().config
    except Exception as exc:  # broad-exception: fallback_recorded - Config lookup failure is logged before safe defaults are applied.
        log_safe_exception(
            logger,
            "Evidence chain config lookup failed; using safe defaults",
            exc,
            error_code="evidence_chain_config_lookup_failed",
            level=logging.DEBUG,
        )
        return None


def is_evidence_chain_enabled(config: Any = None) -> bool:
    resolved = _resolve_runtime_config(config)
    if resolved is None:
        return True
    return bool(getattr(resolved, "evidence_chain_enabled", True))


def _as_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _clip(value: Any, *, limit: int = DEFAULT_MAX_STRING) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _status_pair(present: bool) -> Dict[str, bool]:
    return {"present": present, "absent": not present}


def _recorded_run_evidence_status(value: Any) -> tuple[str, Optional[str]]:
    status = str(value or "").strip().lower()
    if status in {"ok", "success", "succeeded", "completed", "available", "present", "done"}:
        return "present", None
    if status in {"partial", "degraded", "fallback", "warning"}:
        return "partial", f"recorded source run was partial: status={status}"
    return "missing", f"recorded source run did not succeed: status={status or 'unknown'}"


def _with_as_of_status(
    status: str,
    reason: Optional[str],
    as_of: Optional[str],
) -> tuple[str, Optional[str]]:
    if status == "present" and not as_of:
        return "partial", _MISSING_NOTE_NO_AS_OF
    return status, reason or (None if as_of else _MISSING_NOTE_NO_AS_OF)


def _extract_report_strata(raw_result: Mapping[str, Any]) -> Dict[str, Any]:
    dashboard = _as_mapping(raw_result.get("dashboard"))
    strata = dashboard.get("report_strata")
    if not isinstance(strata, Mapping):
        strata = raw_result.get("report_strata")
    return _as_mapping(strata)


def _make_evidence_id(prefix: str, index: int) -> str:
    return f"{prefix}:{index:04d}"


def _build_data_source_evidence(diagnostics: Mapping[str, Any], *, start_index: int = 1) -> List[EvidenceItem]:
    items: List[EvidenceItem] = []
    idx = start_index
    for raw in _as_list(diagnostics.get("provider_runs"))[:80]:
        if not isinstance(raw, Mapping):
            continue
        provider = _clip(raw.get("provider"), limit=64) or "unknown_provider"
        data_type = _clip(raw.get("data_type"), limit=64)
        operation = _clip(raw.get("operation"), limit=64)
        status = _clip(raw.get("status"), limit=32) or "unknown"
        evidence_status, status_reason = _recorded_run_evidence_status(status)
        as_of = _clip(raw.get("as_of") or raw.get("timestamp") or raw.get("ts"), limit=64)
        evidence_status, status_reason = _with_as_of_status(
            evidence_status, status_reason, as_of
        )
        snippet_parts = [p for p in (provider, data_type, operation, f"status={status}") if p]
        items.append(EvidenceItem(
            evidence_id=_make_evidence_id("ds", idx),
            source_type="data_source",
            source_id=provider,
            snippet=" · ".join(snippet_parts),
            as_of=as_of,
            as_of_status="present" if as_of else MISSING_AS_OF,
            status=evidence_status,  # type: ignore[arg-type]
            missing_reason=status_reason,
        ))
        idx += 1
    for raw in _as_list(diagnostics.get("pipeline_stage_runs"))[:40]:
        if not isinstance(raw, Mapping):
            continue
        stage = _clip(raw.get("stage") or raw.get("name"), limit=64) or "stage"
        status = _clip(raw.get("status"), limit=32) or "unknown"
        evidence_status, status_reason = _recorded_run_evidence_status(status)
        as_of = _clip(raw.get("as_of") or raw.get("timestamp") or raw.get("ts"), limit=64)
        evidence_status, status_reason = _with_as_of_status(
            evidence_status, status_reason, as_of
        )
        items.append(EvidenceItem(
            evidence_id=_make_evidence_id("stage", idx),
            source_type="pipeline_stage",
            source_id=stage,
            snippet=f"{stage} status={status}",
            as_of=as_of,
            as_of_status="present" if as_of else MISSING_AS_OF,
            status=evidence_status,  # type: ignore[arg-type]
            missing_reason=status_reason,
        ))
        idx += 1
    for raw in _as_list(diagnostics.get("llm_runs"))[:40]:
        if not isinstance(raw, Mapping):
            continue
        model = _clip(raw.get("model"), limit=120) or "unknown_model"
        call_type = _clip(raw.get("call_type"), limit=64)
        status = _clip(raw.get("status"), limit=32) or "unknown"
        evidence_status, status_reason = _recorded_run_evidence_status(status)
        as_of = _clip(raw.get("as_of") or raw.get("timestamp") or raw.get("ts"), limit=64)
        evidence_status, status_reason = _with_as_of_status(
            evidence_status, status_reason, as_of
        )
        items.append(EvidenceItem(
            evidence_id=_make_evidence_id("llm", idx),
            source_type="model",
            source_id=model,
            snippet=" · ".join(p for p in (model, call_type, f"status={status}") if p),
            as_of=as_of,
            as_of_status="present" if as_of else MISSING_AS_OF,
            status=evidence_status,  # type: ignore[arg-type]
            missing_reason=status_reason,
        ))
        idx += 1
    return items


def _build_tool_call_evidence_and_steps(
    diagnostics: Mapping[str, Any],
    *,
    evidence_start: int = 1,
    step_start: int = 1,
) -> tuple[List[EvidenceItem], List[ReasoningStep]]:
    items: List[EvidenceItem] = []
    steps: List[ReasoningStep] = []
    eidx = evidence_start
    sidx = step_start
    events = _as_list(diagnostics.get("agent_events"))
    if not events:
        steps.append(ReasoningStep(
            step_id=_make_evidence_id("step", sidx),
            stage="agent_events",
            status="missing",
            missing_reason="diagnostics.agent_events not present on this history record",
        ))
        return items, steps

    by_role: Dict[str, List[Mapping[str, Any]]] = {}
    for raw in events[:200]:
        if not isinstance(raw, Mapping):
            continue
        role = _clip(raw.get("name") or raw.get("agent") or raw.get("role"), limit=64) or "agent"
        by_role.setdefault(role, []).append(raw)

    for role, role_events in by_role.items():
        tool_ids: List[str] = []
        for raw in role_events:
            event_type = str(raw.get("event_type") or raw.get("type") or "").lower()
            tool_name = raw.get("tool_name") or raw.get("tool") or raw.get("name")
            is_tool = "tool" in event_type or raw.get("tool_name") is not None or raw.get("tool_call_id") is not None
            if is_tool and tool_name:
                eid = _make_evidence_id("tool", eidx)
                eidx += 1
                status_raw = _clip(raw.get("status"), limit=32)
                evidence_status, status_reason = _recorded_run_evidence_status(status_raw)
                as_of = _clip(raw.get("timestamp") or raw.get("ts"), limit=64)
                evidence_status, status_reason = _with_as_of_status(
                    evidence_status, status_reason, as_of
                )
                has_ts = bool(raw.get("timestamp") or raw.get("ts"))
                items.append(EvidenceItem(
                    evidence_id=eid,
                    source_type="tool_call",
                    source_id=_clip(tool_name, limit=120),
                    snippet=_clip(f"tool={tool_name} status={status_raw or 'unknown'}", limit=200),
                    as_of=as_of,
                    as_of_status="present" if has_ts else MISSING_AS_OF,
                    status=evidence_status,  # type: ignore[arg-type]
                    missing_reason=status_reason or (None if has_ts else _MISSING_NOTE_NO_AS_OF),
                ))
                tool_ids.append(eid)
        last = role_events[-1] if role_events else {}
        output = _clip(
            last.get("summary") or last.get("message") or last.get("status") or f"{len(role_events)} event(s)",
            limit=500,
        )
        step_status, step_reason = _recorded_run_evidence_status(last.get("status"))
        steps.append(ReasoningStep(
            step_id=_make_evidence_id("step", sidx),
            stage=_clip(last.get("phase") or last.get("event_type") or "agent", limit=120) or "agent",
            role=role,
            input_refs=[],
            output_summary=output,
            model_ref=None,
            tool_call_ids=tool_ids[:32],
            status=step_status,  # type: ignore[arg-type]
            missing_reason=step_reason,
        ))
        sidx += 1
    return items, steps


def _conclusion_from_fact(
    fact: Mapping[str, Any],
    *,
    index: int,
    evidence_index: Dict[str, str],
) -> tuple[ConclusionLink, Optional[EvidenceItem]]:
    statement = _clip(fact.get("statement"), limit=1200) or "unspecified fact"
    source_id = _clip(fact.get("source_id"), limit=160)
    as_of = _clip(fact.get("as_of"), limit=64)
    as_of_status = "present" if as_of else MISSING_AS_OF
    refs: List[str] = []
    extra_item: Optional[EvidenceItem] = None
    source_reference_only = False

    if source_id and source_id in evidence_index:
        refs.append(evidence_index[source_id])
        source_reference_only = True
    elif source_id:
        eid = _make_evidence_id("strata", index)
        extra_item = EvidenceItem(
            evidence_id=eid,
            source_type="report_strata",
            source_id=source_id,
            snippet=statement[:200],
            as_of=as_of,
            as_of_status=as_of_status,  # type: ignore[arg-type]
            status="partial" if as_of else "missing",
            missing_reason=(
                "Source identifier was recorded, but the supporting source artifact was not persisted."
            ),
        )
        refs.append(eid)
        evidence_index[source_id] = eid
        source_reference_only = True

    if refs and source_reference_only:
        evidence_status = "partial" if as_of else "missing"
        missing_note = (
            "Source identifier/run metadata was recorded, but the direct supporting "
            "source artifact was not persisted."
        )
        if not as_of:
            missing_note = f"{missing_note} {_MISSING_NOTE_NO_AS_OF}."
    else:
        evidence_status = "missing"
        missing_note = _MISSING_NOTE_NO_EVIDENCE
        if not source_id:
            missing_note = f"{_MISSING_NOTE_NO_SOURCE}; {_MISSING_NOTE_NO_EVIDENCE}"

    link = ConclusionLink(
        conclusion_id=_make_evidence_id("fact", index),
        stratum="verified_fact",
        statement=statement,
        evidence_refs=refs,
        evidence_status=evidence_status,  # type: ignore[arg-type]
        missing_note=missing_note,
        as_of=as_of,
        as_of_status=as_of_status,  # type: ignore[arg-type]
        source_id=source_id,
    )
    return link, extra_item


def _conclusion_without_evidence(*, prefix: str, index: int, stratum: str, statement: str) -> ConclusionLink:
    return ConclusionLink(
        conclusion_id=_make_evidence_id(prefix, index),
        stratum=stratum,  # type: ignore[arg-type]
        statement=statement,
        evidence_refs=[],
        evidence_status="missing",
        missing_note=_MISSING_NOTE_NO_EVIDENCE,
        as_of=None,
        as_of_status=MISSING_AS_OF,
        source_id=None,
    )


def _build_conclusions(
    strata: Mapping[str, Any],
    raw_result: Mapping[str, Any],
    *,
    evidence_index: Dict[str, str],
    data_source_ids: Sequence[str],
) -> tuple[List[ConclusionLink], List[EvidenceItem], List[EvidenceGap]]:
    conclusions: List[ConclusionLink] = []
    extra_evidence: List[EvidenceItem] = []
    gaps: List[EvidenceGap] = []

    facts = _as_list(strata.get("verified_facts"))
    if not facts and not strata:
        gaps.append(EvidenceGap(
            path="dashboard.report_strata",
            status="missing",
            reason="report_strata not present on this history record",
        ))
    for i, raw in enumerate(facts[:DEFAULT_MAX_CONCLUSIONS], start=1):
        if not isinstance(raw, Mapping):
            continue
        link, extra = _conclusion_from_fact(raw, index=i, evidence_index=evidence_index)
        conclusions.append(link)
        if extra is not None:
            extra_evidence.append(extra)
        if link.evidence_status == "missing":
            gaps.append(EvidenceGap(
                path=f"conclusions.{link.conclusion_id}.evidence",
                status="missing",
                reason=link.missing_note or _MISSING_NOTE_NO_EVIDENCE,
                related_conclusion_ids=[link.conclusion_id],
            ))
        elif link.evidence_status == "partial":
            gaps.append(EvidenceGap(
                path=f"conclusions.{link.conclusion_id}.direct_evidence",
                status="partial",
                reason=link.missing_note or "Direct supporting artifact was not persisted",
                related_conclusion_ids=[link.conclusion_id],
            ))
        elif link.as_of_status == "missing":
            gaps.append(EvidenceGap(
                path=f"conclusions.{link.conclusion_id}.as_of",
                status="missing",
                reason=_MISSING_NOTE_NO_AS_OF,
                related_conclusion_ids=[link.conclusion_id],
            ))

    for kind_key, stratum, prefix in (
        ("model_inference", "model_inference", "inf"),
        ("risks_counter_evidence", "risk", "risk"),
    ):
        for i, item in enumerate(_as_list(strata.get(kind_key))[:40], start=1):
            statement = _clip(item, limit=1200)
            if not statement:
                continue
            if data_source_ids:
                link = ConclusionLink(
                    conclusion_id=_make_evidence_id(prefix, i),
                    stratum=stratum,  # type: ignore[arg-type]
                    statement=statement,
                    evidence_refs=list(data_source_ids[:8]),
                    evidence_status="partial",
                    missing_note="No direct evidence link; associated data-source runs listed as partial support.",
                    as_of=None,
                    as_of_status=MISSING_AS_OF,
                )
                gaps.append(EvidenceGap(
                    path=f"conclusions.{link.conclusion_id}.direct_evidence",
                    status="partial",
                    reason="No direct evidence_id link; partial data-source association only",
                    related_conclusion_ids=[link.conclusion_id],
                ))
            else:
                link = _conclusion_without_evidence(prefix=prefix, index=i, stratum=stratum, statement=statement)
                gaps.append(EvidenceGap(
                    path=f"conclusions.{link.conclusion_id}.evidence",
                    status="missing",
                    reason=_MISSING_NOTE_NO_EVIDENCE,
                    related_conclusion_ids=[link.conclusion_id],
                ))
            conclusions.append(link)

    for i, gap_raw in enumerate(_as_list(strata.get("missing_or_conflicts"))[:40], start=1):
        if not isinstance(gap_raw, Mapping):
            continue
        description = _clip(gap_raw.get("description"), limit=1200) or "unspecified gap"
        kind = _clip(gap_raw.get("kind"), limit=32) or "missing"
        source_ids = [_clip(s, limit=120) for s in _as_list(gap_raw.get("source_ids")) if _clip(s, limit=120)]
        refs = [evidence_index[s] for s in source_ids if s in evidence_index]
        conclusions.append(ConclusionLink(
            conclusion_id=_make_evidence_id("gap", i),
            stratum="gap",
            statement=f"[{kind}] {description}",
            evidence_refs=refs,
            evidence_status="linked" if refs else "missing",
            missing_note=None if refs else _MISSING_NOTE_NO_EVIDENCE,
            as_of=None,
            as_of_status=MISSING_AS_OF,
            source_id=source_ids[0] if source_ids else None,
        ))

    dashboard = _as_mapping(raw_result.get("dashboard"))
    core = _as_mapping(dashboard.get("core_conclusion"))
    strategy = _as_mapping(dashboard.get("strategy_synthesis"))
    final_signal = (
        _clip(strategy.get("final_signal"), limit=64)
        or _clip(core.get("decision_type"), limit=64)
        or _clip(raw_result.get("operation_advice"), limit=64)
    )
    analysis_summary = _clip(core.get("analysis_summary"), limit=1200) or _clip(raw_result.get("analysis_summary"), limit=1200)
    if final_signal or analysis_summary:
        statement = " · ".join(p for p in (final_signal, analysis_summary) if p) or "decision"
        if data_source_ids:
            link = ConclusionLink(
                conclusion_id=_make_evidence_id("decision", 1),
                stratum="decision",
                statement=statement,
                evidence_refs=list(data_source_ids[:12]),
                evidence_status="partial",
                missing_note="Decision linked to recorded data-source/tool runs only (partial).",
                as_of=None,
                as_of_status=MISSING_AS_OF,
            )
        else:
            link = _conclusion_without_evidence(prefix="decision", index=1, stratum="decision", statement=statement)
            gaps.append(EvidenceGap(
                path=f"conclusions.{link.conclusion_id}.evidence",
                status="missing",
                reason=_MISSING_NOTE_NO_EVIDENCE,
                related_conclusion_ids=[link.conclusion_id],
            ))
        conclusions.append(link)
    else:
        gaps.append(EvidenceGap(
            path="dashboard.core_conclusion",
            status="missing",
            reason="No decision/synthesis conclusion was present on this record",
        ))

    return conclusions, extra_evidence, gaps


def build_evidence_chain_package(
    *,
    run_id: str,
    record_id: Optional[str] = None,
    query_id: Optional[str] = None,
    lookup_key: Optional[str] = None,
    lookup_mode: Optional[str] = None,
    stock_code: Optional[str] = None,
    stock_name: Optional[str] = None,
    market: Optional[str] = None,
    model: Optional[str] = None,
    started_at: Optional[str] = None,
    diagnostics: Optional[Mapping[str, Any]] = None,
    raw_result: Optional[Mapping[str, Any]] = None,
    context_snapshot: Optional[Mapping[str, Any]] = None,
    config: Any = None,
) -> EvidenceChainBuildResult:
    diagnostics_map = _as_mapping(diagnostics)
    raw_map = _as_mapping(raw_result)
    context_map = _as_mapping(context_snapshot)
    if not diagnostics_map and isinstance(context_map.get("diagnostics"), Mapping):
        diagnostics_map = _as_mapping(context_map["diagnostics"])

    strata = _extract_report_strata(raw_map)
    ds_items = _build_data_source_evidence(diagnostics_map)
    tool_items, steps = _build_tool_call_evidence_and_steps(
        diagnostics_map, evidence_start=len(ds_items) + 1, step_start=1,
    )
    evidence_items: List[EvidenceItem] = list(ds_items) + list(tool_items)
    evidence_index: Dict[str, str] = {}
    for item in evidence_items:
        if item.source_id:
            evidence_index.setdefault(item.source_id, item.evidence_id)

    data_source_ids = [
        e.evidence_id for e in ds_items + tool_items if e.status in {"present", "partial"}
    ]
    conclusions, extra, gaps = _build_conclusions(
        strata, raw_map, evidence_index=evidence_index, data_source_ids=data_source_ids,
    )
    evidence_items.extend(extra)

    if not evidence_items:
        evidence_items.append(EvidenceItem(
            evidence_id="missing:0001",
            source_type="missing",
            source_id=None,
            snippet=None,
            as_of=None,
            as_of_status=MISSING_AS_OF,
            status="missing",
            missing_reason="No data-source, tool-call, or strata evidence was present on this history record",
        ))
        gaps.append(EvidenceGap(
            path="evidence_items",
            status="missing",
            reason="No evidence items could be projected from persisted diagnostics",
        ))

    def _cov(source: str, present: bool) -> EvidenceChainCoverageSource:
        return EvidenceChainCoverageSource(
            source=source, supported=True, **_status_pair(present),
            reasons=[] if present else ["not_present_on_record"],
        )

    coverage_sources = [
        _cov("dashboard.report_strata", bool(strata)),
        _cov("diagnostics.provider_runs", bool(_as_list(diagnostics_map.get("provider_runs")))),
        _cov("diagnostics.agent_events", bool(_as_list(diagnostics_map.get("agent_events")))),
        _cov("diagnostics.llm_runs", bool(_as_list(diagnostics_map.get("llm_runs")))),
        _cov("diagnostics.pipeline_stage_runs", bool(_as_list(diagnostics_map.get("pipeline_stage_runs")))),
    ]

    diagnostic_trace_id = _clip(diagnostics_map.get("trace_id"), limit=128) if diagnostics_map else None
    run = EvidenceChainRun(
        record_id=_clip(record_id, limit=128),
        query_id=_clip(query_id, limit=128),
        trace_id=diagnostic_trace_id,
        run_id=_clip(run_id, limit=128) or "unknown",
        lookup_key=_clip(lookup_key, limit=128),
        lookup_mode=lookup_mode if lookup_mode in {"primary_key", "latest_by_query_id"} else None,
        stock_code=_clip(stock_code, limit=32),
        stock_name=_clip(stock_name, limit=120),
        market=_clip(market, limit=32),
        model=_clip(model, limit=120),
        started_at=_clip(started_at, limit=64),
        exported_at=_utc_now_iso(),
        config_fingerprint=build_config_fingerprint(config),
    )

    package_model = EvidenceChainPackage(
        schema_version=SCHEMA_VERSION,
        run=run,
        conclusions=conclusions[:DEFAULT_MAX_CONCLUSIONS],
        evidence_items=evidence_items[:DEFAULT_MAX_EVIDENCE],
        reasoning_steps=steps[:DEFAULT_MAX_STEPS],
        gaps=gaps[:200],
        coverage=EvidenceChainCoverage(
            sources=coverage_sources,
            not_recorded=list(NOT_RECORDED),
            notes=(
                "Evidence chain is projected only from fields already persisted "
                "by the analysis pipeline. Missing fields are listed under gaps "
                "and coverage; they are never invented."
            ),
        ),
        truncated=(
            len(conclusions) > DEFAULT_MAX_CONCLUSIONS
            or len(evidence_items) > DEFAULT_MAX_EVIDENCE
            or len(steps) > DEFAULT_MAX_STEPS
        ),
    )
    raw_package = package_model.model_dump(mode="json")
    redacted = redact_export_payload(raw_package)
    if not isinstance(redacted, dict):
        raise ValueError("evidence chain redaction failed")
    EvidenceChainPackage.model_validate(redacted)
    return EvidenceChainBuildResult(package=redacted, schema_version=SCHEMA_VERSION)


def render_evidence_chain_markdown(package: Mapping[str, Any], *, language: str = "en") -> str:
    lang = (language or "en").strip().lower()
    zh = lang.startswith("zh")
    title = "证据与审计" if zh else "Evidence & Audit"
    conclusions = _as_list(package.get("conclusions"))
    evidence = _as_list(package.get("evidence_items"))
    gaps = _as_list(package.get("gaps"))
    steps = _as_list(package.get("reasoning_steps"))
    lines = [f"### 🔎 {title}", ""]
    if zh:
        lines.append(f"- 结论 {len(conclusions)} 条 · 证据项 {len(evidence)} 条 · 推理步骤 {len(steps)} 条 · 显式缺口 {len(gaps)} 条")
        lines.append("- 敏感值已脱敏；缺失项以 missing 标注，不会省略。")
    else:
        lines.append(f"- {len(conclusions)} conclusions · {len(evidence)} evidence items · {len(steps)} reasoning steps · {len(gaps)} explicit gaps")
        lines.append("- Sensitive values are redacted; missing evidence is marked missing, never omitted.")
    lines.append("")
    lines.append("#### " + ("结论 → 证据" if zh else "Conclusions → Evidence"))
    if not conclusions:
        lines.append(f"- **missing**: {'无结论可投影' if zh else 'No conclusions could be projected'}")
    for raw in conclusions[:40]:
        if not isinstance(raw, Mapping):
            continue
        statement = _clip(raw.get("statement"), limit=200) or "—"
        status = raw.get("evidence_status") or "missing"
        refs = _as_list(raw.get("evidence_refs"))
        as_of = raw.get("as_of") or ("缺失" if zh else "missing")
        ref_text = ", ".join(str(r) for r in refs[:6]) if refs else ("缺失" if zh else "missing")
        lines.append(f"- [{status}] {statement} ({'来源' if zh else 'refs'}: `{ref_text}` · as-of: {as_of})")
        note = raw.get("missing_note")
        if note:
            lines.append(f"  - _{_clip(note, limit=200)}_")
    lines.append("")
    lines.append("#### " + ("显式缺口" if zh else "Explicit Gaps"))
    if not gaps:
        lines.append(f"- {'无额外缺口' if zh else 'No additional gaps beyond linked statuses'}")
    for raw in gaps[:30]:
        if not isinstance(raw, Mapping):
            continue
        lines.append(f"- **{raw.get('status', 'missing')}** `{raw.get('path', '?')}`: {_clip(raw.get('reason'), limit=200) or '—'}")
    lines.append("")
    return "\n".join(lines)


class EvidenceChainService:
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
        if not is_evidence_chain_enabled(self.config):
            raise EvidenceChainDisabled()

    def build_for_record(self, record_id: str) -> EvidenceChainBuildResult:
        self.ensure_enabled()
        record = self.history_service._resolve_record(record_id)
        if not record:
            raise EvidenceChainNotFound(f"history record not found: {record_id}")

        parse = getattr(self.history_service, "_parse_diagnostic_json_field", None)
        if callable(parse):
            context_snapshot = parse(getattr(record, "context_snapshot", None), "context_snapshot")
            raw_result = parse(getattr(record, "raw_result", None), "raw_result")
        else:
            context_snapshot = getattr(record, "context_snapshot", None)
            raw_result = getattr(record, "raw_result", None)

        if isinstance(context_snapshot, str):
            context_snapshot = json.loads(context_snapshot) if context_snapshot.strip() else None
        if isinstance(raw_result, str):
            raw_result = json.loads(raw_result) if raw_result.strip() else None

        diagnostics = None
        if isinstance(context_snapshot, Mapping):
            diagnostics = context_snapshot.get("diagnostics")

        primary_id = getattr(record, "id", None)
        selected_record_id = str(primary_id) if primary_id is not None else str(record_id)
        selected_query_id = getattr(record, "query_id", None)
        diagnostic_trace_id = diagnostics.get("trace_id") if isinstance(diagnostics, Mapping) else None
        stable_run_id = str(diagnostic_trace_id or selected_query_id or f"history:{selected_record_id}")

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
        lookup_mode = "primary_key" if (requested_pk is not None and resolved_pk is not None and resolved_pk == requested_pk) else "latest_by_query_id"

        started_at = getattr(record, "created_at", None)
        if hasattr(started_at, "isoformat"):
            started_at = started_at.isoformat()

        return build_evidence_chain_package(
            run_id=stable_run_id,
            record_id=selected_record_id,
            query_id=str(selected_query_id) if selected_query_id is not None else None,
            lookup_key=str(record_id),
            lookup_mode=lookup_mode,
            stock_code=getattr(record, "code", None),
            stock_name=getattr(record, "name", None),
            market=getattr(record, "market", None) or getattr(record, "region", None),
            model=getattr(record, "model_used", None),
            started_at=str(started_at) if started_at is not None else None,
            diagnostics=diagnostics if isinstance(diagnostics, Mapping) else None,
            raw_result=raw_result if isinstance(raw_result, Mapping) else None,
            context_snapshot=context_snapshot if isinstance(context_snapshot, Mapping) else None,
            config=self.config,
        )
