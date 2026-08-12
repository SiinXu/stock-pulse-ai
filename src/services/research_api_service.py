# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only research API projection for stratified conclusions (Issue #1143).

Projects a compact, mode-filtered conclusion payload from persisted analysis
history. No write side effects. Does not re-run analysis or expose secrets.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from src.report_language import normalize_report_language
from src.schemas.report_strata import project_report_strata_for_api
from src.services.report_mode import (
    REPORT_MODE_BRIEF,
    REPORT_MODE_RESEARCH,
    REPORT_MODE_STANDARD,
    VALID_REPORT_MODES,
    apply_list_limits_to_dashboard_view,
    get_mode_limits,
    normalize_report_mode,
    truncation_notice,
)

RESEARCH_CONCLUSION_SCHEMA_VERSION = "research-conclusion-v1"


class ResearchApiNotFoundError(LookupError):
    """Raised when the requested analysis record does not exist."""


class ResearchApiValidationError(ValueError):
    """Raised for invalid research API request parameters."""


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _clean_text(value: Any, *, max_chars: int | None = None) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        return text[:max_chars].rstrip() + "…"
    return text


def _unique_refs(values: Sequence[Any]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _collect_evidence_refs(strata: Optional[Mapping[str, Any]]) -> List[str]:
    if not isinstance(strata, Mapping):
        return []
    refs: List[str] = []
    facts = strata.get("verified_facts")
    if isinstance(facts, list):
        for item in facts:
            if isinstance(item, Mapping) and item.get("source_id") is not None:
                refs.append(item.get("source_id"))
    gaps = strata.get("missing_or_conflicts")
    if isinstance(gaps, list):
        for item in gaps:
            if not isinstance(item, Mapping):
                continue
            source_ids = item.get("source_ids")
            if isinstance(source_ids, list):
                refs.extend(source_ids)
            elif isinstance(source_ids, str):
                refs.append(source_ids)
    return _unique_refs(refs)


def _evidence_counts(strata: Optional[Mapping[str, Any]], evidence_refs: Sequence[str]) -> Dict[str, int]:
    if not isinstance(strata, Mapping):
        return {
            "verified_facts": 0,
            "missing_or_conflicts": 0,
            "model_inference": 0,
            "risks_counter_evidence": 0,
            "evidence_refs": 0,
        }

    def _len_list(key: str) -> int:
        value = strata.get(key)
        return len(value) if isinstance(value, list) else 0

    return {
        "verified_facts": _len_list("verified_facts"),
        "missing_or_conflicts": _len_list("missing_or_conflicts"),
        "model_inference": _len_list("model_inference"),
        "risks_counter_evidence": _len_list("risks_counter_evidence"),
        "evidence_refs": len(evidence_refs),
    }


def _resolve_as_of(
    *,
    strata: Optional[Mapping[str, Any]],
    raw_result: Mapping[str, Any],
    record: Mapping[str, Any],
) -> Optional[str]:
    facts = strata.get("verified_facts") if isinstance(strata, Mapping) else None
    if isinstance(facts, list):
        for item in reversed(facts):
            if isinstance(item, Mapping):
                as_of = _clean_text(item.get("as_of"))
                if as_of:
                    return as_of
    for key in ("indicator_as_of", "as_of", "data_as_of"):
        as_of = _clean_text(raw_result.get(key))
        if as_of:
            return as_of
        dashboard = raw_result.get("dashboard")
        if isinstance(dashboard, Mapping):
            as_of = _clean_text(dashboard.get(key))
            if as_of:
                return as_of
    return _clean_text(record.get("created_at"))


def _clip_strata_for_mode(
    strata: Optional[Mapping[str, Any]],
    *,
    mode: str,
    limits: Mapping[str, Any],
) -> tuple[Optional[Dict[str, Any]], int]:
    """Apply report-mode density to strata; brief drops strata (strata_style none)."""
    style = str(limits.get("strata_style") or "full")
    if mode == REPORT_MODE_BRIEF or style == "none":
        return None, 0
    if not isinstance(strata, Mapping):
        return None, 0

    # Reuse the same list-limit path as report rendering by wrapping strata
    # inside a synthetic dashboard view.
    limited_dashboard, omitted = apply_list_limits_to_dashboard_view(
        {"report_strata": dict(strata)},
        limits,
    )
    limited = limited_dashboard.get("report_strata")
    if not isinstance(limited, Mapping):
        return None, omitted
    return dict(limited), omitted


def _gaps_from_strata(strata: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(strata, Mapping):
        return []
    gaps = strata.get("missing_or_conflicts")
    if not isinstance(gaps, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in gaps:
        if isinstance(item, Mapping):
            kind = str(item.get("kind") or "missing").strip() or "missing"
            if kind not in {"missing", "conflict"}:
                kind = "missing"
            description = _clean_text(item.get("description"))
            if not description:
                continue
            source_ids = item.get("source_ids")
            refs = (
                _unique_refs(source_ids)
                if isinstance(source_ids, list)
                else (_unique_refs([source_ids]) if source_ids else [])
            )
            out.append(
                {
                    "kind": kind,
                    "description": description,
                    "source_ids": refs,
                }
            )
        elif isinstance(item, str) and item.strip():
            out.append({"kind": "missing", "description": item.strip(), "source_ids": []})
    return out


class ResearchApiService:
    """Build compact stratified conclusions from history storage."""

    def __init__(
        self,
        *,
        history_service: Any = None,
        get_history_service: Callable[[], Any] | None = None,
    ) -> None:
        self._history_service = history_service
        self._get_history_service = get_history_service

    def history_service(self) -> Any:
        if self._history_service is not None:
            return self._history_service
        if self._get_history_service is not None:
            self._history_service = self._get_history_service()
            return self._history_service
        from src.services.history_service import HistoryService

        self._history_service = HistoryService()
        return self._history_service

    def get_conclusion_by_record_id(
        self,
        record_id: int,
        *,
        mode: str = REPORT_MODE_STANDARD,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return one mode-filtered stratified conclusion for a history record."""
        if not isinstance(record_id, int) or record_id < 1:
            raise ResearchApiValidationError("record_id must be a positive integer")
        report_mode = normalize_report_mode(mode, default=REPORT_MODE_STANDARD)
        if report_mode not in VALID_REPORT_MODES:
            raise ResearchApiValidationError(
                f"mode must be one of: {', '.join(sorted(VALID_REPORT_MODES))}"
            )

        record = self.history_service().get_history_detail_by_id(int(record_id))
        if not record:
            raise ResearchApiNotFoundError(f"Analysis record not found: {record_id}")
        return self.project_conclusion(record, mode=report_mode, language=language)

    def get_latest_conclusion_for_stock(
        self,
        stock_code: str,
        *,
        mode: str = REPORT_MODE_STANDARD,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the newest stock analysis conclusion for ``stock_code``."""
        code = _clean_text(stock_code)
        if not code:
            raise ResearchApiValidationError("stock_code is required")
        report_mode = normalize_report_mode(mode, default=REPORT_MODE_STANDARD)
        listing = self.history_service().get_history_list(
            stock_code=code,
            page=1,
            limit=1,
        )
        items = listing.get("items") if isinstance(listing, Mapping) else None
        if not isinstance(items, list) or not items:
            raise ResearchApiNotFoundError(f"No analysis history for stock_code={code}")
        first = items[0]
        record_id = first.get("id") if isinstance(first, Mapping) else None
        if record_id is None:
            raise ResearchApiNotFoundError(f"No analysis history for stock_code={code}")
        return self.get_conclusion_by_record_id(
            int(record_id),
            mode=report_mode,
            language=language,
        )

    def project_conclusion(
        self,
        record: Mapping[str, Any],
        *,
        mode: str = REPORT_MODE_STANDARD,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Project a compact conclusion DTO from a history detail dict."""
        report_mode = normalize_report_mode(mode, default=REPORT_MODE_STANDARD)
        raw_result = _as_mapping(record.get("raw_result"))
        report_language = normalize_report_language(
            language
            or raw_result.get("report_language")
            or "zh"
        )
        limits = get_mode_limits(report_mode)

        strata_source = raw_result or record
        full_strata = project_report_strata_for_api(
            strata_source,
            language=report_language,
            log_context={
                "record_id": record.get("id"),
                "stock_code": record.get("stock_code"),
            },
        )
        limited_strata, strata_omitted = _clip_strata_for_mode(
            full_strata,
            mode=report_mode,
            limits=limits,
        )

        dashboard = raw_result.get("dashboard")
        limited_dashboard, dashboard_omitted = apply_list_limits_to_dashboard_view(
            dashboard if isinstance(dashboard, Mapping) else {},
            limits,
        )
        core = _as_mapping(limited_dashboard.get("core_conclusion"))
        phase = _as_mapping(limited_dashboard.get("phase_decision"))
        intel = _as_mapping(limited_dashboard.get("intelligence"))

        one_sentence = _clean_text(
            core.get("one_sentence") or record.get("analysis_summary"),
            max_chars=int(limits.get("one_sentence_max", 120)),
        )
        signal_type = _clean_text(core.get("signal_type") or record.get("action"))
        position_advice = _clean_text(
            core.get("position_advice") or record.get("operation_advice")
        )
        time_sensitivity = _clean_text(core.get("time_sensitivity"))
        confidence_level = _clean_text(
            raw_result.get("confidence_level")
            or phase.get("confidence_level")
            or record.get("confidence_level")
        )
        confidence_reason = _clean_text(phase.get("confidence_reason"))

        risks: List[str] = []
        risk_alerts = intel.get("risk_alerts")
        if isinstance(risk_alerts, list):
            risks = [t for t in (_clean_text(item) for item in risk_alerts) if t]
        if report_mode == REPORT_MODE_BRIEF and not risks and limited_strata is None:
            # brief may still surface a single risk from full strata when present
            full_risks = full_strata.get("risks_counter_evidence") if isinstance(full_strata, Mapping) else None
            if isinstance(full_risks, list) and full_risks:
                first = _clean_text(full_risks[0], max_chars=int(limits.get("risk_max_chars", 40)))
                if first:
                    risks = [first]

        gaps = _gaps_from_strata(limited_strata if limited_strata is not None else full_strata)
        if report_mode == REPORT_MODE_BRIEF:
            # brief: keep gaps so clients can still show what is missing
            max_gaps = 2
            if len(gaps) > max_gaps:
                dashboard_omitted += len(gaps) - max_gaps
                gaps = gaps[:max_gaps]

        evidence_source = limited_strata if limited_strata is not None else full_strata
        evidence_refs = _collect_evidence_refs(evidence_source)
        counts = _evidence_counts(evidence_source, evidence_refs)
        omitted = int(strata_omitted) + int(dashboard_omitted)
        notice = truncation_notice(omitted, report_language=report_language) or None
        as_of = _resolve_as_of(
            strata=full_strata,
            raw_result=raw_result,
            record=record,
        )

        conclusion: Dict[str, Any] = {
            "one_sentence": one_sentence,
            "signal_type": signal_type,
            "position_advice": position_advice,
            "time_sensitivity": time_sensitivity,
            "operation_advice": _clean_text(record.get("operation_advice") or position_advice),
            "action": _clean_text(record.get("action")),
            "action_label": _clean_text(record.get("action_label")),
            "risks": risks,
            "gaps": gaps,
            "report_strata": limited_strata,
            "omitted_count": omitted,
            "truncation_notice": notice,
        }
        if report_mode in {REPORT_MODE_STANDARD, REPORT_MODE_RESEARCH}:
            conclusion["confidence_reason"] = confidence_reason
            catalysts = intel.get("positive_catalysts")
            if isinstance(catalysts, list):
                conclusion["positive_catalysts"] = [
                    t for t in (_clean_text(item) for item in catalysts) if t
                ]
            else:
                conclusion["positive_catalysts"] = []
        if report_mode == REPORT_MODE_RESEARCH:
            conclusion["analysis_summary"] = _clean_text(record.get("analysis_summary"))
            conclusion["trend_prediction"] = _clean_text(record.get("trend_prediction"))

        return {
            "schema_version": RESEARCH_CONCLUSION_SCHEMA_VERSION,
            "mode": report_mode,
            "metadata": {
                "record_id": int(record.get("id") or 0),
                "query_id": _clean_text(record.get("query_id")),
                "stock_code": _clean_text(record.get("stock_code")) or "",
                "stock_name": _clean_text(record.get("stock_name")),
                "report_type": _clean_text(record.get("report_type")),
                "created_at": _clean_text(record.get("created_at")),
                "as_of": as_of,
                "confidence_level": confidence_level,
                "evidence_counts": counts,
                "evidence_refs": evidence_refs,
                "report_language": report_language,
            },
            "conclusion": conclusion,
            "disclaimer": (
                _clean_text(full_strata.get("disclaimer"))
                if isinstance(full_strata, Mapping)
                else None
            ),
        }


__all__ = [
    "RESEARCH_CONCLUSION_SCHEMA_VERSION",
    "ResearchApiNotFoundError",
    "ResearchApiValidationError",
    "ResearchApiService",
]
