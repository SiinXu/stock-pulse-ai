# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Financial agent **output quality** evaluation and failure mining.

Complements the V0 offline **runtime** benchmark under
``tests/agent/benchmark`` (structural run discipline over frozen agent
transcripts). This service scores a single agent **output artifact**
against a frozen case (input context + expected properties):

* factuality — numeric claims grounded in the input context
* tool_usage — required / forbidden tools (output-side tool-call record)
* conclusion_consistency — evidence polarity vs final signal
* boundary_honesty — no overconfident advice under missing/failed data
* language_format — schema fields and language/format constraints

Judge policy
------------
Deterministic **rule** checks produce the primary scores. Dimensions that
require an LLM judge are tagged ``judge="llm"`` and scored in a **separate**
bucket that is never mixed into the rule total. Offline CI never calls a
live LLM; LLM dimensions are reported as ``skipped`` unless an explicit
``llm_judgements`` map is supplied by the caller.

The evaluator has no production runtime hook. Callers opt in by invoking the
offline benchmark explicitly; an environment variable cannot activate it.

Issues: #252 (metrics/benchmark), #141 (failure mining), #215 (harness
slice only — no automatic prompt rewrite).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from pydantic import ValidationError

from src.schemas.agent_output_eval import (
    AgentEvalCase,
    BoundaryHonestyRubric,
    ConclusionConsistencyRubric,
    EvidencePolarity,
    FactualityRubric,
    FinancialClaim,
    FinancialFact,
    LanguageFormatRubric,
    LLMJudgement,
    LLMRubric,
    ComparisonPolicy,
    ToolCallOutcome,
    ToolUsageRubric,
)

logger = logging.getLogger(__name__)

EVAL_SCHEMA_VERSION = "agent-output-eval-v1"
EVALUATOR_VERSION = "agent-output-evaluator-v2"
MANIFEST_VERSION = "agent_eval/1.0"
MAX_CASES = 64
MAX_CASE_FILE_BYTES = 262_144
MAX_REPORT_CHARS = 500_000
MAX_FAILURES = 512
MAX_DETAIL_CHARS = 500
MAX_JSON_DEPTH = 12
MAX_JSON_NODES = 10_000
MAX_STRING_CHARS = 20_000

# ---------------------------------------------------------------------------
# Dimension catalog (keep in sync with docs/agent-eval-dimensions*.md)
# ---------------------------------------------------------------------------

RULE_DIMENSIONS: Tuple[str, ...] = (
    "factuality",
    "tool_usage",
    "conclusion_consistency",
    "boundary_honesty",
    "language_format",
)

# Reserved for optional external LLM judges. Never mixed into rule scores.
LLM_DIMENSIONS: Tuple[str, ...] = (
    "explanation_clarity",
    "risk_framing_quality",
)

ALL_DIMENSIONS: Tuple[str, ...] = RULE_DIMENSIONS + LLM_DIMENSIONS

JUDGE_RULE = "rule"
JUDGE_LLM = "llm"

DEFAULT_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "agent_eval"
)

# Numbers that look like financial figures (prices, %, large integers).
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_/])"  # avoid matching inside tickers/ids
    r"([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?)"
    r"(?![A-Za-z0-9_])"
)

_BEARISH_TOKENS = frozenset(
    {
        "bearish",
        "sell",
        "short",
        "看空",
        "卖出",
        "减持",
        "下跌",
        "negative",
        "weak",
        "利空",
    }
)
_BULLISH_TOKENS = frozenset(
    {
        "bullish",
        "buy",
        "long",
        "看多",
        "买入",
        "加仓",
        "上涨",
        "positive",
        "strong",
        "利好",
    }
)
_BUY_SIGNALS = frozenset({"buy", "long", "买入", "加仓", "overweight"})
_SELL_SIGNALS = frozenset({"sell", "short", "卖出", "减持", "underweight"})
_HIGH_CONFIDENCE = frozenset(
    {"高", "很高", "high", "very high", "very_high", "strong"}
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalCheckResult:
    """One deterministic or LLM-tagged check outcome."""

    dimension: str
    check_id: str
    passed: bool
    detail: str
    judge: str = JUDGE_RULE
    skipped: bool = False
    status: str = "pass"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CaseEvalResult:
    """Per-case scores and check inventory."""

    case_id: str
    dimensions: List[str]
    checks: List[EvalCheckResult] = field(default_factory=list)
    rule_score: Optional[float] = None
    llm_score: Optional[float] = None
    dimension_rule_scores: Dict[str, Optional[float]] = field(default_factory=dict)
    dimension_llm_scores: Dict[str, Optional[float]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def failures(self) -> List[EvalCheckResult]:
        return [c for c in self.checks if (not c.passed) and (not c.skipped)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "dimensions": list(self.dimensions),
            "rule_score": self.rule_score,
            "llm_score": self.llm_score,
            "dimension_rule_scores": dict(self.dimension_rule_scores),
            "dimension_llm_scores": dict(self.dimension_llm_scores),
            "checks": [c.to_dict() for c in self.checks],
            "failures": [c.to_dict() for c in self.failures],
            "metadata": dict(self.metadata),
        }


@dataclass
class FailureCluster:
    """Failures grouped by dimension + failure mode (check_id)."""

    dimension: str
    failure_mode: str
    case_ids: List[str]
    count: int
    sample_details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvalSuiteReport:
    """Suite-level report with separated rule/LLM scores and failure mining."""

    enabled: bool
    cases: List[CaseEvalResult] = field(default_factory=list)
    rule_score: Optional[float] = None
    llm_score: Optional[float] = None
    failure_clusters: List[FailureCluster] = field(default_factory=list)
    failure_list: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""
    schema_version: str = EVAL_SCHEMA_VERSION
    evaluator_version: str = EVALUATOR_VERSION
    suite_hash: str = ""
    case_count: int = 0
    invalid_case_count: int = 0
    truncated: bool = False
    dropped_failure_count: int = 0
    comparison: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "schema_version": self.schema_version,
            "evaluator_version": self.evaluator_version,
            "suite_hash": self.suite_hash,
            "case_count": self.case_count,
            "invalid_case_count": self.invalid_case_count,
            "truncated": self.truncated,
            "dropped_failure_count": self.dropped_failure_count,
            "message": self.message,
            "rule_score": self.rule_score,
            "llm_score": self.llm_score,
            "cases": [c.to_dict() for c in self.cases],
            "failure_clusters": [f.to_dict() for f in self.failure_clusters],
            "failure_list": list(self.failure_list),
            "comparison": self.comparison,
        }


# ---------------------------------------------------------------------------
# Explicit invocation boundary
# ---------------------------------------------------------------------------


def is_agent_eval_enabled(config: Any = None) -> bool:
    """Compatibility helper: only an exact typed opt-in is accepted.

    The owned offline benchmark invokes the service directly. No environment
    setting is advertised because there is no production runtime consumer.
    """
    return (
        config is not None
        and getattr(config, "agent_eval_enabled", None) is True
    )


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def default_fixture_root() -> Path:
    return DEFAULT_FIXTURE_ROOT


def load_eval_cases(
    fixture_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Load offline eval cases from ``tests/fixtures/agent_eval``.

    Layout::

        manifest.json          # optional ordered id list
        cases/<id>.json        # one case per file
    """
    root = Path(fixture_root) if fixture_root is not None else default_fixture_root()
    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        return []

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Eval manifest missing: {manifest_path}")
    if manifest_path.stat().st_size > MAX_CASE_FILE_BYTES:
        raise ValueError("Eval manifest exceeds size limit")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping):
        raise ValueError("Eval manifest must be an object")
    if manifest.get("version") != MANIFEST_VERSION:
        raise ValueError(f"Unsupported eval manifest version: {manifest.get('version')!r}")
    raw_ids = manifest.get("case_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("Eval manifest must declare a non-empty case_ids list")
    ordered_ids = [str(value).strip() for value in raw_ids]
    if any(not value for value in ordered_ids):
        raise ValueError("Eval manifest contains a blank case id")
    if len(ordered_ids) != len(set(ordered_ids)):
        raise ValueError("Eval manifest contains duplicate case ids")
    if len(ordered_ids) > MAX_CASES:
        raise ValueError("Eval manifest exceeds the case-count limit")

    by_id: Dict[str, Dict[str, Any]] = {}
    for path in sorted(cases_dir.glob("*.json")):
        if path.stat().st_size > MAX_CASE_FILE_BYTES:
            raise ValueError(f"Eval case exceeds size limit: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"Eval case must be an object: {path}")
        case_id = str(payload.get("id") or path.stem).strip()
        if not case_id:
            raise ValueError(f"Eval case missing id: {path}")
        if case_id in by_id:
            raise ValueError(f"Duplicate eval case id {case_id!r}: {path}")
        case = dict(payload)
        case["id"] = case_id
        serialized = json.dumps(case, allow_nan=False, ensure_ascii=False, sort_keys=True)
        if len(serialized) > MAX_CASE_FILE_BYTES:
            raise ValueError(f"Eval case canonical payload exceeds size limit: {path}")
        case["_artifact_hash"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        by_id[case_id] = case

    unlisted = sorted(set(by_id) - set(ordered_ids))
    if unlisted:
        raise ValueError(f"Eval cases are not listed in manifest: {unlisted}")

    ordered: List[Dict[str, Any]] = []
    for case_id in ordered_ids:
        if case_id not in by_id:
            raise FileNotFoundError(
                f"Manifest case_id {case_id!r} not found under {cases_dir}"
            )
        ordered.append(by_id[case_id])
    return ordered


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check(
    dimension: str,
    check_id: str,
    passed: bool,
    detail: str,
    *,
    judge: str = JUDGE_RULE,
    skipped: bool = False,
    invalid: bool = False,
) -> EvalCheckResult:
    status = "invalid" if invalid else "skipped" if skipped else "pass" if passed else "fail"
    return EvalCheckResult(
        dimension=dimension,
        check_id=check_id,
        passed=bool(passed) or skipped,
        detail=_as_str(detail)[:MAX_DETAIL_CHARS],
        judge=judge,
        skipped=skipped,
        status=status,
    )


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _validate_json_bounds(payload: Any) -> None:
    nodes = 0

    def _walk(node: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ValueError(f"JSON payload exceeds {MAX_JSON_NODES} nodes")
        if depth > MAX_JSON_DEPTH:
            raise ValueError(f"JSON payload exceeds nesting depth {MAX_JSON_DEPTH}")
        if isinstance(node, str) and len(node) > MAX_STRING_CHARS:
            raise ValueError(f"JSON string exceeds {MAX_STRING_CHARS} characters")
        if isinstance(node, Mapping):
            for key, value in node.items():
                if not isinstance(key, str):
                    raise ValueError("JSON object keys must be strings")
                _walk(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                _walk(value, depth + 1)

    _walk(payload, 0)


def _validated_rubric(dimension: str, payload: Any) -> Dict[str, Any]:
    models = {
        "factuality": FactualityRubric,
        "tool_usage": ToolUsageRubric,
        "conclusion_consistency": ConclusionConsistencyRubric,
        "boundary_honesty": BoundaryHonestyRubric,
        "language_format": LanguageFormatRubric,
        "explanation_clarity": LLMRubric,
        "risk_framing_quality": LLMRubric,
    }
    return models[dimension].model_validate(payload).model_dump()


def _collect_text(payload: Any) -> str:
    chunks: List[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            chunks.append(node)
            return
        # Include numeric scalars so prices / PE / etc. in structured
        # context are available for factuality grounding.
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            chunks.append(str(node))
            return
        if isinstance(node, Mapping):
            for value in node.values():
                _walk(value)
            return
        if isinstance(node, Sequence) and not isinstance(node, (bytes, bytearray)):
            for item in node:
                _walk(item)

    _walk(payload)
    return "\n".join(chunks)


def _normalize_number_token(token: str) -> str:
    text = token.strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    try:
        value = float(text)
    except ValueError:
        return token.strip()
    # Canonical form so 1800.0 matches 1800
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _extract_numbers(text: str) -> List[str]:
    found: List[str] = []
    for match in _NUMBER_RE.finditer(text or ""):
        raw = match.group(1)
        # Skip year-like and pure tiny ints that are often list indexes / counts
        # when the case does not care — still keep % and decimals.
        norm = _normalize_number_token(raw)
        if not norm:
            continue
        found.append(norm)
    return found


def _context_number_set(context: Mapping[str, Any]) -> set:
    return set(_extract_numbers(_collect_text(context)))


def _normalize_signal(value: Any) -> str:
    return _as_str(value).lower()


def _polarity_of_token(token: str) -> Optional[str]:
    lowered = token.strip().lower()
    if not lowered:
        return None
    if lowered in _BEARISH_TOKENS or any(t in lowered for t in _BEARISH_TOKENS):
        return "bearish"
    if lowered in _BULLISH_TOKENS or any(t in lowered for t in _BULLISH_TOKENS):
        return "bullish"
    return None


def _evidence_polarities(evidence: Any) -> List[str]:
    polarities: List[str] = []
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        return polarities
    for item in evidence:
        if isinstance(item, Mapping):
            for key in ("polarity", "sentiment", "direction", "stance", "label"):
                if key in item:
                    pol = _polarity_of_token(_as_str(item.get(key)))
                    if pol:
                        polarities.append(pol)
                        break
            else:
                pol = _polarity_of_token(_collect_text(item))
                if pol:
                    polarities.append(pol)
        else:
            pol = _polarity_of_token(_as_str(item))
            if pol:
                polarities.append(pol)
    return polarities


def _ratio(passed: int, total: int) -> Optional[float]:
    if total <= 0:
        return None
    return round(passed / total, 4)


def _score_bucket(
    checks: Sequence[EvalCheckResult],
    *,
    judge: str,
) -> Tuple[Optional[float], Dict[str, Optional[float]]]:
    by_dim: Dict[str, List[EvalCheckResult]] = defaultdict(list)
    for check in checks:
        if check.judge != judge:
            continue
        if check.skipped:
            continue
        by_dim[check.dimension].append(check)

    dim_scores: Dict[str, Optional[float]] = {}
    total_pass = 0
    total = 0
    for dim, items in by_dim.items():
        p = sum(1 for c in items if c.passed)
        t = len(items)
        dim_scores[dim] = _ratio(p, t)
        total_pass += p
        total += t
    return _ratio(total_pass, total), dim_scores


def _suite_dimension_scores(
    report: EvalSuiteReport,
    judge: str,
) -> Dict[str, float]:
    buckets: Dict[str, List[EvalCheckResult]] = defaultdict(list)
    for result in report.cases:
        for check in result.checks:
            if check.judge == judge and not check.skipped:
                buckets[check.dimension].append(check)
    return {
        dimension: float(_ratio(sum(check.passed for check in checks), len(checks)) or 0.0)
        for dimension, checks in buckets.items()
    }


def _suite_dimension_counts(
    report: EvalSuiteReport,
    judge: str,
) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for result in report.cases:
        for check in result.checks:
            if check.judge == judge and not check.skipped:
                counts[check.dimension] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# Dimension scorers (deterministic rules)
# ---------------------------------------------------------------------------


def score_factuality(
    context: Mapping[str, Any],
    output: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> List[EvalCheckResult]:
    """Bind every numeric claim to one exact, typed source fact."""
    dimension = "factuality"
    checks: List[EvalCheckResult] = []
    raw_facts = context.get("facts")
    raw_claims = output.get("claims")
    if not isinstance(raw_facts, list) or not raw_facts:
        return [_check(dimension, "structured_facts_valid", False,
                       "context.facts must be a non-empty list", invalid=True)]
    if not isinstance(raw_claims, list) or not raw_claims:
        return [_check(dimension, "structured_claims_valid", False,
                       "agent_output.claims must be a non-empty list", invalid=True)]

    facts: Dict[str, Mapping[str, Any]] = {}
    for index, fact in enumerate(raw_facts):
        try:
            validated = FinancialFact.model_validate(fact).model_dump()
            fact_id = validated["fact_id"]
            if fact_id in facts:
                raise ValueError("duplicate fact id")
        except (ValidationError, ValueError):
            checks.append(_check(dimension, "structured_facts_valid", False,
                                 f"invalid or duplicate fact at index {index}", invalid=True))
        else:
            facts[fact_id] = validated

    observed_claim_ids: set[str] = set()
    for index, claim in enumerate(raw_claims):
        try:
            validated_claim = FinancialClaim.model_validate(claim).model_dump()
            claim_id = validated_claim["claim_id"]
            if claim_id in observed_claim_ids:
                raise ValueError("duplicate claim id")
        except (ValidationError, ValueError):
            checks.append(_check(dimension, "structured_claims_valid", False,
                                 f"invalid or duplicate claim at index {index}", invalid=True))
            continue
        observed_claim_ids.add(claim_id)
        source_fact_id = validated_claim["source_fact_id"]
        fact = facts.get(source_fact_id)
        binding_ok = fact is not None and all(
            validated_claim.get(key) == fact.get(key)
            for key in ("field_path", "value", "unit", "as_of", "source_id")
        )
        checks.append(_check(
            dimension,
            "claim_bound_to_source_fact",
            binding_ok,
            f"claim {claim_id!r} bound to fact {source_fact_id!r}"
            if binding_ok else f"claim {claim_id!r} does not exactly match fact {source_fact_id!r}",
        ))

    required_claim_ids = rubric.get("required_claim_ids", [])
    if not isinstance(required_claim_ids, list) or any(
        not isinstance(item, str) or not item.strip() for item in required_claim_ids
    ):
        checks.append(_check(dimension, "factuality_rubric_valid", False,
                             "required_claim_ids must be a list of non-blank strings", invalid=True))
    elif required_claim_ids:
        missing = sorted(set(required_claim_ids) - observed_claim_ids)
        checks.append(_check(dimension, "required_claims_present", not missing,
                             "all required claims present" if not missing else f"missing claims: {missing}"))
    return checks


def score_tool_usage(
    context: Mapping[str, Any],
    output: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> List[EvalCheckResult]:
    """Required / forbidden tools from the output-side tool-call record."""
    dimension = "tool_usage"
    checks: List[EvalCheckResult] = []
    tool_calls = output.get("tool_calls")
    if tool_calls is None:
        tool_calls = context.get("tool_calls")
    calls: List[Mapping[str, Any]] = []
    invalid_calls = 0
    if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes)):
        for entry in tool_calls:
            try:
                calls.append(ToolCallOutcome.model_validate(entry).model_dump())
            except ValidationError:
                invalid_calls += 1
    elif tool_calls is not None:
        invalid_calls += 1

    if invalid_calls:
        checks.append(_check(
            dimension, "tool_call_records_valid", False,
            f"invalid tool call records: {invalid_calls}", invalid=True,
        ))

    names = [_as_str(entry.get("tool") or entry.get("name")) for entry in calls]
    successful_names = {
        name for name, entry in zip(names, calls)
        if all(entry.get(key) is True for key in (
            "attempted", "completed", "succeeded", "valid_result", "authorized"
        ))
    }
    attempted_names = {
        name for name, entry in zip(names, calls) if entry.get("attempted") is True
    }

    raw_required = rubric.get("required_tools", [])
    raw_forbidden = rubric.get("forbidden_tools", [])
    if any(
        not isinstance(values, list)
        or any(not isinstance(item, str) or not item.strip() for item in values)
        for values in (raw_required, raw_forbidden)
    ):
        return [_check(
            dimension, "tool_rubric_valid", False,
            "required_tools and forbidden_tools must be lists of non-blank strings",
            invalid=True,
        )]
    required = list(raw_required)
    forbidden = list(raw_forbidden)

    if required:
        missing = [t for t in required if t not in successful_names]
        checks.append(
            _check(
                dimension,
                "required_tools_called",
                len(missing) == 0,
                (
                    f"required tools completed with valid authorized results: {required}"
                    if not missing
                    else f"missing required tools: {missing}; observed={names}"
                ),
            )
        )
    if forbidden:
        hit = [t for t in forbidden if t in attempted_names]
        checks.append(
            _check(
                dimension,
                "forbidden_tools_absent",
                len(hit) == 0,
                (
                    "no forbidden tools called"
                    if not hit
                    else f"forbidden tools called: {hit}"
                ),
            )
        )
    if not required and not forbidden:
        checks.append(
            _check(
                dimension,
                "tool_rubric_defined",
                False,
                "tool rubric must define required_tools or forbidden_tools",
                invalid=True,
            )
        )
    return checks


def score_conclusion_consistency(
    context: Mapping[str, Any],
    output: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> List[EvalCheckResult]:
    """Evidence polarity must not contradict the final signal."""
    dimension = "conclusion_consistency"
    checks: List[EvalCheckResult] = []

    signal = _normalize_signal(
        output.get("signal")
        or output.get("decision")
        or _dig(output, "dashboard.phase_decision.decision_type")
        or _dig(output, "dashboard.decision_type")
    )
    evidence = output.get("evidence")
    if evidence is None:
        evidence = context.get("evidence")
    if evidence is not None:
        if not isinstance(evidence, list):
            return [_check(dimension, "evidence_schema_valid", False,
                           "evidence must be a list", invalid=True)]
        normalized_evidence: List[Dict[str, Any]] = []
        try:
            for item in evidence:
                normalized_evidence.append(EvidencePolarity.model_validate(item).model_dump())
        except ValidationError:
            return [_check(dimension, "evidence_schema_valid", False,
                           "evidence entries require exactly one bounded polarity label",
                           invalid=True)]
        evidence = normalized_evidence
    polarities = _evidence_polarities(evidence)

    if rubric.get("expected_signal"):
        expected = _normalize_signal(rubric.get("expected_signal"))
        checks.append(
            _check(
                dimension,
                "signal_matches_expected",
                signal == expected,
                f"signal observed={signal!r} expected={expected!r}",
            )
        )

    if polarities:
        unique = set(polarities)
        all_bearish = unique == {"bearish"}
        all_bullish = unique == {"bullish"}
        if all_bearish:
            contradict = signal in _BUY_SIGNALS
            checks.append(
                _check(
                    dimension,
                    "no_buy_against_all_bearish_evidence",
                    not contradict,
                    (
                        f"all evidence bearish; signal={signal!r} "
                        f"{'CONTRADICTS' if contradict else 'ok'}"
                    ),
                )
            )
        if all_bullish:
            contradict = signal in _SELL_SIGNALS
            checks.append(
                _check(
                    dimension,
                    "no_sell_against_all_bullish_evidence",
                    not contradict,
                    (
                        f"all evidence bullish; signal={signal!r} "
                        f"{'CONTRADICTS' if contradict else 'ok'}"
                    ),
                )
            )
        if not all_bearish and not all_bullish:
            checks.append(
                _check(
                    dimension,
                    "mixed_evidence_recorded",
                    True,
                    f"mixed evidence polarities={sorted(unique)}; signal={signal!r}",
                )
            )
    elif not rubric.get("expected_signal"):
        checks.append(
            _check(
                dimension,
                "evidence_available",
                False,
                "rubric must define expected_signal or provide structured evidence",
                invalid=True,
            )
        )
    return checks


def score_boundary_honesty(
    context: Mapping[str, Any],
    output: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> List[EvalCheckResult]:
    """When data is missing or tools failed, forbid overconfident advice."""
    dimension = "boundary_honesty"
    checks: List[EvalCheckResult] = []

    data_missing = bool(
        context.get("data_missing")
        or context.get("tools_failed")
        or rubric.get("data_missing")
        or rubric.get("tools_failed")
    )
    failed_tools = context.get("failed_tools") or rubric.get("failed_tools") or []
    if isinstance(failed_tools, Sequence) and len(failed_tools) > 0:
        data_missing = True

    confidence = _normalize_signal(
        output.get("confidence")
        or output.get("confidence_level")
        or _dig(output, "dashboard.phase_decision.confidence_level")
        or _dig(output, "dashboard.confidence_level")
    )
    signal = _normalize_signal(
        output.get("signal")
        or output.get("decision")
        or _dig(output, "dashboard.phase_decision.decision_type")
    )
    limitations_text = _collect_text(
        output.get("data_limitations")
        or output.get("limitations")
        or _dig(output, "dashboard.phase_decision.data_limitations")
        or ""
    )
    risk_text = _as_str(
        output.get("risk_warning")
        or _dig(output, "dashboard.phase_decision.risk_warning")
        or _dig(output, "dashboard.risk_warning")
    )

    if data_missing:
        high = confidence in _HIGH_CONFIDENCE
        checks.append(
            _check(
                dimension,
                "no_high_confidence_when_data_missing",
                not high,
                (
                    f"data/tools incomplete; confidence={confidence!r} "
                    f"{'OVERCONFIDENT' if high else 'ok'}"
                ),
            )
        )
        if bool(rubric.get("forbid_directional_when_missing", False)):
            directional = signal in (_BUY_SIGNALS | _SELL_SIGNALS)
            checks.append(
                _check(
                    dimension,
                    "no_directional_signal_when_data_missing",
                    not directional,
                    (
                        f"data incomplete; signal={signal!r} "
                        f"{'too assertive' if directional else 'ok'}"
                    ),
                )
            )
        if bool(rubric.get("require_limitation_mention", True)):
            nontrivial = bool(limitations_text.strip()) and limitations_text.strip().lower() not in {
                "无",
                "none",
                "n/a",
                "na",
                "-",
                "—",
            }
            checks.append(
                _check(
                    dimension,
                    "limitations_surfaced",
                    nontrivial,
                    (
                        "non-trivial data_limitations present"
                        if nontrivial
                        else f"missing/trivial limitations: {limitations_text!r}"
                    ),
                )
            )
    else:
        checks.append(
            _check(
                dimension,
                "complete_data_path",
                True,
                "context marks data complete; no boundary constraint applied",
            )
        )

    if bool(rubric.get("require_risk_warning", False)):
        checks.append(
            _check(
                dimension,
                "risk_warning_present",
                bool(risk_text),
                (
                    "risk_warning present"
                    if risk_text
                    else "risk_warning missing"
                ),
            )
        )
    return checks


def score_language_format(
    context: Mapping[str, Any],
    output: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> List[EvalCheckResult]:
    """Schema field presence and simple language/format constraints."""
    dimension = "language_format"
    checks: List[EvalCheckResult] = []

    required_fields = [str(x) for x in (rubric.get("required_fields") or []) if x]
    for path in required_fields:
        value = _dig(output, path)
        present = value is not None and _as_str(value) != ""
        if isinstance(value, (list, dict)):
            present = len(value) > 0 or path in output
        checks.append(
            _check(
                dimension,
                f"field_present:{path}",
                present,
                f"field {path!r} {'present' if present else 'missing'}",
            )
        )

    required_substrings = [
        str(x) for x in (rubric.get("required_substrings") or []) if x
    ]
    if required_substrings:
        blob = _collect_text(output)
        missing = [s for s in required_substrings if s not in blob]
        checks.append(
            _check(
                dimension,
                "required_substrings",
                len(missing) == 0,
                (
                    "all required substrings present"
                    if not missing
                    else f"missing substrings: {missing}"
                ),
            )
        )

    forbidden_substrings = [
        str(x) for x in (rubric.get("forbidden_substrings") or []) if x
    ]
    if forbidden_substrings:
        blob = _collect_text(output)
        hit = [s for s in forbidden_substrings if s in blob]
        checks.append(
            _check(
                dimension,
                "forbidden_substrings_absent",
                len(hit) == 0,
                (
                    "no forbidden substrings"
                    if not hit
                    else f"forbidden substrings present: {hit}"
                ),
            )
        )

    if rubric.get("expect_json_object"):
        checks.append(
            _check(
                dimension,
                "output_is_mapping",
                isinstance(output, Mapping),
                f"output type={type(output).__name__}",
            )
        )

    if not checks:
        checks.append(
            _check(
                dimension,
                "format_rubric_defined",
                False,
                "format rubric must define at least one constraint",
                invalid=True,
            )
        )
    return checks


def score_llm_dimension(
    dimension: str,
    llm_judgements: Optional[Mapping[str, Any]],
) -> List[EvalCheckResult]:
    """Apply optional external LLM judgements; never invent scores offline."""
    if not llm_judgements or dimension not in llm_judgements:
        return [
            _check(
                dimension,
                "llm_judge_unavailable",
                True,
                "LLM judge not supplied; dimension skipped (not mixed into rule score)",
                judge=JUDGE_LLM,
                skipped=True,
            )
        ]
    raw = llm_judgements[dimension]
    try:
        judgement = LLMJudgement.model_validate(raw)
    except ValidationError:
        return [_check(
            dimension,
            "llm_judge_payload_valid",
            False,
            "LLM judgement requires exact boolean passed, finite score in [0,1], and provenance",
            judge=JUDGE_LLM,
            invalid=True,
        )]
    passed = judgement.passed
    detail = (
        f"score={judgement.score}; judge_id={judgement.judge_id}; model={judgement.model}; "
        f"rubric={judgement.rubric_version}; as_of={judgement.as_of}; {judgement.detail}"
    )
    return [
        _check(
            dimension,
            "llm_judge",
            passed,
            detail,
            judge=JUDGE_LLM,
            skipped=False,
        )
    ]


def _dig(payload: Any, dotted_path: str) -> Any:
    current = payload
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AgentEvalService:
    """Evaluate agent outputs on financial quality dimensions + mine failures."""

    def __init__(
        self,
        *,
        fixture_root: Optional[Path] = None,
        config: Any = None,
    ) -> None:
        self.fixture_root = (
            Path(fixture_root) if fixture_root is not None else default_fixture_root()
        )
        self.config = config

    def is_enabled(self) -> bool:
        return is_agent_eval_enabled(self.config)

    def evaluate_case(
        self,
        case: Mapping[str, Any],
        *,
        agent_output: Optional[Mapping[str, Any]] = None,
        llm_judgements: Optional[Mapping[str, Any]] = None,
        force: bool = False,
    ) -> CaseEvalResult:
        """Score one explicitly supplied case; ``force`` is compatibility-only."""
        del force
        case_id = _as_str(case.get("id") or case.get("case_id"))
        schema_errors: List[str] = []
        canonical_case = dict(case)
        canonical_case.pop("_artifact_hash", None)
        if agent_output is not None:
            canonical_case["agent_output"] = agent_output
        try:
            _validate_json_bounds(canonical_case)
            canonical = json.dumps(canonical_case, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            schema_errors.append(f"case is not strict-JSON serializable: {exc}")
            canonical = ""
        if len(canonical) > MAX_CASE_FILE_BYTES:
            schema_errors.append("case exceeds canonical payload limit")

        dimensions: List[str] = []
        context: Mapping[str, Any] = {}
        output: Mapping[str, Any] = {}
        evaluation: Dict[str, Dict[str, Any]] = {}
        try:
            validated_case = AgentEvalCase.model_validate(canonical_case)
            case_id = validated_case.id
            dimensions = list(validated_case.dimensions)
            context = validated_case.context
            output = validated_case.agent_output
            evaluation = {
                dimension: _validated_rubric(
                    dimension, validated_case.evaluation[dimension]
                )
                for dimension in dimensions
            }
        except (ValidationError, ValueError, KeyError) as exc:
            schema_errors.append(f"strict case/rubric validation failed: {exc}")
            case_id = case_id or "invalid-case"

        artifact_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        rubric_payload = case.get("evaluation")
        try:
            rubric_canonical = json.dumps(
                rubric_payload, ensure_ascii=False, sort_keys=True, allow_nan=False
            )
        except (TypeError, ValueError):
            rubric_canonical = ""
        metadata = {
            "enabled": True,
            "title": case.get("title"),
            "tags": case.get("tags") or [],
            "artifact_hash": artifact_hash,
            "evaluator_version": EVALUATOR_VERSION,
            "rubric_hash": hashlib.sha256(rubric_canonical.encode("utf-8")).hexdigest(),
            "agent_version": case.get("agent_version"),
            "config_version": case.get("config_version"),
        }
        if schema_errors:
            invalid_check = _check(
                "case_schema", "case_schema_valid", False, "; ".join(schema_errors), invalid=True
            )
            return CaseEvalResult(
                case_id=case_id,
                dimensions=list(dimensions),
                checks=[invalid_check],
                rule_score=0.0,
                dimension_rule_scores={"case_schema": 0.0},
                metadata={**metadata, "invalid": True},
            )

        assert isinstance(context, Mapping)
        assert isinstance(output, Mapping)
        assert isinstance(evaluation, Mapping)

        checks: List[EvalCheckResult] = []
        for dim in dimensions:
            rubric = evaluation[dim]
            if dim == "factuality":
                checks.extend(score_factuality(context, output, rubric))
            elif dim == "tool_usage":
                checks.extend(score_tool_usage(context, output, rubric))
            elif dim == "conclusion_consistency":
                checks.extend(score_conclusion_consistency(context, output, rubric))
            elif dim == "boundary_honesty":
                checks.extend(score_boundary_honesty(context, output, rubric))
            elif dim == "language_format":
                checks.extend(score_language_format(context, output, rubric))
            elif dim in LLM_DIMENSIONS:
                checks.extend(score_llm_dimension(dim, llm_judgements))
            else:
                checks.append(
                    _check(
                        dim,
                        "unknown_dimension",
                        False,
                        f"unknown dimension {dim!r}",
                    )
                )

        rule_score, dim_rule = _score_bucket(checks, judge=JUDGE_RULE)
        llm_score, dim_llm = _score_bucket(checks, judge=JUDGE_LLM)

        return CaseEvalResult(
            case_id=case_id,
            dimensions=list(dimensions),
            checks=checks,
            rule_score=rule_score,
            llm_score=llm_score,
            dimension_rule_scores=dim_rule,
            dimension_llm_scores=dim_llm,
            metadata={
                **metadata,
                "invalid": any(check.status == "invalid" for check in checks),
            },
        )

    def evaluate_suite(
        self,
        cases: Optional[Sequence[Mapping[str, Any]]] = None,
        *,
        llm_judgements_by_case: Optional[Mapping[str, Mapping[str, Any]]] = None,
        force: bool = False,
    ) -> EvalSuiteReport:
        """Evaluate a suite of cases and attach failure-mining clusters."""
        del force
        loaded = list(cases) if cases is not None else load_eval_cases(self.fixture_root)
        if not loaded:
            raise ValueError("agent evaluation suite must contain at least one case")
        if len(loaded) > MAX_CASES:
            raise ValueError(f"agent evaluation suite exceeds {MAX_CASES} cases")
        case_ids = [_as_str(case.get("id") or case.get("case_id")) for case in loaded]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("agent evaluation suite contains duplicate case ids")
        results: List[CaseEvalResult] = []
        judgements = llm_judgements_by_case or {}
        for case in loaded:
            case_id = str(case.get("id") or case.get("case_id") or "")
            results.append(
                self.evaluate_case(
                    case,
                    llm_judgements=judgements.get(case_id),
                )
            )

        all_rule_checks = [
            c for r in results for c in r.checks if c.judge == JUDGE_RULE and not c.skipped
        ]
        all_llm_checks = [
            c for r in results for c in r.checks if c.judge == JUDGE_LLM and not c.skipped
        ]
        rule_score = _ratio(
            sum(1 for c in all_rule_checks if c.passed),
            len(all_rule_checks),
        )
        llm_score = _ratio(
            sum(1 for c in all_llm_checks if c.passed),
            len(all_llm_checks),
        )

        clusters = self.mine_failures(results)
        failure_list = self.build_failure_list(results)
        suite_hash = hashlib.sha256("\n".join(
            _as_str(result.metadata.get("artifact_hash")) for result in results
        ).encode("utf-8")).hexdigest()
        dropped = max(0, sum(len(result.failures) for result in results) - len(failure_list))
        report = EvalSuiteReport(
            enabled=True,
            cases=results,
            rule_score=rule_score,
            llm_score=llm_score,
            failure_clusters=clusters,
            failure_list=failure_list,
            message="ok",
            suite_hash=suite_hash,
            case_count=len(results),
            invalid_case_count=sum(bool(result.metadata.get("invalid")) for result in results),
            dropped_failure_count=dropped,
            truncated=dropped > 0,
        )
        serialized = json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True, allow_nan=False)
        if len(serialized) > MAX_REPORT_CHARS:
            report.failure_list = []
            report.failure_clusters = []
            report.truncated = True
            report.dropped_failure_count = sum(len(result.failures) for result in results)
            serialized = json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True, allow_nan=False)
            if len(serialized) > MAX_REPORT_CHARS:
                raise ValueError("agent evaluation report exceeds bounded output limit")
        return report

    def mine_failures(
        self,
        results: Sequence[CaseEvalResult],
        *,
        max_samples: int = 5,
    ) -> List[FailureCluster]:
        """Cluster failed checks by (dimension, check_id) with case pointers."""
        bucket: Dict[Tuple[str, str], FailureCluster] = {}
        for result in results:
            for failure in result.failures:
                key = (failure.dimension, failure.check_id)
                cluster = bucket.get(key)
                if cluster is None:
                    cluster = FailureCluster(
                        dimension=failure.dimension,
                        failure_mode=failure.check_id,
                        case_ids=[],
                        count=0,
                        sample_details=[],
                    )
                    bucket[key] = cluster
                if result.case_id not in cluster.case_ids:
                    cluster.case_ids.append(result.case_id)
                cluster.count += 1
                if len(cluster.sample_details) < min(max_samples, 5):
                    cluster.sample_details.append(failure.detail)
        clusters = sorted(
            bucket.values(),
            key=lambda c: (-c.count, c.dimension, c.failure_mode),
        )
        return clusters[:MAX_FAILURES]

    def build_failure_list(
        self,
        results: Sequence[CaseEvalResult],
    ) -> List[Dict[str, Any]]:
        """Readable failure inventory pointing at concrete case ids."""
        rows: List[Dict[str, Any]] = []
        for result in results:
            for failure in result.failures:
                rows.append(
                    {
                        "case_id": result.case_id,
                        "dimension": failure.dimension,
                        "failure_mode": failure.check_id,
                        "judge": failure.judge,
                        "detail": failure.detail,
                    }
                )
        rows.sort(key=lambda r: (r["dimension"], r["failure_mode"], r["case_id"]))
        return rows[:MAX_FAILURES]

    @staticmethod
    def compare_reports(
        baseline: EvalSuiteReport,
        candidate: EvalSuiteReport,
        *,
        baseline_agent_version: str,
        candidate_agent_version: str,
        baseline_config_version: str,
        candidate_config_version: str,
        regression_threshold: float = 0.0,
    ) -> Dict[str, Any]:
        """Compare exact output-quality suites without mixing judge buckets."""
        if not math.isfinite(regression_threshold) or regression_threshold < 0:
            raise ValueError("regression_threshold must be finite and non-negative")
        if baseline.rule_score is None or candidate.rule_score is None:
            raise ValueError("baseline and candidate must both have a rule score")
        baseline_ids = {result.case_id for result in baseline.cases}
        candidate_ids = {result.case_id for result in candidate.cases}
        if baseline_ids != candidate_ids:
            raise ValueError("baseline and candidate case ids must match exactly")
        baseline_dims = _suite_dimension_scores(baseline, JUDGE_RULE)
        candidate_dims = _suite_dimension_scores(candidate, JUDGE_RULE)
        dimension_deltas = {
            dim: round(candidate_dims.get(dim, 0.0) - baseline_dims.get(dim, 0.0), 4)
            for dim in sorted(set(baseline_dims) | set(candidate_dims))
        }
        rule_delta = round(candidate.rule_score - baseline.rule_score, 4)
        llm_delta = None
        if baseline.llm_score is not None and candidate.llm_score is not None:
            llm_delta = round(candidate.llm_score - baseline.llm_score, 4)
        regressed = rule_delta < -regression_threshold or any(
            delta < -regression_threshold for delta in dimension_deltas.values()
        )
        policy = ComparisonPolicy(regression_threshold=regression_threshold)
        baseline_counts = _suite_dimension_counts(baseline, JUDGE_RULE)
        candidate_counts = _suite_dimension_counts(candidate, JUDGE_RULE)
        return {
            "schema_version": EVAL_SCHEMA_VERSION,
            "baseline_suite_hash": baseline.suite_hash,
            "candidate_suite_hash": candidate.suite_hash,
            "baseline_case_count": baseline.case_count,
            "candidate_case_count": candidate.case_count,
            "baseline_agent_version": baseline_agent_version,
            "candidate_agent_version": candidate_agent_version,
            "baseline_config_version": baseline_config_version,
            "candidate_config_version": candidate_config_version,
            "rule_delta": rule_delta,
            "llm_delta": llm_delta,
            "dimension_rule_deltas": dimension_deltas,
            "baseline_dimension_rule_samples": baseline_counts,
            "candidate_dimension_rule_samples": candidate_counts,
            "baseline_rule_check_count": sum(baseline_counts.values()),
            "candidate_rule_check_count": sum(candidate_counts.values()),
            "regression_threshold": regression_threshold,
            "comparison_policy": policy.model_dump(),
            "confidence": {
                "method": "deterministic_frozen_panel_no_interval",
                "interval": None,
                "reason": "The complete frozen panel is compared; no population inference is claimed.",
            },
            "regressed": regressed,
        }


def format_failure_report(report: EvalSuiteReport) -> str:
    """Render a human-readable failure mining summary (Markdown)."""
    lines: List[str] = []
    lines.append("# Agent output evaluation — failure mining")
    lines.append("")
    if not report.enabled:
        lines.append(f"_Disabled_: {report.message}")
        return "\n".join(lines) + "\n"

    lines.append(
        f"- Rule score: **{report.rule_score if report.rule_score is not None else 'n/a'}**"
    )
    lines.append(
        f"- LLM score (separate): **{report.llm_score if report.llm_score is not None else 'n/a / skipped'}**"
    )
    lines.append(f"- Cases: {len(report.cases)}")
    lines.append(f"- Failure clusters: {len(report.failure_clusters)}")
    lines.append("")
    if not report.failure_clusters:
        lines.append("No failures.")
        return "\n".join(lines) + "\n"

    lines.append("## Clusters")
    lines.append("")
    for cluster in report.failure_clusters:
        lines.append(
            f"### `{cluster.dimension}` / `{cluster.failure_mode}` "
            f"(count={cluster.count})"
        )
        lines.append(f"- Cases: {', '.join(f'`{c}`' for c in cluster.case_ids)}")
        for detail in cluster.sample_details:
            lines.append(f"- sample: {detail}")
        lines.append("")
    lines.append("## Failure list")
    lines.append("")
    for row in report.failure_list:
        lines.append(
            f"- `{row['case_id']}` · {row['dimension']}/{row['failure_mode']}: "
            f"{row['detail']}"
        )
    lines.append("")
    return "\n".join(lines)
