# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Exportable auditable report package (Issues #127 / #986)."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from src.schemas.evidence_chain import (
    AUDIT_PACKAGE_SCHEMA_VERSION,
    AuditPackageArtifact,
    AuditPackageManifest,
    EvidenceChainRun,
)
from src.services.evidence_chain_service import (
    EvidenceChainDisabled,
    EvidenceChainNotFound,
    EvidenceChainService,
    is_evidence_chain_enabled,
    render_evidence_chain_markdown,
)
from src.services.reasoning_trace_export_service import (
    build_reasoning_trace_package,
    redact_export_payload,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
SCHEMA_VERSION = AUDIT_PACKAGE_SCHEMA_VERSION


class AuditPackageExportDisabled(RuntimeError):
    code = "audit_export_disabled"

    def __init__(self) -> None:
        super().__init__(self.code)


class AuditPackageNotFound(RuntimeError):
    code = "audit_package_not_found"

    def __init__(self, message: str = "audit_package_not_found") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class AuditPackageExportResult:
    zip_bytes: bytes
    manifest: Dict[str, Any]
    evidence_chain: Dict[str, Any]
    truncated: bool
    schema_version: str = SCHEMA_VERSION
    resolved_record_id: Optional[str] = None
    lookup_mode: Optional[str] = None

    def to_json_envelope(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest": self.manifest,
            "evidence_chain": self.evidence_chain,
            "truncated": self.truncated,
        }


def _resolve_runtime_config(config: Any = None) -> Any:
    if config is not None:
        return config
    try:
        from src.application_services import get_application_services
        return get_application_services().config
    except Exception as exc:  # broad-exception: fallback_recorded
        log_safe_exception(logger, "Audit package export config lookup failed", exc,
                           error_code="audit_export_config_lookup_failed", level=logging.DEBUG)
        return None


def is_audit_export_enabled(config: Any = None) -> bool:
    resolved = _resolve_runtime_config(config)
    if resolved is None:
        return False
    return bool(getattr(resolved, "audit_export_enabled", False))


def is_audit_include_raw_artifacts(config: Any = None) -> bool:
    resolved = _resolve_runtime_config(config)
    if resolved is None:
        return False
    return bool(getattr(resolved, "audit_include_raw_artifacts", False))


def _as_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _artifact(*, name: str, content_type: str, data: Optional[bytes],
              status: str = "present", missing_reason: Optional[str] = None) -> AuditPackageArtifact:
    if data is None or status != "present":
        return AuditPackageArtifact(
            name=name, content_type=content_type,
            status="missing" if status == "present" else status,  # type: ignore[arg-type]
            missing_reason=missing_reason or "artifact not available",
            byte_length=None, sha256=None,
        )
    return AuditPackageArtifact(
        name=name, content_type=content_type, status="present",
        missing_reason=None, byte_length=len(data), sha256=_sha256_bytes(data),
    )


def _extract_decision_signal_snapshot(raw_result, context_snapshot):
    raw = _as_mapping(raw_result)
    ctx = _as_mapping(context_snapshot)
    dashboard = _as_mapping(raw.get("dashboard"))
    for candidate in (
        raw.get("decision_signal"), dashboard.get("decision_signal"),
        ctx.get("decision_signal"), raw.get("decision_action"), dashboard.get("decision_action"),
    ):
        if isinstance(candidate, Mapping) and candidate:
            slim = {}
            for key, value in list(candidate.items())[:48]:
                if isinstance(value, (str, int, float, bool)) or value is None:
                    slim[str(key)[:64]] = value
                elif isinstance(value, Mapping):
                    slim[str(key)[:64]] = {
                        str(k)[:64]: v for k, v in list(value.items())[:16]
                        if isinstance(v, (str, int, float, bool)) or v is None
                    }
                elif isinstance(value, list):
                    slim[str(key)[:64]] = [
                        item for item in value[:16]
                        if isinstance(item, (str, int, float, bool)) or item is None
                    ]
            if slim:
                return slim, None
    projected = {}
    for key in ("operation_advice", "sentiment_score", "trend_prediction", "confidence_level"):
        if key in raw and raw[key] is not None:
            projected[key] = raw[key]
    core = _as_mapping(dashboard.get("core_conclusion"))
    for key in ("decision_type", "operation_advice", "confidence_level", "analysis_summary"):
        if key in core and core[key] is not None:
            projected.setdefault(key, core[key])
    strategy = _as_mapping(dashboard.get("strategy_synthesis"))
    if strategy.get("final_signal") is not None:
        projected.setdefault("final_signal", strategy.get("final_signal"))
    if projected:
        projected["projection"] = "dashboard_fields"
        return projected, None
    return None, "decision_signal snapshot not present on this history record"


class AuditPackageExportService:
    def __init__(self, *, history_service=None, config=None, evidence_chain_service=None):
        self._history_service = history_service
        self._config = config
        self._evidence_chain_service = evidence_chain_service

    @property
    def history_service(self):
        if self._history_service is None:
            from src.services.history_service import HistoryService
            self._history_service = HistoryService()
        return self._history_service

    @property
    def config(self):
        if self._config is None:
            self._config = _resolve_runtime_config(None)
        return self._config

    @property
    def evidence_chain_service(self):
        if self._evidence_chain_service is None:
            self._evidence_chain_service = EvidenceChainService(
                history_service=self.history_service, config=self.config,
            )
        return self._evidence_chain_service

    def ensure_enabled(self) -> None:
        if not is_audit_export_enabled(self.config):
            raise AuditPackageExportDisabled()

    def export_for_record(self, record_id: str) -> AuditPackageExportResult:
        self.ensure_enabled()
        if not is_evidence_chain_enabled(self.config):
            raise EvidenceChainDisabled()
        record = self.history_service._resolve_record(record_id)
        if not record:
            raise AuditPackageNotFound(f"history record not found: {record_id}")

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
        diagnostics = context_snapshot.get("diagnostics") if isinstance(context_snapshot, Mapping) else None

        try:
            chain_result = self.evidence_chain_service.build_for_record(record_id)
        except EvidenceChainNotFound as exc:
            raise AuditPackageNotFound(str(exc)) from exc
        evidence_chain = chain_result.package
        chain_run = _as_mapping(evidence_chain.get("run"))
        resolved_record_id = chain_run.get("record_id")
        lookup_mode = chain_run.get("lookup_mode")

        report_bytes = None
        report_missing_reason = None
        try:
            markdown = self.history_service.get_markdown_report(record_id)
            if markdown:
                language = str(getattr(self.config, "report_language", "en") or "en") if self.config else "en"
                section = render_evidence_chain_markdown(evidence_chain, language=language)
                combined = f"{markdown.rstrip()}\n\n---\n\n{section}"
                redacted = redact_export_payload(combined)
                report_bytes = str(redacted if isinstance(redacted, str) else combined).encode("utf-8")
            else:
                report_missing_reason = "markdown report could not be generated"
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "Audit package report markdown generation failed", exc,
                               error_code="audit_package_report_failed",
                               context={"record_id": record_id}, level=logging.WARNING)
            report_missing_reason = "markdown report generation failed"

        primary_id = getattr(record, "id", None)
        selected_record_id = str(primary_id) if primary_id is not None else str(record_id)
        selected_query_id = getattr(record, "query_id", None)
        diagnostic_trace_id = diagnostics.get("trace_id") if isinstance(diagnostics, Mapping) else None
        stable_run_id = str(diagnostic_trace_id or selected_query_id or f"history:{selected_record_id}")
        started_at = getattr(record, "created_at", None)
        if hasattr(started_at, "isoformat"):
            started_at = started_at.isoformat()

        reasoning_bytes = None
        reasoning_missing_reason = None
        reasoning_schema = None
        try:
            trace = build_reasoning_trace_package(
                run_id=stable_run_id,
                record_id=selected_record_id,
                query_id=str(selected_query_id) if selected_query_id is not None else None,
                lookup_key=str(record_id),
                lookup_mode=str(lookup_mode) if lookup_mode else None,
                stock_code=getattr(record, "code", None),
                stock_name=getattr(record, "name", None),
                market=getattr(record, "market", None) or getattr(record, "region", None),
                model=getattr(record, "model_used", None),
                started_at=str(started_at) if started_at is not None else None,
                diagnostics=diagnostics if isinstance(diagnostics, Mapping) else None,
                raw_result=raw_result if isinstance(raw_result, Mapping) else None,
                context_snapshot=context_snapshot if isinstance(context_snapshot, Mapping) else None,
                config=self.config,
                include_markdown=False,
                output_format="json",
            )
            reasoning_schema = trace.schema_version
            reasoning_bytes = _json_bytes(trace.package)
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "Audit package reasoning-trace embed failed", exc,
                               error_code="audit_package_reasoning_trace_failed",
                               context={"record_id": record_id}, level=logging.WARNING)
            reasoning_missing_reason = "reasoning-trace projection failed"

        decision_payload, decision_missing = _extract_decision_signal_snapshot(
            raw_result if isinstance(raw_result, Mapping) else None,
            context_snapshot if isinstance(context_snapshot, Mapping) else None,
        )
        decision_bytes = None
        if decision_payload is not None:
            decision_bytes = _json_bytes(redact_export_payload(decision_payload))

        gaps_payload = {
            "schema_version": "evidence-gaps-v1",
            "gaps": evidence_chain.get("gaps") or [],
            "coverage": evidence_chain.get("coverage") or {},
            "not_recorded": (_as_mapping(evidence_chain.get("coverage")).get("not_recorded") or []),
        }
        gaps_bytes = _json_bytes(redact_export_payload(gaps_payload))
        evidence_json_bytes = _json_bytes(evidence_chain)
        evidence_md_bytes = str(redact_export_payload(
            render_evidence_chain_markdown(evidence_chain, language="en")
        )).encode("utf-8")

        include_raw = is_audit_include_raw_artifacts(self.config)
        raw_missing_reason = (
            "AUDIT_INCLUDE_RAW_ARTIFACTS=false; raw intermediates not included"
            if not include_raw else None
        )

        artifacts = [
            _artifact(name="report.md", content_type="text/markdown; charset=utf-8",
                      data=report_bytes, status="present" if report_bytes else "missing",
                      missing_reason=report_missing_reason),
            _artifact(name="evidence_chain.json", content_type="application/json", data=evidence_json_bytes),
            _artifact(name="evidence_chain.md", content_type="text/markdown; charset=utf-8", data=evidence_md_bytes),
            _artifact(name="reasoning_trace.json", content_type="application/json",
                      data=reasoning_bytes, status="present" if reasoning_bytes else "missing",
                      missing_reason=reasoning_missing_reason),
            _artifact(name="decision_signal.json", content_type="application/json",
                      data=decision_bytes, status="present" if decision_bytes else "missing",
                      missing_reason=decision_missing),
            _artifact(name="gaps.json", content_type="application/json", data=gaps_bytes),
            AuditPackageArtifact(
                name="raw_intermediates/", content_type="application/octet-stream",
                status="skipped", missing_reason=raw_missing_reason,
                byte_length=None, sha256=None,
            ),
        ]

        run_model = EvidenceChainRun.model_validate(chain_run)
        manifest = AuditPackageManifest(
            schema_version=SCHEMA_VERSION, run=run_model, artifacts=artifacts,
            evidence_chain_schema="evidence-chain-v1",
            reasoning_trace_schema=reasoning_schema, redacted=True,
            include_raw_artifacts=include_raw,
            notes="Redacted auditable package. Sensitive values are scrubbed. "
                  "Artifacts with status=missing or skipped are listed explicitly.",
        )
        manifest_dict = redact_export_payload(manifest.model_dump(mode="json"))
        if not isinstance(manifest_dict, dict):
            raise ValueError("audit package manifest redaction failed")
        AuditPackageManifest.model_validate(manifest_dict)
        manifest_bytes = _json_bytes(manifest_dict)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", manifest_bytes)
            zf.writestr("evidence_chain.json", evidence_json_bytes)
            zf.writestr("evidence_chain.md", evidence_md_bytes)
            zf.writestr("gaps.json", gaps_bytes)
            if report_bytes is not None:
                zf.writestr("report.md", report_bytes)
            else:
                zf.writestr("report.MISSING.txt", (report_missing_reason or "report missing").encode("utf-8"))
            if reasoning_bytes is not None:
                zf.writestr("reasoning_trace.json", reasoning_bytes)
            else:
                zf.writestr("reasoning_trace.MISSING.txt",
                            (reasoning_missing_reason or "reasoning_trace missing").encode("utf-8"))
            if decision_bytes is not None:
                zf.writestr("decision_signal.json", decision_bytes)
            else:
                zf.writestr("decision_signal.MISSING.txt",
                            (decision_missing or "decision_signal missing").encode("utf-8"))
            if not include_raw:
                zf.writestr("raw_intermediates/SKIPPED.txt",
                            (raw_missing_reason or "skipped").encode("utf-8"))

        return AuditPackageExportResult(
            zip_bytes=buf.getvalue(),
            manifest=manifest_dict,
            evidence_chain=evidence_chain,
            truncated=bool(evidence_chain.get("truncated")),
            schema_version=SCHEMA_VERSION,
            resolved_record_id=str(resolved_record_id) if resolved_record_id else selected_record_id,
            lookup_mode=str(lookup_mode) if lookup_mode else None,
        )
