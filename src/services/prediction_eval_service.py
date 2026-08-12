# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline prediction-verification eval suite (Issue #1092 / Epic #1107).

Reuses the owned agent trajectory evaluator for compact episode trajectories
and applies deterministic resolution-integrity rules for the prediction loop:

* provider failure / missing actuals => ``data_unavailable`` (never a hit)
* non-parseable prose must not become fabricated verifiable claims
* typed lessons must use known kinds
* Soul charter text must not appear in episode payloads

Regression threshold is fixed at **0.0** (deterministic frozen fixtures). Do not
raise the threshold to keep CI green.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.services.agent_trajectory_eval_service import evaluate_agent_trajectory
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

PREDICTION_EVAL_SCHEMA_VERSION = "prediction-eval-v1"
PREDICTION_EVAL_ENGINE_VERSION = "prediction-eval-engine-v1"
MANIFEST_VERSION = "prediction_eval/1.0"

DEFAULT_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "prediction_eval"
)
DEFAULT_BASELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "agent"
    / "benchmark"
    / "baselines"
    / "prediction_v0.json"
)

# Hard requirement (#1092): threshold has a justification and is not relaxed for CI.
REGRESSION_THRESHOLD = 0.0

MAX_CASES = 64
MAX_CASE_FILE_BYTES = 262_144

TERMINAL_OUTCOMES = frozenset({"hit", "partial", "miss", "data_unavailable"})
KNOWN_LESSON_KINDS = frozenset(
    {
        "evidence_gap",
        "overclaim",
        "overconfidence",
        "tool_failure",
        "risk_omission",
        "format_violation",
        "regime_shift",
        "horizon_mismatch",
        "other",
    }
)


def default_fixture_root() -> Path:
    return DEFAULT_FIXTURE_ROOT


def default_baseline_path() -> Path:
    return DEFAULT_BASELINE_PATH


def load_prediction_eval_cases(fixture_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    root = Path(fixture_root) if fixture_root is not None else default_fixture_root()
    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        raise FileNotFoundError(f"Prediction eval cases missing: {cases_dir}")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Prediction eval manifest missing: {manifest_path}")
    if manifest_path.stat().st_size > MAX_CASE_FILE_BYTES:
        raise ValueError("Prediction eval manifest exceeds size limit")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping):
        raise ValueError("Prediction eval manifest must be an object")
    if manifest.get("version") != MANIFEST_VERSION:
        raise ValueError(
            f"Unsupported prediction eval manifest version: {manifest.get('version')!r}"
        )
    raw_ids = manifest.get("case_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("Prediction eval manifest must declare non-empty case_ids")
    ordered_ids = [str(value).strip() for value in raw_ids]
    if any(not value for value in ordered_ids):
        raise ValueError("Prediction eval manifest contains a blank case id")
    if len(ordered_ids) != len(set(ordered_ids)):
        raise ValueError("Prediction eval manifest contains duplicate case ids")
    if len(ordered_ids) > MAX_CASES:
        raise ValueError("Prediction eval manifest exceeds the case-count limit")

    by_id: Dict[str, Dict[str, Any]] = {}
    for path in sorted(cases_dir.glob("*.json")):
        if path.stat().st_size > MAX_CASE_FILE_BYTES:
            raise ValueError(f"Prediction eval case exceeds size limit: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"Prediction eval case must be an object: {path}")
        case_id = str(payload.get("id") or path.stem).strip()
        if not case_id:
            raise ValueError(f"Prediction eval case missing id: {path}")
        if case_id in by_id:
            raise ValueError(f"Duplicate prediction eval case id {case_id!r}")
        case = dict(payload)
        case["id"] = case_id
        by_id[case_id] = case

    unlisted = sorted(set(by_id) - set(ordered_ids))
    if unlisted:
        raise ValueError(f"Prediction eval cases not listed in manifest: {unlisted}")

    ordered: List[Dict[str, Any]] = []
    for case_id in ordered_ids:
        if case_id not in by_id:
            raise FileNotFoundError(
                f"Manifest case_id {case_id!r} not found under {cases_dir}"
            )
        ordered.append(by_id[case_id])
    return ordered


def load_prediction_baseline(path: Optional[Path] = None) -> Dict[str, Any]:
    target = Path(path) if path is not None else default_baseline_path()
    if not target.is_file():
        raise FileNotFoundError(f"Prediction eval baseline missing: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Prediction eval baseline must be an object")
    return dict(payload)


def evaluate_prediction_case(case: Mapping[str, Any]) -> Dict[str, Any]:
    case_id = str(case.get("id") or "").strip() or "unknown"
    checks: List[Dict[str, Any]] = []

    expected = case.get("expected") if isinstance(case.get("expected"), Mapping) else {}
    resolution = case.get("resolution") if isinstance(case.get("resolution"), Mapping) else {}
    actuals = case.get("actuals") if isinstance(case.get("actuals"), Mapping) else {}
    claims = case.get("claims") if isinstance(case.get("claims"), list) else []
    episode = case.get("episode") if isinstance(case.get("episode"), Mapping) else {}
    lessons = case.get("lessons") if isinstance(case.get("lessons"), list) else []

    observed_outcome = str(resolution.get("outcome") or "").strip().lower()
    expected_outcome = str(expected.get("outcome") or "").strip().lower()
    provider_failed = bool(actuals.get("provider_failed") or actuals.get("unavailable"))
    missing_prices = _actuals_missing_prices(actuals)

    checks.append(
        _check(
            "resolution_integrity",
            "outcome_in_terminal_set",
            observed_outcome in TERMINAL_OUTCOMES,
            f"observed={observed_outcome!r}",
        )
    )
    checks.append(
        _check(
            "resolution_integrity",
            "outcome_matches_expected",
            observed_outcome == expected_outcome and bool(expected_outcome),
            f"observed={observed_outcome!r} expected={expected_outcome!r}",
        )
    )
    if provider_failed or missing_prices:
        checks.append(
            _check(
                "resolution_integrity",
                "provider_failure_is_data_unavailable",
                observed_outcome == "data_unavailable",
                "provider failure or missing actuals must not fabricate hit/miss",
            )
        )
        checks.append(
            _check(
                "resolution_integrity",
                "never_fabricated_hit_without_actuals",
                observed_outcome != "hit",
                "hit is forbidden when actuals are unavailable",
            )
        )

    if expected.get("reject_unstructured_prose") is True:
        unstructured = case.get("unstructured_prose")
        checks.append(
            _check(
                "claim_contract",
                "prose_not_promoted_to_claim",
                not claims and unstructured is not None,
                "non-parseable prose must not become a verifiable claim list",
            )
        )
        checks.append(
            _check(
                "claim_contract",
                "prose_outcome_unavailable",
                observed_outcome == "data_unavailable",
                "unstructured prose must not enter hit/miss metrics",
            )
        )

    if claims:
        scorer_result = _optional_claim_scorer(claims, actuals)
        scorer_status = str(scorer_result.get("status") or "error")
        expected_scorer_outcome = str(
            expected.get("scorer_outcome") or expected_outcome
        ).strip().lower()
        if scorer_status == "unavailable":
            checks.append(
                _check(
                    "claim_scoring",
                    "claim_scorer_contract",
                    True,
                    "A5 ClaimScorer dependency is not present on this branch",
                )
            )
        elif scorer_status == "ok":
            scored_outcome = _claim_scorer_aggregate_label(
                scorer_result.get("report") or {}
            )
            checks.append(
                _check(
                    "claim_scoring",
                    "claim_scorer_contract",
                    scored_outcome == expected_scorer_outcome,
                    f"scorer={scored_outcome!r} expected={expected_scorer_outcome!r}",
                )
            )
        else:
            checks.append(
                _check(
                    "claim_scoring",
                    "claim_scorer_contract",
                    False,
                    str(scorer_result.get("error") or "ClaimScorer failed")[:500],
                )
            )

    trajectory = episode.get("trajectory_summary")
    if isinstance(trajectory, list) and trajectory:
        tool_calls = []
        for item in trajectory:
            if not isinstance(item, Mapping):
                continue
            call: Dict[str, Any] = {
                "step": item.get("step"),
                "tool": item.get("tool"),
                "success": item.get("success"),
                "arguments": {"fingerprint": item.get("argument_fingerprint") or "none"},
            }
            if isinstance(item.get("cached"), bool):
                call["cached"] = item["cached"]
            if isinstance(item.get("timeout"), bool):
                call["timeout"] = item["timeout"]
            if isinstance(item.get("guarded"), bool):
                call["guarded"] = item["guarded"]
            if isinstance(item.get("duration_ms"), int):
                call["duration"] = float(item["duration_ms"]) / 1000.0
            tool_calls.append(call)
        rubric = (
            case.get("trajectory_rubric")
            if isinstance(case.get("trajectory_rubric"), Mapping)
            else {}
        )
        traj = evaluate_agent_trajectory(
            [
                {
                    "run_id": str(episode.get("run_id") or case_id),
                    "execution_id": f"prediction-eval:{case_id}",
                    "task_id": case_id,
                    "agent_id": "prediction-offline",
                    "stock_code": episode.get("symbol"),
                    "market": episode.get("market"),
                    "completed": episode.get("success")
                    if isinstance(episode.get("success"), bool)
                    else None,
                    "tool_calls": tool_calls,
                }
            ],
            rubric={
                "required_tools": list(rubric.get("required_tools") or []),
                "forbidden_tools": list(rubric.get("forbidden_tools") or []),
            },
        )
        traj_dict = traj.to_dict()
        metrics = traj_dict.get("metrics") or {}
        if rubric.get("required_tools"):
            recall = metrics.get("tool_selection_recall")
            checks.append(
                _check(
                    "trajectory",
                    "required_tools_recall",
                    isinstance(recall, (int, float))
                    and math.isfinite(float(recall))
                    and float(recall) + 1e-12
                    >= float(expected.get("min_tool_recall") or 1.0),
                    f"recall={recall!r}",
                )
            )
        checks.append(
            _check(
                "trajectory",
                "trajectory_eval_bounded",
                traj_dict.get("schema_version") is not None,
                "trajectory evaluation returned a versioned result",
            )
        )
    elif expected.get("require_trajectory") is True:
        checks.append(
            _check(
                "trajectory",
                "trajectory_present",
                False,
                "episode trajectory_summary is required for this case",
            )
        )

    if lessons or expected.get("require_lessons"):
        valid_kinds = True
        for lesson in lessons:
            if not isinstance(lesson, Mapping):
                valid_kinds = False
                break
            kind = str(lesson.get("kind") or "").strip()
            if kind not in KNOWN_LESSON_KINDS:
                valid_kinds = False
                break
        checks.append(
            _check(
                "reflection",
                "lesson_kinds_typed",
                valid_kinds and (not expected.get("require_lessons") or bool(lessons)),
                f"lesson_count={len(lessons)}",
            )
        )
        if expected.get("forbid_soul_mutation_claim") is True:
            text_blob = json.dumps(lessons, ensure_ascii=False).lower()
            checks.append(
                _check(
                    "reflection",
                    "no_soul_mutation_claim",
                    "soul_charter" not in text_blob and "rewrite soul" not in text_blob,
                    "lessons must not claim Soul charter mutation",
                )
            )

    episode_blob = json.dumps(episode, ensure_ascii=False)
    checks.append(
        _check(
            "episode_hygiene",
            "no_soul_charter_text",
            "AGENT_SOUL_CHARTER" not in episode_blob and "soul_charter" not in episode_blob,
            "episode must not embed full Soul charter text",
        )
    )
    checks.append(
        _check(
            "episode_hygiene",
            "no_obvious_secrets",
            "sk-" not in episode_blob
            and "api_key" not in episode_blob.lower()
            and "authorization" not in episode_blob.lower(),
            "episode payload must not contain credential markers",
        )
    )

    passed = sum(1 for item in checks if item["passed"])
    total = len(checks)
    score = float(passed) / float(total) if total else 0.0
    return {
        "case_id": case_id,
        "passed": passed,
        "total": total,
        "score": score,
        "failed_checks": [item for item in checks if not item["passed"]],
        "checks": checks,
        "profile": case.get("profile"),
    }


def run_prediction_eval_suite(fixture_root: Optional[Path] = None) -> Dict[str, Any]:
    cases = load_prediction_eval_cases(fixture_root)
    case_scores = [evaluate_prediction_case(case) for case in cases]
    checks_passed = sum(int(item["passed"]) for item in case_scores)
    checks_total = sum(int(item["total"]) for item in case_scores)
    score = float(checks_passed) / float(checks_total) if checks_total else 0.0
    report = {
        "schema_version": PREDICTION_EVAL_SCHEMA_VERSION,
        "engine_version": PREDICTION_EVAL_ENGINE_VERSION,
        "regression_threshold": REGRESSION_THRESHOLD,
        "threshold_rationale": (
            "Deterministic frozen fixtures; any check failure is a contract "
            "regression. Threshold is fixed at 0.0 and must not be relaxed for CI."
        ),
        "aggregate": {
            "cases": len(case_scores),
            "checks_passed": checks_passed,
            "checks_total": checks_total,
            "score": score,
        },
        "cases": sorted(case_scores, key=lambda item: str(item.get("case_id") or "")),
    }
    report["suite_hash"] = hashlib.sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    return report


def score_only_prediction_view(report: Mapping[str, Any]) -> Dict[str, Any]:
    cases = []
    for item in report.get("cases") or []:
        if not isinstance(item, Mapping):
            continue
        cases.append(
            {
                "case_id": item.get("case_id"),
                "passed": item.get("passed"),
                "total": item.get("total"),
                "score": item.get("score"),
                "failed_checks": [
                    {
                        "family": fc.get("family"),
                        "id": fc.get("id"),
                        "detail": fc.get("detail"),
                    }
                    for fc in (item.get("failed_checks") or [])
                    if isinstance(fc, Mapping)
                ],
            }
        )
    return {
        "schema_version": report.get("schema_version") or PREDICTION_EVAL_SCHEMA_VERSION,
        "engine_version": report.get("engine_version") or PREDICTION_EVAL_ENGINE_VERSION,
        "regression_threshold": report.get("regression_threshold", REGRESSION_THRESHOLD),
        "aggregate": report.get("aggregate") or {},
        "cases": cases,
    }


def compare_prediction_to_baseline(
    current: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    regression_threshold: float = REGRESSION_THRESHOLD,
) -> Dict[str, Any]:
    if (
        isinstance(regression_threshold, bool)
        or not math.isfinite(float(regression_threshold))
        or float(regression_threshold) != REGRESSION_THRESHOLD
    ):
        raise ValueError("prediction regression threshold is fixed at 0.0")
    cur_view = _validate_score_view(current, name="current")
    base_view = _validate_score_view(baseline, name="baseline")
    cur_agg = cur_view["aggregate"]
    base_agg = base_view["aggregate"]
    cur_score = cur_agg["score"]
    base_score = base_agg["score"]
    delta = cur_score - base_score
    base_cases = {
        item["case_id"]: item for item in base_view["cases"]
    }
    current_cases = {
        item["case_id"]: item for item in cur_view["cases"]
    }
    missing_case_ids = sorted(set(base_cases) - set(current_cases))
    extra_case_ids = sorted(set(current_cases) - set(base_cases))
    case_deltas: List[Dict[str, Any]] = []
    changed_check_counts: List[str] = []
    for cid in sorted(set(base_cases) | set(current_cases)):
        item = current_cases.get(cid)
        prior = base_cases.get(cid)
        cur_s = item["score"] if item is not None else 0.0
        base_s = prior["score"] if prior is not None else 0.0
        if item is not None and prior is not None and item["total"] != prior["total"]:
            changed_check_counts.append(cid)
        case_deltas.append(
            {
                "case_id": cid,
                "score": cur_s,
                "baseline_score": base_s,
                "delta": cur_s - base_s,
                "dropped": prior is not None
                and (item is None or cur_s + 1e-12 < base_s),
            }
        )
    drops = [row for row in case_deltas if row["dropped"]]
    contract_drift = bool(
        missing_case_ids
        or extra_case_ids
        or changed_check_counts
        or cur_agg["checks_total"] != base_agg["checks_total"]
    )
    return {
        "baseline_score": base_score,
        "current_score": cur_score,
        "delta": delta,
        "regression_threshold": REGRESSION_THRESHOLD,
        "dropped": delta + 1e-12 < 0.0,
        "drop_count": len(drops),
        "drops": drops,
        "case_deltas": case_deltas,
        "contract_drift": contract_drift,
        "missing_case_ids": missing_case_ids,
        "extra_case_ids": extra_case_ids,
        "changed_check_counts": changed_check_counts,
        "regressed": delta + 1e-12 < 0.0 or bool(drops) or contract_drift,
    }


def write_prediction_baseline(
    report: Mapping[str, Any],
    path: Optional[Path] = None,
) -> Path:
    target = Path(path) if path is not None else default_baseline_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = score_only_prediction_view(report)
    _validate_score_view(payload, name="generated baseline")
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _check(family: str, check_id: str, passed: bool, detail: str) -> Dict[str, Any]:
    return {
        "family": family,
        "id": check_id,
        "passed": bool(passed),
        "detail": str(detail)[:500],
    }


def _actuals_missing_prices(actuals: Mapping[str, Any]) -> bool:
    if actuals.get("unavailable") or actuals.get("provider_failed"):
        return True
    start = actuals.get("start_price")
    end = actuals.get("end_price")
    if start is None or end is None:
        return True
    try:
        start_f = float(start)
        end_f = float(end)
    except (TypeError, ValueError):
        return True
    return not (math.isfinite(start_f) and math.isfinite(end_f))


def _require_int(value: Any, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _require_score(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite score")
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a finite score") from exc
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError(f"{field} must be between 0.0 and 1.0")
    return score


def _validate_score_view(view: Mapping[str, Any], *, name: str) -> Dict[str, Any]:
    if not isinstance(view, Mapping):
        raise ValueError(f"{name} prediction score view must be an object")
    if view.get("schema_version") != PREDICTION_EVAL_SCHEMA_VERSION:
        raise ValueError(f"{name} prediction score schema version is invalid")
    if view.get("engine_version") != PREDICTION_EVAL_ENGINE_VERSION:
        raise ValueError(f"{name} prediction score engine version is invalid")
    threshold = _require_score(
        view.get("regression_threshold"),
        field=f"{name}.regression_threshold",
    )
    if threshold != REGRESSION_THRESHOLD:
        raise ValueError(f"{name} prediction regression threshold must be 0.0")
    raw_cases = view.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{name} prediction score cases must be non-empty")
    cases: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, Mapping):
            raise ValueError(f"{name}.cases[{index}] must be an object")
        case_id = str(raw.get("case_id") or "").strip()
        if not case_id or case_id in seen:
            raise ValueError(f"{name} prediction case ids must be unique and non-empty")
        seen.add(case_id)
        total = _require_int(raw.get("total"), field=f"{name}.{case_id}.total", minimum=1)
        passed = _require_int(raw.get("passed"), field=f"{name}.{case_id}.passed")
        if passed > total:
            raise ValueError(f"{name}.{case_id}.passed must not exceed total")
        score = _require_score(raw.get("score"), field=f"{name}.{case_id}.score")
        expected_score = float(passed) / float(total)
        if abs(score - expected_score) > 1e-12:
            raise ValueError(f"{name}.{case_id}.score does not match passed/total")
        cases.append(
            {"case_id": case_id, "passed": passed, "total": total, "score": score}
        )
    aggregate = view.get("aggregate")
    if not isinstance(aggregate, Mapping):
        raise ValueError(f"{name}.aggregate must be an object")
    aggregate_cases = _require_int(
        aggregate.get("cases"), field=f"{name}.aggregate.cases", minimum=1
    )
    checks_passed = _require_int(
        aggregate.get("checks_passed"), field=f"{name}.aggregate.checks_passed"
    )
    checks_total = _require_int(
        aggregate.get("checks_total"),
        field=f"{name}.aggregate.checks_total",
        minimum=1,
    )
    aggregate_score = _require_score(
        aggregate.get("score"), field=f"{name}.aggregate.score"
    )
    if aggregate_cases != len(cases):
        raise ValueError(f"{name}.aggregate.cases does not match case count")
    if checks_passed != sum(item["passed"] for item in cases):
        raise ValueError(f"{name}.aggregate.checks_passed does not match cases")
    if checks_total != sum(item["total"] for item in cases):
        raise ValueError(f"{name}.aggregate.checks_total does not match cases")
    if abs(aggregate_score - checks_passed / checks_total) > 1e-12:
        raise ValueError(f"{name}.aggregate.score does not match check counts")
    return {
        "aggregate": {
            "cases": aggregate_cases,
            "checks_passed": checks_passed,
            "checks_total": checks_total,
            "score": aggregate_score,
        },
        "cases": cases,
    }


def _claim_scorer_aggregate_label(report: Mapping[str, Any]) -> Optional[str]:
    aggregate = report.get("aggregate")
    if not isinstance(aggregate, Mapping):
        return None
    try:
        scored = _require_int(
            aggregate.get("scored_claims"), field="scorer.scored_claims"
        )
        hits = _require_int(aggregate.get("hit_count"), field="scorer.hit_count")
        partials = _require_int(
            aggregate.get("partial_count"), field="scorer.partial_count"
        )
        misses = _require_int(
            aggregate.get("miss_count"), field="scorer.miss_count"
        )
        unavailable = _require_int(
            aggregate.get("data_unavailable_count"),
            field="scorer.data_unavailable_count",
        )
    except ValueError:
        return None
    if hits + partials + misses != scored:
        return None
    if scored <= 0:
        return "data_unavailable" if unavailable > 0 else None
    if hits == scored and partials == 0 and misses == 0:
        return "hit"
    if misses == scored and partials == 0 and hits == 0:
        return "miss"
    if unavailable > 0 and hits == 0 and partials == 0 and misses == 0:
        return "data_unavailable"
    return "partial"


def _optional_claim_scorer(
    claims: Sequence[Any],
    actuals: Mapping[str, Any],
) -> Dict[str, Any]:
    try:
        from src.services.claim_scorer import ClaimScorer  # type: ignore
    except ModuleNotFoundError as exc:
        if exc.name == "src.services.claim_scorer":
            return {"status": "unavailable"}
        return {
            "status": "error",
            "error": f"ClaimScorer import failed ({type(exc).__name__})",
        }
    except Exception as exc:  # broad-exception: fallback_recorded - a broken installed scorer fails the gate
        log_safe_exception(
            logger,
            "prediction_eval_claim_scorer_import_failed",
            exc,
            error_code="prediction_eval_claim_scorer_import_failed",
        )
        return {
            "status": "error",
            "error": f"ClaimScorer import failed ({type(exc).__name__})",
        }
    try:
        report = ClaimScorer().score(claims, actuals)
    except Exception as exc:  # broad-exception: fallback_recorded - installed scorer failures are regressions
        log_safe_exception(
            logger,
            "prediction_eval_claim_scorer_failed",
            exc,
            error_code="prediction_eval_claim_scorer_failed",
        )
        return {
            "status": "error",
            "error": f"ClaimScorer failed ({type(exc).__name__})",
        }
    if hasattr(report, "to_dict"):
        report = report.to_dict()
    if not isinstance(report, Mapping):
        return {"status": "error", "error": "ClaimScorer returned an invalid report"}
    return {"status": "ok", "report": dict(report)}


__all__ = [
    "DEFAULT_BASELINE_PATH",
    "DEFAULT_FIXTURE_ROOT",
    "PREDICTION_EVAL_ENGINE_VERSION",
    "PREDICTION_EVAL_SCHEMA_VERSION",
    "REGRESSION_THRESHOLD",
    "compare_prediction_to_baseline",
    "default_baseline_path",
    "default_fixture_root",
    "evaluate_prediction_case",
    "load_prediction_baseline",
    "load_prediction_eval_cases",
    "run_prediction_eval_suite",
    "score_only_prediction_view",
    "write_prediction_baseline",
]
