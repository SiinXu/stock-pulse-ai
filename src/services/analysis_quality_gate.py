# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Pipeline analysis quality gate — no invented facts (Issue #887).

Reuses the offline agent-eval **rule dimensions** as the sole scoring
standard (no parallel rubric). Pipeline evidence and conclusion claims are
projected into the same ``FinancialFact`` / ``FinancialClaim`` shapes scored
by :mod:`src.services.agent_eval_service`.

Failure path vs advisory path
-----------------------------
* **Failure path** (``factuality`` only): ungrounded claims drive
  annotate/intercept.
* **Advisory path** (``boundary_honesty``): still scored with the offline
  scorer for ``eval_hook`` / trace transparency, but never flips the gate
  verdict or demotes strata. Soft ``data_quality.limitations`` do not mark
  data missing; directional forbids are never enabled by default.

Configurable failure policy:

* ``annotate`` (default): demote ungrounded fact statements to model opinion
* ``intercept``: fail the analysis result so it is not treated as success

Gate-internal exceptions never pass silently: they fail closed to
``annotate`` with ``verdict=gate_error``.
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.schemas.report_strata import (
    ensure_report_strata,
    resolve_report_strata,
)
from src.services.agent_eval_service import (
    ALL_DIMENSIONS,
    EVALUATOR_VERSION,
    JUDGE_RULE,
    RULE_DIMENSIONS,
    EvalCheckResult,
    score_boundary_honesty,
    score_factuality,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

QUALITY_GATE_SCHEMA_VERSION = "analysis-quality-gate/v1"
QUALITY_GATE_VERSION = "analysis-quality-gate-v1"

# Failure path: only factuality drives annotate/intercept (no invented facts).
DEFAULT_GATE_FAILURE_DIMENSIONS: Tuple[str, ...] = ("factuality",)
# Advisory path: same offline scorer catalog, recorded in trace only.
DEFAULT_GATE_ADVISORY_DIMENSIONS: Tuple[str, ...] = ("boundary_honesty",)
# Full default eval-hook catalog (failure + advisory).
DEFAULT_GATE_DIMENSIONS: Tuple[str, ...] = (
    DEFAULT_GATE_FAILURE_DIMENSIONS + DEFAULT_GATE_ADVISORY_DIMENSIONS
)

_MAX_TRACE_CHECKS = 32
_MAX_TRACE_DETAIL = 300
_MAX_UNGROUNDED = 20
_NUMBER_RE = re.compile(
    r"(?<![\w./])(?P<sign>[-+]?)(?P<body>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?(?P<pct>%)?"
)
_OPINION_PREFIX_EN = "[Opinion / ungrounded] "
_OPINION_PREFIX_ZH = "【观点/未核验】"
_OPINION_PREFIX_KO = "[의견/미검증] "

_KNOWN_FIELD_HINTS: Tuple[Tuple[str, str, str], ...] = (
    ("price|现价|股价|报价|last", "quote.price", "price"),
    ("change_pct|涨跌幅|pct|%|涨幅|跌幅", "quote.change_pct", "percent"),
    ("pe|市盈率", "fundamentals.pe", "ratio"),
    ("pb|市净率", "fundamentals.pb", "ratio"),
)


class QualityGateFailurePolicy(str, Enum):
    """What to do when the gate finds ungrounded factual claims."""

    ANNOTATE = "annotate"
    INTERCEPT = "intercept"


class QualityGateVerdict(str, Enum):
    """Deterministic gate outcomes recorded in trace."""

    PASS = "pass"
    ANNOTATE = "annotate"
    INTERCEPT = "intercept"
    GATE_ERROR = "gate_error"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class AnalysisQualityGateResult:
    """Traceable result of one pipeline quality-gate evaluation."""

    verdict: QualityGateVerdict
    failure_policy: QualityGateFailurePolicy
    enabled: bool
    passed: bool
    rule_score: Optional[float]
    dimensions: Tuple[str, ...]
    checks: Tuple[Dict[str, Any], ...]
    ungrounded_claim_ids: Tuple[str, ...]
    ungrounded_statements: Tuple[str, ...]
    fact_count: int
    claim_count: int
    evaluation_id: str
    evaluated_at: str
    fail_closed: bool = False
    action_taken: str = "none"
    detail: str = ""
    failure_dimensions: Tuple[str, ...] = DEFAULT_GATE_FAILURE_DIMENSIONS
    advisory_dimensions: Tuple[str, ...] = DEFAULT_GATE_ADVISORY_DIMENSIONS
    failure_rule_score: Optional[float] = None
    advisory_rule_score: Optional[float] = None
    failure_reason_codes: Tuple[str, ...] = ()
    evaluator_version: str = EVALUATOR_VERSION
    gate_version: str = QUALITY_GATE_VERSION

    def to_trace_dict(self) -> Dict[str, Any]:
        """Low-sensitivity dict safe for traces, dashboard, and raw_result."""
        return {
            "schema_version": QUALITY_GATE_SCHEMA_VERSION,
            "gate_version": self.gate_version,
            "evaluator_version": self.evaluator_version,
            "verdict": self.verdict.value,
            "failure_policy": self.failure_policy.value,
            "enabled": self.enabled,
            "passed": self.passed,
            "rule_score": self.rule_score,
            "failure_rule_score": self.failure_rule_score,
            "advisory_rule_score": self.advisory_rule_score,
            "dimensions": list(self.dimensions),
            "failure_dimensions": list(self.failure_dimensions),
            "advisory_dimensions": list(self.advisory_dimensions),
            "failure_reason_codes": list(self.failure_reason_codes),
            "checks": list(self.checks),
            "ungrounded_claim_ids": list(self.ungrounded_claim_ids),
            "ungrounded_statements": list(self.ungrounded_statements),
            "fact_count": self.fact_count,
            "claim_count": self.claim_count,
            "evaluation_id": self.evaluation_id,
            "evaluated_at": self.evaluated_at,
            "fail_closed": self.fail_closed,
            "action_taken": self.action_taken,
            "detail": self.detail[:_MAX_TRACE_DETAIL],
            "eval_hook": {
                "dimensions": list(self.dimensions),
                "failure_dimensions": list(self.failure_dimensions),
                "advisory_dimensions": list(self.advisory_dimensions),
                "rule_score": self.rule_score,
                "failure_rule_score": self.failure_rule_score,
                "advisory_rule_score": self.advisory_rule_score,
                "failure_reason_codes": list(self.failure_reason_codes),
                "rule_dimensions_catalog": list(RULE_DIMENSIONS),
                "all_dimensions_catalog": list(ALL_DIMENSIONS),
                "check_count": len(self.checks),
            },
        }


def parse_quality_gate_failure_policy(value: Optional[str]) -> str:
    """Parse failure policy; reject unknown values at config load time."""
    normalized = str(value or QualityGateFailurePolicy.ANNOTATE.value).strip().lower()
    if normalized not in {
        QualityGateFailurePolicy.ANNOTATE.value,
        QualityGateFailurePolicy.INTERCEPT.value,
    }:
        raise ValueError(
            "ANALYSIS_QUALITY_GATE_ON_FAILURE must be one of: annotate, intercept"
        )
    return normalized


def resolve_quality_gate_config(config: Any = None) -> Tuple[bool, QualityGateFailurePolicy]:
    """Return (enabled, failure_policy). Defaults: enabled=True, annotate."""
    if config is None:
        return True, QualityGateFailurePolicy.ANNOTATE
    enabled_raw = getattr(config, "analysis_quality_gate_enabled", True)
    enabled = enabled_raw is True if isinstance(enabled_raw, bool) else bool(enabled_raw)
    policy_raw = getattr(
        config,
        "analysis_quality_gate_on_failure",
        QualityGateFailurePolicy.ANNOTATE.value,
    )
    policy = QualityGateFailurePolicy(
        parse_quality_gate_failure_policy(str(policy_raw or "annotate"))
    )
    return enabled, policy


def _finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("%", "")
        if not cleaned or cleaned.upper() in {"N/A", "NA", "NULL", "NONE", "—", "-"}:
            return None
        try:
            number = float(cleaned)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _as_of_now() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _opinion_prefix(language: Optional[str]) -> str:
    key = (language or "zh").strip().lower()
    if key.startswith("en"):
        return _OPINION_PREFIX_EN
    if key.startswith("ko"):
        return _OPINION_PREFIX_KO
    return _OPINION_PREFIX_ZH


def _check_to_trace(check: EvalCheckResult) -> Dict[str, Any]:
    return {
        "dimension": check.dimension,
        "check_id": check.check_id,
        "passed": bool(check.passed),
        "status": check.status,
        "judge": check.judge,
        "detail": str(check.detail or "")[:_MAX_TRACE_DETAIL],
    }


def _rule_score(checks: Sequence[EvalCheckResult]) -> Optional[float]:
    scored = [c for c in checks if c.judge == "rule" and not c.skipped]
    if not scored:
        return None
    passed = sum(1 for c in scored if c.passed and c.status != "invalid")
    return round(passed / len(scored), 4)


def _dig(mapping: Any, path: str) -> Any:
    current = mapping
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _append_fact(
    facts: List[Dict[str, Any]],
    *,
    fact_id: str,
    field_path: str,
    value: Any,
    unit: str,
    as_of: str,
    source_id: str,
) -> None:
    number = _finite_float(value)
    if number is None:
        return
    if any(item.get("fact_id") == fact_id for item in facts):
        return
    facts.append(
        {
            "fact_id": fact_id,
            "field_path": field_path,
            "value": number,
            "unit": unit,
            "as_of": as_of,
            "source_id": source_id,
        }
    )


def project_facts_from_evidence(
    *,
    evidence_context: Optional[Mapping[str, Any]] = None,
    analysis_context_pack_overview: Optional[Mapping[str, Any]] = None,
    market_snapshot: Optional[Mapping[str, Any]] = None,
    fundamental_context: Optional[Mapping[str, Any]] = None,
    current_price: Any = None,
    change_pct: Any = None,
    as_of: Optional[str] = None,
    source_id: str = "pipeline",
) -> List[Dict[str, Any]]:
    """Project pipeline evidence into agent-eval ``FinancialFact`` dicts."""
    facts: List[Dict[str, Any]] = []
    stamp = (as_of or _as_of_now()).strip() or _as_of_now()
    src = (source_id or "pipeline").strip() or "pipeline"

    if isinstance(evidence_context, Mapping):
        raw_facts = evidence_context.get("facts")
        if isinstance(raw_facts, list):
            for item in raw_facts:
                if not isinstance(item, Mapping):
                    continue
                _append_fact(
                    facts,
                    fact_id=str(item.get("fact_id") or "").strip()
                    or f"ctx-{len(facts)}",
                    field_path=str(item.get("field_path") or "unknown"),
                    value=item.get("value"),
                    unit=str(item.get("unit") or "unknown"),
                    as_of=str(item.get("as_of") or stamp),
                    source_id=str(item.get("source_id") or src),
                )

    def _from_mapping(
        mapping: Optional[Mapping[str, Any]],
        *,
        keys: Sequence[Tuple[str, str, str]],
        prefix: str,
    ) -> None:
        if not isinstance(mapping, Mapping):
            return
        for key, field_path, unit in keys:
            if key not in mapping:
                continue
            _append_fact(
                facts,
                fact_id=f"{prefix}-{key}",
                field_path=field_path,
                value=mapping.get(key),
                unit=unit,
                as_of=stamp,
                source_id=src,
            )

    overview = analysis_context_pack_overview
    if isinstance(overview, Mapping):
        for block_name in ("quote", "fundamentals", "daily_bars", "technical"):
            block = overview.get(block_name)
            items = None
            if isinstance(block, Mapping):
                items = block.get("items") if isinstance(block.get("items"), Mapping) else block
            if not isinstance(items, Mapping):
                continue
            for item_key, item_val in items.items():
                value = item_val
                item_source = src
                item_as_of = stamp
                if isinstance(item_val, Mapping):
                    value = item_val.get("value")
                    if item_val.get("source"):
                        item_source = str(item_val.get("source"))
                    if item_val.get("timestamp"):
                        item_as_of = str(item_val.get("timestamp"))[:64]
                field_path = f"{block_name}.{item_key}"
                unit = "ratio" if item_key in {"pe", "pb", "roe"} else (
                    "percent"
                    if "pct" in str(item_key).lower() or "change" in str(item_key).lower()
                    else "number"
                )
                if item_key in {"price", "close", "last", "current_price"}:
                    unit = "price"
                _append_fact(
                    facts,
                    fact_id=f"pack-{block_name}-{item_key}",
                    field_path=field_path,
                    value=value,
                    unit=unit,
                    as_of=item_as_of,
                    source_id=item_source,
                )

    _from_mapping(
        market_snapshot if isinstance(market_snapshot, Mapping) else None,
        keys=(
            ("price", "quote.price", "price"),
            ("current_price", "quote.price", "price"),
            ("close", "quote.close", "price"),
            ("change_pct", "quote.change_pct", "percent"),
            ("pct_chg", "quote.change_pct", "percent"),
        ),
        prefix="snapshot",
    )
    _from_mapping(
        fundamental_context if isinstance(fundamental_context, Mapping) else None,
        keys=(
            ("pe", "fundamentals.pe", "ratio"),
            ("pb", "fundamentals.pb", "ratio"),
            ("pe_ttm", "fundamentals.pe_ttm", "ratio"),
            ("roe", "fundamentals.roe", "ratio"),
        ),
        prefix="fund",
    )

    _append_fact(
        facts,
        fact_id="pipeline-current-price",
        field_path="quote.price",
        value=current_price,
        unit="price",
        as_of=stamp,
        source_id=src,
    )
    _append_fact(
        facts,
        fact_id="pipeline-change-pct",
        field_path="quote.change_pct",
        value=change_pct,
        unit="percent",
        as_of=stamp,
        source_id=src,
    )
    return facts


def _extract_numbers(text: str) -> List[Tuple[float, str]]:
    """Return (value, unit_hint) pairs from free text."""
    found: List[Tuple[float, str]] = []
    for match in _NUMBER_RE.finditer(text or ""):
        body = f"{match.group('sign') or ''}{match.group('body')}{match.group('frac') or ''}"
        cleaned = body.replace(",", "")
        try:
            number = float(cleaned)
        except ValueError:
            continue
        if not math.isfinite(number):
            continue
        unit = "percent" if match.group("pct") else "number"
        found.append((number, unit))
    return found


def _find_matching_fact(
    facts: Sequence[Mapping[str, Any]],
    *,
    value: float,
    unit_hint: str,
    statement: str = "",
) -> Optional[Mapping[str, Any]]:
    statement_l = (statement or "").lower()
    candidates = [
        fact
        for fact in facts
        if _finite_float(fact.get("value")) is not None
        and math.isclose(float(fact["value"]), value, rel_tol=0.0, abs_tol=1e-9)
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    if unit_hint == "percent":
        percentish = [
            c
            for c in candidates
            if str(c.get("unit") or "") in {"percent", "pct", "ratio"}
            or "pct" in str(c.get("field_path") or "")
        ]
        if len(percentish) == 1:
            return percentish[0]
    for markers, field_path, _unit in _KNOWN_FIELD_HINTS:
        if any(token and token in statement_l for token in markers.split("|")):
            path_hits = [
                c
                for c in candidates
                if str(c.get("field_path") or "") == field_path
                or field_path.split(".")[-1] in str(c.get("field_path") or "")
            ]
            if path_hits:
                return path_hits[0]
    return candidates[0]


def project_claims_from_result(
    result: Any,
    *,
    facts: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, str]]:
    """Project conclusion fact claims into agent-eval ``FinancialClaim`` dicts.

    Returns ``(claims, ungrounded_claim_ids, claim_id_to_statement)``.
    """
    claims: List[Dict[str, Any]] = []
    ungrounded: List[str] = []
    statements: Dict[str, str] = {}
    stamp = _as_of_now()

    structured: List[Any] = []
    for source in (
        getattr(result, "claims", None),
        _dig(getattr(result, "dashboard", None), "claims"),
        _dig(getattr(result, "dashboard", None), "quality_claims"),
        _dig(getattr(result, "dashboard", None), "eval_claims"),
    ):
        if isinstance(source, list):
            structured.extend(source)
    seen_ids: set[str] = set()
    for index, raw in enumerate(structured):
        if not isinstance(raw, Mapping):
            continue
        claim_id = str(raw.get("claim_id") or f"structured-{index}").strip()
        if not claim_id or claim_id in seen_ids:
            claim_id = f"structured-{index}"
        seen_ids.add(claim_id)
        claim = {
            "claim_id": claim_id,
            "source_fact_id": str(raw.get("source_fact_id") or "").strip() or "__missing__",
            "field_path": str(raw.get("field_path") or "unknown"),
            "value": raw.get("value"),
            "unit": str(raw.get("unit") or "unknown"),
            "as_of": str(raw.get("as_of") or stamp),
            "source_id": str(raw.get("source_id") or "output"),
        }
        number = _finite_float(claim["value"])
        if number is None:
            continue
        claim["value"] = number
        claims.append(claim)
        statements[claim_id] = str(
            raw.get("statement") or f"{claim['field_path']}={number}"
        )[:_MAX_TRACE_DETAIL]

    strata = resolve_report_strata(result, ensure=False)
    if strata is not None:
        for index, fact_line in enumerate(strata.verified_facts or []):
            statement = str(getattr(fact_line, "statement", "") or "").strip()
            if not statement:
                continue
            numbers = _extract_numbers(statement)
            if not numbers:
                continue
            for num_index, (value, unit_hint) in enumerate(numbers):
                claim_id = f"strata-fact-{index}-{num_index}"
                matched = _find_matching_fact(
                    facts, value=value, unit_hint=unit_hint, statement=statement
                )
                if matched is None:
                    claim = {
                        "claim_id": claim_id,
                        "source_fact_id": "__missing__",
                        "field_path": "verified_facts.statement",
                        "value": value,
                        "unit": unit_hint,
                        "as_of": str(getattr(fact_line, "as_of", None) or stamp),
                        "source_id": str(
                            getattr(fact_line, "source_id", None) or "verified_facts"
                        ),
                    }
                    ungrounded.append(claim_id)
                else:
                    claim = {
                        "claim_id": claim_id,
                        "source_fact_id": str(matched["fact_id"]),
                        "field_path": str(matched["field_path"]),
                        "value": float(matched["value"]),
                        "unit": str(matched["unit"]),
                        "as_of": str(matched["as_of"]),
                        "source_id": str(matched["source_id"]),
                    }
                claims.append(claim)
                statements[claim_id] = statement[:_MAX_TRACE_DETAIL]

    return claims, ungrounded, statements


def _has_price_evidence(facts: Sequence[Mapping[str, Any]]) -> bool:
    """True when projected evidence includes at least one price-like fact."""
    for fact in facts:
        if not isinstance(fact, Mapping):
            continue
        field_path = str(fact.get("field_path") or "").lower()
        unit = str(fact.get("unit") or "").lower()
        fact_id = str(fact.get("fact_id") or "").lower()
        if unit in {"price", "cny", "usd", "hkd"}:
            return True
        if any(token in field_path for token in ("price", "close", "last", "quote.")):
            return True
        if "price" in fact_id:
            return True
    return False


def _core_quote_missing(
    analysis_context_pack_overview: Optional[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
) -> bool:
    """Strict missing signal for advisory honesty only (not soft limitations).

    Soft partial limitations (news window, etc.) must not mark data missing.
    Only hard core-quote unavailability or total absence of price evidence.
    """
    if not facts:
        return True
    if not _has_price_evidence(facts):
        return True
    if not isinstance(analysis_context_pack_overview, Mapping):
        return False
    quote = analysis_context_pack_overview.get("quote")
    if isinstance(quote, Mapping):
        status = str(quote.get("status") or "").strip().lower()
        if status in {"missing", "fetch_failed", "not_supported"}:
            return True
    quality = analysis_context_pack_overview.get("data_quality")
    if isinstance(quality, Mapping):
        level = str(quality.get("level") or "").strip().lower()
        if level in {"poor", "missing"}:
            # Only when quote price evidence is also absent.
            return not _has_price_evidence(facts)
    return False


def evaluate_analysis_quality(
    *,
    facts: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    result: Any = None,
    analysis_context_pack_overview: Optional[Mapping[str, Any]] = None,
    dimensions: Sequence[str] = DEFAULT_GATE_DIMENSIONS,
    failure_dimensions: Sequence[str] = DEFAULT_GATE_FAILURE_DIMENSIONS,
    advisory_dimensions: Sequence[str] = DEFAULT_GATE_ADVISORY_DIMENSIONS,
) -> Tuple[
    List[EvalCheckResult],
    Optional[float],
    Optional[float],
    Optional[float],
]:
    """Run offline eval scorers on projected pipeline artifacts.

    Returns
    ``(checks, overall_rule_score, failure_rule_score, advisory_rule_score)``.
    Only checks under ``failure_dimensions`` should drive annotate/intercept.
    """
    failure_dim_set = set(failure_dimensions)
    advisory_dim_set = set(advisory_dimensions)
    context: Dict[str, Any] = {
        "facts": list(facts),
        # Strict core-missing only; soft limitations are not data_missing.
        "data_missing": _core_quote_missing(analysis_context_pack_overview, facts),
    }
    output: Dict[str, Any] = {
        "claims": list(claims),
        "signal": getattr(result, "decision_type", None)
        or getattr(result, "action", None)
        or "hold",
        "confidence": getattr(result, "confidence_level", None),
        "confidence_level": getattr(result, "confidence_level", None),
        "summary": getattr(result, "analysis_summary", None) or "",
    }
    checks: List[EvalCheckResult] = []
    for dimension in dimensions:
        if dimension == "factuality":
            if not claims:
                checks.append(
                    EvalCheckResult(
                        dimension="factuality",
                        check_id="no_numeric_fact_claims",
                        passed=True,
                        detail="no numeric fact claims presented in conclusion",
                        judge=JUDGE_RULE,
                        skipped=True,
                        status="skipped",
                    )
                )
            else:
                checks.extend(score_factuality(context, output, {}))
        elif dimension == "boundary_honesty":
            # Advisory only: never forbid directional by default (offline cases
            # opt into that forbid via explicit rubric; runtime must not).
            checks.extend(
                score_boundary_honesty(
                    context,
                    output,
                    {
                        "data_missing": context["data_missing"],
                        "require_limitation_mention": False,
                        "forbid_directional_when_missing": False,
                    },
                )
            )
    overall = _rule_score(checks)
    failure_checks = [c for c in checks if c.dimension in failure_dim_set]
    advisory_checks = [c for c in checks if c.dimension in advisory_dim_set]
    return (
        checks,
        overall,
        _rule_score(failure_checks),
        _rule_score(advisory_checks),
    )


def _collect_failed_claim_ids(checks: Sequence[EvalCheckResult]) -> List[str]:
    failed: List[str] = []
    for check in checks:
        if check.passed or check.skipped:
            continue
        detail = check.detail or ""
        match = re.search(r"claim '([^']+)'", detail)
        if match:
            failed.append(match.group(1))
            continue
        match = re.search(r"claim \"([^\"]+)\"", detail)
        if match:
            failed.append(match.group(1))
    return failed


def _demote_ungrounded_strata(
    result: Any,
    *,
    ungrounded_statements: Sequence[str],
    language: Optional[str],
) -> str:
    """Move ungrounded verified_facts into model_inference. Returns action id."""
    if not ungrounded_statements:
        return "none"
    strata_model = resolve_report_strata(result, language=language, ensure=True)
    if strata_model is None:
        strata_model = ensure_report_strata(None, language=language)
    prefix = _opinion_prefix(language)
    ungrounded_set = {s.strip() for s in ungrounded_statements if s and s.strip()}
    kept_facts = []
    demoted: List[str] = []
    for item in strata_model.verified_facts or []:
        statement = str(getattr(item, "statement", "") or "").strip()
        if statement in ungrounded_set:
            demoted.append(
                statement if statement.startswith(prefix) else f"{prefix}{statement}"
            )
        else:
            kept_facts.append(item)
    if not demoted:
        return "none"
    inference = list(strata_model.model_inference or [])
    for line in demoted:
        if line not in inference:
            inference.append(line)
    strata_model.verified_facts = kept_facts
    strata_model.model_inference = inference
    public = strata_model.to_public_dict()
    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        dashboard = {}
        result.dashboard = dashboard
    dashboard = dict(dashboard)
    dashboard["report_strata"] = public
    result.dashboard = dashboard
    return "demote_verified_facts_to_inference"


def _attach_gate_to_result(result: Any, gate: AnalysisQualityGateResult) -> None:
    trace = gate.to_trace_dict()
    result.quality_gate_result = trace
    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        dashboard = {}
        result.dashboard = dashboard
    else:
        dashboard = dict(dashboard)
        result.dashboard = dashboard
    dashboard["quality_gate"] = trace


def _build_result(
    *,
    verdict: QualityGateVerdict,
    failure_policy: QualityGateFailurePolicy,
    enabled: bool,
    passed: bool,
    rule_score: Optional[float],
    dimensions: Sequence[str],
    checks: Sequence[EvalCheckResult],
    ungrounded_claim_ids: Sequence[str],
    ungrounded_statements: Sequence[str],
    fact_count: int,
    claim_count: int,
    action_taken: str,
    detail: str,
    fail_closed: bool = False,
    evaluation_id: Optional[str] = None,
    failure_dimensions: Sequence[str] = DEFAULT_GATE_FAILURE_DIMENSIONS,
    advisory_dimensions: Sequence[str] = DEFAULT_GATE_ADVISORY_DIMENSIONS,
    failure_rule_score: Optional[float] = None,
    advisory_rule_score: Optional[float] = None,
    failure_reason_codes: Sequence[str] = (),
) -> AnalysisQualityGateResult:
    bounded_checks = tuple(
        _check_to_trace(c) for c in list(checks)[:_MAX_TRACE_CHECKS]
    )
    return AnalysisQualityGateResult(
        verdict=verdict,
        failure_policy=failure_policy,
        enabled=enabled,
        passed=passed,
        rule_score=rule_score,
        dimensions=tuple(dimensions),
        checks=bounded_checks,
        ungrounded_claim_ids=tuple(list(ungrounded_claim_ids)[:_MAX_UNGROUNDED]),
        ungrounded_statements=tuple(
            str(s)[:_MAX_TRACE_DETAIL]
            for s in list(ungrounded_statements)[:_MAX_UNGROUNDED]
        ),
        fact_count=int(fact_count),
        claim_count=int(claim_count),
        evaluation_id=(evaluation_id or uuid.uuid4().hex)[:64],
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        fail_closed=fail_closed,
        action_taken=action_taken,
        detail=detail[:_MAX_TRACE_DETAIL],
        failure_dimensions=tuple(failure_dimensions),
        advisory_dimensions=tuple(advisory_dimensions),
        failure_rule_score=failure_rule_score,
        advisory_rule_score=advisory_rule_score,
        failure_reason_codes=tuple(
            str(code)[:64] for code in list(failure_reason_codes)[:_MAX_UNGROUNDED]
        ),
    )


def apply_analysis_quality_gate(
    result: Any,
    *,
    config: Any = None,
    evidence_context: Optional[Mapping[str, Any]] = None,
    analysis_context_pack_overview: Optional[Mapping[str, Any]] = None,
    market_snapshot: Optional[Mapping[str, Any]] = None,
    fundamental_context: Optional[Mapping[str, Any]] = None,
    dimensions: Sequence[str] = DEFAULT_GATE_DIMENSIONS,
) -> AnalysisQualityGateResult:
    """Evaluate and apply the pipeline quality gate.

    Never raises to the caller for gate-internal failures: exceptions fail
    closed to annotate and still attach a trace payload.
    """
    enabled, failure_policy = resolve_quality_gate_config(config)
    if result is None:
        return _build_result(
            verdict=QualityGateVerdict.SKIPPED,
            failure_policy=failure_policy,
            enabled=enabled,
            passed=True,
            rule_score=None,
            dimensions=dimensions,
            checks=(),
            ungrounded_claim_ids=(),
            ungrounded_statements=(),
            fact_count=0,
            claim_count=0,
            action_taken="none",
            detail="no analysis result",
        )

    if not enabled:
        gate = _build_result(
            verdict=QualityGateVerdict.SKIPPED,
            failure_policy=failure_policy,
            enabled=False,
            passed=True,
            rule_score=None,
            dimensions=dimensions,
            checks=(),
            ungrounded_claim_ids=(),
            ungrounded_statements=(),
            fact_count=0,
            claim_count=0,
            action_taken="skipped_disabled",
            detail="analysis quality gate disabled",
        )
        _attach_gate_to_result(result, gate)
        return gate

    try:
        overview = analysis_context_pack_overview
        if overview is None:
            overview = getattr(result, "analysis_context_pack_overview", None)
        snapshot = market_snapshot
        if snapshot is None:
            snapshot = getattr(result, "market_snapshot", None)
        fundamentals = fundamental_context
        if fundamentals is None:
            fundamentals = getattr(result, "fundamental_context", None)

        facts = project_facts_from_evidence(
            evidence_context=evidence_context,
            analysis_context_pack_overview=overview
            if isinstance(overview, Mapping)
            else None,
            market_snapshot=snapshot if isinstance(snapshot, Mapping) else None,
            fundamental_context=fundamentals
            if isinstance(fundamentals, Mapping)
            else None,
            current_price=getattr(result, "current_price", None),
            change_pct=getattr(result, "change_pct", None),
        )
        claims, projected_ungrounded, claim_statements = project_claims_from_result(
            result, facts=facts
        )
        (
            checks,
            rule_score,
            failure_rule_score,
            advisory_rule_score,
        ) = evaluate_analysis_quality(
            facts=facts,
            claims=claims,
            result=result,
            analysis_context_pack_overview=overview
            if isinstance(overview, Mapping)
            else None,
            dimensions=dimensions,
            failure_dimensions=DEFAULT_GATE_FAILURE_DIMENSIONS,
            advisory_dimensions=DEFAULT_GATE_ADVISORY_DIMENSIONS,
        )
        failure_dim_set = set(DEFAULT_GATE_FAILURE_DIMENSIONS)
        # Only factuality (failure-path) checks drive annotate/intercept.
        factuality_failures = [
            c
            for c in checks
            if c.dimension in failure_dim_set
            and (not c.skipped)
            and (not c.passed or c.status == "invalid")
        ]
        failed_ids = list(
            dict.fromkeys(
                projected_ungrounded
                + _collect_failed_claim_ids(factuality_failures)
            )
        )
        reason_codes: List[str] = []
        if failed_ids or any(
            c.check_id.startswith("structured_") or c.status == "invalid"
            for c in factuality_failures
        ):
            if failed_ids:
                reason_codes.append("ungrounded_claim")
            if any(c.status == "invalid" for c in factuality_failures):
                reason_codes.append("factuality_invalid")
            if any(
                c.check_id == "claim_bound_to_source_fact" and not c.passed
                for c in factuality_failures
            ):
                if "ungrounded_claim" not in reason_codes:
                    reason_codes.append("ungrounded_claim")
        # Advisory honesty is never a gate failure reason.
        advisory_failures = [
            c
            for c in checks
            if c.dimension in set(DEFAULT_GATE_ADVISORY_DIMENSIONS)
            and (not c.skipped)
            and not c.passed
        ]
        for check in advisory_failures:
            reason_codes.append(f"advisory:{check.check_id}")

        passed = not factuality_failures and not failed_ids

        ungrounded_statements = [
            claim_statements[cid]
            for cid in failed_ids
            if cid in claim_statements
        ]
        for cid in failed_ids:
            if cid in claim_statements:
                continue
            for claim in claims:
                if claim.get("claim_id") == cid:
                    ungrounded_statements.append(
                        f"{claim.get('field_path')}={claim.get('value')}"
                    )
                    break

        language = getattr(result, "report_language", None)
        action_taken = "none"
        verdict = QualityGateVerdict.PASS
        detail = "all presented fact claims bound to input evidence"

        if not passed:
            ungrounded_count = len(failed_ids) or len(factuality_failures)
            if failure_policy is QualityGateFailurePolicy.INTERCEPT:
                verdict = QualityGateVerdict.INTERCEPT
                action_taken = "intercept_analysis"
                detail = (
                    f"quality gate intercept: {ungrounded_count} "
                    f"factuality failure(s) "
                    f"[{', '.join(reason_codes) or 'ungrounded_claim'}]"
                )
                result.success = False
                result.error_code = "quality_gate_intercept"
                result.error_message = detail
            else:
                verdict = QualityGateVerdict.ANNOTATE
                action_taken = _demote_ungrounded_strata(
                    result,
                    ungrounded_statements=ungrounded_statements,
                    language=language,
                )
                if action_taken == "none":
                    action_taken = "annotate_trace_only"
                detail = (
                    f"quality gate annotate: {ungrounded_count} "
                    f"factuality failure(s) "
                    f"[{', '.join(reason_codes) or 'ungrounded_claim'}]"
                )
                if action_taken == "demote_verified_facts_to_inference":
                    dashboard = getattr(result, "dashboard", None)
                    if isinstance(dashboard, dict):
                        notes = dashboard.get("quality_annotations")
                        if not isinstance(notes, list):
                            notes = []
                        notes = list(notes)
                        notes.append(
                            {
                                "code": "ungrounded_facts_demoted",
                                "detail": detail[:_MAX_TRACE_DETAIL],
                            }
                        )
                        dashboard["quality_annotations"] = notes[:10]

        # Keep advisory reason codes out of the failure_reason_codes field when
        # the gate passed; still expose them only under eval_hook via checks.
        failure_reason_codes = tuple(
            code
            for code in reason_codes
            if not str(code).startswith("advisory:")
        )

        gate = _build_result(
            verdict=verdict,
            failure_policy=failure_policy,
            enabled=True,
            passed=passed,
            rule_score=rule_score,
            dimensions=dimensions,
            checks=checks,
            ungrounded_claim_ids=failed_ids,
            ungrounded_statements=ungrounded_statements,
            fact_count=len(facts),
            claim_count=len(claims),
            action_taken=action_taken,
            detail=detail,
            fail_closed=False,
            failure_dimensions=DEFAULT_GATE_FAILURE_DIMENSIONS,
            advisory_dimensions=DEFAULT_GATE_ADVISORY_DIMENSIONS,
            failure_rule_score=failure_rule_score,
            advisory_rule_score=advisory_rule_score,
            failure_reason_codes=failure_reason_codes,
        )
        _attach_gate_to_result(result, gate)
        return gate
    except Exception as exc:  # broad-exception: fallback_recorded - gate must fail closed to annotate
        log_safe_exception(
            logger,
            "Analysis quality gate failed closed to annotate",
            exc,
            error_code="analysis_quality_gate_error",
            level=logging.WARNING,
            context={
                "stock_code": getattr(result, "code", None),
            },
        )
        try:
            action = _demote_ungrounded_strata(
                result,
                ungrounded_statements=(),
                language=getattr(result, "report_language", None),
            )
        except Exception:  # broad-exception: fallback_recorded - demote best-effort only
            action = "gate_error_annotate"
        if action == "none":
            action = "gate_error_annotate"
        gate = _build_result(
            verdict=QualityGateVerdict.GATE_ERROR,
            failure_policy=QualityGateFailurePolicy.ANNOTATE,
            enabled=True,
            passed=False,
            rule_score=0.0,
            dimensions=dimensions,
            checks=(),
            ungrounded_claim_ids=(),
            ungrounded_statements=(),
            fact_count=0,
            claim_count=0,
            action_taken=action,
            detail=(
                f"quality gate internal error; fail-closed annotate: "
                f"{type(exc).__name__}"
            ),
            fail_closed=True,
        )
        try:
            _attach_gate_to_result(result, gate)
        except Exception:  # broad-exception: fallback_recorded - last-resort attach
            try:
                result.quality_gate_result = gate.to_trace_dict()
            except Exception:
                pass
        return gate


__all__ = [
    "DEFAULT_GATE_ADVISORY_DIMENSIONS",
    "DEFAULT_GATE_DIMENSIONS",
    "DEFAULT_GATE_FAILURE_DIMENSIONS",
    "QUALITY_GATE_SCHEMA_VERSION",
    "QUALITY_GATE_VERSION",
    "AnalysisQualityGateResult",
    "QualityGateFailurePolicy",
    "QualityGateVerdict",
    "apply_analysis_quality_gate",
    "evaluate_analysis_quality",
    "parse_quality_gate_failure_policy",
    "project_claims_from_result",
    "project_facts_from_evidence",
    "resolve_quality_gate_config",
]
