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
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.services.agent_trajectory_eval_service import evaluate_agent_trajectory

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
                "prose_outcome_not_hit",
                observed_outcome != "hit",
                "unstructured prose must not score as hit",
            )
        )

    scorer_report = _optional_claim_scorer(claims, actuals)
    if scorer_report is not None and claims:
        scored_outcome = str(
            (scorer_report.get("aggregate") or {}).get("outcome")
            or (scorer_report.get("aggregate") or {}).get("label")
            or ""
        ).strip().lower()
        if expected.get("scorer_outcome"):
            checks.append(
                _check(
                    "claim_scoring",
                    "scorer_matches_expected",
                    scored_outcome == str(expected.get("scorer_outcome")).strip().lower(),
                    f"scorer={scored_outcome!r} expected={expected.get('scorer_outcome')!r}",
                )
            )
        if provider_failed or missing_prices:
            checks.append(
                _check(
                    "claim_scoring",
                    "scorer_never_hits_without_actuals",
                    scored_outcome != "hit",
                    f"scorer={scored_outcome!r}",
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
    if not math.isfinite(regression_threshold) or regression_threshold < 0:
        raise ValueError("regression_threshold must be finite and non-negative")
    cur_agg = current.get("aggregate") or {}
    base_agg = baseline.get("aggregate") or {}
    cur_score = float(cur_agg.get("score") or 0.0)
    base_score = float(base_agg.get("score") or 0.0)
    delta = cur_score - base_score
    base_cases = {
        str(item.get("case_id")): item
        for item in (baseline.get("cases") or [])
        if isinstance(item, Mapping)
    }
    case_deltas: List[Dict[str, Any]] = []
    for item in current.get("cases") or []:
        if not isinstance(item, Mapping):
            continue
        cid = str(item.get("case_id"))
        prior = base_cases.get(cid) or {}
        cur_s = float(item.get("score") or 0.0)
        base_s = float(prior.get("score") or 0.0)
        case_deltas.append(
            {
                "case_id": cid,
                "score": cur_s,
                "baseline_score": base_s,
                "delta": cur_s - base_s,
                "dropped": cur_s + 1e-12 < base_s - float(regression_threshold),
            }
        )
    drops = [row for row in case_deltas if row["dropped"]]
    return {
        "baseline_score": base_score,
        "current_score": cur_score,
        "delta": delta,
        "regression_threshold": float(regression_threshold),
        "dropped": delta + 1e-12 < -float(regression_threshold),
        "drop_count": len(drops),
        "drops": drops,
        "case_deltas": case_deltas,
        "regressed": (delta + 1e-12 < -float(regression_threshold)) or bool(drops),
    }


def write_prediction_baseline(
    report: Mapping[str, Any],
    path: Optional[Path] = None,
) -> Path:
    target = Path(path) if path is not None else default_baseline_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = score_only_prediction_view(report)
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


def _optional_claim_scorer(
    claims: Sequence[Any],
    actuals: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    try:
        from src.services.claim_scorer import ClaimScorer  # type: ignore
    except Exception:  # broad-exception: optional_metadata - ClaimScorer lands via A5; offline eval stays pure
        return None
    try:
        report = ClaimScorer().score(claims, actuals)
    except Exception:  # broad-exception: cleanup - optional scorer must not fail offline prediction gate
        return None
    if hasattr(report, "to_dict"):
        return report.to_dict()
    if isinstance(report, Mapping):
        return dict(report)
    return None


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
