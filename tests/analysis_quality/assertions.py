# -*- coding: utf-8 -*-
"""Deterministic structural assertions for analysis quality panel cases.

These checks are offline and heuristic/structural only. They do not score
subjective LLM quality, market alpha, or live vendor accuracy.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

from src.analyzer import AnalysisResult
from src.analyzer_parts.result_processing import check_content_integrity
from src.schemas.report_schema import REPORT_SCHEMA_VERSION, AnalysisReportSchema


TRACEBACK_PATTERNS = (
    re.compile(r"\bTraceback \(most recent call last\)\b"),
    re.compile(r'File "[^"]+\.py", line \d+'),
    re.compile(r"\b(?:RuntimeError|ValueError|TypeError|KeyError|Exception):\s"),
    re.compile(r"\bsite-packages\b"),
)


def dig(payload: Any, dotted_path: str) -> Any:
    """Resolve a dotted path through dict-like objects."""
    current = payload
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def collect_string_values(payload: Any) -> List[str]:
    """Collect all string leaves from nested mappings/lists."""
    found: List[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            found.append(node)
            return
        if isinstance(node, Mapping):
            for value in node.values():
                _walk(value)
            return
        if isinstance(node, Sequence) and not isinstance(node, (bytes, bytearray)):
            for item in node:
                _walk(item)

    _walk(payload)
    return found


def assert_no_traceback_leakage(payload: Any, *, case_id: str) -> None:
    """Fail if common traceback / exception-leakage patterns appear in text."""
    for text in collect_string_values(payload):
        for pattern in TRACEBACK_PATTERNS:
            if pattern.search(text):
                raise AssertionError(
                    f"[{case_id}] traceback/exception leakage matched {pattern.pattern!r} in: {text[:200]!r}"
                )


def assert_schema_version(report: Mapping[str, Any], expected: Optional[str], *, case_id: str) -> None:
    """Assert report schema_version when present or expected."""
    actual = report.get("schema_version", REPORT_SCHEMA_VERSION)
    if expected is None:
        expected = REPORT_SCHEMA_VERSION
    if actual != expected:
        raise AssertionError(
            f"[{case_id}] schema_version mismatch: expected {expected!r}, got {actual!r}"
        )


def assert_report_schema_parseable(report: Mapping[str, Any], *, case_id: str) -> AnalysisReportSchema:
    """Parse the public report structure through AnalysisReportSchema."""
    try:
        return AnalysisReportSchema.model_validate(dict(report))
    except Exception as exc:  # pragma: no cover - exercised by negative unit tests
        raise AssertionError(f"[{case_id}] report failed AnalysisReportSchema validation: {exc}") from exc


def report_to_analysis_result(report: Mapping[str, Any], *, code: str, name: str) -> AnalysisResult:
    """Project a panel report dict onto AnalysisResult for integrity checks."""
    return AnalysisResult(
        code=code,
        name=name or str(report.get("stock_name") or code),
        sentiment_score=int(report.get("sentiment_score") or 0),
        trend_prediction=str(report.get("trend_prediction") or ""),
        operation_advice=str(report.get("operation_advice") or ""),
        decision_type=str(report.get("decision_type") or "hold"),
        confidence_level=str(report.get("confidence_level") or ""),
        dashboard=report.get("dashboard") if isinstance(report.get("dashboard"), dict) else {},
        analysis_summary=str(report.get("analysis_summary") or ""),
        risk_warning=str(report.get("risk_warning") or ""),
        key_points=str(report.get("key_points") or ""),
    )


def assert_content_integrity(report: Mapping[str, Any], *, code: str, name: str, case_id: str) -> None:
    """Reuse production content-integrity rules on the fixture report."""
    result = report_to_analysis_result(report, code=code, name=name)
    ok, missing = check_content_integrity(result)
    if not ok:
        raise AssertionError(f"[{case_id}] content integrity failed; missing={missing}")


def assert_non_empty_risk_surface(report: Mapping[str, Any], *, case_id: str) -> None:
    """Require a non-empty risk_warning and list-typed risk_alerts."""
    risk_warning = report.get("risk_warning")
    if not isinstance(risk_warning, str) or not risk_warning.strip():
        raise AssertionError(f"[{case_id}] risk_warning must be a non-empty string")
    alerts = dig(report, "dashboard.intelligence.risk_alerts")
    if not isinstance(alerts, list):
        raise AssertionError(f"[{case_id}] dashboard.intelligence.risk_alerts must be a list")


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "").replace(",", "")
        if not cleaned or cleaned.upper() in {"N/A", "NA", "NULL", "NONE", "—", "-"}:
            return None
        try:
            number = float(cleaned)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def assert_numeric_consistency(
    report: Mapping[str, Any],
    numeric_paths: Mapping[str, Any],
    *,
    case_id: str,
    abs_tol: float = 1e-6,
    rel_tol: float = 1e-9,
) -> None:
    """Fail when structured report numbers contradict frozen expected values."""
    for path, expected_raw in numeric_paths.items():
        expected = _as_float(expected_raw)
        if expected is None:
            raise AssertionError(f"[{case_id}] expectation numeric_paths[{path!r}] is not numeric")
        actual_raw = dig(report, path)
        actual = _as_float(actual_raw)
        if actual is None:
            raise AssertionError(
                f"[{case_id}] missing or non-numeric value at {path}: {actual_raw!r}"
            )
        if not math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol):
            raise AssertionError(
                f"[{case_id}] numeric contradiction at {path}: "
                f"report={actual!r} fixture={expected!r}"
            )


def _joined_text(report: Mapping[str, Any]) -> str:
    return "\n".join(collect_string_values(report)).lower()


def assert_sources_and_gaps(
    report: Mapping[str, Any],
    frozen_sources: Mapping[str, Any],
    *,
    required_present: Sequence[str],
    required_gaps: Sequence[str],
    case_id: str,
) -> None:
    """Require present sources (or as-of stamps) and explicit gap markers for missing ones."""
    data_sources = report.get("data_sources")
    if not isinstance(data_sources, str) or not data_sources.strip():
        raise AssertionError(
            f"[{case_id}] data_sources must be a non-empty string for source auditability"
        )

    lowered_sources = data_sources.lower()
    blob = _joined_text(report)

    for key in required_present:
        source_meta = frozen_sources.get(key) if isinstance(frozen_sources, Mapping) else None
        if not isinstance(source_meta, Mapping) or not source_meta.get("present", False):
            raise AssertionError(
                f"[{case_id}] required present source {key!r} is not marked present in frozen_inputs.sources"
            )
        as_of = source_meta.get("as_of")
        token_ok = key.lower() in lowered_sources
        as_of_ok = isinstance(as_of, str) and as_of and as_of.lower() in lowered_sources
        if not (token_ok or as_of_ok):
            raise AssertionError(
                f"[{case_id}] present source {key!r} is neither named nor as-of stamped in "
                f"data_sources={data_sources!r}"
            )

    for gap in required_gaps:
        token = str(gap).lower()
        if token not in blob:
            raise AssertionError(
                f"[{case_id}] required gap marker {gap!r} was not found in report text/risk surface"
            )


def assert_required_substrings(
    report: Mapping[str, Any],
    substrings: Sequence[str],
    *,
    case_id: str,
) -> None:
    """Require case-specific substrings (e.g. conflict language)."""
    blob = _joined_text(report)
    for item in substrings:
        if str(item).lower() not in blob:
            raise AssertionError(f"[{case_id}] required substring {item!r} not found in report text")


def evaluate_case(case: Mapping[str, Any]) -> None:
    """Run the full offline assertion suite for one panel case."""
    case_id = str(case.get("id") or "<unknown>")
    report = case.get("report")
    if not isinstance(report, Mapping):
        raise AssertionError(f"[{case_id}] case.report must be an object")
    frozen = case.get("frozen_inputs")
    if not isinstance(frozen, Mapping):
        raise AssertionError(f"[{case_id}] case.frozen_inputs must be an object")
    expectations = case.get("expectations")
    if not isinstance(expectations, Mapping):
        raise AssertionError(f"[{case_id}] case.expectations must be an object")

    code = str(frozen.get("stock_code") or "")
    name = str(frozen.get("stock_name") or report.get("stock_name") or code)
    if not code:
        raise AssertionError(f"[{case_id}] frozen_inputs.stock_code is required")

    assert_report_schema_parseable(report, case_id=case_id)
    assert_schema_version(
        report,
        expectations.get("require_schema_version"),
        case_id=case_id,
    )
    assert_content_integrity(report, code=code, name=name, case_id=case_id)
    if expectations.get("require_risk_warning", True):
        assert_non_empty_risk_surface(report, case_id=case_id)
    if expectations.get("forbid_traceback_leakage", True):
        assert_no_traceback_leakage(report, case_id=case_id)

    numeric_paths = expectations.get("numeric_paths") or {}
    if not isinstance(numeric_paths, Mapping):
        raise AssertionError(f"[{case_id}] expectations.numeric_paths must be an object")
    assert_numeric_consistency(report, numeric_paths, case_id=case_id)

    sources = frozen.get("sources") or {}
    if not isinstance(sources, Mapping):
        raise AssertionError(f"[{case_id}] frozen_inputs.sources must be an object")
    assert_sources_and_gaps(
        report,
        sources,
        required_present=list(expectations.get("required_source_keys_present") or []),
        required_gaps=list(expectations.get("required_gaps") or []),
        case_id=case_id,
    )
    assert_required_substrings(
        report,
        list(expectations.get("required_substrings") or []),
        case_id=case_id,
    )


def invent_price_contradiction(case: Mapping[str, Any], *, path: str, bogus_value: float) -> Dict[str, Any]:
    """Return a deep-copied case with one structured number deliberately corrupted."""
    mutated: MutableMapping[str, Any] = copy.deepcopy(dict(case))
    report = mutated.get("report")
    if not isinstance(report, MutableMapping):
        raise TypeError("case.report must be a mapping")
    parts = path.split(".")
    cursor: Any = report
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, MutableMapping):
            raise KeyError(path)
        cursor = nxt
    cursor[parts[-1]] = bogus_value
    return dict(mutated)
