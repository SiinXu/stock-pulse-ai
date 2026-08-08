# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Reasoning-trace export (Issue #135 / T03).

Builds a machine-readable ``reasoning-trace-v1`` package from *already recorded*
analysis history diagnostics and dashboard synthesis fields. This module is a
read-only consumer: it does not change agent recording behaviour.

Security contract (same redaction path as security audit):
- Every export payload is passed through ``redact_sensitive_data``.
- API keys, tokens, credentialed base URLs, and local path leakage must not
  appear in the exported package.
- Export is opt-in via ``REASONING_TRACE_EXPORT_ENABLED`` (default off).
- Oversized packages are truncated with an explicit ``truncated`` marker.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

import re

from src.utils.sanitize import log_safe_exception, redact_sensitive_data

logger = logging.getLogger(__name__)

# Same absolute-path class scrubbed by run diagnostics (exported hard rule).
_LOCAL_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![\w:/.-])(?:/(?:home|Users|root|var|tmp|opt|etc)/[^\s,;]+|[A-Za-z]:\\[^\s,;]+)"
)

SCHEMA_VERSION = "reasoning-trace-v1"
DEFAULT_MAX_EXPORT_CHARS = 500_000
DEFAULT_MAX_AGENT_EVENTS = 200
DEFAULT_MAX_TOOL_CALLS_PER_AGENT = 50
DEFAULT_MAX_STRING_CHARS = 4_000

# Coverage inventory for delivery notes / docs. Keys are stable identifiers.
COVERAGE_RECORDED = (
    "run_meta",
    "diagnostics.agent_events",
    "diagnostics.provider_runs",
    "diagnostics.llm_runs",
    "diagnostics.pipeline_stage_runs",
    "dashboard.committee_deliberation",
    "dashboard.strategy_synthesis",
    "dashboard.core_conclusion",
)
COVERAGE_NOT_RECORDED = (
    "full_agent_prompts_and_system_messages",
    "tool_arguments_without_deep_payload",
    "chat_provider_protocol_thinking_blocks",
    "ephemeral_sse_stream_events",
    "raw_provider_api_responses",
)


class ReasoningTraceExportDisabled(RuntimeError):
    """Raised when export is requested while the feature flag is off."""

    code = "reasoning_trace_export_disabled"

    def __init__(self) -> None:
        super().__init__(self.code)


class ReasoningTraceNotFound(RuntimeError):
    """Raised when the history record (or required payload) cannot be resolved."""

    code = "reasoning_trace_not_found"

    def __init__(self, message: str = "reasoning_trace_not_found") -> None:
        super().__init__(message)
        self.code = "reasoning_trace_not_found"


@dataclass(frozen=True)
class ReasoningTraceExportResult:
    """Exported package plus optional human-readable markdown."""

    package: Dict[str, Any]
    markdown: str
    truncated: bool
    schema_version: str = SCHEMA_VERSION

    def to_json_dict(self) -> Dict[str, Any]:
        return dict(self.package)


def _resolve_runtime_config(config: Any = None) -> Any:
    """Return an injected config or the composition-root config (no bare get_config)."""
    if config is not None:
        return config
    try:
        from src.application_services import get_application_services

        return get_application_services().config
    except Exception as exc:  # broad-exception: fallback_recorded - Config lookup must not enable export accidentally.
        log_safe_exception(
            logger,
            "Reasoning trace export config lookup failed; using safe defaults",
            exc,
            error_code="reasoning_trace_export_config_lookup_failed",
            level=logging.DEBUG,
        )
        return None


def is_reasoning_trace_export_enabled(config: Any = None) -> bool:
    """Return whether export is enabled (default False — zero impact)."""
    resolved = _resolve_runtime_config(config)
    if resolved is None:
        return False
    return bool(getattr(resolved, "reasoning_trace_export_enabled", False))


def resolve_max_export_chars(config: Any = None) -> int:
    """Return the hard character budget for a single export package."""
    resolved = _resolve_runtime_config(config)
    if resolved is None:
        return DEFAULT_MAX_EXPORT_CHARS
    raw = getattr(resolved, "reasoning_trace_export_max_chars", DEFAULT_MAX_EXPORT_CHARS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_EXPORT_CHARS
    return max(10_000, value)


def build_config_fingerprint(config: Any = None) -> str:
    """Stable non-secret fingerprint of analysis-relevant config toggles."""
    keys = (
        "agent_observability_enabled",
        "agent_observability_deep_payload",
        "agent_multi_strategy_deliberation",
        "agent_risk_override",
        "generation_backend",
        "report_type",
        "report_language",
    )
    payload: Dict[str, Any] = {}
    if config is not None:
        for key in keys:
            if hasattr(config, key):
                payload[key] = getattr(config, key)
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return digest[:16]


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _clip_text(value: Any, *, limit: int = DEFAULT_MAX_STRING_CHARS) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 16)] + "…[truncated]"


def _safe_json_size(payload: Any) -> int:
    try:
        return len(json.dumps(payload, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return 0


def _redact_local_paths(value: Any, *, depth: int = 0, seen: Optional[set[int]] = None) -> Any:
    """Replace absolute local filesystem paths after secret redaction."""
    if seen is None:
        seen = set()
    if depth > 20:
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _LOCAL_ABSOLUTE_PATH_RE.sub("<redacted-path>", value)
    obj_id = id(value)
    if obj_id in seen:
        return value
    if isinstance(value, Mapping):
        seen.add(obj_id)
        return {
            str(k): _redact_local_paths(v, depth=depth + 1, seen=seen)
            for k, v in value.items()
        }
    if isinstance(value, list):
        seen.add(obj_id)
        return [_redact_local_paths(item, depth=depth + 1, seen=seen) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_local_paths(item, depth=depth + 1, seen=seen) for item in value)
    return value


def redact_export_payload(value: Any) -> Any:
    """Hard boundary for exports: audit-grade secret redaction + local path scrubbing.

    Secret redaction reuses ``redact_sensitive_data`` (same helper as
    ``SecurityAuditService``). Absolute local paths are scrubbed afterwards so
    user home directories never leave the process boundary.
    """
    redacted = redact_sensitive_data(value)
    return _redact_local_paths(redacted)


def _extract_tool_calls(event: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Project tool-related agent events into a compact call summary."""
    event_type = str(event.get("event_type") or event.get("type") or "")
    name = str(event.get("name") or event.get("tool") or "")
    if "tool" not in event_type.lower() and not name:
        attrs = _as_mapping(event.get("attrs"))
        if not attrs.get("tool") and not attrs.get("tool_name"):
            return []
        name = str(attrs.get("tool") or attrs.get("tool_name") or name)

    if "tool" not in event_type.lower() and "tool" not in name.lower():
        # Still include explicit tool_start / tool_end style names.
        if event_type not in {
            "agent.tool_start",
            "agent.tool_end",
            "tool_start",
            "tool_end",
            "tool",
        }:
            attrs = _as_mapping(event.get("attrs"))
            if not any(k in attrs for k in ("tool", "tool_name", "tool_call_id")):
                return []

    attrs = _as_mapping(event.get("attrs"))
    entry = {
        "name": _clip_text(name or attrs.get("tool") or attrs.get("tool_name") or "tool", limit=120),
        "status": _clip_text(event.get("status") or attrs.get("status"), limit=64),
        "duration_ms": event.get("duration_ms"),
        "step": event.get("step") or attrs.get("step"),
        "sequence": event.get("sequence"),
        "timestamp": event.get("timestamp"),
    }
    # Deep payloads may carry sanitized argument previews; never re-expand secrets.
    for key in ("tool_call_id", "error_code"):
        if key in attrs:
            entry[key] = _clip_text(attrs.get(key), limit=120)
    return [{k: v for k, v in entry.items() if v is not None}]


def _group_agents_from_events(
    agent_events: Sequence[Any],
    *,
    max_events: int = DEFAULT_MAX_AGENT_EVENTS,
) -> List[Dict[str, Any]]:
    """Group observability events into per-agent role timelines."""
    agents: Dict[str, Dict[str, Any]] = {}
    ordered_roles: List[str] = []

    for index, raw in enumerate(list(agent_events)[:max_events]):
        if not isinstance(raw, Mapping):
            continue
        event = dict(raw)
        attrs = _as_mapping(event.get("attrs"))
        role = str(
            attrs.get("agent")
            or attrs.get("agent_name")
            or attrs.get("role")
            or event.get("phase")
            or event.get("name")
            or "unknown"
        )
        role = _clip_text(role, limit=64) or "unknown"
        if role not in agents:
            agents[role] = {
                "role": role,
                "input_summary": None,
                "tool_calls": [],
                "output_opinion": None,
                "events": [],
            }
            ordered_roles.append(role)

        bucket = agents[role]
        summary_event = {
            "event_type": event.get("event_type") or event.get("type"),
            "name": _clip_text(event.get("name"), limit=120),
            "status": event.get("status"),
            "timestamp": event.get("timestamp"),
            "duration_ms": event.get("duration_ms"),
            "sequence": event.get("sequence", index),
            "phase": event.get("phase"),
        }
        bucket["events"].append({k: v for k, v in summary_event.items() if v is not None})

        for call in _extract_tool_calls(event):
            if len(bucket["tool_calls"]) < DEFAULT_MAX_TOOL_CALLS_PER_AGENT:
                bucket["tool_calls"].append(call)

        # Prefer decision/model_end style text as opinion when present.
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        opinion_candidate = (
            attrs.get("signal")
            or attrs.get("decision")
            or attrs.get("opinion")
            or payload.get("signal")
            or payload.get("decision")
        )
        if opinion_candidate is not None and (
            "decision" in event_type or bucket["output_opinion"] is None
        ):
            bucket["output_opinion"] = _clip_text(opinion_candidate, limit=500)

        input_candidate = attrs.get("input_summary") or attrs.get("summary")
        if input_candidate and bucket["input_summary"] is None:
            bucket["input_summary"] = _clip_text(input_candidate, limit=500)

    return [agents[role] for role in ordered_roles]


def _extract_synthesis(raw_result: Mapping[str, Any]) -> Dict[str, Any]:
    dashboard = _as_mapping(raw_result.get("dashboard"))
    strategy = _as_mapping(dashboard.get("strategy_synthesis"))
    committee = _as_mapping(dashboard.get("committee_deliberation"))
    core = _as_mapping(dashboard.get("core_conclusion"))

    disagreement: Dict[str, Any] = {}
    if strategy:
        disagreement = {
            "conflict_severity": strategy.get("conflict_severity"),
            "conflict_count": strategy.get("conflict_count"),
            "consensus_level": strategy.get("consensus_level"),
            "supporting_skills": strategy.get("supporting_skills"),
            "opposing_skills": strategy.get("opposing_skills"),
        }

    final_conclusion = {
        "final_signal": strategy.get("final_signal") or core.get("decision_type") or raw_result.get("decision_type"),
        "operation_advice": _clip_text(
            core.get("operation_advice") or raw_result.get("operation_advice"),
            limit=800,
        ),
        "confidence_level": core.get("confidence_level") or raw_result.get("confidence_level"),
        "analysis_summary": _clip_text(
            core.get("analysis_summary") or raw_result.get("analysis_summary"),
            limit=1200,
        ),
        "sentiment_score": raw_result.get("sentiment_score"),
    }

    return {
        "disagreement": {k: v for k, v in disagreement.items() if v is not None},
        "consensus": {
            "consensus_level": strategy.get("consensus_level"),
            "committee_status": committee.get("status") or committee.get("outcome"),
        },
        "final_conclusion": {k: v for k, v in final_conclusion.items() if v is not None},
        "committee_deliberation": committee or None,
        "strategy_synthesis": strategy or None,
    }


def _extract_data_sources(diagnostics: Mapping[str, Any], context_snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    provider_runs = []
    for raw in _as_list(diagnostics.get("provider_runs"))[:100]:
        if not isinstance(raw, Mapping):
            continue
        provider_runs.append(
            {
                "provider": _clip_text(raw.get("provider"), limit=64),
                "data_type": _clip_text(raw.get("data_type"), limit=64),
                "operation": _clip_text(raw.get("operation"), limit=64),
                "status": _clip_text(raw.get("status"), limit=32),
                "duration_ms": raw.get("duration_ms"),
                "error_code": _clip_text(raw.get("error_code"), limit=64),
            }
        )

    overview = _as_mapping(context_snapshot.get("analysis_context_pack_overview"))
    data_quality = overview.get("data_quality")
    if not isinstance(data_quality, Mapping):
        data_quality = overview.get("quality") if isinstance(overview.get("quality"), Mapping) else None

    return {
        "provider_trace": provider_runs,
        "llm_runs": [
            {
                "provider": _clip_text(raw.get("provider"), limit=64),
                "model": _clip_text(raw.get("model"), limit=120),
                "call_type": _clip_text(raw.get("call_type"), limit=64),
                "status": _clip_text(raw.get("status"), limit=32),
                "duration_ms": raw.get("duration_ms"),
                "token_usage": raw.get("token_usage") or raw.get("usage"),
            }
            for raw in _as_list(diagnostics.get("llm_runs"))[:100]
            if isinstance(raw, Mapping)
        ],
        "data_quality_status": data_quality,
        "pipeline_stage_runs": [
            {
                "stage": _clip_text(raw.get("stage") or raw.get("name"), limit=64),
                "status": _clip_text(raw.get("status"), limit=32),
                "duration_ms": raw.get("duration_ms"),
            }
            for raw in _as_list(diagnostics.get("pipeline_stage_runs"))[:100]
            if isinstance(raw, Mapping)
        ],
    }


def _apply_size_budget(package: Dict[str, Any], *, max_chars: int) -> tuple[Dict[str, Any], bool]:
    """Ensure JSON size stays under budget; shrink agent event lists first."""
    if _safe_json_size(package) <= max_chars:
        return package, False

    truncated = True
    package = dict(package)
    package["truncated"] = True
    package["truncation"] = {
        "marker": "truncated",
        "reason": "export_size_budget_exceeded",
        "max_chars": max_chars,
        "dropped": [],
    }

    agents = list(package.get("agents") or [])
    # Drop detailed per-agent events first, keep tool_calls and opinions.
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        if agent.get("events"):
            package["truncation"]["dropped"].append(
                {"path": f"agents[{agent.get('role')}].events", "count": len(agent["events"])}
            )
            agent["events"] = []
    package["agents"] = agents
    if _safe_json_size(package) <= max_chars:
        return package, truncated

    # Drop provider/llm detail next.
    for key in ("provider_trace", "llm_runs", "pipeline_stage_runs"):
        sources = package.get("data_sources")
        if isinstance(sources, dict) and sources.get(key):
            package["truncation"]["dropped"].append(
                {"path": f"data_sources.{key}", "count": len(sources[key])}
            )
            sources[key] = []
    if _safe_json_size(package) <= max_chars:
        return package, truncated

    # Last resort: strip synthesis nested payloads, keep final_conclusion.
    synthesis = package.get("synthesis")
    if isinstance(synthesis, dict):
        for key in ("committee_deliberation", "strategy_synthesis"):
            if synthesis.get(key):
                package["truncation"]["dropped"].append({"path": f"synthesis.{key}"})
                synthesis[key] = None
    if _safe_json_size(package) <= max_chars:
        return package, truncated

    # Absolute floor: replace agents with count-only stub.
    package["truncation"]["dropped"].append({"path": "agents", "count": len(agents)})
    package["agents"] = [{"role": "truncated", "note": "agent timelines omitted due to size budget"}]
    return package, truncated


def _render_markdown(package: Mapping[str, Any]) -> str:
    run = _as_mapping(package.get("run"))
    synthesis = _as_mapping(package.get("synthesis"))
    final = _as_mapping(synthesis.get("final_conclusion"))
    lines = [
        f"# Reasoning Trace ({package.get('schema_version')})",
        "",
        f"- run_id: `{run.get('run_id') or 'n/a'}`",
        f"- stock: `{run.get('stock_code') or 'n/a'}`",
        f"- market: `{run.get('market') or 'n/a'}`",
        f"- model: `{run.get('model') or 'n/a'}`",
        f"- started_at: `{run.get('started_at') or 'n/a'}`",
        f"- config_fingerprint: `{run.get('config_fingerprint') or 'n/a'}`",
        f"- truncated: `{package.get('truncated', False)}`",
        "",
        "## Agents",
    ]
    for agent in package.get("agents") or []:
        if not isinstance(agent, Mapping):
            continue
        lines.append(f"### {agent.get('role') or 'agent'}")
        if agent.get("input_summary"):
            lines.append(f"- input: {agent['input_summary']}")
        if agent.get("output_opinion"):
            lines.append(f"- opinion: {agent['output_opinion']}")
        tool_calls = agent.get("tool_calls") or []
        if tool_calls:
            lines.append(f"- tool_calls: {len(tool_calls)}")
            for call in tool_calls[:10]:
                if isinstance(call, Mapping):
                    lines.append(
                        f"  - {call.get('name')} status={call.get('status')} duration_ms={call.get('duration_ms')}"
                    )
        lines.append("")

    lines.append("## Synthesis")
    disagreement = _as_mapping(synthesis.get("disagreement"))
    if disagreement:
        lines.append(
            f"- disagreement: severity={disagreement.get('conflict_severity')} "
            f"count={disagreement.get('conflict_count')} consensus={disagreement.get('consensus_level')}"
        )
    if final:
        lines.append(f"- final_signal: {final.get('final_signal')}")
        if final.get("operation_advice"):
            lines.append(f"- advice: {final['operation_advice']}")
        if final.get("analysis_summary"):
            lines.append(f"- summary: {final['analysis_summary']}")
    lines.append("")
    lines.append("## Coverage")
    coverage = _as_mapping(package.get("coverage"))
    recorded = coverage.get("recorded") or []
    missing = coverage.get("not_recorded") or []
    lines.append(f"- recorded: {', '.join(str(x) for x in recorded)}")
    lines.append(f"- not_recorded: {', '.join(str(x) for x in missing)}")
    lines.append("")
    return "\n".join(lines)


def build_reasoning_trace_package(
    *,
    run_id: str,
    stock_code: Optional[str] = None,
    stock_name: Optional[str] = None,
    market: Optional[str] = None,
    model: Optional[str] = None,
    started_at: Optional[str] = None,
    diagnostics: Optional[Mapping[str, Any]] = None,
    raw_result: Optional[Mapping[str, Any]] = None,
    context_snapshot: Optional[Mapping[str, Any]] = None,
    config: Any = None,
    max_chars: Optional[int] = None,
    include_markdown: bool = True,
) -> ReasoningTraceExportResult:
    """Build a redacted reasoning-trace package from already-recorded sources.

    This function does not check the feature flag so unit tests can exercise
    packaging without mutating process config. Callers that gate on the flag
    should use :meth:`ReasoningTraceExportService.export_for_record`.
    """
    diagnostics_map = _as_mapping(diagnostics)
    raw_map = _as_mapping(raw_result)
    context_map = _as_mapping(context_snapshot)
    if not diagnostics_map and isinstance(context_map.get("diagnostics"), Mapping):
        diagnostics_map = dict(context_map["diagnostics"])

    agent_events = _as_list(diagnostics_map.get("agent_events"))
    agents = _group_agents_from_events(agent_events)
    synthesis = _extract_synthesis(raw_map)
    data_sources = _extract_data_sources(diagnostics_map, context_map)

    llm_runs = _as_list(diagnostics_map.get("llm_runs"))
    first_llm_model = None
    if llm_runs and isinstance(llm_runs[0], Mapping):
        first_llm_model = llm_runs[0].get("model")
    resolved_model = (
        model
        or raw_map.get("model_used")
        or diagnostics_map.get("model")
        or first_llm_model
    )

    run_meta = {
        "run_id": _clip_text(run_id, limit=128),
        "stock_code": _clip_text(
            stock_code or diagnostics_map.get("stock_code") or raw_map.get("code"),
            limit=32,
        ),
        "stock_name": _clip_text(stock_name or raw_map.get("name"), limit=120),
        "market": _clip_text(market, limit=32),
        "model": _clip_text(resolved_model, limit=120),
        "started_at": _clip_text(
            started_at or diagnostics_map.get("started_at"),
            limit=64,
        ),
        "trace_id": _clip_text(diagnostics_map.get("trace_id"), limit=128),
        "query_id": _clip_text(diagnostics_map.get("query_id"), limit=128),
        "config_fingerprint": build_config_fingerprint(config),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    package: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run": {k: v for k, v in run_meta.items() if v is not None},
        "agents": agents,
        "synthesis": synthesis,
        "data_sources": data_sources,
        "coverage": {
            "recorded": list(COVERAGE_RECORDED),
            "not_recorded": list(COVERAGE_NOT_RECORDED),
            "notes": (
                "Exporter only includes fields already persisted by the analysis "
                "pipeline. Missing stages require agent-core recording work outside T03."
            ),
        },
        "truncated": False,
    }

    budget = int(max_chars) if max_chars is not None else resolve_max_export_chars(config)
    package, truncated = _apply_size_budget(package, max_chars=budget)
    package["truncated"] = bool(truncated or package.get("truncated"))

    # Final hard boundary: security_audit redaction + local path scrubbing.
    redacted = redact_export_payload(package)
    if not isinstance(redacted, dict):
        redacted = {"schema_version": SCHEMA_VERSION, "error": "redaction_failed", "truncated": True}

    markdown = _render_markdown(redacted) if include_markdown else ""
    if include_markdown:
        markdown = str(redact_export_payload(markdown) or "")

    return ReasoningTraceExportResult(
        package=redacted,
        markdown=markdown,
        truncated=bool(redacted.get("truncated")),
    )


class ReasoningTraceExportService:
    """Load history diagnostics and export a redacted reasoning-trace package."""

    def __init__(
        self,
        *,
        history_service: Any = None,
        config: Any = None,
    ) -> None:
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
        if not is_reasoning_trace_export_enabled(self.config):
            raise ReasoningTraceExportDisabled()

    def export_for_record(
        self,
        record_id: str,
        *,
        format: str = "json",
        include_markdown: bool = True,
    ) -> ReasoningTraceExportResult:
        """Export a reasoning trace for one analysis history record.

        Raises:
            ReasoningTraceExportDisabled: when the feature flag is off.
            ReasoningTraceNotFound: when the record cannot be resolved.
            ValueError: when stored diagnostic JSON is malformed.
        """
        self.ensure_enabled()
        record = self.history_service._resolve_record(record_id)
        if not record:
            raise ReasoningTraceNotFound(f"history record not found: {record_id}")

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

        started_at = getattr(record, "created_at", None)
        if hasattr(started_at, "isoformat"):
            started_at = started_at.isoformat()

        result = build_reasoning_trace_package(
            run_id=str(getattr(record, "query_id", None) or record_id),
            stock_code=getattr(record, "code", None),
            stock_name=getattr(record, "name", None),
            model=getattr(record, "model_used", None),
            started_at=str(started_at) if started_at is not None else None,
            diagnostics=diagnostics if isinstance(diagnostics, Mapping) else None,
            raw_result=raw_result if isinstance(raw_result, Mapping) else None,
            context_snapshot=context_snapshot if isinstance(context_snapshot, Mapping) else None,
            config=self.config,
            include_markdown=include_markdown or format == "markdown",
        )
        return result
