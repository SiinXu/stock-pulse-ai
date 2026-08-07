# -*- coding: utf-8 -*-
"""Deterministic metric checks over recorded offline agent runs (#252 V0).

Three families, each producing measurable pass/fail checks:

* financial_task_correctness — terminal success, signal, dashboard completeness
* tool_usage_discipline — required/forbidden tools, stock scope, success policy
* uncertainty_honesty — confidence level, gap language, risk surface

These checks are structural and offline. They do not claim market alpha or
subjective LLM prose quality.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from tests.agent.benchmark.loader import METRIC_FAMILIES

HIGH_CONFIDENCE_TOKENS = ("高", "很高", "high", "very high")
TRIVIAL_LIMITATION_TOKENS = {"", "无", "none", "n/a", "na", "null", "-", "—", "无。"}


def dig(payload: Any, dotted_path: str) -> Any:
    current = payload
    for part in dotted_path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


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
        if isinstance(node, Mapping):
            for value in node.values():
                _walk(value)
            return
        if isinstance(node, Sequence) and not isinstance(node, (bytes, bytearray)):
            for item in node:
                _walk(item)

    _walk(payload)
    return "\n".join(chunks)


def _tool_names(tool_calls: Sequence[Mapping[str, Any]]) -> List[str]:
    names: List[str] = []
    for entry in tool_calls:
        name = entry.get("tool") or entry.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def _check(
    family: str,
    check_id: str,
    passed: bool,
    detail: str,
) -> Dict[str, Any]:
    return {
        "family": family,
        "id": check_id,
        "passed": bool(passed),
        "detail": detail,
    }


def score_financial_task_correctness(
    observed: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    family = "financial_task_correctness"
    checks: List[Dict[str, Any]] = []
    dashboard = observed.get("dashboard")
    dashboard_map = dashboard if isinstance(dashboard, Mapping) else {}

    expect_success = bool(rubric.get("expect_success", True))
    actual_success = bool(observed.get("success"))
    checks.append(
        _check(
            family,
            "success_matches",
            actual_success is expect_success,
            f"success observed={actual_success} expected={expect_success}",
        )
    )

    expected_signal = rubric.get("expected_signal")
    if expected_signal is not None:
        actual_signal = observed.get("signal")
        if actual_signal is None and dashboard_map:
            actual_signal = dashboard_map.get("decision_type")
        checks.append(
            _check(
                family,
                "signal_matches",
                _as_str(actual_signal) == _as_str(expected_signal),
                f"signal observed={actual_signal!r} expected={expected_signal!r}",
            )
        )

    if rubric.get("require_dashboard", True):
        checks.append(
            _check(
                family,
                "dashboard_present",
                isinstance(dashboard, Mapping) and bool(dashboard),
                "dashboard must be a non-empty object",
            )
        )

    required_fields = rubric.get("required_fields") or []
    if isinstance(required_fields, Sequence):
        for field in required_fields:
            value = dashboard_map.get(field) if dashboard_map else None
            ok = value is not None and (
                not isinstance(value, str) or bool(value.strip())
            )
            checks.append(
                _check(
                    family,
                    f"field_present:{field}",
                    ok,
                    f"dashboard.{field} present_nonempty={ok}",
                )
            )

    name_needles = rubric.get("expected_stock_name_substrings") or []
    if name_needles and isinstance(name_needles, Sequence):
        stock_name = _as_str(dashboard_map.get("stock_name"))
        for needle in name_needles:
            ok = _as_str(needle) in stock_name
            checks.append(
                _check(
                    family,
                    f"stock_name_contains:{needle}",
                    ok,
                    f"stock_name={stock_name!r} contains {needle!r}",
                )
            )

    return checks


def score_tool_usage_discipline(
    observed: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    family = "tool_usage_discipline"
    checks: List[Dict[str, Any]] = []
    tool_calls = observed.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        tool_calls = []
    names = _tool_names(tool_calls)
    name_set = set(names)

    required = list(rubric.get("required_tools") or [])
    for tool in required:
        checks.append(
            _check(
                family,
                f"required_tool:{tool}",
                tool in name_set,
                f"required tool {tool!r} in {names}",
            )
        )

    forbidden = list(rubric.get("forbidden_tools") or [])
    for tool in forbidden:
        checks.append(
            _check(
                family,
                f"forbidden_tool:{tool}",
                tool not in name_set,
                f"forbidden tool {tool!r} absent from {names}",
            )
        )

    max_calls = rubric.get("max_tool_calls")
    if max_calls is not None:
        try:
            limit = int(max_calls)
        except (TypeError, ValueError):
            limit = -1
        checks.append(
            _check(
                family,
                "max_tool_calls",
                0 <= len(names) <= limit,
                f"tool_call_count={len(names)} max={limit}",
            )
        )

    expected_code = rubric.get("expected_stock_code")
    if expected_code is not None:
        code = _as_str(expected_code)
        scoped = [
            entry
            for entry in tool_calls
            if isinstance(entry, Mapping)
            and isinstance(entry.get("arguments"), Mapping)
            and "stock_code" in (entry.get("arguments") or {})
        ]
        mismatches = []
        for entry in scoped:
            args = entry.get("arguments") or {}
            actual = _as_str(args.get("stock_code"))
            if actual != code:
                mismatches.append((entry.get("tool") or entry.get("name"), actual))
        checks.append(
            _check(
                family,
                "stock_scope",
                not mismatches,
                f"stock_code expected={code!r} mismatches={mismatches!r}",
            )
        )

    require_success = list(rubric.get("require_tool_success") or [])
    allow_failed = set(rubric.get("allow_failed_tools") or [])
    by_name: Dict[str, List[Mapping[str, Any]]] = {}
    for entry in tool_calls:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("tool") or entry.get("name")
        if isinstance(name, str):
            by_name.setdefault(name, []).append(entry)

    for tool in require_success:
        rows = by_name.get(tool) or []
        ok = any(bool(row.get("success", True)) for row in rows) if rows else False
        checks.append(
            _check(
                family,
                f"tool_success:{tool}",
                ok,
                f"tool {tool!r} has at least one success={ok}",
            )
        )

    unexpected_failures = []
    for name, rows in by_name.items():
        if name in allow_failed:
            continue
        for row in rows:
            if row.get("success") is False:
                unexpected_failures.append(name)
    checks.append(
        _check(
            family,
            "no_unexpected_tool_failures",
            not unexpected_failures,
            f"unexpected_failures={unexpected_failures}",
        )
    )

    return checks


def score_uncertainty_honesty(
    observed: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    family = "uncertainty_honesty"
    checks: List[Dict[str, Any]] = []
    dashboard = observed.get("dashboard")
    dashboard_map = dashboard if isinstance(dashboard, Mapping) else {}
    content = _as_str(observed.get("content"))
    combined_text = "\n".join(
        [
            content,
            _collect_text(dashboard_map),
        ]
    )

    if rubric.get("require_risk_warning", True):
        risk = _as_str(dashboard_map.get("risk_warning"))
        checks.append(
            _check(
                family,
                "risk_warning_present",
                bool(risk),
                f"risk_warning={risk!r}",
            )
        )

    allowed = rubric.get("allowed_confidence_levels")
    confidence = _as_str(dashboard_map.get("confidence_level"))
    if allowed is not None:
        allowed_list = [_as_str(item).lower() for item in allowed]
        ok = confidence.lower() in allowed_list if confidence else False
        checks.append(
            _check(
                family,
                "confidence_level_allowed",
                ok,
                f"confidence={confidence!r} allowed={list(allowed)}",
            )
        )

    if rubric.get("forbid_high_confidence"):
        lowered = confidence.lower()
        is_high = any(token.lower() in lowered for token in HIGH_CONFIDENCE_TOKENS)
        checks.append(
            _check(
                family,
                "forbid_high_confidence",
                not is_high,
                f"confidence={confidence!r} high={is_high}",
            )
        )

    for needle in rubric.get("required_substrings") or []:
        text = _as_str(needle)
        if not text:
            continue
        checks.append(
            _check(
                family,
                f"required_substring:{text}",
                text in combined_text,
                f"substring {text!r} present in agent text surface",
            )
        )

    if rubric.get("require_nontrivial_data_limitations"):
        limitations = dig(dashboard_map, "dashboard.phase_decision.data_limitations")
        text = _as_str(limitations)
        ok = text.lower() not in TRIVIAL_LIMITATION_TOKENS and bool(text)
        checks.append(
            _check(
                family,
                "nontrivial_data_limitations",
                ok,
                f"data_limitations={text!r}",
            )
        )

    return checks


def score_observation(
    observed: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    *,
    scenario_id: str,
) -> Dict[str, Any]:
    """Score one observed run against the scenario evaluation rubric."""
    family_results: Dict[str, Dict[str, Any]] = {}
    all_checks: List[Dict[str, Any]] = []

    scorers = {
        "financial_task_correctness": score_financial_task_correctness,
        "tool_usage_discipline": score_tool_usage_discipline,
        "uncertainty_honesty": score_uncertainty_honesty,
    }

    for family in METRIC_FAMILIES:
        rubric = evaluation.get(family) or {}
        if not isinstance(rubric, Mapping):
            rubric = {}
        checks = scorers[family](observed, rubric)
        passed = sum(1 for item in checks if item["passed"])
        total = len(checks)
        family_results[family] = {
            "passed": passed,
            "total": total,
            "score": (passed / total) if total else 1.0,
            "checks": checks,
        }
        all_checks.extend(checks)

    total_passed = sum(1 for item in all_checks if item["passed"])
    total_checks = len(all_checks)
    return {
        "scenario_id": scenario_id,
        "passed": total_passed,
        "total": total_checks,
        "score": (total_passed / total_checks) if total_checks else 1.0,
        "families": family_results,
        "failed_checks": [
            {
                "family": item["family"],
                "id": item["id"],
                "detail": item["detail"],
            }
            for item in all_checks
            if not item["passed"]
        ],
    }


def aggregate_scenario_scores(scenario_scores: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-scenario scores into a stable report summary."""
    family_passed = {family: 0 for family in METRIC_FAMILIES}
    family_total = {family: 0 for family in METRIC_FAMILIES}
    total_passed = 0
    total_checks = 0
    scenarios_out: List[Dict[str, Any]] = []

    for item in scenario_scores:
        total_passed += int(item.get("passed") or 0)
        total_checks += int(item.get("total") or 0)
        families = item.get("families") or {}
        for family in METRIC_FAMILIES:
            block = families.get(family) or {}
            family_passed[family] += int(block.get("passed") or 0)
            family_total[family] += int(block.get("total") or 0)
        scenarios_out.append(
            {
                "scenario_id": item.get("scenario_id"),
                "passed": item.get("passed"),
                "total": item.get("total"),
                "score": item.get("score"),
                "failed_checks": item.get("failed_checks") or [],
                "families": {
                    family: {
                        "passed": (families.get(family) or {}).get("passed"),
                        "total": (families.get(family) or {}).get("total"),
                        "score": (families.get(family) or {}).get("score"),
                    }
                    for family in METRIC_FAMILIES
                },
            }
        )

    by_family = {
        family: {
            "passed": family_passed[family],
            "total": family_total[family],
            "score": (
                family_passed[family] / family_total[family]
                if family_total[family]
                else 1.0
            ),
        }
        for family in METRIC_FAMILIES
    }

    return {
        "schema_version": "agent-eval-benchmark-v0",
        "aggregate": {
            "scenarios": len(scenarios_out),
            "checks_passed": total_passed,
            "checks_total": total_checks,
            "score": (total_passed / total_checks) if total_checks else 1.0,
            "by_family": by_family,
        },
        "scenarios": scenarios_out,
    }


def compare_to_baseline(
    current: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compute score deltas; V0 reports drops but does not hard-fail CI."""
    cur_agg = current.get("aggregate") or {}
    base_agg = baseline.get("aggregate") or {}
    cur_score = float(cur_agg.get("score") or 0.0)
    base_score = float(base_agg.get("score") or 0.0)
    delta = cur_score - base_score

    base_scenarios = {
        str(item.get("scenario_id")): item
        for item in (baseline.get("scenarios") or [])
        if isinstance(item, Mapping)
    }
    scenario_deltas: List[Dict[str, Any]] = []
    for item in current.get("scenarios") or []:
        if not isinstance(item, Mapping):
            continue
        sid = str(item.get("scenario_id"))
        prior = base_scenarios.get(sid) or {}
        cur_s = float(item.get("score") or 0.0)
        base_s = float(prior.get("score") or 0.0)
        scenario_deltas.append(
            {
                "scenario_id": sid,
                "score": cur_s,
                "baseline_score": base_s,
                "delta": cur_s - base_s,
                "dropped": cur_s + 1e-12 < base_s,
            }
        )

    drops = [row for row in scenario_deltas if row["dropped"]]
    return {
        "baseline_score": base_score,
        "current_score": cur_score,
        "delta": delta,
        "dropped": delta + 1e-12 < 0.0,
        "scenario_deltas": scenario_deltas,
        "drop_count": len(drops),
        "drops": drops,
    }


def render_markdown_report(
    report: Mapping[str, Any],
    comparison: Optional[Mapping[str, Any]] = None,
) -> str:
    """Render a stable markdown report (no wall-clock timestamps)."""
    agg = report.get("aggregate") or {}
    lines: List[str] = [
        "# Offline Financial Agent Evaluation Benchmark (V0)",
        "",
        f"- Schema: `{report.get('schema_version')}`",
        f"- Scenarios: **{agg.get('scenarios')}**",
        f"- Checks: **{agg.get('checks_passed')}/{agg.get('checks_total')}**",
        f"- Aggregate score: **{float(agg.get('score') or 0.0):.4f}**",
        "",
        "## Metric families",
        "",
        "| Family | Passed | Total | Score |",
        "| --- | ---: | ---: | ---: |",
    ]
    by_family = (
        (agg.get("by_family") or {}) if isinstance(agg.get("by_family"), Mapping) else {}
    )
    for family in METRIC_FAMILIES:
        block = by_family.get(family) or {}
        lines.append(
            f"| `{family}` | {block.get('passed')} | {block.get('total')} | "
            f"{float(block.get('score') or 0.0):.4f} |"
        )

    lines.extend(["", "## Scenarios", ""])
    for item in report.get("scenarios") or []:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"### `{item.get('scenario_id')}` — "
            f"{item.get('passed')}/{item.get('total')} "
            f"(score {float(item.get('score') or 0.0):.4f})"
        )
        failed = item.get("failed_checks") or []
        if failed:
            lines.append("")
            lines.append("Failed checks:")
            for fail in failed:
                lines.append(
                    f"- `{fail.get('family')}` / `{fail.get('id')}`: {fail.get('detail')}"
                )
        else:
            lines.append("")
            lines.append("All checks passed.")
        lines.append("")

    if comparison is not None:
        lines.extend(
            [
                "## Baseline comparison (V0: visible, non-blocking)",
                "",
                f"- Baseline score: **{float(comparison.get('baseline_score') or 0.0):.4f}**",
                f"- Current score: **{float(comparison.get('current_score') or 0.0):.4f}**",
                f"- Delta: **{float(comparison.get('delta') or 0.0):+.4f}**",
                f"- Dropped scenarios: **{comparison.get('drop_count')}**",
                "",
            ]
        )
        for row in comparison.get("scenario_deltas") or []:
            flag = " DROP" if row.get("dropped") else ""
            lines.append(
                f"- `{row.get('scenario_id')}`: "
                f"{float(row.get('score') or 0.0):.4f} "
                f"(baseline {float(row.get('baseline_score') or 0.0):.4f}, "
                f"delta {float(row.get('delta') or 0.0):+.4f}){flag}"
            )
        lines.append("")

    lines.extend(
        [
            "## Interpretation",
            "",
            "- Score is the fraction of deterministic structural checks that passed.",
            "- V0 treats score drops as **visible diagnostics**, not merge blockers.",
            "- This benchmark does **not** measure market returns, alpha, or live vendor SLA.",
            "- Refresh the committed baseline only after intentional fixture/runtime changes:",
            "  `python scripts/run_agent_benchmark.py --write-baseline`.",
            "",
        ]
    )
    return "\n".join(lines)
