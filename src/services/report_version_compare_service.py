# -*- coding: utf-8 -*-
"""Report version selection and presentation service (issue #188 / T18).

Owns run listing, config-fingerprint extraction, side-by-side field snapshots,
and adapter-backed delta status. Does **not** implement T17 comparison logic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.report_language import is_supported_report_language_value, normalize_report_language
from src.schemas.decision_action import display_action_fields, normalize_decision_action
from src.schemas.decision_scale import extract_decision_guardrail_reason
from src.services.report_version_compare_adapter import (
    CompareAnalysesFn,
    invoke_compare_analyses,
)
from src.storage import DatabaseManager
from src.utils.data_processing import normalize_model_used, parse_json_field

logger = logging.getLogger(__name__)

SEVERITY_MAJOR = "major"
SEVERITY_MODERATE = "moderate"
SEVERITY_MINOR = "minor"
SEVERITY_NONE = "none"
SEVERITY_UNKNOWN = "unknown"

_BULLISH_ACTIONS = frozenset({"buy", "add"})
_BEARISH_ACTIONS = frozenset({"sell", "reduce", "avoid"})
_SCORE_MINOR_DELTA = 5
_EXCLUDED_DEFAULT_REPORT_TYPES = ("market_review",)
_CONFIG_REQUIRED_KEYS = (
    "model_used",
    "report_type",
    "report_language",
    "provider_route",
    "model_route",
    "config_profile",
    "config_version",
)


class ReportVersionCompareError(ValueError):
    """Controlled validation / not-found error with stable API code."""

    def __init__(self, message: str, *, code: str, params: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.params = params or {}


class ReportVersionCompareService:
    """List analysis runs and build presentation payloads for version compare."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        compare_fn: Optional[CompareAnalysesFn] = None,
    ) -> None:
        self.db = db_manager or DatabaseManager.get_instance()
        self._compare_fn = compare_fn

    def list_runs(
        self,
        stock_code: str,
        *,
        page: int = 1,
        limit: int = 20,
        report_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        code = self._require_stock_code(stock_code)
        page_norm = self._require_page(page)
        limit_norm = self._require_limit(limit)
        offset = (page_norm - 1) * limit_norm

        records, total = self.db.get_analysis_history_paginated(
            code=code,
            report_type=report_type,
            excluded_report_types=(
                None if report_type is not None else _EXCLUDED_DEFAULT_REPORT_TYPES
            ),
            offset=offset,
            limit=limit_norm,
        )

        items = [self._record_to_run_item(record) for record in records]

        return {
            "stock_code": code,
            "total": total,
            "page": page_norm,
            "limit": limit_norm,
            "items": items,
        }

    def compare_runs(
        self,
        stock_code: str,
        base_run_id: str,
        target_run_id: str,
    ) -> Dict[str, Any]:
        code = self._require_stock_code(stock_code)
        base_id = self._require_run_id(base_run_id, field="base_run_id")
        target_id = self._require_run_id(target_run_id, field="target_run_id")
        if base_id == target_id:
            raise ReportVersionCompareError(
                "base_run_id and target_run_id must be different",
                code="same_run_ids",
                params={"run_id": str(base_id)},
            )

        base_record = self.db.get_analysis_history_by_id(base_id)
        target_record = self.db.get_analysis_history_by_id(target_id)
        if base_record is None:
            raise ReportVersionCompareError(
                f"Base run not found: {base_id}",
                code="base_run_not_found",
                params={"run_id": str(base_id)},
            )
        if target_record is None:
            raise ReportVersionCompareError(
                f"Target run not found: {target_id}",
                code="target_run_not_found",
                params={"run_id": str(target_id)},
            )

        base_code = self._normalize_code(getattr(base_record, "code", None))
        target_code = self._normalize_code(getattr(target_record, "code", None))
        if not base_code or not target_code:
            raise ReportVersionCompareError(
                "One or both runs are missing a stock code",
                code="incomparable",
                params={"reason": "missing_stock_code"},
            )
        if base_code != target_code:
            raise ReportVersionCompareError(
                "Runs belong to different symbols and cannot be compared",
                code="incomparable",
                params={
                    "reason": "stock_code_mismatch",
                    "base_stock_code": base_code,
                    "target_stock_code": target_code,
                },
            )

        requested = self._normalize_code(code)
        display_requested = self._display_code(requested)
        display_base = self._display_code(base_code)
        if requested and requested != base_code and display_requested != display_base:
            raise ReportVersionCompareError(
                "stock_code does not match the selected runs",
                code="stock_code_mismatch",
                params={"stock_code": code, "run_stock_code": base_code},
            )

        base_run = self._record_to_run_item(base_record)
        target_run = self._record_to_run_item(target_record)
        config_diff = self._build_config_diff(
            base_run.get("config_components") or {},
            target_run.get("config_components") or {},
            base_fingerprint=str(base_run.get("config_fingerprint") or ""),
            target_fingerprint=str(target_run.get("config_fingerprint") or ""),
            base_complete=bool(base_run.get("config_complete")),
            target_complete=bool(target_run.get("config_complete")),
            base_missing_keys=base_run.get("config_missing_keys") or [],
            target_missing_keys=target_run.get("config_missing_keys") or [],
        )
        field_diffs = self._build_field_diffs(base_run, target_run)

        engine_status, delta = invoke_compare_analyses(
            base_code,
            base_id,
            target_id,
            compare_fn=self._compare_fn,
        )

        if engine_status == "engine_pending" or delta is None:
            compare_status = "engine_pending"
        elif delta.get("baseline_status") == "incomparable_structure":
            compare_status = "incomparable"
        elif not delta.get("has_baseline", False):
            compare_status = "no_baseline"
        else:
            compare_status = "ok"

        return {
            "status": compare_status,
            "stock_code": self._display_code(base_code),
            "base_run": base_run,
            "target_run": target_run,
            "config_diff": config_diff,
            "field_diffs": field_diffs,
            "delta": delta,
            "engine_status": engine_status,
        }

    def _record_to_run_item(self, record: Any) -> Dict[str, Any]:
        raw_result = parse_json_field(getattr(record, "raw_result", None))
        if not isinstance(raw_result, dict):
            raw_result = {}
        context_snapshot = parse_json_field(getattr(record, "context_snapshot", None))
        if not isinstance(context_snapshot, dict):
            context_snapshot = {}

        sentiment_score = self._finite_score(getattr(record, "sentiment_score", None))
        model_used = self._safe_text(normalize_model_used(raw_result.get("model_used")))
        persisted_report_language = (
            raw_result.get("report_language") or getattr(record, "report_language", None)
        )
        report_language = normalize_report_language(
            persisted_report_language
            if isinstance(persisted_report_language, str)
            else None
        )
        config_report_language = (
            report_language
            if is_supported_report_language_value(persisted_report_language)
            else None
        )
        action_fields = display_action_fields(
            operation_advice=raw_result.get("operation_advice") or getattr(record, "operation_advice", None),
            explicit_action=raw_result.get("action"),
            action_label=raw_result.get("action_label"),
            report_type=getattr(record, "report_type", None),
            report_language=config_report_language,
            sentiment_score=sentiment_score,
            guardrail_reason=extract_decision_guardrail_reason(raw_result),
        )

        config_components = self._extract_config_components(
            raw_result=raw_result,
            context_snapshot=context_snapshot,
            report_type=getattr(record, "report_type", None),
            model_used=model_used,
            report_language=config_report_language,
        )
        missing_config_keys = [
            key for key in _CONFIG_REQUIRED_KEYS if not config_components.get(key)
        ]
        config_complete = not missing_config_keys
        fingerprint = (
            self._fingerprint_components(config_components) if config_complete else None
        )

        created_at = getattr(record, "created_at", None)
        created_at_text = created_at.isoformat() if hasattr(created_at, "isoformat") else (
            str(created_at) if created_at is not None else None
        )

        return {
            "run_id": str(getattr(record, "id", "") or ""),
            "query_id": self._safe_text(getattr(record, "query_id", None)) or "",
            "stock_code": self._display_code(getattr(record, "code", None)),
            "stock_name": self._safe_text(getattr(record, "name", None)),
            "report_type": self._safe_text(getattr(record, "report_type", None)),
            "created_at": created_at_text,
            "model_used": model_used,
            "report_language": report_language,
            "action": self._safe_text(action_fields.get("action")),
            "action_label": self._safe_text(action_fields.get("action_label")),
            "operation_advice": self._safe_text(getattr(record, "operation_advice", None)),
            "sentiment_score": sentiment_score,
            "trend_prediction": self._safe_text(getattr(record, "trend_prediction", None)),
            "analysis_summary": self._safe_text(getattr(record, "analysis_summary", None)),
            "config_fingerprint": fingerprint,
            "config_components": config_components,
            "config_complete": config_complete,
            "config_missing_keys": missing_config_keys,
        }

    @staticmethod
    def _extract_config_components(
        *,
        raw_result: Mapping[str, Any],
        context_snapshot: Mapping[str, Any],
        report_type: Any,
        model_used: Any,
        report_language: Any,
    ) -> Dict[str, str]:
        def pick(*values: Any) -> str:
            for value in values:
                if value is None:
                    continue
                if isinstance(value, float) and not math.isfinite(value):
                    continue
                text = str(value).strip()
                if text:
                    return text
            return ""

        diagnostics = context_snapshot.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        enhanced = context_snapshot.get("enhanced_context")
        if not isinstance(enhanced, dict):
            enhanced = {}
        routing = context_snapshot.get("routing")
        if not isinstance(routing, dict):
            routing = {}

        return {
            "model_used": pick(model_used),
            "report_type": pick(report_type, raw_result.get("report_type")),
            "report_language": pick(report_language),
            "provider_route": pick(
                raw_result.get("provider_route"),
                raw_result.get("model_provider"),
                context_snapshot.get("provider_route"),
                routing.get("provider"),
                diagnostics.get("model_provider"),
            ),
            "model_route": pick(
                raw_result.get("model_route"),
                raw_result.get("resolved_model"),
                context_snapshot.get("model_route"),
                routing.get("model"),
                diagnostics.get("resolved_model"),
            ),
            "model_version": pick(
                raw_result.get("model_version"),
                context_snapshot.get("model_version"),
                diagnostics.get("model_version"),
            ),
            "analysis_phase": pick(
                raw_result.get("analysis_phase"),
                context_snapshot.get("analysis_phase"),
                diagnostics.get("analysis_phase"),
                enhanced.get("analysis_phase"),
            ),
            "strategy_mode": pick(
                raw_result.get("strategy_mode"),
                context_snapshot.get("strategy_mode"),
                diagnostics.get("strategy_mode"),
            ),
            "config_profile": pick(
                raw_result.get("config_profile"),
                raw_result.get("config_profile_id"),
                context_snapshot.get("config_profile"),
                context_snapshot.get("config_profile_id"),
                diagnostics.get("config_profile"),
            ),
            "config_version": pick(
                raw_result.get("config_version"),
                context_snapshot.get("config_version"),
                diagnostics.get("config_version"),
            ),
            "prompt_version": pick(
                raw_result.get("prompt_version"),
                context_snapshot.get("prompt_version"),
                diagnostics.get("prompt_version"),
            ),
        }

    @staticmethod
    def _fingerprint_components(components: Mapping[str, str]) -> str:
        canonical = json.dumps(
            {str(key): str(components.get(key) or "") for key in sorted(components.keys())},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    def _build_config_diff(
        self,
        base_components: Mapping[str, Any],
        target_components: Mapping[str, Any],
        *,
        base_fingerprint: str,
        target_fingerprint: str,
        base_complete: bool,
        target_complete: bool,
        base_missing_keys: Sequence[str],
        target_missing_keys: Sequence[str],
    ) -> Dict[str, Any]:
        keys = sorted(set(base_components.keys()) | set(target_components.keys()))
        changes: List[Dict[str, Any]] = []
        for key in keys:
            base_value = str(base_components.get(key) or "")
            target_value = str(target_components.get(key) or "")
            changes.append(
                {
                    "key": key,
                    "base_value": base_value or None,
                    "target_value": target_value or None,
                    "changed": base_value != target_value,
                }
            )
        has_differences = any(item["changed"] for item in changes)
        comparable = base_complete and target_complete
        identical = comparable and base_fingerprint == target_fingerprint
        comparison_status = (
            "unknown" if not comparable else ("different" if has_differences else "identical")
        )
        return {
            "base_fingerprint": base_fingerprint or None,
            "target_fingerprint": target_fingerprint or None,
            "identical": identical,
            "has_differences": has_differences,
            "comparison_status": comparison_status,
            "base_complete": base_complete,
            "target_complete": target_complete,
            "base_missing_keys": [str(key) for key in base_missing_keys],
            "target_missing_keys": [str(key) for key in target_missing_keys],
            "components": changes,
        }

    def _build_field_diffs(
        self,
        base_run: Mapping[str, Any],
        target_run: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        fields: Sequence[Tuple[str, str]] = (
            ("action", "action"),
            ("sentiment_score", "sentiment_score"),
            ("trend_prediction", "trend_prediction"),
            ("operation_advice", "operation_advice"),
            ("analysis_summary", "analysis_summary"),
            ("model_used", "model_used"),
        )
        diffs: List[Dict[str, Any]] = []
        for field_key, source_key in fields:
            base_value = base_run.get(source_key)
            target_value = target_run.get(source_key)
            changed = self._values_differ(base_value, target_value)
            severity = (
                self._grade_field_severity(field_key, base_value, target_value)
                if changed
                else SEVERITY_NONE
            )
            diffs.append(
                {
                    "field": field_key,
                    "base_value": self._stringify_value(base_value),
                    "target_value": self._stringify_value(target_value),
                    "changed": changed,
                    "severity": severity,
                }
            )
        return diffs

    @staticmethod
    def _values_differ(left: Any, right: Any) -> bool:
        if left is None and right is None:
            return False
        if left is None or right is None:
            return True
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if not math.isfinite(float(left)) or not math.isfinite(float(right)):
                return left is not right
            return float(left) != float(right)
        return str(left).strip() != str(right).strip()

    @staticmethod
    def _stringify_value(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, float):
            if not math.isfinite(value):
                return None
            if value == int(value):
                return str(int(value))
            return str(value)
        text = str(value).strip()
        return text or None

    def _grade_field_severity(self, field: str, base_value: Any, target_value: Any) -> str:
        if field == "action":
            base_action = normalize_decision_action(base_value)
            target_action = normalize_decision_action(target_value)
            if base_action is None or target_action is None:
                return SEVERITY_MODERATE if base_value != target_value else SEVERITY_NONE
            if base_action == target_action:
                return SEVERITY_NONE
            if (
                (base_action in _BULLISH_ACTIONS and target_action in _BEARISH_ACTIONS)
                or (base_action in _BEARISH_ACTIONS and target_action in _BULLISH_ACTIONS)
            ):
                return SEVERITY_MAJOR
            return SEVERITY_MODERATE

        if field == "sentiment_score":
            try:
                base_score = float(base_value)
                target_score = float(target_value)
            except (TypeError, ValueError):
                return SEVERITY_UNKNOWN
            if not math.isfinite(base_score) or not math.isfinite(target_score):
                return SEVERITY_UNKNOWN
            delta = abs(base_score - target_score)
            if delta <= _SCORE_MINOR_DELTA:
                return SEVERITY_MINOR
            if delta <= 20:
                return SEVERITY_MODERATE
            return SEVERITY_MAJOR

        if field in {"trend_prediction", "operation_advice"}:
            return SEVERITY_MODERATE
        if field == "analysis_summary":
            return SEVERITY_MINOR
        if field == "model_used":
            return SEVERITY_MODERATE
        return SEVERITY_UNKNOWN

    @staticmethod
    def _finite_score(value: Any) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None
        try:
            score = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(score) or not 0 <= score <= 100:
            return None
        return score

    @staticmethod
    def _safe_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, float) and not math.isfinite(value):
            return None
        text = str(value).strip()
        return text or None

    def _require_stock_code(self, stock_code: str) -> str:
        text = str(stock_code or "").strip()
        if not text:
            raise ReportVersionCompareError(
                "stock_code is required",
                code="missing_stock_code",
            )
        return text

    @staticmethod
    def _require_page(page: int) -> int:
        try:
            value = int(page)
        except (TypeError, ValueError) as exc:
            raise ReportVersionCompareError(
                "page must be a positive integer",
                code="invalid_page",
            ) from exc
        if value < 1:
            raise ReportVersionCompareError(
                "page must be a positive integer",
                code="invalid_page",
                params={"page": page},
            )
        return value

    @staticmethod
    def _require_limit(limit: int) -> int:
        try:
            value = int(limit)
        except (TypeError, ValueError) as exc:
            raise ReportVersionCompareError(
                "limit must be between 1 and 100",
                code="invalid_limit",
            ) from exc
        if value < 1 or value > 100:
            raise ReportVersionCompareError(
                "limit must be between 1 and 100",
                code="invalid_limit",
                params={"limit": limit},
            )
        return value

    @staticmethod
    def _require_run_id(run_id: str, *, field: str) -> int:
        text = str(run_id or "").strip()
        if not text or not text.isdigit():
            raise ReportVersionCompareError(
                f"{field} must be a positive integer run id",
                code="invalid_run_id",
                params={field: run_id},
            )
        value = int(text)
        if value <= 0:
            raise ReportVersionCompareError(
                f"{field} must be a positive integer run id",
                code="invalid_run_id",
                params={field: run_id},
            )
        return value

    @staticmethod
    def _normalize_code(code: Any) -> str:
        text = str(code or "").strip()
        if not text:
            return ""
        try:
            from data_provider.base import normalize_stock_code

            return normalize_stock_code(text) or text
        except (ImportError, TypeError, ValueError, AttributeError):
            return text

    @staticmethod
    def _display_code(code: Any) -> str:
        text = str(code or "").strip()
        if not text:
            return ""
        try:
            from src.data.stock_index_loader import resolve_index_stock_code

            return resolve_index_stock_code(text) or text
        except (ImportError, TypeError, ValueError, AttributeError):
            return text
