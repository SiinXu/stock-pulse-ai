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

Default-off: when ``AGENT_EVAL_ENABLED`` is false, evaluation short-circuits
with ``enabled=False`` and no scores (zero impact on production pipelines).

Issues: #252 (metrics/benchmark), #141 (failure mining), #215 (harness
slice only — no automatic prompt rewrite).
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.config_parts.parsers import parse_env_bool


logger = logging.getLogger(__name__)

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "message": self.message,
            "rule_score": self.rule_score,
            "llm_score": self.llm_score,
            "cases": [c.to_dict() for c in self.cases],
            "failure_clusters": [f.to_dict() for f in self.failure_clusters],
            "failure_list": list(self.failure_list),
        }


# ---------------------------------------------------------------------------
# Enable switch
# ---------------------------------------------------------------------------


def is_agent_eval_enabled(config: Any = None) -> bool:
    """Return whether agent output evaluation is enabled (default off).

    Resolution order:
    1. ``config.agent_eval_enabled`` when a config object is provided
    2. Environment variable ``AGENT_EVAL_ENABLED``
    3. Default ``False``
    """
    if config is not None and hasattr(config, "agent_eval_enabled"):
        return bool(getattr(config, "agent_eval_enabled", False))
    return parse_env_bool(os.getenv("AGENT_EVAL_ENABLED"), False)


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

    ordered_ids: Optional[List[str]] = None
    manifest_path = root / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(manifest, Mapping):
            raw_ids = manifest.get("case_ids") or manifest.get("cases")
            if isinstance(raw_ids, list):
                ordered_ids = [str(x) for x in raw_ids]

    by_id: Dict[str, Dict[str, Any]] = {}
    for path in sorted(cases_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"Eval case must be an object: {path}")
        case_id = str(payload.get("id") or path.stem).strip()
        if not case_id:
            raise ValueError(f"Eval case missing id: {path}")
        case = dict(payload)
        case["id"] = case_id
        by_id[case_id] = case

    if ordered_ids is None:
        return [by_id[k] for k in sorted(by_id)]

    ordered: List[Dict[str, Any]] = []
    for case_id in ordered_ids:
        if case_id not in by_id:
            raise FileNotFoundError(
                f"Manifest case_id {case_id!r} not found under {cases_dir}"
            )
        ordered.append(by_id[case_id])
    # Include any on-disk cases not listed in the manifest (stable order).
    for case_id in sorted(by_id):
        if case_id not in ordered_ids:
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
) -> EvalCheckResult:
    return EvalCheckResult(
        dimension=dimension,
        check_id=check_id,
        passed=bool(passed) or skipped,
        detail=detail,
        judge=judge,
        skipped=skipped,
    )


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


# ---------------------------------------------------------------------------
# Dimension scorers (deterministic rules)
# ---------------------------------------------------------------------------


def score_factuality(
    context: Mapping[str, Any],
    output: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> List[EvalCheckResult]:
    """Numeric claims in the output must appear in the input context."""
    dimension = "factuality"
    checks: List[EvalCheckResult] = []
    context_nums = _context_number_set(context)
    claim_paths = rubric.get("claim_paths")
    if isinstance(claim_paths, Sequence) and claim_paths:
        claim_text_parts: List[str] = []
        for path in claim_paths:
            claim_text_parts.append(_as_str(_dig(output, str(path))))
        claim_text = "\n".join(claim_text_parts)
    else:
        claim_text = _collect_text(output)

    claimed = _extract_numbers(claim_text)
    # Optional allowlist of numbers that need not be grounded (e.g. step counts).
    ignore = {
        _normalize_number_token(str(x))
        for x in (rubric.get("ignore_numbers") or [])
        if x is not None
    }
    claimed = [n for n in claimed if n not in ignore]

    if not claimed:
        # If rubric requires claims, empty is a failure; otherwise pass.
        require_claims = bool(rubric.get("require_numeric_claims", False))
        checks.append(
            _check(
                dimension,
                "numeric_claims_present",
                not require_claims,
                "no numeric claims extracted from output"
                if require_claims
                else "no numeric claims to ground (vacuous pass)",
            )
        )
        return checks

    missing = [n for n in claimed if n not in context_nums]
    checks.append(
        _check(
            dimension,
            "numbers_grounded_in_context",
            len(missing) == 0,
            (
                f"all {len(claimed)} claim number(s) grounded in context"
                if not missing
                else f"ungrounded numbers: {missing[:12]}"
            ),
        )
    )

    # Explicit expected numbers from rubric (positive control).
    expected = rubric.get("expected_numbers")
    if isinstance(expected, Sequence) and expected:
        expected_norm = [_normalize_number_token(str(x)) for x in expected]
        output_nums = set(claimed)
        missing_expected = [n for n in expected_norm if n not in output_nums]
        checks.append(
            _check(
                dimension,
                "expected_numbers_present",
                len(missing_expected) == 0,
                (
                    "all expected numbers present in output"
                    if not missing_expected
                    else f"missing expected numbers: {missing_expected}"
                ),
            )
        )
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
    names: List[str] = []
    if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes)):
        for entry in tool_calls:
            if isinstance(entry, Mapping):
                name = entry.get("tool") or entry.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
            elif isinstance(entry, str) and entry.strip():
                names.append(entry.strip())
    name_set = set(names)

    required = [str(x) for x in (rubric.get("required_tools") or []) if x]
    forbidden = [str(x) for x in (rubric.get("forbidden_tools") or []) if x]

    if required:
        missing = [t for t in required if t not in name_set]
        checks.append(
            _check(
                dimension,
                "required_tools_called",
                len(missing) == 0,
                (
                    f"required tools present: {required}"
                    if not missing
                    else f"missing required tools: {missing}; observed={names}"
                ),
            )
        )
    if forbidden:
        hit = [t for t in forbidden if t in name_set]
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
                True,
                "no tool constraints in rubric (vacuous pass)",
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
                True,
                "no evidence polarities and no expected_signal (vacuous pass)",
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
                True,
                "no format constraints in rubric (vacuous pass)",
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
    if isinstance(raw, Mapping):
        passed = bool(raw.get("passed", raw.get("pass", False)))
        detail = _as_str(raw.get("detail") or raw.get("reason") or "llm judgement")
        score = raw.get("score")
        if score is not None and "detail" not in raw:
            detail = f"score={score}; {detail}"
    elif isinstance(raw, bool):
        passed = raw
        detail = "llm judgement bool"
    else:
        passed = False
        detail = f"unusable llm judgement payload type={type(raw).__name__}"
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
        """Score one case. When disabled (and not ``force``), returns empty scores."""
        case_id = str(case.get("id") or case.get("case_id") or "unknown")
        if not force and not self.is_enabled():
            return CaseEvalResult(
                case_id=case_id,
                dimensions=[],
                metadata={"enabled": False, "message": "AGENT_EVAL_ENABLED is off"},
            )

        context = case.get("context") if isinstance(case.get("context"), Mapping) else {}
        output = (
            agent_output
            if isinstance(agent_output, Mapping)
            else case.get("agent_output")
        )
        if not isinstance(output, Mapping):
            output = {}

        evaluation = case.get("evaluation") if isinstance(case.get("evaluation"), Mapping) else {}
        dimensions = case.get("dimensions")
        if not isinstance(dimensions, Sequence) or not dimensions:
            dimensions = list(RULE_DIMENSIONS)
        else:
            dimensions = [str(d) for d in dimensions]

        checks: List[EvalCheckResult] = []
        for dim in dimensions:
            rubric = evaluation.get(dim) if isinstance(evaluation.get(dim), Mapping) else {}
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
                "enabled": True,
                "title": case.get("title"),
                "tags": case.get("tags") or [],
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
        if not force and not self.is_enabled():
            return EvalSuiteReport(
                enabled=False,
                message="AGENT_EVAL_ENABLED is off; suite not executed",
            )

        loaded = list(cases) if cases is not None else load_eval_cases(self.fixture_root)
        results: List[CaseEvalResult] = []
        judgements = llm_judgements_by_case or {}
        for case in loaded:
            case_id = str(case.get("id") or case.get("case_id") or "")
            results.append(
                self.evaluate_case(
                    case,
                    llm_judgements=judgements.get(case_id),
                    force=True,
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

        return EvalSuiteReport(
            enabled=True,
            cases=results,
            rule_score=rule_score,
            llm_score=llm_score,
            failure_clusters=clusters,
            failure_list=failure_list,
            message="ok",
        )

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
                if len(cluster.sample_details) < max_samples:
                    cluster.sample_details.append(failure.detail)
        clusters = sorted(
            bucket.values(),
            key=lambda c: (-c.count, c.dimension, c.failure_mode),
        )
        return clusters

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
        return rows


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
