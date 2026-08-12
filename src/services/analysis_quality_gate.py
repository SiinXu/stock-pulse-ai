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
from inspect import getattr_static
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.config_parts.parsers import parse_quality_gate_failure_policy
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
_MAX_INPUT_FACTS = 256
_MAX_STRUCTURED_CLAIMS = 128
_MAX_VERIFIED_FACTS = 128
_MAX_NUMBERS_PER_STATEMENT = 16
_MAX_SCAN_CHARS = 20_000
_MAX_ID_CHARS = 128
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

# Numeric dashboard fields emitted by both the legacy analyzer and Agent path.
# These are actual runtime consumers, unlike optional test/eval-only claim arrays.
_DASHBOARD_NUMERIC_CLAIMS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    (
        "data_perspective.price_position.current_price",
        ("quote.price", "technical.current_price"),
        "price",
    ),
    ("data_perspective.price_position.ma5", ("technical.ma5",), "price"),
    ("data_perspective.price_position.ma10", ("technical.ma10",), "price"),
    ("data_perspective.price_position.ma20", ("technical.ma20",), "price"),
    (
        "data_perspective.price_position.bias_ma5",
        ("technical.bias_ma5",),
        "percent",
    ),
    (
        "data_perspective.price_position.support_level",
        ("technical.support_levels.",),
        "price",
    ),
    (
        "data_perspective.price_position.resistance_level",
        ("technical.resistance_levels.",),
        "price",
    ),
    (
        "data_perspective.volume_analysis.volume_ratio",
        ("technical.volume_ratio_5d",),
        "ratio",
    ),
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


def resolve_quality_gate_config(config: Any = None) -> Tuple[bool, QualityGateFailurePolicy]:
    """Return (enabled, failure_policy). Defaults: enabled=True, annotate."""
    if config is None:
        return True, QualityGateFailurePolicy.ANNOTATE
    try:
        getattr_static(config, "analysis_quality_gate_enabled")
    except AttributeError:
        enabled_raw = True
    else:
        enabled_raw = getattr(config, "analysis_quality_gate_enabled")
    if type(enabled_raw) is not bool:
        raise ValueError("analysis_quality_gate_enabled must be a boolean")

    try:
        getattr_static(config, "analysis_quality_gate_on_failure")
    except AttributeError:
        policy_raw = QualityGateFailurePolicy.ANNOTATE.value
    else:
        policy_raw = getattr(config, "analysis_quality_gate_on_failure")
    policy = QualityGateFailurePolicy(
        parse_quality_gate_failure_policy(str(policy_raw or "annotate"))
    )
    return enabled_raw, policy


def _finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except (OverflowError, ValueError):
            return None
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


def _bounded_text(value: Any, *, default: str = "", limit: int = _MAX_ID_CHARS) -> str:
    """Return stripped, bounded metadata without accepting container reprs."""
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return default
    text = str(value).strip()
    return text[:limit] if text else default


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
    if len(facts) >= _MAX_INPUT_FACTS:
        return
    number = _finite_float(value)
    if number is None:
        return
    bounded_id = _bounded_text(fact_id, default=f"fact-{len(facts)}")
    if any(item.get("fact_id") == bounded_id for item in facts):
        return
    facts.append(
        {
            "fact_id": bounded_id,
            "field_path": _bounded_text(field_path, default="unknown"),
            "value": number,
            "unit": _bounded_text(unit, default="unknown", limit=32),
            "as_of": _bounded_text(as_of, default=_as_of_now(), limit=64),
            "source_id": _bounded_text(source_id, default="pipeline"),
        }
    )


def project_facts_from_evidence(
    *,
    evidence_context: Optional[Mapping[str, Any]] = None,
    analysis_context_pack_overview: Optional[Mapping[str, Any]] = None,
    market_snapshot: Optional[Mapping[str, Any]] = None,
    fundamental_context: Optional[Mapping[str, Any]] = None,
    technical_context: Any = None,
    current_price: Any = None,
    change_pct: Any = None,
    as_of: Optional[str] = None,
    source_id: str = "pipeline",
) -> List[Dict[str, Any]]:
    """Project pipeline evidence into agent-eval ``FinancialFact`` dicts."""
    facts: List[Dict[str, Any]] = []
    stamp = _bounded_text(as_of, default=_as_of_now(), limit=64)
    src = _bounded_text(source_id, default="pipeline")

    if isinstance(evidence_context, Mapping):
        raw_facts = evidence_context.get("facts")
        if isinstance(raw_facts, list):
            for item in raw_facts[:_MAX_INPUT_FACTS]:
                if not isinstance(item, Mapping):
                    continue
                _append_fact(
                    facts,
                    fact_id=_bounded_text(
                        item.get("fact_id"), default=f"ctx-{len(facts)}"
                    ),
                    field_path=_bounded_text(
                        item.get("field_path"), default="unknown"
                    ),
                    value=item.get("value"),
                    unit=_bounded_text(item.get("unit"), default="unknown", limit=32),
                    as_of=_bounded_text(item.get("as_of"), default=stamp, limit=64),
                    source_id=_bounded_text(item.get("source_id"), default=src),
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

    # The public AnalysisContextPack overview intentionally contains statuses,
    # counts, and provenance only. It has no raw item values, so it must not be
    # treated as a factual-value source. It is consumed separately by the
    # boundary-honesty check below.
    del analysis_context_pack_overview

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

    technical_keys: Tuple[Tuple[str, str, str], ...] = (
        ("current_price", "technical.current_price", "price"),
        ("ma5", "technical.ma5", "price"),
        ("ma10", "technical.ma10", "price"),
        ("ma20", "technical.ma20", "price"),
        ("ma60", "technical.ma60", "price"),
        ("bias_ma5", "technical.bias_ma5", "percent"),
        ("bias_ma10", "technical.bias_ma10", "percent"),
        ("bias_ma20", "technical.bias_ma20", "percent"),
        ("volume_ratio_5d", "technical.volume_ratio_5d", "ratio"),
        ("macd_dif", "technical.macd_dif", "number"),
        ("macd_dea", "technical.macd_dea", "number"),
        ("macd_bar", "technical.macd_bar", "number"),
        ("rsi_6", "technical.rsi_6", "ratio"),
        ("rsi_12", "technical.rsi_12", "ratio"),
        ("rsi_24", "technical.rsi_24", "ratio"),
    )
    if isinstance(technical_context, Mapping):
        technical_mapping: Mapping[str, Any] = technical_context
    else:
        technical_mapping = {
            key: getattr(technical_context, key, None)
            for key, _path, _unit in technical_keys
        }
    _from_mapping(
        technical_mapping,
        keys=technical_keys,
        prefix="technical",
    )
    for level_name in ("support_levels", "resistance_levels"):
        levels = (
            technical_context.get(level_name)
            if isinstance(technical_context, Mapping)
            else getattr(technical_context, level_name, None)
        )
        if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)):
            continue
        for index, value in enumerate(list(levels)[:10]):
            _append_fact(
                facts,
                fact_id=f"technical-{level_name}-{index}",
                field_path=f"technical.{level_name}.{index}",
                value=value,
                unit="price",
                as_of=stamp,
                source_id=src,
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
    for match in _NUMBER_RE.finditer((text or "")[:_MAX_SCAN_CHARS]):
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
        if len(found) >= _MAX_NUMBERS_PER_STATEMENT:
            break
    return found


def _statement_has_marker(statement: str, marker: str) -> bool:
    if not marker:
        return False
    if marker == "%" or any(ord(char) > 127 for char in marker):
        return marker in statement
    return re.search(rf"(?<![a-z0-9_]){re.escape(marker)}(?![a-z0-9_])", statement) is not None


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

    if unit_hint == "percent":
        percentish = [
            c
            for c in candidates
            if str(c.get("unit") or "") in {"percent", "pct", "ratio"}
            or "pct" in str(c.get("field_path") or "")
        ]
        if not percentish:
            return None
        candidates = percentish
    for markers, field_path, _unit in _KNOWN_FIELD_HINTS:
        if any(
            _statement_has_marker(statement_l, token)
            for token in markers.split("|")
        ):
            path_hits = [
                c
                for c in candidates
                if str(c.get("field_path") or "") == field_path
                or field_path.split(".")[-1] in str(c.get("field_path") or "")
            ]
            if path_hits:
                return path_hits[0]
            return None
    if len(candidates) == 1:
        return candidates[0]
    # Equal values in different fields are ambiguous without a field marker.
    # Binding to the first candidate would turn insertion order into evidence.
    return None


def _find_dashboard_fact(
    facts: Sequence[Mapping[str, Any]],
    *,
    value: float,
    accepted_paths: Sequence[str],
) -> Optional[Mapping[str, Any]]:
    for fact in facts:
        fact_value = _finite_float(fact.get("value"))
        if fact_value is None or not math.isclose(
            fact_value,
            value,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            continue
        field_path = _bounded_text(fact.get("field_path"))
        if any(
            field_path == accepted
            or (accepted.endswith(".") and field_path.startswith(accepted))
            for accepted in accepted_paths
        ):
            return fact
    return None


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
    for index, raw in enumerate(structured[:_MAX_STRUCTURED_CLAIMS]):
        if not isinstance(raw, Mapping):
            continue
        claim_id = _bounded_text(
            raw.get("claim_id"), default=f"structured-{index}"
        )
        claim = {
            "claim_id": claim_id,
            "source_fact_id": _bounded_text(
                raw.get("source_fact_id"), default="__missing__"
            ),
            "field_path": _bounded_text(raw.get("field_path"), default="unknown"),
            "value": raw.get("value"),
            "unit": _bounded_text(raw.get("unit"), default="unknown", limit=32),
            "as_of": _bounded_text(raw.get("as_of"), default=stamp, limit=64),
            "source_id": _bounded_text(raw.get("source_id"), default="output"),
        }
        number = _finite_float(claim["value"])
        if number is None:
            continue
        claim["value"] = number
        claims.append(claim)
        statements[claim_id] = _bounded_text(
            raw.get("statement"),
            default=f"{claim['field_path']}={number}",
            limit=_MAX_SCAN_CHARS,
        )

    dashboard = getattr(result, "dashboard", None)
    if isinstance(dashboard, Mapping):
        for output_path, accepted_paths, unit in _DASHBOARD_NUMERIC_CLAIMS:
            number = _finite_float(_dig(dashboard, output_path))
            if number is None:
                continue
            claim_id = f"dashboard:{output_path}"
            matched = _find_dashboard_fact(
                facts,
                value=number,
                accepted_paths=accepted_paths,
            )
            if matched is None:
                claim = {
                    "claim_id": claim_id,
                    "source_fact_id": "__missing__",
                    "field_path": f"dashboard.{output_path}",
                    "value": number,
                    "unit": unit,
                    "as_of": stamp,
                    "source_id": "dashboard",
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
            statements[claim_id] = f"dashboard.{output_path}={number}"

    strata = resolve_report_strata(result, ensure=False)
    if strata is not None:
        for index, fact_line in enumerate(
            list(strata.verified_facts or [])[:_MAX_VERIFIED_FACTS]
        ):
            if len(claims) >= _MAX_STRUCTURED_CLAIMS + (
                _MAX_VERIFIED_FACTS * _MAX_NUMBERS_PER_STATEMENT
            ):
                break
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
                statements[claim_id] = statement

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
    blocks = analysis_context_pack_overview.get("blocks")
    if isinstance(blocks, list):
        for block in blocks[:32]:
            if not isinstance(block, Mapping):
                continue
            if _bounded_text(block.get("key"), limit=32).lower() != "quote":
                continue
            status = _bounded_text(block.get("status"), limit=32).lower()
            if status in {"missing", "fetch_failed", "not_supported"}:
                return True
            break
    quality = analysis_context_pack_overview.get("data_quality")
    if isinstance(quality, Mapping):
        level = str(quality.get("level") or "").strip().lower()
        if level in {"poor", "missing"}:
            # Only when quote price evidence is also absent.
            return not _has_price_evidence(facts)
    return False


def _normalize_gate_dimensions(dimensions: Sequence[str]) -> Tuple[str, ...]:
    if isinstance(dimensions, (str, bytes)):
        raise ValueError("quality gate dimensions must be a sequence of names")
    normalized = tuple(dict.fromkeys(str(item).strip() for item in dimensions))
    unknown = [item for item in normalized if item not in DEFAULT_GATE_DIMENSIONS]
    if unknown:
        raise ValueError(f"unsupported quality gate dimensions: {unknown}")
    if "factuality" not in normalized:
        raise ValueError("quality gate dimensions must include factuality")
    return normalized


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
    dimensions = _normalize_gate_dimensions(dimensions)
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
    matched_statements: set[str] = set()
    for item in strata_model.verified_facts or []:
        statement = str(getattr(item, "statement", "") or "").strip()
        if statement in ungrounded_set:
            matched_statements.add(statement)
            demoted.append(
                statement if statement.startswith(prefix) else f"{prefix}{statement}"
            )
        else:
            kept_facts.append(item)
    for statement in ungrounded_set - matched_statements:
        demoted.append(
            statement if statement.startswith(prefix) else f"{prefix}{statement}"
        )
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
    return (
        "demote_verified_facts_to_inference"
        if matched_statements
        else "annotate_ungrounded_claims_as_inference"
    )


def _quarantine_failed_structured_claims(
    result: Any,
    *,
    failed_claim_ids: Sequence[str],
) -> bool:
    """Remove failed structured claims from conclusion-facing claim arrays."""
    failed = {item for item in failed_claim_ids if item}
    if not failed:
        return False
    changed = False

    def _filtered(raw_claims: Any) -> Any:
        nonlocal changed
        if not isinstance(raw_claims, list):
            return raw_claims
        kept = []
        for item in raw_claims:
            claim_id = (
                _bounded_text(item.get("claim_id"))
                if isinstance(item, Mapping)
                else ""
            )
            if claim_id and claim_id in failed:
                changed = True
                continue
            kept.append(item)
        return kept

    direct_claims = getattr(result, "claims", None)
    if isinstance(direct_claims, list):
        result.claims = _filtered(direct_claims)
    dashboard = getattr(result, "dashboard", None)
    if isinstance(dashboard, dict):
        dashboard = dict(dashboard)
        for key in ("claims", "quality_claims", "eval_claims"):
            if isinstance(dashboard.get(key), list):
                dashboard[key] = _filtered(dashboard[key])
        for claim_id in failed:
            prefix = "dashboard:"
            if claim_id.startswith(prefix):
                changed = _clear_nested_dashboard_value(
                    dashboard,
                    claim_id[len(prefix) :],
                ) or changed
        result.dashboard = dashboard
    return changed


def _clear_nested_dashboard_value(dashboard: Dict[str, Any], path: str) -> bool:
    """Copy and clear one known numeric dashboard claim path."""
    parts = path.split(".")
    if not parts or any(not part for part in parts):
        return False
    current: Dict[str, Any] = dashboard
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            return False
        copied = dict(child)
        current[part] = copied
        current = copied
    leaf = parts[-1]
    if leaf not in current or current[leaf] is None:
        return False
    current[leaf] = None
    return True


def _quarantine_all_structured_claims(result: Any) -> bool:
    """Remove every structured claim when the gate cannot validate them."""
    changed = False
    direct_claims = getattr(result, "claims", None)
    if isinstance(direct_claims, list) and direct_claims:
        result.claims = []
        changed = True
    dashboard = getattr(result, "dashboard", None)
    if isinstance(dashboard, dict):
        dashboard = dict(dashboard)
        for key in ("claims", "quality_claims", "eval_claims"):
            if isinstance(dashboard.get(key), list) and dashboard[key]:
                dashboard[key] = []
                changed = True
        for output_path, _accepted_paths, _unit in _DASHBOARD_NUMERIC_CLAIMS:
            changed = (
                _clear_nested_dashboard_value(dashboard, output_path) or changed
            )
        result.dashboard = dashboard
    return changed


def _demote_all_verified_facts(result: Any, *, language: Optional[str]) -> str:
    """Fail closed by removing every claimed verified fact after a gate error."""
    strata_model = resolve_report_strata(result, language=language, ensure=True)
    if strata_model is None:
        strata_model = ensure_report_strata(None, language=language)
    statements = [
        str(getattr(item, "statement", "") or "").strip()
        for item in strata_model.verified_facts or []
    ]
    statements = [statement for statement in statements if statement]
    if not statements:
        return "gate_error_no_verified_facts"
    action = _demote_ungrounded_strata(
        result,
        ungrounded_statements=statements,
        language=language,
    )
    if action == "none":
        raise RuntimeError("quality gate could not demote verified facts after error")
    return "gate_error_demote_all_verified_facts"


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
    technical_context: Any = None,
    dimensions: Sequence[str] = DEFAULT_GATE_DIMENSIONS,
) -> AnalysisQualityGateResult:
    """Evaluate and apply the pipeline quality gate.

    Gate-internal failures demote every verified fact before returning an
    annotate trace. If that enforcement itself cannot be applied, the error is
    allowed to propagate so an unchecked result cannot be published.
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

    if getattr(result, "success", True) is not True:
        gate = _build_result(
            verdict=QualityGateVerdict.SKIPPED,
            failure_policy=failure_policy,
            enabled=enabled,
            passed=False,
            rule_score=None,
            dimensions=dimensions,
            checks=(),
            ungrounded_claim_ids=(),
            ungrounded_statements=(),
            fact_count=0,
            claim_count=0,
            action_taken="skipped_failed_analysis",
            detail="analysis result already failed",
        )
        _attach_gate_to_result(result, gate)
        return gate

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

    gate_dimensions = DEFAULT_GATE_DIMENSIONS
    try:
        gate_dimensions = _normalize_gate_dimensions(dimensions)
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
            technical_context=technical_context,
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
            dimensions=gate_dimensions,
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
                invalid_factuality = any(
                    check.status == "invalid" for check in factuality_failures
                )
                quarantined = (
                    _quarantine_all_structured_claims(result)
                    if invalid_factuality
                    else _quarantine_failed_structured_claims(
                        result,
                        failed_claim_ids=failed_ids,
                    )
                )
                if quarantined:
                    action_taken = (
                        f"{action_taken}_and_quarantine_"
                        f"{'all_' if invalid_factuality else ''}structured_claims"
                        if action_taken != "none"
                        else (
                            "quarantine_all_structured_claims"
                            if invalid_factuality
                            else "quarantine_structured_claims"
                        )
                    )
                if action_taken == "none":
                    action_taken = "annotate_trace_only"
                detail = (
                    f"quality gate annotate: {ungrounded_count} "
                    f"factuality failure(s) "
                    f"[{', '.join(reason_codes) or 'ungrounded_claim'}]"
                )
                if action_taken != "annotate_trace_only":
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
            dimensions=gate_dimensions,
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
        action = _demote_all_verified_facts(
            result,
            language=getattr(result, "report_language", None),
        )
        if _quarantine_all_structured_claims(result):
            action = f"{action}_and_quarantine_all_structured_claims"
        gate = _build_result(
            verdict=QualityGateVerdict.GATE_ERROR,
            failure_policy=QualityGateFailurePolicy.ANNOTATE,
            enabled=True,
            passed=False,
            rule_score=0.0,
            dimensions=gate_dimensions,
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
        _attach_gate_to_result(result, gate)
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
